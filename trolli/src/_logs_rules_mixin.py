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
        self.logs_state["rule_matches_src"] = []
        self.logs_state["active_rule_id"] = None
        self.logs_state["analysis_panel_open"] = bool(domain)
        if domain:
            self.begin_global_loading("Analizando reglas...")
            self._page.update()
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
            # Al activar un chip, desactivar filtros de nivel para no ocultar
            # filas que coinciden con la regla pero tienen un nivel distinto al filtrado.
            self.logs_state["level_filters"] = []
            self.logs_state["signal_filter_active"] = False
        self.logs_state["active_rule_id"] = new_value
        # Reset paginacion para que el usuario vea desde la primera pagina del subset
        self.logs_state["current_page"] = 1
        self.refresh_logs_view()

    def rerun_rules_if_active(self) -> None:
        """Relanza las reglas si hay un perfil activo. Usado tras editar reglas."""
        domain = self.logs_state.get("active_domain")
        if not domain:
            return
        # Invalidar solo la entrada de este dominio (el resto de dominios en caché
        # siguen siendo válidos, ya que el conjunto de filas no ha cambiado).
        _cache_key = (id(self.logs_rows), domain)
        self._rules_cache.pop(_cache_key, None)
        self.logs_state["rule_matches"] = {}
        self.begin_global_loading("Analizando reglas...")
        self._page.update()
        self.page.run_task(self._run_rules_async)

    # ── Tarea asíncrona ──────────────────────────────────────────────────────

    async def _run_rules_async(self) -> None:
        domain = self.logs_state.get("active_domain")
        if not domain:
            return

        # Ejecutar siempre sobre TODAS las filas del archivo (igual que el Dashboard),
        # para que los conteos de chips sean consistentes con independencia de los filtros
        # de nivel/búsqueda activos en la vista. Los índices de `matches` referencian
        # este snapshot; _logs_load_mixin los traducirá a posiciones en sort_rows.
        all_rows: list[dict] = list(self.logs_rows) if getattr(self, "logs_rows", None) else []
        if not all_rows:
            self.logs_state["rule_matches"] = {}
            self.logs_state["rule_matches_src"] = []
            self.end_global_loading()
            self.refresh_logs_view()
            return

        # ── Caché multi-dominio ──────────────────────────────────────────────
        # Si logs_rows ha cambiado (nuevo archivo / watcher) limpiar todas las
        # entradas antiguas; el nuevo id las hace inaccesibles de todos modos.
        _rows_id = id(self.logs_rows)
        _rules_cache: dict = getattr(self, "_rules_cache", {})
        if getattr(self, "_rules_cache_rows_id", 0) != _rows_id:
            _rules_cache.clear()
            self._rules_cache_rows_id = _rows_id
        _cache_key = (_rows_id, domain)
        if _cache_key in _rules_cache:
            cached_matches, cached_src = _rules_cache[_cache_key]
            logger.debug("[RULES] Cache hit: domain=%s rows_id=%d", domain, _rows_id)
            self.logs_state["rule_matches"] = cached_matches
            self.logs_state["rule_matches_src"] = cached_src
            self.end_global_loading()
            # Sanear active_rule_id con el resultado cacheado
            active_rid = self.logs_state.get("active_rule_id")
            if active_rid and active_rid != "__ANY__":
                still_present = any(
                    any(r.id == active_rid for r in rl)
                    for rl in cached_matches.values()
                )
                if not still_present:
                    self.logs_state["active_rule_id"] = None
            elif active_rid == "__ANY__" and not cached_matches:
                self.logs_state["active_rule_id"] = None
            self.refresh_logs_view()
            return
        # ── Cache miss: calcular ─────────────────────────────────────────────

        # Ceder un ciclo para que Flet transmita el frame con el overlay
        # antes de que el motor de reglas empiece el trabajo pesado en el thread pool.
        await asyncio.sleep(0.05)

        try:
            from smart_rules import rules_engine
            matches: dict[int, list] = await asyncio.to_thread(
                rules_engine.apply, all_rows, domain
            )
        except Exception as exc:
            logger.error("[RULES] Error aplicando reglas para dominio '%s': %s", domain, exc)
            self.end_global_loading()
            return

        # Descartar resultado si el dominio cambió mientras corría
        if self.logs_state.get("active_domain") != domain:
            self.end_global_loading()
            return

        # Guardar en caché antes de actualizar el estado
        _rules_cache[_cache_key] = (matches, all_rows)

        self.logs_state["rule_matches"] = matches
        # Guardar el snapshot usado para que load_mixin pueda traducir índices a sort_rows
        self.logs_state["rule_matches_src"] = all_rows

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

        self.end_global_loading()
        self.refresh_logs_view()
