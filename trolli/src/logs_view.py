from __future__ import annotations


import asyncio
import inspect

import flet as ft
import flet_datatable2 as fdt
from dialog import DialogSizer, build_column_selector_dialog
from app_logging import perf_timer
from ui_tokens import APP_BORDER, APP_SURFACE, APP_SURFACE_ALT, APP_SURFACE_MUTED, APP_TEXT_MUTED, APP_TEXT_PRIMARY, surface_shadow


class LogsView(ft.Column):
    _DEFAULT_DATA_ROW_HEIGHT = 42
    _MESSAGE_DATA_ROW_HEIGHT = 64

    _COLUMN_FIXED_WIDTHS: dict[str, int] = {
        "Timestamp": 180,
        "Process": 110,
        "TID": 60,
        "Area": 150,
        "Category": 150,
        "EventID": 75,
        "Level": 90,
        "Correlation": 140,
        "Message": 640,
    }

    # Mapa nivel -> color de fondo (pastel suave). None => usa zebra striping.
    _LEVEL_BG_COLORS: dict[str, str | None] = {
        "CRITICAL": "#FDECEA",
        "ERROR": "#FDECEA",
        "HIGH": "#FFF1E6",
        "WARNING": "#FFF8E1",
        "MEDIUM": "#FFF8E1",
        "UNEXPECTED": "#F3E8FD",
        "MONITORABLE": "#E8F8F0",
        "INFO": None,
        "INFORMATION": None,
        "VERBOSE": None,
        "VERBOSEEX": None,
    }

    _LEVEL_COLUMN_CANDIDATES: tuple[str, ...] = ("Level", "Nivel", "LogLevel", "Severity")

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

    def _on_scroll(self, e: ft.OnScrollEvent) -> None:
        try:
            pixels = float(getattr(e, "pixels", 0) or 0)
        except (TypeError, ValueError):
            pixels = 0.0
        # Si el usuario se aleja del inicio, desactivar el auto-follow.
        self._auto_follow_scroll = pixels <= 10

    def _scroll_to_top(self, force: bool = False) -> None:
        # En modo Vivo no robamos el scroll del usuario bajo ninguna circunstancia.
        app = getattr(self, "app", None)
        if app is not None and bool(getattr(app, "logs_state", {}).get("is_watching", False)):
            return
        if not force and not self._auto_follow_scroll:
            return
        result = self.scroll_to(offset=0, duration=0)
        if not inspect.isawaitable(result):
            return
        try:
            asyncio.get_running_loop().create_task(result)
        except RuntimeError:
            if inspect.iscoroutine(result):
                result.close()

    def request_scroll_to_top(self) -> None:
        # En modo Vivo no robamos el scroll del usuario bajo ninguna circunstancia.
        app = getattr(self, "app", None)
        if app is not None and bool(getattr(app, "logs_state", {}).get("is_watching", False)):
            return
        self._auto_follow_scroll = True
        self._scroll_to_top(force=True)
    
    def __init__(self, app):
        super().__init__(
            expand=True,
            spacing=10,
            scroll=ft.ScrollMode.AUTO,
            on_scroll=self._on_scroll,
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
        self._pool_rows: list = []  # list[fdt.DataRow2]
        self._pool_row_texts: list[list[ft.Text]] = []  # [slot][col_idx] -> Text
        self._pool_row_data: list[dict[str, str]] = []  # ultima fila asignada a cada slot
        self._pool_row_decorations: list = []  # [slot] -> BoxDecoration
        self._pool_cell_containers: list[list] = []  # [slot][col_idx] -> Container
        self._pool_active_n: int = 0  # filas actualmente en uso

        self.title_text = ft.Text(
            "SharePoint ULS Logs",
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
        self.watch_folder_field = ft.TextField(
            label="Carpeta a vigilar",
            hint_text=r"C:\Program Files\Common Files\Microsoft Shared\Web Server Extensions\16\LOGS",
            expand=True,
            on_change=lambda e: self.app.on_logs_watch_folder_change(e.control.value),
        )
        self.watch_pattern_field = ft.TextField(
            label="Patron (regex)",
            hint_text=r".+-\d{8}-\d{4}\.log$",
            width=240,
            on_change=lambda e: self.app.on_logs_watch_pattern_change(e.control.value),
        )
        self.watch_toggle_button = ft.IconButton(
            icon=ft.Icons.PLAY_ARROW,
            icon_color=ft.Colors.GREEN_700,
            tooltip="Iniciar vigilancia en vivo",
            on_click=lambda e: self.app.on_logs_toggle_watch(),
        )
        self.watch_status_text = ft.Text("", size=12, color=APP_TEXT_MUTED)
        self.watch_row = ft.Row(
            [
                self.watch_folder_field,
                self.watch_pattern_field,
                self.watch_toggle_button,
                self.watch_status_text,
            ],
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

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
        self.level_dropdown = ft.Dropdown(
            width=220,
            label="Nivel",
            options=[ft.dropdown.Option("All")],
            value="All",
            on_select=lambda e: self.app.on_logs_level_change(e.control.value),
        )
        self.sort_dropdown = ft.Dropdown(
            width=240,
            label="Ordenar por",
            options=[],
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
            on_select=lambda e: self.app.on_logs_page_size_change(e.control.value),
        )

        self.prev_page_button = ft.IconButton(
            icon=ft.Icons.CHEVRON_LEFT,
            tooltip="Pagina anterior",
            mouse_cursor=ft.MouseCursor.CLICK,
            on_click=lambda e: self.app.on_logs_prev_page(),
        )
        self.next_page_button = ft.IconButton(
            icon=ft.Icons.CHEVRON_RIGHT,
            tooltip="Pagina siguiente",
            mouse_cursor=ft.MouseCursor.CLICK,
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
        self.open_log_button = ft.IconButton(
            icon=ft.Icons.FOLDER_OPEN,
            tooltip="Abrir .log",
            mouse_cursor=ft.MouseCursor.CLICK,
            on_click=self.app.open_log_file_dialog,
        )
        self.export_csv_button = ft.IconButton(
            icon=ft.Icons.DOWNLOAD,
            tooltip="Exportar CSV",
            mouse_cursor=ft.MouseCursor.CLICK,
            on_click=lambda e: self.app.on_logs_export_click(),
        )
        self.apply_columns_button = ft.Button(
            "Aplicar",
            icon=ft.Icons.CHECK_CIRCLE,
            on_click=lambda e: self.app.on_logs_apply_columns(),
            disabled=True,
        )
        self.apply_columns_status = ft.Row(
            [
                ft.ProgressRing(width=14, height=14, stroke_width=2, color=ft.Colors.BLUE_GREY_700),
            ],
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

        # Inicializacion de contenedores de tabla y overlay de carga
        self.table_content_container = ft.Container(
            padding=ft.padding.Padding(left=8, top=8, right=8, bottom=8),
        )
        self.table_surface = ft.Container(
            content=self.table_content_container,
            bgcolor=APP_SURFACE,
            border=ft.Border.all(1, APP_BORDER),
            border_radius=ft.BorderRadius(16, 16, 16, 16),
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
            shadow=surface_shadow(),
        )

        # Fila de filtros + boton columnas alineado a la derecha
        self.filters_row = ft.Row(
            [
                ft.Row(
                    [
                        self.search_field,
                        self.level_dropdown,
                        self.sort_dropdown,
                        self.sort_direction_button,
                        self.page_size_dropdown,
                    ],
                    spacing=8,
                    expand=True,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Row(
                    [
                        ft.Container(
                            content=self.toggle_column_selector_button,
                            alignment=ft.Alignment(1, 0),
                            padding=ft.padding.Padding(left=12),
                        ),
                    ],
                    spacing=0,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            wrap=False,
        )

        self.controls = [
            ft.Row(
                [
                    ft.Column([self.title_text, self.metadata_row], spacing=2, expand=True),
                    ft.Container(
                        content=ft.Row(
                            [
                                self.open_log_button,
                                self.export_csv_button,
                            ],
                            spacing=4,
                            tight=True,
                        ),
                        padding=ft.padding.Padding(top=6, right=8),
                    ),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            self.watch_row,
            self.filters_row,
            ft.Row([self.pending_new_button], alignment=ft.MainAxisAlignment.START),
            self.table_surface,
            ft.Row(
                [self.prev_page_button, self.page_info_text, self.next_page_button],
                alignment=ft.MainAxisAlignment.END,
            ),
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
        self.file_text.value = state.get("file_label", "Sin archivo cargado")

        error = state.get("error", "")
        if error:
            self.status_text.value = error
            self.status_text.color = ft.Colors.RED_600
        else:
            total = state.get("filtered_total", 0)
            self.status_text.value = f"Registros filtrados: {total}"
            self.status_text.color = ft.Colors.GREEN_800

        self.search_field.value = state.get("search_text", "")

        level_options = state.get("level_options", ["All"])
        self.level_dropdown.options = [ft.dropdown.Option(level) for level in level_options]
        selected_level = state.get("level_filter", "All")
        if selected_level not in level_options:
            selected_level = "All"
        self.level_dropdown.value = selected_level

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
        self.watch_folder_field.value = state.get("watch_folder", "")
        self.watch_pattern_field.value = state.get("watch_pattern", "")
        self.watch_folder_field.disabled = is_watching
        self.watch_pattern_field.disabled = is_watching
        if is_watching:
            self.watch_toggle_button.icon = ft.Icons.STOP
            self.watch_toggle_button.icon_color = ft.Colors.RED_700
            self.watch_toggle_button.tooltip = "Detener vigilancia"
        else:
            self.watch_toggle_button.icon = ft.Icons.PLAY_ARROW
            self.watch_toggle_button.icon_color = ft.Colors.GREEN_700
            self.watch_toggle_button.tooltip = "Iniciar vigilancia en vivo"
        watch_error = state.get("watch_error", "")
        if watch_error:
            self.watch_status_text.value = watch_error
            self.watch_status_text.color = ft.Colors.RED_600
        elif is_watching:
            rate = state.get("lines_per_sec", 0.0)
            buf = state.get("buffer_count", 0)
            buf_max = state.get("buffer_max", 0)
            self.watch_status_text.value = (
                f"En vivo · buffer {buf}/{buf_max} · {rate:.0f} l/s"
            )
            self.watch_status_text.color = ft.Colors.GREEN_800
        else:
            self.watch_status_text.value = ""

        pending_new = int(state.get("pending_new_count", 0))
        if pending_new > 0:
            self.pending_new_text.value = f"Nuevas ({pending_new})"
            self.pending_new_button.visible = True
        else:
            self.pending_new_text.value = "Nuevas (0)"
            self.pending_new_button.visible = False

        self._render_column_selector(state)
        self._render_table(state)

        # El refresco global lo hace la app con page.update().
        # Evita AssertionError cuando la vista aun no esta montada.
        if getattr(self, "page", None) is not None:
            self.update()

    def _render_column_selector(self, state: dict):
        columns = state.get("columns", [])
        pending_list = list(state.get("visible_columns_pending", state.get("visible_columns", [])))
        pending_columns = set(pending_list)
        applied_columns = list(state.get("visible_columns", []))
        self.column_selector_visible = bool(state.get("column_selector_expanded", False))
        is_applying = bool(state.get("is_applying_columns", False))
        is_busy = bool(state.get("is_loading", False)) or is_applying

        self.column_selector.controls = [
            ft.Container(
                width=150,
                padding=ft.padding.Padding(left=0, top=0, right=0, bottom=0),
                content=ft.Row(
                    [
                        ft.GestureDetector(
                            mouse_cursor=ft.MouseCursor.CLICK,
                            content=ft.Checkbox(
                                value=column in pending_columns,
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
        self.apply_columns_button.disabled = (not has_columns) or is_busy or (pending_list == applied_columns)
        self.apply_columns_status.visible = is_applying
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
        watch_error = state.get("watch_error", "")
        if watch_error:
            self.watch_status_text.value = watch_error
            self.watch_status_text.color = ft.Colors.RED_600
        elif is_watching:
            rate = state.get("lines_per_sec", 0.0)
            buf = state.get("buffer_count", 0)
            buf_max = state.get("buffer_max", 0)
            self.watch_status_text.value = (
                f"En vivo · buffer {buf}/{buf_max} · {rate:.0f} l/s"
            )
            self.watch_status_text.color = ft.Colors.GREEN_800
        else:
            self.watch_status_text.value = ""

        if getattr(self, "page", None) is not None:
            # Solo refrescamos los controles afectados para minimizar diffs WS.
            try:
                self.pending_new_button.update()
                self.watch_status_text.update()
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
                if callable(opener):
                    opener(self.column_selector_dialog)
                else:
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
        has_message_col = any(self._is_message_column(c) for c in visible_columns)
        specific_height = self._MESSAGE_DATA_ROW_HEIGHT if has_message_col else None

        # Columnas (cabeceras)
        data_table_columns = []
        for column in visible_columns:
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
                    fixed_width=self._column_width(column),
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
                        max_lines=2,
                        overflow=ft.TextOverflow.ELLIPSIS,
                        no_wrap=False,
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
                        max_lines=2,
                        overflow=ft.TextOverflow.ELLIPSIS,
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
            )
            pool_rows.append(data_row)
            pool_texts.append(cell_texts)
            pool_decorations.append(decoration)
            pool_cell_containers.append(cell_containers)

        min_table_width = max(600, sum(self._column_width(c) for c in visible_columns))
        data_table = fdt.DataTable2(
            min_width=min_table_width,
            fixed_top_rows=0,
            fixed_left_columns=0,
            heading_row_color=APP_SURFACE_MUTED,
            fixed_corner_color=APP_SURFACE_MUTED,
            fixed_columns_color=APP_SURFACE_ALT,
            visible_horizontal_scroll_bar=True,
            visible_vertical_scroll_bar=False,
            data_row_height=self._DEFAULT_DATA_ROW_HEIGHT,
            horizontal_margin=18,
            column_spacing=24,
            show_heading_checkbox=False,
            columns=data_table_columns,
            rows=[],
            empty=ft.Text("No hay filas para los filtros actuales."),
        )

        self._pool_data_table = data_table
        self._pool_visible_columns = cols_tuple
        self._pool_rows = pool_rows
        self._pool_row_texts = pool_texts
        self._pool_row_data = pool_data
        self._pool_row_decorations = pool_decorations
        self._pool_cell_containers = pool_cell_containers
        self._pool_active_n = 0

    def _render_table(self, state: dict):
        visible_columns = state.get("visible_columns", [])
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
        needs_rebuild = (
            self._pool_data_table is None
            or self._pool_visible_columns != cols_tuple
            or len(self._pool_rows) < n
        )
        if needs_rebuild:
            # pool al menos del tamano de la pagina; un suelo de 50 cubre el caso normal.
            self._build_table_pool(visible_columns, max(n, 50))

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

        # Slice de filas visibles. Asignar lista nueva fuerza diff en Flet de forma controlada.
        self._pool_data_table.rows = self._pool_rows[:n]
        self._pool_active_n = n

        # Solo reasignar el container si cambia la instancia (tras rebuild).
        if self.table_content_container.content is not self._pool_data_table:
            self.table_content_container.content = self._pool_data_table
            self._scroll_to_top()
