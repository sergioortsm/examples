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
DOMAIN_TIMER  = "Timer Jobs"  # constante legacy: ya no se expone como tab
DOMAIN_WSP    = "wsps / Paquetes"
DOMAIN_PS     = "PowerShell / Deploy"
DOMAIN_CACHE  = "Distributed Cache"   # constante legacy: ya no se expone como tab
DOMAIN_CONFIG = "Config / Object Cache"  # constante legacy: ya no se expone como tab
DOMAIN_EVTRX = "EventReceivers"
DOMAIN_SYNC  = "Estado de sincronización / listas"
DOMAIN_API   = "API (Sync / REST / integración)"

ALL_DOMAINS: list[str] = [
    DOMAIN_SPFX,
    DOMAIN_API,
    DOMAIN_WSP,
    DOMAIN_PS,
    DOMAIN_EVTRX,
    DOMAIN_SYNC,
]

DOMAIN_COLORS: dict[str, str] = {
    DOMAIN_SPFX:   "#7B52AB",
    DOMAIN_TIMER:  "#1565C0",
    DOMAIN_WSP:    "#2E7D32",
    DOMAIN_PS:     "#B71C1C",
    DOMAIN_CACHE:  "#BF360C",
    DOMAIN_CONFIG: "#4527A0",
    DOMAIN_EVTRX:  "#00695C",
    DOMAIN_SYNC:   "#AD1457",
    DOMAIN_API:    "#1565C0",
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


def _rule(
    name: str,
    domain: str,
    field: str,
    pattern: str,
    is_regex: bool,
    enabled: bool = True,
) -> SmartRule:
    return SmartRule(
        id=_rule_id(domain, name),
        name=name,
        domain=domain,
        field=field,
        pattern=pattern,
        is_regex=is_regex,
        highlight_color=DOMAIN_COLORS[domain],
        enabled=enabled,
    )


_DEFAULT_RULES: list[SmartRule] = [
    # ── SPFx ──────────────────────────────────────────────────────────────────
    # Reglas COLABORAWS para despliegue SPFx. Todas regex, activadas.
    _rule("SPFx: Error al activar spfx",       DOMAIN_SPFX, "Message",  r"error al activar spfx",         True),
    _rule("SPFx: UMEAppcustomizerId",          DOMAIN_SPFX, "Message",        r"\bumeappcustomizerid\b",        True),
    _rule("SPFx: UMEWebpartBotonesId",         DOMAIN_SPFX, "Message",        r"\bumewebpartbotonesid\b",       True),
    _rule("SPFx: AgregarSPFxEnSitio",          DOMAIN_SPFX, "Message",        r"\bagregarspfxensitio\b",        True),
    _rule("SPFx: ExecuteIfSubsiteExists",      DOMAIN_SPFX, "Message",        r"\bexecuteifsubsiteexists\b",    True),

    # ── API (Sync / REST / integración) ───────────────────────────────────────
    # Reglas COLABORAWS para llamadas REST/sincronización. Todas regex, field="Message", activadas.
    _rule("API: FetchOperations",  DOMAIN_API, "Message", r"fetchoperations.*",       True),
    _rule("API: WebException al obtener operaciones",            DOMAIN_API, "Message", r"webexception al obtener operaciones",                            True),
    _rule("API: Excepción inesperada en FetchOperations",        DOMAIN_API, "Message", r"excepci[óo]n inesperada en fetchoperations",                   True),
    _rule("API: 401 Unauthorized Bearer Token",                  DOMAIN_API, "Message", r"\[401 unauthorized\].*bearer token (?:inv[áa]lido|expirado)",     True),
    _rule("API: 404 Not Found No se encontraron operaciones",    DOMAIN_API, "Message", r"\[404 not found\].*no se encontraron operaciones",               True),
    _rule("API: Error HTTP",                                     DOMAIN_API, "Message", r"\berror http\b",                                                  True),
    _rule("API: No se pudieron obtener operaciones del servicio",DOMAIN_API, "Message", r"no se pudieron obtener operaciones del servicio",                True),
    _rule("API: Sincronizando desde",                            DOMAIN_API, "Message", r"sincronizando desde\s*:",                                         True),
    _rule("API: Error al llamar al servicio (código)",           DOMAIN_API, "Message", r"error al llamar al servicio\.?\s*c[óo]digo\s*:",                  True),
    _rule("API: Respuesta sin ID válido",                        DOMAIN_API, "Message", r"la respuesta del servicio no contiene un id v[áa]lido",          True),
    _rule("API: No se recibió respuesta del servicio",           DOMAIN_API, "Message", r"no se recibi[óo] respuesta del servicio",                        True),

    # ── wsps / Paquetes ───────────────────────────────────────────────────────
    # Reglas genéricas (deshabilitadas por defecto: el tab WSP PAQUETES se centra
    # en los marcadores propios de COLABORAWS). Reactivar manualmente si interesa.
    _rule("WSP: Solution deployment failed",    DOMAIN_WSP, "Message",        r"solution deployment.*failed|failed.*solution deployment", True,  enabled=False),
    _rule("WSP: Feature receiver error",        DOMAIN_WSP, "Message",        r"spfeaturereceiver|feature.*receiver.*error",      True,  enabled=False),
    _rule("WSP: Assembly not found",            DOMAIN_WSP, "Message",        r"assembly.*not found|could not load.*assembly",    True,  enabled=False),
    _rule("WSP: Feature activation failed",     DOMAIN_WSP, "Message",        r"feature activation.*failed|failed.*feature activation", True,  enabled=False),
    _rule("WSP: SafeControl error",             DOMAIN_WSP, "Message",        r"safecontrol",                                     False, enabled=False),
    _rule("WSP: Solution retract error",        DOMAIN_WSP, "Message",        r"solution.*retract|retract.*solution",             True,  enabled=False),
    _rule("WSP: Solution cannot be deployed",   DOMAIN_WSP, "Message",        r"solution.*cannot be deployed",                    False, enabled=False),
    _rule("WSP: Feature already activated",     DOMAIN_WSP, "Message",        r"feature.*already activated|already exists in the solution", True,  enabled=False),
    _rule("WSP: Assembly version conflict",     DOMAIN_WSP, "Message",        r"strong name.*validation|assembly.*version.*conflict", True,  enabled=False),
    _rule("WSP: Failed to open resource file",  DOMAIN_WSP, "Message",        r"failed to (open|read) (the file|resource file)",  True,  enabled=False),
    # Reglas COLABORAWS (despliegue SharePoint On-Prem). Todas regex, case-insensitive.
    _rule("WSP: Error al crear niveles de permisos",          DOMAIN_WSP, "Message",  r"error al crear niveles de permisos",                                True),
    _rule("WSP: Error al crear listas",                       DOMAIN_WSP, "Message",  r"error al crear listas",                                             True),
    _rule("WSP: Error al crear bibliotecas",                  DOMAIN_WSP, "Message",  r"error al crear bibliotecas",                                        True),
    _rule("WSP: Error al crear páginas",                      DOMAIN_WSP, "Message",  r"error al crear p[áa]ginas",                                         True),
    _rule("WSP: Error al desplegar ArchivosWebparts",         DOMAIN_WSP, "Message",  r"error al desplegar biblioteca\s*['\"]?archivoswebparts",            True),
    _rule("WSP: No se encontró configuración IIS",            DOMAIN_WSP, "Message",  r"no se encontr[óo] configuraci[óo]n iis",                            True),
    _rule("WSP: Current User marker",                         DOMAIN_WSP, "Message",  r"\bcurrent user\s*:",                                                True),
    _rule("WSP: COLABORAWS.Infraestructure",                  DOMAIN_WSP, "*", r"\bcolaboraws\.infraestructure\b(?!\.master)",                       True),
    _rule("WSP: COLABORAWS.Infraestructure.Master",           DOMAIN_WSP, "*", r"\bcolaboraws\.infraestructure\.master\b",                           True),
    _rule("WSP: COLABORAWS.Import",                           DOMAIN_WSP, "*", r"\bcolaboraws\.import\b",                                            True),
    _rule("WSP: COLABORAWS.Export",                           DOMAIN_WSP, "*", r"\bcolaboraws\.export\b",                                            True),

    # ── PowerShell / Deploy ───────────────────────────────────────────────────
    _rule("PS: Could not get super user token",  DOMAIN_PS, "Message",         r"could not get token super user",                  False),
    _rule("PS: Claim in token is null",          DOMAIN_PS, "Message",         r"claim in token.*null|claim.*null",                True),
    _rule("PS: Access is denied",               DOMAIN_PS, "Message",         r"access is denied|access denied",                 True),
    _rule("PS: Unauthorized",                   DOMAIN_PS, "Message",         r"unauthorized",                                    False),
    _rule("PS: Execution policy blocked",       DOMAIN_PS, "Message",         r"execution policy",                                False),
    _rule("PS: Scripts disabled",               DOMAIN_PS, "Message",         r"running scripts is disabled",                     False),
    _rule("PS: UnauthorizedAccessException",    DOMAIN_PS, "Message",         r"unauthorizedaccessexception",                     False),
    _rule("PS: HTTP 401/403/500 error",         DOMAIN_PS, "Message",         r"the remote server returned.*\(401\)|\(403\)|\(500\)", True),
    _rule("PS: Cannot load module",             DOMAIN_PS, "Message",         r"cannot be loaded because",                        False),
    _rule("PS: AppPool identity error",         DOMAIN_PS, "Message",         r"apppool.*identity|identity.*apppool",             True),
    _rule("PS: Security token expired",         DOMAIN_PS, "Message",         r"token.*expired|expired.*token|security token",   True),

    # ── EventReceivers ────────────────────────────────────────────────────────
    _rule("EvtRx: FeatureActivated",                    DOMAIN_EVTRX, "*", r"\bfeatureactivated\b",                                      True),
    _rule("EvtRx: Error al limpiar los event receivers", DOMAIN_EVTRX, "Message",  r"error al limpiar los event receivers",                     True),
    _rule("EvtRx: EventReceiverListaOperaciones",       DOMAIN_EVTRX, "*", r"\beventreceiverlistaoperaciones\b",                         True),
    _rule("EvtRx: COLABORAWS.EventReceiver",            DOMAIN_EVTRX, "Category", r"\bcolaboraws\.eventreceiver\b(?!listaoperaciones)",         True),
    _rule("EvtRx: COLABORAWS.EventReceiverListaOperaciones", DOMAIN_EVTRX, "Category", r"\bcolaboraws\.eventreceiverlistaoperaciones\b",        True),
    _rule("EvtRx: Error al activar feature",            DOMAIN_EVTRX, "Message",  r"error al activar feature",                                  True),

    # ── Estado de sincronización / listas ───────────────────────────────────────────
    _rule("Sync: EstadoSync",                          DOMAIN_SYNC, "Message", r"\bestadosync\b",                                            True),
    _rule("Sync: Pendiente",                           DOMAIN_SYNC, "Message", r"\bpendiente\b",                                             True),
    _rule("Sync: En curso",                            DOMAIN_SYNC, "Message", r"\ben curso\b",                                              True),
    _rule("Sync: Completado",                          DOMAIN_SYNC, "Message", r"\bcompletado\b",                                            True),
    _rule("Sync: Error",                               DOMAIN_SYNC, "Message", r"\berror\b",                                                 True),
    _rule("Sync: Lista 'Sincronizaciones' no encontrada",   DOMAIN_SYNC, "Message", r"lista\s*['\"]sincronizaciones['\"]\s*no encontrada",   True),
    _rule("Sync: Error al consultar la lista 'Sincronizaciones'", DOMAIN_SYNC, "Message", r"error al consultar la lista\s*['\"]sincronizaciones['\"]", True),
    _rule("Sync: Error al desmarcar 'Activo'",         DOMAIN_SYNC, "Message", r"error al desmarcar\s*['\"]activo['\"]",                    True),
    _rule("Sync: La lista '{...}' no existe",          DOMAIN_SYNC, "Message", r"la lista\s*['\"][^'\"]+['\"]\s*no existe",                  True),
    _rule("Sync: Lista '{...}' no encontrada",         DOMAIN_SYNC, "Message", r"lista\s*['\"][^'\"]+['\"]\s*no encontrada",                 True),
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
