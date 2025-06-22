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
from llm_engines.manual import ManualAIPlugin
from core import blocklist
from core import response_proxy
from core import say_proxy, recent_chats
from core.context import context_command
from collections import deque
import json
from core.message_sender import send_content
from core.message_sender import detect_media_type
from core.message_sender import extract_response_target
from core.config import get_active_llm, set_active_llm, list_available_llms
from core.config import BOT_TOKEN, BOT_USERNAME, OWNER_ID
from core.plugin_instance import plugin, load_plugin

load_plugin(get_active_llm()) 

# Carica variabili da .env
load_dotenv()
BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
BOT_USERNAME = "Rekku_the_bot"
OWNER_ID = int(os.getenv("OWNER_ID", "123456789"))

say_sessions = {}
context_memory = {}
last_selected_chat = {}
message_id = None

from core.config import LLM_MODE

if LLM_MODE == "manual":
    from llm_engines.manual import ManualAIPlugin
    plugin = ManualAIPlugin()
elif LLM_MODE == "chatgpt":
    from llm_engines.openai_chatgpt import OpenAIAIPlugin
    plugin = OpenAIAIPlugin(api_key=os.getenv("OPENAI_API_KEY"))
else:
    raise ValueError(f"Modalità LLM non riconosciuta: {LLM_MODE}")


def resolve_forwarded_target(message):
    """Dato un messaggio (presumibilmente reply a un messaggio inoltrato),
    prova a ricostruire chat_id e message_id originali."""

    if hasattr(message, "forward_from_chat") and hasattr(message, "forward_from_message_id"):
        if message.forward_from_chat and message.forward_from_message_id:
            return message.forward_from_chat.id, message.forward_from_message_id

    tracked = plugin.get_target(message.message_id)
    if tracked:
        return tracked["chat_id"], tracked["message_id"]

    return None, None

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

from core.message_sender import send_content, detect_media_type, extract_response_target

async def handle_incoming_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        print("[DEBUG] Messaggio ignorato: non da OWNER_ID")
        return

    message = update.message
    if not message:
        print("[DEBUG] ❌ Nessun message presente, esco.")
        return

    media_type = detect_media_type(message)
    print(f"[DEBUG] ✅ handle_incoming_response: media_type = {media_type}; reply_to = {bool(message.reply_to_message)}")

    # === 1. Prova target da response_proxy (es. /say)
    target = response_proxy.get_target(OWNER_ID)
    print(f"[DEBUG] Target iniziale da response_proxy = {target}")

    # === 2. Se risponde a un messaggio, cerca nel plugin mapping
    if not target and message.reply_to_message:
        reply = message.reply_to_message
        print(f"[DEBUG] Risposta a trainer_message_id={reply.message_id}")
        possible_ids = [reply.message_id]
        if reply.reply_to_message:
            possible_ids.append(reply.reply_to_message.message_id)

        for mid in possible_ids:
            tracked = plugin.get_target(mid)
            if tracked:
                target = {
                    "chat_id": tracked["chat_id"],
                    "message_id": tracked["message_id"],
                    "type": media_type
                }
                print(f"[DEBUG] Trovato target via plugin.get_target({mid}): {target}")
                break
        if not target:
            print("[DEBUG] ❌ Nessun mapping trovato nel plugin")

    # === 3. Fallback da /say
    if not target:
        fallback = say_proxy.get_target(OWNER_ID)
        print(f"[DEBUG] Fallback da say_proxy = {fallback}")
        if fallback and fallback != "EXPIRED":
            target = {
                "chat_id": fallback,
                "message_id": None,
                "type": media_type
            }
            print(f"[DEBUG] Target impostato da say_proxy: {target}")
        elif fallback == "EXPIRED":
            await message.reply_text("⏳ Tempo scaduto, rifai /say.")
            return

    # === 4. Se ancora niente, abort
    if not target:
        print("[ERROR] ❌ Nessun target trovato per l'invio.")
        await message.reply_text("⚠️ Nessun destinatario rilevato. Usa /say o rispondi a un messaggio inoltrato.")
        return

    # === 5. Invia contenuto
    chat_id = target["chat_id"]
    reply_to = target["message_id"]
    content_type = target["type"]

    print(f"[DEBUG] Invio media_type={content_type} to chat_id={chat_id}, reply_to={reply_to}")
    success, feedback = await send_content(context.bot, chat_id, message, content_type, reply_to)

    await message.reply_text(feedback)

    if success:
        print("[DEBUG] ✅ Invio avvenuto con successo. Pulizia proxy.")
        response_proxy.clear_target(OWNER_ID)
        say_proxy.clear(OWNER_ID)
    else:
        print("[ERROR] ❌ Invio fallito.")

from core.message_sender import detect_media_type

# === Comando generico per sticker/audio/photo/file/video ===

async def handle_response_command(update: Update, context: ContextTypes.DEFAULT_TYPE, content_type: str):
    if update.effective_user.id != OWNER_ID:
        return

    message = update.message
    if not message.reply_to_message:
        await message.reply_text("\u26a0\ufe0f Devi usare questo comando in risposta a un messaggio inoltrato da Rekku.")
        return

    chat_id, message_id = resolve_forwarded_target(message.reply_to_message)

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
        say_proxy.clear(OWNER_ID)
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

    entries = await recent_chats.get_last_active_chats_verbose(10, context.bot)
    if not entries:
        await update.message.reply_text("\u26a0\ufe0f Nessuna chat recente trovata.")
        return

    lines = [f"[{name}](tg://user?id={cid}) — `{cid}`" for cid, name in entries]
    await update.message.reply_text(
        "\U0001f553 Ultime chat attive:\n" + "\n".join(lines),
        parse_mode="Markdown"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message or not message.from_user:
        print("[DEBUG] Messaggio ignorato (vuoto o senza mittente)")
        return

    user = message.from_user
    user_id = user.id
    username = user.full_name
    usertag = f"@{user.username}" if user.username else "(nessun tag)"
    text = message.text or ""

    # Traccia contesto
    if message.chat_id not in context_memory:
        context_memory[message.chat_id] = deque(maxlen=10)
    context_memory[message.chat_id].append({
        "message_id": message.message_id,
        "username": username,
        "usertag": usertag,
        "text": text,
        "timestamp": message.date.isoformat()
    })
    recent_chats.track_chat(message.chat_id)
    print(f"[DEBUG] context_memory[{message.chat_id}] = {list(context_memory[message.chat_id])}")

    # Step interattivo /say
    if message.chat.type == "private" and user_id == OWNER_ID and context.user_data.get("say_choices"):
        await handle_say_step(update, context)
        return

    print(f"[DEBUG] Messaggio da {user_id} ({message.chat.type}): {text}")

    # Utente bloccato
    if blocklist.is_blocked(user_id) and user_id != OWNER_ID:
        print(f"[DEBUG] Utente {user_id} è bloccato. Ignoro messaggio.")
        return

    # Risposta owner a messaggio inoltrato
    if message.chat.type == "private" and user_id == OWNER_ID and message.reply_to_message:
        reply_msg_id = message.reply_to_message.message_id
        print(f"[DEBUG] Risposta a trainer_message_id={reply_msg_id}")
        original = plugin.get_target(reply_msg_id)
        if original:
            print(f"[DEBUG] Trainer risponde a messaggio {original}")
            await context.bot.send_message(
                chat_id=original["chat_id"],
                text=message.text,
                reply_to_message_id=original["message_id"]
            )
            await message.reply_text("✅ Risposta inviata.")
        else:
            await message.reply_text("⚠️ Nessun messaggio da rispondere trovato.")
        return

    # === FILTRO: Rispondi solo se menzionata o in risposta
    if message.chat.type in ["group", "supergroup"]:
        bot_username = BOT_USERNAME.lower()
        mentioned = any(
            entity.type == "mention" and message.text[entity.offset:entity.offset + entity.length].lower() == f"@{bot_username}"
            for entity in message.entities or []
        )
        is_reply_to_bot = (
            message.reply_to_message and
            message.reply_to_message.from_user and
            message.reply_to_message.from_user.username and
            message.reply_to_message.from_user.username.lower() == bot_username
        )
        if not mentioned and not is_reply_to_bot:
            print("[DEBUG] Ignoro messaggio: non menzionata né in risposta a me.")
            return

    # === Passa al plugin
    try:
        await plugin.handle_incoming_message(context.bot, message, context_memory)
    except Exception as e:
        print(f"[ERROR] plugin.handle_incoming_message fallito: {e}")

async def cancel_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    if response_proxy.has_pending(OWNER_ID):
        response_proxy.clear_target(OWNER_ID)
        print("[DEBUG] Invio risposta annullato.")
        await update.message.reply_text("\u274c Invio annullato.")
    else:
        await update.message.reply_text("\u26a0\ufe0f Nessun invio attivo da annullare.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from core.context import get_context_state
    from core.config import get_active_llm
    from core.plugin_instance import plugin

    if update.effective_user.id != OWNER_ID:
        return

    context_status = "attiva ✅" if get_context_state() else "disattiva ❌"
    llm_mode = get_active_llm()

    help_text = (
        f"🧞‍♀️ *Rekku – Comandi disponibili*\n\n"
        "*🧠 Modalità context*\n"
        f"`/context` – Attiva/disattiva la cronologia nei messaggi inoltrati, attualmente *{context_status}*\n\n"
        "*✏️ Comando /say*\n"
        "`/say` – Seleziona una chat dalle più recenti\n"
        "`/say <id> <messaggio>` – Invia direttamente un messaggio a una chat\n\n"
        "*🧩 Modalità manuale*\n"
        "Rispondi a un messaggio inoltrato con testo o contenuti (sticker, foto, audio, file, ecc.)\n"
        "`/cancel` – Annulla un invio in attesa\n\n"
        "*🧱 Gestione utenti*\n"
        "`/block <user_id>` – Blocca un utente\n"
        "`/unblock <user_id>` – Sblocca un utente\n"
        "`/block_list` – Elenca gli utenti bloccati\n\n"
        "*⚙️ Modalità LLM*\n"
        f"`/llm` – Mostra e seleziona il motore attuale (attivo: `{llm_mode}`)\n"
    )

    # Aggiungi /model se supportato
    if hasattr(plugin, "get_supported_models") and callable(getattr(plugin, "get_supported_models", None)):
        current_model = None
        if hasattr(plugin, "get_current_model") and callable(getattr(plugin, "get_current_model", None)):
            try:
                current_model = plugin.get_current_model()
            except Exception:
                pass

        if current_model:
            help_text += f"`/model` – Visualizza o imposta il modello attivo (attivo: `{current_model}`)\n"
        else:
            help_text += "`/model` – Visualizza o imposta il modello attivo\n"

    help_text += (
        "\n*📋 Varie*\n"
        "`/last_chats` – Ultime chat attive\n"
    )

    await update.message.reply_text(help_text, parse_mode="Markdown")

async def last_chats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return

    entries = await recent_chats.get_last_active_chats_verbose(10, context.bot)
    if not entries:
        await update.message.reply_text("\u26a0\ufe0f Nessuna chat recente trovata.")
        return

    lines = [f"[{name}](tg://user?id={cid}) — `{cid}`" for cid, name in entries]
    await update.message.reply_text(
        "\U0001f553 Ultime chat attive:\n" + "\n".join(lines),
        parse_mode="Markdown"
    )

async def say_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return

    args = context.args
    bot = context.bot

    # Caso 1: /say <chat_id> <messaggio>
    if len(args) >= 2:
        try:
            chat_id = int(args[0])
            text = " ".join(args[1:])
            await bot.send_message(chat_id=chat_id, text=text)
            await update.message.reply_text("\u2705 Messaggio inviato.")
        except Exception as e:
            print(f"[ERROR] Errore /say diretto: {e}")
            await update.message.reply_text("\u274c Errore nell'invio.")
        return

    # Caso 2: /say (senza argomenti) \u2192 mostra ultime chat
    entries = await recent_chats.get_last_active_chats_verbose(10, bot)
    if not entries:
        await update.message.reply_text("\u26a0\ufe0f Nessuna chat recente trovata.")
        return

    # Salva lista in memoria e mostra opzioni
    buttons = [
        [f"{i+1}. {name} \u2014 `{cid}`"] for i, (cid, name) in enumerate(entries)
    ]
    numbered = "\n".join(f"{i+1}. {name} \u2014 `{cid}`" for i, (cid, name) in enumerate(entries))
    numbered += "\n\n\u270f\ufe0f Rispondi con il numero per scegliere la chat."

    say_proxy.clear(update.effective_user.id)  # Assicura pulizia prima della scelta
    context.user_data["say_choices"] = entries

    await update.message.reply_text(numbered, parse_mode="Markdown")

async def handle_say_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from core.plugin_instance import plugin

    user_id = update.effective_user.id
    message = update.message

    target_chat = say_proxy.get_target(user_id)

    if target_chat == "EXPIRED":
        await message.reply_text("\u23f3 Tempo scaduto. Usa di nuovo /say.")
        return

    # Se il target non è ancora stato scelto, prova SEMPRE a interpretare il testo come numero
    if not target_chat and message.text:
        stripped = message.text.strip()
        if stripped.isdigit():
            try:
                index = int(stripped) - 1
                choices = context.user_data.get("say_choices", [])
                if 0 <= index < len(choices):
                    selected_chat_id = choices[index][0]
                    say_proxy.set_target(user_id, selected_chat_id)
                    context.user_data.pop("say_choices", None)
                    await message.reply_text(
                        "✅ Chat selezionata.\n\nOra inviami il *messaggio*, una *foto*, un *file*, un *audio* o qualsiasi altro contenuto da inoltrare.",
                        parse_mode="Markdown"
                    )
                    return
            except Exception:
                pass

        await message.reply_text("❌ Selezione non valida. Invia un numero corretto.")
        return

    # Chat selezionata → inoltra il contenuto attraverso il plugin
    if target_chat:
        print(f"[DEBUG] Inoltro tramite plugin.handle_incoming_message (chat_id={target_chat})")
        try:
            await plugin.handle_incoming_message(context.bot, message, context.user_data)
            response_proxy.clear_target(OWNER_ID)
            say_proxy.clear(OWNER_ID)
        except Exception as e:
            print(f"[ERROR] Errore durante plugin.handle_incoming_message in /say: {e}")
            await message.reply_text("❌ Errore durante l'invio del messaggio.")

async def llm_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return

    args = context.args
    current = get_active_llm()
    available = list_available_llms()

    if not args:
        msg = f"*LLM attivo:* `{current}`\n\n*Disponibili:*"
        msg += "\n" + "\n".join(f"\u2022 `{name}`" for name in available)
        msg += "\n\nPer cambiare: `/llm <nome>`"
        await update.message.reply_text(msg, parse_mode="Markdown")
        return

    choice = args[0]
    if choice not in available:
        await update.message.reply_text(f"\u274c LLM `{choice}` non trovato.")
        return

    from core.plugin_instance import load_plugin
    try:
        load_plugin(choice)
        set_active_llm(choice)
        await update.message.reply_text(f"\u2705 Modalità LLM aggiornata dinamicamente a `{choice}`.")
    except Exception as e:
        await update.message.reply_text(f"\u274c Errore nel caricamento del plugin: {e}")

async def model_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return

    if not hasattr(plugin, "get_supported_models"):
        await update.message.reply_text("⚠️ Questo plugin non supporta la selezione del modello.")
        return

    models = plugin.get_supported_models()
    if not models:
        await update.message.reply_text("⚠️ Nessun modello disponibile per questo plugin.")
        return

    # Nessun argomento → mostra lista
    if not context.args:
        current = plugin.get_current_model()
        current = current or models[0]
        msg = f"*Modelli disponibili:*\n" + "\n".join(f"• `{m}`" for m in models)
        msg += f"\n\nModello attivo: `{current}`"
        msg += "\n\nPer cambiare: `/model <nome>`"
        await update.message.reply_text(msg, parse_mode="Markdown")
        return

    # Con argomento → cambio modello
    choice = context.args[0]
    if choice not in models:
        await update.message.reply_text(f"❌ Modello `{choice}` non valido.")
        return

    try:
        plugin.set_current_model(choice)
        await update.message.reply_text(f"✅ Modello aggiornato a `{choice}`.")
    except Exception as e:
        await update.message.reply_text(f"❌ Errore nel cambio modello: {e}")

# === Avvio ===

def start_bot():
    
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("help", help_command))

    app.add_handler(CommandHandler("block", block_user))
    app.add_handler(CommandHandler("block_list", block_list))
    app.add_handler(CommandHandler("unblock", unblock_user))
    
    app.add_handler(CommandHandler("last_chats", last_chats_command))
    app.add_handler(CommandHandler("context", context_command))
    app.add_handler(CommandHandler("llm", llm_command))
    if hasattr(plugin, "get_supported_models") and callable(plugin.get_supported_models) and plugin.get_supported_models():
        app.add_handler(CommandHandler("model", model_command))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    app.add_handler(CommandHandler("say", say_command))

    # Prima gestisci /say step
    app.add_handler(MessageHandler(
        filters.Chat(OWNER_ID) & (
            filters.TEXT | filters.PHOTO | filters.AUDIO | filters.VOICE | filters.VIDEO | filters.Document.ALL
        ),
        handle_say_step
    ))

    # Poi gli altri messaggi media generici
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

    print("🧞‍♀️ Rekku è online.")
    app.run_polling()
