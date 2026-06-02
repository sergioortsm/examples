"""
settings_view.py
Página de configuración de reglas inteligentes de detección en logs ULS.
"""
from __future__ import annotations

import asyncio
import re
import uuid

import flet as ft

from learn_engine import (
    LearnProgress,
    analyze_coverage,
    analyze_unmatched,
    enrich_candidates,
    filter_by_level,
    guess_domain_from_pattern,
    load_single_file,
    suggest_candidates,
)
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
        self._learn_button = ft.TextButton(
            content=ft.Row(
                [ft.Icon(ft.Icons.QUERY_STATS, size=16, color=APP_TEXT_MUTED), ft.Text("Aprender de logs…", color=APP_TEXT_MUTED, size=13)],
                tight=True,
                spacing=4,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            on_click=self._on_learn_logs,
        )

        action_bar = ft.Container(
            content=ft.Row(
                [self._add_button, self._reset_button, self._learn_button, ft.Row([], expand=True)],
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
    # Diálogo "Aprender de logs"
    # ──────────────────────────────────────────────────────────────────────────

    def _on_learn_logs(self, e) -> None:
        """Abre el diálogo de aprendizaje de reglas desde un directorio de logs."""
        progress_path = self.app._prefs_path.parent / "learn_progress.json"
        learn_progress = LearnProgress()
        learn_progress.load(progress_path)

        # ── Estado del diálogo ────────────────────────────────────────────────
        _state: dict = {
            "phase": "config",      # "config" | "analyzing" | "reviewing" | "done"
            "cancel": False,
            "new_files": [],
            "already_count": 0,
            "all_candidates": [],
            "by_category": {},
            "total_rows": 0,
            "covered_rows": 0,
            "rules_added": 0,
            "rules_skipped": 0,
            "existing_ids": {r.id for r in rules_engine.get_rules()},
            "pending_cards": [],    # lista de (cand, card) para "Aceptar todos"
        }

        # ── Controles de la fase CONFIG ───────────────────────────────────────
        dir_tf = ft.TextField(
            value=learn_progress.watched_dir or "",
            label="Directorio de logs",
            hint_text="C:\\Temp\\LOGS",
            expand=True,
            read_only=False,
            dense=True,
            text_size=13,
            border_color=APP_BORDER,
        )
        dir_status = ft.Text("", size=12, color=APP_TEXT_MUTED)

        def _do_scan(directory: str) -> None:
            if not directory:
                dir_status.value = "Indica un directorio."
                dlg.content.update() if hasattr(dlg.content, "update") else None
                self.app._page.update()
                return
            learn_progress.watched_dir = directory
            new_files, already = learn_progress.scan_new_files(directory)
            _state["new_files"] = new_files
            _state["already_count"] = already
            total = len(new_files) + already
            if total == 0:
                dir_status.value = "No se encontraron ficheros .log en ese directorio."
                start_btn.disabled = True
            else:
                dir_status.value = (
                    f"{len(new_files)} nuevos · {already} ya procesados"
                    + (f"  (de {total} en total)" if already > 0 else "")
                )
                start_btn.disabled = len(new_files) == 0
            self.app._page.update()

        def _on_browse(e) -> None:
            async def _pick() -> None:
                path = await self.app.dir_picker.get_directory_path(
                    dialog_title="Selecciona directorio de logs ULS"
                )
                if path:
                    dir_tf.value = path
                    _do_scan(path)
                    self.app._page.update()

            try:
                asyncio.get_running_loop().create_task(_pick())
            except RuntimeError:
                pass

        def _on_dir_submit(e) -> None:
            _do_scan(dir_tf.value or "")

        browse_btn = ft.TextButton(
            content=ft.Row(
                [ft.Icon(ft.Icons.FOLDER_OPEN_OUTLINED, size=15), ft.Text("Examinar…", size=13)],
                tight=True, spacing=4,
            ),
            on_click=_on_browse,
        )
        start_btn = ft.ElevatedButton(
            "Iniciar análisis",
            icon=ft.Icons.PLAY_ARROW_OUTLINED,
            disabled=True,
            on_click=lambda e: asyncio.ensure_future(_run_analysis()),
        )
        config_row = ft.Row([dir_tf, browse_btn], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER)

        # ── Picker para importar candidates.json ──────────────────────────────
        json_picker = ft.FilePicker()
        self.app._page.services.append(json_picker)

        def _on_import_json(e) -> None:
            async def _pick() -> None:
                import json as _json
                result = await json_picker.pick_files(
                    dialog_title="Selecciona candidates.json",
                    file_type=ft.FilePickerFileType.CUSTOM,
                    allowed_extensions=["json"],
                    allow_multiple=False,
                )
                if not result:
                    return
                from pathlib import Path as _Path
                path = _Path(result[0].path)
                try:
                    data = _json.loads(path.read_text(encoding="utf-8"))
                except Exception:
                    dir_status.value = f"Error al leer {path.name}."
                    self.app._page.update()
                    return
                if not isinstance(data, list):
                    dir_status.value = "El JSON no tiene el formato esperado (lista de candidatos)."
                    self.app._page.update()
                    return
                candidates = [c for c in data if isinstance(c, dict) and "id" in c]
                candidates = [c for c in candidates if c["id"] not in _state["existing_ids"]]
                candidates = [c for c in candidates if c["id"] not in learn_progress.skipped_ids]
                # Auto-asignar dominio desde patrón + muestra (los JSON exportados
                # suelen llevar "SPFx" como valor por defecto en todos los campos).
                for _c in candidates:
                    guessed = guess_domain_from_pattern(
                        _c.get("pattern", ""),
                        _c.get("_sample", ""),
                    )
                    _c["domain"] = guessed
                    _c["highlight_color"] = DOMAIN_COLORS.get(guessed, "#888888")
                _populate_reviewing(candidates, f"{len(candidates)} candidatos cargados desde «{path.name}»")

            try:
                asyncio.get_running_loop().create_task(_pick())
            except RuntimeError:
                pass

        import_btn = ft.TextButton(
            content=ft.Row(
                [ft.Icon(ft.Icons.UPLOAD_FILE_OUTLINED, size=15), ft.Text("Importar JSON…", size=13)],
                tight=True, spacing=4,
            ),
            on_click=_on_import_json,
        )

        # ── Controles de la fase ANALYZING ───────────────────────────────────
        progress_bar  = ft.ProgressBar(value=0, bgcolor=APP_BORDER, color=APP_SHELL_ACCENT, expand=True)
        progress_lbl  = ft.Text("Preparando…", size=12, color=APP_TEXT_MUTED)
        stop_btn = ft.TextButton(
            content=ft.Row(
                [ft.Icon(ft.Icons.STOP_CIRCLE_OUTLINED, size=15, color=ft.Colors.RED_400),
                 ft.Text("Detener", size=13, color=ft.Colors.RED_400)],
                tight=True, spacing=4,
            ),
            on_click=lambda e: _set_cancel(),
        )

        def _set_cancel() -> None:
            _state["cancel"] = True
            stop_btn.disabled = True
            progress_lbl.value = "Deteniendo tras el fichero actual…"
            self.app._page.update()

        # ── Controles de la fase REVIEWING ────────────────────────────────────
        coverage_lbl  = ft.Text("", size=13, color=APP_TEXT_MUTED)
        candidates_col = ft.Column([], spacing=6, scroll=ft.ScrollMode.AUTO)
        stats_lbl      = ft.Text("0 añadidas · 0 saltadas", size=12, color=APP_TEXT_MUTED, italic=True)

        def _build_candidate_card(cand: dict, card_ref: list) -> ft.Container:
            """Construye una card para un candidato de regla."""
            domain_dd = ft.Dropdown(
                value=cand["domain"],
                options=[ft.dropdown.Option(d) for d in ALL_DOMAINS],
                dense=True,
                text_size=12,
                width=180,
                border_color=APP_BORDER,
                on_select=lambda e, c=cand: c.update({"domain": e.control.value,
                                                       "highlight_color": DOMAIN_COLORS.get(e.control.value, "#888888")}),
            )
            pattern_tf = ft.TextField(
                value=cand["pattern"],
                dense=True,
                text_size=12,
                expand=True,
                border_color=APP_BORDER,
                on_change=lambda e, c=cand: c.update({"pattern": e.control.value}),
            )
            color_dot = ft.Container(
                width=10, height=10,
                bgcolor=cand["highlight_color"],
                border_radius=ft.BorderRadius(5, 5, 5, 5),
            )

            def _accept(e, c=cand, ref=card_ref):
                _add_candidate(c, ref[0])

            def _skip(e, c=cand, ref=card_ref):
                _skip_candidate(c, ref[0])

            card = ft.Container(
                content=ft.Column(
                    [
                        ft.Row(
                            [
                                color_dot,
                                ft.Text(
                                    f"{cand['_count']:,} ocurrencias",
                                    size=11,
                                    weight=ft.FontWeight.W_600,
                                    color=APP_SHELL_ACCENT,
                                ),
                                ft.Text(
                                    cand["_sample"][:80],
                                    size=11,
                                    color=APP_TEXT_MUTED,
                                    italic=True,
                                    expand=True,
                                    max_lines=1,
                                    overflow=ft.TextOverflow.ELLIPSIS,
                                ),
                            ],
                            spacing=6,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        ft.Row(
                            [pattern_tf, domain_dd],
                            spacing=8,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        ft.Row(
                            [
                                ft.TextButton(
                                    content=ft.Row(
                                        [ft.Icon(ft.Icons.CHECK, size=14, color=ft.Colors.GREEN_600),
                                         ft.Text("Añadir", size=12, color=ft.Colors.GREEN_600)],
                                        tight=True, spacing=4,
                                    ),
                                    on_click=_accept,
                                ),
                                ft.TextButton(
                                    content=ft.Row(
                                        [ft.Icon(ft.Icons.CLOSE, size=14, color=APP_TEXT_MUTED),
                                         ft.Text("Saltar", size=12, color=APP_TEXT_MUTED)],
                                        tight=True, spacing=4,
                                    ),
                                    on_click=_skip,
                                ),
                            ],
                            spacing=4,
                        ),
                    ],
                    spacing=6,
                    tight=True,
                ),
                bgcolor=APP_SURFACE,
                border=ft.Border.all(1, APP_BORDER),
                border_radius=ft.BorderRadius(8, 8, 8, 8),
                padding=ft.padding.Padding(left=12, top=8, right=12, bottom=8),
            )
            card_ref.append(card)
            return card

        def _add_candidate(cand: dict, card: ft.Container) -> None:
            if cand["id"] in _state["existing_ids"]:
                _skip_candidate(cand, card)
                return
            from smart_rules import SmartRule as SR
            new_rule = SR(
                id=cand["id"],
                name=cand["name"],
                domain=cand["domain"],
                field=cand["field"],
                pattern=cand["pattern"],
                is_regex=cand["is_regex"],
                highlight_color=cand["highlight_color"],
                enabled=True,
            )
            rules_engine.add_rule(new_rule)
            self._save_rules()
            self._refresh_rules_list()
            _state["existing_ids"].add(cand["id"])
            _state["rules_added"] += 1
            _update_stats()
            _hide_card(card)
            if hasattr(self.app, "rerun_rules_if_active"):
                self.app.rerun_rules_if_active()

        def _skip_candidate(cand: dict, card: ft.Container) -> None:
            learn_progress.skipped_ids.add(cand["id"])
            learn_progress.save(progress_path)
            _state["rules_skipped"] += 1
            _update_stats()
            _hide_card(card)

        def _hide_card(card: ft.Container) -> None:
            card.visible = False
            _check_all_done()
            self.app._page.update()

        def _check_all_done() -> None:
            pending = [card for _, card in _state["pending_cards"] if card.visible]
            if pending:
                return
            # No quedan tarjetas: mostrar banner de resumen y cerrar
            added   = _state["rules_added"]
            skipped = _state["rules_skipped"]
            candidates_col.controls.clear()
            candidates_col.controls.append(
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Row(
                                [
                                    ft.Icon(ft.Icons.CHECK_CIRCLE_OUTLINED,
                                            color=ft.Colors.GREEN_600, size=22),
                                    ft.Text(
                                        "¡Revisión completada!",
                                        size=14,
                                        weight=ft.FontWeight.W_600,
                                        color=ft.Colors.GREEN_600,
                                    ),
                                ],
                                spacing=8,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            ),
                            ft.Text(
                                f"{added} regla{'s' if added != 1 else ''} añadida{'s' if added != 1 else ''} · "
                                f"{skipped} descartada{'s' if skipped != 1 else ''}.",
                                size=12,
                                color=APP_TEXT_MUTED,
                            ),
                        ],
                        spacing=6,
                        tight=True,
                    ),
                    bgcolor=APP_SURFACE,
                    border=ft.Border.all(1, ft.Colors.GREEN_200),
                    border_radius=ft.BorderRadius(8, 8, 8, 8),
                    padding=ft.padding.Padding(left=16, top=12, right=16, bottom=12),
                )
            )
            accept_all_btn.visible = False
            close_dlg_btn.text = "Cerrar"

        def _update_stats() -> None:
            stats_lbl.value = (
                f"{_state['rules_added']} añadidas · "
                f"{_state['rules_skipped']} saltadas"
            )
            self.app._page.update()

        def _accept_all(e) -> None:
            for cand, card in list(_state["pending_cards"]):
                if card.visible:
                    _add_candidate(cand, card)

        accept_all_btn = ft.TextButton(
            content=ft.Row(
                [ft.Icon(ft.Icons.CHECK_BOX_OUTLINED, size=14, color=ft.Colors.GREEN_600),
                 ft.Text("Aceptar todos", size=12, color=ft.Colors.GREEN_600)],
                tight=True, spacing=4,
            ),
            on_click=_accept_all,
        )

        # ── Contenido principal del diálogo (contenedor de fases) ─────────────
        phase_config = ft.Column(
            [
                ft.Text("Selecciona el directorio que contiene los ficheros .log ULS:",
                        size=13, color=APP_TEXT_PRIMARY),
                config_row,
                ft.Row([dir_status], spacing=0),
                ft.Row(
                    [start_btn, ft.Container(width=12), import_btn],
                    spacing=0,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            ],
            spacing=10,
            tight=True,
            visible=True,
        )

        phase_analyzing = ft.Column(
            [
                ft.Row([progress_bar], vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ft.Row([progress_lbl, ft.Row([], expand=True), stop_btn],
                       vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ],
            spacing=8,
            tight=True,
            visible=False,
        )

        phase_reviewing = ft.Column(
            [
                ft.Row([coverage_lbl], spacing=0),
                ft.Container(
                    content=candidates_col,
                    height=380,
                    border=ft.Border.all(1, APP_BORDER),
                    border_radius=ft.BorderRadius(8, 8, 8, 8),
                    padding=ft.padding.Padding(left=8, top=8, right=8, bottom=8),
                    bgcolor=APP_SURFACE_MUTED,
                    clip_behavior=ft.ClipBehavior.HARD_EDGE,
                ),
                ft.Row(
                    [stats_lbl, ft.Row([], expand=True), accept_all_btn],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            ],
            spacing=8,
            tight=True,
            visible=False,
        )

        dlg_body = ft.Column(
            [phase_config, phase_analyzing, phase_reviewing],
            spacing=0,
            tight=True,
            width=680,
        )

        def _show_phase(name: str) -> None:
            _state["phase"] = name
            phase_config.visible    = (name == "config")
            phase_analyzing.visible = (name == "analyzing")
            phase_reviewing.visible = (name == "reviewing")
            self.app._page.update()

        def _populate_reviewing(candidates: list, coverage_text: str) -> None:
            """Rellena la fase de revisión y la muestra."""
            coverage_lbl.value = coverage_text
            _state["all_candidates"] = candidates
            _state["pending_cards"].clear()
            candidates_col.controls.clear()
            if not candidates:
                candidates_col.controls.append(
                    ft.Text(
                        "No hay candidatos nuevos: la cobertura cubre todos los patrones encontrados.",
                        size=13,
                        color=APP_TEXT_MUTED,
                        italic=True,
                    )
                )
            else:
                for cand in candidates:
                    card_ref: list = []
                    card = _build_candidate_card(cand, card_ref)
                    candidates_col.controls.append(card)
                    _state["pending_cards"].append((cand, card))
            _show_phase("reviewing")

        # ── Acciones del diálogo ──────────────────────────────────────────────
        close_dlg_btn = ft.TextButton("Cerrar", on_click=lambda e: _close())

        def _close() -> None:
            _state["cancel"] = True
            try:
                self.app._page.services.remove(json_picker)
            except (ValueError, AttributeError):
                pass
            self.app._close_control(dlg)
            self.app._page.update()

        dlg = ft.AlertDialog(
            title=ft.Row(
                [
                    ft.Icon(ft.Icons.QUERY_STATS, size=18, color=APP_TEXT_MUTED),
                    ft.Text("Aprender de logs", weight=ft.FontWeight.W_600),
                ],
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            content=dlg_body,
            actions=[close_dlg_btn],
            actions_alignment=ft.MainAxisAlignment.END,
            on_dismiss=lambda e: None,
        )

        # ── Inicio de escaneo inicial si ya hay directorio guardado ───────────
        if learn_progress.watched_dir:
            _do_scan(learn_progress.watched_dir)

        # ── Lógica de análisis asíncrono ──────────────────────────────────────
        async def _run_analysis() -> None:
            directory = dir_tf.value or ""
            if not directory:
                return

            learn_progress.watched_dir = directory
            new_files, _ = learn_progress.scan_new_files(directory)
            _state["new_files"] = new_files
            if not new_files:
                return

            _show_phase("analyzing")
            _state["cancel"] = False
            stop_btn.disabled = False

            all_unmatched: list[dict] = []
            all_rows_count = 0
            all_covered   = 0
            completed_files: list[tuple] = []   # (fpath, candidates_found, rules_added_at_that_time)

            total = len(new_files)
            for idx, fpath in enumerate(new_files):
                if _state["cancel"]:
                    break

                progress_bar.value = idx / total
                progress_lbl.value = f"Analizando {idx + 1} de {total}: {fpath.name}"
                self.app._page.update()

                rows, _, err = load_single_file(fpath)
                if err:
                    completed_files.append(fpath)
                    learn_progress.mark_processed(fpath, 0, 0)
                    learn_progress.save(progress_path)
                    continue

                error_rows = filter_by_level(rows)
                all_rows_count += len(error_rows)

                _, unmatched, covered = analyze_coverage(rules_engine, error_rows)
                all_covered   += covered
                all_unmatched.extend(unmatched)

                # Marcar como procesado (candidatos y reglas añadidas se actualizan al final)
                completed_files.append(fpath)

                await asyncio.sleep(0)   # cede el hilo para que la UI respire

            if _state["cancel"]:
                # Guardar solo los ficheros completados antes del cancel
                for fpath in completed_files:
                    if not learn_progress.is_processed(fpath):
                        learn_progress.mark_processed(fpath, 0, 0)
                learn_progress.save(progress_path)
                _show_phase("config")
                _do_scan(directory)
                return

            # Marcar el resto como procesados temporalmente (se actualizarán con candidatos reales)
            for fpath in completed_files:
                if not learn_progress.is_processed(fpath):
                    learn_progress.mark_processed(fpath, 0, 0)
            learn_progress.save(progress_path)

            progress_bar.value = 1.0
            progress_lbl.value = "Generando candidatos…"
            self.app._page.update()
            await asyncio.sleep(0)

            _state["total_rows"]   = all_rows_count
            _state["covered_rows"] = all_covered

            # Generar candidatos
            analysis  = analyze_unmatched(all_unmatched)
            norm_ctr  = analysis["norm_counter"]
            by_cat    = analysis["by_category"]
            candidates = suggest_candidates(norm_ctr)
            candidates = enrich_candidates(candidates, by_cat)

            # Filtrar los que ya existen o ya fueron descartados
            candidates = [c for c in candidates if c["id"] not in _state["existing_ids"]]
            candidates = [c for c in candidates if c["id"] not in learn_progress.skipped_ids]
            _state["all_candidates"] = candidates
            _state["by_category"]    = by_cat

            # ── Construir fase REVIEWING ──────────────────────────────────────
            pct = (all_covered / all_rows_count * 100) if all_rows_count else 0.0
            coverage_text = (
                f"Cobertura: {pct:.1f}%  "
                f"({all_covered:,} / {all_rows_count:,} filas de error cubierta)  ·  "
                f"{len(candidates)} candidatos nuevos"
            )
            _populate_reviewing(candidates, coverage_text)

        # ── Abrir el diálogo ──────────────────────────────────────────────────
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
