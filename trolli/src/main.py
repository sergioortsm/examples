from importlib.metadata import PackageNotFoundError, version
import asyncio
import logging
import os
import ssl

# Entornos corporativos con CA privada (ej. servidores SharePoint):
# flet_desktop descarga su cliente Flutter en el primer arranque via urllib/https.
# Si el servidor tiene un proxy SSL con CA no reconocida por Python, esa descarga
# falla con SSLCertVerificationError. La variable TROLLI_SKIP_SSL_VERIFY=1 parchea
# ssl antes de que flet_desktop haga la peticion.
# Solo es necesario en el primer arranque; despues queda cacheado en %LOCALAPPDATA%\flet\bin.
if os.environ.get("TROLLI_SKIP_SSL_VERIFY", "0") == "1":
    ssl._create_default_https_context = ssl._create_unverified_context

import flet as ft
from pathlib import Path
from app_layout import AppLayout
from board import Board
from user import User
from data_store import DataStore
from memory_store import InMemoryStore
from dialog import build_logs_message_dialog
from notification_banner import build_notification_banner
from logs_view import LogsView
from app_logging import (
    install_asyncio_exception_handler,
    install_global_exception_hooks,
    resolve_app_data_dir,
    setup_logging,
)
from log_buffer import LifoLogBuffer
from log_watcher import LogWatcher
from ui_tokens import (
    APP_APP_LOADING_OVERLAY,
    APP_SHELL_ACCENT,
    APP_SHELL_BG,
    APP_SURFACE_MUTED,
    APP_TEXT_ON_ACCENT,
    APP_TEXT_PRIMARY,
    CLICK_CURSOR,
    click_button_style,
)

from _logs_prefs_mixin import LogsPreferencesMixin
from _logs_cache_mixin import LogsCacheMixin
from _logs_load_mixin import LogsLoadMixin
from _logs_events_mixin import LogsEventsMixin
from _logs_watcher_mixin import LogsWatcherMixin
from _logs_export_mixin import LogsExportMixin
from _logs_detail_mixin import LogsDetailMixin
from _logs_rules_mixin import LogsRulesMixin
from settings_view import SettingsView
from search_view import SearchView
from analytics_view import AnalyticsView
from smart_rules import rules_engine as _rules_engine


logger = logging.getLogger("trolli")


class TrelloApp(
    LogsRulesMixin,
    LogsWatcherMixin,
    LogsExportMixin,
    LogsDetailMixin,
    LogsEventsMixin,
    LogsLoadMixin,
    LogsCacheMixin,
    LogsPreferencesMixin,
    AppLayout,
):
    def __init__(self, page: ft.Page, store: DataStore):
        self._page: ft.Page = page
        self.store: DataStore = store
        self.user: str | None = None
        self._fallback_storage: dict[str, object] = {}
        self._shared_preferences = ft.SharedPreferences()
        self._prefs_path = resolve_app_data_dir() / "logs_prefs.json"
        logger.info("[PREFS] logs_prefs.json path: %s", self._prefs_path)
        # Cargar reglas inteligentes desde JSON si existe
        _rules_path = resolve_app_data_dir() / "smart_rules.json"
        _rules_engine.load(_rules_path)
        self._page.on_route_change = self.route_change
        self._page.on_error = self._on_page_error
        self.boards = self.store.get_boards()
        self.logs_rows: list[dict[str, str]] = []
        # Cache en dos niveles para evitar recomputo cuando solo cambia paginacion,
        # tamano de pagina o el sentido del sort:
        #   - filter_cache: depende de (file, columns, search, level)
        #   - sort_cache: depende de filter_cache + (sort_by, sort_desc)
        # Si solo cambia sort_desc, sort_cache se obtiene con reversed() en O(n).
        self._logs_filter_cache_signature: tuple[object, ...] | None = None
        self._logs_filter_cache_rows: list[dict[str, str]] = []
        self._logs_sort_cache_signature: tuple[object, ...] | None = None
        self._logs_sort_cache_rows: list[dict[str, str]] = []
        self._logs_prefs_signature_last_saved: tuple[object, ...] | None = None
        self._logs_refresh_pending = False
        # Caché multi-dominio del motor de reglas.
        # Clave: (id(self.logs_rows), domain). Valor: (matches, src_snapshot).
        # Se limpia automáticamente cuando logs_rows es reasignado (nuevo id).
        self._rules_cache: dict[tuple, tuple[dict, list]] = {}
        self._rules_cache_rows_id: int = 0
        self.logs_state = {
            "file_path": "",
            "file_label": "Sin archivo cargado",
            "is_loading": False,
            "is_applying_columns": False,
            "columns": [],
            "col_values": {},
            "visible_columns": [],
            "visible_columns_pending": [],
            "column_selector_expanded": False,
            "level_options": ["All"],
            "search_text": "",
            "level_filters": [],
            "sort_by": None,
            "sort_desc": False,
            "page_size": 100,
            "current_page": 1,
            "total_pages": 1,
            "filtered_total": 0,
            "page_rows": [],
            "error": "",
            "message_dialog_open": False,
            "message_dialog_text": "",
            "message_dialog_title": "Detalle de Message",
            # --- modo watcher (live tailing) ---
            "watch_folder": "",
            "watch_pattern": r".+\.log$",
            "is_watching": False,
            "watch_error": "",
            "buffer_count": 0,
            "buffer_max": 100_000,
            "pending_new_count": 0,
            "lines_per_sec": 0.0,
            "live_paused": False,
            "column_filters": {},
            "timestamp_preset": "all",
            # --- motor de reglas inteligentes ---
            "active_domain": None,
            "rule_matches": {},
            "rule_matches_src": [],  # snapshot de logs_rows usado al calcular rule_matches
            "analysis_panel_open": False,
            "active_rule_id": None,  # filtro de tabla por regla concreta o "__ANY__"
            "page_global_indices": [],  # indices originales (sort cache) por slot de la pagina actual
            # --- filtros rápidos de diagnóstico ---
            "signal_filter_active": False,
            "candidate_filter_active": False,
        }
        # Buffer LIFO compartido entre el hilo del watcher y el event loop.
        self._log_buffer = LifoLogBuffer(maxlen=100_000)
        self._watcher: LogWatcher | None = None
        self._watcher_pending_batches: list[tuple[list[dict[str, str]], list[str], list[str]]] = []
        self._watcher_pending_lock = __import__("threading").Lock()
        self._watcher_drain_task: asyncio.Task | None = None
        self._watcher_lines_window: list[tuple[float, int]] = []  # (timestamp, count) ultimos 5s
        self._live_cap_logged_for_size: int | None = None  # ultima page_size para la que ya se logueo el cap
        # Throttle adaptativo del drain loop: si el ultimo render tardo X ms,
        # esperamos max(REFRESH_MS, X * 1.2) ms antes del siguiente drain para
        # romper la bola de nieve cuando el render satura.
        self._last_render_ms: float = 0.0
        self.login_profile_button = ft.PopupMenuItem(
            content="Log in",
            on_click=self.login,
            mouse_cursor=CLICK_CURSOR,
        )
        self.appbar_items = [
            self.login_profile_button,
            ft.PopupMenuItem(),  # divider
            ft.PopupMenuItem(
                content="Open SharePoint LOG",
                on_click=self.open_log_file_dialog,
                mouse_cursor=CLICK_CURSOR,
            ),
            ft.PopupMenuItem(content="Settings"),
        ]
        self.appbar_info_text = ft.Text(
            "",
            size=12,
            color=APP_TEXT_ON_ACCENT,
            opacity=0.75,
            text_align=ft.TextAlign.START,
            no_wrap=True,
            overflow=ft.TextOverflow.ELLIPSIS,
        )
        self.appbar = ft.AppBar(
            leading=ft.Icon(ft.Icons.MANAGE_SEARCH_ROUNDED, color=APP_TEXT_ON_ACCENT, size=52),
            leading_width=100,
            title=ft.Column(
                [
                    ft.Text(
                        "SharePoint ULS Log Viewer",
                        font_family="Outfit",
                        size=26,
                        color=APP_TEXT_ON_ACCENT,
                        text_align=ft.TextAlign.START,
                        no_wrap=True,
                    ),
                    self.appbar_info_text,
                ],
                spacing=0,
                tight=True,
            ),
            center_title=False,
            toolbar_height=75,
            bgcolor=APP_SHELL_ACCENT,
            actions=[
                ft.Container(
                    content=ft.PopupMenuButton(
                        items=self.appbar_items,
                        style=click_button_style(),
                    ),
                    margin=ft.margin.Margin(left=50, right=25),
                )
            ],
        )
        self._page.appbar = self.appbar
        self.file_picker = ft.FilePicker()
        if hasattr(self.file_picker, "on_result"):
            self.file_picker.on_result = self.on_log_file_selected
        self._page.services.append(self.file_picker)
        self.dir_picker = ft.FilePicker()
        self._page.services.append(self.dir_picker)
        self._page.services.append(self._shared_preferences)
        # Servicio de portapapeles (Flet 0.80+): debe estar registrado en
        # `page.services` para poder usar `page.clipboard.set(...)`.
        self._clipboard = ft.Clipboard()
        self._page.services.append(self._clipboard)
        (
            self.logs_message_dialog_title,
            self.logs_message_dialog_content,
            self.logs_message_dialog_container,
            self.logs_message_dialog,
        ) = build_logs_message_dialog(
            on_copy=self.on_logs_copy_message_detail,
            on_close=self.on_logs_close_message_detail,
        )
        self.global_loading_overlay = ft.Container(
            visible=False,
            expand=True,
            bgcolor=APP_APP_LOADING_OVERLAY,
            alignment=ft.Alignment(x=0, y=0),
            content=ft.Container(
                width=140,
                height=140,
                bgcolor=ft.Colors.TRANSPARENT,
                border=None,
                shadow=None,
                # bgcolor=APP_SURFACE,
                # border=ft.Border.all(1, APP_BORDER),
                border_radius=ft.BorderRadius(24, 24, 24, 24),
                #shadow=surface_shadow(offset_y=10, blur_radius=28),
                alignment=ft.Alignment(x=0, y=0),
                content=ft.Column(
                    [
                        ft.ProgressRing(width=56, height=56, stroke_width=5, color=APP_SHELL_ACCENT),
                        ft.Text("Cargando", size=14, weight=ft.FontWeight.W_600, color=APP_TEXT_PRIMARY),
                    ],
                    tight=True,
                    spacing=14,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    alignment=ft.MainAxisAlignment.CENTER,
                ),
            ),
        )
        self._global_loading_counter = 0
        self._global_loading_registered = False
        self._root_stack: ft.Stack | None = None
        self._restore_logs_preferences()
        self.logs_view = LogsView(self)
        self.settings_view = SettingsView(self)
        self.search_view = SearchView(self)
        self.analytics_view = AnalyticsView(self)
        self._load_candidate_patterns()

        self._page.update()
        super().__init__(
            self,
            self._page,
            self.store,
            tight=False,
            expand=True,
            vertical_alignment=ft.CrossAxisAlignment.START,
        )

    def _on_page_error(self, e):
        route = getattr(self._page, "route", "")
        event_data = getattr(e, "data", e)
        logger.error("Flet UI error | route=%s | event=%s", route, event_data)

    def _open_control(self, control: ft.Control):
        """Abre un SnackBar o AlertDialog de forma compatible con Flet 0.85.x y versiones superiores."""
        if isinstance(control, ft.SnackBar):
            # API clasica: page.snack_bar
            try:
                self._page.snack_bar = control
                control.open = True
                return
            except Exception:
                pass
            # Fallback: overlay (elimina anteriores para evitar acumulación)
            for old in list(self._page.overlay):
                if isinstance(old, ft.SnackBar):
                    self._page.overlay.remove(old)
            self._page.overlay.append(control)
            control.open = True
            return
        # AlertDialog y similares — evitar "Dialog is already opened"
        if getattr(control, "open", False):
            return
        if hasattr(self._page, "show_dialog"):
            self._page.show_dialog(control)
            return
        if control not in self._page.overlay:
            self._page.overlay.append(control)
        control.open = True

    def _close_control(self, control: ft.Control):
        """Cierra un control de forma compatible con Flet 0.85.x y versiones superiores."""
        if hasattr(control, "open"):
            control.open = False

    def _show_snack_bar(self, message: str):
        self._open_control(ft.SnackBar(ft.Text(message)))

    # ------------------------------------------------------------------
    # Notification banner (error / success)
    # ------------------------------------------------------------------

    def _show_banner(self, message: str, level: str) -> None:
        self._close_banner()  # cierra el banner anterior si lo hay
        self._active_banner = build_notification_banner(
            message=message,
            level=level,
            on_close=self._close_banner,
        )
        self._active_banner_open = True
        if hasattr(self._page, "show_dialog"):
            self._page.show_dialog(self._active_banner)
        else:
            if self._active_banner not in self._page.overlay:
                self._page.overlay.append(self._active_banner)
            self._active_banner.open = True
            self._page.update()

    def _close_banner(self, e=None) -> None:
        if not getattr(self, "_active_banner_open", False):
            return  # ya cerrado o nunca abierto
        banner = getattr(self, "_active_banner", None)
        self._active_banner = None
        self._active_banner_open = False
        if banner is None:
            return
        if hasattr(self._page, "pop_dialog"):
            try:
                self._page.pop_dialog()
                return
            except Exception:
                pass
        if hasattr(self._page, "close_dialog"):
            try:
                self._page.close_dialog(banner)
                return
            except Exception:
                pass
        banner.open = False
        self._page.update()

    def show_error(self, message: str) -> None:
        self._show_banner(message, "error")

    def show_success(self, message: str) -> None:
        self._show_banner(message, "success")

    def initialize(self):
        if not self._global_loading_registered:
            self._root_stack = ft.Stack(
                controls=[self, self.global_loading_overlay],
                expand=True,
            )
            self._global_loading_registered = True
        if self._root_stack is not None and self._root_stack not in self._page.controls:
            self._page.add(self._root_stack)
        self._page.update()
        # Restaura las preferencias de los logs al inicializar
        self._restore_logs_preferences()
        # create an initial board for demonstration if no boards
        if len(self.boards) == 0:
            self.create_new_board("My First Board")
        # Render de logs_view solo si ya está en el árbol de controles
        try:
            self.logs_view.render(self.logs_state)
        except RuntimeError:
            pass
        if self._page.route != "/logs":
            self._page.navigate("/logs")
        else:
            self.set_logs_view()

    def on_layout_resize(self, e=None):
        if self.global_loading_overlay.visible:
            self._page.update()

    def begin_global_loading(self, label: str = "Cargando archivo..."):
        self._global_loading_counter += 1
        self.global_loading_overlay.visible = True

    def end_global_loading(self):
        self._global_loading_counter = max(0, self._global_loading_counter - 1)
        if self._global_loading_counter == 0:
            self.global_loading_overlay.visible = False

    # ------------------------------------------------------------------
    # Login y gestión de boards
    # ------------------------------------------------------------------

    def login(self, e):
        def close_dlg(e):
            if user_name.value == "" or password.value == "":
                user_name.error_text = "Please provide username"
                password.error_text = "Please provide password"
                self._page.update()
                return
            else:
                user = User(user_name.value, password.value)
                if user not in self.store.get_users():
                    self.store.add_user(user)
                self.user = user_name.value
                self._storage_set("current_user", user_name.value)

            self._close_control(dialog)
            self.appbar_items[0] = ft.PopupMenuItem(
                content=f"{self._storage_get('current_user', '')}'s Profile"
            )
            self._page.update()

        user_name = ft.TextField(label="User name")
        password = ft.TextField(label="Password", password=True)
        dialog = ft.AlertDialog(
            title=ft.Text("Please enter your login credentials"),
            content=ft.Column(
                [
                    user_name,
                    password,
                    ft.Button("Login", on_click=close_dlg),
                ],
                tight=True,
            ),
            on_dismiss=lambda e: logger.debug("Modal dialog dismissed!"),
        )
        self._open_control(dialog)

    def route_change(self, e):
        troute = ft.TemplateRoute(self._page.route)
        if troute.match("/"):
            self.set_all_boards_view()
        elif troute.match("/board/:id"):
            if int(troute.id) >= len(self.store.get_boards()): # type: ignore
                self.set_all_boards_view()
                return
            self.set_board_view(int(troute.id)) # type: ignore
        elif troute.match("/boards"):
            self.set_all_boards_view()
        elif troute.match("/members"):
            self.set_members_view()
        elif troute.match("/logs"):
            self.set_logs_view()
            self.refresh_logs_view()
        elif troute.match("/settings"):
            self.set_settings_view()
        elif troute.match("/search"):
            self.set_search_view()
        elif troute.match("/analytics"):
            self.set_analytics_view()
        self._page.update()

    def add_board(self, e):
        def close_dlg(e):
            if (hasattr(e.control, "text") and not e.control.text == "Cancel") or (
                type(e.control) is ft.TextField and e.control.value != ""
            ):
                self.create_new_board(dialog_text.value)
            self._close_control(dialog)
            self._page.update()

        def textfield_change(e):
            if dialog_text.value == "":
                create_button.disabled = True
            else:
                create_button.disabled = False
            self._page.update()

        dialog_text = ft.TextField(
            label="New Board Name", on_submit=close_dlg, on_change=textfield_change
        )
        create_button = ft.Button(
            "Create", bgcolor=ft.Colors.BLUE_200, on_click=close_dlg, disabled=True
        )
        dialog = ft.AlertDialog(
            title=ft.Text("Name your new board"),
            content=ft.Column(
                [
                    dialog_text,
                    ft.Row(
                        [
                            ft.Button("Cancel", on_click=close_dlg),
                            create_button,
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                ],
                tight=True,
            ),
            on_dismiss=lambda e: logger.debug("Modal dialog dismissed!"),
        )
        self._open_control(dialog)
        self._page.update()
        dialog_text.focus()

    def create_new_board(self, board_name):
        new_board = Board(self, self.store, board_name, self._page)
        self.store.add_board(new_board)
        self.hydrate_all_boards_view()

    def delete_board(self, e):
        self.store.remove_board(e.control.data)
        self.set_all_boards_view()


def main(page: ft.Page):
    page.window.maximized = True  # Configura la ventana maximizada
    install_asyncio_exception_handler(logger)

    page.title = "Log Viewer"
    page.padding = ft.padding.Padding(left=0, top=0, right=16, bottom=0)
    page.theme = ft.Theme(font_family="Verdana")
    page.theme.tooltip_theme = ft.TooltipTheme(
        wait_duration=700,
        padding=ft.padding.Padding(left=12, top=8, right=12, bottom=8),
        text_style=ft.TextStyle(color=APP_TEXT_PRIMARY, size=12),
        decoration=ft.BoxDecoration(
            bgcolor=APP_SURFACE_MUTED,
            border_radius=ft.BorderRadius(10, 10, 10, 10),
        ),
    )
    page.theme_mode = ft.ThemeMode.LIGHT
    page.theme.page_transitions.windows = "cupertino" # type: ignore
    _pointer = click_button_style()
    page.theme.button_theme = ft.ButtonTheme(style=_pointer)
    page.theme.filled_button_theme = ft.FilledButtonTheme(style=_pointer)
    page.theme.text_button_theme = ft.TextButtonTheme(style=_pointer)
    page.theme.outlined_button_theme = ft.OutlinedButtonTheme(style=_pointer)
    page.theme.icon_button_theme = ft.IconButtonTheme(style=_pointer)
    page.fonts = {"Pacifico": "Pacifico-Regular.ttf"}
    page.bgcolor = APP_SHELL_BG
    app = TrelloApp(page, InMemoryStore())
    app.initialize()


try:
    setup_logging()    
    install_global_exception_hooks(logger)

    flet_version = version("flet")
except PackageNotFoundError:
    flet_version = "unknown"

logger.info("flet version: %s", flet_version)
logger.info("flet path: %s", ft.__file__)
ft.run(main, assets_dir="../assets")
