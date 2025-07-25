import asyncio
import time
from collections import deque
from datetime import datetime

from core.config import OWNER_ID
from core import plugin_instance, rate_limit, recent_chats
from core.logging_utils import log_debug, log_error, log_warning

# Use a deque for priority insertion
_queue: deque = deque()
_condition = asyncio.Condition()
_lock = asyncio.Lock()


async def _delayed_put(item: dict, delay: float) -> None:
    await asyncio.sleep(delay)
    async with _condition:
        _queue.append(item)
        _condition.notify()


async def enqueue(bot, message, context_memory, priority: bool = False) -> None:
    """Enqueue a message for serialized processing with rate limiting.
    
    Args:
        bot: The bot instance
        message: The message to process
        context_memory: Message context
        priority: If True, message is added to front of queue (for events)
    """
    plugin = plugin_instance.get_plugin()
    if not plugin:
        log_error("[QUEUE] No active plugin")
        return

    try:
        max_messages, window_seconds, owner_fraction = plugin.get_rate_limit()
    except Exception as e:  # pragma: no cover - plugin may misbehave
        log_error(f"[QUEUE] Error obtaining rate limit: {repr(e)}", e)
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
            "priority": priority,
        }
        asyncio.create_task(_delayed_put(item, delay))
        return

    meta = message.chat.title or message.chat.username or message.chat.first_name
    recent_chats.track_chat(chat_id, meta)

    item = {
        "bot": bot,
        "message": message,
        "chat_id": chat_id,
        "timestamp": time.time(),
        "context": context_memory,
        "priority": priority,
    }

    async with _condition:
        if priority:
            # Events go to the front of the queue
            _queue.appendleft(item)
            log_debug(f"[QUEUE] High-priority message enqueued from chat {chat_id} by user {user_id}")
        else:
            _queue.append(item)
            log_debug(f"[QUEUE] Regular message enqueued from chat {chat_id} by user {user_id}")
        _condition.notify()


async def compact_similar_messages(first: dict) -> list:
    """Merge up to 4 additional queued messages from the same chat."""
    batch = [first]
    chat_id = first["chat_id"]
    ts = first["timestamp"]
    candidates = []
    
    # Convert deque to list for iteration and removal
    queue_items = list(_queue)
    for item in queue_items:
        if len(batch) >= 5:
            break
        if item["chat_id"] == chat_id and item["timestamp"] - ts <= 600:
            candidates.append(item)

    for item in candidates:
        _queue.remove(item)
        batch.append(item)

    batch.sort(key=lambda x: x["timestamp"])

    if len(batch) > 1:
        log_debug(f"[COMPACT] Compacted {len(batch)} messages from chat {chat_id}")

    return batch


async def start_queue_loop() -> None:
    """Continuously process queued messages one at a time."""
    while True:
        async with _condition:
            while not _queue:
                await _condition.wait()
            item = _queue.popleft()

        async with _lock:
            batch = await compact_similar_messages(item)
            final = batch[-1]

            plugin = plugin_instance.get_plugin()
            if not plugin:
                log_error("[QUEUE] No active plugin when dispatching")
                continue

            try:
                max_messages, window_seconds, owner_fraction = plugin.get_rate_limit()
            except Exception as e:  # pragma: no cover - plugin may misbehave
                log_error(f"[QUEUE] Error obtaining rate limit: {repr(e)}", e)
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
                continue

            try:
                # Check if this is an event prompt
                if "event_prompt" in final:
                    # For events, we need to use the LLM plugin directly with the structured prompt
                    plugin = plugin_instance.get_plugin()
                    if plugin and hasattr(plugin, 'handle_incoming_message'):
                        # Create a mock message for event processing
                        from types import SimpleNamespace
                        event_message = SimpleNamespace(
                            message_id=f"event_{final['event_prompt']['input']['event_id']}",
                            chat_id="SYSTEM_SCHEDULER",
                            text="Scheduled event: " + str(final['event_prompt']['input']['payload']['description']),
                            from_user=SimpleNamespace(
                                id=-1,
                                full_name="Rekku Scheduler",
                                username="rekku_scheduler"
                            ),
                            date=datetime.utcnow(),
                            reply_to_message=None,
                            chat=SimpleNamespace(
                                id="SYSTEM_SCHEDULER",
                                type="private",
                                title="System Scheduler"
                            ),
                            message_thread_id=None
                        )
                        await plugin.handle_incoming_message(
                            final["bot"], event_message, final["event_prompt"]
                        )
                    else:
                        log_error("[QUEUE] No LLM plugin available or doesn't support handle_incoming_message")
                else:
                    await plugin_instance.handle_incoming_message(
                        final["bot"], final["message"], final["context"]
                    )
            except Exception as e:  # pragma: no cover - plugin may misbehave
                log_error(
                    f"[ERROR] Failed to process message from chat {final['chat_id']}: {e}",
                    e,
                )


async def enqueue_event(bot, prompt_data) -> None:
    """Enqueue an event prompt with highest priority."""
    # Debug log to verify the payload content
    log_debug(f"[QUEUE] Verifying event payload: {prompt_data}")

    # Check required fields in the payload - adjust for the actual structure
    payload = prompt_data.get("input", {}).get("payload", {})
    if not payload.get("description"):
        log_error("[QUEUE] Invalid event payload: missing 'description' in input.payload")
        return

    async with _condition:
        item = {
            "bot": bot,
            "message": None,  # Events don't have actual messages
            "chat_id": "TARDIS/system/events",
            "timestamp": time.time(),
            "context": {},
            "priority": True,
            "event_prompt": prompt_data,  # Special event data
        }

        # Check to avoid duplicates in the queue
        for queued_item in _queue:
            if queued_item.get("event_prompt") == prompt_data:
                log_warning("[QUEUE] Duplicate event detected, not added to the queue")
                return

        # Add the event to the queue
        # Events always go to the front
        _queue.appendleft(item)
        log_debug(f"[QUEUE] Event added to the queue with priority: {prompt_data}")
        log_debug(f"[QUEUE] Current queue state: {list(_queue)}")
        _condition.notify()