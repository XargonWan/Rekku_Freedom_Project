from telegram import Update
from telegram.ext import ContextTypes
from core.db import get_db
import time
import os

OWNER_ID = int(os.getenv("OWNER_ID", "123456789"))
MAX_ENTRIES = 100

def track_chat(chat_id: int):
    now = time.time()
    with get_db() as db:
        db.execute("""
            INSERT INTO recent_chats (chat_id, last_active)
            VALUES (?, ?)
            ON CONFLICT(chat_id) DO UPDATE SET last_active=excluded.last_active
        """, (chat_id, now))

def get_last_active_chats(n=10):
    with get_db() as db:
        rows = db.execute("""
            SELECT chat_id FROM recent_chats
            ORDER BY last_active DESC
            LIMIT ?
        """, (n,))
        return [row[0] for row in rows]  # oppure row["chat_id"] se hai row_factory

def format_chat_entry(chat):
    name = chat.title or chat.username or chat.first_name or str(chat.id)

    if chat.username:
        # Pubblico: link cliccabile
        link = f"https://t.me/{chat.username}"
        return f"[{name}]({link}) — `{chat.id}`"
    else:
        # Nessun link disponibile, mostra solo nome + ID
        return f"{name} — `{chat.id}`"

async def last_chats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return

    bot = context.bot
    lines = ["\U0001f553 *Ultime chat attive:*"]

    for chat_id in get_last_active_chats():
        try:
            chat = await bot.get_chat(chat_id)
            lines.append("- " + format_chat_entry(chat))
        except Exception as e:
            print(f"[DEBUG] Errore recuperando chat {chat_id}: {e}")
            lines.append(f"- `{chat_id}`")


    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def get_last_active_chats_verbose(n=10, bot=None):
    chat_ids = get_last_active_chats(n)
    results = []
    for chat_id in chat_ids:
        name = str(chat_id)
        if bot:
            try:
                chat = await bot.get_chat(chat_id)
                name = chat.title or chat.username or str(chat_id)
            except Exception:
                pass
        results.append((chat_id, name))
    return results

