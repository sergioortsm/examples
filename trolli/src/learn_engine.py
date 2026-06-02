"""
learn_engine.py
===============
Motor de análisis de logs ULS para el ciclo de aprendizaje de reglas inteligentes.

Extrae la lógica de análisis de scripts/analyze_logs.py en un módulo importable
por la app Flet (sin CLI, sin prints, sin flujo interactivo).

Responsabilidades:
  - Cargar ficheros .log ULS y aplicar reglas activas para medir cobertura.
  - Detectar mensajes no cubiertos y proponer candidatos a nuevas reglas.
  - Persistir qué ficheros ya han sido procesados (learn_progress.json).
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

# ──────────────────────────────────────────────────────────────────────────────
# Import del servicio de carga de logs (disponible en src/)
# ──────────────────────────────────────────────────────────────────────────────
from log_service import load_sharepoint_log  # noqa: E402
from smart_rules import RulesEngine, ALL_DOMAINS, DOMAIN_COLORS  # noqa: E402

# ──────────────────────────────────────────────────────────────────────────────
# Constantes
# ──────────────────────────────────────────────────────────────────────────────
DEFAULT_LEVELS: set[str] = {"CRITICAL", "UNEXPECTED", "HIGH", "MONITORABLE"}
DEFAULT_TOP: int = 30
DEFAULT_MIN_COUNT: int = 3

# Normalizadores de mensajes
_GUID_RE = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I
)
_HEX_RE  = re.compile(r"\b0x[0-9a-f]{4,}\b", re.I)
_NUM4_RE = re.compile(r"\b\d{4,}\b")
_PATH_RE = re.compile(r"[A-Za-z]:\\[^\t\n\r]{3,}|(?:https?|file)://\S+")
_QUOT_RE = re.compile(r"'[^']{2,60}'|\"[^\"]{2,60}\"")

_SKIP_WORDS = frozenset({
    "the", "a", "an", "is", "was", "were", "has", "have", "had",
    "to", "of", "in", "for", "on", "with", "at", "by", "from",
    "this", "that", "and", "or", "but", "not", "be", "it", "its",
    "<guid>", "<hex>", "<n>", "<path>", "<str>",
})

_DOMAIN_COLORS: dict[str, str] = DOMAIN_COLORS  # alias

# ──────────────────────────────────────────────────────────────────────────────
# Normalización
# ──────────────────────────────────────────────────────────────────────────────

def _normalize_msg(msg: str) -> str:
    m = msg.strip()
    m = _GUID_RE.sub("<GUID>", m)
    m = _HEX_RE.sub("<HEX>", m)
    m = _PATH_RE.sub("<PATH>", m)
    m = _QUOT_RE.sub("<STR>", m)
    m = _NUM4_RE.sub("<N>", m)
    return m[:150]


def _rule_id(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()[:16]


def _key_phrase(norm_msg: str) -> str | None:
    tokens = [
        w.lower().strip(".,;:()")
        for w in re.split(r"\s+", norm_msg)
        if re.match(r"[a-zA-Z]", w)
        and len(w) >= 4
        and w.lower() not in _SKIP_WORDS
    ]
    if len(tokens) < 2:
        return None
    return " ".join(tokens[:4])


def _matches_phrase(phrase: str, msg: str) -> bool:
    words = phrase.lower().split()
    msg_l = msg.lower()
    return all(w in msg_l for w in words)


def _guess_domain(categories: list[str]) -> str:
    text = " ".join(categories).lower()
    if any(w in text for w in ("timer", "topology", "usagemanager", "upgrade", "health")):
        return "Timer Jobs"
    if any(w in text for w in ("distributed", "appfabric", "feedcache")):
        return "Distributed Cache"
    if any(w in text for w in ("taxonomy", "config", "objectcache", "sql", "publish", "lookup")):
        return "Config / Object Cache"
    if any(w in text for w in ("solution", "feature", "assembly", "wsp")):
        return "wsps / Paquetes"
    if any(w in text for w in ("powershell", "claims", "token", "spfx", "modern", "auth")):
        return "PowerShell / Deploy"
    return "Config / Object Cache"


def guess_domain_from_pattern(pattern: str, sample: str = "") -> str:
    """Infiere el dominio directamente desde el texto del patrón y la muestra.

    Útil cuando no se dispone de datos de categorías ULS (p.ej. importación
    de candidates.json sin análisis previo).  El orden de comprobación importa:
    las reglas más específicas van primero.
    """
    text = (pattern + " " + sample).lower()
    if any(w in text for w in ("timer", "timerjob", "topology", "usagemanager", "upgrade")):
        return "Timer Jobs"
    if any(w in text for w in ("distributed", "appfabric", "feedcache", "datacache")):
        return "Distributed Cache"
    if any(w in text for w in ("taxonomy", "objectcache", "persistedobject", "collectioncache",
                               "configcache", "sql", "publish", "lookup")):
        return "Config / Object Cache"
    if any(w in text for w in ("solution", "feature", "assembly", ".wsp", "solutiondeployment")):
        return "wsps / Paquetes"
    if any(w in text for w in ("powershell", "claims", "oauthcontext", "authentication")):
        return "PowerShell / Deploy"
    return "SPFx"


# ──────────────────────────────────────────────────────────────────────────────
# Carga de un único fichero
# ──────────────────────────────────────────────────────────────────────────────

def load_single_file(fpath: str | Path) -> tuple[list[dict], list[str], str | None]:
    """
    Carga un fichero .log ULS.
    Devuelve (rows, columns, error_msg).
    error_msg es None si fue OK.
    """
    result = load_sharepoint_log(str(fpath))
    if result.error:
        return [], [], result.error
    return result.rows, result.columns or [], None


# ──────────────────────────────────────────────────────────────────────────────
# Análisis de cobertura
# ──────────────────────────────────────────────────────────────────────────────

def analyze_coverage(
    engine: RulesEngine,
    error_rows: list[dict],
) -> tuple[dict[str, int], list[dict], int]:
    """
    Evalúa todas las reglas activas sobre las filas de error.

    Devuelve:
        rule_hits       dict[rule_id → nº filas que matchean]
        unmatched       filas no capturadas por ninguna regla
        covered_count   nº de filas únicas cubiertas por al menos una regla
    """
    rules = [r for r in engine.get_rules() if r.enabled]
    rule_hits: dict[str, int] = {r.id: 0 for r in rules}

    compiled_pats: dict[str, re.Pattern | None] = {}
    for r in rules:
        if r.is_regex:
            try:
                compiled_pats[r.id] = re.compile(r.pattern, re.IGNORECASE)
            except re.error:
                compiled_pats[r.id] = None
        else:
            compiled_pats[r.id] = None

    matched_mask = [False] * len(error_rows)

    for r in rules:
        pat_lower = r.pattern.lower()
        compiled  = compiled_pats.get(r.id)
        field     = r.field

        for idx, row in enumerate(error_rows):
            if field == "*":
                text = row.get("_search_key", "")
            else:
                text = row.get(field, "").lower()
            if not text:
                continue
            hit = (
                bool(compiled.search(text)) if r.is_regex and compiled
                else pat_lower in text
            )
            if hit:
                rule_hits[r.id] += 1
                matched_mask[idx] = True

    unmatched = [row for idx, row in enumerate(error_rows) if not matched_mask[idx]]
    covered   = sum(matched_mask)
    return rule_hits, unmatched, covered


# ──────────────────────────────────────────────────────────────────────────────
# Análisis de mensajes no cubiertos
# ──────────────────────────────────────────────────────────────────────────────

def analyze_unmatched(unmatched: list[dict]) -> dict:
    """
    Agrupa los mensajes no cubiertos.
    Devuelve dict con 'by_category' y 'norm_counter'.
    """
    by_category: defaultdict[tuple, list[str]] = defaultdict(list)
    norm_counter: Counter = Counter()

    for row in unmatched:
        cat  = row.get("Category", "").strip() or "(sin categoría)"
        area = row.get("Area", "").strip()      or "(sin área)"
        proc = row.get("Process", "").strip()   or ""
        msg  = row.get("Message", "").strip()

        by_category[(cat, area, proc)].append(msg)
        norm = _normalize_msg(msg)
        if norm:
            norm_counter[norm] += 1

    return {
        "by_category": dict(by_category),
        "norm_counter": norm_counter,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Sugerencia de candidatos
# ──────────────────────────────────────────────────────────────────────────────

def suggest_candidates(
    norm_counter: Counter,
    min_count: int = DEFAULT_MIN_COUNT,
    top: int = DEFAULT_TOP,
) -> list[dict]:
    """Genera candidatos a reglas desde mensajes frecuentes no cubiertos."""
    candidates: list[dict] = []
    seen_phrases: set[str] = set()

    for norm_msg, count in norm_counter.most_common(top * 3):
        if count < min_count:
            break
        phrase = _key_phrase(norm_msg)
        if not phrase or phrase in seen_phrases:
            continue
        seen_phrases.add(phrase)

        candidates.append({
            "id":              _rule_id(phrase),
            "name":            phrase[:55],
            "domain":          "SPFx",
            "field":           "*",
            "pattern":         phrase,
            "is_regex":        False,
            "highlight_color": "#888888",
            "enabled":         False,
            "_count":          count,
            "_sample":         norm_msg[:120],
            "_categories":     [],
        })

        if len(candidates) >= top:
            break

    return candidates


def enrich_candidates(
    candidates: list[dict],
    by_category: dict,
) -> list[dict]:
    """Añade '_categories' y ajusta 'domain'/'highlight_color' heurísticamente."""
    for cand in candidates:
        phrase = cand["pattern"]
        matching: list[str] = []
        for (cat, area, _proc), msgs in by_category.items():
            if any(_matches_phrase(phrase, m) for m in msgs[:40]):
                matching.append(f"{cat} / {area}")
            if len(matching) >= 5:
                break
        cand["_categories"]     = matching
        cand["domain"]          = _guess_domain(matching)
        cand["highlight_color"] = _DOMAIN_COLORS.get(cand["domain"], "#888888")
    return candidates


# ──────────────────────────────────────────────────────────────────────────────
# Filtrado por nivel ULS
# ──────────────────────────────────────────────────────────────────────────────

def filter_by_level(rows: list[dict], levels: set[str] | None = None) -> list[dict]:
    """Filtra filas por nivel ULS. Si levels es None usa DEFAULT_LEVELS."""
    lvls = levels if levels is not None else DEFAULT_LEVELS
    return [
        r for r in rows
        if r.get("Level", "").upper() in lvls
    ]


# ──────────────────────────────────────────────────────────────────────────────
# Progreso / ficheros ya procesados
# ──────────────────────────────────────────────────────────────────────────────

def _file_key(path: Path) -> tuple[str, int, float]:
    """Clave de identidad de un fichero: (path, size, mtime)."""
    try:
        stat = path.stat()
        return str(path), stat.st_size, stat.st_mtime
    except OSError:
        return str(path), 0, 0.0


class LearnProgress:
    """
    Gestiona el JSON de ficheros ya procesados para el ciclo de aprendizaje.

    Formato de learn_progress.json:
    {
        "watched_dir": "C:\\Temp\\LOGS",
        "processed": [
            {
                "path": "...",
                "size": 123456,
                "mtime": 1748736000.0,
                "processed_at": "2026-06-02T10:15:00",
                "candidates_found": 8,
                "rules_added": 3
            }
        ]
    }

    Identidad de fichero: (path, size, mtime).
    Si el fichero crece (log rotativo) el mtime o size cambia → se reproces.
    """

    def __init__(self) -> None:
        self.watched_dir: str = ""
        self._processed: list[dict] = []   # registros completos
        self._processed_keys: set[tuple] = set()   # (path, size, mtime)
        self.skipped_ids: set[str] = set()   # IDs de candidatos descartados por el usuario

    # ── Persistencia ──────────────────────────────────────────────────────────

    def load(self, path: str | Path) -> None:
        p = Path(path)
        if not p.exists():
            return
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            self.watched_dir  = data.get("watched_dir", "")
            self._processed   = data.get("processed", [])
            self._processed_keys = {
                (r["path"], r["size"], r["mtime"])
                for r in self._processed
                if "path" in r and "size" in r and "mtime" in r
            }
            self.skipped_ids = set(data.get("skipped_ids", []))
        except (json.JSONDecodeError, OSError, KeyError):
            pass

    def save(self, path: str | Path) -> None:
        p = Path(path)
        try:
            p.write_text(
                json.dumps(
                    {
                        "watched_dir": self.watched_dir,
                        "processed": self._processed,
                        "skipped_ids": sorted(self.skipped_ids),
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        except OSError:
            pass

    # ── Consulta ──────────────────────────────────────────────────────────────

    def scan_new_files(self, directory: str | Path) -> tuple[list[Path], int]:
        """
        Escanea *.log en 'directory'.
        Devuelve (nuevos: list[Path], ya_procesados: int).
        """
        d = Path(directory)
        if not d.is_dir():
            return [], 0

        all_logs = sorted(d.glob("*.log"))
        new: list[Path] = []
        already = 0

        for fpath in all_logs:
            key = _file_key(fpath)
            if key in self._processed_keys:
                already += 1
            else:
                new.append(fpath)

        return new, already

    def is_processed(self, fpath: Path) -> bool:
        return _file_key(fpath) in self._processed_keys

    def mark_processed(
        self,
        fpath: Path,
        candidates_found: int,
        rules_added: int,
    ) -> None:
        """Registra un fichero como procesado. Solo llamar si completó el ciclo."""
        key_path, key_size, key_mtime = _file_key(fpath)
        entry = {
            "path":             key_path,
            "size":             key_size,
            "mtime":            key_mtime,
            "processed_at":     datetime.now().isoformat(timespec="seconds"),
            "candidates_found": candidates_found,
            "rules_added":      rules_added,
        }
        self._processed.append(entry)
        self._processed_keys.add((key_path, key_size, key_mtime))

    @property
    def processed_count(self) -> int:
        return len(self._processed)
