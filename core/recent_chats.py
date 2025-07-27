from telegram import Update
from telegram.ext import ContextTypes
from core.db import get_conn
import aiomysql
import time
import os
import re
from core.logging_utils import log_debug, log_info, log_warning, log_error
import json
from pathlib import Path

OWNER_ID = int(os.getenv("OWNER_ID", "123456789"))
MAX_ENTRIES = 100
_metadata = {}
chat_path_map = {}

_CHAT_MAP_PATH = Path(__file__).with_name("chat_paths.json")

def _save_chat_paths():
    try:
        with _CHAT_MAP_PATH.open("w", encoding="utf-8") as f:
            json.dump(chat_path_map, f)
        log_debug(f"[recent_chats] Saved chat path map with {len(chat_path_map)} entries")
    except Exception as e:  # pragma: no cover - best effort
        log_warning(f"[recent_chats] Failed to save chat path map: {e}")

if _CHAT_MAP_PATH.exists():
    try:
        with _CHAT_MAP_PATH.open("r", encoding="utf-8") as f:
            chat_path_map = {int(k): v for k, v in json.load(f).items()}
        log_debug(
            f"[recent_chats] Loaded chat path map with {len(chat_path_map)} entries"
        )
    except Exception as e:  # pragma: no cover - best effort
        log_warning(f"[recent_chats] Failed to load chat path map: {e}")

async def track_chat(chat_id: int, metadata=None):
    now = time.time()
    conn = await get_conn()
    try:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO recent_chats (chat_id, last_active)
                VALUES (%s, %s)
                ON DUPLICATE KEY UPDATE last_active = VALUES(last_active)
                """,
                (chat_id, now),
            )
            await conn.commit()
    finally:
        conn.close()
    if metadata:
        _metadata[chat_id] = metadata

async def reset_chat(chat_id: int):
    conn = await get_conn()
    try:
        async with conn.cursor() as cur:
            await cur.execute("DELETE FROM recent_chats WHERE chat_id = %s", (chat_id,))
            await conn.commit()
    finally:
        conn.close()
    _metadata.pop(chat_id, None)
    if chat_path_map.pop(chat_id, None) is not None:
        _save_chat_paths()

def set_chat_path(chat_id: int, chat_path: str) -> None:
    chat_path_map[chat_id] = chat_path
    _save_chat_paths()

def get_chat_path(chat_id: int) -> str | None:
    return chat_path_map.get(chat_id)

async def get_last_active_chats(n=10):
    conn = await get_conn()
    try:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                """
                SELECT chat_id FROM recent_chats
                ORDER BY last_active DESC
                LIMIT %s
                """,
                (n,),
            )
            rows = await cur.fetchall()
            return [row["chat_id"] for row in rows]
    finally:
        conn.close()

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

    for chat_id in await get_last_active_chats():
        try:
            chat = await bot.get_chat(chat_id)
            lines.append("- " + format_chat_entry(chat))
        except Exception as e:
            log_debug(f"Error retrieving chat {chat_id}: {e}")
            lines.append(f"- `{chat_id}`")


    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def get_last_active_chats_verbose(n=10, bot=None):
    chat_ids = await get_last_active_chats(n)
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
