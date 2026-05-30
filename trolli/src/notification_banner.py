from __future__ import annotations

from typing import Callable, Literal

import flet as ft
from ui_tokens import APP_ERROR_BG, APP_ERROR_FG, APP_SUCCESS_BG, APP_SUCCESS_FG, APP_TEXT_MUTED, APP_TEXT_PRIMARY

NotificationLevel = Literal["error", "success"]

_LEVEL_CONFIG: dict[str, dict] = {
    "error": {
        "bgcolor": APP_ERROR_BG,
        "icon": ft.Icons.ERROR_OUTLINE,
        "icon_color": APP_ERROR_FG,
    },
    "success": {
        "bgcolor": APP_SUCCESS_BG,
        "icon": ft.Icons.CHECK_CIRCLE_OUTLINE,
        "icon_color": APP_SUCCESS_FG,
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
        content=ft.Text(message, color=APP_TEXT_PRIMARY),
        actions=[
            ft.IconButton(
                icon=ft.Icons.CLOSE,
                icon_color=APP_TEXT_MUTED,
                tooltip="Cerrar",
                on_click=on_close,
            )
        ],
        force_actions_below=False,
        margin=0,
    )
