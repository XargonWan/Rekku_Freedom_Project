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
from core import response_proxy
from core import recent_chats

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

    # Traccia ogni chat attiva
    recent_chats.track_chat(message.chat_id)
    
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
                # Prepara intestazione con info sull'autore originale
                sender = message.from_user
                user_ref = f"@{sender.username}" if sender.username else f"{sender.full_name}"

                # 1. Manda intestazione con nome e ID
                await context.bot.send_message(
                    chat_id=OWNER_ID,
                    text=f"{user_ref}:",
                )

                # 2. Inoltra il messaggio subito dopo
                sent = await context.bot.forward_message(
                    chat_id=OWNER_ID,
                    from_chat_id=message.chat_id,
                    message_id=message.message_id
                )

                # 3. Traccia il messaggio inoltrato
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
        await message.reply_text("\u26a0\ufe0f Devi usare /sticker in risposta a un messaggio inoltrato da Rekku.")
        return

    replied = message.reply_to_message

    # 1. Prova a usare forward info, se disponibile
    chat_id = None
    message_id = None

    if hasattr(replied, "forward_from_chat") and hasattr(replied, "forward_from_message_id"):
        if replied.forward_from_chat and replied.forward_from_message_id:
            chat_id = replied.forward_from_chat.id
            message_id = replied.forward_from_message_id

    # 2. Altrimenti, cerca tra i messaggi tracciati
    if not chat_id or not message_id:
        tracked = plugin.get_target(replied.message_id)
        if tracked:
            chat_id = tracked["chat_id"]
            message_id = tracked["message_id"]

    if not chat_id or not message_id:
        print("[DEBUG] Impossibile determinare il messaggio originale.")
        await message.reply_text("\u274c Messaggio non valido per /sticker. Deve essere un messaggio inoltrato da Rekku.")
        return

    # Salva il target per lo sticker
    response_proxy.set_target(OWNER_ID, chat_id, message_id, "sticker")
    print(f"[DEBUG] Target sticker impostato: chat_id={chat_id}, message_id={message_id}")
    await context.bot.send_message(
        chat_id=OWNER_ID,
        text="\U0001f5bc Inviami ora lo sticker da usare come risposta."
    )

async def handle_incoming_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return

    message = update.message
    if not message:
        return

    target = response_proxy.get_target(OWNER_ID)

    # === Se non c'� target attivo, prova a usare reply diretto a un messaggio inoltrato ===
    if not target and message.reply_to_message:
        replied = message.reply_to_message
        tracked = plugin.get_target(replied.message_id)
        if tracked:
            print("[DEBUG] Uso risposta diretta a messaggio inoltrato.")
            target = {
                "chat_id": tracked["chat_id"],
                "message_id": tracked["message_id"],
                "type": detect_media_type(message)
            }

    if target == "EXPIRED":
        print("[DEBUG] Invio contenuto scaduto.")
        await message.reply_text("\u23f3 Tempo scaduto. Usa di nuovo il comando.")
        return
    elif not target:
        await message.reply_text("\u26a0\ufe0f Nessuna risposta attiva. Usa un comando tipo /sticker, /audio, o rispondi a un messaggio inoltrato.")
        return

    content_type = target["type"]
    chat_id = target["chat_id"]
    message_id = target["message_id"]

    try:
        if content_type == "sticker" and message.sticker:
            await context.bot.send_sticker(chat_id=chat_id, sticker=message.sticker.file_id, reply_to_message_id=message_id)
        elif content_type == "photo" and message.photo:
            await context.bot.send_photo(chat_id=chat_id, photo=message.photo[-1].file_id, reply_to_message_id=message_id)
        elif content_type == "audio" and (message.audio or message.voice):
            audio = message.audio or message.voice
            await context.bot.send_audio(chat_id=chat_id, audio=audio.file_id, reply_to_message_id=message_id)
        elif content_type == "file" and message.document:
            await context.bot.send_document(chat_id=chat_id, document=message.document.file_id, reply_to_message_id=message_id)
        elif content_type == "video" and message.video:
            await context.bot.send_video(chat_id=chat_id, video=message.video.file_id, reply_to_message_id=message_id)
        else:
            await message.reply_text(f"\u274c Il contenuto ricevuto non corrisponde a {content_type.upper()}.")
            return

        print(f"[DEBUG] Risposta {content_type} inviata a {chat_id}:{message_id}")
        await message.reply_text("\u2705 Risposta inviata.")
        response_proxy.clear_target(OWNER_ID)
    except Exception as e:
        print(f"[ERROR] Invio {content_type} fallito: {e}")
        await message.reply_text("\u274c Errore durante l'invio.")

def detect_media_type(message):
    if message.sticker:
        return "sticker"
    elif message.photo:
        return "photo"
    elif message.audio or message.voice:
        return "audio"
    elif message.video:
        return "video"
    elif message.document:
        return "file"
    return "unknown"

# === Comando generico per sticker/audio/photo/file/video ===

async def handle_response_command(update: Update, context: ContextTypes.DEFAULT_TYPE, content_type: str):
    if update.effective_user.id != OWNER_ID:
        return

    message = update.message
    if not message.reply_to_message:
        await message.reply_text("\u26a0\ufe0f Devi usare questo comando in risposta a un messaggio inoltrato da Rekku.")
        return

    replied = message.reply_to_message
    chat_id = None
    message_id = None

    if hasattr(replied, "forward_from_chat") and hasattr(replied, "forward_from_message_id"):
        if replied.forward_from_chat and replied.forward_from_message_id:
            chat_id = replied.forward_from_chat.id
            message_id = replied.forward_from_message_id

    if not chat_id or not message_id:
        tracked = plugin.get_target(replied.message_id)
        if tracked:
            chat_id = tracked["chat_id"]
            message_id = tracked["message_id"]

    if not chat_id or not message_id:
        await message.reply_text("\u274c Messaggio non valido per questo comando.")
        return

    response_proxy.set_target(OWNER_ID, chat_id, message_id, content_type)
    print(f"[DEBUG] Target {content_type} impostato: chat_id={chat_id}, message_id={message_id}")
    await context.bot.send_message(
        chat_id=OWNER_ID,
        text=f"\U0001f4ce Inviami ora il file {content_type.upper()} da usare come risposta."
    )

async def cancel_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    if response_proxy.has_pending(OWNER_ID):
        response_proxy.clear_target(OWNER_ID)
        print("[DEBUG] Invio risposta annullato.")
        await update.message.reply_text("\u274c Invio annullato.")
    else:
        await update.message.reply_text("\u26a0\ufe0f Nessun invio attivo da annullare.")


async def test_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("[DEBUG] /test ricevuto")
    await update.message.reply_text("✅ Test OK")

async def last_chats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return

    entries = recent_chats.get_last_active_chats_verbose(10, context.bot)
    if not entries:
        await update.message.reply_text("\u26a0\ufe0f Nessuna chat recente trovata.")
        return

    lines = [f"`{cid}` \u2014 {name}" for cid, name in entries]
    await update.message.reply_text(
        "\U0001f553 Ultime chat attive:\n" + "\n".join(lines),
        parse_mode="Markdown"
    )

# === Avvio ===

def start_bot():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CommandHandler("block", block_user))
    app.add_handler(CommandHandler("block_list", block_list))
    app.add_handler(CommandHandler("unblock", unblock_user))
    
    app.add_handler(CommandHandler("last_chats", last_chats_command))

    app.add_handler(CommandHandler("sticker", lambda u, c: handle_response_command(u, c, "sticker")))
    app.add_handler(CommandHandler("audio", lambda u, c: handle_response_command(u, c, "audio")))
    app.add_handler(CommandHandler("photo", lambda u, c: handle_response_command(u, c, "photo")))
    app.add_handler(CommandHandler("file", lambda u, c: handle_response_command(u, c, "file")))
    app.add_handler(CommandHandler("video", lambda u, c: handle_response_command(u, c, "video")))

    app.add_handler(MessageHandler(
    filters.Chat(OWNER_ID) & (
        filters.Sticker.ALL |
        filters.PHOTO |
        filters.AUDIO |
        filters.VOICE |
        filters.VIDEO |
        filters.Document.ALL
    ),
    handle_incoming_response
    ))

    app.add_handler(CommandHandler("cancel", cancel_response))

    app.add_handler(CommandHandler("test", test_command))

    print("🧞‍♀️ Rekku è online.")
    app.run_polling()
