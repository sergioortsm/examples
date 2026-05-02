from __future__ import annotations

import importlib
import json
import os
import smtplib
import sys
from datetime import date, timedelta
from email.message import EmailMessage
from pathlib import Path

import requests

def _cargar_dependencias():
    try:
        # Ejecucion como modulo del paquete.
        attendance_mod = importlib.import_module(".attendance_bot", package=__package__)
        auth_mod = importlib.import_module(".auth", package=__package__)
        config_mod = importlib.import_module(".config", package=__package__)
        logger_mod = importlib.import_module(".logger", package=__package__)
        return (
            attendance_mod.AttendanceBot,
            auth_mod.AuthManager,
            config_mod.cargar_configuracion,
            logger_mod.configurar_logger,
        )
    except Exception:
        pass

    try:
        # Compatibilidad para ejecutable PyInstaller (modulos planos en bundle).
        attendance_mod = importlib.import_module("attendance_bot")
        auth_mod = importlib.import_module("auth")
        config_mod = importlib.import_module("config")
        logger_mod = importlib.import_module("logger")
        return (
            attendance_mod.AttendanceBot,
            auth_mod.AuthManager,
            config_mod.cargar_configuracion,
            logger_mod.configurar_logger,
        )
    except Exception:
        pass

    # Ejecutado como script desde raiz: forzamos imports calificados.
    repo_root = Path(__file__).resolve().parents[2]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    attendance_mod = importlib.import_module("personio_fichajes.src.attendance_bot")
    auth_mod = importlib.import_module("personio_fichajes.src.auth")
    config_mod = importlib.import_module("personio_fichajes.src.config")
    logger_mod = importlib.import_module("personio_fichajes.src.logger")
    return (
        attendance_mod.AttendanceBot,
        auth_mod.AuthManager,
        config_mod.cargar_configuracion,
        logger_mod.configurar_logger,
    )


AttendanceBot, AuthManager, cargar_configuracion, configurar_logger = _cargar_dependencias()


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


def _es_festivo(fecha: date, cfg) -> bool:
    """Devuelve True si la fecha esta en la lista de festivos de la configuracion."""
    return fecha.isoformat() in set(cfg.festivos)


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


def _ruta_log_file(cfg) -> Path:
    """Devuelve la ruta del archivo de log activo (misma logica que configurar_logger)."""
    if cfg.ruta_log:
        ruta = Path(cfg.ruta_log)
        if ruta.is_dir():
            return ruta / "personio_fichajes.log"
        return ruta
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).resolve().parent
    else:
        base = Path(__file__).resolve().parents[1]
    return base / "runtime" / "personio_fichajes.log"


def _leer_log_desde(ruta: Path, offset: int) -> str:
    """Lee el archivo de log desde el byte indicado hasta el final. Devuelve cadena vacia si falla."""
    try:
        with ruta.open("rb") as f:
            f.seek(offset)
            return f.read().decode("utf-8", errors="replace")
    except Exception:
        return ""


def _enviar_resumen_email(cfg, asunto: str, cuerpo_resumen: str, log_contenido: str, logger) -> None:
    if not (cfg.smtp_host and cfg.smtp_user and cfg.smtp_password and cfg.email_destinatario):
        return
    try:
        msg = EmailMessage()
        msg["Subject"] = f"[Personio] {asunto}"
        msg["From"] = cfg.smtp_user
        msg["To"] = cfg.email_destinatario
        cuerpo = cuerpo_resumen
        if log_contenido:
            cuerpo += "\n\n--- LOG ---\n" + log_contenido
        msg.set_content(cuerpo)
        with smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=30) as smtp:
            smtp.starttls()
            smtp.login(cfg.smtp_user, cfg.smtp_password)
            smtp.send_message(msg)
        logger.info(f"Resumen por email enviado a {cfg.email_destinatario}.")
    except Exception as exc:
        logger.warning(f"No se pudo enviar resumen por email: {exc}")


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


def _obtener_solo_fecha_obligatoria() -> date:
    solo_fecha_raw = os.getenv("SOLO_FECHA", "").strip()
    if not solo_fecha_raw:
        raise ValueError(
            "SOLO_FECHA es obligatoria. Formato esperado: YYYY-MM-DD. "
            "Ejemplo: SOLO_FECHA=2026-03-22"
        )

    try:
        return date.fromisoformat(solo_fecha_raw)
    except ValueError as exc:
        raise ValueError(
            f"SOLO_FECHA invalida: '{solo_fecha_raw}'. Formato esperado: YYYY-MM-DD"
        ) from exc


def _cerrar_driver(driver, conectado_a_existente: bool) -> None:
    if conectado_a_existente:
        # Cerrar solo la pestaña abierta por el bot, sin tocar el resto de Chrome.
        try:
            driver.close()
        except Exception:
            pass
        return
    driver.quit()


def ejecutar_fichaje_diario(*, _enviar_resumen: bool = True) -> bool:
    cfg = cargar_configuracion()
    logger = configurar_logger(cfg.ruta_log)

    solo_fecha = _obtener_solo_fecha_obligatoria()

    log_offset: int = 0
    if cfg.email_resumen and _enviar_resumen:
        try:
            log_offset = _ruta_log_file(cfg).stat().st_size
        except Exception:
            log_offset = 0

    logger.info("Iniciando servicio de fichajes Personio...")
    logger.info(f"Modo fecha unica activo: SOLO_FECHA={solo_fecha.isoformat()}")

    ok = False
    asunto_estado = "FALLIDO"
    cuerpo_resumen = (
        f"El fichaje del {solo_fecha.isoformat()} NO quedo confirmado.\n"
        "Revisa los logs y lanza el bot manualmente si es necesario."
    )

    if _es_festivo(solo_fecha, cfg):
        logger.info(
            f"{solo_fecha.isoformat()} es festivo segun configuracion. "
            "No se realiza fichaje. Se marca en stamp para evitar reintentos."
        )
        _guardar_en_stamp(solo_fecha)
        ok = True
        asunto_estado = "OK"
        cuerpo_resumen = (
            f"{solo_fecha.isoformat()} es festivo segun configuracion. "
            "No se realizo fichaje y se registro en stamp."
        )
    elif not _confirmar_imputacion_manual(solo_fecha, logger, cfg.modo_interactivo):
        logger.info("Ejecucion cancelada por el usuario. No se realizara ninguna imputacion.")
        ok = False
        asunto_estado = "CANCELADO"
        cuerpo_resumen = (
            f"Ejecucion cancelada por el usuario para {solo_fecha.isoformat()}. "
            "No se realizo ninguna imputacion."
        )
    else:
        session = requests.Session()
        auth = AuthManager(cfg, logger)
        auth.ensure_authenticated(session)
        logger.info("Sesion autenticada y lista.")

        attendance_url = f"{cfg.base_url}/attendance/employee/{cfg.employee_id}?hideEmployeeHeader=true"
        driver, conectado_a_existente = auth.navegar_con_sesion(session, attendance_url)

        try:
            bot = AttendanceBot(driver, cfg, logger)
            ok = bot.rellenar_semana(solo_fecha=solo_fecha)
        finally:
            _cerrar_driver(driver, conectado_a_existente)

        if ok:
            _guardar_en_stamp(solo_fecha)
            logger.info(f"Fichaje de {solo_fecha.isoformat()} registrado en stamp file.")
            asunto_estado = "OK"
            cuerpo_resumen = f"Fichaje del {solo_fecha.isoformat()} registrado correctamente."
        else:
            logger.warning(
                f"No se registro en stamp {solo_fecha.isoformat()} porque no hubo guardado confirmado."
            )

    if cfg.email_resumen and _enviar_resumen:
        log_texto = _leer_log_desde(_ruta_log_file(cfg), log_offset)
        _enviar_resumen_email(
            cfg,
            f"Resumen {solo_fecha.isoformat()} — {asunto_estado}",
            cuerpo_resumen,
            log_texto,
            logger,
        )
    return ok


def ejecutar_catch_up() -> bool:
    """Detecta dias laborables recientes sin imputar y los rellena automaticamente."""
    cfg = cargar_configuracion()
    logger = configurar_logger(cfg.ruta_log)
    logger.info("Modo catch-up iniciado.")

    log_offset: int = 0
    if cfg.email_resumen:
        try:
            log_offset = _ruta_log_file(cfg).stat().st_size
        except Exception:
            log_offset = 0

    stamp = _cargar_stamp()
    dias_candidatos = _dias_laborables_pasados(cfg.catch_up_dias)
    dias_pendientes = [
        d for d in dias_candidatos
        if d.isoformat() not in stamp and not _es_festivo(d, cfg)
    ]

    if not dias_pendientes:
        logger.info("Catch-up: todos los dias laborables recientes estan en el stamp. Nada que hacer.")
        if cfg.email_resumen:
            log_texto = _leer_log_desde(_ruta_log_file(cfg), log_offset)
            _enviar_resumen_email(
                cfg,
                "Catch-up — Sin pendientes",
                "Todos los dias laborables recientes ya estaban en el stamp. No se realizo ninguna imputacion.",
                log_texto,
                logger,
            )
        return True

    logger.info(
        f"Catch-up: {len(dias_pendientes)} dia(s) sin confirmar en stamp: "
        + ", ".join(d.isoformat() for d in dias_pendientes)
    )

    dias_fallidos: list[date] = []
    for dia in dias_pendientes:
        logger.info(f"Catch-up: procesando {dia.isoformat()}...")
        try:
            os.environ["SOLO_FECHA"] = dia.isoformat()
            ok = ejecutar_fichaje_diario(_enviar_resumen=False)
            if not ok:
                logger.warning(
                    f"Catch-up: {dia.isoformat()} no quedo confirmado (sin excepcion)."
                )
                dias_fallidos.append(dia)
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
        if cfg.email_resumen:
            log_texto = _leer_log_desde(_ruta_log_file(cfg), log_offset)
            cuerpo = (
                f"Catch-up finalizado con {len(dias_fallidos)} dia(s) fallido(s):\n\n"
                + "\n".join(f"  - {d.isoformat()}" for d in dias_fallidos)
                + "\n\nRevisa los logs y lanza el bot manualmente si es necesario."
            )
            _enviar_resumen_email(
                cfg,
                f"Catch-up — {len(dias_fallidos)} dia(s) FALLIDO(s)",
                cuerpo,
                log_texto,
                logger,
            )
        else:
            _enviar_alerta_email(cfg, dias_fallidos, logger)
        return False
    else:
        logger.info("Catch-up completado: todos los dias procesados correctamente.")
        if cfg.email_resumen:
            log_texto = _leer_log_desde(_ruta_log_file(cfg), log_offset)
            procesados = len(dias_pendientes)
            cuerpo = (
                f"Catch-up completado: {procesados} dia(s) imputado(s) correctamente.\n\n"
                + "\n".join(f"  - {d.isoformat()}" for d in dias_pendientes)
            )
            _enviar_resumen_email(
                cfg,
                f"Catch-up — {procesados} dia(s) OK",
                cuerpo,
                log_texto,
                logger,
            )
        return True


def main():
    modo_catch_up = os.getenv("MODO_CATCH_UP", "").strip().lower() in ("1", "true", "yes")
    accion = ejecutar_catch_up if modo_catch_up else ejecutar_fichaje_diario
    msg_no_ok = (
        "Catch-up finalizado con dias no confirmados"
        if modo_catch_up
        else "Imputacion no confirmada; no se registro en stamp"
    )
    contexto_error = "catch-up" if modo_catch_up else "servicio"

    try:
        ok = accion()
        if not ok:
            raise RuntimeError(msg_no_ok)
    except Exception as exc:
        logger = configurar_logger(None)
        logger.exception(f"Error en {contexto_error} Personio: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
