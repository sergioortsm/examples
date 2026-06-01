"""
settings_view.py
Página de configuración de reglas inteligentes de detección en logs ULS.
"""
from __future__ import annotations

import re
import uuid

import flet as ft

from smart_rules import ALL_DOMAINS, DOMAIN_COLORS, SmartRule, rules_engine
from ui_tokens import (
    APP_BORDER,
    APP_SURFACE,
    APP_SURFACE_ALT,
    APP_SURFACE_MUTED,
    APP_TEXT_MUTED,
    APP_TEXT_PRIMARY,
    APP_TEXT_ON_ACCENT,
    APP_SHELL_ACCENT,
    CLICK_CURSOR,
    surface_shadow,
)

# Columnas ULS habituales para el selector "Campo"
_FIELD_OPTIONS = ["*", "Message", "Process", "Area", "Category", "EventID", "Level", "Correlation"]


class SettingsView(ft.Column):
    """Vista principal de configuración de reglas inteligentes."""

    def __init__(self, app) -> None:
        super().__init__(
            expand=True,
            spacing=0,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        )
        self.app = app
        self._active_tab_idx: int = 0
        self._rules_list = ft.Column(spacing=0, scroll=ft.ScrollMode.AUTO)
        self._build()

    # ──────────────────────────────────────────────────────────────────────────
    # Construcción de la UI
    # ──────────────────────────────────────────────────────────────────────────

    def _update_tab_bar(self) -> None:
        """Reconstruye los botones de la barra de tabs marcando el activo."""
        buttons = []
        for idx, domain in enumerate(ALL_DOMAINS):
            is_active = idx == self._active_tab_idx
            color_dot = DOMAIN_COLORS.get(domain, "#888888")
            buttons.append(
                ft.GestureDetector(
                    on_tap=lambda e, i=idx: self._on_tab_click(i),
                    content=ft.Container(
                        content=ft.Row(
                            [
                                ft.Container(
                                    width=8,
                                    height=8,
                                    bgcolor=color_dot,
                                    border_radius=ft.BorderRadius(4, 4, 4, 4),
                                ),
                                ft.Text(
                                    domain,
                                    size=13,
                                    weight=ft.FontWeight.W_600 if is_active else ft.FontWeight.W_400,
                                    color=APP_TEXT_PRIMARY if is_active else APP_TEXT_MUTED,
                                ),
                            ],
                            spacing=6,
                            tight=True,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        padding=ft.padding.Padding(left=14, top=10, right=14, bottom=10),
                        border=ft.Border(
                            bottom=ft.BorderSide(3, color_dot if is_active else ft.Colors.TRANSPARENT)
                        ),
                        bgcolor=APP_SURFACE_MUTED if is_active else ft.Colors.TRANSPARENT,
                    ),
                )
            )
        if hasattr(self, "_tab_bar_row"):
            self._tab_bar_row.controls = buttons

    def _build(self) -> None:
        # Cabecera
        header = ft.Container(
            content=ft.Column(
                [
                    ft.Text(
                        "Reglas de detección inteligente",
                        size=22,
                        weight=ft.FontWeight.W_600,
                        color=APP_TEXT_PRIMARY,
                    ),
                    ft.Text(
                        "Detecta patrones de error en logs ULS: SPFx, Timer Jobs, wsps y PowerShell.",
                        size=13,
                        color=APP_TEXT_MUTED,
                    ),
                ],
                spacing=4,
                tight=True,
            ),
            padding=ft.padding.Padding(left=20, top=16, right=20, bottom=8),
        )

        # Barra de tabs manual (ft.Tabs cambió su API en 0.85.x)
        self._tab_bar_row = ft.Row([], spacing=0)
        self._update_tab_bar()

        # Barra de acciones
        self._add_button = ft.TextButton(
            content=ft.Row(
                [ft.Icon(ft.Icons.ADD, size=16, color=APP_SHELL_ACCENT), ft.Text("Añadir regla", color=APP_SHELL_ACCENT, size=13)],
                tight=True,
                spacing=4,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            on_click=self._on_add_rule,
        )
        self._reset_button = ft.TextButton(
            content=ft.Row(
                [ft.Icon(ft.Icons.RESTORE, size=16, color=APP_TEXT_MUTED), ft.Text("Restaurar predefinidas", color=APP_TEXT_MUTED, size=13)],
                tight=True,
                spacing=4,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            on_click=self._on_reset_defaults,
        )

        action_bar = ft.Container(
            content=ft.Row(
                [self._add_button, self._reset_button, ft.Row([], expand=True)],
                spacing=4,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.padding.Padding(left=20, top=4, right=20, bottom=4),
        )

        # Cabecera de columnas de la lista
        col_header = ft.Container(
            content=ft.Row(
                [
                    ft.Container(width=48),  # switch
                    ft.Container(width=14),  # color badge
                    ft.Text("Nombre", size=11, weight=ft.FontWeight.W_600, color=APP_TEXT_MUTED, expand=True),
                    ft.Container(content=ft.Text("Campo", size=11, weight=ft.FontWeight.W_600, color=APP_TEXT_MUTED), width=80),
                    ft.Container(content=ft.Text("Patrón", size=11, weight=ft.FontWeight.W_600, color=APP_TEXT_MUTED), width=220),
                    ft.Container(content=ft.Text("RE", size=11, weight=ft.FontWeight.W_600, color=APP_TEXT_MUTED), width=28),
                    ft.Container(width=80),  # botones
                ],
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            bgcolor=APP_SURFACE_MUTED,
            padding=ft.padding.Padding(left=12, top=6, right=8, bottom=6),
            border=ft.Border(bottom=ft.BorderSide(1, APP_BORDER)),
        )

        # Contenedor de la lista de reglas con scroll
        rules_container = ft.Container(
            content=ft.Column(
                [
                    col_header,
                    ft.Container(
                        content=self._rules_list,
                        expand=True,
                    ),
                ],
                spacing=0,
                expand=True,
            ),
            expand=True,
            bgcolor=APP_SURFACE,
            border=ft.Border.all(1, APP_BORDER),
            border_radius=ft.BorderRadius(10, 10, 10, 10),
            shadow=surface_shadow(),
            margin=ft.Margin(left=20, top=0, right=20, bottom=20),
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
        )

        self.controls = [
            header,
            ft.Container(
                content=self._tab_bar_row,
                padding=ft.padding.Padding(left=20, top=0, right=20, bottom=0),
                border=ft.Border(bottom=ft.BorderSide(1, APP_BORDER)),
            ),
            action_bar,
            rules_container,
        ]

        self._refresh_rules_list()

    # ──────────────────────────────────────────────────────────────────────────
    # Refresh de la lista de reglas
    # ──────────────────────────────────────────────────────────────────────────

    def _refresh_rules_list(self) -> None:
        domain = ALL_DOMAINS[self._active_tab_idx]
        domain_rules = rules_engine.get_rules_for_domain(domain)
        rows = []
        for i, rule in enumerate(domain_rules):
            rows.append(self._build_rule_row(rule, i))
        if not rows:
            rows.append(
                ft.Container(
                    content=ft.Text("No hay reglas para este dominio. Añade una o restaura las predefinidas.", size=13, color=APP_TEXT_MUTED, italic=True),
                    padding=ft.padding.Padding(left=16, top=20, right=16, bottom=20),
                )
            )
        self._rules_list.controls = rows

    def _build_rule_row(self, rule: SmartRule, idx: int) -> ft.Container:
        bg = APP_SURFACE if idx % 2 == 0 else APP_SURFACE_ALT

        color_badge = ft.Container(
            width=12,
            height=12,
            bgcolor=rule.highlight_color,
            border_radius=ft.BorderRadius(6, 6, 6, 6),
        )

        enabled_cb = ft.Checkbox(
            value=rule.enabled,
            fill_color={
                ft.ControlState.SELECTED: APP_SHELL_ACCENT,
                ft.ControlState.DEFAULT: APP_BORDER,
            },
            on_change=lambda e, r=rule: self._on_toggle_enabled(r, bool(e.control.value)),
        )

        return ft.Container(
            content=ft.Row(
                [
                    ft.Container(content=enabled_cb, width=48),
                    color_badge,
                    ft.Container(
                        content=ft.Text(rule.name, size=13, color=APP_TEXT_PRIMARY, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                        expand=True,
                    ),
                    ft.Container(
                        content=ft.Text(rule.field, size=11, color=APP_TEXT_MUTED, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                        width=80,
                    ),
                    ft.Container(
                        content=ft.Text(rule.pattern, size=11, color=APP_TEXT_MUTED, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS, font_family="Courier New"),
                        width=220,
                    ),
                    ft.Container(
                        content=ft.Text("RE" if rule.is_regex else "", size=10, weight=ft.FontWeight.W_700, color="#7B52AB"),
                        width=28,
                    ),
                    ft.Row(
                        [
                            ft.IconButton(
                                icon=ft.Icons.EDIT_OUTLINED,
                                icon_size=16,
                                icon_color=APP_TEXT_MUTED,
                                tooltip="Editar",
                                mouse_cursor=CLICK_CURSOR,
                                on_click=lambda e, r=rule: self._on_edit_rule(r),
                            ),
                            ft.IconButton(
                                icon=ft.Icons.DELETE_OUTLINE,
                                icon_size=16,
                                icon_color=ft.Colors.RED_400,
                                tooltip="Eliminar",
                                mouse_cursor=CLICK_CURSOR,
                                on_click=lambda e, r=rule: self._on_delete_rule(r),
                            ),
                        ],
                        spacing=0,
                        tight=True,
                        width=80,
                    ),
                ],
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            bgcolor=bg,
            padding=ft.padding.Padding(left=12, top=4, right=8, bottom=4),
            border=ft.Border(bottom=ft.BorderSide(1, APP_BORDER)),
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Handlers
    # ──────────────────────────────────────────────────────────────────────────

    def _on_tab_click(self, idx: int) -> None:
        self._active_tab_idx = idx
        self._update_tab_bar()
        self._refresh_rules_list()
        self.app._page.update()

    def _on_add_rule(self, e) -> None:
        self._open_rule_dialog(None)

    def _on_edit_rule(self, rule: SmartRule) -> None:
        self._open_rule_dialog(rule)

    def _on_toggle_enabled(self, rule: SmartRule, enabled: bool) -> None:
        updated = SmartRule(
            id=rule.id,
            name=rule.name,
            domain=rule.domain,
            field=rule.field,
            pattern=rule.pattern,
            is_regex=rule.is_regex,
            highlight_color=rule.highlight_color,
            enabled=enabled,
        )
        rules_engine.update_rule(updated)
        self._save_rules()
        self._refresh_rules_list()
        self.app._page.update()
        # Relanzar reglas si el dominio activo coincide
        if hasattr(self.app, "rerun_rules_if_active"):
            self.app.rerun_rules_if_active()

    def _on_delete_rule(self, rule: SmartRule) -> None:
        def _confirm(e):
            rules_engine.delete_rule(rule.id)
            self._save_rules()
            self.app._close_control(confirm_dlg)
            self._refresh_rules_list()
            self.app._page.update()
            if hasattr(self.app, "rerun_rules_if_active"):
                self.app.rerun_rules_if_active()

        def _cancel(e):
            self.app._close_control(confirm_dlg)
            self.app._page.update()

        confirm_dlg = ft.AlertDialog(
            title=ft.Text("Confirmar eliminación"),
            content=ft.Text(f"¿Eliminar la regla '{rule.name}'?"),
            actions=[
                ft.TextButton("Cancelar", on_click=_cancel),
                ft.TextButton(
                    content=ft.Text("Eliminar", color=ft.Colors.RED_600),
                    on_click=_confirm,
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
            on_dismiss=lambda e: None,
        )
        self.app._open_control(confirm_dlg)
        self.app._page.update()

    def _on_reset_defaults(self, e) -> None:
        def _confirm(e):
            rules_engine.reset_to_defaults()
            self._save_rules()
            self.app._close_control(confirm_dlg)
            self._refresh_rules_list()
            self.app._page.update()
            if hasattr(self.app, "rerun_rules_if_active"):
                self.app.rerun_rules_if_active()

        def _cancel(e):
            self.app._close_control(confirm_dlg)
            self.app._page.update()

        confirm_dlg = ft.AlertDialog(
            title=ft.Text("Restaurar reglas predefinidas"),
            content=ft.Text("Se reemplazarán todas las reglas con los valores predefinidos. ¿Continuar?"),
            actions=[
                ft.TextButton("Cancelar", on_click=_cancel),
                ft.TextButton("Restaurar", on_click=_confirm),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
            on_dismiss=lambda e: None,
        )
        self.app._open_control(confirm_dlg)
        self.app._page.update()

    # ──────────────────────────────────────────────────────────────────────────
    # Diálogo de edición / creación
    # ──────────────────────────────────────────────────────────────────────────

    def _open_rule_dialog(self, rule: SmartRule | None) -> None:
        is_new = rule is None
        domain = ALL_DOMAINS[self._active_tab_idx]
        default_color = DOMAIN_COLORS.get(domain, "#888888")

        name_tf = ft.TextField(
            label="Nombre",
            value=rule.name if rule else "",
            expand=True,
            autofocus=True,
        )
        field_dd = ft.Dropdown(
            label="Campo",
            value=rule.field if rule else "*",
            options=[ft.dropdown.Option(f) for f in _FIELD_OPTIONS],
            width=160,
        )
        pattern_tf = ft.TextField(
            label="Patrón",
            value=rule.pattern if rule else "",
            expand=True,
            hint_text="Texto o expresión regular",
            multiline=False,
        )
        is_regex_cb = ft.Checkbox(
            label="Es expresión regular (regex)",
            value=rule.is_regex if rule else False,
        )
        color_tf = ft.TextField(
            label="Color highlight (hex, ej: #7B52AB)",
            value=rule.highlight_color if rule else default_color,
            width=220,
        )
        enabled_cb = ft.Checkbox(
            label="Regla activa",
            value=rule.enabled if rule else True,
        )
        error_text = ft.Text("", color=ft.Colors.RED_600, size=12)

        def _save(e):
            name = (name_tf.value or "").strip()
            pattern = (pattern_tf.value or "").strip()
            error_text.value = ""
            if not name:
                error_text.value = "El nombre es obligatorio."
                self.app._page.update()
                return
            if not pattern:
                error_text.value = "El patrón es obligatorio."
                self.app._page.update()
                return
            if is_regex_cb.value:
                try:
                    re.compile(pattern)
                except re.error as ex:
                    error_text.value = f"Regex inválida: {ex}"
                    self.app._page.update()
                    return

            color = (color_tf.value or "").strip() or default_color
            if not color.startswith("#"):
                color = "#" + color

            if is_new:
                new_rule = SmartRule(
                    id=str(uuid.uuid4()),
                    name=name,
                    domain=domain,
                    field=field_dd.value or "*",
                    pattern=pattern,
                    is_regex=bool(is_regex_cb.value),
                    highlight_color=color,
                    enabled=bool(enabled_cb.value),
                )
                rules_engine.add_rule(new_rule)
            else:
                updated = SmartRule(
                    id=rule.id,  # type: ignore[union-attr]
                    name=name,
                    domain=domain,
                    field=field_dd.value or "*",
                    pattern=pattern,
                    is_regex=bool(is_regex_cb.value),
                    highlight_color=color,
                    enabled=bool(enabled_cb.value),
                )
                rules_engine.update_rule(updated)

            self._save_rules()
            self.app._close_control(dlg)
            self._refresh_rules_list()
            self.app._page.update()
            if hasattr(self.app, "rerun_rules_if_active"):
                self.app.rerun_rules_if_active()

        def _cancel(e):
            self.app._close_control(dlg)
            self.app._page.update()

        dlg = ft.AlertDialog(
            title=ft.Text("Añadir regla" if is_new else "Editar regla"),
            content=ft.Column(
                [
                    ft.Row([name_tf], spacing=8),
                    ft.Row([field_dd], spacing=8),
                    ft.Row([pattern_tf], spacing=8),
                    is_regex_cb,
                    ft.Row([color_tf], spacing=8),
                    enabled_cb,
                    error_text,
                ],
                tight=True,
                spacing=12,
                width=500,
            ),
            actions=[
                ft.TextButton("Cancelar", on_click=_cancel),
                ft.TextButton("Guardar", on_click=_save),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
            on_dismiss=lambda e: None,
        )
        self.app._open_control(dlg)
        self.app._page.update()

    # ──────────────────────────────────────────────────────────────────────────
    # Persistencia
    # ──────────────────────────────────────────────────────────────────────────

    def _save_rules(self) -> None:
        try:
            path = self.app._prefs_path.parent / "smart_rules.json"
            rules_engine.save(path)
        except Exception:
            pass
