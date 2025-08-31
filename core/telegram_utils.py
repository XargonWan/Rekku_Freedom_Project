from typing import Optional
import asyncio
from telegram.error import TimedOut
from core.config import TELEGRAM_TRAINER_ID
from core.logging_utils import (
    log_debug,
    log_info,
    log_warning,
    log_error,
    setup_logging,
)

# Maximum preview length for logging failed messages
max_message_preview_len = 100


def truncate_message(text: Optional[str], limit: int = 4000) -> str:
    """Return ``text`` truncated to fit within Telegram limits."""
    if not text:
        return text or ""
    if len(text) > limit:
        return text[:limit] + "\n... (truncated)"
    return text


async def _send_with_retry(
    bot,
    chat_id: int,
    text: str,
    retries: int = 5,
    delay: int = 3,
    **kwargs,
):
    """Send a single message with retry support."""
    if bot is None:
        log_error("[telegram_utils] _send_with_retry called with None bot")
        return None
    if chat_id is None or not isinstance(chat_id, int):
        log_error("[telegram_utils] Cannot send message: chat_id is invalid")
        return None
    
    # Filter kwargs to only include valid Telegram bot parameters
    # Remove custom parameters that are not supported by bot.send_message()
    valid_kwargs = {k: v for k, v in kwargs.items() if k not in ['event_id']}
    
    last_error = None
    logger = setup_logging()
    for attempt in range(1, retries + 1):
        try:
            return await bot.send_message(chat_id=chat_id, text=text, **valid_kwargs)
        except TimedOut as e:
            last_error = e
            if attempt < retries:
                print(f"[telegram retry] send_message timed out ({attempt}/{retries}), retrying...")
                await asyncio.sleep(delay)
            else:
                print(f"[telegram retry] send_message failed after {retries} retries: {e}")
        except Exception:
            raise
    trainer_id = TELEGRAM_TRAINER_ID
    if trainer_id:
        try:
            await bot.send_message(
                chat_id=trainer_id,
                text=f"\u274c Telegram send_message failed after {retries} retries (TimedOut)"
            )
        except Exception:
            pass
    logger.critical(
        "[telegram_utils] Failed to send message after %d retries to chat_id=%s. Content preview: %r",
        retries,
        chat_id,
        text[:max_message_preview_len],
    )
    if last_error:
        raise last_error


async def safe_send(bot, chat_id: int, text: str, chunk_size: int = 4000, retries: int = 3, delay: int = 2, **kwargs):
    """Send ``text`` in chunks using the universal transport layer."""  # [FIX]
    if bot is None:
        log_error("[telegram_utils] safe_send called with None bot")
        return None
    if chat_id is None or not isinstance(chat_id, int):
        log_error("[telegram_utils] Cannot send message: chat_id is invalid")
        return None
    from core.transport_layer import telegram_safe_send
    return await telegram_safe_send(bot, chat_id, text, chunk_size, retries, delay, **kwargs)


async def safe_edit(bot, chat_id: int, message_id: int, text: str, retries: int = 3, delay: int = 2, **kwargs):
    """Edit a Telegram message with retry support."""  # [FIX][telegram retry]
    
    # Filter kwargs to only include valid Telegram bot parameters
    # Remove custom parameters that are not supported by bot.edit_message_text()
    valid_kwargs = {k: v for k, v in kwargs.items() if k not in ['event_id']}
    
    last_error = None
    for attempt in range(1, retries + 1):
        try:
            return await bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text, **valid_kwargs)
        except TimedOut as e:
            last_error = e
            if attempt < retries:
                print(f"[telegram retry] edit_message_text timed out ({attempt}/{retries}), retrying...")
                await asyncio.sleep(delay)
            else:
                print(f"[telegram retry] edit_message_text failed after {retries} retries: {e}")
        except Exception:
            raise
    trainer_id = TELEGRAM_TRAINER_ID
    if trainer_id:
        try:
            await bot.send_message(
                chat_id=trainer_id,
                text=f"\u274c Telegram edit_message_text failed after {retries} retries (TimedOut)"
            )
        except Exception:
            pass
    if last_error:
        raise last_error


async def send_with_thread_fallback(
    bot,
    chat_id: int | str,
    text: str,
    *,
    thread_id: int | None = None,
    reply_to_message_id: int | None = None,
    fallback_chat_id: int | None = None,
    fallback_thread_id: int | None = None,
    fallback_reply_to_message_id: int | None = None,
    **kwargs,
) -> object | None:
    """Send a Telegram message with automatic thread fallback.

    ``message_thread_id`` is the correct Telegram Bot API parameter.  This
    helper mirrors the old ``_send_telegram_message`` logic so that any
    interface can reuse the same behaviour.  It first tries to send with the
    provided ``thread_id`` (mapped to ``message_thread_id``) and falls back to sending without it if the
    thread does not exist.  If ``fallback_chat_id`` is provided it will then try
    sending to that chat using the accompanying fallback parameters.
    """

    if bot is None:
        log_error("[telegram_utils] send_with_thread_fallback called with None bot")
        return

    # Convert string chat_id to integer if needed
    if isinstance(chat_id, str):
        try:
            chat_id = int(chat_id)
        except ValueError:
            log_error(f"[telegram_utils] Invalid chat_id format: {chat_id}")
            return

    send_kwargs = {"chat_id": chat_id, "text": text, **kwargs}
    if thread_id is not None:
        send_kwargs["message_thread_id"] = thread_id  # fixed: correct param is message_thread_id
    if reply_to_message_id is not None:
        send_kwargs["reply_to_message_id"] = reply_to_message_id

    try:
        message = await bot.send_message(**send_kwargs)
        log_info(
            f"[telegram_utils] Message sent to {chat_id}"
            f" (thread: {thread_id}, reply_message_id: {reply_to_message_id})"
        )
        return message
    except Exception as e:
        error_message = str(e)

        # Retry without parse_mode if Markdown/HTML entities are malformed
        if "can't parse entities" in error_message.lower() and send_kwargs.get("parse_mode"):
            log_warning(
                f"[telegram_utils] Parse error with parse_mode={send_kwargs['parse_mode']}; retrying without parse_mode"
            )
            send_kwargs.pop("parse_mode", None)
            try:
                message = await bot.send_message(**send_kwargs)
                log_info(
                    f"[telegram_utils] Message sent to {chat_id} without parse_mode"
                )
                return message
            except Exception as e2:
                error_message = str(e2)

        if thread_id and "thread not found" in error_message.lower():
            log_warning(
                f"[telegram_utils] Thread {thread_id} not found; retrying without thread"
            )
            send_kwargs.pop("message_thread_id", None)
            try:
                message = await bot.send_message(**send_kwargs)
                log_info(
                    f"[telegram_utils] Message sent to {chat_id} without thread"
                )
                return message
            except Exception as no_thread_error:
                log_error(
                    f"[telegram_utils] Fallback without thread failed: {no_thread_error}"
                )
        else:
            log_error(
                f"[telegram_utils] Failed to send to {chat_id} (thread {thread_id}): {repr(e)}"
            )

    if fallback_chat_id and fallback_chat_id != chat_id:
        fallback_kwargs = {"chat_id": fallback_chat_id, "text": text, **kwargs}
        if fallback_thread_id is not None:
            fallback_kwargs["message_thread_id"] = fallback_thread_id
        if fallback_reply_to_message_id is not None:
            fallback_kwargs["reply_to_message_id"] = fallback_reply_to_message_id
        log_debug(
            f"[telegram_utils] Retrying in fallback chat {fallback_chat_id}"
        )
        try:
            message = await bot.send_message(**fallback_kwargs)
            log_info(
                f"[telegram_utils] Message sent to fallback chat {fallback_chat_id}"
            )
            return message
        except Exception as fallback_error:
            log_error(
                f"[telegram_utils] Final fallback failed: {fallback_error}"
            )
    return None
