from __future__ import annotations

import flet as ft


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
) -> tuple[ft.Row, ft.Text, ft.Text, ft.Container, ft.AlertDialog]:
    title = ft.Row(
        [
            ft.Icon(ft.Icons.ARTICLE_OUTLINED, size=18, color=ft.Colors.BLUE_GREY_700),
            ft.Text("", weight=ft.FontWeight.W_600),
        ],
        spacing=8,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )

    meta = ft.Text("", size=12, color=ft.Colors.BLUE_GREY_700)
    body = ft.Text("", selectable=True)
    content = ft.Column(
        [
            meta,
            ft.Divider(height=10, thickness=1),
            body,
        ],
        scroll=ft.ScrollMode.AUTO,
        expand=True,
    )

    container = ft.Container(
        content=content,
        width=860,
        height=400,
        padding=ft.padding.Padding(left=12, top=12, right=12, bottom=12),
        border=ft.Border.all(1, ft.Colors.BLUE_GREY_100),
        border_radius=ft.BorderRadius(8, 8, 8, 8),
        bgcolor=ft.Colors.WHITE,
    )

    dialog = ft.AlertDialog(
        modal=True,
        title=title,
        content=container,
        actions=[
            ft.TextButton("Copiar", on_click=on_copy),
            ft.TextButton("Cerrar", on_click=on_close),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
        on_dismiss=on_close,
    )

    return title, meta, body, container, dialog


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
                ft.Text("Selecciona las columnas a mostrar en la tabla.", size=12, color=ft.Colors.BLUE_GREY_700),
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
                ft.Icon(ft.Icons.VIEW_COLUMN, size=18, color=ft.Colors.BLUE_GREY_700),
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