import logging
import os
import sys
import traceback
from logging.handlers import RotatingFileHandler
from typing import Optional

from core.config import OWNER_ID
from core.notifier import notify_owner as send_private_message

LOG_DIR = "/app/logs"
LOG_FILE = os.path.join(LOG_DIR, "rekku.log")

os.makedirs(LOG_DIR, exist_ok=True)

LEVELS = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "WARN": logging.WARNING,
    "ERROR": logging.ERROR,
}

LOGGING_LEVEL = os.getenv("LOGGING_LEVEL", "ERROR").upper()

logger = logging.getLogger("rekku")
logger.setLevel(LEVELS.get(LOGGING_LEVEL, logging.ERROR))
logger.propagate = False

if not logger.handlers:
    formatter = logging.Formatter(
        "[%(asctime)s.%(msecs)03d] [%(levelname)s] [%(funcName)s] %(message)s",
        "%Y-%m-%d %H:%M:%S",
    )
    file_handler = RotatingFileHandler(LOG_FILE, maxBytes=1_000_000, backupCount=3)
    file_handler.setFormatter(formatter)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)


def log(level: str, message: str, exc: Optional[Exception] = None) -> None:
    """Central logging entry point."""
    level = level.upper()
    if exc:
        message = f"{message}\n{''.join(traceback.format_exception(exc))}"
    log_level = LEVELS.get(level, logging.INFO)
    logger.log(log_level, message, stacklevel=2)
    if level == "ERROR":
        try:
            send_private_message(OWNER_ID, f"[ERROR] {message}")
        except Exception as e:  # pragma: no cover
            logger.error("Failed to send owner notification: %s", e, stacklevel=2)


def log_debug(msg: str) -> None:
    log("DEBUG", msg)


def log_info(msg: str) -> None:
    log("INFO", msg)


def log_warning(msg: str) -> None:
    log("WARNING", msg)


def log_error(msg: str, exc: Optional[Exception] = None) -> None:
    log("ERROR", msg, exc)
