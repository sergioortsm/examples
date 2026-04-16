from __future__ import annotations

import json
import os
import smtplib
import sys
from datetime import date, timedelta
from email.message import EmailMessage
from pathlib import Path

import requests

_imports_cargados = False

try:
    # Ejecucion como modulo del paquete.
    from .attendance_bot import AttendanceBot
    from .auth import AuthManager
    from .config import cargar_configuracion
    from .logger import configurar_logger
    _imports_cargados = True
except ImportError:
    pass

if not _imports_cargados:
    try:
        # Compatibilidad para ejecutable PyInstaller (modulos planos en bundle).
        from attendance_bot import AttendanceBot
        from auth import AuthManager
        from config import cargar_configuracion
        from logger import configurar_logger
        _imports_cargados = True
    except ImportError:
        pass

if not _imports_cargados:
    # Ejecutado como script desde raiz: forzamos imports calificados.
    repo_root = Path(__file__).resolve().parents[2]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    from personio_fichajes.src.attendance_bot import AttendanceBot
    from personio_fichajes.src.auth import AuthManager
    from personio_fichajes.src.config import cargar_configuracion
    from personio_fichajes.src.logger import configurar_logger


def _es_terminal_interactiva() -> bool:
    try:
        return bool(sys.stdin.isatty() and sys.stdout.isatty())
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Stamp file: registro persistente de dias imputados correctamente
# ---------------------------------------------------------------------------

def _ruta_stamp() -> Path:
    """Devuelve la ruta absoluta al fichero de stamp, independiente del CWD."""
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).resolve().parent
    else:
        base = Path(__file__).resolve().parents[1]
    return base / "runtime" / "fichajes_realizados.json"


def _cargar_stamp() -> dict[str, str]:
    ruta = _ruta_stamp()
    if ruta.exists():
        try:
            return json.loads(ruta.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _guardar_en_stamp(fecha: date) -> None:
    from datetime import datetime
    ruta = _ruta_stamp()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    stamp = _cargar_stamp()
    stamp[fecha.isoformat()] = datetime.now().isoformat(timespec="seconds")
    ruta.write_text(json.dumps(stamp, indent=2, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------------------
# Utilidades de calendario
# ---------------------------------------------------------------------------

def _dias_laborables_pasados(n: int) -> list[date]:
    """Devuelve los ultimos n dias laborables (Lun-Vie) anteriores a hoy, en orden cronologico."""
    resultado: list[date] = []
    cursor = date.today() - timedelta(days=1)
    while len(resultado) < n:
        if cursor.weekday() < 5:  # 0=Lun … 4=Vie
            resultado.append(cursor)
        cursor -= timedelta(days=1)
    return list(reversed(resultado))


# ---------------------------------------------------------------------------
# Notificacion por email (opcional)
# ---------------------------------------------------------------------------

def _enviar_alerta_email(cfg, dias_fallidos: list[date], logger) -> None:
    if not (cfg.smtp_host and cfg.smtp_user and cfg.smtp_password and cfg.email_destinatario):
        return
    try:
        msg = EmailMessage()
        msg["Subject"] = "Personio: dias sin imputar tras catch-up"
        msg["From"] = cfg.smtp_user
        msg["To"] = cfg.email_destinatario
        cuerpo = "Los siguientes dias no pudieron imputarse automaticamente:\n\n"
        cuerpo += "\n".join(f"  - {d.isoformat()}" for d in dias_fallidos)
        cuerpo += "\n\nRevisa los logs y lanza el bot manualmente si es necesario."
        msg.set_content(cuerpo)
        with smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=30) as smtp:
            smtp.starttls()
            smtp.login(cfg.smtp_user, cfg.smtp_password)
            smtp.send_message(msg)
        logger.info(f"Alerta por email enviada a {cfg.email_destinatario}.")
    except Exception as exc:
        logger.warning(f"No se pudo enviar alerta por email: {exc}")


def _confirmar_imputacion_manual(solo_fecha: date, logger, modo_interactivo: bool = True) -> bool:
    motivo_omision = None
    
    if not modo_interactivo:
        motivo_omision = "modo_interactivo=false en configuracion"
    elif not _es_terminal_interactiva():
        motivo_omision = "entorno no interactivo (tarea programada/servicio)"

    if motivo_omision is not None:
        logger.info(f"Confirmacion omitida: {motivo_omision}.")
        return True

    while True:
        try:
            respuesta = input(
                f"\n¿Confirmas lanzar la imputacion para {solo_fecha.isoformat()}? [S/N]: "
            ).strip().lower()
        except (EOFError, KeyboardInterrupt):
            logger.info("Ejecucion cancelada por el usuario antes de iniciar el bot.")
            return False

        if respuesta == "s":
            return True
        if respuesta == "n":
            return False

        print("Respuesta no valida. Escribe S para continuar o N para cancelar.")


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
    logger.info(f"Modo fecha unica activo: SOLO_FECHA={solo_fecha.isoformat()}")

    if not _confirmar_imputacion_manual(solo_fecha, logger, cfg.modo_interactivo):
        logger.info("Ejecucion cancelada por el usuario. No se realizara ninguna imputacion.")
        return

    session = requests.Session()
    auth = AuthManager(cfg, logger)
    auth.ensure_authenticated(session)
    logger.info("Sesion autenticada y lista.")

    attendance_url = f"{cfg.base_url}/attendance/employee/{cfg.employee_id}?hideEmployeeHeader=true"
    driver, conectado_a_existente = auth.navegar_con_sesion(session, attendance_url)

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

    _guardar_en_stamp(solo_fecha)
    logger.info(f"Fichaje de {solo_fecha.isoformat()} registrado en stamp file.")


def ejecutar_catch_up():
    """Detecta dias laborables recientes sin imputar y los rellena automaticamente."""
    cfg = cargar_configuracion()
    logger = configurar_logger(cfg.ruta_log)
    logger.info("Modo catch-up iniciado.")

    stamp = _cargar_stamp()
    dias_candidatos = _dias_laborables_pasados(cfg.catch_up_dias)
    dias_pendientes = [d for d in dias_candidatos if d.isoformat() not in stamp]

    if not dias_pendientes:
        logger.info("Catch-up: todos los dias laborables recientes estan en el stamp. Nada que hacer.")
        return

    logger.info(
        f"Catch-up: {len(dias_pendientes)} dia(s) sin confirmar en stamp: "
        + ", ".join(d.isoformat() for d in dias_pendientes)
    )

    dias_fallidos: list[date] = []
    for dia in dias_pendientes:
        logger.info(f"Catch-up: procesando {dia.isoformat()}...")
        try:
            os.environ["SOLO_FECHA"] = dia.isoformat()
            ejecutar_fichaje_diario()
        except Exception as exc:
            logger.error(f"Catch-up: fallo al imputar {dia.isoformat()}: {exc}")
            dias_fallidos.append(dia)
        finally:
            os.environ.pop("SOLO_FECHA", None)

    if dias_fallidos:
        logger.warning(
            f"Catch-up finalizado con {len(dias_fallidos)} dia(s) fallido(s): "
            + ", ".join(d.isoformat() for d in dias_fallidos)
        )
        _enviar_alerta_email(cfg, dias_fallidos, logger)
    else:
        logger.info("Catch-up completado: todos los dias procesados correctamente.")


def main():
    modo_catch_up = os.getenv("MODO_CATCH_UP", "").strip().lower() in ("1", "true", "yes")
    if modo_catch_up:
        try:
            ejecutar_catch_up()
        except Exception as exc:
            logger = configurar_logger(None)
            logger.exception(f"Error en catch-up Personio: {exc}")
            sys.exit(1)
    else:
        try:
            ejecutar_fichaje_diario()
        except Exception as exc:
            logger = configurar_logger(None)
            logger.exception(f"Error en servicio Personio: {exc}")
            sys.exit(1)


if __name__ == "__main__":
    main()
