"""LogsWatcherMixin — ciclo de vida del watcher de logs en tiempo real (live tailing).

Extraído de TrelloApp en main.py. Gestiona inicio/parada del LogWatcher,
el drain loop asíncrono, callbacks thread-safe, auto-pausa y estado Vivo.
"""
import asyncio
import logging
import os
from pathlib import Path

from log_buffer import LifoLogBuffer
from log_watcher import LogWatcher
from log_service import col_spec_name, make_col_spec

logger = logging.getLogger("trolli")


class LogsWatcherMixin:
    # ------------------------------------------------------------------
    # Normalización de ruta de carpeta
    # ------------------------------------------------------------------

    def _normalize_watch_folder(self, value: str) -> str:
        folder = (value or "").strip().strip('"').strip("'")
        if not folder:
            return ""
        expanded = os.path.expandvars(os.path.expanduser(folder))
        return str(Path(expanded))

    # ------------------------------------------------------------------
    # Cambios de configuración del watcher
    # ------------------------------------------------------------------

    def on_logs_watch_folder_change(self, value: str):
        self.logs_state["watch_folder"] = self._normalize_watch_folder(value)
        self.logs_state["watch_error"] = ""
        self._close_banner()
        try:
            self.logs_view.render(self.logs_state)
        except RuntimeError:
            pass
        self._persist_logs_preferences_if_needed()

    def on_logs_watch_pattern_change(self, value: str):
        self.logs_state["watch_pattern"] = (value or "").strip()
        self.logs_state["watch_error"] = ""
        self._close_banner()
        try:
            self.logs_view.render(self.logs_state)
        except RuntimeError:
            pass
        self._persist_logs_preferences_if_needed()

    # ------------------------------------------------------------------
    # Helpers de estado
    # ------------------------------------------------------------------

    def _is_view_following_live(self) -> bool:
        """True si la vista esta en modo 'seguir el flujo': pagina 1 y sin pausa manual.

        Los filtros de Level o busqueda de texto NO interrumpen el seguimiento:
        los registros se muestran en cada drain ya filtrados.
        El boton 'Nuevas (n)' solo aparece cuando hay pausa manual explícita
        o el usuario está navegando una pagina distinta a la primera.
        """
        # Pausa manual explícita: el usuario pidió congelar la vista.
        if bool(self.logs_state.get("live_paused", False)):
            return False
        if int(self.logs_state.get("current_page", 1)) != 1:
            return False
        return True

    # ------------------------------------------------------------------
    # Callbacks thread-safe (invocados desde el hilo del watcher)
    # ------------------------------------------------------------------

    def _watcher_on_batch_threadsafe(self, file_path: str, rows: list, levels: list, columns: list):
        """Callback invocado desde el hilo del watcher. Acumula y NO toca la UI."""
        try:
            self._log_buffer.set_columns(columns)
            self._log_buffer.extend(rows, levels)
            with self._watcher_pending_lock:
                self._watcher_pending_batches.append((rows, levels, columns))
        except Exception:
            logger.exception("[WATCHER] Error en callback batch")

    def _watcher_on_status_threadsafe(self, status: dict):
        with self._watcher_pending_lock:
            self._watcher_pending_batches.append(("__status__", status))  # type: ignore[arg-type]
        # Si el status incluye las columnas del header (watch_columns), las primamos
        # en el buffer ahora mismo (thread-safe) para que snapshot() las devuelva
        # incluso antes del primer lote de filas. Esto re-habilita el botón de
        # columnas en cuanto el watcher detecta la cabecera del fichero.
        if isinstance(status, dict):
            cols = status.get("watch_columns")
            if isinstance(cols, list) and cols:
                self._log_buffer.set_columns(cols)

    def _watcher_on_file_changed_threadsafe(self, file_path: str):
        with self._watcher_pending_lock:
            self._watcher_pending_batches.append(("__file_changed__", file_path))  # type: ignore[arg-type]

    # ------------------------------------------------------------------
    # Drain loop (corre en el event loop de Flet)
    # ------------------------------------------------------------------

    async def _watcher_drain_loop(self):
        """Drena los lotes acumulados por el watcher y refresca la UI con coalescing."""
        REFRESH_MS = 250
        MAX_SLEEP_S = 3.0  # tope para no congelar actualizaciones tras un pico anomalo
        try:
            while self._watcher is not None and self._watcher.is_running():
                # Throttle adaptativo: si el ultimo render tardo X ms, espera al menos X*1.2.
                # Asi rompemos la bola de nieve cuando el render satura bajo super stress,
                # manteniendo cadencia normal cuando los renders son rapidos.
                base_s = REFRESH_MS / 1000.0
                adaptive_s = (self._last_render_ms / 1000.0) * 1.2
                sleep_s = min(MAX_SLEEP_S, max(base_s, adaptive_s))
                await asyncio.sleep(sleep_s)
                with self._watcher_pending_lock:
                    pending = self._watcher_pending_batches
                    self._watcher_pending_batches = []

                if not pending:
                    self._update_lines_per_sec(0)
                    continue

                total_new_rows = 0
                columns_seen: list[str] = []
                file_changed: str | None = None
                for item in pending:
                    if isinstance(item, tuple) and len(item) == 2 and item[0] == "__status__":
                        status = item[1] or {}
                        if isinstance(status, dict):
                            for k, v in status.items():
                                if k == "watch_error":
                                    self.logs_state["watch_error"] = v
                        continue
                    if isinstance(item, tuple) and len(item) == 2 and item[0] == "__file_changed__":
                        file_changed = str(item[1])
                        continue
                    if isinstance(item, tuple) and len(item) == 3:
                        rows, _levels, columns = item
                        _active_levels = set(self.logs_state.get("level_filters") or [])
                        if _active_levels and columns:
                            _lvl_col = next((c for c in columns if c.lower() == "level"), None)
                            if _lvl_col:
                                total_new_rows += sum(
                                    1 for r in rows if r.get(_lvl_col, "") in _active_levels
                                )
                            else:
                                total_new_rows += len(rows)
                        else:
                            total_new_rows += len(rows)
                        if columns and not columns_seen:
                            columns_seen = list(columns)

                if file_changed:
                    self.logs_state["file_path"] = file_changed
                    self.logs_state["file_label"] = f"En vivo: {Path(file_changed).name}"

                snap_rows, snap_columns, snap_levels, snap_col_values, buf_size, _total = self._log_buffer.snapshot()
                columns_changed = False
                if snap_columns and self.logs_state.get("columns") != snap_columns:
                    columns_changed = True
                    self.logs_state["columns"] = snap_columns
                    snap_col_set = set(snap_columns)
                    visible = [s for s in self.logs_state.get("visible_columns", []) if col_spec_name(s) in snap_col_set]
                    if not visible:
                        visible = [make_col_spec(c) for c in snap_columns]
                    self.logs_state["visible_columns"] = visible
                    self.logs_state["visible_columns_pending"] = [dict(s) for s in visible]
                self.logs_state["col_values"] = snap_col_values
                self.logs_state["level_options"] = ["All"] + snap_col_values.get("Level", snap_levels)
                self.logs_state["buffer_count"] = buf_size
                self.logs_state["buffer_max"] = self._log_buffer.maxlen
                self._update_lines_per_sec(total_new_rows)

                following = self._is_view_following_live()
                if following and total_new_rows > 0:
                    self.logs_rows = snap_rows
                    self._invalidate_logs_query_cache()
                    self.logs_state["pending_new_count"] = 0
                    current_page_size = int(self.logs_state["page_size"])
                    live_cap = min(current_page_size, self.LIVE_MODE_MAX_ROWS)
                    if live_cap < current_page_size and self._live_cap_logged_for_size != current_page_size:
                        logger.info(
                            "[WATCHER] live cap applied (page_size=%d -> %d)",
                            current_page_size,
                            live_cap,
                        )
                        self._live_cap_logged_for_size = current_page_size
                    # filter+sort sobre snap_rows (hasta 100k) puede ser pesado en super stress:
                    # lo movemos a un thread para no bloquear el event loop de Flet en cada drain.
                    # Después _refresh_logs_view_core paginará desde el caché ya precomputado.
                    await self._rebuild_logs_query_cache_in_thread_if_needed()
                    self._refresh_logs_view_core(should_render=True, page_size_override=live_cap)
                else:
                    self.logs_state["pending_new_count"] = int(self.logs_state.get("pending_new_count", 0)) + total_new_rows
                    # Auto-pausa: refresco minimo (chip + status). Evita re-render
                    # de tabla/columnas en cada drain (cada 250ms) bajo super stress,
                    # lo cual saturaba el WebSocket y bloqueaba clicks de la UI.
                    # Excepción: si las columnas cambiaron (primera recepción de datos),
                    # refrescar selector y fila de filtros para habilitar el botón.
                    if columns_changed:
                        try:
                            self.logs_view.refresh_column_selector(self.logs_state)
                            self.logs_view.refresh_column_filters(self.logs_state)
                        except RuntimeError:
                            pass
                        self._page.update()
                    else:
                        try:
                            self.logs_view.refresh_pending_chip_and_status(self.logs_state)
                        except RuntimeError:
                            pass
        except asyncio.CancelledError:
            return
        except Exception:
            logger.exception("[WATCHER] Drain loop error")

    def _update_lines_per_sec(self, new_count: int):
        import time as _time
        now = _time.monotonic()
        if new_count > 0:
            self._watcher_lines_window.append((now, new_count))
        cutoff = now - 5.0
        self._watcher_lines_window = [(t, c) for t, c in self._watcher_lines_window if t >= cutoff]
        total = sum(c for _, c in self._watcher_lines_window)
        self.logs_state["lines_per_sec"] = total / 5.0

    # ------------------------------------------------------------------
    # Pausa/reanudación manual del modo Vivo
    # ------------------------------------------------------------------

    def on_logs_toggle_live_pause(self):
        """Alternar pausa/reanudación manual del empuje Vivo a la vista."""
        currently_paused = bool(self.logs_state.get("live_paused", False))
        if currently_paused:
            # Reanudar: descongelar y mostrar inmediatamente lo acumulado.
            self.logs_state["live_paused"] = False
            self.on_logs_show_pending_new()
        else:
            # Pausar: congelar la vista; el watcher sigue acumulando en buffer.
            self.logs_state["live_paused"] = True
            try:
                self.logs_view.render(self.logs_state)
            except RuntimeError:
                pass
            self._page.update()

    def on_logs_show_pending_new(self):
        """Forzar consumo del buffer y reset de filtros que estan ocultando lo nuevo.

        En 'super stress' el snapshot del buffer (hasta 100k filas) y el
        filter+sort sobre ese snapshot pueden bloquear el event loop varios
        cientos de ms. Hacemos:
          1. Feedback inmediato: reset visual del chip + overlay de carga.
          2. snapshot() y filter+sort en thread (fuera del event loop).
          3. Render final cuando todo esta listo.
        """
        if bool(self.logs_state.get("_pending_new_in_progress", False)):
            return  # debounce: ignora clicks repetidos durante el proceso

        self.logs_state["_pending_new_in_progress"] = True
        # Reset visual inmediato del chip y pagina antes de salir del handler.
        self.logs_state["pending_new_count"] = 0
        self.logs_state["current_page"] = 1
        self.logs_view.request_scroll_to_top()
        self.begin_global_loading("Recuperando nuevas...")
        try:
            self.logs_view.refresh_pending_chip_and_status(self.logs_state)
        except RuntimeError:
            pass
        self._page.update()

        try:
            asyncio.get_running_loop().create_task(self._show_pending_new_deferred())
        except RuntimeError:
            # Fallback sin loop async: ejecucion sincrona (entornos de test).
            try:
                self._show_pending_new_sync()
            finally:
                self.end_global_loading()
                self.logs_state["_pending_new_in_progress"] = False
                try:
                    self.logs_view.render(self.logs_state)
                except RuntimeError:
                    pass
                self._page.update()

    def _show_pending_new_sync(self):
        snap_rows, snap_columns, snap_levels, snap_col_values, buf_size, _ = self._log_buffer.snapshot()
        self._apply_pending_new_snapshot(snap_rows, snap_columns, snap_levels, snap_col_values, buf_size)
        self._refresh_logs_view_core(should_render=False)

    def _apply_pending_new_snapshot(
        self,
        snap_rows: list,
        snap_columns: list,
        snap_levels: list,
        snap_col_values: dict,
        buf_size: int,
    ):
        if snap_columns:
            self.logs_state["columns"] = snap_columns
            snap_col_set = set(snap_columns)
            visible = [s for s in self.logs_state.get("visible_columns", []) if col_spec_name(s) in snap_col_set]
            if not visible:
                visible = [make_col_spec(c) for c in snap_columns]
            self.logs_state["visible_columns"] = visible
            self.logs_state["visible_columns_pending"] = [dict(s) for s in visible]
        self.logs_state["col_values"] = snap_col_values
        self.logs_state["level_options"] = ["All"] + snap_col_values.get("Level", snap_levels)
        self.logs_state["buffer_count"] = buf_size
        self.logs_rows = snap_rows
        self._invalidate_logs_query_cache()

    async def _show_pending_new_deferred(self, min_loading_seconds: float = 0.15):
        loop = asyncio.get_running_loop()
        started = loop.time()
        await asyncio.sleep(0)  # deja pintar overlay/chip
        try:
            # snapshot() copia hasta 100k filas bajo lock: fuera del event loop.
            snap = await asyncio.to_thread(self._log_buffer.snapshot)
            snap_rows, snap_columns, snap_levels, snap_col_values, buf_size, _ = snap
            self._apply_pending_new_snapshot(snap_rows, snap_columns, snap_levels, snap_col_values, buf_size)
            # filter+sort sobre snap_rows en thread (helper existente).
            await self._rebuild_logs_query_cache_in_thread_if_needed()
            self._refresh_logs_view_core(should_render=False)
        except Exception:
            logger.exception("[WATCHER] Error al recuperar nuevas pendientes")
        finally:
            remaining = min_loading_seconds - (loop.time() - started)
            if remaining > 0:
                await asyncio.sleep(remaining)
            self.end_global_loading()
            self.logs_state["_pending_new_in_progress"] = False
            try:
                self.logs_view.render(self.logs_state)
            except RuntimeError:
                pass
            self._page.update()

    # ------------------------------------------------------------------
    # Inicio y parada del watcher
    # ------------------------------------------------------------------

    def on_logs_toggle_watch(self):
        if self.logs_state.get("is_watching", False):
            self._stop_watcher()
        else:
            self._start_watcher()

    def _start_watcher(self):
        folder = self._normalize_watch_folder(str(self.logs_state.get("watch_folder") or ""))
        self.logs_state["watch_folder"] = folder
        pattern = (self.logs_state.get("watch_pattern") or r".+\.log$").strip()
        if not folder:
            self.show_error("Indica una carpeta para vigilar.")
            self._page.update()
            return
        if not Path(folder).is_dir():
            self.logs_state["watch_error"] = ""
            self.show_error("La carpeta a vigilar no existe o no es accesible.")
            try:
                self.logs_view.render(self.logs_state)
            except RuntimeError:
                pass
            self._page.update()
            return

        # Resetea estado de carga manual previa.
        self._log_buffer = LifoLogBuffer(maxlen=self.logs_state.get("buffer_max", 100_000))
        self.logs_rows = []
        self._invalidate_logs_query_cache()
        self.logs_state.update({
            "is_watching": True,
            "watch_error": "",
            "columns": [],
            "col_values": {},
            "level_options": ["All"],
            "pending_new_count": 0,
            "buffer_count": 0,
            "lines_per_sec": 0.0,
            "live_paused": False,
            "current_page": 1,
            "file_label": "Esperando primer fichero...",
        })
        self._persist_logs_preferences_if_needed()

        try:
            self._watcher = LogWatcher(
                folder=folder,
                pattern=pattern,
                on_batch=self._watcher_on_batch_threadsafe,
                on_status=self._watcher_on_status_threadsafe,
                on_file_changed=self._watcher_on_file_changed_threadsafe,
                start_from_end_for_current=True,
            )
        except ValueError as e:
            self.logs_state["is_watching"] = False
            self.logs_state["watch_error"] = ""
            self.show_error(f"No se pudo iniciar el vigilante: {e}")
            try:
                self.logs_view.render(self.logs_state)
            except RuntimeError:
                pass
            self._page.update()
            return

        self._watcher.start()
        self._close_banner()  # éxito: cierra banner de error previo si lo había
        try:
            self._watcher_drain_task = asyncio.get_running_loop().create_task(self._watcher_drain_loop())
        except RuntimeError:
            self._watcher_drain_task = None

        try:
            self.logs_view.render(self.logs_state)
        except RuntimeError:
            pass
        self._page.update()

    def _stop_watcher(self):
        if self._watcher is not None:
            try:
                self._watcher.stop()
            except Exception:
                logger.exception("[WATCHER] Error al detener")
                self.show_error("Error al detener el vigilante (ver logs).")
            self._watcher = None
        if self._watcher_drain_task is not None:
            self._watcher_drain_task.cancel()
            self._watcher_drain_task = None
        self.logs_state["is_watching"] = False
        self.logs_state["lines_per_sec"] = 0.0
        try:
            self.logs_view.render(self.logs_state)
        except RuntimeError:
            pass
        self._page.update()
