"""Watcher en hilo dedicado: vigila una carpeta + regex y empuja lineas nuevas.

Comportamiento:
- Cada POLL_INTERVAL_MS escanea la carpeta y resuelve el fichero MAS RECIENTE
  cuyo nombre matchee el regex (mtime descendente).
- Mantiene abierto un LogTailer sobre ese fichero.
- Si cambia el fichero objetivo (rotacion) o el actual es truncado: termina de
  leer hasta EOF el anterior y abre uno nuevo arrancando desde el inicio (no
  desde EOF) para no perder el inicio del fichero recien creado.
- Lee la cabecera (primera linea no vacia) para inferir columnas. Si las
  columnas cambian respecto al fichero anterior, resetea el buffer.
- Cada lote leido se entrega via callback `on_batch(file_path, rows, levels)`.
  El callback corre en el hilo del watcher: debe ser ligero y thread-safe.

Solo Windows / SharePoint On-Premise local.
"""
from __future__ import annotations

import logging
import re
import threading
import time
from pathlib import Path

from log_service import build_row_from_line, parse_header_line
from log_tailer import LogTailer

logger = logging.getLogger("trolli.log_watcher")

POLL_INTERVAL_S = 0.5
HEADER_READ_MAX_BYTES = 64 * 1024


class LogWatcher:
    def __init__(
        self,
        folder: str,
        pattern: str,
        on_batch,  # callable(file_path, rows, levels, columns)
        on_status,  # callable(status_dict)
        on_file_changed,  # callable(file_path)
        start_from_end_for_current: bool = True,
        poll_interval_s: float = POLL_INTERVAL_S,
        max_bytes_per_tick: int = 4 * 1024 * 1024,
    ):
        self._folder = folder
        self._pattern_raw = pattern
        try:
            self._pattern = re.compile(pattern, re.IGNORECASE)
        except re.error as e:
            raise ValueError(f"Patron regex invalido: {e}")
        self._on_batch = on_batch
        self._on_status = on_status
        self._on_file_changed = on_file_changed
        self._start_from_end_for_current = start_from_end_for_current
        self._poll_interval_s = poll_interval_s
        self._max_bytes_per_tick = max_bytes_per_tick

        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

        self._tailer: LogTailer | None = None
        self._current_path: str | None = None
        self._columns: list[str] = []
        self._level_col_idx: int = -1

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.is_running():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name=f"LogWatcher({Path(self._folder).name})",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        self._close_tailer()
        self._thread = None

    # ---------- internos ----------

    def _close_tailer(self) -> None:
        if self._tailer is not None:
            self._tailer.close()
            self._tailer = None

    def _resolve_newest(self) -> str | None:
        try:
            folder = Path(self._folder)
            if not folder.is_dir():
                return None
            newest: tuple[float, Path] | None = None
            for entry in folder.iterdir():
                if not entry.is_file():
                    continue
                if not self._pattern.search(entry.name):
                    continue
                try:
                    mtime = entry.stat().st_mtime
                except OSError:
                    continue
                if newest is None or mtime > newest[0]:
                    newest = (mtime, entry)
            return str(newest[1]) if newest else None
        except OSError as e:
            logger.warning("[WATCHER] Error escaneando carpeta %s: %s", self._folder, e)
            return None

    def _read_header(self, path: str) -> list[str]:
        try:
            from log_tailer import open_shared_read

            with open_shared_read(path) as fp:
                chunk = fp.read(HEADER_READ_MAX_BYTES)
        except OSError as e:
            logger.warning("[WATCHER] No se pudo leer cabecera de %s: %s", path, e)
            return []
        # Decodificar best-effort
        for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
            try:
                text = chunk.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        else:
            text = chunk.decode("latin-1", errors="replace")
        for line in text.splitlines():
            stripped = line.strip()
            if stripped:
                return parse_header_line(stripped)
        return []

    def _switch_to(self, new_path: str, is_first_open: bool) -> bool:
        """Abre tailer sobre new_path. Devuelve True si OK."""
        self._close_tailer()
        columns = self._read_header(new_path)
        if not columns:
            self._on_status({"watch_error": f"Cabecera no detectada en {Path(new_path).name}"})
            return False
        # Cuando es el primer fichero al arrancar: respetar preferencia (EOF si start_from_end).
        # En rotaciones posteriores: arrancar desde el inicio del nuevo fichero para
        # no perderse las primeras lineas que justo escribe SP al crearlo.
        start_from_end = self._start_from_end_for_current if is_first_open else False
        tailer = LogTailer(new_path, start_from_end=start_from_end)
        try:
            tailer.open()
        except OSError as e:
            logger.warning("[WATCHER] No se pudo abrir %s: %s", new_path, e)
            self._on_status({"watch_error": f"No se pudo abrir: {e}"})
            return False

        # Si la cabecera ya fue contada en el offset (EOF), no la reprocesamos.
        # Si arrancamos desde 0, descartamos la primera linea no vacia (cabecera) en el
        # primer lote: el callback recibira lineas con columns coherentes.
        self._tailer = tailer
        previous_columns = self._columns
        self._columns = columns
        level_column = next((c for c in columns if c.lower() == "level"), None)
        self._level_col_idx = columns.index(level_column) if level_column else -1
        self._current_path = new_path
        self._on_file_changed(new_path)
        self._on_status({
            "watch_error": "",
            "watch_columns": list(columns),
            "watch_columns_changed": previous_columns != columns and bool(previous_columns),
            "watch_file_path": new_path,
        })
        return True

    def _process_tick(self, is_first_open_holder: list[bool]) -> None:
        # 1) Resolver el fichero mas reciente.
        newest = self._resolve_newest()
        if newest is None:
            self._on_status({"watch_error": "Sin ficheros que coincidan con el patron."})
            return

        # 2) Cambio de fichero (rotacion o primera vez).
        if self._tailer is None or newest != self._current_path:
            # Drenar el fichero anterior hasta EOF antes de cambiar.
            if self._tailer is not None:
                self._drain_current()
            ok = self._switch_to(newest, is_first_open=is_first_open_holder[0])
            is_first_open_holder[0] = False
            if not ok:
                return

        # 3) Detectar truncado del actual.
        assert self._tailer is not None
        if self._tailer.is_truncated():
            self._drain_current()
            ok = self._switch_to(self._current_path or newest, is_first_open=False)
            if not ok:
                return

        # 4) Leer nuevas lineas.
        self._drain_current()

    def _drain_current(self) -> None:
        if self._tailer is None or not self._columns:
            return
        # Bucle interno: leer en raciones de max_bytes hasta agotar lo disponible.
        # Limite duro de iteraciones para no monopolizar el hilo si SP vuelca muy rapido.
        for _ in range(8):
            lines = self._tailer.read_new_lines(self._max_bytes_per_tick)
            if not lines:
                return
            rows: list[dict[str, str]] = []
            levels: list[str] = []
            for line in lines:
                # Saltar la cabecera si se cuela en el primer lote tras abrir desde inicio.
                if line.startswith(self._columns[0]) and "\t" in line:
                    # Heuristica simple: si la primera celda coincide exacta con el nombre
                    # de la primera columna, es la cabecera. Saltar.
                    first_cell = line.split("\t", 1)[0].strip()
                    if first_cell == self._columns[0]:
                        continue
                row, level = build_row_from_line(line, self._columns, self._level_col_idx)
                rows.append(row)
                if level:
                    levels.append(level)
            if rows:
                self._on_batch(self._current_path or "", rows, levels, self._columns)

    def _run(self) -> None:
        logger.info(
            "[WATCHER] Arrancando en %s con patron %r (poll=%ss)",
            self._folder,
            self._pattern_raw,
            self._poll_interval_s,
        )
        is_first_open_holder = [True]
        try:
            while not self._stop_event.is_set():
                try:
                    self._process_tick(is_first_open_holder)
                except Exception as e:  # noqa: BLE001
                    logger.exception("[WATCHER] Error en tick: %s", e)
                    self._on_status({"watch_error": f"Error: {e}"})
                # Espera interruptible.
                if self._stop_event.wait(self._poll_interval_s):
                    break
        finally:
            self._close_tailer()
            logger.info("[WATCHER] Parado en %s", self._folder)
