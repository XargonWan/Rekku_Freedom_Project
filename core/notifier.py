# core/notifier.py

from core.config import TRAINER_ID
from typing import Callable, List, Tuple
from core.logging_utils import log_debug, log_info, log_warning, log_error

_pending: List[Tuple[int, str]] = []

def _default_notify(chat_id: int, message: str):
    """Fallback when no real notifier is configured."""
    log_info(f"[NOTIFY:{chat_id}] {message}")
    _pending.append((chat_id, message))

_notify_impl: Callable[[int, str], None] = _default_notify

def set_notifier(fn: Callable[[int, str], None]):
    """Register the real notifier and flush any queued messages."""
    global _notify_impl
    _notify_impl = fn
    for chat_id, msg in list(_pending):
        try:
            fn(chat_id, msg)
        except Exception as e:
            log_error(f"[notifier] Failed to send pending message: {repr(e)}")
    _pending.clear()

CHUNK_SIZE = 4000

def notify(chat_id: int, message: str):
    """Send ``message`` to ``chat_id`` in chunks to avoid Telegram limits."""
    log_debug(f"[notifier] Sending message to {chat_id}: {message}")
    for i in range(0, len(message or ""), CHUNK_SIZE):
        chunk = message[i : i + CHUNK_SIZE]
        try:
            _notify_impl(chat_id, chunk)
        except Exception as e:  # pragma: no cover - best effort
            log_error(f"[notifier] Failed to send notification chunk: {repr(e)}")

def notify_trainer(message: str):
    log_debug(f"[notifier] Notification for TRAINER_ID={TRAINER_ID}: {message}")
    notify(TRAINER_ID, message)
