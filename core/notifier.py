# core/notifier.py

from core.config import OWNER_ID
from typing import Callable, List, Tuple

_pending: List[Tuple[int, str]] = []

def _default_notify(chat_id: int, message: str):
    """Fallback when no real notifier is configured."""
    print(f"[NOTIFY:{chat_id}] {message}")
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
            print(f"[ERROR/notifier] Failed to send pending message: {e}")
    _pending.clear()

def notify(chat_id: int, message: str):
    print(f"[DEBUG/notifier] Inviando messaggio a {chat_id}: {message}")
    _notify_impl(chat_id, message)

def notify_owner(message: str):
    print(f"[DEBUG/notifier] Notifica per OWNER_ID={OWNER_ID}: {message}")
    notify(OWNER_ID, message)
