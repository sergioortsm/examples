from __future__ import annotations

from typing import Callable, Literal

import flet as ft

NotificationLevel = Literal["error", "success"]

_LEVEL_CONFIG: dict[str, dict] = {
    "error": {
        "bgcolor": ft.Colors.RED_100,
        "icon": ft.Icons.ERROR_OUTLINE,
        "icon_color": ft.Colors.RED_700,
    },
    "success": {
        "bgcolor": ft.Colors.GREEN_100,
        "icon": ft.Icons.CHECK_CIRCLE_OUTLINE,
        "icon_color": ft.Colors.GREEN_700,
    },
}


def build_notification_banner(
    message: str,
    level: NotificationLevel,
    on_close: Callable,
) -> ft.Banner:
    cfg = _LEVEL_CONFIG[level]
    return ft.Banner(
        bgcolor=cfg["bgcolor"],
        leading=ft.Icon(cfg["icon"], color=cfg["icon_color"], size=28),
        content=ft.Text(message, color=ft.Colors.BLACK87),
        actions=[
            ft.IconButton(
                icon=ft.Icons.CLOSE,
                icon_color=ft.Colors.BLACK54,
                tooltip="Cerrar",
                on_click=on_close,
            )
        ],
        force_actions_below=False,
        margin=0,
    )
