from __future__ import annotations


import flet as ft
import flet_datatable2 as fdt
from dialog import DialogSizer, build_column_selector_dialog
from app_logging import perf_timer
from log_service import TIMESTAMP_PRESETS, col_spec_name, col_names
from ui_tokens import APP_BORDER, APP_SURFACE, APP_SURFACE_ALT, APP_SURFACE_MUTED, APP_TEXT_MUTED, APP_TEXT_PRIMARY, surface_shadow, DROPDOWN_MENU_HEIGHT, DROPDOWN_MENU_WIDTH


class LogsView(ft.Column):
    _DEFAULT_DATA_ROW_HEIGHT = 28
    _MESSAGE_DATA_ROW_HEIGHT = 64

    # Altura ocupada por los controles fijos encima de la tabla:
    #   AppBar: 75 px  |  cabecera (title+metadata): ~58 px
    #   filters_row: ~48 px  |  chip nuevas: ~40 px  |  paginación: ~40 px
    #   4 × spacing(10) entre controles base: ~40 px
    #   page.padding vertical (top=0, bottom=0): 0 px
    # Total base (sin archivo cargado): ~301 px → 305 con margen.
    # Subir si aparece scrollbar exterior; bajar si queda espacio en blanco abajo.
    _COLUMN_FIXED_WIDTHS: dict[str, int] = {
        "Timestamp": 180,
        "Process": 110,
        "TID": 60,
        "Area": 150,
        "Category": 150,
        "EventID": 75,
        "Level": 110,
        "Correlation": 140,
        "Message": 640,
    }

    # Mapa nivel -> color de fondo (pastel medio). None => usa zebra striping.
    _LEVEL_BG_COLORS: dict[str, str | None] = {
        "CRITICAL": "#F5C0BC",
        "ERROR": "#F5C0BC",
        "HIGH": "#FAD4A8",
        "WARNING": "#FDE99A",
        "MEDIUM": "#FDE99A",
        "UNEXPECTED": "#F5C0BC",
        "MONITORABLE": "#AEDFC8",
        "INFO": None,
        "INFORMATION": None,
        "VERBOSE": None,
        "VERBOSEEX": None,
    }

    _LEVEL_COLUMN_CANDIDATES: tuple[str, ...] = ("Level", "Nivel", "LogLevel", "Severity")
    _NO_FILTER_COLUMNS: tuple[str, ...] = ("Timestamp", "TimeSpan", "Message")
    COLUMN_FILTER_DROPDOWN_THRESHOLD: int = 20

    def _row_level(self, row: dict[str, str]) -> str:
        for key in self._LEVEL_COLUMN_CANDIDATES:
            value = row.get(key)
            if value:
                return str(value).strip().upper()
        # Fallback case-insensitive si el header viene con otro casing.
        for key, value in row.items():
            if isinstance(key, str) and key.strip().lower() == "level" and value:
                return str(value).strip().upper()
        return ""

    def _row_bgcolor(self, row: dict[str, str], idx: int) -> str:
        level = self._row_level(row)
        base = self._LEVEL_BG_COLORS.get(level)
        if base is not None:
            return base
        return APP_SURFACE if idx % 2 == 0 else APP_SURFACE_ALT

    def _column_width(self, column_name: str) -> int:
        """Ancho fijo por columna, con override persistido en logs_prefs.json."""
        stored_widths = getattr(self.app, "logs_state", {}).get("column_widths", {})
        if isinstance(stored_widths, dict):
            try:
                stored = int(stored_widths.get(column_name, 0))
            except (TypeError, ValueError):
                stored = 0
            if stored > 0:
                return stored
        return self._COLUMN_FIXED_WIDTHS.get(column_name, 120)

    def _is_message_column(self, column_name: str) -> bool:
        """Devuelve True si la columna es 'Message' (insensible a mayúsculas/minúsculas)."""
        return column_name.strip().lower() == "message"

    def _scroll_to_top(self, force: bool = False) -> None:
        # El scroll del DataTable2 es interno; este método queda como no-op.
        pass

    def request_scroll_to_top(self) -> None:
        # El scroll del DataTable2 es interno; este método queda como no-op.
        pass
    
    def __init__(self, app):
        super().__init__(
            expand=True,
            spacing=10,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        )
        self.app = app
        self.column_selector_visible = False
        self._auto_follow_scroll = True

        # Row pooling: cacheamos DataTable2 + DataRow2 + handles a los Text internos
        # para evitar reconstruir 50 filas x N celdas en cada render. Solo mutamos
        # text.value y los datos referenciados por los handlers (doble tap / clic derecho).
        # Se invalida cuando cambian visible_columns o crece el numero de filas necesarias.
        self._pool_data_table: "fdt.DataTable2 | None" = None
        self._pool_visible_columns: tuple[str, ...] | None = None
        self._pool_column_widths: dict[str, int] = {}  # anchos usados al construir el pool
        self._pool_rows: list = []  # list[fdt.DataRow2]
        self._pool_row_texts: list[list[ft.Text]] = []  # [slot][col_idx] -> Text
        self._pool_row_data: list[dict[str, str]] = []  # ultima fila asignada a cada slot
        self._pool_row_decorations: list = []  # [slot] -> BoxDecoration
        self._pool_cell_containers: list[list] = []  # [slot][col_idx] -> Container
        self._pool_active_n: int = 0  # filas actualmente en uso

        # Interaction guard para filtros por columna en modo live.
        # Evita que el drain loop destruya y recree los Dropdown/TextField
        # mientras el usuario los está usando (foco activo).
        self._filter_controls_by_col: dict[str, tuple[str, ft.Control]] = {}  # col -> ("dd"|"tf", ctrl)
        self._filter_focus_count: int = 0
        self._filter_rebuild_pending_state: dict | None = None

        self.title_text = ft.Text(
            "",
            size=28,
            weight=ft.FontWeight.W_600,
            color=APP_TEXT_PRIMARY,
        )
        self.file_text = ft.Text(
            "Sin archivo cargado",
            color=APP_TEXT_MUTED,
            max_lines=1,
            no_wrap=True,
            overflow=ft.TextOverflow.ELLIPSIS,
        )
        self.status_text = ft.Text(
            "",
            color=ft.Colors.RED_600,
            max_lines=1,
            no_wrap=True,
        )
        self.metadata_row = ft.Row(
            [
                ft.Container(content=self.file_text, expand=True),
                self.status_text,
            ],
            spacing=12,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        # --- Watcher (modo live) ---------------------------------------------
        # self.watch_folder_field = ft.TextField(
        #     label="Carpeta a vigilar",
        #     hint_text=r"C:\Program Files\Common Files\Microsoft Shared\Web Server Extensions\16\LOGS",
        #     expand=True,
        #     on_change=lambda e: self.app.on_logs_watch_folder_change(e.control.value),
        # )
        # self.watch_pattern_field = ft.TextField(
        #     label="Patron (regex)",
        #     hint_text=r".+-\d{8}-\d{4}\.log$",
        #     width=240,
        #     on_change=lambda e: self.app.on_logs_watch_pattern_change(e.control.value),
        # )
        self.watch_toggle_button = ft.IconButton(
            icon=ft.Icons.PLAY_ARROW,
            icon_color=ft.Colors.GREEN_700,
            tooltip="Iniciar vigilancia en vivo",
            on_click=lambda e: self.app.on_logs_toggle_watch(),
        )
        self.watch_pause_button = ft.IconButton(
            icon=ft.Icons.PAUSE,
            icon_color=ft.Colors.AMBER_700,
            tooltip="Pausar empuje en vivo (el watcher sigue activo)",
            visible=False,
            on_click=lambda e: self.app.on_logs_toggle_live_pause(),
        )
        self.watch_status_text = ft.Text("", size=12, color=APP_TEXT_MUTED)
        # self.watch_row = ft.Row(
        #     [
        #         self.watch_folder_field,
        #         self.watch_pattern_field,
        #         self.watch_toggle_button,
        #         self.watch_status_text,
        #     ],
        #     spacing=8,
        #     vertical_alignment=ft.CrossAxisAlignment.CENTER,
        # )

        # Chip "N nuevas lineas pendientes" (auto-pausa cuando hay filtros activos)
        self.pending_new_text = ft.Text("Nuevas (0)")
        self.pending_new_button = ft.FilledTonalButton(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.ARROW_UPWARD, size=16),
                    self.pending_new_text,
                ],
                spacing=6,
                tight=True,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            on_click=lambda e: self.app.on_logs_show_pending_new(),
            visible=False,
        )

        self.search_field = ft.TextField(
            label="Buscar",
            hint_text="Texto libre en todas las columnas",
            width=320,
            on_change=lambda e: self.app.on_logs_search_change(e.control.value),
        )
        self.sort_dropdown = ft.Dropdown(
            width=240,
            label="Ordenar por",
            options=[],
            menu_height=DROPDOWN_MENU_HEIGHT,
            menu_width=DROPDOWN_MENU_WIDTH,
            on_select=lambda e: self.app.on_logs_sort_column_change(e.control.value),
        )
        self.sort_direction_button = ft.IconButton(
            icon=ft.Icons.ARROW_DOWNWARD,
            tooltip="Alternar orden asc/desc",
            on_click=lambda e: self.app.on_logs_toggle_sort_direction(),
        )

        self.page_size_dropdown = ft.Dropdown(
            width=160,
            label="Filas por pagina",
            value="100",
            options=[ft.dropdown.Option("50"), ft.dropdown.Option("100"), ft.dropdown.Option("250")],
            menu_height=DROPDOWN_MENU_HEIGHT,
            menu_width=DROPDOWN_MENU_WIDTH,
            margin=ft.Margin(left=0, top=8, right=0, bottom=0),
            on_select=lambda e: self.app.on_logs_page_size_change(e.control.value),
        )

        self.prev_page_button = ft.IconButton(
            icon=ft.Icons.CHEVRON_LEFT,
            tooltip="Pagina anterior",
            mouse_cursor=ft.MouseCursor.CLICK,
            style=ft.ButtonStyle(
                bgcolor={
                    ft.ControlState.DEFAULT: ft.Colors.BLUE_GREY_100,
                    ft.ControlState.HOVERED: ft.Colors.BLUE_GREY_200,
                    ft.ControlState.DISABLED: ft.Colors.TRANSPARENT,
                },
                shape=ft.RoundedRectangleBorder(radius=8),
            ),
            on_click=lambda e: self.app.on_logs_prev_page(),
        )
        self.next_page_button = ft.IconButton(
            icon=ft.Icons.CHEVRON_RIGHT,
            tooltip="Pagina siguiente",
            mouse_cursor=ft.MouseCursor.CLICK,
            style=ft.ButtonStyle(
                bgcolor={
                    ft.ControlState.DEFAULT: ft.Colors.BLUE_GREY_100,
                    ft.ControlState.HOVERED: ft.Colors.BLUE_GREY_200,
                    ft.ControlState.DISABLED: ft.Colors.TRANSPARENT,
                },
                shape=ft.RoundedRectangleBorder(radius=8),
            ),
            on_click=lambda e: self.app.on_logs_next_page(),
        )
        self.page_info_text = ft.Text("Pagina 1 / 1")

        self.column_selector = ft.Row(
            [],
            spacing=2,
            wrap=True,
            run_spacing=2,
            scroll=ft.ScrollMode.AUTO,
        )
        self.toggle_column_selector_button = ft.IconButton(
            icon=ft.Icons.VIEW_COLUMN,
            tooltip="Columnas visibles",
            mouse_cursor=ft.MouseCursor.CLICK,
            on_click=lambda e: self.app.on_logs_toggle_column_selector(),
        )
        # Botón icono de filtro por Level (visible solo cuando la columna Level está activa)
        self._level_filter_dialog: ft.AlertDialog | None = None
        self.level_filter_button = ft.IconButton(
            icon=ft.Icons.FILTER_ALT,
            tooltip="Filtrar por nivel",
            visible=False,
            mouse_cursor=ft.MouseCursor.CLICK,
            on_click=lambda e: self._on_level_filter_btn_click(e),
        )
        self.open_log_button = ft.IconButton(
            icon=ft.Icons.FOLDER_OPEN,
            tooltip="Abrir .log",
            mouse_cursor=ft.MouseCursor.CLICK,
            on_click=self.app.open_log_file_dialog,
        )
        self.clear_buffer_button = ft.IconButton(
            icon=ft.Icons.DELETE_SWEEP,
            tooltip="Limpiar todos los datos del listado",
            mouse_cursor=ft.MouseCursor.CLICK,
            on_click=lambda e: self.app.on_logs_clear_buffer(),
        )
        self.export_csv_button = ft.IconButton(
            icon=ft.Icons.DOWNLOAD,
            tooltip="Exportar CSV",
            mouse_cursor=ft.MouseCursor.CLICK,
            on_click=lambda e: self.app.on_logs_export_click(),
        )
        self._apply_btn_icon = ft.Icon(ft.Icons.CHECK_CIRCLE, size=18)
        self._apply_btn_ring = ft.ProgressRing(width=14, height=14, stroke_width=2, visible=False)
        self.apply_columns_button = ft.Button(
            content=ft.Row(
                [self._apply_btn_ring, self._apply_btn_icon, ft.Text("Aplicar")],
                tight=True,
                spacing=6,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            on_click=lambda e: self.app.on_logs_apply_columns(),
            disabled=True,
        )
        self.apply_columns_status = ft.Row(
            [],
            spacing=6,
            visible=False,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
        (
            self.column_selector_dialog_container,
            self.column_selector_dialog,
        ) = build_column_selector_dialog(
            column_selector=self.column_selector,
            apply_columns_status=self.apply_columns_status,
            apply_columns_button=self.apply_columns_button,
            on_close=self._close_column_selector,
            show_close_button=True,
        )

        # Inicializacion de contenedores de tabla y overlay de carga.
        # height=600 es valor inicial; se sobreescribe en update_table_height() cuando
        # la página notifica su altura real (on_resize y al montar la vista).
        self.table_content_container = ft.Container(
            padding=ft.padding.Padding(left=8, top=8, right=8, bottom=8),
            expand=True,
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
        )
        self.table_surface = ft.Container(
            content=self.table_content_container,
            expand=True,
            bgcolor=APP_SURFACE,
            border=ft.Border.all(1, APP_BORDER),
            border_radius=ft.BorderRadius(16, 16, 16, 16),
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
            shadow=surface_shadow(),
        )

        # Botón de filtro de periodo (popup de presets de tiempo)
        self._timestamp_preset_key: str = "all"
        self.timestamp_preset_button = ft.PopupMenuButton(
            icon=ft.Icons.SCHEDULE,
            tooltip="Periodo",
            items=[
                ft.PopupMenuItem(
                    content=ft.Text(v),
                    on_click=lambda e, k=k: self.app.on_logs_timestamp_preset_change(k),
                )
                for k, v in TIMESTAMP_PRESETS.items()
            ],
        )

        # Fila de busqueda y controles de watcher (ocupa todo el ancho)
        self.filters_row = ft.Row(
            [
                self.search_field,
                self.watch_toggle_button,
                self.watch_pause_button,
                self.watch_status_text,
            ],
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        self.column_filters_row = ft.Row(
            [],
            spacing=8,
            wrap=True,
            run_spacing=4,
            visible=False,
        )

        # ── Perfil de detección inteligente ─────────────────────────────────
        from smart_rules import ALL_DOMAINS
        self.profile_dropdown = ft.Dropdown(
            width=170,
            hint_text="Perfil",
            value="",
            options=[ft.dropdown.Option(key="", text="Sin perfil")]
            + [ft.dropdown.Option(key=d, text=d) for d in ALL_DOMAINS],
            menu_height=DROPDOWN_MENU_HEIGHT,
            menu_width=DROPDOWN_MENU_WIDTH,
            margin=ft.Margin(left=0, top=8, right=0, bottom=0),
            on_select=lambda e: self.app.on_profile_change(e.control.value or None),
        )
        self.analysis_toggle_button = ft.IconButton(
            icon=ft.Icons.ANALYTICS_OUTLINED,
            tooltip="Mostrar / ocultar panel de análisis",
            mouse_cursor=ft.MouseCursor.CLICK,
            visible=False,
            on_click=lambda e: self.app.on_logs_toggle_analysis_panel(),
        )
        # Botón Señal: filtra rápidamente por niveles de error/excepción
        self.signal_filter_button = ft.IconButton(
            icon=ft.Icons.BOLT,
            tooltip="Señal: filtrar niveles de error/excepción",
            visible=False,
            mouse_cursor=ft.MouseCursor.CLICK,
            on_click=lambda e: self.app.on_logs_signal_filter_toggle(),
        )
        # Botón Candidatos: filtra por patrones de candidates.json
        self.candidate_filter_button = ft.IconButton(
            icon=ft.Icons.SAVED_SEARCH,
            tooltip="Candidatos: filtrar por patrones conocidos",
            mouse_cursor=ft.MouseCursor.CLICK,
            on_click=lambda e: self.app.on_logs_candidate_filter_toggle(),
        )
        # Botón de carga por directorio (logs modificados en la última hora)
        self.open_dir_button = ft.IconButton(
            icon=ft.Icons.FOLDER_SPECIAL,
            tooltip="Cargar todos los .log del directorio",
            mouse_cursor=ft.MouseCursor.CLICK,
            on_click=self.app.open_log_directory_dialog,
        )
        # Panel de análisis de reglas (colapsable; visible cuando hay matches)
        self.analysis_chips_row = ft.Row([], wrap=True, spacing=6, run_spacing=4)
        self.analysis_total_text = ft.Text(
            "", size=11, weight=ft.FontWeight.W_600, color=APP_TEXT_PRIMARY
        )
        self.analysis_panel = ft.Container(
            visible=False,
            bgcolor=APP_SURFACE_MUTED,
            border=ft.Border.all(1, APP_BORDER),
            border_radius=ft.BorderRadius(8, 8, 8, 8),
            padding=ft.padding.Padding(left=12, top=8, right=12, bottom=8),
            content=ft.Column(
                [self.analysis_total_text, self.analysis_chips_row],
                spacing=6,
                tight=True,
            ),
        )

        self.controls = [
            ft.Row(
                [
                    self.timestamp_preset_button,
                    self.level_filter_button,
                    self.toggle_column_selector_button,
                    self.open_log_button,
                    self.open_dir_button,
                    self.export_csv_button,
                    self.clear_buffer_button,
                    self.profile_dropdown,
                    self.analysis_toggle_button,
                    self.signal_filter_button,
                    self.candidate_filter_button,
                    ft.Row([], expand=True),
                    self.page_size_dropdown,
                    ft.Row(
                        [self.prev_page_button, self.page_info_text, self.next_page_button],
                        spacing=4,
                        tight=True,
                    ),
                ],
                spacing=4,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            self.filters_row,
            self.column_filters_row,
            self.analysis_panel,
            ft.Row(
                [self.pending_new_button],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            self.table_surface,
        ]

    def _close_column_selector(self):
        # Oculta el panel selector de columnas
        self.app.logs_state["column_selector_expanded"] = False
        self.refresh_column_selector(self.app.logs_state)

    def render(self, state: dict):
        page_rows_count = len(state.get("page_rows", []))
        import time as _time
        _t0 = _time.perf_counter()
        with perf_timer("logs_view.render", rows=page_rows_count):
            self._render_impl(state)
        elapsed_ms = (_time.perf_counter() - _t0) * 1000.0
        # Reportar al app para que el drain loop ajuste su cadencia.
        try:
            self.app._last_render_ms = elapsed_ms
        except AttributeError:
            pass

    def _render_impl(self, state: dict):
        file_label = state.get("file_label", "")
        self.file_text.value = file_label

        error = state.get("error", "")
        if error:
            self.status_text.value = ""
            _info = file_label or "Sin archivo cargado"
        else:
            total = state.get("filtered_total", 0)
            self.status_text.value = f"Registros filtrados: {total}"
            self.status_text.color = ft.Colors.GREEN_800
            if file_label:
                import os as _os
                _info = f"Archivo: {_os.path.basename(file_label)}  ·  Registros filtrados: {total}"
            else:
                _info = "Sin archivo cargado"

        try:
            self.app.appbar_info_text.value = _info
        except AttributeError:
            pass

        self.search_field.value = state.get("search_text", "")

        columns = state.get("columns", [])
        sort_options = [ft.dropdown.Option(column) for column in columns]
        self.sort_dropdown.options = sort_options
        sort_by = state.get("sort_by")
        self.sort_dropdown.value = sort_by if sort_by in columns else None

        sort_desc = bool(state.get("sort_desc", False))
        self.sort_direction_button.icon = (
            ft.Icons.ARROW_DOWNWARD if sort_desc else ft.Icons.ARROW_UPWARD
        )

        page_size = str(state.get("page_size", 100))
        self.page_size_dropdown.value = page_size if page_size in {"50", "100", "250"} else "100"

        current_page = state.get("current_page", 1)
        total_pages = state.get("total_pages", 1)
        self.page_info_text.value = f"Pagina {current_page} / {total_pages}"
        is_loading = bool(state.get("is_loading", False))
        self.prev_page_button.disabled = is_loading or current_page <= 1
        self.next_page_button.disabled = is_loading or current_page >= total_pages

        # --- watcher ---
        is_watching = bool(state.get("is_watching", False))
        live_paused = bool(state.get("live_paused", False))
        # self.watch_folder_field.value = state.get("watch_folder", "")
        # self.watch_pattern_field.value = state.get("watch_pattern", "")
        # self.watch_folder_field.disabled = is_watching
        # self.watch_pattern_field.disabled = is_watching
        if is_watching:
            self.watch_toggle_button.icon = ft.Icons.STOP
            self.watch_toggle_button.icon_color = ft.Colors.RED_700
            self.watch_toggle_button.tooltip = "Detener vigilancia"
        else:
            self.watch_toggle_button.icon = ft.Icons.PLAY_ARROW
            self.watch_toggle_button.icon_color = ft.Colors.GREEN_700
            self.watch_toggle_button.tooltip = "Iniciar vigilancia en vivo"
        # Botón Pausa: solo visible cuando el watcher está activo
        self.watch_pause_button.visible = is_watching
        if is_watching:
            if live_paused:
                self.watch_pause_button.icon = ft.Icons.PLAY_CIRCLE
                self.watch_pause_button.icon_color = ft.Colors.GREEN_700
                self.watch_pause_button.tooltip = "Reanudar empuje en vivo"
            else:
                self.watch_pause_button.icon = ft.Icons.PAUSE
                self.watch_pause_button.icon_color = ft.Colors.AMBER_700
                self.watch_pause_button.tooltip = "Pausar empuje en vivo (el watcher sigue activo)"
        self.open_log_button.disabled = is_watching
        self.open_dir_button.disabled = is_watching
        signal_active = bool(state.get("signal_filter_active", False))
        self.signal_filter_button.icon_color = ft.Colors.PRIMARY if signal_active else None
        candidate_active = bool(state.get("candidate_filter_active", False))
        self.candidate_filter_button.icon_color = ft.Colors.PRIMARY if candidate_active else None
        self.candidate_filter_button.disabled = not bool(state.get("columns"))
        self.export_csv_button.disabled = is_watching and not live_paused
        watch_error = state.get("watch_error", "")
        if watch_error:
            self.watch_status_text.value = watch_error
            self.watch_status_text.color = ft.Colors.RED_600
        elif is_watching:
            rate = state.get("lines_per_sec", 0.0)
            buf = state.get("buffer_count", 0)
            buf_max = state.get("buffer_max", 0)
            paused_label = " ⏸ PAUSADO" if live_paused else ""
            self.watch_status_text.value = (
                f"En vivo{paused_label} · buffer {buf}/{buf_max} · {rate:.0f} l/s"
            )
            self.watch_status_text.color = ft.Colors.AMBER_800 if live_paused else ft.Colors.GREEN_800
        else:
            self.watch_status_text.value = ""

        pending_new = int(state.get("pending_new_count", 0))
        if pending_new > 0:
            self.pending_new_text.value = f"Nuevas ({pending_new})"
            self.pending_new_button.visible = True
        else:
            self.pending_new_text.value = "Nuevas (0)"
            self.pending_new_button.visible = False

        # ── Perfil de reglas inteligentes ────────────────────────────────────
        active_domain = state.get("active_domain")
        self.profile_dropdown.value = active_domain or ""
        self.analysis_toggle_button.visible = bool(active_domain)
        self.analysis_toggle_button.icon_color = (
            ft.Colors.PRIMARY if state.get("analysis_panel_open") else None
        )
        self._render_analysis_panel(state)

        self._render_column_selector(state)
        self._refresh_column_filters_controls(state)
        self._render_table(state)

        # El refresco global lo hace la app con page.update().
        # Evita AssertionError cuando la vista aun no esta montada.
        if getattr(self, "page", None) is not None:
            self.update()

    def _render_column_selector(self, state: dict):
        columns = state.get("columns", [])
        pending_specs: list[dict] = list(state.get("visible_columns_pending", state.get("visible_columns", [])))
        # Normalizar: si hay strings antiguos los tratamos como specs con filter=True
        pending_specs = [s if isinstance(s, dict) else {"name": s, "filter": True} for s in pending_specs]
        pending_names = set(col_spec_name(s) for s in pending_specs)
        # Mapa name -> spec para consultas rápidas
        pending_map: dict[str, dict] = {col_spec_name(s): s for s in pending_specs}
        applied_columns = col_names(list(state.get("visible_columns", [])))
        self.column_selector_visible = bool(state.get("column_selector_expanded", False))
        is_applying = bool(state.get("is_applying_columns", False))
        is_busy = bool(state.get("is_loading", False)) or is_applying

        def _filter_icon(col_name: str) -> str:
            spec = pending_map.get(col_name)
            if spec is None:
                return ft.Icons.FILTER_ALT_OFF
            return ft.Icons.FILTER_ALT if spec.get("filter", True) else ft.Icons.FILTER_ALT_OFF

        def _filter_color(col_name: str):
            spec = pending_map.get(col_name)
            if spec and spec.get("filter", True):
                return ft.Colors.PRIMARY
            return ft.Colors.BLUE_GREY_300

        self.column_selector.controls = [
            ft.Container(
                width=178,
                padding=ft.padding.Padding(left=0, top=0, right=0, bottom=0),
                content=ft.Row(
                    [
                        ft.IconButton(
                            icon=_filter_icon(column),
                            icon_size=16,
                            icon_color=_filter_color(column),
                            tooltip="Mostrar en barra de filtros" if (pending_map.get(column) or {}).get("filter", True) is False else "Ocultar de barra de filtros",
                            disabled=is_busy or column not in pending_names,
                            style=ft.ButtonStyle(
                                padding=ft.padding.Padding(left=2, top=0, right=2, bottom=0),
                            ),
                            on_click=lambda e, col=column: self.app.on_logs_toggle_column_filter(
                                col, not (pending_map.get(col) or {}).get("filter", True)
                            ),
                        ),
                        ft.GestureDetector(
                            mouse_cursor=ft.MouseCursor.CLICK,
                            content=ft.Checkbox(
                                value=column in pending_names,
                                disabled=is_busy,
                                scale=0.9,
                                on_change=lambda e, col=column: self.app.on_logs_toggle_column(col, bool(e.control.value)),
                            ),
                        ),
                        ft.Container(
                            width=112,
                            content=ft.Text(
                                column,
                                size=12,
                                max_lines=1,
                                no_wrap=True,
                                overflow=ft.TextOverflow.ELLIPSIS,
                            ),
                        ),
                    ],
                    spacing=2,
                    tight=True,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            )
            for column in columns
        ]

        has_columns = len(columns) > 0
        self.toggle_column_selector_button.disabled = (not has_columns) or is_busy
        self.apply_columns_button.disabled = (not has_columns) or is_busy or (pending_specs == [s if isinstance(s, dict) else {"name": s, "filter": True} for s in state.get("visible_columns", [])])
        self._apply_btn_ring.visible = is_applying
        self._apply_btn_icon.visible = not is_applying
        self.apply_columns_status.visible = False
        if not has_columns:
            self.column_selector_visible = False
        self._sync_column_selector_visibility()

    def refresh_column_selector(self, state: dict):
        # Refresco ligero para evitar reconstruir la tabla completa en cada checkbox.
        self._render_column_selector(state)
        if getattr(self, "page", None) is not None:
            self.update()

    def refresh_table_only(self, state: dict):
        # Refresco acotado del area de tabla para evitar re-render global innecesario.
        with perf_timer("logs_view.refresh_table_only", rows=len(state.get("page_rows", []))):
            self._render_table(state)
            if getattr(self, "page", None) is not None:
                self.update()

    def _on_level_filter_btn_click(self, e) -> None:
        """Abre el diálogo de selección múltiple de niveles."""
        if self._level_filter_dialog is not None:
            self.app._open_control(self._level_filter_dialog)
            _p = getattr(self, "page", None)
            if _p is not None:
                _p.update()

    def _on_level_filter_dlg_close(self) -> None:
        """Cierra el diálogo de filtro de nivel."""
        if self._level_filter_dialog is not None:
            self.app._close_control(self._level_filter_dialog)
        _p = getattr(self, "page", None)
        if _p is not None:
            _p.update()

    def _build_column_filters_row(self, state: dict) -> list[ft.Control]:
        """Construye la lista de controles de filtro para cada columna visible.

        Reutiliza los mismos objetos ft.Dropdown/ft.TextField por columna para que
        Flutter los actualice in-place en lugar de destruirlos y recrearlos en cada
        drain del watcher. Esto evita que el control se cierre/pierda el foco mientras
        el usuario interactua con el en modo Vivo.
        """
        visible_specs = state.get("visible_columns", [])
        col_values = state.get("col_values", {}) or {}
        column_filters = state.get("column_filters", {}) or {}
        controls: list[ft.Control] = []
        visible_set = set(col_spec_name(s) for s in visible_specs)
        for spec in visible_specs:
            col = col_spec_name(spec)
            filter_on = spec.get("filter", True) if isinstance(spec, dict) else True
            vals = col_values.get(col, []) if isinstance(col_values, dict) else []

            # --- Columnas sin filtro por diseño: Timestamp, TimeSpan, Message ---
            if col in self._NO_FILTER_COLUMNS:
                continue

            # --- Columnas marcadas explícitamente como sin filtro por el usuario ---
            if not filter_on:
                # Columna marcada sin filtro: ocultar botón de Level si aplica y saltar.
                if col in self._LEVEL_COLUMN_CANDIDATES:
                    self.level_filter_button.visible = False
                    self.signal_filter_button.visible = False
                continue

            # --- Caso especial: columna Level → botón icono en filters_row + diálogo ---
            # Level NUNCA cae al bloque general (evita Dropdown vacío al arrancar watcher
            # cuando col_values aún está vacío pero visible_columns ya tiene Level).
            if col in self._LEVEL_COLUMN_CANDIDATES:
                if isinstance(vals, list) and vals:
                    level_filters_set = set(state.get("level_filters") or [])
                    current_vals_key = frozenset(vals)
                    existing = self._filter_controls_by_col.get(col)
                    if (existing is not None
                            and existing[0] == "cb_level_dd"
                            and len(existing) >= 3
                            and existing[2] == current_vals_key):
                        # ── REUTILIZAR: actualizar checkboxes in-place ──
                        for cb in existing[1]:
                            if hasattr(cb, "data"):
                                cb.value = cb.data in level_filters_set
                    else:
                        # ── CREAR: cerrar diálogo anterior si existía ──
                        if self._level_filter_dialog is not None:
                            self.app._close_control(self._level_filter_dialog)
                            _p = getattr(self, "page", None)
                            if _p is not None and self._level_filter_dialog in _p.overlay:
                                _p.overlay.remove(self._level_filter_dialog)
                        checkboxes = [
                            ft.Checkbox(
                                label=v,
                                value=v in level_filters_set,
                                data=v,
                                on_change=lambda e, lv=v: self.app.on_logs_level_toggle(lv, bool(e.control.value)),
                            )
                            for v in vals
                        ]
                        self._level_filter_dialog = ft.AlertDialog(
                            title=ft.Row(
                                [ft.Icon(ft.Icons.FILTER_LIST, size=18), ft.Text("Filtrar por nivel")],
                                spacing=8,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            ),
                            content=ft.Column(controls=checkboxes, tight=True, spacing=4),
                            actions=[ft.TextButton("Cerrar", on_click=lambda e: self._on_level_filter_dlg_close())],
                            actions_alignment=ft.MainAxisAlignment.END,
                            on_dismiss=lambda e: None,
                        )
                        self._filter_controls_by_col[col] = ("cb_level_dd", checkboxes, current_vals_key)
                    # Actualizar visibilidad y color del botón según filter_on
                    self.level_filter_button.visible = filter_on
                    self.signal_filter_button.visible = filter_on
                    self.level_filter_button.icon_color = ft.Colors.PRIMARY if level_filters_set else None
                else:
                    # Level en visible_columns pero sin valores aún (watcher arrancando)
                    self.level_filter_button.visible = False
                    self.signal_filter_button.visible = False
                continue  # Level NUNCA cae al bloque general de columnas

            # --- Resto de columnas: Dropdown o TextField ---
            current_val = column_filters.get(col, "") or ""
            required_type = "dd" if isinstance(vals, list) and len(vals) <= self.COLUMN_FILTER_DROPDOWN_THRESHOLD else "tf"
            existing = self._filter_controls_by_col.get(col)
            if existing is not None and existing[0] == required_type:
                # Reusar el control existente: solo mutar propiedades, no recrear
                ctrl = existing[1]
                if required_type == "dd":
                    ctrl.options = [ft.dropdown.Option(key="", text="(todos)")] + [
                        ft.dropdown.Option(v) for v in vals
                    ]  # type: ignore[union-attr]
                    ctrl.value = current_val
                else:
                    ctrl.value = current_val  # type: ignore[union-attr]
            else:
                # Crear control nuevo (primera vez o cambio de tipo dd<->tf)
                if required_type == "dd":
                    ctrl = ft.Dropdown(
                        label=col,
                        width=160,
                        options=[ft.dropdown.Option(key="", text="(todos)")] + [
                            ft.dropdown.Option(v) for v in vals
                        ],
                        value=current_val,
                        menu_height=DROPDOWN_MENU_HEIGHT,
                        menu_width=DROPDOWN_MENU_WIDTH,
                        on_select=lambda e, c=col: self.app.on_logs_column_filter_change(
                            c, e.control.value or ""
                        ),
                        on_focus=self._on_filter_focus,
                        on_blur=self._on_filter_blur,
                    )
                else:
                    ctrl = ft.TextField(
                        label=col,
                        width=160,
                        value=current_val,
                        on_change=lambda e, c=col: self.app.on_logs_column_filter_change(
                            c, e.control.value or ""
                        ),
                        on_focus=self._on_filter_focus,
                        on_blur=self._on_filter_blur,
                    )
                self._filter_controls_by_col[col] = (required_type, ctrl)
            controls.append(ctrl)
        # Limpiar referencias a columnas que ya no son visibles
        stale = [c for c in self._filter_controls_by_col if c not in visible_set]
        for c in stale:
            entry = self._filter_controls_by_col[c]
            if entry[0] == "cb_level_dd":
                if self._level_filter_dialog is not None:
                    self.app._close_control(self._level_filter_dialog)
                    _p = getattr(self, "page", None)
                    if _p is not None and self._level_filter_dialog in _p.overlay:
                        _p.overlay.remove(self._level_filter_dialog)
                    self._level_filter_dialog = None
                self.level_filter_button.visible = False
                self.signal_filter_button.visible = False
            del self._filter_controls_by_col[c]
        # Si ningún spec de Level tiene filter=True, ocultar el botón
        has_active_level_filter = any(
            col_spec_name(s) in self._LEVEL_COLUMN_CANDIDATES and (s.get("filter", True) if isinstance(s, dict) else True)
            for s in visible_specs
        )
        if not has_active_level_filter:
            self.level_filter_button.visible = False
            self.signal_filter_button.visible = False
        return controls

    def _on_filter_focus(self, e) -> None:
        """Incrementa el contador de filtros con foco activo."""
        self._filter_focus_count += 1

    def _on_filter_blur(self, e) -> None:
        """Decrementa el contador de foco; si llega a 0 aplica rebuild diferido."""
        self._filter_focus_count = max(0, self._filter_focus_count - 1)
        if self._filter_focus_count == 0 and self._filter_rebuild_pending_state is not None:
            pending = self._filter_rebuild_pending_state
            self._filter_rebuild_pending_state = None
            self._refresh_column_filters_controls(pending)
            if getattr(self, "page", None) is not None:
                self.column_filters_row.update()

    def _refresh_column_filters_controls(self, state: dict) -> None:
        """Reconstruye controles de filtros por columna sin llamar a update()."""
        if self._filter_focus_count > 0:
            # Un filtro tiene el foco: diferir el rebuild para no interrumpir la interaccion
            self._filter_rebuild_pending_state = state
            return
        visible_columns = state.get("visible_columns", [])
        has_columns = bool(state.get("columns", []))
        _preset = state.get("timestamp_preset", "all") or "all"
        self._timestamp_preset_key = _preset
        self.timestamp_preset_button.icon_color = ft.Colors.PRIMARY if _preset != "all" else None
        self.column_filters_row.controls = self._build_column_filters_row(state)
        self.column_filters_row.visible = bool(self.column_filters_row.controls)

    def refresh_column_filters(self, state: dict) -> None:
        """Reconstruye controles de filtros por columna y refresca la UI."""
        self._refresh_column_filters_controls(state)
        if getattr(self, "page", None) is not None:
            self.update()

    def _level_options_from_state(self, state: dict) -> list[str]:
        col_values = state.get("col_values", {}) or {}
        if isinstance(col_values, dict):
            level_values = col_values.get("Level")
            if isinstance(level_values, list) and level_values:
                return ["All"] + level_values
        level_options = state.get("level_options", ["All"])
        return level_options if isinstance(level_options, list) and level_options else ["All"]

    def refresh_pending_chip_and_status(self, state: dict):
        # Refresco ultraligero para auto-pausa del watcher: solo chip y status.
        # Evita repintar tabla / selector de columnas en cada drain (cada 250ms)
        # cuando hay filtros activos o el usuario no esta en pagina 1.
        pending_new = int(state.get("pending_new_count", 0))
        if pending_new > 0:
            self.pending_new_text.value = f"Nuevas ({pending_new})"
            self.pending_new_button.visible = True
        else:
            self.pending_new_text.value = "Nuevas (0)"
            self.pending_new_button.visible = False

        is_watching = bool(state.get("is_watching", False))
        live_paused = bool(state.get("live_paused", False))
        watch_error = state.get("watch_error", "")
        if watch_error:
            self.watch_status_text.value = watch_error
            self.watch_status_text.color = ft.Colors.RED_600
        elif is_watching:
            rate = state.get("lines_per_sec", 0.0)
            buf = state.get("buffer_count", 0)
            buf_max = state.get("buffer_max", 0)
            paused_label = " ⏸ PAUSADO" if live_paused else ""
            self.watch_status_text.value = (
                f"En vivo{paused_label} · buffer {buf}/{buf_max} · {rate:.0f} l/s"
            )
            self.watch_status_text.color = ft.Colors.AMBER_800 if live_paused else ft.Colors.GREEN_800
        else:
            self.watch_status_text.value = ""

        # Sincronizar icono del botón de pausa (puede cambiar sin render completo)
        if is_watching:
            if live_paused:
                self.watch_pause_button.icon = ft.Icons.PLAY_CIRCLE
                self.watch_pause_button.icon_color = ft.Colors.GREEN_700
                self.watch_pause_button.tooltip = "Reanudar empuje en vivo"
            else:
                self.watch_pause_button.icon = ft.Icons.PAUSE
                self.watch_pause_button.icon_color = ft.Colors.AMBER_700
                self.watch_pause_button.tooltip = "Pausar empuje en vivo (el watcher sigue activo)"

        if getattr(self, "page", None) is not None:
            # Solo refrescamos los controles afectados para minimizar diffs WS.
            try:
                self.pending_new_button.update()
                self.watch_status_text.update()
                self.watch_pause_button.update()
            except (AssertionError, RuntimeError):
                pass

    def refresh_loading_state(self, state: dict):
        # Refresco ligero para estado de paginacion sin reconstruir la tabla.
        current_page = state.get("current_page", 1)
        total_pages = state.get("total_pages", 1)
        self.page_info_text.value = f"Pagina {current_page} / {total_pages}"
        is_loading = bool(state.get("is_loading", False))
        self.prev_page_button.disabled = is_loading or current_page <= 1
        self.next_page_button.disabled = is_loading or current_page >= total_pages
        if getattr(self, "page", None) is not None:
            self.update()

    def _update_column_selector_dialog_size(self):
        page = getattr(self, "page", None)
        if page is None:
            return

        DialogSizer.fit_container(
            page,
            self.column_selector_dialog_container,
            width_ratio=0.41,
            min_width=260,
            max_width=490,
            height_ratio=0.36,
            min_height=160,
            max_height=350,
        )

    def _sync_column_selector_visibility(self):
        page = getattr(self, "page", None)
        if page is not None:
            if self.column_selector_visible:
                self._update_column_selector_dialog_size()
                opener = getattr(page, "open", None)
                if callable(opener) and not getattr(self.column_selector_dialog, "open", False):
                    opener(self.column_selector_dialog)
                elif not callable(opener):
                    if self.column_selector_dialog not in page.overlay:
                        page.overlay.append(self.column_selector_dialog)
                    self.column_selector_dialog.open = True
                    page.update()
            else:
                closer = getattr(page, "close", None)
                if callable(closer):
                    closer(self.column_selector_dialog)
                else:
                    self.column_selector_dialog.open = False
                    page.update()
        # Mantener icono estable para evitar dos botones de cierre simultaneos.
        self.toggle_column_selector_button.icon = ft.Icons.VIEW_COLUMN
        self.toggle_column_selector_button.tooltip = "Columnas visibles"

    def _invalidate_table_pool(self):
        self._pool_data_table = None
        self._pool_visible_columns = None
        self._pool_column_widths = {}
        self._pool_rows = []
        self._pool_row_texts = []
        self._pool_row_data = []
        self._pool_row_decorations = []
        self._pool_cell_containers = []
        self._pool_active_n = 0

    def _build_table_pool(self, visible_columns: list[str], pool_size: int):
        """Construye una unica vez el DataTable2 con `pool_size` DataRow2 reutilizables.

        Cada celda contiene un ft.Text cuyo handle guardamos en `_pool_row_texts[slot][col_idx]`.
        Los handlers de doble tap / clic derecho leen la fila actual desde `_pool_row_data[slot]`,
        asi no hay que reasignar lambdas en cada render.
        """
        cols_tuple = tuple(visible_columns)
        specific_height = None

        # Columnas (cabeceras)
        def _make_sort_handler(col_name: str):
            def _on_sort(e: ft.DataColumnSortEvent) -> None:
                self.app.on_logs_sort_by_header(col_name, e.ascending)
            return _on_sort

        data_table_columns = []
        last_col_idx = len(visible_columns) - 1
        for idx, column in enumerate(visible_columns):
            is_last = idx == last_col_idx
            data_table_columns.append(
                fdt.DataColumn2(
                    label=ft.Container(
                        content=ft.Text(
                            column,
                            size=12,
                            weight=ft.FontWeight.W_600,
                            color=APP_TEXT_MUTED,
                        ),
                        alignment=ft.Alignment(x=-1, y=0),
                        padding=ft.padding.Padding(left=4, top=10, right=4, bottom=10),
                    ),
                    fixed_width=None if is_last else self._column_width(column),
                    size=fdt.DataColumnSize.L if is_last else None,
                    on_sort=_make_sort_handler(column),
                )
            )

        # Filas (pool)
        pool_rows: list = []
        pool_texts: list[list[ft.Text]] = []
        pool_data: list[dict[str, str]] = [{} for _ in range(pool_size)]
        pool_decorations: list = []
        pool_cell_containers: list[list] = []

        def _make_double_tap(slot: int):
            return lambda e: self.app.on_logs_open_message_detail(
                self._pool_row_data[slot], list(self._pool_visible_columns or [])
            )

        def _make_secondary_tap(slot: int):
            return lambda e: self.app.on_logs_copy_row(
                self._pool_row_data[slot], list(self._pool_visible_columns or [])
            )

        for slot in range(pool_size):
            # Zebra striping inicial por slot; se sobrescribe en _render_table segun el level.
            row_bg = APP_SURFACE if slot % 2 == 0 else APP_SURFACE_ALT
            cells: list[ft.DataCell] = []
            cell_texts: list[ft.Text] = []
            cell_containers: list = []
            for column in visible_columns:
                is_message = self._is_message_column(column)
                if is_message:
                    text_ctrl = ft.Text(
                        "",
                        max_lines=1,
                        overflow=ft.TextOverflow.ELLIPSIS,
                        no_wrap=True,
                    )
                    cell_container = ft.Container(
                        content=ft.Row(
                            [
                                ft.Container(
                                    content=text_ctrl,
                                    alignment=ft.Alignment(x=-1, y=0),
                                    expand=True,
                                ),
                                ft.Icon(ft.Icons.OPEN_IN_FULL, size=16, color=APP_TEXT_MUTED),
                            ],
                            spacing=8,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        alignment=ft.Alignment(x=-1, y=0),
                        padding=ft.padding.Padding(left=6, top=4, right=6, bottom=4),
                        bgcolor=row_bg,
                    )
                    cells.append(ft.DataCell(cell_container))
                else:
                    text_ctrl = ft.Text(
                        "",
                        selectable=True,
                        max_lines=1,
                        overflow=ft.TextOverflow.ELLIPSIS,
                        no_wrap=True,
                        color=APP_TEXT_PRIMARY,
                    )
                    cell_container = ft.Container(
                        content=text_ctrl,
                        alignment=ft.Alignment(x=-1, y=0),
                        padding=ft.padding.Padding(left=4, top=6, right=4, bottom=6),
                        bgcolor=row_bg,
                        border_radius=ft.BorderRadius(6, 6, 6, 6),
                    )
                    cells.append(ft.DataCell(cell_container))
                cell_texts.append(text_ctrl)
                cell_containers.append(cell_container)

            decoration = ft.BoxDecoration(bgcolor=row_bg)
            data_row = fdt.DataRow2(
                cells=cells,
                decoration=decoration,
                specific_row_height=specific_height,
                on_double_tap=_make_double_tap(slot),
                on_secondary_tap=_make_secondary_tap(slot),
                color={ft.ControlState.HOVERED: "#1A2D6015"},  # azul grisáceo semitransparente
            )
            pool_rows.append(data_row)
            pool_texts.append(cell_texts)
            pool_decorations.append(decoration)
            pool_cell_containers.append(cell_containers)

        min_table_width = max(600, sum(self._column_width(c) for c in visible_columns))
        # Calcular indicador inicial de sort para esta construccion del pool.
        _state = getattr(self.app, "logs_state", {})
        _sort_by = _state.get("sort_by")
        _sort_desc = bool(_state.get("sort_desc", False))
        _sort_col_idx: int | None = None
        if _sort_by and _sort_by in visible_columns:
            _sort_col_idx = list(visible_columns).index(_sort_by)

        data_table = fdt.DataTable2(
            min_width=min_table_width,
            fixed_top_rows=0,
            fixed_left_columns=0,
            heading_row_color=APP_SURFACE_MUTED,
            fixed_corner_color=APP_SURFACE_MUTED,
            fixed_columns_color=APP_SURFACE_ALT,
            visible_horizontal_scroll_bar=True,
            visible_vertical_scroll_bar=True,
            data_row_height=self._DEFAULT_DATA_ROW_HEIGHT,
            horizontal_margin=18,
            column_spacing=24,
            show_heading_checkbox=False,
            sort_column_index=_sort_col_idx,
            sort_ascending=not _sort_desc,
            columns=data_table_columns,
            rows=[],
            empty=ft.Text("No hay filas para los filtros actuales."),
        )

        self._pool_data_table = data_table
        self._pool_visible_columns = cols_tuple
        self._pool_column_widths = {c: self._column_width(c) for c in visible_columns}
        self._pool_rows = pool_rows
        self._pool_row_texts = pool_texts
        self._pool_row_data = pool_data
        self._pool_row_decorations = pool_decorations
        self._pool_cell_containers = pool_cell_containers
        self._pool_active_n = 0

    def _render_table(self, state: dict):
        visible_specs = state.get("visible_columns", [])
        visible_columns = col_names(visible_specs)
        page_rows = state.get("page_rows", [])

        if not visible_columns:
            self._invalidate_table_pool()
            self.table_content_container.content = ft.Container(
                content=ft.Text("No hay columnas visibles para mostrar."),
                padding=ft.padding.Padding(left=10, top=10, right=10, bottom=10),
            )
            return

        if not page_rows:
            # No invalidamos el pool (las columnas no han cambiado): solo mostramos placeholder.
            self.table_content_container.content = ft.Container(
                content=ft.Text("No hay filas para los filtros actuales."),
                padding=ft.padding.Padding(left=10, top=10, right=10, bottom=10),
            )
            return

        cols_tuple = tuple(visible_columns)
        n = len(page_rows)
        current_widths = {c: self._column_width(c) for c in visible_columns}
        needs_rebuild = (
            self._pool_data_table is None
            or self._pool_visible_columns != cols_tuple
            or len(self._pool_rows) < n
            or current_widths != self._pool_column_widths
        )
        if needs_rebuild:
            # pool al menos del tamano de la pagina; un suelo de 50 cubre el caso normal.
            self._build_table_pool(visible_columns, max(n, 50))

        rule_matches = state.get("rule_matches", {})
        current_page = state.get("current_page", 1)
        page_size = state.get("page_size", 100)
        page_global_indices = state.get("page_global_indices") or []

        # Mutar datos: solo text.value + slot data + bgcolor segun level.
        for slot in range(n):
            row = page_rows[slot]
            self._pool_row_data[slot] = row
            row_bg = self._row_bgcolor(row, slot)
            self._pool_row_decorations[slot].bgcolor = row_bg
            containers = self._pool_cell_containers[slot]
            for c in containers:
                c.bgcolor = row_bg
            texts = self._pool_row_texts[slot]
            for col_idx, column in enumerate(visible_columns):
                texts[col_idx].value = str(row.get(column, ""))
            # ── Borde izquierdo por regla coincidente ─────────────────────
            if rule_matches:
                if slot < len(page_global_indices):
                    global_idx = page_global_indices[slot]
                else:
                    global_idx = (current_page - 1) * page_size + slot
                matched = rule_matches.get(global_idx)
                if matched:
                    self._pool_row_decorations[slot].border = ft.Border(
                        left=ft.BorderSide(4, matched[0].highlight_color)
                    )
                else:
                    self._pool_row_decorations[slot].border = None
            else:
                self._pool_row_decorations[slot].border = None

        # Slice de filas visibles. Asignar lista nueva fuerza diff en Flet de forma controlada.
        self._pool_data_table.rows = self._pool_rows[:n]
        self._pool_active_n = n

        # Actualizar indicador visual de sort en la cabecera.
        sort_by = state.get("sort_by")
        sort_desc = bool(state.get("sort_desc", False))
        if sort_by and sort_by in visible_columns:
            self._pool_data_table.sort_column_index = list(visible_columns).index(sort_by)
        else:
            self._pool_data_table.sort_column_index = None
        self._pool_data_table.sort_ascending = not sort_desc

        # Solo reasignar el container si cambia la instancia (tras rebuild).
        if self.table_content_container.content is not self._pool_data_table:
            self.table_content_container.content = self._pool_data_table
            self._scroll_to_top()

    def _render_analysis_panel(self, state: dict) -> None:
        """Actualiza el panel de análisis de reglas inteligentes."""
        active_domain = state.get("active_domain")
        panel_open = bool(state.get("analysis_panel_open", False))
        rule_matches = state.get("rule_matches", {})
        active_rid = state.get("active_rule_id")

        self.analysis_panel.visible = bool(active_domain and panel_open)
        if not self.analysis_panel.visible:
            return

        total = len(rule_matches)
        filtered_total = state.get("filtered_total", 0)
        if active_rid and rule_matches:
            if active_rid == "__ANY__":
                label_rule = "Todas las reglas del dominio"
            else:
                # Buscar nombre desde algun match
                label_rule = active_rid
                for matches in rule_matches.values():
                    for r in matches:
                        if r.id == active_rid:
                            raw = r.name
                            label_rule = raw.split(": ", 1)[-1] if ": " in raw else raw
                            break
                    else:
                        continue
                    break
            self.analysis_total_text.value = (
                f"Dominio: {active_domain}  ·  Filtrando por: {label_rule}  ·  Filas visibles: {filtered_total}"
            )
        else:
            self.analysis_total_text.value = (
                f"Dominio: {active_domain}  ·  Filas con coincidencias: {total}"
                if total else f"Dominio: {active_domain}  ·  Sin coincidencias en los datos actuales."
            )

        if not rule_matches:
            self.analysis_chips_row.controls = []
            return

        # Contar hits por regla
        counts: dict[str, int] = {}
        names: dict[str, str] = {}
        colors: dict[str, str] = {}
        for matches in rule_matches.values():
            seen: set[str] = set()
            for r in matches:
                if r.id not in seen:
                    seen.add(r.id)
                    counts[r.id] = counts.get(r.id, 0) + 1
                    names[r.id] = r.name
                    colors[r.id] = r.highlight_color

        sorted_ids = sorted(counts, key=lambda rid: -counts[rid])

        def _make_chip(rid: str, label: str, color: str, count: int) -> ft.Container:
            is_active = active_rid == rid
            return ft.Container(
                content=ft.Row(
                    [
                        ft.Container(
                            width=10,
                            height=10,
                            bgcolor=color,
                            border_radius=ft.BorderRadius(5, 5, 5, 5),
                        ),
                        ft.Text(
                            f"{label}  ({count})",
                            size=11,
                            color=APP_TEXT_PRIMARY,
                            weight=ft.FontWeight.W_700 if is_active else ft.FontWeight.NORMAL,
                        ),
                    ],
                    spacing=6,
                    tight=True,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                bgcolor=APP_SURFACE_MUTED if is_active else APP_SURFACE,
                border=ft.Border.all(2 if is_active else 1, color if is_active else APP_BORDER),
                border_radius=ft.BorderRadius(14, 14, 14, 14),
                padding=ft.padding.Padding(left=10, top=3, right=10, bottom=3),
                tooltip=("Quitar filtro" if is_active else f"Filtrar por: {label}"),
                on_click=(lambda e, _rid=rid: self.app.on_logs_toggle_rule_filter(_rid)),
                ink=True,
            )

        chips: list[ft.Control] = []
        # Chip "Todas" (cualquier regla del dominio coincide)
        chips.append(_make_chip("__ANY__", "Todas", APP_TEXT_MUTED, total))
        for rid in sorted_ids:
            count = counts[rid]
            color = colors[rid]
            raw_name = names[rid]
            short = raw_name.split(": ", 1)[-1] if ": " in raw_name else raw_name
            chips.append(_make_chip(rid, short, color, count))

        # Boton para quitar filtro cuando hay uno activo
        if active_rid:
            chips.append(
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Icon(ft.Icons.CLOSE, size=12, color=APP_TEXT_PRIMARY),
                            ft.Text("Quitar filtro", size=11, color=APP_TEXT_PRIMARY),
                        ],
                        spacing=4,
                        tight=True,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    bgcolor=APP_SURFACE,
                    border=ft.Border.all(1, APP_BORDER),
                    border_radius=ft.BorderRadius(14, 14, 14, 14),
                    padding=ft.padding.Padding(left=8, top=3, right=10, bottom=3),
                    tooltip="Quitar el filtro de regla activo",
                    on_click=lambda e: self.app.on_logs_toggle_rule_filter(None),
                    ink=True,
                )
            )

        self.analysis_chips_row.controls = chips
