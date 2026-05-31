"""LogsExportMixin — exportación de la vista filtrada a CSV.

Extraído de TrelloApp en main.py.
"""
import asyncio
import logging
from datetime import datetime
from pathlib import Path

from app_logging import perf_timer
from log_service import export_rows_to_csv, filter_sort_rows

logger = logging.getLogger("trolli")


class LogsExportMixin:

    def on_logs_export_click(self):
        logger.info("[CSV] on_logs_export_click invocado | file_path=%r visible_columns=%s rows=%d",
                    self.logs_state.get("file_path"),
                    self.logs_state.get("visible_columns"),
                    len(self.logs_rows))
        if bool(self.logs_state.get("_export_in_progress", False)):
            return  # debounce
        if not self.logs_state.get("file_path"):
            self.show_error("Carga un archivo antes de exportar.")
            self._page.update()
            return

        visible_columns = list(self.logs_state.get("visible_columns", []))
        if not visible_columns:
            self.show_error("No hay columnas visibles para exportar.")
            self._page.update()
            return

        self.logs_state["_export_in_progress"] = True
        self.begin_global_loading("Exportando CSV...")
        self._page.update()

        try:
            asyncio.get_running_loop().create_task(self._export_csv_deferred(visible_columns))
        except RuntimeError:
            # Fallback sin loop activo (tests/entornos sync).
            try:
                self._export_csv_sync(visible_columns)
            finally:
                self.end_global_loading()
                self.logs_state["_export_in_progress"] = False
                self._page.update()

    def _compute_export_rows(self) -> list[dict[str, str]]:
        """Devuelve filas filtradas+ordenadas reutilizando la cache si es valida."""
        sort_signature = self._logs_sort_signature()
        if sort_signature == self._logs_sort_cache_signature and self._logs_sort_cache_rows:
            return list(self._logs_sort_cache_rows)
        return filter_sort_rows(
            self.logs_rows,
            self.logs_state["columns"],
            self.logs_state["search_text"],
            self.logs_state["level_filter"],
            self.logs_state["sort_by"],
            self.logs_state["sort_desc"],
        )

    def _export_csv_sync(self, visible_columns: list[str]):
        rows_to_export = self._compute_export_rows()
        try:
            source = Path(str(self.logs_state["file_path"]))
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            export_file = source.with_name(f"{source.stem}-filtered-{timestamp}.csv")
            output_path = export_rows_to_csv(str(export_file), visible_columns, rows_to_export)
            logger.info("[CSV] Exportado: %s (%d filas)", output_path, len(rows_to_export))
            self.show_success(f"CSV exportado: {output_path}")
        except Exception as exc:
            logger.exception("[CSV] Error al exportar")
            self.show_error(f"Error al exportar: {exc}")

    async def _export_csv_deferred(self, visible_columns: list[str], min_loading_seconds: float = 0.15):
        loop = asyncio.get_running_loop()
        started = loop.time()
        await asyncio.sleep(0)  # deja pintar el overlay
        try:
            # Reusa cache si vale; si no, recalcula filter+sort fuera del loop.
            sort_signature = self._logs_sort_signature()
            if (
                sort_signature == self._logs_sort_cache_signature
                and self._logs_sort_cache_rows
            ):
                rows_to_export = list(self._logs_sort_cache_rows)
            else:
                await self._rebuild_logs_query_cache_in_thread_if_needed()
                rows_to_export = list(self._logs_sort_cache_rows)

            source = Path(str(self.logs_state["file_path"]))
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            export_file = source.with_name(f"{source.stem}-filtered-{timestamp}.csv")
            with perf_timer("export_csv_write", rows=len(rows_to_export)):
                output_path = await asyncio.to_thread(
                    export_rows_to_csv, str(export_file), visible_columns, rows_to_export
                )
            logger.info("[CSV] Exportado: %s (%d filas)", output_path, len(rows_to_export))
            self.show_success(f"CSV exportado: {output_path}")
        except Exception as exc:
            logger.exception("[CSV] Error al exportar")
            self.show_error(f"Error al exportar: {exc}")
        finally:
            remaining = min_loading_seconds - (loop.time() - started)
            if remaining > 0:
                await asyncio.sleep(remaining)
            self.end_global_loading()
            self.logs_state["_export_in_progress"] = False
            self._page.update()
