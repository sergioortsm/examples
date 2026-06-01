"""LogsLoadMixin — carga de archivo de log y refresco de vista paginada.

Extraído de TrelloApp en main.py. Accede a self.logs_rows, self.logs_state,
self.logs_view, self._page, self.file_picker, y los métodos de cache/prefs
disponibles vía herencia múltiple.
"""
import asyncio
import logging
from pathlib import Path

import flet as ft

from app_logging import perf_timer
from log_service import load_sharepoint_log, paginate_rows

logger = logging.getLogger("trolli")


class LogsLoadMixin:
    # Número máximo de filas que se muestran en modo Vivo para no saturar el render.
    LIVE_MODE_MAX_ROWS = 50

    # ------------------------------------------------------------------
    # Selector de archivo de log
    # ------------------------------------------------------------------

    def open_log_file_dialog(self, e=None):
        logger.info("[LOGS] open_log_file_dialog llamado")

        async def _pick_and_handle_file():
            files = await self.file_picker.pick_files(
                allow_multiple=False,
                file_type=ft.FilePickerFileType.CUSTOM,
                allowed_extensions=["log"],
                dialog_title="Selecciona un archivo .log de SharePoint",
            )
            self._handle_selected_log_files(files)

        try:
            asyncio.get_running_loop().create_task(_pick_and_handle_file())
        except RuntimeError:
            pass

    def _handle_selected_log_files(self, files):
        logger.info("[LOGS] _handle_selected_log_files: files=%s", files)
        if not files:
            logger.info("[LOGS] _handle_selected_log_files: sin archivos, saliendo")
            return

        file_path = getattr(files[0], "path", None)
        logger.info("[LOGS] _handle_selected_log_files: file_path=%r", file_path)
        if not file_path:
            logger.warning("[LOGS] _handle_selected_log_files: ruta vacia, saliendo")
            return

        self.load_log_file(file_path)
        if self._page.route != "/logs":
            self._page.navigate("/logs")
        else:
            self.set_logs_view()

    def on_log_file_selected(self, e):
        self._handle_selected_log_files(getattr(e, "files", None))

    # ------------------------------------------------------------------
    # Carga sincrónica y asíncrona del archivo
    # ------------------------------------------------------------------

    def _load_log_file_sync(self, file_path: str):
        self._invalidate_logs_query_cache()
        result = load_sharepoint_log(file_path)
        logger.info(
            "[LOGS] load_sharepoint_log: error=%r rows=%s columns=%s",
            result.error,
            len(result.rows),
            result.columns,
        )
        if result.error:
            self.logs_rows = []
            self.logs_state.update(
                {
                    "file_path": file_path,
                    "file_label": f"Archivo: {Path(file_path).name}",
                    "columns": [],
                    "col_values": {},
                    "visible_columns": [],
                    "visible_columns_pending": [],
                    "column_selector_expanded": False,
                    "level_options": ["All"],
                    "current_page": 1,
                    "total_pages": 1,
                    "filtered_total": 0,
                    "page_rows": [],
                    "error": result.error,
                }
            )
            self.show_error(f"No se pudo cargar el log: {result.error}")
            return

        self.logs_rows = result.rows
        visible_columns = self.logs_state.get("visible_columns", [])
        valid_visible = [c for c in visible_columns if c in result.columns]
        if not valid_visible:
            valid_visible = list(result.columns)

        pending_columns = self.logs_state.get("visible_columns_pending", [])
        valid_pending = [c for c in pending_columns if c in result.columns]
        if not valid_pending:
            valid_pending = list(valid_visible)

        sort_by = self.logs_state.get("sort_by")
        if sort_by not in result.columns:
            sort_by = result.columns[0] if result.columns else None

        level_filter = self.logs_state.get("level_filter", "All")
        level_options = ["All"] + result.col_values.get("Level", result.levels)
        if level_filter not in level_options:
            level_filter = "All"

        self.logs_state.update(
            {
                "file_path": file_path,
                "file_label": f"Archivo: {Path(file_path).name}",
                "columns": result.columns,
                "visible_columns": valid_visible,
                "visible_columns_pending": valid_pending,
                "column_selector_expanded": False,
                "col_values": result.col_values,
                "level_options": level_options,
                "sort_by": sort_by,
                "level_filter": level_filter,
                "current_page": 1,
                "error": "",
            }
        )

        self.refresh_logs_view(show_loading=False)

    async def _load_log_file_deferred(self, file_path: str, min_loading_seconds: float = 0.15):
        # Cede un ciclo para garantizar que el overlay global se pinte antes del parseo pesado.
        loop = asyncio.get_running_loop()
        started = loop.time()
        await asyncio.sleep(0)
        try:
            # run_in_executor mueve el parseo (CPU/IO intensivo) a un thread del pool,
            # liberando el event loop de Flet durante la carga del fichero.
            await loop.run_in_executor(None, self._load_log_file_sync, file_path)
        finally:
            remaining = min_loading_seconds - (loop.time() - started)
            if remaining > 0:
                await asyncio.sleep(remaining)
            self.end_global_loading()
            try:
                self.logs_view.render(self.logs_state)
            except RuntimeError:
                pass
            self._page.update()

    def load_log_file(self, file_path: str):
        logger.info("[LOGS] load_log_file: iniciando con file_path=%r", file_path)
        self.begin_global_loading("Cargando archivo .log...")
        scheduled_async = False
        self._page.update()

        try:
            asyncio.get_running_loop().create_task(self._load_log_file_deferred(file_path))
            scheduled_async = True
            return
        except RuntimeError:
            # Fallback para entornos sin loop async.
            self._load_log_file_sync(file_path)
        finally:
            if scheduled_async:
                return
            self.end_global_loading()
            try:
                self.logs_view.render(self.logs_state)
            except RuntimeError:
                pass
            self._page.update()

    # ------------------------------------------------------------------
    # Refresco de la vista paginada
    # ------------------------------------------------------------------

    def _refresh_logs_view_core(self, should_render: bool = True, page_size_override: int | None = None):
        if not self.logs_state.get("columns"):
            self._invalidate_logs_query_cache()
            self.logs_state.update(
                {
                    "page_rows": [],
                    "filtered_total": 0,
                    "total_pages": 1,
                    "current_page": 1,
                }
            )
            if should_render:
                try:
                    self.logs_view.render(self.logs_state)
                except RuntimeError:
                    pass
                self._page.update()
            return

        query_signature = self._logs_sort_signature()
        if query_signature != self._logs_sort_cache_signature:
            self._rebuild_sort_cache_sync()

        effective_page_size = (
            page_size_override if page_size_override is not None
            else int(self.logs_state["page_size"])
        )
        with perf_timer("paginate_rows", total=len(self._logs_sort_cache_rows), page_size=effective_page_size):
            page_rows, filtered_total, total_pages, safe_page = paginate_rows(
                self._logs_sort_cache_rows,
                self.logs_state["current_page"],
                effective_page_size,
            )

        self.logs_state.update(
            {
                "page_rows": page_rows,
                "filtered_total": filtered_total,
                "total_pages": total_pages,
                "current_page": safe_page,
            }
        )
        self._persist_logs_preferences_if_needed()
        if should_render:
            try:
                self.logs_view.render(self.logs_state)
            except RuntimeError:
                pass
            self._page.update()

    def refresh_logs_view(self, show_loading: bool = True):
        # Centraliza el overlay para cualquier accion que refresque el listado.
        if show_loading:
            if bool(self.logs_state.get("is_loading", False)):
                self._logs_refresh_pending = True
                return

            self.logs_state["is_loading"] = True
            self.begin_global_loading("Cargando...")
            try:
                self.logs_view.refresh_loading_state(self.logs_state)
            except RuntimeError:
                pass
            self._page.update()
            try:
                asyncio.get_running_loop().create_task(self._refresh_logs_view_deferred())
            except RuntimeError:
                # Fallback para contextos sin loop async.
                try:
                    self._refresh_logs_view_core(should_render=False)
                finally:
                    self.end_global_loading()
                    self.logs_state["is_loading"] = False
                    try:
                        self.logs_view.render(self.logs_state)
                    except RuntimeError:
                        pass
                    self._page.update()
            return

        self._refresh_logs_view_core()

    async def _refresh_logs_view_deferred(self, min_loading_seconds: float = 0.15):
        # Cede un ciclo para que Flet pinte el overlay antes del trabajo de filtrado/orden/paginacion.
        loop = asyncio.get_running_loop()
        started = loop.time()
        await asyncio.sleep(0)
        try:
            await self._rebuild_logs_query_cache_in_thread_if_needed()
            self._refresh_logs_view_core(should_render=False)
        finally:
            remaining = min_loading_seconds - (loop.time() - started)
            if remaining > 0:
                await asyncio.sleep(remaining)
            self.end_global_loading()
            self.logs_state["is_loading"] = False
            try:
                self.logs_view.render(self.logs_state)
            except RuntimeError:
                pass
            self._page.update()
            if self._logs_refresh_pending:
                self._logs_refresh_pending = False
                self.refresh_logs_view(show_loading=True)
