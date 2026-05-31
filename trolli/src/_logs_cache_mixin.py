"""LogsCacheMixin — firmas de cache y recomputo de filtrado/orden de Logs.

Extraído de TrelloApp en main.py. Accede a self.logs_rows, self.logs_state,
self._logs_filter_cache_* y self._logs_sort_cache_* definidos en __init__.
"""
import asyncio

from app_logging import perf_timer
from log_service import filter_rows, sort_rows


class LogsCacheMixin:
    # ------------------------------------------------------------------
    # Firmas (tuplas hashables para comparar estado de cache)
    # ------------------------------------------------------------------

    def _logs_query_signature(self) -> tuple[object, ...]:
        # Firma combinada (filter + sort + page_size) usada por la cache de export
        # y como conveniencia en logs/diagnostico.
        return self._logs_filter_signature() + (
            self.logs_state.get("sort_by", None),
            bool(self.logs_state.get("sort_desc", False)),
            int(self.logs_state.get("page_size", 100)),
        )

    def _logs_filter_signature(self) -> tuple[object, ...]:
        return (
            self.logs_state.get("file_path", ""),
            tuple(self.logs_state.get("columns", [])),
            self.logs_state.get("search_text", ""),
            self.logs_state.get("level_filter", "All"),
        )

    def _logs_sort_signature(self) -> tuple[object, ...]:
        return self._logs_filter_signature() + (
            self.logs_state.get("sort_by", None),
            bool(self.logs_state.get("sort_desc", False)),
        )

    def _logs_prefs_signature(self) -> tuple[object, ...]:
        return (
            self.logs_state.get("search_text", ""),
            self.logs_state.get("level_filter", "All"),
            self.logs_state.get("sort_by", None),
            bool(self.logs_state.get("sort_desc", False)),
            int(self.logs_state.get("page_size", 100)),
            tuple(self.logs_state.get("visible_columns", [])),
            tuple(sorted(dict(self.logs_state.get("column_widths", {})).items())),
            self.logs_state.get("watch_folder", ""),
            self.logs_state.get("watch_pattern", ""),
        )

    # ------------------------------------------------------------------
    # Invalidación y recomputo de cache
    # ------------------------------------------------------------------

    def _invalidate_logs_query_cache(self):
        self._logs_filter_cache_signature = None
        self._logs_filter_cache_rows = []
        self._logs_sort_cache_signature = None
        self._logs_sort_cache_rows = []

    def _rebuild_filter_cache_sync(self):
        filter_signature = self._logs_filter_signature()
        if filter_signature == self._logs_filter_cache_signature:
            return
        with perf_timer("filter_rows", rows=len(self.logs_rows)):
            self._logs_filter_cache_rows = filter_rows(
                self.logs_rows,
                self.logs_state["columns"],
                self.logs_state["search_text"],
                self.logs_state["level_filter"],
            )
        self._logs_filter_cache_signature = filter_signature
        # Si el filtrado cambia, la cache de sort dejo de ser valida.
        self._logs_sort_cache_signature = None
        self._logs_sort_cache_rows = []

    def _rebuild_sort_cache_sync(self):
        self._rebuild_filter_cache_sync()
        sort_signature = self._logs_sort_signature()
        if sort_signature == self._logs_sort_cache_signature:
            return

        # Sort-skip: si solo cambia el sentido (sort_desc) y la cache previa era
        # del mismo filtro y misma columna, reaprovechamos reversed() en O(n).
        prev_sig = self._logs_sort_cache_signature
        if (
            prev_sig is not None
            and prev_sig[:-1] == sort_signature[:-1]
            and prev_sig[-1] != sort_signature[-1]
            and self._logs_sort_cache_rows
        ):
            with perf_timer("sort_skip_reverse", rows=len(self._logs_sort_cache_rows)):
                self._logs_sort_cache_rows = list(reversed(self._logs_sort_cache_rows))
            self._logs_sort_cache_signature = sort_signature
            return

        with perf_timer("sort_rows", rows=len(self._logs_filter_cache_rows), col=self.logs_state.get("sort_by")):
            self._logs_sort_cache_rows = sort_rows(
                self._logs_filter_cache_rows,
                self.logs_state["columns"],
                self.logs_state["sort_by"],
                self.logs_state["sort_desc"],
            )
        self._logs_sort_cache_signature = sort_signature

    async def _rebuild_logs_query_cache_in_thread_if_needed(self):
        # Filtrado: si la firma cambio, lo lanzamos a un thread.
        filter_signature = self._logs_filter_signature()
        if filter_signature != self._logs_filter_cache_signature:
            with perf_timer("filter_rows_async", rows=len(self.logs_rows)):
                self._logs_filter_cache_rows = await asyncio.to_thread(
                    filter_rows,
                    self.logs_rows,
                    self.logs_state["columns"],
                    self.logs_state["search_text"],
                    self.logs_state["level_filter"],
                )
            self._logs_filter_cache_signature = filter_signature
            self._logs_sort_cache_signature = None
            self._logs_sort_cache_rows = []

        # Sort: sort-skip si solo cambio el sentido.
        sort_signature = self._logs_sort_signature()
        if sort_signature == self._logs_sort_cache_signature:
            return

        prev_sig = self._logs_sort_cache_signature
        if (
            prev_sig is not None
            and prev_sig[:-1] == sort_signature[:-1]
            and prev_sig[-1] != sort_signature[-1]
            and self._logs_sort_cache_rows
        ):
            with perf_timer("sort_skip_reverse_async", rows=len(self._logs_sort_cache_rows)):
                self._logs_sort_cache_rows = list(reversed(self._logs_sort_cache_rows))
            self._logs_sort_cache_signature = sort_signature
            return

        with perf_timer("sort_rows_async", rows=len(self._logs_filter_cache_rows), col=self.logs_state.get("sort_by")):
            self._logs_sort_cache_rows = await asyncio.to_thread(
                sort_rows,
                self._logs_filter_cache_rows,
                self.logs_state["columns"],
                self.logs_state["sort_by"],
                self.logs_state["sort_desc"],
            )
        self._logs_sort_cache_signature = sort_signature
