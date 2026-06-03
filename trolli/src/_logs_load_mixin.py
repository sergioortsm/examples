"""LogsLoadMixin — carga de archivo de log y refresco de vista paginada.

Extraído de TrelloApp en main.py. Accede a self.logs_rows, self.logs_state,
self.logs_view, self._page, self.file_picker, y los métodos de cache/prefs
disponibles vía herencia múltiple.
"""
import asyncio
import json
import logging
import threading
from pathlib import Path

import flet as ft

from app_logging import perf_timer
from dialog import build_dir_load_progress_dialog
from log_service import load_sharepoint_log, paginate_rows, col_spec_name, col_names, make_col_spec

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

    def open_log_directory_dialog(self, e=None):
        """Abre el selector de carpeta y carga todos los .log modificados en la última hora."""
        logger.info("[LOGS] open_log_directory_dialog llamado")

        async def _pick_and_handle_dir():
            result = await self.file_picker.get_directory_path(
                dialog_title="Selecciona carpeta con logs de la última hora",
            )
            if result:
                self.load_log_directory(result)

        try:
            asyncio.get_running_loop().create_task(_pick_and_handle_dir())
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
        col_set = set(result.columns)
        # Preservar qué columnas están visibles (y su spec) pero respetando el orden del fichero.
        col_to_spec = {col_spec_name(s): s for s in visible_columns if col_spec_name(s) in col_set}
        valid_visible = [col_to_spec[c] for c in result.columns if c in col_to_spec]
        if not valid_visible:
            valid_visible = [make_col_spec(c) for c in result.columns]

        pending_columns = self.logs_state.get("visible_columns_pending", [])
        col_to_pending = {col_spec_name(s): s for s in pending_columns if col_spec_name(s) in col_set}
        valid_pending = [col_to_pending[c] for c in result.columns if c in col_to_pending]
        if not valid_pending:
            valid_pending = [dict(s) for s in valid_visible]

        sort_by = self.logs_state.get("sort_by")
        if sort_by not in result.columns:
            sort_by = result.columns[0] if result.columns else None

        level_filters = list(self.logs_state.get("level_filters") or [])
        level_options = ["All"] + result.col_values.get("Level", result.levels)
        available_levels = set(result.col_values.get("Level", result.levels))
        # Descartar niveles seleccionados que ya no existan en el nuevo archivo
        level_filters = [lf for lf in level_filters if lf in available_levels]

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
                "level_filters": level_filters,
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
    # Carga por directorio (última hora)
    # ------------------------------------------------------------------

    def _load_candidate_patterns(self):
        """Carga los patrones de candidates.json desde la raíz del proyecto."""
        try:
            cands_path = Path(__file__).parent.parent / "candidates.json"
            if not cands_path.exists():
                cands_path = Path(__file__).parent / "candidates.json"
            data = json.loads(cands_path.read_text(encoding="utf-8"))
            self._candidate_patterns = [
                c["pattern"].lower()
                for c in data
                if isinstance(c.get("pattern"), str) and c["pattern"]
            ]
            logger.info("[LOGS] _load_candidate_patterns: %d patrones cargados", len(self._candidate_patterns))
        except Exception as exc:
            logger.warning("[LOGS] _load_candidate_patterns: error cargando candidates.json: %s", exc)
            self._candidate_patterns = []

    def _make_dir_load_progress_cb(self, progress_bar, filename_text, stats_text):
        """Devuelve un callback de progreso que actualiza el diálogo desde el hilo del executor."""
        def cb(i: int, total: int, fname: str, rows_so_far: int):
            progress_bar.value = i / total if total > 0 else 0
            filename_text.value = fname
            stats_text.value = f"{i} / {total} archivos  ·  {rows_so_far:,} filas"
            try:
                self._page.update()
            except Exception:
                pass
        return cb

    def _close_dir_load_progress_dialog(self):
        dlg = getattr(self, "_dir_load_dialog", None)
        if dlg is None:
            return
        self._dir_load_dialog = None
        try:
            self._close_control(dlg)
            _p = self._page
            if hasattr(_p, "overlay") and dlg in _p.overlay:
                _p.overlay.remove(dlg)
        except Exception:
            pass

    def _on_dir_load_cancel(self, e=None):
        ev = getattr(self, "_dir_load_cancel_event", None)
        if ev is not None:
            ev.set()
        self._close_dir_load_progress_dialog()
        try:
            self._page.update()
        except Exception:
            pass

    def _load_log_directory_sync(self, dir_path: str, progress_cb=None, cancel_event=None):
        self._invalidate_logs_query_cache()
        dir_p = Path(dir_path)

        try:
            log_files = sorted(
                list(dir_p.glob("*.log")),
                key=lambda f: f.stat().st_mtime,
            )
        except Exception as exc:
            self.show_error(f"Error accediendo al directorio: {exc}")
            return

        if not log_files:
            self.show_error("No se encontraron archivos .log en el directorio.")
            return

        all_rows: list[dict[str, str]] = []
        first_result = None
        col_values_combined: dict[str, set] = {}
        loaded = 0
        total = len(log_files)

        for i, log_file in enumerate(log_files):
            if cancel_event is not None and cancel_event.is_set():
                logger.info("[LOGS] directorio: carga cancelada por el usuario")
                return
            if progress_cb is not None:
                progress_cb(i + 1, total, log_file.name, len(all_rows))
            result = load_sharepoint_log(str(log_file))
            if result.error:
                logger.warning("[LOGS] directorio: error en %s: %s", log_file.name, result.error)
                continue
            if first_result is None:
                first_result = result
                for col in result.columns:
                    col_values_combined[col] = set(result.col_values.get(col, []))
            else:
                for col in result.columns:
                    col_values_combined.setdefault(col, set()).update(result.col_values.get(col, []))
            all_rows.extend(result.rows)
            loaded += 1

        if cancel_event is not None and cancel_event.is_set():
            return

        if progress_cb is not None:
            progress_cb(total, total, "\u2713 Listo", len(all_rows))

        if not all_rows or first_result is None:
            self.show_error("No se pudo cargar ningún log del directorio.")
            return

        columns = first_result.columns
        col_values = {col: sorted(vals) for col, vals in col_values_combined.items()}

        if "Timestamp" in columns:
            all_rows.sort(key=lambda r: r.get("Timestamp", ""))

        self.logs_rows = all_rows

        visible_columns = self.logs_state.get("visible_columns", [])
        col_set = set(columns)
        col_to_spec = {col_spec_name(s): s for s in visible_columns if col_spec_name(s) in col_set}
        valid_visible = [col_to_spec[c] for c in columns if c in col_to_spec]
        if not valid_visible:
            valid_visible = [make_col_spec(c) for c in columns]

        pending_columns = self.logs_state.get("visible_columns_pending", [])
        col_to_pending = {col_spec_name(s): s for s in pending_columns if col_spec_name(s) in col_set}
        valid_pending = [col_to_pending[c] for c in columns if c in col_to_pending]
        if not valid_pending:
            valid_pending = [dict(s) for s in valid_visible]

        sort_by = self.logs_state.get("sort_by")
        if sort_by not in columns:
            sort_by = columns[0] if columns else None

        level_filters = list(self.logs_state.get("level_filters") or [])
        level_options = ["All"] + col_values.get("Level", [])
        available_levels = set(col_values.get("Level", []))
        level_filters = [lf for lf in level_filters if lf in available_levels]

        self.logs_state.update({
            "file_path": dir_path,
            "file_label": f"Directorio: {dir_p.name} ({loaded} arch., {len(all_rows):,} líneas)",
            "columns": columns,
            "visible_columns": valid_visible,
            "visible_columns_pending": valid_pending,
            "column_selector_expanded": False,
            "col_values": col_values,
            "level_options": level_options,
            "sort_by": sort_by,
            "level_filters": level_filters,
            "current_page": 1,
            "error": "",
        })

    async def _load_log_directory_deferred(
        self, dir_path: str, cancel_event: threading.Event, progress_bar, filename_text, stats_text
    ):
        await asyncio.sleep(0)  # cede el ciclo para que el dialogo se pinte
        progress_cb = self._make_dir_load_progress_cb(progress_bar, filename_text, stats_text)
        try:
            await asyncio.get_running_loop().run_in_executor(
                None, self._load_log_directory_sync, dir_path, progress_cb, cancel_event
            )
        finally:
            self._close_dir_load_progress_dialog()
            cancelled = cancel_event.is_set()
            if not cancelled and self.logs_state.get("columns"):
                if self._page.route != "/logs":
                    self._page.navigate("/logs")
                else:
                    self.refresh_logs_view(show_loading=False)
                    self.show_success(self.logs_state.get("file_label", "Directorio cargado"))
            self._page.update()

    def load_log_directory(self, dir_path: str):
        logger.info("[LOGS] load_log_directory: %r", dir_path)
        cancel_event = threading.Event()
        self._dir_load_cancel_event = cancel_event

        progress_bar, filename_text, stats_text, dialog = build_dir_load_progress_dialog(
            on_cancel=lambda e: self._on_dir_load_cancel(),
        )
        self._dir_load_dialog = dialog
        self._open_control(dialog)
        self._page.update()

        try:
            asyncio.get_running_loop().create_task(
                self._load_log_directory_deferred(dir_path, cancel_event, progress_bar, filename_text, stats_text)
            )
        except RuntimeError:
            # Fallback sin loop async
            self._load_log_directory_sync(dir_path)
            self._close_dir_load_progress_dialog()
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
                    "page_global_indices": [],
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

        # Filtro por regla activa: si esta seteado, restringimos las filas que se paginan
        # a las que coincidan con esa regla (o cualquier regla si "__ANY__"). Mantenemos
        # un mapping slot -> indice global en sort cache para que el render pinte los bordes.
        active_rid = self.logs_state.get("active_rule_id")
        rule_matches = self.logs_state.get("rule_matches") or {}
        source_rows = self._logs_sort_cache_rows
        global_indices: list[int] | None = None
        if active_rid and rule_matches:
            with perf_timer("rule_filter", total=len(source_rows), rule=active_rid):
                if active_rid == "__ANY__":
                    matched_idx = sorted(rule_matches.keys())
                else:
                    matched_idx = sorted(
                        i for i, rules in rule_matches.items()
                        if any(r.id == active_rid for r in rules)
                    )
                source_rows = [self._logs_sort_cache_rows[i] for i in matched_idx]
                global_indices = matched_idx

        with perf_timer("paginate_rows", total=len(source_rows), page_size=effective_page_size):
            page_rows, filtered_total, total_pages, safe_page = paginate_rows(
                source_rows,
                self.logs_state["current_page"],
                effective_page_size,
            )

        # Calcular indices globales por slot para que el render mapee bordes correctamente.
        if global_indices is not None:
            start = (safe_page - 1) * effective_page_size
            page_global_indices = global_indices[start:start + effective_page_size]
        else:
            start = (safe_page - 1) * effective_page_size
            page_global_indices = list(range(start, start + len(page_rows)))

        self.logs_state.update(
            {
                "page_rows": page_rows,
                "filtered_total": filtered_total,
                "total_pages": total_pages,
                "current_page": safe_page,
                "page_global_indices": page_global_indices,
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
