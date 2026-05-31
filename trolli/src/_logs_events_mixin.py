"""LogsEventsMixin — handlers de eventos de UI para la vista de Logs.

Extraído de TrelloApp en main.py. Cubre búsqueda, nivel, sort, paginación
y selector de columnas visibles.
"""
import asyncio


class LogsEventsMixin:
    # ------------------------------------------------------------------
    # Búsqueda y filtros
    # ------------------------------------------------------------------

    def on_logs_search_change(self, value: str):
        self.logs_state["search_text"] = value or ""
        self.logs_state["current_page"] = 1
        self.logs_view.request_scroll_to_top()
        self.refresh_logs_view()

    def on_logs_level_change(self, value: str | None):
        self.logs_state["level_filter"] = value or "All"
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
        current = list(self.logs_state.get("visible_columns_pending", []))
        if is_visible and column_name not in current:
            current.append(column_name)
        if not is_visible and column_name in current:
            current.remove(column_name)

        if not current and self.logs_state["columns"]:
            current = [self.logs_state["columns"][0]]

        self.logs_state["visible_columns_pending"] = current
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
            self.logs_state["visible_columns_pending"] = list(self.logs_state.get("visible_columns", []))
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

        pending = [c for c in self.logs_state.get("visible_columns_pending", []) if c in columns]
        if not pending:
            pending = [columns[0]]

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

    def _apply_columns_sync(self, pending: list[str]):
        try:
            self.logs_state["visible_columns"] = list(pending)
            # Cambiar columnas visibles no altera filtros, orden ni pagina.
            # Evitamos recomputo pesado y solo repintamos la tabla actual.
            self._persist_logs_preferences_if_needed()
            self.logs_view.refresh_table_only(self.logs_state)
        finally:
            self.logs_state["is_applying_columns"] = False
            # Colapsar al finalizar para que el usuario vea el estado "Aplicando..." mientras corre.
            self.logs_state["column_selector_expanded"] = False
            try:
                self.logs_view.refresh_column_selector(self.logs_state)
            except RuntimeError:
                pass
