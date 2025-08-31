# core/notifier.py

import asyncio
import time
from typing import List, Tuple, Callable
from core.logging_utils import log_debug, log_info, log_warning
from core.config import get_log_chat_id_sync
from collections import deque

_in_notify = False

_pending: List[Tuple[int, str]] = []
# Messages targeting interfaces that are not yet registered
_pending_interface_msgs: List[Tuple[str, int, str]] = []

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
            log_warning(f"[notifier] Failed to send pending message: {repr(e)}")
    _pending.clear()

CHUNK_SIZE = 4000

def notify(chat_id: int, message: str):
    global _last_notify_times, _last_notify_messages
    _last_notify_times = deque(maxlen=100)
    _last_notify_messages = {}
    _NOTIFY_CAP_PER_SEC = 5
    _NOTIFY_IDENTICAL_BLOCK_SEC = 300  # 5 minuti

    """Send ``message`` to ``chat_id`` in chunks to avoid Telegram limits."""
    global _in_notify
    if _in_notify:
        log_warning("[notifier] Recursive notify call detected; skipping")
        return
    _in_notify = True
    try:
        log_debug(f"[notifier] Sending message to {chat_id}: {message}")
        for i in range(0, len(message or ""), CHUNK_SIZE):
            chunk = message[i : i + CHUNK_SIZE]
            try:
                _notify_impl(chat_id, chunk)
            except Exception as e:  # pragma: no cover - best effort
                log_warning(
                    f"[notifier] Failed to send notification chunk: {repr(e)}"
                )
    finally:
        _in_notify = False
    now = time.time()
    # Flood control: non inviare più di X notify al secondo
    _last_notify_times.append(now)
    recent = [t for t in _last_notify_times if now - t < 1]
    if len(recent) > _NOTIFY_CAP_PER_SEC:
        log_warning(f"[notifier] Flood control: troppe notify in 1 secondo, bloccata: {message}")
        return
    # Blocca messaggi identici per 5 minuti
    last_time, last_msg = _last_notify_messages.get(chat_id, (0, None))
    if last_msg == message and now - last_time < _NOTIFY_IDENTICAL_BLOCK_SEC:
        log_info(f"[notifier] Messaggio identico già inviato <5min, bloccato: {message}")
        return
    _last_notify_messages[chat_id] = (now, message)

def notify_trainer(message: str) -> None:
    """Notify the trainer via selected interfaces."""
    from core.config import NOTIFY_ERRORS_TO_INTERFACES
    from core.core_initializer import INTERFACE_REGISTRY

    if not NOTIFY_ERRORS_TO_INTERFACES:
        log_debug("[notifier] No interfaces configured for error notifications")
        return

    for interface_name, trainer_id in NOTIFY_ERRORS_TO_INTERFACES.items():
        iface = INTERFACE_REGISTRY.get(interface_name)
        if not iface:
            available = ", ".join(sorted(INTERFACE_REGISTRY)) or "none"
            log_warning(
                f"[notifier] No interface '{interface_name}' available. "
                f"Available: {available}; queuing notification"
            )
            _pending_interface_msgs.append((interface_name, trainer_id, message))
            continue

        targets = [trainer_id]
        if interface_name == "telegram_bot":
            log_chat_id = get_log_chat_id_sync()
            if log_chat_id and log_chat_id not in targets:
                targets.append(log_chat_id)

        async def send(target: int):
            try:
                await iface.send_message({"text": message, "target": target})
            except Exception as e:  # pragma: no cover - best effort
                log_warning(
                    f"[notifier] Failed to notify via {interface_name}: {repr(e)}",
                )

        for tgt in targets:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None
            if loop and loop.is_running():
                loop.create_task(send(tgt))
            else:
                asyncio.run(send(tgt))


def flush_pending_for_interface(interface_name: str) -> None:
    """Flush queued trainer notifications for a newly registered interface."""
    from core.core_initializer import INTERFACE_REGISTRY

    iface = INTERFACE_REGISTRY.get(interface_name)
    if not iface:
        return

    remaining: List[Tuple[str, int, str]] = []
    for name, trainer_id, msg in _pending_interface_msgs:
        if name != interface_name:
            remaining.append((name, trainer_id, msg))
            continue

        async def send():
            try:
                await iface.send_message({"text": msg, "target": trainer_id})
            except Exception as e:  # pragma: no cover - best effort
                log_warning(
                    f"[notifier] Failed to flush pending notify via {interface_name}: {repr(e)}",
                )

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop and loop.is_running():
            loop.create_task(send())
        else:
            asyncio.run(send())

    _pending_interface_msgs[:] = remaining

