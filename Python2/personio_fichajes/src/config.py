import json
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, ValidationError, field_validator


_HHMM_PATTERN = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class Configuracion(BaseModel):
    employee_id: int
    timezone: str = "Europe/Madrid"
    base_url: str = "https://unikaltech.app.personio.com"

    morning_start: str = "08:30"
    morning_end: str = "14:30"
    afternoon_start: str = "15:30"
    afternoon_end: str = "18:00"
    friday_start: str = "09:00"
    friday_end: str = "15:00"

    headless: bool = False
    modo_prueba: bool = False  #Modo prueba: no realiza cambios en Personio, solo simula el proceso y muestra logs.
    modo_interactivo: bool = True

    request_timeout_sec: int = 30
    login_timeout_sec: int = 360
    max_retries: int = 3

    catch_up_dias: int = 7  #Dias a cubrir en modo catch-up (si no se ha ejecutado el bot en varios dias, para imputar los dias anteriores automaticamente).

    ruta_log: str | None = None
    sesion_cookies_path: str = "session_cookies.json"
    remote_debug_port: int | None = None
    chrome_user_data_dir: str | None = None
    chrome_profile_directory: str | None = None

    # Notificacion por email al finalizar catch-up con dias fallidos (opcional).
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    email_destinatario: str | None = None

    @field_validator(
        "morning_start",
        "morning_end",
        "afternoon_start",
        "afternoon_end",
        "friday_start",
        "friday_end",
    )
    @classmethod
    def validar_hora(cls, value: str) -> str:
        if not _HHMM_PATTERN.match(value):
            raise ValueError(f"Hora invalida: {value}")
        return value

    @field_validator("base_url")
    @classmethod
    def normalizar_base_url(cls, value: str) -> str:
        return value.rstrip("/")


def _base_path() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def obtener_ruta_config(nombre_archivo: str = "configuracion.json") -> Path:
    ruta_config_env = os.getenv("RUTA_CONFIG")
    if ruta_config_env:
        ruta = Path(ruta_config_env)
        if ruta.suffix.lower() == ".json":
            return ruta
        return ruta / nombre_archivo

    base = _base_path()
    candidatos = [
        base / "dist" / nombre_archivo,
        base / nombre_archivo,
    ]
    for candidato in candidatos:
        if candidato.exists():
            return candidato

    return candidatos[0]


def cargar_configuracion() -> Configuracion:
    load_dotenv(_base_path() / ".env")

    ruta = obtener_ruta_config()
    if not ruta.exists():
        raise RuntimeError(f"No se encontro archivo de configuracion: {ruta}")

    with ruta.open("r", encoding="utf-8") as f:
        data = json.load(f)

    try:
        return Configuracion(**data)
    except ValidationError as exc:
        raise RuntimeError(f"Configuracion invalida en {ruta}: {exc}") from exc


def obtener_directorio_runtime() -> Path:
    base = _base_path()
    runtime = base / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    return runtime
