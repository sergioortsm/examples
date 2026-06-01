from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import csv
import io
import re

MAX_LOG_SIZE_BYTES = 350 * 1024 * 1024
_ULS_TIMESTAMP_RE = re.compile(r"^\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2}\.\d{2,3}$")

# Columnas que nunca tienen filtro de valor por diseño (demasiados valores únicos
# o columna de texto libre). Se usa tanto en la vista como en la migración de prefs.
DEFAULT_NO_FILTER_COLUMNS: frozenset[str] = frozenset({"Timestamp", "TimeSpan", "Message"})


def col_spec_name(spec: "str | dict") -> str:
    """Extrae el nombre de un ColumnSpec (acepta str o dict para backward compat)."""
    if isinstance(spec, dict):
        return str(spec.get("name", ""))
    return str(spec)


def col_names(specs: list) -> list[str]:
    """Devuelve lista de nombres a partir de una lista de ColumnSpecs o strings."""
    return [col_spec_name(s) for s in specs]


def make_col_spec(name: str, filter_on: bool | None = None) -> dict:
    """Construye un ColumnSpec. filter_on=None deduce el valor según DEFAULT_NO_FILTER_COLUMNS."""
    if filter_on is None:
        filter_on = name not in DEFAULT_NO_FILTER_COLUMNS
    return {"name": name, "filter": filter_on}

# Presets de filtro temporal (key → label para la UI)
TIMESTAMP_PRESETS: dict[str, str] = {
    "all":       "Todas",
    "15m":       "Últ. 15min",
    "1h":        "Última hora",
    "4h":        "Últimas 4h",
    "today":     "Hoy",
    "yesterday": "Ayer",
}
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
    col_values: dict[str, list[str]] = field(default_factory=dict)
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


def _fast_parse_ts(ts: str):
    """Parsea un timestamp ULS 'MM/DD/YYYY HH:MM:SS.mmm' por slicing (sin strptime).

    Devuelve una tupla comparable (YYYY, MM, DD, HH, MM, SS) o None si el
    string no tiene el formato esperado. Es ~5x mas rapido que strptime para
    100k filas.
    """
    if len(ts) < 19:
        return None
    try:
        month  = int(ts[0:2])
        day    = int(ts[3:5])
        year   = int(ts[6:10])
        hour   = int(ts[11:13])
        minute = int(ts[14:16])
        second = int(ts[17:19])
        return (year, month, day, hour, minute, second)
    except (ValueError, IndexError):
        return None


def compute_max_timestamp(rows: list[dict[str, str]]) -> tuple | None:
    """Devuelve la tupla (year, month, day, hour, minute, second) del timestamp mas
    reciente del log, o None si no hay filas con timestamp valido.

    Se llama una sola vez al activar un preset distinto de 'all'; el coste es O(n)
    pero las comparaciones son solo tuplas de ints, sin objetos datetime.
    """
    max_ts = None
    for row in rows:
        ts = row.get("Timestamp", "")
        if not ts:
            continue
        parsed = _fast_parse_ts(ts)
        if parsed is not None and (max_ts is None or parsed > max_ts):
            max_ts = parsed
    return max_ts


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
            error="El archivo supera el limite de 150 MB.",
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
    col_values: dict[str, set[str]] = {column: set() for column in columns}
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
        for column in columns:
            value = row.get(column, "").strip()
            if value:
                col_values[column].add(value)
        if level:
            level_values.add(level)

    return LogLoadResult(
        file_path=file_path,
        columns=columns,
        rows=rows,
        levels=sorted(level_values),
        col_values={column: sorted(values) for column, values in col_values.items()},
        error=None,
    )


def apply_filters_sort_paginate(
    rows: list[dict[str, str]],
    columns: list[str],
    search_text: str,
    level_filters: list[str],
    sort_by: str | None,
    sort_desc: bool,
    page: int,
    page_size: int,
) -> tuple[list[dict[str, str]], int, int, int]:
    filtered = filter_sort_rows(
        rows,
        columns,
        search_text,
        level_filters,
        sort_by,
        sort_desc,
    )
    return paginate_rows(filtered, page, page_size)


def filter_sort_rows(
    rows: list[dict[str, str]],
    columns: list[str],
    search_text: str,
    level_filters: list[str],
    sort_by: str | None,
    sort_desc: bool,
    column_filters: dict[str, str] | None = None,
) -> list[dict[str, str]]:
    filtered = filter_rows(rows, columns, search_text, level_filters, column_filters)
    return sort_rows(filtered, columns, sort_by, sort_desc)


def filter_rows(
    rows: list[dict[str, str]],
    columns: list[str],
    search_text: str,
    level_filters: list[str],
    column_filters: dict[str, str] | None = None,
    timestamp_preset: str = "all",
    timestamp_ref: tuple | None = None,
) -> list[dict[str, str]]:
    search = (search_text or "").strip().lower()
    level_filter_set: set[str] = set(level_filters) if level_filters else set()

    filtered = rows

    # --- Filtro de rango temporal (preset) ---
    preset = (timestamp_preset or "all").strip()
    if preset != "all" and timestamp_ref is not None:
        ref_year, ref_month, ref_day, ref_hour, ref_minute, ref_second = timestamp_ref
        if preset in ("15m", "1h", "4h"):
            delta_seconds = {"15m": 15 * 60, "1h": 60 * 60, "4h": 4 * 60 * 60}[preset]
            # Calcular cutoff como tupla restando delta_seconds de la referencia
            ref_total_sec = ref_hour * 3600 + ref_minute * 60 + ref_second
            cutoff_total_sec = ref_total_sec - delta_seconds
            # Gestionar desbordamiento de dias (simplificado: solo ajustamos el dia)
            cutoff_day_offset = 0
            if cutoff_total_sec < 0:
                cutoff_day_offset = -((-cutoff_total_sec + 86399) // 86400)
                cutoff_total_sec = cutoff_total_sec % 86400
            c_h = cutoff_total_sec // 3600
            c_m = (cutoff_total_sec % 3600) // 60
            c_s = cutoff_total_sec % 60
            c_d = ref_day + cutoff_day_offset  # aproximacion valida para rangos < 1 dia
            # Construir tupla cutoff comparable
            cutoff = (ref_year, ref_month, c_d, c_h, c_m, c_s)
            filtered = [r for r in filtered if _fast_parse_ts(r.get("Timestamp", "") or "") is not None
                        and _fast_parse_ts(r.get("Timestamp", "") or "") >= cutoff]
        elif preset == "today":
            filtered = [
                r for r in filtered
                if (lambda p: p is not None and p[0] == ref_year and p[1] == ref_month and p[2] == ref_day)(
                    _fast_parse_ts(r.get("Timestamp", "") or "")
                )
            ]
        elif preset == "yesterday":
            # Ayer: restar 1 dia (simplificado, ignora meses/años al cruzar)
            y_d = ref_day - 1
            y_m = ref_month
            y_y = ref_year
            if y_d < 1:
                y_m -= 1
                if y_m < 1:
                    y_m = 12
                    y_y -= 1
                # Dias en el mes anterior (aproximacion)
                _days_in_month = [0,31,28,31,30,31,30,31,31,30,31,30,31]
                y_d = _days_in_month[y_m]
            filtered = [
                r for r in filtered
                if (lambda p: p is not None and p[0] == y_y and p[1] == y_m and p[2] == y_d)(
                    _fast_parse_ts(r.get("Timestamp", "") or "")
                )
            ]

    if level_filter_set:
        level_column = next((c for c in columns if c.lower() == "level"), None)
        if level_column:
            filtered = [r for r in filtered if r.get(level_column, "") in level_filter_set]

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

    # Filtros por columna individual (AND entre todos, contains case-insensitive)
    if column_filters:
        for col, val in column_filters.items():
            needle = (val or "").strip().lower()
            if needle and col in columns:
                filtered = [r for r in filtered if needle in r.get(col, "").lower()]

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
