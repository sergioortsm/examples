from datetime import date, timedelta
import sys
from pathlib import Path
from typing import Any

try:
    from .config import Configuracion
except ImportError:
    # Ejecutado como script: forzamos raiz del repo para imports calificados.
    repo_root = Path(__file__).resolve().parents[2]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    from personio_fichajes.src.config import Configuracion


def obtener_rango_semanal(fecha: date) -> tuple[date, date]:
    inicio = fecha - timedelta(days=fecha.weekday())
    fin = inicio + timedelta(days=6)
    return inicio, fin


def _normalizar_fecha(value: Any) -> str | None:
    if not value:
        return None
    text = str(value)
    # Soporta "YYYY-MM-DD" y variantes con hora/zona.
    return text[:10]


def _iterar_dias_timesheet(timesheet: dict[str, Any]) -> list[dict[str, Any]]:
    candidatos = [
        timesheet.get("timecards"),
        timesheet.get("days"),
        timesheet.get("attendance_days"),
    ]

    for candidato in candidatos:
        if isinstance(candidato, list):
            return [d for d in candidato if isinstance(d, dict)]

        if isinstance(candidato, dict):
            # Algunos BFF devuelven diccionario indexado por fecha.
            valores = [v for v in candidato.values() if isinstance(v, dict)]
            if valores:
                return valores

    return []


def buscar_timecard_de_fecha(timesheet: dict[str, Any], fecha: date) -> dict[str, Any] | None:
    fecha_str = fecha.isoformat()
    for day in _iterar_dias_timesheet(timesheet):
        fecha_day = _normalizar_fecha(day.get("date") or day.get("day") or day.get("day_date"))
        if fecha_day == fecha_str:
            return day
    return None


def obtener_day_id(dia: dict[str, Any] | None) -> str | None:
    if not dia:
        return None

    def _normalizar_id(value: Any) -> str | None:
        if value is None:
            return None

        if isinstance(value, bool):
            return None

        if isinstance(value, (int, float)):
            return str(value)

        if isinstance(value, str):
            text = value.strip()
            return text or None

        if isinstance(value, dict):
            for key in ("value", "id", "uuid", "attendance_day_id", "day_id"):
                nested = _normalizar_id(value.get(key))
                if nested is not None:
                    return nested

        if isinstance(value, list):
            for item in value:
                nested = _normalizar_id(item)
                if nested is not None:
                    return nested

        return None

    def _buscar_id_en_estructura(node: Any, depth: int = 0) -> str | None:
        if depth > 4:
            return None

        if isinstance(node, dict):
            for key in posibles_claves:
                if key in node:
                    normalized = _normalizar_id(node.get(key))
                    if normalized is not None:
                        return normalized

            for value in node.values():
                nested = _buscar_id_en_estructura(value, depth + 1)
                if nested is not None:
                    return nested

        if isinstance(node, list):
            for item in node:
                nested = _buscar_id_en_estructura(item, depth + 1)
                if nested is not None:
                    return nested

        return None

    posibles_claves = ["day_id", "attendance_day_id", "id", "attendance_day_uuid"]
    for key in posibles_claves:
        normalized = _normalizar_id(dia.get(key))
        if normalized is not None:
            return normalized

    attendance_day = dia.get("attendance_day")
    if isinstance(attendance_day, dict):
        for key in ("id", "day_id", "attendance_day_id"):
            normalized = _normalizar_id(attendance_day.get(key))
            if normalized is not None:
                return normalized

    return _buscar_id_en_estructura(dia)


def es_fin_de_semana(fecha: date) -> bool:
    return fecha.weekday() >= 5


def dia_tiene_periodos(dia: dict[str, Any] | None) -> bool:
    if not dia:
        return False
    return bool(dia.get("periods"))


def debe_saltar_dia(fecha: date, dia: dict[str, Any] | None) -> tuple[bool, str]:
    if es_fin_de_semana(fecha):
        return True, "Fin de semana"

    if dia is None:
        return True, "No existe informacion del dia en el timesheet"

    if dia.get("is_off_day"):
        return True, "Dia marcado como off day por Personio"

    return False, ""


def _combinar_fecha_hora(fecha: date, hhmm: str, separador: str = "T") -> str:
    return f"{fecha.isoformat()}{separador}{hhmm}:00"


def _extraer_periodos_desde_working_schedule(fecha: date, dia: dict[str, Any]) -> list[dict[str, Any]]:
    schedule = dia.get("working_schedule")
    if not isinstance(schedule, dict):
        return []

    intervals = schedule.get("intervals")
    if not isinstance(intervals, list):
        return []

    periodos: list[dict[str, Any]] = []
    for interval in intervals:
        start = interval.get("start")
        end = interval.get("end")
        if not start or not end:
            continue

        # Soporta formatos "08:30" o "08:30:00".
        hhmm_start = start[:5]
        hhmm_end = end[:5]

        periodos.append(
            {
                "period_type": "work",
                "start": _combinar_fecha_hora(fecha, hhmm_start),
                "end": _combinar_fecha_hora(fecha, hhmm_end),
                "comment": None,
                "project_id": None,
                "auto_generated": False,
            }
        )

    return periodos


def _periodos_por_defecto(fecha: date, cfg: Configuracion) -> list[dict[str, Any]]:
    if fecha.weekday() == 4:
        return [
            {
                "period_type": "work",
                "start": _combinar_fecha_hora(fecha, cfg.friday_start),
                "end": _combinar_fecha_hora(fecha, cfg.friday_end),
                "comment": None,
                "project_id": None,
                "auto_generated": False,
            }
        ]

    return [
        {
            "period_type": "work",
            "start": _combinar_fecha_hora(fecha, cfg.morning_start),
            "end": _combinar_fecha_hora(fecha, cfg.morning_end),
            "comment": None,
            "project_id": None,
            "auto_generated": False,
        },
        {
            "period_type": "work",
            "start": _combinar_fecha_hora(fecha, cfg.afternoon_start),
            "end": _combinar_fecha_hora(fecha, cfg.afternoon_end),
            "comment": None,
            "project_id": None,
            "auto_generated": False,
        },
    ]


def construir_periodos_para_dia(fecha: date, dia: dict[str, Any] | None, cfg: Configuracion) -> list[dict[str, Any]]:
    if not dia:
        return _periodos_por_defecto(fecha, cfg)

    periodos_schedule = _extraer_periodos_desde_working_schedule(fecha, dia)
    if periodos_schedule:
        return periodos_schedule

    return _periodos_por_defecto(fecha, cfg)
