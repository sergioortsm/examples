"""Tailer incremental de ficheros .log con apertura compartida (Windows-only).

Usa CreateFileW via ctypes con FILE_SHARE_READ|WRITE|DELETE para coexistir con
el proceso de SharePoint (OWSTIMER / w3wp) que mantiene el fichero abierto en
escritura y lo rota periodicamente. Solo lectura, optimizada para tail rapido:

- FILE_FLAG_SEQUENTIAL_SCAN  -> prefetch agresivo del cache manager de Windows.
- Lectura por bloques de 1 MB (bytes), no readline().
- Decode diferido al parsear cada linea.
- Conserva la ultima linea parcial entre lecturas (SharePoint puede volcar a mitad).

Solo se usa en local en el servidor SharePoint On-Premise (entorno de dev).
"""
from __future__ import annotations

import ctypes
import logging
import msvcrt
import os
from ctypes import wintypes
from pathlib import Path
from typing import BinaryIO

logger = logging.getLogger("trolli.log_tailer")

# Constantes de la API Win32 (https://learn.microsoft.com/windows/win32/api/fileapi/nf-fileapi-createfilew)
_GENERIC_READ = 0x80000000
_FILE_SHARE_READ = 0x00000001
_FILE_SHARE_WRITE = 0x00000002
_FILE_SHARE_DELETE = 0x00000004
_OPEN_EXISTING = 3
_FILE_FLAG_SEQUENTIAL_SCAN = 0x08000000
_INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

_DEFAULT_CHUNK = 1024 * 1024  # 1 MB

_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_kernel32.CreateFileW.argtypes = [
    wintypes.LPCWSTR,
    wintypes.DWORD,
    wintypes.DWORD,
    ctypes.c_void_p,
    wintypes.DWORD,
    wintypes.DWORD,
    wintypes.HANDLE,
]
_kernel32.CreateFileW.restype = wintypes.HANDLE


def open_shared_read(path: str) -> BinaryIO:
    """Abre un fichero en modo lectura permitiendo escritura/borrado concurrente.

    Devuelve un objeto BinaryIO buffered (1 MB) sobre el handle Win32.
    Lanza OSError si no se puede abrir.
    """
    handle = _kernel32.CreateFileW(
        path,
        _GENERIC_READ,
        _FILE_SHARE_READ | _FILE_SHARE_WRITE | _FILE_SHARE_DELETE,
        None,
        _OPEN_EXISTING,
        _FILE_FLAG_SEQUENTIAL_SCAN,
        None,
    )
    if handle is None or handle == _INVALID_HANDLE_VALUE:
        err = ctypes.get_last_error()
        raise OSError(err, f"CreateFileW fallo para {path} (WinError {err})")
    try:
        fd = msvcrt.open_osfhandle(int(handle), os.O_RDONLY)
    except OSError:
        ctypes.windll.kernel32.CloseHandle(handle)
        raise
    return os.fdopen(fd, "rb", buffering=_DEFAULT_CHUNK)


def detect_encoding(first_chunk: bytes) -> str:
    """Detecta encoding razonable a partir del primer bloque leido.

    Por orden: BOM UTF-8 (utf-8-sig), UTF-8 valido, fallback cp1252.
    """
    if first_chunk.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    try:
        first_chunk.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        return "cp1252"


class LogTailer:
    """Tailer ligado a un unico fichero.

    No hace polling de la carpeta (eso lo hace LogWatcher). Solo:
    - Mantiene el handle abierto.
    - Devuelve nuevas lineas completas leidas desde el ultimo offset.
    - Detecta truncado (size < last_offset) -> el caller decide reabrir.
    """

    def __init__(self, file_path: str, start_from_end: bool = True):
        self.file_path = file_path
        self._fp: BinaryIO | None = None
        self._encoding: str | None = None
        self._partial: bytes = b""
        self._offset: int = 0
        self._start_from_end = start_from_end

    def open(self) -> None:
        if self._fp is not None:
            return
        self._fp = open_shared_read(self.file_path)
        if self._start_from_end:
            self._fp.seek(0, os.SEEK_END)
            self._offset = self._fp.tell()
        else:
            self._offset = 0
        self._partial = b""
        logger.info("[TAILER] Abierto %s (offset inicial=%s)", self.file_path, self._offset)

    def close(self) -> None:
        if self._fp is not None:
            try:
                self._fp.close()
            except Exception:
                pass
            self._fp = None

    def current_size(self) -> int:
        try:
            return Path(self.file_path).stat().st_size
        except OSError:
            return -1

    def is_truncated(self) -> bool:
        size = self.current_size()
        return size >= 0 and size < self._offset

    def read_new_lines(self, max_bytes: int = _DEFAULT_CHUNK * 4) -> list[str]:
        """Lee bytes nuevos hasta EOF (o tope max_bytes) y devuelve lineas completas.

        Conserva la linea parcial final para concatenar en la siguiente llamada.
        """
        if self._fp is None:
            return []

        size = self.current_size()
        if size < 0:
            return []

        if size < self._offset:
            # Truncado / rotacion. El caller debe reabrir.
            return []

        if size == self._offset:
            return []

        to_read = min(size - self._offset, max_bytes)
        try:
            data = self._fp.read(to_read)
        except OSError as e:
            logger.warning("[TAILER] read fallo en %s: %s", self.file_path, e)
            return []

        if not data:
            return []

        self._offset += len(data)

        if self._encoding is None:
            self._encoding = detect_encoding(data)

        buffer = self._partial + data
        # split B-fast: bytes.split es C-puro, mas rapido que readline en bucle Python.
        parts = buffer.split(b"\n")
        self._partial = parts[-1]
        complete = parts[:-1]

        enc = self._encoding or "cp1252"
        lines: list[str] = []
        for raw in complete:
            if raw.endswith(b"\r"):
                raw = raw[:-1]
            if not raw:
                continue
            try:
                lines.append(raw.decode(enc))
            except UnicodeDecodeError:
                lines.append(raw.decode("latin-1", errors="replace"))
        return lines

    @property
    def offset(self) -> int:
        return self._offset
