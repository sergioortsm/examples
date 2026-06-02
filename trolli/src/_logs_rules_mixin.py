"""
_logs_rules_mixin.py
Mixin para TrelloApp: activa el motor de reglas inteligentes sobre los logs cargados.
"""
from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger("trolli")


class LogsRulesMixin:
    """Gestiona la activación de perfiles de detección y la ejecución asíncrona del motor."""

    # ── API pública (llamada desde logs_view.py y settings_view.py) ──────────

    def on_profile_change(self, domain: str | None) -> None:
        """Llamado cuando el usuario cambia el perfil activo en el dropdown."""
        self.logs_state["active_domain"] = domain
        self.logs_state["rule_matches"] = {}
        self.logs_state["active_rule_id"] = None
        self.logs_state["analysis_panel_open"] = bool(domain)
        if domain:
            self.page.run_task(self._run_rules_async)
        else:
            # Perfil desactivado: refrescar para limpiar bordes y filtro
            self.refresh_logs_view()

    def on_logs_toggle_analysis_panel(self) -> None:
        """Alterna la visibilidad del panel de análisis."""
        self.logs_state["analysis_panel_open"] = not self.logs_state.get(
            "analysis_panel_open", False
        )
        self.refresh_logs_view()

    def on_logs_toggle_rule_filter(self, rule_id: str | None) -> None:
        """Activa/desactiva el filtro de tabla por una regla concreta o "__ANY__"."""
        current = self.logs_state.get("active_rule_id")
        new_value: str | None
        if rule_id is None or current == rule_id:
            new_value = None
        else:
            new_value = rule_id
        self.logs_state["active_rule_id"] = new_value
        # Reset paginacion para que el usuario vea desde la primera pagina del subset
        self.logs_state["current_page"] = 1
        self.refresh_logs_view()

    def rerun_rules_if_active(self) -> None:
        """Relanza las reglas si hay un perfil activo. Usado tras editar reglas."""
        domain = self.logs_state.get("active_domain")
        if not domain:
            return
        self.logs_state["rule_matches"] = {}
        self.page.run_task(self._run_rules_async)

    # ── Tarea asíncrona ──────────────────────────────────────────────────────

    async def _run_rules_async(self) -> None:
        domain = self.logs_state.get("active_domain")
        if not domain:
            return

        # Snapshot de las filas ordenadas/filtradas
        sort_rows = getattr(self, "_logs_sort_cache_rows", None)
        filter_rows = getattr(self, "_logs_filter_cache_rows", None)
        if sort_rows:
            rows = list(sort_rows)
        elif filter_rows:
            rows = list(filter_rows)
        else:
            rows = []

        if not rows:
            self.logs_state["rule_matches"] = {}
            self.refresh_logs_view()
            return

        try:
            from smart_rules import rules_engine
            matches: dict[int, list] = await asyncio.to_thread(
                rules_engine.apply, rows, domain
            )
        except Exception as exc:
            logger.error("[RULES] Error aplicando reglas para dominio '%s': %s", domain, exc)
            return

        # Descartar resultado si el dominio cambió mientras corría
        if self.logs_state.get("active_domain") != domain:
            return

        self.logs_state["rule_matches"] = matches

        # Sanear active_rule_id: si la regla ya no aparece en los nuevos matches, limpiarlo.
        active_rid = self.logs_state.get("active_rule_id")
        if active_rid and active_rid != "__ANY__":
            still_present = any(
                any(r.id == active_rid for r in rule_list)
                for rule_list in matches.values()
            )
            if not still_present:
                self.logs_state["active_rule_id"] = None
        elif active_rid == "__ANY__" and not matches:
            self.logs_state["active_rule_id"] = None

        self.refresh_logs_view()
