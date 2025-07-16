from telegram import Update
from telegram.ext import ContextTypes
from core.db import get_db
import time
import os
import re
from core.logging_utils import log_debug, log_info, log_warning, log_error

OWNER_ID = int(os.getenv("OWNER_ID", "123456789"))
MAX_ENTRIES = 100
_metadata = {}

def track_chat(chat_id: int, metadata=None):
    now = time.time()
    with get_db() as db:
        db.execute(
            """
            INSERT INTO recent_chats (chat_id, last_active)
            VALUES (?, ?)
            ON CONFLICT(chat_id) DO UPDATE SET last_active=excluded.last_active
        """,
            (chat_id, now),
        )
    if metadata:
        _metadata[chat_id] = metadata

def reset_chat(chat_id: int):
    with get_db() as db:
        db.execute("DELETE FROM recent_chats WHERE chat_id = ?", (chat_id,))
    _metadata.pop(chat_id, None)

def get_last_active_chats(n=10):
    with get_db() as db:
        rows = db.execute("""
            SELECT chat_id FROM recent_chats
            ORDER BY last_active DESC
            LIMIT ?
        """, (n,))
        return [row[0] for row in rows]  # or row["chat_id"] if using row_factory

def format_chat_entry(chat):
    name = chat.title or chat.username or chat.first_name or str(chat.id)
    safe_name = escape_markdown(name)

    if chat.username:
        # Public: clickable link
        link = f"https://t.me/{chat.username}"
        return f"[{safe_name}]({link}) — `{chat.id}`"
    else:
        return f"{safe_name} — `{chat.id}`"

async def last_chats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return

    bot = context.bot
    lines = ["\U0001f553 *Last active chats:*"]

    for chat_id in get_last_active_chats():
        try:
            chat = await bot.get_chat(chat_id)
            lines.append("- " + format_chat_entry(chat))
        except Exception as e:
            log_debug(f"Error retrieving chat {chat_id}: {e}")
            lines.append(f"- `{chat_id}`")


    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def get_last_active_chats_verbose(n=10, bot=None):
    chat_ids = get_last_active_chats(n)
    results = []
    for chat_id in chat_ids:
        name = _metadata.get(chat_id)
        if bot and not name:
            try:
                chat = await bot.get_chat(chat_id)
                name = chat.title or chat.username or str(chat_id)
            except Exception:
                pass
        if not name:
            name = str(chat_id)
        results.append((chat_id, name))
    return results

def escape_markdown(text: str) -> str:
    """
    Escape Markdown v1 characters to avoid errors or malformed output.
    """
    escape_chars = r'\_*[]()~`>#+-=|{}.!'
    return re.sub(f'([{re.escape(escape_chars)}])', r'\\\1', text)
