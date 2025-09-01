import asyncio
import time
import queue as _thread_queue
from datetime import datetime
import traceback
from types import SimpleNamespace

from core.config import TELEGRAM_TRAINER_ID
from core import plugin_instance, rate_limit, recent_chats
from core.logging_utils import log_debug, log_error, log_warning, log_info
from core.mention_utils import is_message_for_bot

# Use a priority queue so events can be processed before regular messages
HIGH_PRIORITY = 0
NORMAL_PRIORITY = 1

_queue: asyncio.PriorityQueue = asyncio.PriorityQueue()
_lock = asyncio.Lock()
_consumer_task: asyncio.Task | None = None


class MessageQueue:
    """Minimal thread-safe queue for interfaces expecting blocking semantics."""

    def __init__(self):
        self._q = _thread_queue.Queue()

    def put(self, item):
        self._q.put(item)

    def get(self, timeout=None):
        return self._q.get(timeout=timeout)


async def _delayed_put(item: dict, delay: float) -> None:
    await asyncio.sleep(delay)
    priority = HIGH_PRIORITY if item.get("priority") else NORMAL_PRIORITY
    await _queue.put((priority, item))


async def enqueue(bot, message, context_memory, priority: bool = False) -> None:
    """Enqueue a message for serialized processing with rate limiting.

    Args:
        bot: The bot instance
        message: The message to process
        context_memory: Message context
        priority: If True, message is added to front of queue (for events)
    """
    human_count = getattr(message, "human_count", None)
    if human_count is None and hasattr(message, "chat"):
        human_count = getattr(message.chat, "human_count", None)

    directed, reason = await is_message_for_bot(
        message, bot, human_count=human_count
    )
    if not directed:
        if reason == "missing_human_count":
            log_debug(
                "[QUEUE] Message ignored: interface lacks participant count and no direct mention"
            )
        elif reason == "multiple_humans":
            log_debug(
                "[QUEUE] Message ignored: multiple humans in chat and no direct mention"
            )
        else:
            log_debug(f"[QUEUE] Message ignored: {reason or 'not directed to bot'}")
        return

    plugin = plugin_instance.get_plugin()
    if not plugin:
        log_error("[QUEUE] No active plugin")
        return

    try:
        max_messages, window_seconds, trainer_fraction = plugin.get_rate_limit()
    except Exception as e:  # pragma: no cover - plugin may misbehave
        log_error(f"[QUEUE] Error obtaining rate limit: {repr(e)}", e)
        max_messages, window_seconds, trainer_fraction = float("inf"), 1, 1.0

    user_id = message.from_user.id if message.from_user else 0
    chat_id = message.chat_id
    llm_name = plugin.__class__.__module__.split(".")[-1]

    if (
        user_id != TELEGRAM_TRAINER_ID
        and not rate_limit.is_allowed(
            llm_name, user_id, max_messages, window_seconds, trainer_fraction, consume=False
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
    await recent_chats.track_chat(chat_id, meta)

    thread_id = getattr(message, "message_thread_id", None)
    interface = bot.__class__.__name__ if bot else None

    item = {
        "bot": bot,
        "message": message,
        "chat_id": chat_id,
        "thread_id": thread_id,
        "interface": interface,
        "timestamp": time.time(),
        "context": context_memory,
        "priority": priority,
    }

    priority_val = HIGH_PRIORITY if priority else NORMAL_PRIORITY
    await _queue.put((priority_val, item))
    if priority:
        log_debug(
            f"[QUEUE] High-priority message enqueued from {interface} chat {chat_id}"
            f" thread {thread_id} by user {user_id}"
        )
    else:
        log_debug(
            f"[QUEUE] Regular message enqueued from {interface} chat {chat_id}"
            f" thread {thread_id} by user {user_id}"
        )


async def compact_similar_messages(first: dict, limit: int = 5) -> list:
    """Collect already-queued messages from same chat/thread/interface."""
    batch = [first]
    chat_id = first["chat_id"]
    thread_id = first.get("thread_id")
    interface = first.get("interface")
    ts = first["timestamp"]

    queue_items = list(_queue._queue)
    for prio, item in queue_items:
        if len(batch) >= limit:
            break
        if (
            item["chat_id"] == chat_id
            and item.get("thread_id") == thread_id
            and item.get("interface") == interface
            and item["timestamp"] - ts <= 600
        ):
            _queue._queue.remove((prio, item))
            batch.append(item)

    batch.sort(key=lambda x: x["timestamp"])

    if len(batch) > 1:
        log_debug(f"[COMPACT] Compacted {len(batch)} messages from chat {chat_id}")

    return batch


async def _consumer_loop() -> None:
    """Continuously process queued messages one at a time."""
    log_info("[QUEUE] Consumer loop started")
    while True:
        try:
            priority, item = await _queue.get()
            log_debug(
                f"[QUEUE] Dequeued message from chat {item.get('chat_id')} (priority={priority})"
            )

            async with _lock:
                batch = await compact_similar_messages(item)
                final = batch[0]
                if len(batch) > 1 and final.get("message"):
                    lines = []
                    for b in batch:
                        msg = b.get("message")
                        if not (msg and getattr(msg, "text", None)):
                            continue
                        user = getattr(msg, "from_user", None)
                        if user:
                            if getattr(user, "username", None):
                                name = f"@{user.username}"
                            elif getattr(user, "full_name", None):
                                name = user.full_name
                            else:
                                name = f"user_{getattr(user, 'id', 'unknown')}"
                            lines.append(f"{name}: {msg.text}")
                        else:
                            lines.append(msg.text)
                    base = final["message"]
                    merged = SimpleNamespace(
                        chat_id=getattr(base, "chat_id", None),
                        message_id=getattr(base, "message_id", None),
                        text="\n".join(lines),
                        from_user=SimpleNamespace(id=0, username="group", full_name="group"),
                        date=getattr(base, "date", datetime.utcnow()),
                        message_thread_id=getattr(base, "message_thread_id", None),
                        chat=getattr(base, "chat", None),
                        reply_to_message=getattr(base, "reply_to_message", None),
                    )
                    final["message"] = merged
                    final["context"] = batch[-1].get("context", final.get("context"))
                log_debug(
                    f"[QUEUE] Processing message from chat {final.get('chat_id')}"
                )

            plugin = plugin_instance.get_plugin()
            if not plugin:
                log_error("[QUEUE] No active plugin when dispatching")
                continue

            try:
                max_messages, window_seconds, trainer_fraction = plugin.get_rate_limit()
            except Exception as e:  # pragma: no cover - plugin may misbehave
                log_error(f"[QUEUE] Error obtaining rate limit: {repr(e)}", e)
                max_messages, window_seconds, trainer_fraction = float("inf"), 1, 1.0

            user_msg = final.get("message")
            user_id = (
                user_msg.from_user.id
                if user_msg is not None and getattr(user_msg, "from_user", None)
                else 0
            )
            llm_name = plugin.__class__.__module__.split(".")[-1]

            if (
                user_id != TELEGRAM_TRAINER_ID
                and not rate_limit.is_allowed(
                    llm_name, user_id, max_messages, window_seconds, trainer_fraction, consume=True
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
                    # Create a mock message object with event_id for events
                    mock_message = SimpleNamespace()
                    mock_message.event_id = final["context"].get("event_id")
                    mock_message.chat_id = "TARDIS/system/events"  
                    mock_message.message_id = f"event_{mock_message.event_id}"
                    
                    # Deliver the structured event prompt using the standard pipeline
                    await plugin_instance.handle_incoming_message(
                        final["bot"], mock_message, final["event_prompt"]
                    )
                else:
                    await plugin_instance.handle_incoming_message(
                        final["bot"], final["message"], final["context"]
                    )
            except Exception as e:  # pragma: no cover - plugin may misbehave
                log_error(
                    f"[ERROR] Failed to process message from chat {final['chat_id']}: {e}\n{traceback.format_exc()}",
                )
                bot = final.get("bot")
                chat_id = final.get("chat_id")
                thread_id = final.get("thread_id")
                try:
                    if bot and chat_id:
                        kwargs = {"chat_id": chat_id, "text": "😵‍💫"}
                        if thread_id:
                            kwargs["message_thread_id"] = thread_id
                        reply_msg = final.get("message")
                        reply_id = getattr(reply_msg, "message_id", None)
                        if reply_id:
                            kwargs["reply_to_message_id"] = reply_id
                        await bot.send_message(**kwargs)
                except Exception as send_err:  # pragma: no cover - best effort
                    log_warning(
                        f"[QUEUE] Failed to send fallback message: {send_err}"
                    )
            finally:
                for _ in batch:
                    _queue.task_done()
        except asyncio.CancelledError:
            log_info("[QUEUE] Consumer loop cancelled")
            break
        except Exception as e:
            log_error(
                f"[QUEUE] Unexpected error in consumer loop: {repr(e)}\n{traceback.format_exc()}"
            )


async def enqueue_event(bot, prompt_data, event_id: int = None) -> None:
    """Enqueue an event prompt with highest priority."""
    # Debug log to verify the payload content
    log_debug(f"[QUEUE] Verifying event payload: {prompt_data}")

    # Check required fields in the payload - adjust for the actual structure
    payload = prompt_data.get("input", {}).get("payload", {})
    if not payload.get("description"):
        log_error("[QUEUE] Invalid event payload: missing 'description' in input.payload")
        return

    item = {
        "bot": bot,
        "message": None,  # Events don't have actual messages
        "chat_id": "TARDIS/system/events",
        "thread_id": None,
        "interface": bot.__class__.__name__ if bot else None,
        "timestamp": time.time(),
        "context": {"event_id": event_id} if event_id else {},
        "priority": True,
        "event_prompt": prompt_data,  # Special event data
    }

    # Check to avoid duplicates in the queue
    for prio, queued_item in list(_queue._queue):
        if queued_item.get("event_prompt") == prompt_data:
            log_warning("[QUEUE] Duplicate event detected, not added to the queue")
            return

    await _queue.put((HIGH_PRIORITY, item))
    log_debug(f"[QUEUE] Event added to the queue with priority: {prompt_data}")
    log_debug(f"[QUEUE] Current queue state: {list(_queue._queue)}")


async def run() -> None:
    """Convenience wrapper to launch the consumer task if not running."""
    global _consumer_task

    if _consumer_task and not _consumer_task.done():
        log_debug("[QUEUE] Consumer already running")
        return

    _consumer_task = asyncio.create_task(_consumer_loop())
    log_info("[QUEUE] Consumer task started")

