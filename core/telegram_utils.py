from typing import Optional
import asyncio
from telegram.error import TimedOut
from core.config import OWNER_ID


def truncate_message(text: Optional[str], limit: int = 4000) -> str:
    """Return ``text`` truncated to fit within Telegram limits."""
    if not text:
        return text or ""
    if len(text) > limit:
        return text[:limit] + "\n... (truncated)"
    return text


async def safe_send(bot, chat_id: int, text: str, retries: int = 3, delay: int = 2, **kwargs):
    """Send a Telegram message with basic retry logic."""  # [FIX][telegram retry]
    last_error = None
    for attempt in range(1, retries + 1):
        try:
            return await bot.send_message(chat_id=chat_id, text=text, **kwargs)
        except TimedOut as e:
            last_error = e
            if attempt < retries:
                print(f"[telegram retry] send_message timed out ({attempt}/{retries}), retrying...")
                await asyncio.sleep(delay)
            else:
                print(f"[telegram retry] send_message failed after {retries} retries: {e}")
        except Exception:
            raise
    # notify owner on final failure
    try:
        await bot.send_message(chat_id=OWNER_ID,
                               text=f"\u274c Telegram send_message failed after {retries} retries (TimedOut)")
    except Exception:
        pass  # last resort, ignore
    if last_error:
        raise last_error


async def safe_edit(bot, chat_id: int, message_id: int, text: str, retries: int = 3, delay: int = 2, **kwargs):
    """Edit a Telegram message with retry support."""  # [FIX][telegram retry]
    last_error = None
    for attempt in range(1, retries + 1):
        try:
            return await bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text, **kwargs)
        except TimedOut as e:
            last_error = e
            if attempt < retries:
                print(f"[telegram retry] edit_message_text timed out ({attempt}/{retries}), retrying...")
                await asyncio.sleep(delay)
            else:
                print(f"[telegram retry] edit_message_text failed after {retries} retries: {e}")
        except Exception:
            raise
    try:
        await bot.send_message(chat_id=OWNER_ID,
                               text=f"\u274c Telegram edit_message_text failed after {retries} retries (TimedOut)")
    except Exception:
        pass
    if last_error:
        raise last_error
