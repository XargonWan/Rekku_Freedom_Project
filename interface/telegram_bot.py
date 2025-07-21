# interface/telegram_bot.py

import os
import re
import asyncio
from telegram import Update, Bot
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    ContextTypes,
    CommandHandler,
    filters,
)
try:
    from dotenv import load_dotenv  # type: ignore
except Exception:  # pragma: no cover - fallback if python-dotenv not installed
    def load_dotenv(*args, **kwargs):
        return False
from llm_engines.manual import ManualAIPlugin
from core import blocklist
from core import response_proxy
from core import say_proxy, recent_chats, message_map, message_queue
from core.context import context_command
from collections import deque
import json
from core.logging_utils import log_debug, log_info, log_warning, log_error
from core.telegram_utils import truncate_message, safe_send
from core.message_sender import (
    send_content,
    detect_media_type,
    extract_response_target,
)
from core.config import get_active_llm, set_active_llm, list_available_llms
from core.config import BOT_TOKEN, BOT_USERNAME, OWNER_ID
# Import mention detector to recognize Rekku aliases even without explicit @username
from core.mention_utils import is_rekku_mentioned, is_message_for_bot
import core.plugin_instance as plugin_instance
from core.plugin_instance import load_plugin
from core.weather import start_weather_updater, update_weather
import traceback
from telethon import TelegramClient

# Carica variabili da .env
load_dotenv()

say_sessions = {}
context_memory = {}
last_selected_chat = {}
message_id = None

from core.config import LLM_MODE

async def ensure_plugin_loaded(update: Update):
    """
    Check that an LLM plugin has been loaded correctly.
    If absent, reply to the user with an error message and log the issue.
    """
    if plugin_instance.plugin is None:
        log_error("No LLM plugin loaded.")
        if update and update.message:
            await update.message.reply_text("⚠️ No LLM plugin active. Use /llm to select one.")
        return False
    return True

def resolve_forwarded_target(message):
    """Dato un messaggio (presumibilmente reply a un messaggio inoltrato),
    prova a ricostruire chat_id e message_id originali."""

    if hasattr(message, "forward_from_chat") and hasattr(message, "forward_from_message_id"):
        if message.forward_from_chat and message.forward_from_message_id:
            return message.forward_from_chat.id, message.forward_from_message_id

    tracked = plugin_instance.get_target(message.message_id)
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
        log_debug(f"User {to_block} blocked.")
        await update.message.reply_text(f"\U0001f6ab User {to_block} blocked.")
    except (IndexError, ValueError):
        await update.message.reply_text("\u274c Usa: /block <user_id>")

async def block_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    blocked = blocklist.get_block_list()
    log_debug("Blocked users list requested.")
    if not blocked:
        await update.message.reply_text("\u2705 No users blocked.")
    else:
        await update.message.reply_text("\U0001f6ab Blocked users:\n" + "\n".join(map(str, blocked)))

async def unblock_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    try:
        to_unblock = int(context.args[0])
        blocklist.unblock_user(to_unblock)
        log_debug(f"User {to_unblock} unblocked.")
        await update.message.reply_text(f"\u2705 User {to_unblock} unblocked.")
    except (IndexError, ValueError):
        await update.message.reply_text("\u274c Usa: /unblock <user_id>")

async def purge_mappings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    # Ensure table exists even if manual plugin never loaded
    message_map.init_table()
    try:
        days = int(context.args[0]) if context.args else 7
    except ValueError:
        await update.message.reply_text("\u274c Usa: /purge_map [giorni]")
        return
    deleted = message_map.purge_old_entries(days * 86400)
    await update.message.reply_text(
        f"\U0001f5d1 Removed {deleted} mappings older than {days} days."
    )


async def handle_incoming_response(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not await ensure_plugin_loaded(update):
        return

    if update.effective_user.id != OWNER_ID:
        log_debug("Messaggio ignorato: non da OWNER_ID")
        return

    message = update.message
    if not message:
        log_debug("❌ No message present, aborting.")
        return

    media_type = detect_media_type(message)
    log_debug(f"✅ handle_incoming_response: media_type = {media_type}; reply_to = {bool(message.reply_to_message)}")

    # === 1. Prova target da response_proxy (es. /say)
    target = response_proxy.get_target(OWNER_ID)
    log_debug(f"Target iniziale da response_proxy = {target}")

    # === 2. Se risponde a un messaggio, cerca nel plugin mapping
    if not target and message.reply_to_message:
        reply = message.reply_to_message
        log_debug(f"Risposta a trainer_message_id={reply.message_id}")
        possible_ids = [reply.message_id]
        if reply.reply_to_message:
            possible_ids.append(reply.reply_to_message.message_id)

        for mid in possible_ids:
            tracked = plugin_instance.get_target(mid)
            if tracked:
                target = {
                    "chat_id": tracked["chat_id"],
                    "message_id": tracked["message_id"],
                    "type": media_type
                }
                log_debug(f"Trovato target via plugin_instance.get_target({mid}): {target}")
                break
        if not target:
            log_debug("❌ No mapping found in plugin")

    # === 3. Fallback da /say
    if not target:
        fallback = say_proxy.get_target(OWNER_ID)
        log_debug(f"Fallback da say_proxy = {fallback}")
        if fallback and fallback != "EXPIRED":
            target = {
                "chat_id": fallback,
                "message_id": None,
                "type": media_type
            }
            log_debug(f"Target impostato da say_proxy: {target}")
        elif fallback == "EXPIRED":
            await message.reply_text("⏳ Timeout expired, run /say again.")
            return

    # === 4. Se ancora niente, abort
    if not target:
        log_error("No target found for sending.")
        await message.reply_text("⚠️ No recipient detected. Use /say or reply to a forwarded message.")
        return

    # === 5. Invia contenuto
    chat_id = target["chat_id"]
    reply_to = target["message_id"]
    content_type = target["type"]

    log_debug(f"Invio media_type={content_type} to chat_id={chat_id}, reply_to={reply_to}")
    success, feedback = await send_content(context.bot, chat_id, message, content_type, reply_to)

    await message.reply_text(feedback)

    if success:
        log_debug("✅ Invio avvenuto con successo. Pulizia proxy.")
        response_proxy.clear_target(OWNER_ID)
        say_proxy.clear(OWNER_ID)
    else:
        log_error("Invio fallito.")


# === Comando generico per sticker/audio/photo/file/video ===

async def handle_response_command(update: Update, context: ContextTypes.DEFAULT_TYPE, content_type: str):

    if not await ensure_plugin_loaded(update):
        return

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
    log_debug(f"Target {content_type} impostato: chat_id={chat_id}, message_id={message_id}")
    await safe_send(
        context.bot,
        chat_id=OWNER_ID,
        text=f"\U0001f4ce Inviami ora il file {content_type.upper()} da usare come risposta."
    )  # [FIX]

async def cancel_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    if response_proxy.has_pending(OWNER_ID):
        response_proxy.clear_target(OWNER_ID)
        say_proxy.clear(OWNER_ID)
        log_debug("Response sending cancelled.")
        await update.message.reply_text("\u274c Sending cancelled.")
    else:
        await update.message.reply_text("\u26a0\ufe0f No active send to cancel.")


async def test_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    log_debug("/test ricevuto")
    await update.message.reply_text("✅ Test OK")

async def last_chats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return

    entries = await recent_chats.get_last_active_chats_verbose(10, context.bot)
    if not entries:
        await update.message.reply_text("\u26a0\ufe0f No recent chat found.")
        return

    lines = [f"[{name}](tg://user?id={cid}) — `{cid}`" for cid, name in entries]
    await update.message.reply_text(
        "\U0001f553 Last active chats:\n" + "\n".join(lines),
        parse_mode="Markdown"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not await ensure_plugin_loaded(update):
        return

    message = update.message
    if not message or not message.from_user:
        log_debug("Messaggio ignorato (vuoto o senza mittente)")
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
    chat_meta = message.chat.title or message.chat.username or message.chat.first_name
    recent_chats.track_chat(message.chat_id, chat_meta)
    log_debug(f"context_memory[{message.chat_id}] = {list(context_memory[message.chat_id])}")

    # Step interattivo /say
    if message.chat.type == "private" and user_id == OWNER_ID and context.user_data.get("say_choices"):
        await handle_say_step(update, context)
        return

    log_debug(f"Messaggio da {user_id} ({message.chat.type}): {text}")

    # Blocked user
    if blocklist.is_blocked(user_id) and user_id != OWNER_ID:
        log_debug(f"User {user_id} is blocked. Ignoring message.")
        return

    # Risposta owner a messaggio inoltrato
    if message.chat.type == "private" and user_id == OWNER_ID and message.reply_to_message:
        reply_msg_id = message.reply_to_message.message_id
        log_debug(f"Risposta a trainer_message_id={reply_msg_id}")
        original = plugin_instance.get_target(reply_msg_id)
        if original:
            log_debug(f"Trainer risponde a messaggio {original}")
            await safe_send(
                context.bot,
                chat_id=original["chat_id"],
                text=message.text,
                reply_to_message_id=original["message_id"]
            )  # [FIX]
            await message.reply_text("✅ Reply sent.")
        else:
            await message.reply_text("⚠️ No message found to reply to.")
        return

    # === FILTRO: Rispondi solo se menzionata o in risposta
    log_debug(f"[telegram_bot] Checking if message is for bot: chat_type={message.chat.type}, "
              f"text='{text[:50]}{'...' if len(text) > 50 else ''}', "
              f"reply_to={message.reply_to_message is not None}")
    
    if message.reply_to_message:
        log_debug(f"[telegram_bot] Reply to message from user ID: {message.reply_to_message.from_user.id if message.reply_to_message.from_user else 'None'}, "
                  f"username: {message.reply_to_message.from_user.username if message.reply_to_message.from_user else 'None'}")
    
    is_for_bot = is_message_for_bot(message, context.bot)
    log_debug(f"[telegram_bot] is_message_for_bot result: {is_for_bot}")
    
    if not is_for_bot:
        log_debug("Ignoring message: no Rekku mention detected.")
        return

    # === Inoltra nella coda centralizzata
    try:
        await message_queue.enqueue(context.bot, message, context_memory)
    except Exception as e:
        log_error(f"message_queue enqueue failed: {e}", e)
        await message.reply_text("⚠️ Errore nell'elaborazione del messaggio.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from core.context import get_context_state
    from core.config import get_active_llm

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
    try:
        models = plugin_instance.get_supported_models()
        if models:
            current_model = plugin_instance.get_current_model() or models[0]
            help_text += f"`/model` – Visualizza o imposta il modello attivo (attivo: `{current_model}`)\n"
    except Exception:
        pass
        current_model = None
        try:
            models = plugin_instance.get_supported_models()
            if models:
                current_model = plugin_instance.get_current_model() or models[0]
                help_text += f"`/model` – Visualizza o imposta il modello attivo (attivo: `{current_model}`)\n"
        except Exception:
            pass
            try:
                current_model = plugin_instance.get_current_model()
            except Exception:
                pass

        if current_model:
            help_text += f"`/model` – Visualizza o imposta il modello attivo (attivo: `{current_model}`)\n"
        else:
            help_text += "`/model` – Visualizza o imposta il modello attivo\n"

    help_text += (
        "\n*📋 Misc*\n"
        "`/last_chats` – Last active chats\n"
        "`/purge_map [days]` – Purge old mappings\n"
        "`/clean_chat_link <chat_id>` – Rimuove il collegamento tra una chat Telegram e ChatGPT.\n"
    )

    await update.message.reply_text(help_text, parse_mode="Markdown")

def escape_markdown(text):
    return re.sub(r'([_*\[\]()~`>#+=|{}.!-])', r'\\\1', text)

async def last_chats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return

    entries = await recent_chats.get_last_active_chats_verbose(10, context.bot)
    if not entries:
        await update.message.reply_text("\u26a0\ufe0f Nessuna chat recente trovata.")
        return

    lines = [f"[{escape_markdown(name)}](tg://user?id={cid}) — `{cid}`" for cid, name in entries]
    await update.message.reply_text(
        "\U0001f553 Last active chats:\n" + "\n".join(lines),
        parse_mode="Markdown"
    )

async def manage_chat_id_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return

    args = context.args
    if not args:
        entries = await recent_chats.get_last_active_chats_verbose(20, context.bot)
        if not entries:
            await update.message.reply_text("\u26a0\ufe0f Nessuna chat trovata.")
            return
        lines = []
        for cid, name in entries:
            path = recent_chats.get_chat_path(cid)
            if path:
                lines.append(f"{escape_markdown(name)} — `{cid}` -> {escape_markdown(path)}")
            else:
                lines.append(f"{escape_markdown(name)} — `{cid}`")
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
        return

    if args[0] == "reset":
        if len(args) < 2:
            await update.message.reply_text("Uso: /manage_chat_id reset <id|this>")
            return
        if args[1] == "this":
            cid = update.effective_chat.id
        else:
            try:
                cid = int(args[1])
            except ValueError:
                await update.message.reply_text("ID non valido")
                return
        recent_chats.reset_chat(cid)
        await update.message.reply_text(f"\u2705 Reset mapping for `{cid}`.", parse_mode="Markdown")
    else:
        await update.message.reply_text("Uso: /manage_chat_id [reset <id>|reset this>")

async def say_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return

    args = context.args
    bot = context.bot

    # Caso 1: /say <chat_id> <messaggio>
    if len(args) >= 2:
        try:
            chat_id = int(args[0])
            text = truncate_message(" ".join(args[1:]))
            await safe_send(bot, chat_id=chat_id, text=text)  # [FIX]
            await update.message.reply_text("\u2705 Messaggio inviato.")
        except Exception as e:
            log_error(f"Errore /say diretto: {e}", e)
            await update.message.reply_text("\u274c Errore nell'invio.")
        return

    # Caso 2: /say @username -> seleziona chat privata
    if len(args) == 1 and args[0].startswith("@"):  # /say @username
        username = args[0]
        log_debug(f"Resolving username {username} via bot.get_chat")
        try:
            chat = await bot.get_chat(username)
            log_debug(
                f"Resolved to chat_id = {chat.id}, type = {chat.type}"
            )
            if chat.type == "private":
                say_proxy.set_target(update.effective_user.id, chat.id)
                context.user_data.pop("say_choices", None)
                await update.message.reply_text(
                    f"\u2709\ufe0f What do you want to send to {username}?",
                    parse_mode="Markdown",
                )
            else:
                await update.message.reply_text(
                    f"\u274c Cannot send to {username}. They must start the chat with the bot first."
                )
        except Exception as e:
            log_error(f"Errore /say @username: {e}", e)
            await update.message.reply_text(
                f"\u274c Cannot send to {username}. They must start the chat with the bot first."
            )
        return

    # Caso 3: /say (senza argomenti) -> mostra ultime chat
    all_entries = await recent_chats.get_last_active_chats_verbose(20, bot)
    entries = all_entries[:10]
    if not entries:
        await update.message.reply_text("\u26a0\ufe0f Nessuna chat recente trovata.")
        return

    # Salva lista in memoria e mostra opzioni
    numbered = "\n".join(
        f"{i+1}. {escape_markdown(name)} \u2014 `{cid}`"
        for i, (cid, name) in enumerate(entries)
    )

    # Elenco aggiuntivo di chat private recenti
    privates = [(cid, name) for cid, name in all_entries if cid > 0][:5]
    if privates:
        private_lines = "\n".join(
            f"{i+1}. {escape_markdown(name)} \u2014 `{cid}`"
            for i, (cid, name) in enumerate(privates)
        )
        numbered += "\n\n\U0001f512 Recent private chats:\n" + private_lines

    numbered += "\n\n\u270f\ufe0f Rispondi con il numero per scegliere la chat."

    say_proxy.clear(update.effective_user.id)  # Assicura pulizia prima della scelta
    context.user_data["say_choices"] = entries

    await update.message.reply_text(numbered, parse_mode="Markdown")

async def handle_say_step(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not await ensure_plugin_loaded(update):
        return

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
        log_debug(f"Inoltro tramite plugin_instance.handle_incoming_message (chat_id={target_chat})")
        try:
            await plugin_instance.handle_incoming_message(context.bot, message, context.user_data)
            response_proxy.clear_target(OWNER_ID)
            say_proxy.clear(OWNER_ID)
        except Exception as e:
            log_error(
                f"Errore durante plugin_instance.handle_incoming_message in /say: {e}",
                e,
            )
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

    try:
        load_plugin(choice)
        await update.message.reply_text(f"\u2705 Modalità LLM aggiornata dinamicamente a `{choice}`.")
    except Exception as e:
        await update.message.reply_text(f"\u274c Errore nel caricamento del plugin: {e}")

async def model_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return

    try:
        models = plugin_instance.get_supported_models()
    except Exception:
        await update.message.reply_text("\u26a0\ufe0f Questo plugin non supporta la selezione del modello.")
        return

    if not models:
        await update.message.reply_text("\u26a0\ufe0f Nessun modello disponibile per questo plugin.")
        return

    if not context.args:
        current = plugin_instance.get_current_model() or models[0]
        msg = f"*Modelli disponibili:*\n" + "\n".join(f"\u2022 `{m}`" for m in models)
        msg += f"\n\nModello attivo: `{current}`"
        msg += "\n\nPer cambiare: `/model <nome>`"
        await update.message.reply_text(msg, parse_mode="Markdown")
        return

    choice = context.args[0]
    if choice not in models:
        await update.message.reply_text(f"\u274c Modello `{choice}` non valido.")
        return

    try:
        plugin_instance.set_current_model(choice)
        await update.message.reply_text(f"\u2705 Modello aggiornato a `{choice}`.")
    except Exception as e:
        await update.message.reply_text(f"\u274c Errore nel cambio modello: {e}")

def telegram_notify(chat_id: int, message: str, reply_to_message_id: int = None):
    import html
    import re
    from telegram import Bot
    from telegram.error import TelegramError
    from telegram.constants import ParseMode

    log_debug(f"[telegram_notify] → CHIAMATO con chat_id={chat_id}")
    log_debug(f"[telegram_notify] → MESSAGGIO:\n{message}")

    bot = Bot(token=BOT_TOKEN)

    # Rende cliccabili eventuali URL
    url_pattern = re.compile(r"https?://\S+")
    match = url_pattern.search(message or "")
    formatted_message = None
    if match:
        def repl(m):
            url = m.group(0)
            return f'<a href="{html.escape(url)}">{html.escape(url)}</a>'

        formatted_message = url_pattern.sub(repl, html.escape(message))

    async def send():
        try:
            text = truncate_message(formatted_message or message)
            await safe_send(
                bot,
                chat_id=chat_id,
                text=text,
                reply_to_message_id=reply_to_message_id,
                parse_mode=ParseMode.HTML if formatted_message else None,
                disable_web_page_preview=True,
            )  # [FIX][telegram retry]
            log_debug(f"[notify] ✅ Messaggio Telegram inviato a {chat_id}")
        except TelegramError as e:
            log_error(f"[notify] ❌ Errore Telegram: {e}", e)
        except Exception as e:
            log_error(f"[notify] ❌ Altro errore nel send(): {e}", e)

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        loop.create_task(send())
    else:
        asyncio.run(send())

# === Avvio ===


async def plugin_startup_callback(application):
    """Launch plugin start() once the bot's event loop is ready."""
    plugin_obj = plugin_instance.get_plugin()
    if plugin_obj and hasattr(plugin_obj, "start"):
        try:
            if asyncio.iscoroutinefunction(plugin_obj.start):
                await plugin_obj.start()
            else:
                plugin_obj.start()
            log_debug("[plugin] Plugin start executed")
        except Exception as e:
            log_error(f"[plugin] Error during post_init start: {e}", e)
    application.create_task(message_queue.start_queue_loop())


def start_bot():


    # 🔁 Passa la funzione di notifica corretta (per i plugin)
    load_plugin(get_active_llm(), notify_fn=telegram_notify)

    # 🌀 Weather fetch subito e loop periodico
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(update_weather())
    start_weather_updater()

    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .post_init(plugin_startup_callback)
        .build()
    )

    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("block", block_user))
    app.add_handler(CommandHandler("block_list", block_list))
    app.add_handler(CommandHandler("unblock", unblock_user))
    app.add_handler(CommandHandler("purge_map", purge_mappings))
    app.add_handler(CommandHandler("last_chats", last_chats_command))
    app.add_handler(CommandHandler("manage_chat_id", manage_chat_id_command))
    app.add_handler(CommandHandler("context", context_command))
    app.add_handler(CommandHandler("llm", llm_command))

    try:
        if plugin_instance.get_supported_models():
            app.add_handler(CommandHandler("model", model_command))
    except Exception as e:
        log_warning(f"Il plugin attivo non supporta modelli: {e}")

    app.add_handler(CommandHandler("say", say_command))
    app.add_handler(CommandHandler("cancel", cancel_response))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    app.add_handler(MessageHandler(
        filters.Chat(OWNER_ID) & (
            filters.TEXT | filters.PHOTO | filters.AUDIO | filters.VOICE |
            filters.VIDEO | filters.Document.ALL
        ),
        handle_say_step
    ))

    app.add_handler(MessageHandler(
        filters.Chat(OWNER_ID) & (
            filters.Sticker.ALL | filters.PHOTO | filters.AUDIO |
            filters.VOICE | filters.VIDEO | filters.Document.ALL
        ),
        handle_incoming_response
    ))

    log_info("🧞‍♀️ Rekku is online.")
    log_info("[telegram_bot] Interface registered as telegram_bot.")

    # Fallback: ensure plugin.start() invoked in case post_init failed
    plugin_obj = plugin_instance.get_plugin()
    if plugin_obj and hasattr(plugin_obj, "start"):
        try:
            if asyncio.iscoroutinefunction(plugin_obj.start):
                asyncio.get_event_loop().create_task(plugin_obj.start())
            else:
                plugin_obj.start()
            log_debug("[plugin] Plugin start scheduled from start_bot")
        except Exception as e:
            log_error(f"[plugin] Fallback start error: {e}", e)

    app.run_polling()

class TelegramInterface:
    def __init__(self, api_id, api_hash, bot_token):
        self.client = TelegramClient('bot', api_id, api_hash).start(bot_token=bot_token)

    async def send_message(self, chat_id, text):
        """Send a message to a specific chat."""
        from core.transport_layer import universal_send
        try:
            await universal_send(self.client.send_message, chat_id, text=text)
            log_debug(f"[telegram_bot] Message sent to {chat_id}: {text}")
        except Exception as e:
            log_error(f"[telegram_bot] Failed to send message to {chat_id}: {e}")

    @staticmethod
    def get_interface_instructions():
        """Return specific instructions for Telegram interface."""
        return """TELEGRAM INTERFACE INSTRUCTIONS:
- Use chat_id for targets (can be negative for groups/channels)
- For groups with topics, include thread_id to reply in the correct topic
- Keep messages under 4096 characters
- Use Markdown formatting:
    * *bold* → `*bold*`
    * _italic_ → `_italic_`
    * __underline__ → `__underline__`
    * ~strikethrough~ → `~strikethrough~`
    * `monospace` → `` `monospace` ``
    * ```code block``` → triple backticks (```)
    * [inline URL](https://example.com) → standard Markdown link
- Escape special characters using a backslash if needed: `_ * [ ] ( ) ~ ` > # + - = | { } . !`
- For groups, always reply in the same chat and thread unless specifically instructed otherwise
- Target should be the exact chat_id from input.payload.source.chat_id
- Thread_id should be the exact thread_id from input.payload.source.thread_id (if present)
- Interface should always be "telegram_bot"
"""

