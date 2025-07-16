from typing import Optional
from telegram.constants import ParseMode
import json
from core.config import OWNER_ID
from core.logging_utils import log_error


def truncate_message(text: Optional[str], limit: int = 4000) -> str:
    """Return ``text`` truncated to fit within Telegram limits."""
    if not text:
        return text or ""
    if len(text) > limit:
        return text[:limit] + "\n... (truncated)"
    return text


async def send_json_preview(bot, prompt: dict, owner_id: int = OWNER_ID) -> None:
    """Send a JSON preview of ``prompt`` to ``owner_id``."""
    try:
        prompt_json = json.dumps(prompt, ensure_ascii=False, indent=2)
        prompt_json = truncate_message(prompt_json)
        await bot.send_message(
            chat_id=owner_id,
            text=f"\U0001f4e6 Prompt JSON:\n```json\n{prompt_json}\n```",
            parse_mode=ParseMode.MARKDOWN,
        )
    except Exception as e:  # pragma: no cover - best effort
        log_error(f"[preview] Failed to send JSON preview: {e}", e)
