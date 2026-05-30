from __future__ import annotations

import asyncio
import logging
import os
import sys
import threading
import __main__
from logging.handlers import RotatingFileHandler
from pathlib import Path


_LOGGER_NAME = "trolli"
_LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s:%(lineno)d] %(message)s"


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


def _resolve_log_path() -> Path:
    log_dir_env = os.getenv("TROLLI_LOG_DIR", "").strip()
    if log_dir_env:
        log_dir = Path(log_dir_env)
    else:
        log_dir = _resolve_default_log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / "trolli.log"


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
