"""
smart_rules.py
Motor de detección de patrones de error en logs ULS de SharePoint.

Dominios soportados: SPFx, Timer Jobs, wsps / Paquetes, PowerShell / Deploy.
"""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path

# ──────────────────────────────────────────────────────────────────────────────
# Dominios y colores
# ──────────────────────────────────────────────────────────────────────────────

DOMAIN_SPFX   = "SPFx"
DOMAIN_TIMER  = "Timer Jobs"
DOMAIN_WSP    = "wsps / Paquetes"
DOMAIN_PS     = "PowerShell / Deploy"
DOMAIN_CACHE  = "Distributed Cache"
DOMAIN_CONFIG = "Config / Object Cache"

ALL_DOMAINS: list[str] = [
    DOMAIN_SPFX,
    DOMAIN_TIMER,
    DOMAIN_WSP,
    DOMAIN_PS,
    DOMAIN_CACHE,
    DOMAIN_CONFIG,
]

DOMAIN_COLORS: dict[str, str] = {
    DOMAIN_SPFX:   "#7B52AB",
    DOMAIN_TIMER:  "#1565C0",
    DOMAIN_WSP:    "#2E7D32",
    DOMAIN_PS:     "#B71C1C",
    DOMAIN_CACHE:  "#BF360C",
    DOMAIN_CONFIG: "#4527A0",
}


# ──────────────────────────────────────────────────────────────────────────────
# Modelo de datos
# ──────────────────────────────────────────────────────────────────────────────


@dataclass
class SmartRule:
    id: str
    name: str
    domain: str
    field: str          # "*" = _search_key (toda la fila), else nombre de columna exacto
    pattern: str
    is_regex: bool
    highlight_color: str
    enabled: bool = True


# ──────────────────────────────────────────────────────────────────────────────
# Construcción de reglas predefinidas
# ──────────────────────────────────────────────────────────────────────────────


def _rule_id(domain: str, name: str) -> str:
    """ID determinista (MD5 truncado) para que los IDs sean estables entre reinicios."""
    return hashlib.md5(f"{domain}:{name}".encode()).hexdigest()[:16]


def _rule(name: str, domain: str, field: str, pattern: str, is_regex: bool) -> SmartRule:
    return SmartRule(
        id=_rule_id(domain, name),
        name=name,
        domain=domain,
        field=field,
        pattern=pattern,
        is_regex=is_regex,
        highlight_color=DOMAIN_COLORS[domain],
        enabled=True,
    )


_DEFAULT_RULES: list[SmartRule] = [
    # ── SPFx ──────────────────────────────────────────────────────────────────
    _rule("SPFx: Failed to load component",     DOMAIN_SPFX, "*",       r"failed to load component",                       False),
    _rule("SPFx: Could not find component",     DOMAIN_SPFX, "*",       r"could not find component",                       False),
    _rule("SPFx: ClientSideAssets error",       DOMAIN_SPFX, "*",       r"clientsideassets",                               False),
    _rule("SPFx: Component manifest error",     DOMAIN_SPFX, "*",       r"component manifest",                             False),
    _rule("SPFx: ClientSideComponent error",    DOMAIN_SPFX, "*",       r"clientsidecomponent",                            False),
    _rule("SPFx: Script failed to load",        DOMAIN_SPFX, "Message", r"script.*failed to load",                         True),
    _rule("SPFx: CORS / Access-Control",        DOMAIN_SPFX, "*",       r"access-control-allow-origin",                    False),
    _rule("SPFx: REST 401 Unauthorized",        DOMAIN_SPFX, "*",       r"401 unauthorized",                               False),
    _rule("SPFx: REST 403 Forbidden",           DOMAIN_SPFX, "*",       r"403 forbidden",                                  False),
    _rule("SPFx: WebPart exception",            DOMAIN_SPFX, "*",       r"webpart.*exception|exception.*webpart",           True),
    _rule("SPFx: RequestDigest / token error",  DOMAIN_SPFX, "*",       r"requestdigest|xrequestdigest",                   False),

    # ── Timer Jobs ────────────────────────────────────────────────────────────
    _rule("Jobs: Job failed",                   DOMAIN_TIMER, "*",       r"job.*failed|failed.*job",                        True),
    _rule("Jobs: Job definition not found",     DOMAIN_TIMER, "Message", r"job definition.*was not found",                  False),
    _rule("Jobs: Job time limit exceeded",      DOMAIN_TIMER, "Message", r"exceeded.*time limit|time limit.*exceeded",      True),
    _rule("Jobs: SPTimerJob error",             DOMAIN_TIMER, "*",       r"sptimerjob",                                     False),
    _rule("Jobs: SPJobDefinition error",        DOMAIN_TIMER, "*",       r"spjobdefinition",                                False),
    _rule("Jobs: OWSTIMER critical",            DOMAIN_TIMER, "Process", r"owstimer",                                       False),
    _rule("Jobs: Timer job exception",          DOMAIN_TIMER, "*",       r"timer.*job.*exception|job.*exception.*timer",    True),
    _rule("Jobs: Health Analyzer error",        DOMAIN_TIMER, "*",       r"health analyzer",                                False),
    _rule("Jobs: Job throttled / blocked",      DOMAIN_TIMER, "*",       r"job.*throttl|throttl.*job",                      True),
    _rule("Jobs: UsageManager is null",         DOMAIN_TIMER, "*",       r"usagemanager is null",                            False),
    _rule("Jobs: SharePoint Foundation Upgrade",DOMAIN_TIMER, "Category",r"upgrade",                                         False),

    # ── wsps / Paquetes ───────────────────────────────────────────────────────
    _rule("WSP: Solution deployment failed",    DOMAIN_WSP, "*",        r"solution deployment.*failed|failed.*solution deployment", True),
    _rule("WSP: Feature receiver error",        DOMAIN_WSP, "*",        r"spfeaturereceiver|feature.*receiver.*error",      True),
    _rule("WSP: Assembly not found",            DOMAIN_WSP, "*",        r"assembly.*not found|could not load.*assembly",    True),
    _rule("WSP: Feature activation failed",     DOMAIN_WSP, "*",        r"feature activation.*failed|failed.*feature activation", True),
    _rule("WSP: SafeControl error",             DOMAIN_WSP, "*",        r"safecontrol",                                     False),
    _rule("WSP: Solution retract error",        DOMAIN_WSP, "*",        r"solution.*retract|retract.*solution",             True),
    _rule("WSP: Solution cannot be deployed",   DOMAIN_WSP, "Message",  r"solution.*cannot be deployed",                    False),
    _rule("WSP: Feature already activated",     DOMAIN_WSP, "*",        r"feature.*already activated|already exists in the solution", True),
    _rule("WSP: Assembly version conflict",     DOMAIN_WSP, "*",        r"strong name.*validation|assembly.*version.*conflict", True),
    _rule("WSP: Failed to open resource file",  DOMAIN_WSP, "*",        r"failed to (open|read) (the file|resource file)",  True),

    # ── PowerShell / Deploy ───────────────────────────────────────────────────
    _rule("PS: Could not get super user token",  DOMAIN_PS, "*",         r"could not get token super user",                  False),
    _rule("PS: Claim in token is null",          DOMAIN_PS, "*",         r"claim in token.*null|claim.*null",                True),
    _rule("PS: Access is denied",               DOMAIN_PS, "*",         r"access is denied|access denied",                 True),
    _rule("PS: Unauthorized",                   DOMAIN_PS, "*",         r"unauthorized",                                    False),
    _rule("PS: Execution policy blocked",       DOMAIN_PS, "*",         r"execution policy",                                False),
    _rule("PS: Scripts disabled",               DOMAIN_PS, "*",         r"running scripts is disabled",                     False),
    _rule("PS: UnauthorizedAccessException",    DOMAIN_PS, "*",         r"unauthorizedaccessexception",                     False),
    _rule("PS: HTTP 401/403/500 error",         DOMAIN_PS, "*",         r"the remote server returned.*\(401\)|\(403\)|\(500\)", True),
    _rule("PS: Cannot load module",             DOMAIN_PS, "Message",   r"cannot be loaded because",                        False),
    _rule("PS: AppPool identity error",         DOMAIN_PS, "*",         r"apppool.*identity|identity.*apppool",             True),
    _rule("PS: Security token expired",         DOMAIN_PS, "*",         r"token.*expired|expired.*token|security token",   True),

    # ── Distributed Cache ─────────────────────────────────────────────────────
    _rule("Cache: SPDistributedCachePointerWrapper",    DOMAIN_CACHE, "*", r"spdistributedcachepointerwrapper",                         False),
    _rule("Cache: Token Cache failed to initialize",    DOMAIN_CACHE, "*", r"token cache.*failed to initialize",                         True),
    _rule("Cache: Token Cache failed to get token",     DOMAIN_CACHE, "*", r"token cache.*failed to get token",                          True),
    _rule("Cache: Token Cache reverting to local",      DOMAIN_CACHE, "*", r"reverting to local cache",                                  False),
    _rule("Cache: FeedCacheImplementation error",       DOMAIN_CACHE, "*", r"feedcacheimplementation",                                   False),
    _rule("Cache: SPDistributedCache probably down",    DOMAIN_CACHE, "*", r"spdistributedcache is probably down",                       False),
    _rule("Cache: FeedCacheService excepcion (ES)",     DOMAIN_CACHE, "*", r"feedcacheservice.isrepopulationneeded",                     False),

    # ── Config / Object Cache ─────────────────────────────────────────────────
    _rule("Config: RefreshDirtyCollections",            DOMAIN_CONFIG, "*", r"sppersistedobjectcollectioncache.refreshdirtycollections",  False),
    _rule("Config: SPPersistedObject OnDeserialization",DOMAIN_CONFIG, "*", r"sppersistedobject.ondeserialization",                      False),
    _rule("Config: Duplicate content type",             DOMAIN_CONFIG, "*", r"duplicate content type definition",                        False),
    _rule("Config: Forced due to logging gap",          DOMAIN_CONFIG, "*", r"forced due to logging gap",                               False),
    _rule("Config: LookupHostHeaderSite not found",     DOMAIN_CONFIG, "*", r"could not find spsite lookupinfo for host-header",         False),
    _rule("Config: Taxonomy cache miss expired",         DOMAIN_CONFIG, "*", r"taxonomy database change cache miss",                      False),
    _rule("Config: Flushing SQL connection pool",        DOMAIN_CONFIG, "*", r"flushing connection pool",                                 False),
    _rule("Config: ScriptType duplicated (CSOM)",        DOMAIN_CONFIG, "*", r"scripttype.*is duplicated",                                True),
]


# ──────────────────────────────────────────────────────────────────────────────
# Motor de reglas
# ──────────────────────────────────────────────────────────────────────────────


class RulesEngine:
    """Motor de detección de patrones por dominio sobre filas ULS."""

    def __init__(self) -> None:
        self._rules: list[SmartRule] = [_copy(r) for r in _DEFAULT_RULES]
        self._compiled: dict[str, re.Pattern[str]] = {}

    # ── Persistencia ─────────────────────────────────────────────────────────

    def load(self, path: str | Path) -> None:
        """Carga reglas desde JSON; si el archivo no existe mantiene los defaults."""
        p = Path(path)
        if not p.exists():
            return
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if not isinstance(data, list):
                return
            rules: list[SmartRule] = []
            for item in data:
                if not isinstance(item, dict):
                    continue
                try:
                    r = SmartRule(
                        id=str(item.get("id") or str(uuid.uuid4())),
                        name=str(item.get("name", "")),
                        domain=str(item.get("domain", "")),
                        field=str(item.get("field", "*")),
                        pattern=str(item.get("pattern", "")),
                        is_regex=bool(item.get("is_regex", False)),
                        highlight_color=str(item.get("highlight_color", "#888888")),
                        enabled=bool(item.get("enabled", True)),
                    )
                    if r.domain and r.pattern:
                        rules.append(r)
                except (TypeError, KeyError, ValueError):
                    continue
            if rules:
                self._rules = rules
                self._compiled.clear()
        except (json.JSONDecodeError, OSError):
            pass  # Mantiene defaults

    def save(self, path: str | Path) -> None:
        """Persiste las reglas actuales a JSON."""
        p = Path(path)
        try:
            p.write_text(
                json.dumps([asdict(r) for r in self._rules], ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError:
            pass

    # ── Acceso a reglas ───────────────────────────────────────────────────────

    def get_rules(self) -> list[SmartRule]:
        return list(self._rules)

    def get_rules_for_domain(self, domain: str) -> list[SmartRule]:
        return [r for r in self._rules if r.domain == domain]

    def get_domains(self) -> list[str]:
        return ALL_DOMAINS

    def add_rule(self, rule: SmartRule) -> None:
        if not rule.id:
            rule.id = str(uuid.uuid4())
        self._rules.append(rule)
        self._compiled.pop(rule.id, None)

    def update_rule(self, rule: SmartRule) -> None:
        for i, r in enumerate(self._rules):
            if r.id == rule.id:
                self._rules[i] = rule
                self._compiled.pop(rule.id, None)
                return

    def delete_rule(self, rule_id: str) -> None:
        self._rules = [r for r in self._rules if r.id != rule_id]
        self._compiled.pop(rule_id, None)

    def reset_to_defaults(self) -> None:
        self._rules = [_copy(r) for r in _DEFAULT_RULES]
        self._compiled.clear()

    # ── Motor de matching ─────────────────────────────────────────────────────

    def _compile(self, rule: SmartRule) -> re.Pattern[str] | None:
        if not rule.is_regex:
            return None
        cached = self._compiled.get(rule.id)
        if cached is not None:
            return cached
        try:
            compiled = re.compile(rule.pattern, re.IGNORECASE)
            self._compiled[rule.id] = compiled
            return compiled
        except re.error:
            return None

    def _match(self, rule: SmartRule, row: dict[str, str]) -> bool:
        if rule.field == "*":
            text = row.get("_search_key", "")
        else:
            text = row.get(rule.field, "") or ""
        if not text:
            return False
        if rule.is_regex:
            compiled = self._compile(rule)
            if compiled is None:
                return False
            return bool(compiled.search(text))
        return rule.pattern.lower() in text.lower()

    def apply(
        self, rows: list[dict[str, str]], domain: str
    ) -> dict[int, list[SmartRule]]:
        """Aplica las reglas del dominio a ``rows``.

        Devuelve ``dict[row_index → [SmartRule]]`` solo para índices con al menos un match.
        Es seguro llamarlo desde un hilo secundario (no modifica estado compartido).
        """
        active_rules = [r for r in self._rules if r.domain == domain and r.enabled]
        if not active_rules:
            return {}
        result: dict[int, list[SmartRule]] = {}
        for idx, row in enumerate(rows):
            matched: list[SmartRule] = []
            for rule in active_rules:
                if self._match(rule, row):
                    matched.append(rule)
            if matched:
                result[idx] = matched
        return result


def _copy(rule: SmartRule) -> SmartRule:
    return SmartRule(**asdict(rule))


# ──────────────────────────────────────────────────────────────────────────────
# Singleton global (compartido entre mixin y settings view)
# ──────────────────────────────────────────────────────────────────────────────

rules_engine = RulesEngine()
