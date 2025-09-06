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

# Flood-control / de-duplication state (initialized once at module load)
_last_notify_times = deque(maxlen=100)
_last_notify_messages = {}  # chat_id -> (last_time, message)
_NOTIFY_CAP_PER_SEC = 5
_NOTIFY_IDENTICAL_BLOCK_SEC = 300  # 5 minutes


def _default_notify(chat_id: int, message: str):
    """Fallback when no real notifier is configured: queue the message."""
    log_info(f"[NOTIFY:{chat_id}] {message}")
    # Queue pending so real notifier can flush later
    if (chat_id, message) not in _pending:
        _pending.append((chat_id, message))


_notify_impl: Callable[[int, str], None] = _default_notify


def _maybe_call_notify_fn(fn: Callable[[int, str], None], chat_id: int, chunk: str):
    """Call notifier function which may be sync or return a coroutine.

    Schedule coroutine results appropriately depending on whether an event
    loop is already running.
    """
    try:
        result = fn(chat_id, chunk)
        # If the notifier returned a coroutine, schedule or run it
        if asyncio.iscoroutine(result):
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None
            if loop and loop.is_running():
                loop.create_task(result)
            else:
                # Running outside of an event loop: run synchronously
                asyncio.run(result)
    except Exception as e:  # pragma: no cover - best effort
        log_warning(f"[notifier] Notifier function raised while sending: {repr(e)}")


def set_notifier(fn: Callable[[int, str], None]):
    """Register the real notifier and flush any queued messages.

    The notifier can be a synchronous function or an async function that
    returns a coroutine; both are supported.
    """
    global _notify_impl
    _notify_impl = fn
    # Flush pending messages safely
    for chat_id, msg in list(_pending):
        try:
            _maybe_call_notify_fn(fn, chat_id, msg)
        except Exception as e:
            log_warning(f"[notifier] Failed to send pending message: {repr(e)}")
    _pending.clear()


CHUNK_SIZE = 4000


def notify(chat_id: int, message: str):
    """Send ``message`` to ``chat_id`` in chunks to avoid Telegram limits.

    Rate-limits and deduplicates messages across calls.
    """
    global _in_notify

    if _in_notify:
        log_warning("[notifier] Recursive notify call detected; skipping")
        return

    # Flood control: non inviare più di X notify al secondo
    now = time.time()
    recent = [t for t in _last_notify_times if now - t < 1]
    if len(recent) >= _NOTIFY_CAP_PER_SEC:
        log_warning(f"[notifier] Flood control: troppe notify in 1 secondo, bloccata: {message}")
        return

    # Blocca messaggi identici per N secondi
    last_time, last_msg = _last_notify_messages.get(chat_id, (0, None))
    if last_msg == message and now - last_time < _NOTIFY_IDENTICAL_BLOCK_SEC:
        log_info(f"[notifier] Messaggio identico già inviato <{_NOTIFY_IDENTICAL_BLOCK_SEC}s, bloccato: {message}")
        return

    # Record this send
    _last_notify_times.append(now)
    _last_notify_messages[chat_id] = (now, message)

    _in_notify = True
    try:
        log_debug(f"[notifier] Sending message to {chat_id}: {message}")
        for i in range(0, len(message or ""), CHUNK_SIZE):
            chunk = message[i : i + CHUNK_SIZE]
            try:
                # Use helper that supports async notifier functions
                _maybe_call_notify_fn(_notify_impl, chat_id, chunk)
            except Exception as e:  # pragma: no cover - best effort
                log_warning(f"[notifier] Failed to send notification chunk: {repr(e)}")
    finally:
        _in_notify = False


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
            entry = (interface_name, trainer_id, message)
            if entry not in _pending_interface_msgs:
                _pending_interface_msgs.append(entry)
            continue

        targets: list[int] = []
        if interface_name == "telegram_bot":
            targets.append(trainer_id)
            log_chat_id = get_log_chat_id_sync()
            if log_chat_id and log_chat_id not in targets:
                targets.append(log_chat_id)
        elif interface_name == "discord_bot":
            targets.append(trainer_id)
        else:
            targets.append(trainer_id)

        if not targets:
            continue

        async def send(target: int):
            try:
                await iface.send_message({"text": message, "target": target})
            except Exception as e:  # pragma: no cover - best effort
                # Check if interpreter is shutting down
                if "interpreter shutdown" in str(e) or "cannot schedule new futures" in str(e):
                    log_debug(f"[notifier] Notification failed due to interpreter shutdown, skipping: {repr(e)}")
                else:
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

