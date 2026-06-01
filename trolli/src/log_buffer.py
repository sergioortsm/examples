"""Buffer LIFO acotado y thread-safe para filas de log en streaming.

Diseño:
- collections.deque(maxlen=N) -> descarte O(1) por el extremo cuando se llena.
- appendleft -> semantica LIFO (mas reciente al inicio, indice 0).
- Lock para coexistencia entre el hilo del watcher y el event loop de Flet.
- snapshot() devuelve una lista nueva (copia superficial de referencias) que el
  resto de la app puede usar de forma segura sin retener el lock.
"""
from __future__ import annotations

import threading
from collections import deque
from typing import Iterable


class LifoLogBuffer:
    def __init__(self, maxlen: int = 100_000):
        self._rows: deque[dict[str, str]] = deque(maxlen=maxlen)
        self._lock = threading.Lock()
        self._columns: list[str] = []
        self._levels: set[str] = set()
        self._col_values: dict[str, set[str]] = {}
        self._total_ingested: int = 0
        self._maxlen = maxlen

    @property
    def maxlen(self) -> int:
        return self._maxlen

    def reset(self, columns: list[str]) -> None:
        with self._lock:
            self._rows.clear()
            self._levels.clear()
            self._columns = list(columns)
            self._col_values = {column: set() for column in columns}
            self._total_ingested = 0

    def set_columns(self, columns: list[str]) -> None:
        with self._lock:
            self._columns = list(columns)
            for column in columns:
                self._col_values.setdefault(column, set())
            stale_columns = [column for column in self._col_values if column not in columns]
            for column in stale_columns:
                del self._col_values[column]

    def extend(
        self,
        new_rows: Iterable[dict[str, str]],
        new_levels: Iterable[str] = (),
    ) -> int:
        """Inserta filas al frente (LIFO). Devuelve cuantas filas se han añadido."""
        count = 0
        with self._lock:
            for row in new_rows:
                self._rows.appendleft(row)
                for column in self._columns:
                    value = row.get(column, "").strip()
                    if value:
                        self._col_values.setdefault(column, set()).add(value)
                count += 1
            for lvl in new_levels:
                if lvl:
                    self._levels.add(lvl)
            self._total_ingested += count
        return count

    def snapshot(self) -> tuple[list[dict[str, str]], list[str], list[str], dict[str, list[str]], int, int]:
        """Devuelve (rows, columns, levels_sorted, col_values, current_size, total_ingested).

        rows es una nueva lista (LIFO order) cuyas filas son referencias a dicts
        compartidos: el caller no debe mutarlas en sitio.
        """
        with self._lock:
            return (
                list(self._rows),
                list(self._columns),
                sorted(self._levels),
                {column: sorted(values) for column, values in self._col_values.items()},
                len(self._rows),
                self._total_ingested,
            )

    def size(self) -> int:
        with self._lock:
            return len(self._rows)
