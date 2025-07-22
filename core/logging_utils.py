import logging
import os
import sys
import traceback
from logging.handlers import RotatingFileHandler
from typing import Optional

_logger: Optional[logging.Logger] = None
_LOG_DIR = "/config/logs"
_LOG_FILE = os.path.join(_LOG_DIR, "rekku.log")
_LEVELS = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "WARN": logging.WARNING,
    "ERROR": logging.ERROR,
}


def setup_logging() -> logging.Logger:
    """Initialize the logger once and return it."""
    global _logger
    if _logger:
        return _logger

    os.makedirs(_LOG_DIR, exist_ok=True)

    level = os.getenv("LOGGING_LEVEL", "ERROR").upper()
    logger = logging.getLogger("rekku")
    logger.setLevel(_LEVELS.get(level, logging.ERROR))
    logger.propagate = False

    if not logger.handlers:
        formatter = logging.Formatter(
            "[%(asctime)s] [%(levelname)s] [%(filename)s:%(lineno)d] %(message)s",
            "%Y-%m-%d %H:%M:%S",
        )
        fh = RotatingFileHandler(_LOG_FILE, maxBytes=1_000_000, backupCount=3)
        fh.setFormatter(formatter)
        ch = logging.StreamHandler(sys.stdout)
        ch.setFormatter(formatter)
        logger.addHandler(fh)
        logger.addHandler(ch)

    _logger = logger
    return logger


def _notify_owner(message: str) -> None:
    """Send a message to the owner if possible."""
    try:
        from core.notifier import notify_owner
        notify_owner(message)
    except Exception as e:  # pragma: no cover - notification best effort
        logger = setup_logging()
        logger.error("Failed to notify owner: %s", e, stacklevel=2)


def _log(level: str, message: str, exc: Optional[Exception] = None) -> None:
    logger = setup_logging()
    level = level.upper()
    if exc is not None:
        message = f"{message}\n{''.join(traceback.format_exception(exc))}".rstrip()
    logger.log(_LEVELS.get(level, logging.INFO), message, stacklevel=3)
    if level == "ERROR":
        _notify_owner(f"[ERROR] {message}")


def log_debug(msg: str) -> None:
    _log("DEBUG", msg)


def log_info(msg: str) -> None:
    _log("INFO", msg)


def log_warning(msg: str) -> None:
    _log("WARNING", msg)


def log_error(msg: str, exc: Optional[Exception] = None) -> None:
    _log("ERROR", msg, exc)
