from __future__ import annotations

import asyncio
import logging
import os
import sys
import threading
import time
import __main__
from contextlib import contextmanager
from logging.handlers import RotatingFileHandler
from pathlib import Path


_LOGGER_NAME = "trolli"
_LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s:%(lineno)d] %(message)s"

PERF_ENABLED = os.getenv("TROLLI_PERF", "0").strip() in {"1", "true", "TRUE", "yes"}
_perf_logger = logging.getLogger("trolli.perf")


@contextmanager
def perf_timer(label: str, min_ms: float = 0.0, **extra):
    """Context manager para medir y loguear duracion de bloques.

    Solo emite si TROLLI_PERF esta activo y la duracion supera ``min_ms``.
    """
    if not PERF_ENABLED:
        yield
        return
    t0 = time.perf_counter()
    try:
        yield
    finally:
        ms = (time.perf_counter() - t0) * 1000.0
        if ms >= min_ms:
            if extra:
                extra_str = " ".join(f"{k}={v}" for k, v in extra.items())
                _perf_logger.info("[PERF] %s ms=%.2f %s", label, ms, extra_str)
            else:
                _perf_logger.info("[PERF] %s ms=%.2f", label, ms)


def _resolve_log_level() -> int:
    level_name = os.getenv("TROLLI_LOG_LEVEL", "INFO").strip().upper()
    return getattr(logging, level_name, logging.INFO)


def _resolve_default_log_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent

    main_file = getattr(__main__, "__file__", "")
    if main_file:
        return Path(main_file).resolve().parent

    argv0 = (sys.argv[0] or "").strip()
    if argv0 and argv0 != "-c":
        return Path(argv0).resolve().parent

    return Path.cwd()


def resolve_app_data_dir() -> Path:
    """Directorio base para artefactos de la app (logs, preferencias, etc.).

    Usa la misma politica que el fichero de log: respeta TROLLI_LOG_DIR si esta
    definido y, en caso contrario, cae en el directorio del script/exe.
    """
    log_dir_env = os.getenv("TROLLI_LOG_DIR", "").strip()
    if log_dir_env:
        app_dir = Path(log_dir_env)
    else:
        app_dir = _resolve_default_log_dir()
    app_dir.mkdir(parents=True, exist_ok=True)
    return app_dir


def _resolve_log_path() -> Path:
    return resolve_app_data_dir() / "trolli.log"


def setup_logging() -> logging.Logger:
    logger = logging.getLogger(_LOGGER_NAME)
    if logger.handlers:
        return logger

    logger.setLevel(_resolve_log_level())
    logger.propagate = False

    formatter = logging.Formatter(_LOG_FORMAT)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    file_handler = RotatingFileHandler(
        _resolve_log_path(),
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    logger.info("Logging inicializado")
    return logger


def install_asyncio_exception_handler(logger: logging.Logger, loop: asyncio.AbstractEventLoop | None = None):
    try:
        target_loop = loop or asyncio.get_running_loop()
    except RuntimeError:
        return

    def _handle_async_exception(_loop: asyncio.AbstractEventLoop, context: dict):
        exc = context.get("exception")
        message = context.get("message", "Unhandled asyncio exception")
        if exc:
            logger.error("%s", message, exc_info=(type(exc), exc, exc.__traceback__))
        else:
            logger.error("%s | context=%s", message, context)

    target_loop.set_exception_handler(_handle_async_exception)


def install_global_exception_hooks(logger: logging.Logger):
    previous_excepthook = sys.excepthook

    def _sys_excepthook(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            previous_excepthook(exc_type, exc_value, exc_traceback)
            return
        logger.critical("Unhandled exception", exc_info=(exc_type, exc_value, exc_traceback))

    sys.excepthook = _sys_excepthook

    if hasattr(threading, "excepthook"):
        previous_threading_hook = threading.excepthook

        def _threading_excepthook(args: threading.ExceptHookArgs):
            logger.critical(
                "Unhandled threading exception in %s",
                getattr(args.thread, "name", "unknown"),
                exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
            )
            previous_threading_hook(args)

        threading.excepthook = _threading_excepthook
