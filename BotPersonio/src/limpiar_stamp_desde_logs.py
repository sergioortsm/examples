from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

_TS_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) \|")
_OK_RE = re.compile(r"Fichaje de (\d{4}-\d{2}-\d{2}) registrado en stamp file\.")
_FAIL_RE_LIST = [
    re.compile(r"Fin de intento sin guardado confirmado.*fecha_visible=(\d{4}-\d{2}-\d{2})"),
    re.compile(r"No se registro en stamp (\d{4}-\d{2}-\d{2}) porque no hubo guardado confirmado\."),
    re.compile(r"Catch-up: (\d{4}-\d{2}-\d{2}) no quedo confirmado"),
    re.compile(r"Catch-up: fallo al imputar (\d{4}-\d{2}-\d{2})"),
]


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def _runtime_dir() -> Path:
    return _base_dir() / "runtime"


def _stamp_path() -> Path:
    return _runtime_dir() / "fichajes_realizados.json"


def _log_paths() -> list[Path]:
    runtime = _runtime_dir()
    candidatos = [
        runtime / "personio_fichajes.log",
        runtime / "tarea_programada.log",
        runtime / "catch_up.log",
    ]
    existentes = [p for p in candidatos if p.exists()]
    return sorted(existentes, key=lambda p: (p.stat().st_mtime, p.name))


def _parse_ts(linea: str) -> datetime | None:
    m = _TS_RE.match(linea)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def _event_key(ts: datetime | None, secuencia: int) -> tuple[int, datetime, int]:
    if ts is None:
        return (0, datetime.min, secuencia)
    return (1, ts, secuencia)


def _scan_status_from_logs(log_paths: list[Path]) -> dict[str, tuple[str, tuple[int, datetime, int], str]]:
    # date -> (status, key, log_name)
    estado: dict[str, tuple[str, tuple[int, datetime, int], str]] = {}
    secuencia = 0

    for log_path in log_paths:
        try:
            with log_path.open("r", encoding="utf-8", errors="replace") as fh:
                for linea in fh:
                    secuencia += 1
                    ts = _parse_ts(linea)
                    key = _event_key(ts, secuencia)

                    m_ok = _OK_RE.search(linea)
                    if m_ok:
                        fecha = m_ok.group(1)
                        previo = estado.get(fecha)
                        if previo is None or key >= previo[1]:
                            estado[fecha] = ("ok", key, log_path.name)
                        continue

                    for patron_fallo in _FAIL_RE_LIST:
                        m_fail = patron_fallo.search(linea)
                        if not m_fail:
                            continue
                        fecha = m_fail.group(1)
                        previo = estado.get(fecha)
                        if previo is None or key >= previo[1]:
                            estado[fecha] = ("fail", key, log_path.name)
                        break
        except OSError as exc:
            print(f"[WARNING] No se pudo leer {log_path}: {exc}")

    return estado


def _load_stamp(stamp_path: Path) -> dict[str, str]:
    if not stamp_path.exists():
        return {}
    try:
        return json.loads(stamp_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeError(f"Stamp invalido en {stamp_path}: {exc}") from exc


def _save_stamp(stamp_path: Path, data: dict[str, str]) -> None:
    stamp_path.parent.mkdir(parents=True, exist_ok=True)
    stamp_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def limpiar_stamp_desde_logs() -> int:
    stamp_path = _stamp_path()
    stamp = _load_stamp(stamp_path)
    if not stamp:
        print(f"[INFO] Stamp vacio o inexistente: {stamp_path}")
        return 0

    logs = _log_paths()
    if not logs:
        print(f"[WARNING] No hay logs para analizar en {_runtime_dir()}")
        return 1

    estado = _scan_status_from_logs(logs)
    fechas_a_borrar = [
        fecha
        for fecha in stamp.keys()
        if fecha in estado and estado[fecha][0] == "fail"
    ]

    if not fechas_a_borrar:
        print("[INFO] No hay fechas en stamp con ultimo estado de fallo en logs.")
        return 0

    nuevo_stamp = {k: v for k, v in stamp.items() if k not in set(fechas_a_borrar)}
    _save_stamp(stamp_path, nuevo_stamp)

    print("[INFO] Fechas eliminadas del stamp por fallo confirmado en logs:")
    for fecha in fechas_a_borrar:
        _, _, log_name = estado[fecha]
        print(f"  - {fecha} (ultimo evento en {log_name})")
    print(f"[INFO] Stamp actualizado: {stamp_path}")
    return 0


def main() -> None:
    raise SystemExit(limpiar_stamp_desde_logs())


if __name__ == "__main__":
    main()
