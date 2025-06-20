import os
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    ContextTypes,
    CommandHandler,
    filters,
)
from dotenv import load_dotenv
from core.manual_ai_plugin import ManualAIPlugin
from core import blocklist
from core import sticker_proxy

# Carica variabili da .env
load_dotenv()
BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
BOT_USERNAME = "Rekku_the_bot"
OWNER_ID = int(os.getenv("OWNER_ID", "123456789"))

plugin = ManualAIPlugin()

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message or not message.from_user:
        print("[DEBUG] Messaggio ignorato (vuoto o senza mittente)")
        return

    user_id = message.from_user.id
    text = message.text or ""
    
    print(f"[DEBUG] Messaggio da {user_id} ({message.chat.type}): {text}")

    if blocklist.is_blocked(user_id) and user_id != OWNER_ID:
        print(f"[DEBUG] Utente {user_id} � bloccato. Ignoro messaggio.")
        return

    # === 1. Trainer risponde ===
    if message.chat.type == "private" and user_id == OWNER_ID and message.reply_to_message:
        original = plugin.get_target(message.reply_to_message.message_id)
        if original:
            print(f"[DEBUG] Trainer risponde a messaggio {original}")
            await context.bot.send_message(
                chat_id=original["chat_id"],
                text=message.text,
                reply_to_message_id=original["message_id"]
            )
            plugin.clear(message.reply_to_message.message_id)
            await message.reply_text("\u2705 Risposta inviata.")
        else:
            print("[DEBUG] Nessun messaggio da rispondere trovato.")
            await message.reply_text("\u26a0\ufe0f Nessun messaggio da rispondere trovato.")
        return

    # === 2. Messaggi in gruppo ===
    if message.chat.type in ["group", "supergroup"] and (user_id != OWNER_ID or True):
        print("[DEBUG] Messaggio in gruppo ricevuto")
        member_count = await context.bot.get_chat_member_count(chat_id=message.chat_id)
        print(f"[DEBUG] chat_id={message.chat_id}, member_count={member_count}")
        print(f"[DEBUG] Numero membri nel gruppo: {member_count}")
        print(f"[DEBUG] Entities: {[e.type for e in message.entities or []]}")

        should_forward = False

        # Se � una menzione
        if any(
            entity.type == "mention" and f"@{BOT_USERNAME}" in text[entity.offset:entity.offset + entity.length]
            for entity in message.entities or []
        ):
            print(f"[DEBUG] Trovata mention: @{BOT_USERNAME}")
            should_forward = True

        # Se � una risposta al bot
        elif message.reply_to_message and message.reply_to_message.from_user.id == context.bot.id:
            print("[DEBUG] � una risposta a Rekku.")
            should_forward = True

        # Se � un gruppo con solo 2 membri
        elif member_count <= 2:
            print("[DEBUG] Gruppo con 2 membri, inoltro forzato.")
            should_forward = True

        print(f"[DEBUG] should_forward: {should_forward}")

        if should_forward:
            try:
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
                print("[DEBUG] Messaggio inoltrato con successo.")
            except Exception as e:
                print(f"[ERROR] Inoltro fallito: {e}")
        else:
            print("[DEBUG] Nessun criterio soddisfatto. Messaggio ignorato.")
        return

    # === 3. Messaggi privati da altri ===
    if message.chat.type == "private" and user_id != OWNER_ID:
        print(f"[DEBUG] Inoltro messaggio da utente in privato: {user_id}")
        try:
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
            await message.reply_text("\U0001f44b Il mio trainer ti risponder� a breve.")
            print("[DEBUG] Messaggio inoltrato correttamente.")
        except Exception as e:
            print(f"[ERROR] Inoltro da chat privata fallito: {e}")
        return


# === Comandi blocco ===

async def block_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    try:
        to_block = int(context.args[0])
        blocklist.block_user(to_block)
        print(f"[DEBUG] Utente {to_block} bloccato.")
        await update.message.reply_text(f"\U0001f6ab Utente {to_block} bloccato.")
    except (IndexError, ValueError):
        await update.message.reply_text("\u274c Usa: /block <user_id>")

async def block_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    blocked = blocklist.get_block_list()
    print(f"[DEBUG] Lista utenti bloccati richiesta.")
    if not blocked:
        await update.message.reply_text("\u2705 Nessun utente bloccato.")
    else:
        await update.message.reply_text("\U0001f6ab Utenti bloccati:\n" + "\n".join(map(str, blocked)))

async def unblock_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    try:
        to_unblock = int(context.args[0])
        blocklist.unblock_user(to_unblock)
        print(f"[DEBUG] Utente {to_unblock} sbloccato.")
        await update.message.reply_text(f"\u2705 Utente {to_unblock} sbloccato.")
    except (IndexError, ValueError):
        await update.message.reply_text("\u274c Usa: /unblock <user_id>")


# === Sticker ===

async def handle_sticker_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    message = update.message
    if not message.reply_to_message:
        await message.reply_text("\u26a0\ufe0f Devi usare /sticker in risposta a un messaggio.")
        return
    sticker_proxy.set_target(OWNER_ID, message.chat_id, message.reply_to_message.message_id)
    print(f"[DEBUG] Richiesta sticker su messaggio {message.reply_to_message.message_id}")
    await context.bot.send_message(chat_id=OWNER_ID, text="\U0001f5bc Inviami ora lo sticker da usare come risposta.")

async def handle_incoming_sticker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    sticker = update.message.sticker
    if not sticker:
        return
    target = sticker_proxy.get_target(OWNER_ID)
    if target == "EXPIRED":
        print("[DEBUG] Tentativo di invio sticker scaduto.")
        await update.message.reply_text("\u274c Ok, niente sticker.")
        return
    elif not target:
        print("[DEBUG] Nessun sticker in attesa.")
        await update.message.reply_text("\u26a0\ufe0f Nessuna risposta attiva. Usa /sticker su un messaggio.")
        return
    print(f"[DEBUG] Invio sticker a {target}")
    await context.bot.send_sticker(
        chat_id=target["chat_id"],
        sticker=sticker.file_id,
        reply_to_message_id=target["message_id"]
    )
    await update.message.reply_text("\u2705 Sticker inviato.")
    sticker_proxy.clear_target(OWNER_ID)

async def cancel_sticker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    if sticker_proxy.has_pending(OWNER_ID):
        sticker_proxy.clear_target(OWNER_ID)
        print("[DEBUG] Invio sticker annullato.")
        await update.message.reply_text("\u274c Invio sticker annullato.")
    else:
        await update.message.reply_text("\u26a0\ufe0f Nessun invio sticker da annullare.")


async def test_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("[DEBUG] /test ricevuto")
    await update.message.reply_text("✅ Test OK")

# === Avvio ===

def start_bot():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CommandHandler("block", block_user))
    app.add_handler(CommandHandler("block_list", block_list))
    app.add_handler(CommandHandler("unblock", unblock_user))

    app.add_handler(CommandHandler("sticker", handle_sticker_command))
    app.add_handler(CommandHandler("cancel_sticker", cancel_sticker))

    app.add_handler(CommandHandler("test", test_command))

    app.add_handler(MessageHandler(filters.Sticker.ALL & filters.ChatType.PRIVATE, handle_incoming_sticker))

    print("🧞‍♀️ Rekku è online.")
    app.run_polling()
