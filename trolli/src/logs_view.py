from __future__ import annotations


import flet as ft
import flet_datatable2 as fdt
from dialog import DialogSizer, build_column_selector_dialog


class LogsView(ft.Column):
    _COLUMN_FIXED_WIDTHS: dict[str, int] = {
        "Timestamp": 165,
        "Process": 90,
        "TID": 60,
        "Area": 120,
        "Category": 130,
        "EventID": 75,
        "Level": 80,
        "Correlation": 100,
    }

    def _column_width(self, column_name: str) -> int:
        """Ancho fijo en píxeles para columnas no-Message. Usa mapa por nombre; fallback 120."""
        return self._COLUMN_FIXED_WIDTHS.get(column_name, 120)

    def _is_message_column(self, column_name: str) -> bool:
        """Devuelve True si la columna es 'Message' (insensible a mayúsculas/minúsculas)."""
        return column_name.strip().lower() == "message"
    
    def __init__(self, app):
        super().__init__(expand=True, spacing=10)
        self.app = app
        self.column_selector_visible = False

        self.title_text = ft.Text("SharePoint ULS Logs", size=28, weight=ft.FontWeight.W_600)
        self.file_text = ft.Text(
            "Sin archivo cargado",
            color=ft.Colors.BLACK_54,
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
        self.watch_status_text = ft.Text("", size=12, color=ft.Colors.BLUE_GREY_700)
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
        self.table_content_container = ft.Container(expand=True)
        self.loading_overlay = ft.Container(
            visible=False,
            expand=True,
            bgcolor="#47000000",
            alignment=ft.Alignment(x=0, y=0),
            content=ft.ProgressRing(width=44, height=44, stroke_width=4, color=ft.Colors.WHITE),
        )

        self.table_container = ft.Stack(
            [
                self.table_content_container,
                self.loading_overlay,
            ],
            expand=True,
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
            self.table_container,
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
        self.prev_page_button.disabled = current_page <= 1
        self.next_page_button.disabled = current_page >= total_pages
        self.loading_overlay.visible = bool(state.get("is_loading", False))

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
        self._render_table(state)
        if getattr(self, "page", None) is not None:
            self.update()

    def refresh_loading_state(self, state: dict):
        # Refresco ligero para mostrar overlay/estado de paginacion sin reconstruir la tabla.
        current_page = state.get("current_page", 1)
        total_pages = state.get("total_pages", 1)
        self.page_info_text.value = f"Pagina {current_page} / {total_pages}"
        is_loading = bool(state.get("is_loading", False))
        self.prev_page_button.disabled = is_loading or current_page <= 1
        self.next_page_button.disabled = is_loading or current_page >= total_pages
        self.loading_overlay.visible = is_loading
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

    def _render_table(self, state: dict):
        visible_columns = state.get("visible_columns", [])
        page_rows = state.get("page_rows", [])

        if not visible_columns:
            self.table_content_container.content = ft.Container(
                content=ft.Text("No hay columnas visibles para mostrar."),
                padding=ft.padding.Padding(left=10, top=10, right=10, bottom=10),
            )
            return

        if not page_rows:
            self.table_content_container.content = ft.Container(
                content=ft.Text("No hay filas para los filtros actuales."),
                padding=ft.padding.Padding(left=10, top=10, right=10, bottom=10),
            )
            return


        data_table_columns = []
        for idx, column in enumerate(visible_columns):
            if self._is_message_column(column) or (len(visible_columns) == 1):
                data_table_columns.append(
                    fdt.DataColumn2(
                        label=ft.Text(column),
                        size=fdt.DataColumnSize.L if self._is_message_column(column) else None,
                        fixed_width=None if self._is_message_column(column) else self._column_width(column),
                    )
                )
            else:
                data_table_columns.append(
                    fdt.DataColumn2(
                        label=ft.Text(column),
                        fixed_width=self._column_width(column),
                    )
                )

        # min_width = suma de columnas fijas + mínimo razonable para columnas size=
        fixed_total = sum(
            self._column_width(c) for c in visible_columns if not self._is_message_column(c)
        )
        has_message_col = any(self._is_message_column(c) for c in visible_columns)
        min_table_width = max(600, fixed_total + (360 if has_message_col else 0))

        data_table = fdt.DataTable2(
            expand=True,
            min_width=min_table_width,
            fixed_top_rows=1,
            fixed_left_columns=1 if visible_columns else 0,
            heading_row_color=ft.Colors.BLUE_GREY_100,
            horizontal_margin=18,
            column_spacing=24,
            show_heading_checkbox=False,
            columns=data_table_columns,
            rows=[
                fdt.DataRow2(
                    cells=[self._build_cell(column, row) for column in visible_columns]
                )
                for row in page_rows
            ],
            empty=ft.Text("No hay filas para los filtros actuales."),
        )

        # DataTable2 gestiona su propio scroll (horizontal con min_width, vertical con fixed_top_rows).
        # NO envolver en ft.Row(scroll=AUTO): daría espacio horizontal infinito y rompería size=L.
        self.table_content_container.content = data_table

    def _build_cell(self, column_name: str, row: dict[str, str]) -> ft.DataCell:
        value = str(row.get(column_name, ""))
        is_message = self._is_message_column(column_name)
        if is_message:
            preview = value.replace("\n", " ").strip()
            tooltip_text = preview if preview else "Mensaje vacio"
            content = ft.GestureDetector(
                mouse_cursor=ft.MouseCursor.CLICK,
                on_tap=lambda e, text=value, col=column_name: self.app.on_logs_open_message_detail(text, col),
                content=ft.Container(
                    content=ft.Row(
                        [
                            ft.Container(
                                content=ft.Text(
                                    value,
                                    max_lines=2,
                                    overflow=ft.TextOverflow.ELLIPSIS,
                                    no_wrap=False,
                                ),
                                expand=True,
                            ),
                            ft.Icon(ft.Icons.OPEN_IN_FULL, size=16, color=ft.Colors.BLUE_GREY_500),
                        ],
                        spacing=8,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    padding=ft.padding.Padding(left=6, top=4, right=6, bottom=4),
                    border_radius=ft.BorderRadius(6, 6, 6, 6),
                    tooltip=f"Clic para ver completo: {tooltip_text}",
                ),
            )
            return ft.DataCell(content)
        else:
            return ft.DataCell(
                ft.Text(
                    value,
                    selectable=True,
                    max_lines=2,
                    overflow=ft.TextOverflow.ELLIPSIS,
                )
            )
