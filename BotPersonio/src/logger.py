import sys
from pathlib import Path

from loguru import logger


def configurar_logger(ruta_log: str | None = None):
    logger.remove()

    # Colores solo en consola interactiva para evitar codigos ANSI en pipelines/logs.
    consola_interactiva = bool(getattr(sys.stdout, "isatty", lambda: False)())

    logger.level("INFO", color="<green>")
    logger.level("WARNING", color="<yellow>")
    logger.level("ERROR", color="<red>")
    logger.level("CRITICAL", color="<RED><bold>")

    logger.add(
        sys.stdout,
        level="INFO",
        colorize=consola_interactiva,
        format="<cyan>{time:YYYY-MM-DD HH:mm:ss}</cyan> | <level>{level}</level> | <level>{message}</level>",
    )

    if ruta_log:
        ruta_archivo = Path(ruta_log)
        if ruta_archivo.is_dir():
            ruta_archivo = ruta_archivo / "personio_fichajes.log"
    else:
        ruta_archivo = Path(__file__).resolve().parents[1] / "runtime" / "personio_fichajes.log"

    ruta_archivo.parent.mkdir(parents=True, exist_ok=True)

    logger.add(
        str(ruta_archivo),
        rotation="5 MB",
        retention=5,
        encoding="utf-8",
        level="INFO",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
    )

    return logger
