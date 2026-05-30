from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import csv
import io

MAX_LOG_SIZE_BYTES = 50 * 1024 * 1024


@dataclass
class LogLoadResult:
    file_path: str
    columns: list[str]
    rows: list[dict[str, str]]
    levels: list[str]
    error: str | None = None


def _read_text_with_fallbacks(file_path: str) -> str:
    raw = Path(file_path).read_bytes()
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
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
    n_cols = len(columns)

    for raw_line in line_iter:
        if not raw_line.strip():
            continue
        row_values = _split_row(raw_line, n_cols)
        # _search_key: clave de búsqueda pre-computada (evita lowercase por columna en cada consulta).
        search_key = "\t".join(row_values).lower()
        row = dict(zip(columns, row_values))
        row["_search_key"] = search_key
        rows.append(row)
        if level_col_idx >= 0:
            level = row_values[level_col_idx].strip()
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

    if sort_by and sort_by in columns:
        filtered = sorted(filtered, key=lambda row: row.get(sort_by, ""), reverse=sort_desc)

    return filtered


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
