"""
search_view.py
Vista Buscador IA — análisis de logs SharePoint ULS con Ollama local.
Sigue el mismo patrón que SettingsView / LogsView.
"""
from __future__ import annotations

import flet as ft

from ollama_service import OllamaService
from ui_tokens import (
    APP_BORDER,
    APP_ERROR_BG,
    APP_ERROR_FG,
    APP_SHELL_ACCENT,
    APP_SHELL_ACCENT_HOVER,
    APP_SURFACE,
    APP_SURFACE_ALT,
    APP_SURFACE_MUTED,
    APP_TEXT_MUTED,
    APP_TEXT_PRIMARY,
    APP_SUCCESS_BG,
    APP_SUCCESS_FG,
    surface_shadow,
)

_PLACEHOLDER = (
    "Pega aquí los logs de SharePoint ULS, IIS o Event Viewer…\n\n"
    "Ejemplo:\n"
    "Could not load assembly COLABORAWS.Infrastructure\n"
    "SPDistributedCachePointerWrapper failed\n"
    "Access denied for SPFarm account"
)

# Niveles ULS considerados relevantes para enviar a Ollama
_RELEVANT_LEVELS = {"UNEXPECTED", "CRITICAL", "ERROR", "HIGH"}
# Máximo de líneas a enviar (ventana de contexto del LLM)
_MAX_IMPORT_LINES = 60
# Columnas ULS útiles para el LLM (en orden de prioridad)
_USEFUL_COLS = ["Timestamp", "Process", "Area", "Category", "EventID", "Level", "Message", "Correlation"]


class SearchView(ft.Column):
    """Vista principal del Buscador IA con Ollama."""

    def __init__(self, app) -> None:
        super().__init__(
            expand=True,
            spacing=0,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        )
        self.app = app
        self._service = OllamaService()
        self._analyzing = False

        # Controles que se actualizan dinámicamente
        self._status_chip: ft.Container | None = None
        self._import_btn: ft.OutlinedButton | None = None
        self._import_label: ft.Text | None = None
        self._model_dropdown: ft.Dropdown | None = None
        self._log_input: ft.TextField | None = None
        self._analyze_btn: ft.ElevatedButton | None = None
        self._progress_ring: ft.ProgressRing | None = None
        self._result_text: ft.Text | None = None
        self._result_container: ft.Container | None = None

        self._build()

    # ------------------------------------------------------------------
    # Construcción de la UI
    # ------------------------------------------------------------------

    def _build(self) -> None:
        # ── Chip de estado Ollama ──────────────────────────────────────
        self._status_chip = ft.Container(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.CIRCLE, size=10, color=APP_TEXT_MUTED),
                    ft.Text("Comprobando…", size=12, color=APP_TEXT_MUTED),
                ],
                spacing=5,
                tight=True,
            ),
            padding=ft.padding.Padding(left=10, top=4, right=10, bottom=4),
            border_radius=12,
            bgcolor=APP_SURFACE_MUTED,
            border=ft.Border.all(1, APP_BORDER),
        )

        # ── Botón importar desde Logs ─────────────────────────────────
        self._import_label = ft.Text(
            "Sin logs cargados",
            size=11,
            color=APP_TEXT_MUTED,
            italic=True,
        )
        self._import_btn = ft.OutlinedButton(
            content="Importar desde Logs",
            icon=ft.Icons.INPUT_ROUNDED,
            disabled=True,
            tooltip=(
                "Importa automáticamente las líneas Unexpected / Critical / Error / High "
                "del archivo cargado en la vista Logs (máx. 60 líneas)"
            ),
            on_click=self._on_import_click,
            style=ft.ButtonStyle(
                side={
                    ft.ControlState.DEFAULT: ft.BorderSide(1, APP_SHELL_ACCENT),
                    ft.ControlState.HOVERED: ft.BorderSide(1, APP_SHELL_ACCENT),
                    ft.ControlState.DISABLED: ft.BorderSide(1, APP_BORDER),
                },
                color={
                    ft.ControlState.DEFAULT: APP_SHELL_ACCENT,
                    ft.ControlState.HOVERED: APP_SHELL_ACCENT_HOVER,
                    ft.ControlState.DISABLED: APP_TEXT_MUTED,
                },
            ),
        )

        # ── Selector de modelo ────────────────────────────────────────
        self._model_dropdown = ft.Dropdown(
            label="Modelo",
            hint_text="Sin modelos disponibles",
            options=[],
            disabled=True,
            width=280,
            border_color=APP_BORDER,
            focused_border_color=APP_SHELL_ACCENT,
            text_style=ft.TextStyle(color=APP_TEXT_PRIMARY, size=13),
        )

        # ── Área de texto de logs ──────────────────────────────────────
        self._log_input = ft.TextField(
            hint_text=_PLACEHOLDER,
            multiline=True,
            min_lines=8,
            max_lines=16,
            expand=True,
            border_color=APP_BORDER,
            focused_border_color=APP_SHELL_ACCENT,
            text_size=12,
            bgcolor=APP_SURFACE,
            content_padding=ft.padding.Padding(left=12, top=12, right=12, bottom=12),
        )

        # ── Botón analizar ────────────────────────────────────────────
        self._progress_ring = ft.ProgressRing(
            width=16,
            height=16,
            stroke_width=2,
            color=APP_SHELL_ACCENT,
            visible=False,
        )
        self._analyze_btn = ft.ElevatedButton(
            "Analizar",
            icon=ft.Icons.MANAGE_SEARCH,
            disabled=True,
            on_click=self._on_analyze_click,
            style=ft.ButtonStyle(
                bgcolor={
                    ft.ControlState.DEFAULT: APP_SHELL_ACCENT,
                    ft.ControlState.HOVERED: APP_SHELL_ACCENT_HOVER,
                    ft.ControlState.DISABLED: APP_SURFACE_MUTED,
                },
                color={
                    ft.ControlState.DEFAULT: APP_SURFACE,
                    ft.ControlState.HOVERED: APP_SURFACE,
                },
            ),
        )

        # ── Panel de resultado ────────────────────────────────────────
        self._result_text = ft.Text(
            value="",
            selectable=True,
            size=13,
            color=APP_TEXT_PRIMARY,
        )
        self._result_container = ft.Container(
            content=ft.Column(
                [self._result_text],
                scroll=ft.ScrollMode.AUTO,
                spacing=0,
            ),
            bgcolor=APP_SURFACE_ALT,
            border=ft.Border.all(1, APP_BORDER),
            border_radius=6,
            padding=ft.padding.Padding(left=14, top=14, right=14, bottom=14),
            expand=True,
            visible=False,
            shadow=surface_shadow(offset_y=2, blur_radius=8),
        )

        # ── Ensamblado de la vista ────────────────────────────────────
        header = ft.Container(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.MANAGE_SEARCH, color=APP_SHELL_ACCENT, size=22),
                    ft.Text(
                        "Buscador IA · SharePoint Logs",
                        size=16,
                        weight=ft.FontWeight.W_600,
                        color=APP_TEXT_PRIMARY,
                    ),
                    ft.Container(expand=True),
                    self._status_chip,
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=8,
            ),
            padding=ft.padding.Padding(left=24, top=16, right=24, bottom=16),
            border=ft.Border(
                bottom=ft.BorderSide(1, APP_BORDER)
            ),
            bgcolor=APP_SURFACE,
        )

        toolbar = ft.Container(
            content=ft.Row(
                [
                    self._model_dropdown,
                    ft.Container(expand=True),
                    ft.Row(
                        [self._progress_ring, self._analyze_btn],
                        spacing=8,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.padding.Padding(left=24, top=12, right=24, bottom=12),
        )

        body = ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Text(
                                "Logs a analizar",
                                size=12,
                                weight=ft.FontWeight.W_600,
                                color=APP_TEXT_MUTED,
                            ),
                            ft.Container(expand=True),
                            self._import_label,
                            ft.Container(width=8),
                            self._import_btn,
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    self._log_input,
                    self._result_container,
                ],
                spacing=10,
                expand=True,
            ),
            expand=True,
            padding=ft.padding.Padding(left=24, top=12, right=24, bottom=12),
        )

        self.controls = [header, toolbar, body]

    # ------------------------------------------------------------------
    # Ciclo de vida
    # ------------------------------------------------------------------

    def did_mount(self) -> None:
        """Llamado por Flet cuando el control se monta en el árbol."""
        self._check_ollama()

    def refresh(self) -> None:
        """Re-verifica el estado de Ollama y actualiza el botón Importar al navegar a esta vista."""
        self._check_ollama()
        self._update_import_btn()

    # ------------------------------------------------------------------
    # Lógica interna
    # ------------------------------------------------------------------

    def _check_ollama(self) -> None:
        """Verifica la conexión con Ollama y carga la lista de modelos."""
        connected = self._service.check_connection()
        models = self._service.get_models() if connected else []
        self._update_status_ui(connected, models)
        self._update_import_btn()

    def _update_import_btn(self) -> None:
        """Activa/desactiva el botón Importar según si hay filas en el cache de logs."""
        rows: list[dict] = getattr(self.app, "_logs_sort_cache_rows", []) or []
        file_label: str = ""
        if hasattr(self.app, "logs_state"):
            file_label = self.app.logs_state.get("file_label") or ""

        has_rows = bool(rows)
        self._import_btn.disabled = not has_rows  # type: ignore[union-attr]
        if has_rows:
            relevant_count = sum(
                1 for r in rows if (r.get("Level") or "").upper() in _RELEVANT_LEVELS
            )
            self._import_label.value = f"{relevant_count} líneas relevantes · {file_label}"  # type: ignore[union-attr]
        else:
            self._import_label.value = "Sin logs cargados"  # type: ignore[union-attr]
        try:
            self.update()
        except Exception:
            pass

    def _on_import_click(self, e) -> None:
        """Extrae las líneas más relevantes del cache de logs y las mete en el textarea."""
        rows: list[dict] = getattr(self.app, "_logs_sort_cache_rows", []) or []
        if not rows:
            self.app.show_error("No hay logs cargados en la vista Logs.")
            return

        state = getattr(self.app, "logs_state", {})
        file_label = state.get("file_label", "desconocido")
        search_text = state.get("search_text", "")
        level_filters = state.get("level_filters") or []
        rule_matches: dict = state.get("rule_matches") or {}

        # Filtrar solo niveles relevantes; si no hay, usar todo el cache filtrado
        relevant = [r for r in rows if (r.get("Level") or "").upper() in _RELEVANT_LEVELS]
        if not relevant:
            relevant = rows

        sample = relevant[:_MAX_IMPORT_LINES]

        # Cabecera de contexto para que el LLM entienda el origen de los datos
        lines: list[str] = [
            "=== CONTEXTO ===",
            f"Archivo         : {file_label}",
        ]
        if search_text:
            lines.append(f"Búsqueda activa : {search_text}")
        if level_filters:
            lines.append(f"Filtros nivel   : {', '.join(level_filters)}")
        if rule_matches:
            resumen = ", ".join(
                f"{rid} ×{len(hits)}" for rid, hits in list(rule_matches.items())[:5]
            )
            lines.append(f"Smart Rules     : {resumen}")
        lines.append(
            f"Líneas enviadas : {len(sample)} de {len(relevant)} relevantes"
            f" (total en cache: {len(rows)})"
        )
        lines.append("=" * 50)
        lines.append("")

        # Columnas a incluir: solo las presentes en el archivo cargado
        columns_present = set(rows[0].keys()) if rows else set()
        cols = [c for c in _USEFUL_COLS if c in columns_present]
        if not cols:
            cols = [c for c in rows[0].keys() if not c.startswith("_")]

        lines.append("\t".join(cols))
        lines.append("-" * 60)
        for row in sample:
            lines.append("\t".join(str(row.get(c, "")) for c in cols))

        self._log_input.value = "\n".join(lines)  # type: ignore[union-attr]
        self._result_text.value = ""  # type: ignore[union-attr]
        self._result_container.visible = False  # type: ignore[union-attr]
        try:
            self.update()
        except Exception:
            pass

    def _update_status_ui(self, connected: bool, models: list[str]) -> None:
        # Chip de estado
        chip_row = self._status_chip.content  # type: ignore[union-attr]
        chip_icon: ft.Icon = chip_row.controls[0]
        chip_label: ft.Text = chip_row.controls[1]

        if connected:
            chip_icon.color = APP_SUCCESS_FG
            chip_label.value = "Ollama activo"
            chip_label.color = APP_SUCCESS_FG
            self._status_chip.bgcolor = APP_SUCCESS_BG  # type: ignore[union-attr]
            self._status_chip.border = ft.Border.all(1, APP_SUCCESS_FG)  # type: ignore[union-attr]
        else:
            chip_icon.color = APP_ERROR_FG
            chip_label.value = "Ollama no disponible"
            chip_label.color = APP_ERROR_FG
            self._status_chip.bgcolor = APP_ERROR_BG  # type: ignore[union-attr]
            self._status_chip.border = ft.Border.all(1, APP_ERROR_FG)  # type: ignore[union-attr]

        # Dropdown de modelos
        if models:
            self._model_dropdown.options = [  # type: ignore[union-attr]
                ft.dropdown.Option(m) for m in models
            ]
            self._model_dropdown.value = models[0]  # type: ignore[union-attr]
            self._model_dropdown.disabled = False  # type: ignore[union-attr]
            self._analyze_btn.disabled = False  # type: ignore[union-attr]
        else:
            self._model_dropdown.options = []  # type: ignore[union-attr]
            self._model_dropdown.value = None  # type: ignore[union-attr]
            self._model_dropdown.disabled = True  # type: ignore[union-attr]
            self._analyze_btn.disabled = True  # type: ignore[union-attr]

        try:
            self.update()
        except Exception:
            pass  # La vista puede no estar montada aún en el primer build

    def _on_analyze_click(self, e) -> None:
        if self._analyzing:
            return
        text = (self._log_input.value or "").strip()  # type: ignore[union-attr]
        if not text:
            self.app.show_error("Pega primero los logs que deseas analizar.")
            return
        model = self._model_dropdown.value  # type: ignore[union-attr]
        if not model:
            self.app.show_error("Selecciona un modelo Ollama antes de analizar.")
            return

        self._set_loading(True)
        self._service.analyze(
            text=text,
            model=model,
            on_result=self._on_result,
            on_error=self._on_error,
        )

    def _on_result(self, text: str) -> None:
        self._result_text.value = text  # type: ignore[union-attr]
        self._result_container.visible = True  # type: ignore[union-attr]
        self._set_loading(False)
        try:
            self.update()
        except Exception:
            pass

    def _on_error(self, message: str) -> None:
        self._set_loading(False)
        try:
            self.app.show_error(message)
        except Exception:
            pass

    def _set_loading(self, loading: bool) -> None:
        self._analyzing = loading
        self._progress_ring.visible = loading  # type: ignore[union-attr]
        self._analyze_btn.disabled = loading  # type: ignore[union-attr]
        try:
            self.update()
        except Exception:
            pass
