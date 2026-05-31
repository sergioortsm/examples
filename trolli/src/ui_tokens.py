from __future__ import annotations

import flet as ft


APP_SHELL_BG = "#DCE8F2"
APP_SHELL_ACCENT = "#5B9BC8"
APP_SHELL_ACCENT_HOVER = "#4B8AB6"
APP_SIDEBAR_BG = "#6E8598"
APP_SURFACE = "#FFFFFF"
APP_SURFACE_ALT = "#F7FAFC"
APP_SURFACE_MUTED = "#EEF3F8"
APP_BORDER = "#D6DEE8"
APP_BORDER_STRONG = "#C3D0DD"
APP_DIVIDER = "#C8D4DF"
APP_TEXT_PRIMARY = "#203245"
APP_TEXT_MUTED = "#5D748A"
APP_TEXT_ON_ACCENT = "#F7FBFF"
APP_ICON_MUTED = "#6B7F91"
APP_OVERLAY = "#16FFFFFF"
APP_APP_LOADING_OVERLAY = "#30EEF4FA"
APP_SURFACE_SHADOW = "#163A5C22"
APP_SUCCESS_BG = "#E9F6ED"
APP_SUCCESS_FG = "#2E7D52"
APP_ERROR_BG = "#FBE9E9"
APP_ERROR_FG = "#B24444"

CLICK_CURSOR = ft.MouseCursor.CLICK


def click_button_style() -> ft.ButtonStyle:
    return ft.ButtonStyle(mouse_cursor=CLICK_CURSOR)


def surface_shadow(offset_y: int = 6, blur_radius: int = 18) -> list[ft.BoxShadow]:
    return [
        ft.BoxShadow(
            spread_radius=0,
            blur_radius=blur_radius,
            color=APP_SURFACE_SHADOW,
            offset=ft.Offset(0, offset_y),
        )
    ]