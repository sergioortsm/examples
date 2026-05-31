from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import csv
import io
import re

MAX_LOG_SIZE_BYTES = 50 * 1024 * 1024
_ULS_TIMESTAMP_RE = re.compile(r"^\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2}\.\d{2,3}$")
_VALID_ULS_LEVELS = {
    "CRITICAL",
    "ERROR",
    "WARNING",
    "HIGH",
    "MEDIUM",
    "MONITORABLE",
    "INFORMATION",
    "VERBOSE",
    "VERBOSEEX",
    "UNEXPECTED",
}


@dataclass
class LogLoadResult:
    file_path: str
    columns: list[str]
    rows: list[dict[str, str]]
    levels: list[str]
    error: str | None = None


def _read_text_with_fallbacks(file_path: str) -> str:
    raw = Path(file_path).read_bytes()
    # Si hay BOM UTF-8, el fichero declara su encoding. En ese caso no debemos
    # degradar todo el contenido a cp1252 por un byte invalido aislado: es mejor
    # mantener UTF-8 y reemplazar solo la secuencia rota.
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw.decode("utf-8-sig", errors="replace")
    for encoding in ("utf-8", "cp1252", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1", errors="replace")


def _split_row(line: str, expected_columns: int) -> list[str]:
    parts = [part.strip() for part in line.split("\t")]
    if len(parts) < expected_columns:
        parts.extend([""] * (expected_columns - len(parts)))
    elif len(parts) > expected_columns and expected_columns > 0:
        overflow = parts[expected_columns - 1 :]
        parts = parts[: expected_columns - 1] + [" ".join(overflow)]
    return parts


def _is_valid_uls_row(
    line: str,
    row_values: list[str],
    expected_columns: int,
    level_col_idx: int,
) -> bool:
    if expected_columns <= 0:
        return False

    # Si faltan tabs estructurales, la línea ya llegó truncada/intercalada.
    if line.count("\t") < expected_columns - 1:
        return False

    timestamp = row_values[0].strip() if row_values else ""
    if not _ULS_TIMESTAMP_RE.match(timestamp):
        return False

    if 0 <= level_col_idx < len(row_values):
        level = row_values[level_col_idx].strip().upper()
        if level and level not in _VALID_ULS_LEVELS:
            return False

    return True


def build_row_from_line(
    line: str,
    columns: list[str],
    level_col_idx: int = -1,
) -> tuple[dict[str, str] | None, str]:
    """Parsea una linea ULS y devuelve (row_dict_con_search_key, nivel_o_vacio).

    Reutilizable por el tailer en modo streaming. No hace I/O. Eficiente:
    - Una sola pasada de split.
    - Un solo lowercase para _search_key.
    """
    n_cols = len(columns)
    row_values = _split_row(line, n_cols)
    if not _is_valid_uls_row(line, row_values, n_cols, level_col_idx):
        return None, ""
    search_key = "\t".join(row_values).lower()
    row = dict(zip(columns, row_values))
    row["_search_key"] = search_key
    level = ""
    if 0 <= level_col_idx < len(row_values):
        level = row_values[level_col_idx].strip()
    return row, level


def parse_header_line(header_line: str) -> list[str]:
    """Extrae columnas de la primera linea no vacia de un ULS."""
    if "\t" not in header_line:
        return []
    return [c.strip() for c in header_line.split("\t") if c.strip()]


def load_sharepoint_log(file_path: str) -> LogLoadResult:
    path = Path(file_path)
    if not path.exists() or not path.is_file():
        return LogLoadResult(file_path=file_path, columns=[], rows=[], levels=[], error="El archivo no existe.")

    if path.suffix.lower() != ".log":
        return LogLoadResult(
            file_path=file_path,
            columns=[],
            rows=[],
            levels=[],
            error="Solo se admite formato .log de SharePoint ULS en esta version.",
        )

    if path.stat().st_size > MAX_LOG_SIZE_BYTES:
        return LogLoadResult(
            file_path=file_path,
            columns=[],
            rows=[],
            levels=[],
            error="El archivo supera el limite de 50 MB.",
        )

    text = _read_text_with_fallbacks(file_path)

    # Iterar con io.StringIO evita materializar una segunda lista gigante con splitlines().
    line_iter = iter(io.StringIO(text))

    header_line: str | None = None
    for raw_line in line_iter:
        stripped = raw_line.strip()
        if stripped:
            header_line = stripped
            break

    if not header_line:
        return LogLoadResult(file_path=file_path, columns=[], rows=[], levels=[], error="El archivo esta vacio.")

    if "\t" not in header_line:
        return LogLoadResult(
            file_path=file_path,
            columns=[],
            rows=[],
            levels=[],
            error="No se detecto cabecera ULS tabulada.",
        )

    columns = [column.strip() for column in header_line.split("\t") if column.strip()]
    if not columns:
        return LogLoadResult(
            file_path=file_path,
            columns=[],
            rows=[],
            levels=[],
            error="La cabecera no contiene columnas validas.",
        )

    rows: list[dict[str, str]] = []
    level_values: set[str] = set()
    level_column = next((c for c in columns if c.lower() == "level"), None)
    level_col_idx: int = columns.index(level_column) if level_column else -1

    for raw_line in line_iter:
        line = raw_line.rstrip("\r\n")
        if not line.strip():
            continue
        row, level = build_row_from_line(line, columns, level_col_idx)
        if row is None:
            continue
        rows.append(row)
        if level:
            level_values.add(level)

    return LogLoadResult(
        file_path=file_path,
        columns=columns,
        rows=rows,
        levels=sorted(level_values),
        error=None,
    )


def apply_filters_sort_paginate(
    rows: list[dict[str, str]],
    columns: list[str],
    search_text: str,
    level_filter: str,
    sort_by: str | None,
    sort_desc: bool,
    page: int,
    page_size: int,
) -> tuple[list[dict[str, str]], int, int, int]:
    filtered = filter_sort_rows(
        rows,
        columns,
        search_text,
        level_filter,
        sort_by,
        sort_desc,
    )
    return paginate_rows(filtered, page, page_size)


def filter_sort_rows(
    rows: list[dict[str, str]],
    columns: list[str],
    search_text: str,
    level_filter: str,
    sort_by: str | None,
    sort_desc: bool,
) -> list[dict[str, str]]:
    filtered = filter_rows(rows, columns, search_text, level_filter)
    return sort_rows(filtered, columns, sort_by, sort_desc)


def filter_rows(
    rows: list[dict[str, str]],
    columns: list[str],
    search_text: str,
    level_filter: str,
) -> list[dict[str, str]]:
    search = (search_text or "").strip().lower()
    level_filter_normalized = (level_filter or "All").strip()

    filtered = rows
    if level_filter_normalized and level_filter_normalized != "All":
        level_column = next((c for c in columns if c.lower() == "level"), None)
        if level_column:
            filtered = [r for r in filtered if r.get(level_column, "") == level_filter_normalized]

    if search:
        # Usar _search_key pre-computado evita hacer lowercase × columna en cada fila.
        if filtered and "_search_key" in filtered[0]:
            filtered = [r for r in filtered if search in r["_search_key"]]
        else:
            filtered = [
                r
                for r in filtered
                if any(search in r.get(column, "").lower() for column in columns)
            ]

    # Devolvemos siempre una lista nueva para que callers puedan mutar/cachear
    # sin riesgo de alterar `rows` original.
    return list(filtered) if filtered is rows else filtered


def sort_rows(
    filtered_rows: list[dict[str, str]],
    columns: list[str],
    sort_by: str | None,
    sort_desc: bool,
) -> list[dict[str, str]]:
    if sort_by and sort_by in columns:
        return sorted(filtered_rows, key=lambda row: row.get(sort_by, ""), reverse=sort_desc)
    # Sin sort efectivo devolvemos una copia para no exponer la lista original.
    return list(filtered_rows)


def paginate_rows(
    filtered_rows: list[dict[str, str]],
    page: int,
    page_size: int,
) -> tuple[list[dict[str, str]], int, int, int]:
    total_filtered = len(filtered_rows)
    if total_filtered == 0:
        return [], 0, 1, 1

    safe_page_size = max(page_size, 1)
    total_pages = max((total_filtered + safe_page_size - 1) // safe_page_size, 1)
    safe_page = min(max(page, 1), total_pages)

    start = (safe_page - 1) * safe_page_size
    end = start + safe_page_size
    return filtered_rows[start:end], total_filtered, total_pages, safe_page


def export_rows_to_csv(file_path: str, columns: list[str], rows: list[dict[str, str]]) -> str:
    output_path = Path(file_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in columns})

    return str(output_path)
