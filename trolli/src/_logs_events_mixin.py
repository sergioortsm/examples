"""LogsEventsMixin — handlers de eventos de UI para la vista de Logs.

Extraído de TrelloApp en main.py. Cubre búsqueda, nivel, sort, paginación
y selector de columnas visibles.
"""
import asyncio

from log_service import col_spec_name, col_names, make_col_spec

class LogsEventsMixin:
    # ------------------------------------------------------------------
    # Búsqueda y filtros
    # ------------------------------------------------------------------

    def on_logs_search_change(self, value: str):
        self.logs_state["search_text"] = value or ""
        self.logs_state["current_page"] = 1
        self.logs_view.request_scroll_to_top()
        self.refresh_logs_view()

    def on_logs_timestamp_preset_change(self, preset: str):
        self.logs_state["timestamp_preset"] = preset or "all"
        self.logs_state["current_page"] = 1
        self.logs_view.request_scroll_to_top()
        self.refresh_logs_view()

    def on_logs_column_filter_change(self, col: str, value: str):
        cf = dict(self.logs_state.get("column_filters", {}))
        if value and value.strip():
            cf[col] = value.strip()
        else:
            cf.pop(col, None)
        self.logs_state["column_filters"] = cf
        self.logs_state["current_page"] = 1
        self.logs_view.request_scroll_to_top()
        self.refresh_logs_view()

    def on_logs_level_toggle(self, level: str, checked: bool):
        """Activa/desactiva un nivel del filtro multi-selección de Level."""
        current: list[str] = list(self.logs_state.get("level_filters") or [])
        if checked:
            if level not in current:
                current.append(level)
        else:
            try:
                current.remove(level)
            except ValueError:
                pass
        self.logs_state["level_filters"] = current
        self.logs_state["current_page"] = 1
        self.logs_view.request_scroll_to_top()
        self.refresh_logs_view()

    # ------------------------------------------------------------------
    # Ordenación
    # ------------------------------------------------------------------

    def on_logs_sort_column_change(self, value: str | None):
        if value and value in self.logs_state["columns"]:
            self.logs_state["sort_by"] = value
        self.logs_state["current_page"] = 1
        self.logs_view.request_scroll_to_top()
        self.refresh_logs_view()

    def on_logs_sort_by_header(self, col_name: str, ascending: bool):
        """Llamado desde la cabecera de DataTable2 al hacer clic en una columna."""
        if col_name in self.logs_state["columns"]:
            self.logs_state["sort_by"] = col_name
            self.logs_state["sort_desc"] = not ascending
        self.logs_state["current_page"] = 1
        self.logs_view.request_scroll_to_top()
        self.refresh_logs_view()

    def on_logs_toggle_sort_direction(self):
        self.logs_state["sort_desc"] = not self.logs_state["sort_desc"]
        self.logs_state["current_page"] = 1
        self.logs_view.request_scroll_to_top()
        self.refresh_logs_view()

    # ------------------------------------------------------------------
    # Paginación
    # ------------------------------------------------------------------

    def on_logs_page_size_change(self, value: str | None):
        try:
            self.logs_state["page_size"] = int(value or "100")
        except ValueError:
            self.logs_state["page_size"] = 100
        self.logs_state["current_page"] = 1
        self.logs_view.request_scroll_to_top()
        self.refresh_logs_view()

    def on_logs_prev_page(self):
        self.logs_state["current_page"] = max(1, int(self.logs_state["current_page"]) - 1)
        self.logs_view.request_scroll_to_top()
        self.refresh_logs_view()

    def on_logs_next_page(self):
        self.logs_state["current_page"] = min(
            int(self.logs_state["total_pages"]), int(self.logs_state["current_page"]) + 1
        )
        self.logs_view.request_scroll_to_top()
        self.refresh_logs_view()

    # ------------------------------------------------------------------
    # Selector de columnas visibles
    # ------------------------------------------------------------------

    def on_logs_toggle_column(self, column_name: str, is_visible: bool):
        current: list[dict] = list(self.logs_state.get("visible_columns_pending", []))
        if is_visible:
            # Añadir solo si no existe ya; insertar en la posición correcta según el orden del fichero.
            if not any(col_spec_name(s) == column_name for s in current):
                all_columns = self.logs_state.get("columns", [])
                col_pos = all_columns.index(column_name) if column_name in all_columns else len(all_columns)
                insert_at = len(current)
                for i, s in enumerate(current):
                    name = col_spec_name(s)
                    pos = all_columns.index(name) if name in all_columns else len(all_columns)
                    if pos > col_pos:
                        insert_at = i
                        break
                current.insert(insert_at, make_col_spec(column_name))
        else:
            current = [s for s in current if col_spec_name(s) != column_name]

        if not current and self.logs_state["columns"]:
            current = [make_col_spec(self.logs_state["columns"][0])]

        self.logs_state["visible_columns_pending"] = current
        try:
            self.logs_view.refresh_column_selector(self.logs_state)
        except RuntimeError:
            pass

    def on_logs_toggle_column_filter(self, column_name: str, filter_on: bool):
        """Activa/desactiva la propiedad `filter` de una columna en pending."""
        pending: list[dict] = list(self.logs_state.get("visible_columns_pending", []))
        for spec in pending:
            if col_spec_name(spec) == column_name:
                spec["filter"] = filter_on
                break
        self.logs_state["visible_columns_pending"] = pending
        try:
            self.logs_view.refresh_column_selector(self.logs_state)
        except RuntimeError:
            pass

    def on_logs_toggle_column_selector(self):
        if not self.logs_state.get("columns"):
            return
        if bool(self.logs_state.get("is_loading", False)) or bool(self.logs_state.get("is_applying_columns", False)):
            return

        current = bool(self.logs_state.get("column_selector_expanded", False))
        next_state = not current
        self.logs_state["column_selector_expanded"] = next_state
        if next_state:
            self.logs_state["visible_columns_pending"] = [dict(s) for s in self.logs_state.get("visible_columns", [])]
        try:
            self.logs_view.refresh_column_selector(self.logs_state)
        except RuntimeError:
            pass

    def on_logs_apply_columns(self):
        columns = list(self.logs_state.get("columns", []))
        if not columns:
            return
        if bool(self.logs_state.get("is_applying_columns", False)):
            return

        pending = [s for s in self.logs_state.get("visible_columns_pending", []) if col_spec_name(s) in columns]
        if not pending:
            pending = [make_col_spec(columns[0])]

        self.logs_state["visible_columns_pending"] = pending
        self.logs_state["is_applying_columns"] = True

        try:
            self.logs_view.refresh_column_selector(self.logs_state)
        except RuntimeError:
            pass
        self._page.update()

        try:
            asyncio.get_running_loop().create_task(self._apply_columns_deferred(list(pending)))
        except RuntimeError:
            self._apply_columns_sync(list(pending))

    async def _apply_columns_deferred(self, pending: list[str]):
        # Cede el control para que Flet pinte el estado "Aplicando..." antes del trabajo de UI.
        await asyncio.sleep(0)
        self._apply_columns_sync(pending)

    def _apply_columns_sync(self, pending: list):
        try:
            self.logs_state["visible_columns"] = list(pending)
            # Limpiar filtros de columnas que ya no son visibles.
            cf = dict(self.logs_state.get("column_filters", {}))
            pending_set = set(col_names(pending))
            cleaned_cf = {col: val for col, val in cf.items() if col in pending_set}
            filters_changed = cleaned_cf != cf
            self.logs_state["column_filters"] = cleaned_cf
            self._persist_logs_preferences_if_needed()
            if filters_changed:
                # Columnas eliminadas tenían filtros activos; recomputar.
                self.refresh_logs_view()
            else:
                # Solo cambió el render de columnas; repintar sin recomputo pesado.
                self.logs_view.refresh_table_only(self.logs_state)
        finally:
            self.logs_state["is_applying_columns"] = False
            # Colapsar al finalizar para que el usuario vea el estado "Aplicando..." mientras corre.
            self.logs_state["column_selector_expanded"] = False
            try:
                self.logs_view.refresh_column_selector(self.logs_state)
            except RuntimeError:
                pass
            try:
                self.logs_view.refresh_column_filters(self.logs_state)
            except RuntimeError:
                pass
