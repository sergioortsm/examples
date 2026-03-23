import sys
from pathlib import Path

from loguru import logger


def configurar_logger(ruta_log: str | None = None):
    logger.remove()

    logger.add(
        sys.stdout,
        level="INFO",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
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
