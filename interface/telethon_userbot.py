from telethon import TelegramClient, events, Button
from telethon.tl.types import PeerUser, PeerChat, PeerChannel
from dotenv import load_dotenv
import os
import re
from collections import deque
import core.plugin_instance as plugin_instance
from core.plugin_instance import load_plugin
from logging_utils import log_debug, log_info, log_warning, log_error
from core.message_sender import detect_media_type, extract_response_target
from core.config import get_active_llm, set_active_llm, list_available_llms
from core.config import OWNER_ID
from core import blocklist, response_proxy, say_proxy, recent_chats
from core.context import context_command
import traceback

load_dotenv()

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
SESSION = os.getenv("SESSION", "rekku_userbot")
OWNER_ID = int(os.getenv("OWNER_ID"))

say_sessions = {}
context_memory = {}
last_selected_chat = {}
message_id = None

client = TelegramClient(SESSION, API_ID, API_HASH)

def escape_markdown(text):
    return re.sub(r'([_*\[\]()~`>#+=|{}.!-])', r'\\\1', text)

async def ensure_plugin_loaded(event):
    if plugin_instance.plugin is None:
        log_error("Nessun plugin LLM caricato.")
        await event.reply("⚠️ Nessun plugin LLM attivo. Usa .llm per selezionarne uno.")
        return False
    return True

def resolve_forwarded_target(message):
    if getattr(message, "fwd_from", None):
        if getattr(message.fwd_from, "from_id", None):
            return message.fwd_from.from_id.user_id, message.fwd_from.channel_post
    tracked = plugin_instance.get_target(message.id)
    if tracked:
        return tracked["chat_id"], tracked["message_id"]
    return None, None

@client.on(events.NewMessage(pattern=r"\.block (\d+)"))
async def block_user(event):
    if event.sender_id != OWNER_ID:
        return
    try:
        to_block = int(event.pattern_match.group(1))
        blocklist.block_user(to_block)
        await event.reply(f"\U0001f6ab Utente {to_block} bloccato.")
    except Exception:
        await event.reply("\u274c Usa: .block <user_id>")

@client.on(events.NewMessage(pattern=r"\.block_list"))
async def block_list(event):
    if event.sender_id != OWNER_ID:
        return
    blocked = blocklist.get_block_list()
    if not blocked:
        await event.reply("\u2705 Nessun utente bloccato.")
    else:
        await event.reply("\U0001f6ab Utenti bloccati:\n" + "\n".join(map(str, blocked)))

@client.on(events.NewMessage(pattern=r"\.unblock (\d+)"))
async def unblock_user(event):
    if event.sender_id != OWNER_ID:
        return
    try:
        to_unblock = int(event.pattern_match.group(1))
        blocklist.unblock_user(to_unblock)
        await event.reply(f"\u2705 Utente {to_unblock} sbloccato.")
    except Exception:
        await event.reply("\u274c Usa: .unblock <user_id>")

@client.on(events.NewMessage(pattern=r"\.last_chats"))
async def last_chats_command(event):
    if event.sender_id != OWNER_ID:
        return
    entries = await recent_chats.get_last_active_chats_verbose(10, client)
    if not entries:
        await event.reply("\u26a0\ufe0f No recent chat found.")
        return
    lines = [f"[{escape_markdown(name)}](tg://user?id={cid}) — `{cid}`" for cid, name in entries]
    await event.reply(
        "\U0001f553 Ultime chat attive:\n" + "\n".join(lines),
        parse_mode="md"
    )

@client.on(events.NewMessage(pattern=r"\.help"))
async def help_command(event):
    if event.sender_id != OWNER_ID:
        return
    from core.context import get_context_state
    context_status = "attiva ✅" if get_context_state() else "disattiva ❌"
    llm_mode = get_active_llm()
    help_text = (
        f"🧞‍♀️ *Rekku – Comandi disponibili*\n\n"
        "*🧠 Modalità context*\n"
        f"`.context` – Attiva/disattiva la cronologia nei messaggi inoltrati, attualmente *{context_status}*\n\n"
        "*✏️ Comando .say*\n"
        "`.say` – Seleziona una chat dalle più recenti\n"
        "`.say <id> <messaggio>` – Invia direttamente un messaggio a una chat\n\n"
        "*🧩 Modalità manuale*\n"
        "Rispondi a un messaggio inoltrato con testo o contenuti (sticker, foto, audio, file, ecc.)\n"
        "`.cancel` – Annulla un invio in attesa\n\n"
        "*🧱 Gestione utenti*\n"
        "`.block <user_id>` – Blocca un utente\n"
        "`.unblock <user_id>` – Sblocca un utente\n"
        "`.block_list` – Elenca gli utenti bloccati\n\n"
        "*⚙️ Modalità LLM*\n"
        f"`.llm` – Mostra e seleziona il motore attuale (attivo: `{llm_mode}`)\n"
        "\n*📋 Varie*\n"
        "`.last_chats` – Ultime chat attive\n"
    )
    await event.reply(help_text, parse_mode="md")

@client.on(events.NewMessage(pattern=r"\.llm(?: (.+))?"))
async def llm_command(event):
    if event.sender_id != OWNER_ID:
        return
    args = event.pattern_match.group(1)
    current = get_active_llm()
    available = list_available_llms()
    if not args:
        msg = f"*LLM attivo:* `{current}`\n\n*Disponibili:*"
        msg += "\n" + "\n".join(f"\u2022 `{name}`" for name in available)
        msg += "\n\nPer cambiare: `.llm <nome>`"
        await event.reply(msg, parse_mode="md")
        return
    choice = args.strip()
    if choice not in available:
        await event.reply(f"\u274c LLM `{choice}` non trovato.")
        return
    try:
        load_plugin(choice)
        set_active_llm(choice)
        await event.reply(f"\u2705 Modalità LLM aggiornata dinamicamente a `{choice}`.")
    except Exception as e:
        await event.reply(f"\u274c Errore nel caricamento del plugin: {e}")

@client.on(events.NewMessage(pattern=r"\.say(?: (\d+) (.+))?"))
async def say_command(event):
    if event.sender_id != OWNER_ID:
        return
    args = event.pattern_match.groups()
    # Caso 1: .say <chat_id> <messaggio>
    if args[0] and args[1]:
        try:
            chat_id = int(args[0])
            text = args[1]
            await client.send_message(chat_id, text)
            await event.reply("\u2705 Messaggio inviato.")
        except Exception as e:
            log_error(f"Errore .say diretto: {e}")
            await event.reply("\u274c Error during sending.")
        return
    # Caso 2: .say (senza argomenti)
    entries = await recent_chats.get_last_active_chats_verbose(10, client)
    if not entries:
        await event.reply("\u26a0\ufe0f No recent chat found.")
        return
    numbered = "\n".join(f"{i+1}. {name} — `{cid}`" for i, (cid, name) in enumerate(entries))
    numbered += "\n\n\u270f\ufe0f Reply with the number to choose the chat."
    say_proxy.clear(event.sender_id)
    say_sessions[event.sender_id] = entries
    await event.reply(numbered)

@client.on(events.NewMessage())
async def handle_message(event):
    if not await ensure_plugin_loaded(event):
        return
    message = event.message
    if not message or not message.sender_id:
        return
    user_id = message.sender_id
    text = message.message or ""
    # Step interattivo /say
    if user_id == OWNER_ID and user_id in say_sessions:
        stripped = text.strip()
        if stripped.isdigit():
            index = int(stripped) - 1
            choices = say_sessions[user_id]
            if 0 <= index < len(choices):
                selected_chat_id = choices[index][0]
                say_proxy.set_target(user_id, selected_chat_id)
                del say_sessions[user_id]
                await event.reply(
                    "✅ Chat selezionata.\n\nOra inviami il *messaggio*, una *foto*, un *file*, un *audio* o qualsiasi altro contenuto da inoltrare.",
                    parse_mode="md"
                )
                return
        await event.reply("❌ Selezione non valida. Invia un numero corretto.")
        return
    # Utente bloccato
    if blocklist.is_blocked(user_id) and user_id != OWNER_ID:
        return
    # Risposta owner a messaggio inoltrato
    if user_id == OWNER_ID and message.is_reply:
        reply_msg_id = message.reply_to_msg_id
        original = plugin_instance.get_target(reply_msg_id)
        if original:
            await client.send_message(
                original["chat_id"],
                text,
                reply_to=original["message_id"]
            )
            await event.reply("✅ Risposta inviata.")
        else:
            await event.reply("⚠️ Nessun messaggio da rispondere trovato.")
        return
    # Passa al plugin
    try:
        await plugin_instance.handle_incoming_message(client, message, context_memory)
    except Exception as e:
        log_error(f"plugin_instance.handle_incoming_message fallito: {e}")

def main():
    def telegram_notify(chat_id: int, message: str, reply_to_message_id: int = None):
        async def send():
            try:
                await client.send_message(
                    chat_id,
                    message,
                    reply_to=reply_to_message_id
                )
                log_debug(f"[notify] Messaggio Telegram inviato a {chat_id}")
            except Exception as e:
                log_error(f"[notify] Fallito invio messaggio Telegram: {e}")
        import asyncio
        asyncio.create_task(send())
    plugin_instance.load_plugin(get_active_llm(), notify_fn=telegram_notify)
    log_info("🧞‍♀️ Rekku Userbot (Telethon) is online.")
    client.run_until_disconnected()

if __name__ == "__main__":
    main()