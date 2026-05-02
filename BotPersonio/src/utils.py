from __future__ import annotations

import random
from datetime import date
from typing import Any


def parse_hhmm(hhmm: str) -> tuple[str, str]:
    horas, minutos = hhmm.split(":")
    return horas, minutos


def hora_a_minutos(hora: tuple[str, str]) -> int:
    return int(hora[0]) * 60 + int(hora[1])


def minutos_a_hora(total_minutos: int) -> tuple[str, str]:
    minutos_dia = 24 * 60
    normalizado = max(0, min(total_minutos, minutos_dia - 1))
    horas = normalizado // 60
    minutos = normalizado % 60
    return f"{horas:02d}", f"{minutos:02d}"


def sumar_minutos_hora(hora: tuple[str, str], delta_minutos: int) -> tuple[str, str]:
    return minutos_a_hora(hora_a_minutos(hora) + delta_minutos)


def max_desfase_minutos(cfg: Any) -> int:
    try:
        valor = int(getattr(cfg, "desfase_horario_max_min", 10))
    except Exception:
        valor = 10
    return max(0, min(valor, 10))


def rng_para_dia(cfg: Any, nombre_norm: str, fecha: date | None) -> random.Random:
    semilla = f"{getattr(cfg, 'employee_id', 'na')}|{fecha.isoformat() if fecha else nombre_norm}"
    return random.Random(semilla)


def aplicar_desfase_horario(
    cfg: Any,
    logger: Any,
    horario: list[dict[str, Any]],
    nombre_norm: str,
    fecha: date | None,
) -> list[dict[str, Any]]:
    max_desfase = max_desfase_minutos(cfg)
    if max_desfase == 0:
        return horario

    rng = rng_para_dia(cfg, nombre_norm, fecha)

    if nombre_norm == "vie" or len(horario) == 1:
        inicio_base = horario[0]["inicio"]
        fin_base = horario[0]["fin"]

        delta_inicio = rng.randint(-max_desfase, max_desfase)
        delta_fin = rng.randint(0, max_desfase)

        inicio = sumar_minutos_hora(inicio_base, delta_inicio)
        fin = sumar_minutos_hora(fin_base, delta_fin)

        fin_min = max(
            hora_a_minutos(fin),
            hora_a_minutos(fin_base),
            hora_a_minutos(inicio) + 1,
        )
        fin = minutos_a_hora(fin_min)

        logger.info(
            "Desfase aplicado "
            f"({fecha.isoformat() if fecha else nombre_norm}): inicio {delta_inicio:+d}m, fin +{delta_fin}m"
        )
        return [{"tipo": "trabajo", "inicio": inicio, "fin": fin}]

    inicio_manana_base = horario[0]["inicio"]
    fin_manana_base = horario[0]["fin"]
    inicio_tarde_base = horario[2]["inicio"]
    fin_tarde_base = horario[2]["fin"]

    delta_inicio_manana = rng.randint(-max_desfase, max_desfase)
    delta_fin_manana = rng.randint(0, max_desfase)
    delta_inicio_tarde = rng.randint(-max_desfase, max_desfase)
    delta_fin_tarde = rng.randint(0, max_desfase)

    inicio_manana = sumar_minutos_hora(inicio_manana_base, delta_inicio_manana)
    fin_manana = sumar_minutos_hora(fin_manana_base, delta_fin_manana)

    inicio_tarde_candidato = sumar_minutos_hora(inicio_tarde_base, delta_inicio_tarde)
    inicio_tarde_min = max(
        hora_a_minutos(inicio_tarde_candidato),
        hora_a_minutos(fin_manana),
    )
    inicio_tarde = minutos_a_hora(inicio_tarde_min)

    fin_tarde = sumar_minutos_hora(fin_tarde_base, delta_fin_tarde)
    fin_tarde_min = max(
        hora_a_minutos(fin_tarde),
        hora_a_minutos(fin_tarde_base),
        hora_a_minutos(inicio_tarde) + 1,
    )
    fin_tarde = minutos_a_hora(fin_tarde_min)

    logger.info(
        "Desfase aplicado "
        f"({fecha.isoformat() if fecha else nombre_norm}): "
        f"inicio manana {delta_inicio_manana:+d}m, fin manana +{delta_fin_manana}m, "
        f"inicio tarde {delta_inicio_tarde:+d}m, fin tarde +{delta_fin_tarde}m"
    )

    return [
        {"tipo": "trabajo", "inicio": inicio_manana, "fin": fin_manana},
        {"tipo": "descanso", "inicio": fin_manana, "fin": inicio_tarde},
        {"tipo": "trabajo", "inicio": inicio_tarde, "fin": fin_tarde},
    ]