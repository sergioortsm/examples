from __future__ import annotations

import flet as ft
from ui_tokens import APP_BORDER, APP_SURFACE, APP_TEXT_MUTED


class DialogSizer:
    @staticmethod
    def _resolve_page_size(page: ft.Page) -> tuple[int | float | None, int | float | None]:
        window = getattr(page, "window", None)
        width = getattr(window, "width", None)
        height = getattr(window, "height", None)

        if not isinstance(width, (int, float)):
            width = getattr(page, "width", None)
        if not isinstance(height, (int, float)):
            height = getattr(page, "height", None)

        return width, height

    @staticmethod
    def fit_container(
        page: ft.Page,
        container: ft.Container,
        *,
        width_ratio: float,
        min_width: int,
        max_width: int,
        height_ratio: float,
        min_height: int,
        max_height: int,
    ) -> None:
        width, height = DialogSizer._resolve_page_size(page)

        if isinstance(width, (int, float)):
            container.width = max(min_width, min(max_width, int(width * width_ratio)))

        if isinstance(height, (int, float)):
            container.height = max(min_height, min(max_height, int(height * height_ratio)))


def build_logs_message_dialog(
    on_copy,
    on_close,
) -> tuple[ft.Row, ft.Column, ft.Container, ft.AlertDialog]:
    title = ft.Row(
        [
            ft.Icon(ft.Icons.ARTICLE_OUTLINED, size=18, color=APP_TEXT_MUTED),
            ft.Text("Detalle de registro", weight=ft.FontWeight.W_600),
        ],
        spacing=8,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )

    # Columna dinámica: se llena al abrir el dialog con un bloque por cada campo visible.
    content_column = ft.Column(
        [],
        scroll=ft.ScrollMode.AUTO,
        expand=True,
        spacing=4,
    )

    container = ft.Container(
        content=content_column,
        width=860,
        height=400,
        padding=ft.padding.Padding(left=12, top=8, right=12, bottom=12),
        border=ft.Border.all(1, APP_BORDER),
        border_radius=ft.BorderRadius(8, 8, 8, 8),
        bgcolor=APP_SURFACE,
    )

    dialog = ft.AlertDialog(
        modal=True,
        title=title,
        content=container,
        actions=[
            ft.TextButton("Copiar todo", on_click=on_copy),
            ft.TextButton("Cerrar", on_click=on_close),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
        on_dismiss=on_close,
    )

    return title, content_column, container, dialog


def build_column_selector_dialog(
    column_selector: ft.Row,
    apply_columns_status: ft.Row,
    apply_columns_button: ft.Button,
    on_close,
    show_close_button: bool = True,
) -> tuple[ft.Container, ft.AlertDialog]:
    content_container = ft.Container(
        content=ft.Column(
            [
                ft.Text("Selecciona las columnas a mostrar en la tabla.", size=12, color=APP_TEXT_MUTED),
                ft.Divider(height=10, thickness=1),
                ft.Container(content=column_selector, expand=True),
            ],
            spacing=8,
            expand=True,
        ),
        width=350,
        height=210,
    )

    actions = [
        apply_columns_status,
        apply_columns_button,
    ]
    if show_close_button:
        actions.append(ft.TextButton("Cerrar", on_click=lambda e: on_close()))

    dialog = ft.AlertDialog(
        modal=True,
        title=ft.Row(
            [
                ft.Icon(ft.Icons.VIEW_COLUMN, size=18, color=APP_TEXT_MUTED),
                ft.Text("Columnas visibles", weight=ft.FontWeight.W_600),
            ],
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        content=content_container,
        actions=actions,
        actions_alignment=ft.MainAxisAlignment.END,
        on_dismiss=lambda e: on_close(),
    )

    return content_container, dialog