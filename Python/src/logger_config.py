import logging
from logging.handlers import RotatingFileHandler
import os

from config import RUTA_LOG

def getLogger(nombre_logger="fichajes", archivo_log="fichajes.log"):
    logger = logging.getLogger(nombre_logger)
    logger.setLevel(logging.INFO)

    # Evitar handlers duplicados si ya se configuró
    if not logger.handlers:
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

        # Handler para consola
        consola_handler = logging.StreamHandler()
        consola_handler.setLevel(logging.INFO)
        consola_handler.setFormatter(formatter)
        logger.addHandler(consola_handler)

        # Handler para archivo (mismo directorio del script principal)
        ruta_log = os.path.join(RUTA_LOG, archivo_log)
        archivo_handler = RotatingFileHandler(ruta_log, maxBytes=1_000_000, backupCount=5, encoding='utf-8')
        archivo_handler.setLevel(logging.INFO)
        archivo_handler.setFormatter(formatter)
        logger.addHandler(archivo_handler)

    return logger
