"""Plugin to handle simple text messages."""

from telegram import Bot
from telegram.constants import ParseMode

async def run(bot: Bot, params: dict):
    text = params.get("text")
    chat_id = params.get("chat_id")
    reply_to = params.get("reply_to")
    if not text or chat_id is None:
        raise ValueError("message action requires 'text' and 'chat_id'")

    await bot.send_message(chat_id=chat_id, text=text, reply_to_message_id=reply_to, parse_mode=ParseMode.HTML)
