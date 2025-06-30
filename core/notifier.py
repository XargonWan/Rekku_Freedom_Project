# core/notifier.py

from core.config import OWNER_ID
from typing import Callable

_notify_impl: Callable[[int, str], None] = lambda chat_id, msg: print(f"[NOTIFY:{chat_id}] {msg}")

def set_notifier(fn: Callable[[int, str], None]):
    global _notify_impl
    _notify_impl = fn

def notify(chat_id: int, message: str):
    print(f"[DEBUG/notifier] Inviando messaggio a {chat_id}: {message}")
    _notify_impl(chat_id, message)

def notify_owner(message: str):
    print(f"[DEBUG/notifier] Notifica per OWNER_ID={OWNER_ID}: {message}")
    notify(OWNER_ID, message)
