from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path

import requests

try:
    from .attendance_bot import AttendanceBot
    from .auth import AuthManager
    from .config import cargar_configuracion
    from .logger import configurar_logger
except ImportError:
    try:
        # Compatibilidad para ejecutable PyInstaller (modulos planos en bundle).
        from attendance_bot import AttendanceBot
        from auth import AuthManager
        from config import cargar_configuracion
        from logger import configurar_logger
    except ImportError:
        # Ejecutado como script desde raiz: forzamos imports calificados.
        repo_root = Path(__file__).resolve().parents[2]
        if str(repo_root) not in sys.path:
            sys.path.insert(0, str(repo_root))

        from personio_fichajes.src.attendance_bot import AttendanceBot
        from personio_fichajes.src.auth import AuthManager
        from personio_fichajes.src.config import cargar_configuracion
        from personio_fichajes.src.logger import configurar_logger


def ejecutar_fichaje_diario():
    cfg = cargar_configuracion()
    logger = configurar_logger(cfg.ruta_log)

    solo_fecha_raw = os.getenv("SOLO_FECHA", "").strip()
    if not solo_fecha_raw:
        raise ValueError(
            "SOLO_FECHA es obligatoria. Formato esperado: YYYY-MM-DD. "
            "Ejemplo: SOLO_FECHA=2026-03-22"
        )

    try:
        solo_fecha = date.fromisoformat(solo_fecha_raw)
    except ValueError as exc:
        raise ValueError(
            f"SOLO_FECHA invalida: '{solo_fecha_raw}'. Formato esperado: YYYY-MM-DD"
        ) from exc

    logger.info("Iniciando servicio de fichajes Personio...")

    session = requests.Session()
    auth = AuthManager(cfg, logger)
    auth.ensure_authenticated(session)
    logger.info("Sesion autenticada y lista.")

    attendance_url = f"{cfg.base_url}/attendance/employee/{cfg.employee_id}?hideEmployeeHeader=true"
    driver, conectado_a_existente = auth.navegar_con_sesion(session, attendance_url)

    logger.info(f"Modo fecha unica activo: SOLO_FECHA={solo_fecha.isoformat()}")

    try:
        bot = AttendanceBot(driver, cfg, logger)
        bot.rellenar_semana(solo_fecha=solo_fecha)
    finally:
        if conectado_a_existente:
            # Cerrar solo la pestaña abierta por el bot, sin tocar el resto de Chrome.
            try:
                driver.close()
            except Exception:
                pass
        else:
            driver.quit()


def main():
    try:
        ejecutar_fichaje_diario()
    except Exception as exc:
        logger = configurar_logger(None)
        logger.exception(f"Error en servicio Personio: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
