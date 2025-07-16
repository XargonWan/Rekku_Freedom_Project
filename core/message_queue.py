import asyncio
import time

from core.config import OWNER_ID
from core import plugin_instance, rate_limit, recent_chats
from core.logging_utils import log_debug, log_error

_queue: asyncio.Queue = asyncio.Queue()
_lock = asyncio.Lock()


async def _delayed_put(item: dict, delay: float) -> None:
    await asyncio.sleep(delay)
    await _queue.put(item)


async def enqueue(bot, message, context_memory) -> None:
    """Enqueue a message for serialized processing with rate limiting."""
    plugin = plugin_instance.get_plugin()
    if not plugin:
        log_error("[QUEUE] No active plugin")
        return

    try:
        max_messages, window_seconds, owner_fraction = plugin.get_rate_limit()
    except Exception as e:  # pragma: no cover - plugin may misbehave
        log_error(f"[QUEUE] Error obtaining rate limit: {e}", e)
        max_messages, window_seconds, owner_fraction = float("inf"), 1, 1.0

    user_id = message.from_user.id if message.from_user else 0
    chat_id = message.chat_id
    llm_name = plugin.__class__.__module__.split(".")[-1]

    if (
        user_id != OWNER_ID
        and not rate_limit.is_allowed(
            llm_name, user_id, max_messages, window_seconds, owner_fraction, consume=False
        )
    ):
        delay = 300
        log_debug(f"[RATE LIMIT] Delaying user {user_id} by {delay} seconds (quota exceeded)")
        item = {
            "bot": bot,
            "message": message,
            "chat_id": chat_id,
            "timestamp": time.time(),
            "context": context_memory,
        }
        asyncio.create_task(_delayed_put(item, delay))
        return

    meta = message.chat.title or message.chat.username or message.chat.first_name
    recent_chats.track_chat(chat_id, meta)

    await _queue.put(
        {
            "bot": bot,
            "message": message,
            "chat_id": chat_id,
            "timestamp": time.time(),
            "context": context_memory,
        }
    )
    log_debug(f"[QUEUE] Enqueued message from chat {chat_id} by user {user_id}")


async def compact_similar_messages(first: dict) -> list:
    """Merge up to 4 additional queued messages from the same chat."""
    batch = [first]
    chat_id = first["chat_id"]
    ts = first["timestamp"]
    candidates = []
    for item in list(_queue._queue):
        if len(batch) >= 5:
            break
        if item["chat_id"] == chat_id and item["timestamp"] - ts <= 600:
            candidates.append(item)

    for item in candidates:
        _queue._queue.remove(item)
        batch.append(item)

    batch.sort(key=lambda x: x["timestamp"])

    if len(batch) > 1:
        log_debug(f"[COMPACT] Compacted {len(batch)} messages from chat {chat_id}")

    return batch


async def start_queue_loop() -> None:
    """Continuously process queued messages one at a time."""
    while True:
        item = await _queue.get()

        async with _lock:
            batch = await compact_similar_messages(item)
            final = batch[-1]

            plugin = plugin_instance.get_plugin()
            if not plugin:
                log_error("[QUEUE] No active plugin when dispatching")
                for _ in batch:
                    _queue.task_done()
                continue

            try:
                max_messages, window_seconds, owner_fraction = plugin.get_rate_limit()
            except Exception as e:  # pragma: no cover - plugin may misbehave
                log_error(f"[QUEUE] Error obtaining rate limit: {e}", e)
                max_messages, window_seconds, owner_fraction = float("inf"), 1, 1.0

            user_id = final["message"].from_user.id if final["message"].from_user else 0
            llm_name = plugin.__class__.__module__.split(".")[-1]

            if (
                user_id != OWNER_ID
                and not rate_limit.is_allowed(
                    llm_name, user_id, max_messages, window_seconds, owner_fraction, consume=True
                )
            ):
                delay = 300
                log_debug(
                    f"[RATE LIMIT] Delaying user {user_id} by {delay} seconds (quota exceeded)"
                )
                asyncio.create_task(_delayed_put(final, delay))
                for _ in batch:
                    _queue.task_done()
                continue

            try:
                await plugin_instance.handle_incoming_message(
                    final["bot"], final["message"], final["context"]
                )
            except Exception as e:  # pragma: no cover - plugin may misbehave
                log_error(
                    f"[ERROR] Failed to process message from chat {final['chat_id']}: {e}",
                    e,
                )

            for _ in batch:
                _queue.task_done()
