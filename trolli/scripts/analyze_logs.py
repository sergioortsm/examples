#!/usr/bin/env python3
"""
analyze_logs.py
===============
Analiza ficheros ULS reales para mejorar src/smart_rules.json.

Flujo:
  1. Carga uno o varios ficheros .log de SharePoint ULS.
  2. Filtra por niveles de severidad (defecto: CRITICAL, UNEXPECTED, HIGH, MONITORABLE).
  3. Evalúa TODAS las reglas activas de smart_rules.json contra las filas de error.
  4. Imprime:
       a) Cobertura de cada regla (cuántas filas captura).
       b) Reglas con 0 matches (posibles patrones erróneos o demasiado específicos).
       c) Top N mensajes de error NO cubiertos, agrupados por Category/Area.
       d) Top N frases normalizadas más frecuentes (para idear nuevos patrones).
  5. Opcional: exporta candidatos de nuevas reglas a un JSON listo para revisar.

Uso básico:
    python scripts/analyze_logs.py C:\\logs\\SharePoint.log

Varios ficheros / glob:
    python scripts/analyze_logs.py "C:\\logs\\*.log"

Con candidatos exportados:
    python scripts/analyze_logs.py C:\\logs\\SharePoint.log --out candidates.json

Opciones:
    --top N          Top N líneas en cada sección del reporte (defecto: 30)
    --levels L,...   Niveles a analizar, separados por coma
                     (defecto: CRITICAL,UNEXPECTED,HIGH,MONITORABLE)
    --out FILE       Exportar candidatos de reglas a JSON
    --min-count N    Mínimo de ocurrencias para incluir un candidato (defecto: 3)
    --all-levels     Analizar TODOS los niveles (ignora --levels)
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

# ──────────────────────────────────────────────────────────────────────────────
# Ajuste de path para importar desde src/
# ──────────────────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent.resolve()
SRC_DIR = SCRIPT_DIR.parent / "src"
sys.path.insert(0, str(SRC_DIR))

from log_service import load_sharepoint_log   # noqa: E402
from smart_rules import RulesEngine            # noqa: E402

# ──────────────────────────────────────────────────────────────────────────────
# Constantes
# ──────────────────────────────────────────────────────────────────────────────
DEFAULT_LEVELS   = {"CRITICAL", "UNEXPECTED", "HIGH", "MONITORABLE"}
DEFAULT_TOP      = 30
DEFAULT_MIN_COUNT = 3

# Patrones para normalizar mensajes y agrupar variantes del mismo error
_GUID_RE  = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I)
_HEX_RE   = re.compile(r"\b0x[0-9a-f]{4,}\b", re.I)
_NUM4_RE  = re.compile(r"\b\d{4,}\b")
_PATH_RE  = re.compile(r"[A-Za-z]:\\[^\t\n\r]{3,}|(?:https?|file)://\S+")
_QUOT_RE  = re.compile(r"'[^']{2,60}'|\"[^\"]{2,60}\"")  # strings entrecomillados


def _normalize_msg(msg: str) -> str:
    """Elimina partes variables (GUIDs, rutas, números grandes) para agrupar variantes."""
    m = msg.strip()
    m = _GUID_RE.sub("<GUID>", m)
    m = _HEX_RE.sub("<HEX>", m)
    m = _PATH_RE.sub("<PATH>", m)
    m = _QUOT_RE.sub("<STR>", m)
    m = _NUM4_RE.sub("<N>", m)
    return m[:150]


def _rule_id(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()[:16]


# ──────────────────────────────────────────────────────────────────────────────
# Carga de ficheros
# ──────────────────────────────────────────────────────────────────────────────

def load_files(file_patterns: list[str]) -> tuple[list[dict], list[str], int]:
    """
    Devuelve (all_rows, columns, total_files_ok).
    'all_rows' incluye la clave '_search_key' de cada fila.
    """
    all_rows: list[dict] = []
    columns: list[str] = []
    total_ok = 0

    for pattern in file_patterns:
        expanded = sorted(glob.glob(pattern, recursive=True))
        if not expanded:
            expanded = [pattern]

        for fpath in expanded:
            if not Path(fpath).exists():
                print(f"  ✗ No encontrado: {fpath}")
                continue
            print(f"  Cargando: {fpath} …", end="", flush=True)
            result = load_sharepoint_log(fpath)
            if result.error:
                print(f"  ERROR: {result.error}")
                continue
            total_ok += 1
            all_rows.extend(result.rows)
            if not columns and result.columns:
                columns = result.columns
            print(f"  {len(result.rows):>10,} filas")

    return all_rows, columns, total_ok


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
        rule_hits   dict[rule_id → nº filas que matchean esa regla]
        unmatched   filas no capturadas por NINGUNA regla activa
        covered_count  nº de filas únicas cubiertas por al menos una regla
    """
    rules = [r for r in engine.get_rules() if r.enabled]
    rule_hits: dict[str, int] = {r.id: 0 for r in rules}

    # Precompilar reglas regex
    compiled_pats: dict[str, re.Pattern | None] = {}
    for r in rules:
        if r.is_regex:
            try:
                compiled_pats[r.id] = re.compile(r.pattern, re.IGNORECASE)
            except re.error as exc:
                print(f"  ⚠  Regex inválida en regla '{r.name}': {exc}")
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
    Agrupa los mensajes no cubiertos y cuenta frases normalizadas.

    Devuelve:
        by_category   dict[(category, area, process) → [mensaje_raw, ...]]
        norm_counter  Counter de frases normalizadas (para detectar patrones)
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
# Sugerencia de candidatos de reglas
# ──────────────────────────────────────────────────────────────────────────────

_SKIP_WORDS = frozenset({
    "the", "a", "an", "is", "was", "were", "has", "have", "had",
    "to", "of", "in", "for", "on", "with", "at", "by", "from",
    "this", "that", "and", "or", "but", "not", "be", "it", "its",
    # Placeholders del normalizador
    "<guid>", "<hex>", "<n>", "<path>", "<str>",
})


def _key_phrase(norm_msg: str) -> str | None:
    """
    Extrae una frase candidata a patrón desde un mensaje normalizado.
    Toma los primeros 4 tokens de palabra (≥4 chars, solo letras/guiones).
    Devuelve None si no hay suficientes tokens.
    """
    tokens = [
        w.lower().strip(".,;:()")
        for w in re.split(r"\s+", norm_msg)
        if re.match(r"[a-zA-Z]", w)
        and len(w) >= 4
        and w.lower() not in _SKIP_WORDS
    ]
    if len(tokens) < 2:
        return None
    # Frase de hasta 4 palabras clave
    return " ".join(tokens[:4])


def suggest_candidates(
    norm_counter: Counter,
    min_count: int,
    top: int,
) -> list[dict]:
    """
    Genera una lista de reglas candidatas basadas en mensajes frecuentes no cubiertos.
    Cada candidato tiene:
        - Los mismos campos que smart_rules.json
        - enabled=false (para revisión manual)
        - _count y _sample para contexto
    """
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
            "name":            f"[CANDIDATO] {phrase[:55]}",
            "domain":          "SPFx",          # ← ajustar manualmente
            "field":           "*",
            "pattern":         phrase,
            "is_regex":        False,
            "highlight_color": "#888888",
            "enabled":         False,
            "_count":          count,
            "_sample":         norm_msg[:120],
        })

        if len(candidates) >= top:
            break

    return candidates


# ──────────────────────────────────────────────────────────────────────────────
# Aprendizaje interactivo
# ──────────────────────────────────────────────────────────────────────────────

_DOMAINS = [
    "SPFx",
    "Timer Jobs",
    "wsps / Paquetes",
    "PowerShell / Deploy",
    "Distributed Cache",
    "Config / Object Cache",
]

_DOMAIN_COLORS = {
    "SPFx":                 "#FF6F00",
    "Timer Jobs":           "#1565C0",
    "wsps / Paquetes":      "#2E7D32",
    "PowerShell / Deploy":  "#B71C1C",
    "Distributed Cache":    "#BF360C",
    "Config / Object Cache":"#4527A0",
}


def _matches_phrase(phrase: str, msg: str) -> bool:
    """True si todas las palabras del patrón aparecen en el mensaje."""
    words = phrase.lower().split()
    msg_l = msg.lower()
    return all(w in msg_l for w in words)


def _guess_domain(categories: list[str]) -> str:
    """Heurístico: deduce el dominio a partir de nombres de categoría/área."""
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


def _enrich_candidates(
    candidates: list[dict],
    by_category: dict,
) -> list[dict]:
    """Añade '_categories' y ajusta 'domain' / 'highlight_color' heurísticamente."""
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


def _pick_domain(current: str) -> str:
    """Menú numerado para elegir dominio; Enter mantiene el actual."""
    print()
    for i, d in enumerate(_DOMAINS, 1):
        marker = "  ◄" if d == current else ""
        print(f"    {i}. {d}{marker}")
    while True:
        v = input("  Dominio (nº o nombre, Enter=mantener): ").strip()
        if not v:
            return current
        if v.isdigit():
            idx = int(v) - 1
            if 0 <= idx < len(_DOMAINS):
                return _DOMAINS[idx]
        matches = [d for d in _DOMAINS if v.lower() in d.lower()]
        if len(matches) == 1:
            return matches[0]
        print(f"  No reconocido. Elige número 1-{len(_DOMAINS)} o escribe parte del nombre.")


def learn_loop(candidates: list[dict], rules_path: Path) -> None:
    """
    Presenta cada candidato interactivamente.
    Los aceptados se escriben inmediatamente en smart_rules.json.

    Teclas:
        Enter / a  →  Añadir con los valores mostrados
        e          →  Editar patrón e is_regex
        d          →  Cambiar dominio
        n          →  Editar nombre
        r          →  Marcar como is_regex=true/false
        s          →  Saltar (no añadir)
        q          →  Guardar lo aceptado y salir
    """
    existing: list[dict] = json.loads(rules_path.read_text(encoding="utf-8"))
    existing_ids: set[str] = {r["id"] for r in existing}

    added   = 0
    skipped = 0
    total   = len(candidates)

    print(f"\n{'═'*72}")
    print(f"  MODO APRENDIZAJE  —  {total} candidatos para revisar")
    print(f"  Teclas: Enter/[a]=Añadir  [e]=Editar patrón  [d]=Dominio")
    print(f"          [n]=Nombre  [r]=toggle regex  [s]=Saltar  [q]=Salir")
    print(f"{'═'*72}\n")

    for i, cand in enumerate(candidates, 1):
        if cand["id"] in existing_ids:
            skipped += 1
            continue

        cats_str = ", ".join(cand.get("_categories", [])[:3]) or "(sin categoría)"

        while True:
            print(f"[{i}/{total}]{'─'*56}")
            print(f"  Ocurrencias : {cand['_count']:,}")
            print(f"  Muestra     : {cand['_sample'][:70]}")
            print(f"  Categorías  : {cats_str}")
            print(f"  Patrón      : {cand['pattern']!r}  (is_regex={cand['is_regex']})")
            print(f"  Nombre      : {cand['name'].replace('[CANDIDATO] ', '')}")
            print(f"  Dominio     : {cand['domain']}")
            print()

            raw = input("  ¿Qué hago? > ").strip().lower()

            if raw in ("", "a"):
                new_rule = {
                    "id":              cand["id"],
                    "name":            cand["name"].replace("[CANDIDATO] ", ""),
                    "domain":          cand["domain"],
                    "field":           cand["field"],
                    "pattern":         cand["pattern"],
                    "is_regex":        cand["is_regex"],
                    "highlight_color": cand["highlight_color"],
                    "enabled":         True,
                }
                existing.append(new_rule)
                existing_ids.add(new_rule["id"])
                rules_path.write_text(
                    json.dumps(existing, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                print(f"  ✓ Añadida → {new_rule['name']}\n")
                added += 1
                break

            elif raw == "e":
                new_pat = input(f"  Nuevo patrón [{cand['pattern']}]: ").strip()
                if new_pat:
                    cand["pattern"] = new_pat
                    cand["id"]      = _rule_id(new_pat)

            elif raw == "r":
                cand["is_regex"] = not cand["is_regex"]
                print(f"  is_regex → {cand['is_regex']}")

            elif raw == "d":
                cand["domain"]          = _pick_domain(cand["domain"])
                cand["highlight_color"] = _DOMAIN_COLORS.get(cand["domain"], "#888888")

            elif raw == "n":
                new_name = input(f"  Nuevo nombre: ").strip()
                if new_name:
                    cand["name"] = new_name

            elif raw == "s":
                skipped += 1
                print()
                break

            elif raw == "q":
                print(f"\n  Sesión terminada.")
                print(f"  Añadidas: {added}  |  Saltadas: {skipped}  |  Pendientes: {total - i}")
                return

            else:
                print("  Tecla no reconocida (Enter, a, e, r, d, n, s, q).")

    print(f"\n{'═'*72}")
    print(f"  APRENDIZAJE COMPLETADO  —  Añadidas: {added}  |  Saltadas/ya existían: {skipped}")
    print(f"{'═'*72}\n")


def merge_candidates_file(cand_path: Path, rules_path: Path) -> None:
    """
    Importa en smart_rules.json los candidatos con 'enabled': true del fichero
    cand_path.  Los que ya existen (mismo id) se omiten silenciosamente.
    """
    candidates: list[dict] = json.loads(cand_path.read_text(encoding="utf-8"))
    existing:   list[dict] = json.loads(rules_path.read_text(encoding="utf-8"))
    existing_ids = {r["id"] for r in existing}

    added = 0
    for c in candidates:
        if not c.get("enabled"):
            continue
        if c["id"] in existing_ids:
            print(f"  ⚠ Ya existe, omitido: {c.get('name', c['id'])}")
            continue
        new_rule = {k: v for k, v in c.items() if not k.startswith("_")}
        new_rule["name"] = new_rule.get("name", "").replace("[CANDIDATO] ", "")
        existing.append(new_rule)
        existing_ids.add(new_rule["id"])
        print(f"  ✓ Importada: {new_rule['name']}")
        added += 1

    if added:
        rules_path.write_text(
            json.dumps(existing, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\n✓ {added} regla(s) importadas → {rules_path}")
    else:
        print("  Sin cambios (ningún candidato habilitado o todos ya existían).")


# ──────────────────────────────────────────────────────────────────────────────
# Reporte en consola
# ──────────────────────────────────────────────────────────────────────────────

_SEP  = "=" * 72
_DASH = "-" * 72


def _bar(pct: float, width: int = 20) -> str:
    filled = round(pct * width / 100)
    return "█" * filled + "░" * (width - filled)


def print_report(
    engine: RulesEngine,
    rule_hits: dict[str, int],
    unmatched: list[dict],
    covered: int,
    total_error: int,
    analysis: dict,
    top: int,
) -> None:
    rules_by_id = {r.id: r for r in engine.get_rules()}
    norm_counter: Counter = analysis["norm_counter"]
    by_category: dict     = analysis["by_category"]

    # ── 1. Cobertura global ──────────────────────────────────────────────────
    print(f"\n{_SEP}")
    print("  COBERTURA GLOBAL")
    print(_SEP)
    pct_covered = (covered / total_error * 100) if total_error else 0.0
    pct_uncov   = 100.0 - pct_covered
    print(f"  Filas de error totales  : {total_error:>10,}")
    print(f"  Cubiertas (≥1 regla)    : {covered:>10,}  ({pct_covered:.1f}%)")
    print(f"  No cubiertas            : {len(unmatched):>10,}  ({pct_uncov:.1f}%)")

    # ── 2. Cobertura por regla ───────────────────────────────────────────────
    print(f"\n{_SEP}")
    print("  COBERTURA POR REGLA (ordenado por matches)")
    print(_SEP)
    print(f"  {'Matches':>7}  {'Bar':20}  Regla")
    print(f"  {_DASH}")

    sorted_hits = sorted(rule_hits.items(), key=lambda kv: -kv[1])
    for rule_id, hits in sorted_hits:
        r    = rules_by_id.get(rule_id)
        name = r.name if r else rule_id
        pct  = (hits / total_error * 100) if total_error else 0.0
        bar  = _bar(pct, 18)
        print(f"  {hits:>7,}  {bar}  {name}")

    # ── 3. Reglas con 0 matches ──────────────────────────────────────────────
    zero_rules = [
        rules_by_id[rid]
        for rid, hits in rule_hits.items()
        if hits == 0 and rid in rules_by_id
    ]
    if zero_rules:
        print(f"\n  ⚠  {len(zero_rules)} regla(s) con 0 matches sobre estas filas de error:")
        for r in zero_rules:
            regex_flag = "[regex]" if r.is_regex else "[texto]"
            print(f"     {regex_flag:9}  campo={r.field!r:<14}  patrón={r.pattern!r}")
            print(f"             → {r.name}")

    # ── 4. Top mensajes no cubiertos (normalizados) ──────────────────────────
    print(f"\n{_SEP}")
    print(f"  TOP {top} FRASES NO CUBIERTAS (normalizadas, por frecuencia)")
    print(_SEP)
    print(f"  {'Count':>7}  Mensaje normalizado")
    print(f"  {_DASH}")
    for norm_msg, count in norm_counter.most_common(top):
        print(f"  {count:>7,}  {norm_msg[:64]}")

    # ── 5. Top grupos Category+Area ──────────────────────────────────────────
    print(f"\n{_SEP}")
    print(f"  TOP {top} GRUPOS Category+Area NO CUBIERTOS")
    print(_SEP)

    cat_counts = Counter({k: len(v) for k, v in by_category.items()})
    for (cat, area, proc), count in cat_counts.most_common(top):
        msgs   = by_category[(cat, area, proc)]
        sample = msgs[0][:70] if msgs else ""
        proc_s = f"  Proceso={proc!r}" if proc else ""
        print(f"\n  {count:>6,}  Category={cat!r}")
        print(f"          Area={area!r}{proc_s}")
        print(f"          Muestra: {sample}")

    print(f"\n{'='*72}")


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="analyze_logs",
        description="Analiza ULS logs reales para mejorar smart_rules.json",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "files", nargs="*",
        help="Uno o varios ficheros .log (admite glob entre comillas). "
             "No necesario con --merge.",
    )
    parser.add_argument(
        "--top", type=int, default=DEFAULT_TOP, metavar="N",
        help=f"Número de líneas en cada sección (defecto: {DEFAULT_TOP})",
    )
    parser.add_argument(
        "--levels", default=",".join(sorted(DEFAULT_LEVELS)), metavar="L,...",
        help=(
            "Niveles a analizar, separados por coma "
            f"(defecto: {','.join(sorted(DEFAULT_LEVELS))})"
        ),
    )
    parser.add_argument(
        "--all-levels", action="store_true",
        help="Analizar TODOS los niveles ULS (ignora --levels)",
    )
    parser.add_argument(
        "--out", default=None, metavar="FILE",
        help="Exportar candidatos de nuevas reglas a este fichero JSON",
    )
    parser.add_argument(
        "--min-count", type=int, default=DEFAULT_MIN_COUNT, metavar="N",
        help=f"Mínimo ocurrencias para incluir un candidato (defecto: {DEFAULT_MIN_COUNT})",
    )
    parser.add_argument(
        "--learn", action="store_true",
        help=(
            "Modo aprendizaje interactivo: tras el análisis presenta los candidatos "
            "y escribe en smart_rules.json los que el usuario acepte."
        ),
    )
    parser.add_argument(
        "--merge", default=None, metavar="FILE",
        help=(
            "Importar silenciosamente a smart_rules.json los candidatos con "
            "'enabled': true de un JSON previo (no necesita ficheros de log)."
        ),
    )
    args = parser.parse_args()

    rules_path = SRC_DIR / "smart_rules.json"

    # ── Modo --merge: importación silenciosa, sin necesidad de logs ───────────
    if args.merge:
        cand_path = Path(args.merge)
        if not cand_path.exists():
            print(f"ERROR: No se encontró el fichero de candidatos: {cand_path}")
            sys.exit(1)
        if not rules_path.exists():
            print(f"ERROR: No se encontró smart_rules.json en {rules_path}")
            sys.exit(1)
        print(f"Importando candidatos desde {cand_path} → {rules_path} …")
        merge_candidates_file(cand_path, rules_path)
        return

    # ── Validar que se proporcionaron ficheros de log ─────────────────────────
    if not args.files:
        parser.error(
            "Debes indicar al menos un fichero .log, o usar --merge FILE "
            "para importar candidatos sin analizar logs."
        )

    target_levels: set[str] | None = (
        None if args.all_levels
        else {lv.strip().upper() for lv in args.levels.split(",") if lv.strip()}
    )

    # ── Cargar reglas ─────────────────────────────────────────────────────────
    engine = RulesEngine()
    if rules_path.exists():
        engine.load(str(rules_path))
        n_rules  = len(engine.get_rules())
        n_active = sum(1 for r in engine.get_rules() if r.enabled)
        print(f"Reglas cargadas: {n_rules} total, {n_active} activas  ← {rules_path}")
    else:
        print("AVISO: smart_rules.json no encontrado; usando reglas por defecto")

    # ── Cargar ficheros ───────────────────────────────────────────────────────
    print("\nCargando ficheros de log…")
    all_rows, _columns, total_files = load_files(args.files)

    if not all_rows:
        print("\nERROR: No se cargaron filas. Verifica las rutas de los ficheros.")
        sys.exit(1)

    print(f"\nTotal filas cargadas : {len(all_rows):,}  ({total_files} fichero(s))")

    # ── Filtrar por nivel ─────────────────────────────────────────────────────
    if target_levels:
        error_rows = [r for r in all_rows if r.get("Level", "").upper() in target_levels]
        lvl_label  = ", ".join(sorted(target_levels))
        print(f"Filas en niveles [{lvl_label}]: {len(error_rows):,}")
    else:
        error_rows = list(all_rows)
        print(f"Filas (todos los niveles): {len(error_rows):,}")

    if not error_rows:
        print("\nNo hay filas con los niveles seleccionados.")
        print("Prueba --all-levels o ajusta --levels con los niveles presentes en tu log.")
        sys.exit(0)

    # ── Cobertura de reglas ───────────────────────────────────────────────────
    print("\nEvaluando cobertura de reglas…")
    rule_hits, unmatched, covered = analyze_coverage(engine, error_rows)

    # ── Análisis de no cubiertos ──────────────────────────────────────────────
    print("Analizando mensajes no cubiertos…")
    analysis = analyze_unmatched(unmatched)

    # ── Reporte ───────────────────────────────────────────────────────────────
    print_report(
        engine, rule_hits, unmatched, covered,
        len(error_rows), analysis, args.top,
    )

    # ── Exportar candidatos ───────────────────────────────────────────────────
    if args.out:
        candidates = suggest_candidates(
            analysis["norm_counter"],
            args.min_count,
            args.top,
        )
        out_path = Path(args.out)
        out_path.write_text(
            json.dumps(candidates, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\n✓ {len(candidates)} candidatos exportados → {out_path}")
        print("  Revisa el JSON, ajusta 'domain', 'pattern' e 'is_regex',")
        print("  pon 'enabled': true en los que quieras activar,")
        print("  y ejecuta:  python scripts/analyze_logs.py --merge <fichero>")
        print("  o arranca el modo interactivo con:  ... --learn\n")

    # ── Modo aprendizaje interactivo ──────────────────────────────────────────
    if args.learn:
        if not rules_path.exists():
            print("ERROR: --learn requiere que exista src/smart_rules.json")
            sys.exit(1)
        candidates = suggest_candidates(
            analysis["norm_counter"],
            args.min_count,
            args.top,
        )
        candidates = _enrich_candidates(candidates, analysis["by_category"])
        learn_loop(candidates, rules_path)


if __name__ == "__main__":
    main()


    # ── Cobertura de reglas ───────────────────────────────────────────────────
    print("\nEvaluando cobertura de reglas…")
    rule_hits, unmatched, covered = analyze_coverage(engine, error_rows)

    # ── Análisis de no cubiertos ──────────────────────────────────────────────
    print("Analizando mensajes no cubiertos…")
    analysis = analyze_unmatched(unmatched)

    # ── Reporte ───────────────────────────────────────────────────────────────
    print_report(
        engine, rule_hits, unmatched, covered,
        len(error_rows), analysis, args.top,
    )

    # ── Exportar candidatos ───────────────────────────────────────────────────
    if args.out:
        candidates = suggest_candidates(
            analysis["norm_counter"],
            args.min_count,
            args.top,
        )
        out_path = Path(args.out)
        out_path.write_text(
            json.dumps(candidates, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\n✓ {len(candidates)} candidatos exportados → {out_path}")
        print("  Revisa el JSON, ajusta 'domain', 'pattern' e 'is_regex',")
        print("  pon 'enabled': true en los que quieras activar,")
        print("  y copia las entradas a src/smart_rules.json.\n")


if __name__ == "__main__":
    main()
