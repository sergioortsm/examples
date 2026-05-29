from __future__ import annotations

import flet as ft


class LogsView(ft.Column):
    def _column_width(self, column_name: str) -> int:
        """Devuelve el ancho en píxeles para columnas normales (excepto Message)."""
        return 120

    def _message_column_width(self) -> int:
        """Ancho fijo para la columna Message."""
        return 820

    def _is_message_column(self, column_name: str) -> bool:
        """Devuelve True si la columna es 'Message' (insensible a mayúsculas/minúsculas)."""
        return column_name.strip().lower() == "message"
    
    def __init__(self, app):
        super().__init__(expand=True, spacing=10)
        self.app = app
        self.column_selector_visible = False

        self.title_text = ft.Text("SharePoint ULS Logs", size=28, weight=ft.FontWeight.W_600)
        self.file_text = ft.Text("Sin archivo cargado", color=ft.Colors.BLACK54)
        self.status_text = ft.Text("", color=ft.Colors.RED_600)

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
            on_click=lambda e: self.app.on_logs_prev_page(),
        )
        self.next_page_button = ft.IconButton(
            icon=ft.Icons.CHEVRON_RIGHT,
            tooltip="Pagina siguiente",
            on_click=lambda e: self.app.on_logs_next_page(),
        )
        self.page_info_text = ft.Text("Pagina 1 / 1")

        self.column_selector = ft.Column(
            [],
            spacing=4,
            tight=True,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        )
        self.column_selector_container = ft.Container(
            content=self.column_selector,
            visible=self.column_selector_visible,
            height=220,
            padding=ft.padding.Padding(top=4),
        )
        self.column_selector_panel = self.column_selector_container
        self.toggle_column_selector_button = ft.TextButton(
            "Mostrar",
            icon=ft.Icons.KEYBOARD_ARROW_DOWN,
            on_click=self.toggle_column_selector,
        )

        self.table_content_container = ft.Container(expand=True)
        self.loading_overlay = ft.Container(
            visible=False,
            expand=True,
            bgcolor="#47000000",
            alignment=ft.Alignment(x=0, y=0),
            content=ft.Column(
                [
                    ft.ProgressRing(width=44, height=44, stroke_width=4, color=ft.Colors.WHITE),
                    ft.Text("Cargando...", color=ft.Colors.WHITE),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                tight=True,
                spacing=10,
            ),
        )
        self.table_container = ft.Stack(
            [
                self.table_content_container,
                self.loading_overlay,
            ],
            expand=True,
        )

        self.controls = [
            ft.Row(
                [
                    ft.Column([self.title_text, self.file_text], spacing=2, expand=True),
                    ft.ElevatedButton("Abrir .log", icon=ft.Icons.FOLDER_OPEN, on_click=self.app.open_log_file_dialog),
                    ft.ElevatedButton("Exportar CSV", icon=ft.Icons.DOWNLOAD, on_click=lambda e: self.app.on_logs_export_click()),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.START,
            ),
            self.status_text,
            ft.Row(
                [
                    self.search_field,
                    self.level_dropdown,
                    self.sort_dropdown,
                    self.sort_direction_button,
                    self.page_size_dropdown,
                ],
                wrap=True,
            ),
            ft.Container(
                content=ft.Column(
                    [
                        ft.Row(
                            [
                                ft.Text("Columnas visibles", size=16, weight=ft.FontWeight.W_600),
                                self.toggle_column_selector_button,
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        ),
                        self.column_selector_panel,
                    ],
                    spacing=6,
                ),
                padding=ft.padding.Padding(left=8, top=8, right=8, bottom=8),
                bgcolor="#8AFFFFFF",
                border_radius=ft.BorderRadius(6, 6, 6, 6),
            ),
            self.table_container,
            ft.Row(
                [self.prev_page_button, self.page_info_text, self.next_page_button],
                alignment=ft.MainAxisAlignment.END,
            ),
        ]

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

        self._render_column_selector(state)
        self._render_table(state)

        # El refresco global lo hace la app con page.update().
        # Evita AssertionError cuando la vista aun no esta montada.
        if getattr(self, "page", None) is not None:
            self.update()

    def _render_column_selector(self, state: dict):
        columns = state.get("columns", [])
        visible_columns = set(state.get("visible_columns", []))

        self.column_selector.controls = [
            ft.Checkbox(
                label=column,
                value=column in visible_columns,
                on_change=lambda e, col=column: self.app.on_logs_toggle_column(col, bool(e.control.value)),
            )
            for column in columns
        ]

        has_columns = len(columns) > 0
        self.toggle_column_selector_button.disabled = not has_columns
        if not has_columns:
            self.column_selector_visible = False
        self._sync_column_selector_visibility()

    def toggle_column_selector(self, e):
        self.column_selector_visible = not self.column_selector_visible
        self._sync_column_selector_visibility()
        if getattr(self, "page", None) is not None:
            self.update()

    def _sync_column_selector_visibility(self):
        self.column_selector_container.visible = self.column_selector_visible
        self.toggle_column_selector_button.text = (
            "Ocultar" if self.column_selector_visible else "Mostrar"
        )
        self.toggle_column_selector_button.icon = (
            ft.Icons.KEYBOARD_ARROW_UP
            if self.column_selector_visible
            else ft.Icons.KEYBOARD_ARROW_DOWN
        )

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

        data_table = ft.DataTable(
            columns=[
                ft.DataColumn(
                    ft.Container(
                        content=ft.Text(column),
                        width=self._message_column_width() if self._is_message_column(column) else self._column_width(column),
                    )
                )
                for column in visible_columns
            ],
            rows=[
                ft.DataRow(
                    cells=[self._build_cell(column, row) for column in visible_columns]
                )
                for row in page_rows
            ],
            expand=True,
            heading_row_color=ft.Colors.BLUE_GREY_100,
            data_row_min_height=44,
            data_row_max_height=64,
            horizontal_margin=18,
            column_spacing=24,
            show_checkbox_column=False,
        )

        self.table_content_container.content = ft.Column(
            [
                ft.Container(
                    content=ft.Row([data_table], scroll=ft.ScrollMode.AUTO),
                    margin=ft.margin.Margin(top=8, right=8, bottom=8, left=8),
                )
            ],
            expand=True,
            scroll=ft.ScrollMode.AUTO,
        )

    def _build_cell(self, column_name: str, row: dict[str, str]) -> ft.DataCell:
        value = str(row.get(column_name, ""))
        is_message = self._is_message_column(column_name)
        max_lines = 3 if is_message else 2
        if is_message:
            content = ft.GestureDetector(
                mouse_cursor=ft.MouseCursor.CLICK,
                on_tap=lambda e, text=value, col=column_name: self.app.on_logs_open_message_detail(text, col),
                content=ft.Container(
                    content=ft.Text(
                        value,
                        max_lines=2,
                        overflow=ft.TextOverflow.ELLIPSIS,
                        no_wrap=False,
                    ),
                    width=self._message_column_width(),
                    padding=ft.padding.Padding(right=4),
                ),
            )
            return ft.DataCell(content)
        else:
            content = ft.Container(
                content=ft.Text(
                    value,
                    selectable=True,
                    max_lines=max_lines,
                    overflow=ft.TextOverflow.ELLIPSIS,
                ),
                width=self._column_width(column_name),
            )
            return ft.DataCell(content)