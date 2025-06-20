import os
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    ContextTypes,
    filters,
)
from dotenv import load_dotenv
from core.manual_ai_plugin import ManualAIPlugin
from core import blocklist
from telegram.ext import CommandHandler, MessageHandler, filters
from core import sticker_proxy


# Carica variabili da .env
load_dotenv()
BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
BOT_USERNAME = "Rekku_the_bot"
OWNER_ID = int(os.getenv("OWNER_ID", "123456789"))

# Plugin per risposte manuali
plugin = ManualAIPlugin()


# Gestore messaggi principali
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if blocklist.is_blocked(user_id) and user_id != OWNER_ID:
        return  # ignora tutto da utenti bloccati

    message = update.message
    user_id = message.from_user.id
    text = message.text or ""

    # === 1. Risposta del trainer ===
    if message.chat.type == "private" and user_id == OWNER_ID and message.reply_to_message:
        original = plugin.get_target(message.reply_to_message.message_id)
        if original:
            await context.bot.send_message(
                chat_id=original["chat_id"],
                text=message.text,
                reply_to_message_id=original["message_id"]
            )
            plugin.clear(message.reply_to_message.message_id)
            await message.reply_text("\u2705 Risposta inviata.")
        else:
            await message.reply_text("\u26a0\ufe0f Nessun messaggio da rispondere trovato.")
        return

    # === 2. Messaggio in GRUPPO \u2014 solo se taggato ===
    if message.chat.type in ["group", "supergroup"]:
        should_forward = False

        # 1. Se è una menzione
        if any(entity.type == "mention" and f"@{BOT_USERNAME}" in text[entity.offset:entity.offset + entity.length]
            for entity in message.entities or []):
            should_forward = True

        # 2. Se è una risposta a un messaggio di Rekku
        elif message.reply_to_message and message.reply_to_message.from_user.id == context.bot.id:
            should_forward = True

        if not should_forward:
            return  # Ignora tutto il resto

        sent = await context.bot.forward_message(
            chat_id=OWNER_ID,
            from_chat_id=message.chat_id,
            message_id=message.message_id
        )
        plugin.track_message(
            trainer_message_id=sent.message_id,
            original_chat_id=message.chat_id,
            original_message_id=message.message_id
        )
        return

    # === 3. Messaggio privato da utenti (non il trainer) ===
    if message.chat.type == "private" and user_id != OWNER_ID:
        sent = await context.bot.forward_message(
            chat_id=OWNER_ID,
            from_chat_id=message.chat_id,
            message_id=message.message_id
        )
        plugin.track_message(
            trainer_message_id=sent.message_id,
            original_chat_id=message.chat_id,
            original_message_id=message.message_id
        )
        await message.reply_text("\U0001f44b Ciao! Il mio trainer ti risponder� presto.")
        return
    
    # === 4. Messaggio privato da altri utenti ===
    if message.chat.type == "private" and user_id != OWNER_ID:
        sent = await context.bot.forward_message(
            chat_id=OWNER_ID,
            from_chat_id=message.chat_id,
            message_id=message.message_id
        )
        plugin.track_message(
            trainer_message_id=sent.message_id,
            original_chat_id=message.chat_id,
            original_message_id=message.message_id
        )
        await message.reply_text("\U0001f44b Ciao! Il mio trainer ti risponder� presto.")
        return
    

from core import blocklist

async def block_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    try:
        to_block = int(context.args[0])
        blocklist.block_user(to_block)
        await update.message.reply_text(f"🚫 Utente {to_block} bloccato.")
    except (IndexError, ValueError):
        await update.message.reply_text("❌ Usa: /block <user_id>")

async def block_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    blocked = blocklist.get_block_list()
    if not blocked:
        await update.message.reply_text("✅ Nessun utente bloccato.")
    else:
        await update.message.reply_text("🚫 Utenti bloccati:\n" + "\n".join(map(str, blocked)))

async def unblock_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    try:
        to_unblock = int(context.args[0])
        blocklist.unblock_user(to_unblock)
        await update.message.reply_text(f"✅ Utente {to_unblock} sbloccato.")
    except (IndexError, ValueError):
        await update.message.reply_text("❌ Usa: /unblock <user_id>")

async def handle_sticker_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return

    message = update.message
    if not message.reply_to_message:
        await message.reply_text("⚠️ Devi usare /sticker in risposta a un messaggio.")
        return

    target_chat_id = message.chat_id
    target_message_id = message.reply_to_message.message_id

    sticker_proxy.set_target(OWNER_ID, target_chat_id, target_message_id)
    await context.bot.send_message(
        chat_id=OWNER_ID,
        text="🖼 Inviami ora lo sticker da usare come risposta."
    )

async def handle_incoming_sticker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return

    sticker = update.message.sticker
    if not sticker:
        return

    target = sticker_proxy.get_target(OWNER_ID)
    if target == "EXPIRED":
        await update.message.reply_text("❌ Ok, niente sticker.")
        return
    elif not target:
        await update.message.reply_text("⚠️ Nessuna risposta attiva. Usa /sticker su un messaggio.")
        return

    await context.bot.send_sticker(
        chat_id=target["chat_id"],
        sticker=sticker.file_id,
        reply_to_message_id=target["message_id"]
    )
    await update.message.reply_text("✅ Sticker inviato.")
    sticker_proxy.clear_target(OWNER_ID)

async def cancel_sticker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    if sticker_proxy.has_pending(OWNER_ID):
        sticker_proxy.clear_target(OWNER_ID)
        await update.message.reply_text("❌ Invio sticker annullato.")
    else:
        await update.message.reply_text("⚠️ Nessun invio sticker da annullare.")

# Funzione di avvio del bot
def start_bot():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CommandHandler("block", block_user))
    app.add_handler(CommandHandler("block_list", block_list))
    app.add_handler(CommandHandler("unblock", unblock_user))

    app.add_handler(CommandHandler("sticker", handle_sticker_command))
    app.add_handler(CommandHandler("cancel_sticker", cancel_sticker))

    app.add_handler(MessageHandler(filters.STICKER & filters.ChatType.PRIVATE, handle_incoming_sticker))

    print("🧞‍♀️ Rekku è online.")
    app.run_polling()
