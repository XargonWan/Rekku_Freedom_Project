from telethon import TelegramClient, events, Button
from telethon.tl.types import PeerUser, PeerChat, PeerChannel
try:
    from dotenv import load_dotenv  # type: ignore
except Exception:  # pragma: no cover - fallback if python-dotenv not installed
    def load_dotenv(*args, **kwargs):
        return False
import os
import re
import asyncio
from collections import deque
import core.plugin_instance as plugin_instance
from core.logging_utils import log_debug, log_info, log_warning, log_error
from core.message_sender import detect_media_type, extract_response_target
from core.config import set_active_llm, list_available_llms, get_active_llm
from core.config import TRAINER_ID
from core import blocklist, response_proxy, say_proxy, recent_chats
from core.context import context_command
from core.auto_response import request_llm_delivery
from core.core_initializer import register_interface, core_initializer
import traceback

load_dotenv()

# Provide safe defaults so this module can be imported even when env vars are missing
API_ID = int(os.getenv("API_ID", "0") or "0")
API_HASH = os.getenv("API_HASH", "")
SESSION = os.getenv("SESSION", "rekku_userbot")
TRAINER_ID = int(os.getenv("TRAINER_ID", "0") or "0")

say_sessions = {}
context_memory = {}
last_selected_chat = {}
message_id = None

client = TelegramClient(SESSION, API_ID, API_HASH)
register_interface("telegram_userbot", client)
log_info("[telethon_userbot] Registered TelethonUserbot")

def escape_markdown(text):
    return re.sub(r'([_*\[\]()~`>#+=|{}.!-])', r'\\\1', text)

async def ensure_plugin_loaded(event):
    if plugin_instance.plugin is None:
        log_error("No LLM plugin loaded.")
        await event.reply("⚠️ No active LLM plugin. Use .llm to select one.")
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
    if event.sender_id != TRAINER_ID:
        return
    try:
        to_block = int(event.pattern_match.group(1))
        blocklist.block_user(to_block)
        await event.reply(f"🚫 User {to_block} blocked.")
    except Exception:
        await event.reply("❌ Use: .block <user_id>")

@client.on(events.NewMessage(pattern=r"\.block_list"))
async def block_list(event):
    if event.sender_id != TRAINER_ID:
        return
    blocked = blocklist.get_block_list()
    if not blocked:
        await event.reply("✅ No blocked users.")
    else:
        await event.reply("🚫 Blocked users:\n" + "\n".join(map(str, blocked)))

@client.on(events.NewMessage(pattern=r"\.unblock (\d+)"))
async def unblock_user(event):
    if event.sender_id != TRAINER_ID:
        return
    try:
        to_unblock = int(event.pattern_match.group(1))
        blocklist.unblock_user(to_unblock)
        await event.reply(f"✅ User {to_unblock} unblocked.")
    except Exception:
        await event.reply("❌ Use: .unblock <user_id>")

@client.on(events.NewMessage(pattern=r"\.last_chats"))
async def last_chats_command(event):
    if event.sender_id != TRAINER_ID:
        return
    entries = await recent_chats.get_last_active_chats_verbose(10, client)
    if not entries:
        await event.reply("⚠️ No recent chat found.")
        return
    lines = [f"[{escape_markdown(name)}](tg://user?id={cid}) — `{cid}`" for cid, name in entries]
    await event.reply(
        "🕓 Recent active chats:\n" + "\n".join(lines),
        parse_mode="md"
    )

@client.on(events.NewMessage(pattern=r"\.help"))
async def help_command(event):
    if event.sender_id != TRAINER_ID:
        return
    from core.context import get_context_state
    context_status = "active ✅" if get_context_state() else "inactive ❌"
    llm_mode = "LLM managed centrally in initialize_core_components"
    help_text = (
        f"🧞‍♀️ *Rekku – Available Commands*\n\n"
        "*🧠 Context Mode*\n"
        f"`.context` – Toggle history in forwarded messages, currently *{context_status}*\n\n"
        "*✏️ .say Command*\n"
        "`.say` – Select a chat from recent ones\n"
        "`.say <id> <message>` – Send a message directly to a chat\n\n"
        "*🧩 Manual Mode*\n"
        "Reply to a forwarded message with text or content (stickers, photos, audio, files, etc.)\n"
        "`.cancel` – Cancel a pending send\n\n"
        "*🧱 User Management*\n"
        "`.block <user_id>` – Block a user\n"
        "`.unblock <user_id>` – Unblock a user\n"
        "`.block_list` – List blocked users\n\n"
        "*⚙️ LLM Mode*\n"
        f"`.llm` – Show and select current engine (active: `{llm_mode}`)\n"
        "\n*📋 Miscellaneous*\n"
        "`.last_chats` – Recent active chats\n"
    )
    await event.reply(help_text, parse_mode="md")

@client.on(events.NewMessage(pattern=r"\.llm(?: (.+))?"))
async def llm_command(event):
    if event.sender_id != TRAINER_ID:
        return
    args = event.pattern_match.group(1)
    current = await get_active_llm()
    available = list_available_llms()
    if not args:
        msg = f"*Active LLM:* `{current}`\n\n*Available:*"
        msg += "\n" + "\n".join(f"• `{name}`" for name in available)
        msg += "\n\nTo change: `.llm <name>`"
        await event.reply(msg, parse_mode="md")
        return
    choice = args.strip()
    if choice not in available:
        await event.reply(f"❌ LLM `{choice}` not found.")
        return
    try:
        await set_active_llm(choice)
        
        # We don't load plugins here - that's the core's job
        # The system will restart with the new LLM on next restart
        
        await event.reply(f"✅ LLM mode updated to `{choice}`. Restart to apply changes.")
    except Exception as e:
        await event.reply(f"❌ Error changing LLM: {e}")

@client.on(events.NewMessage(pattern=r"\.say(?: (\d+) (.+))?"))
async def say_command(event):
    if event.sender_id != TRAINER_ID:
        return
    args = event.pattern_match.groups()
    # Case 1: .say <chat_id> <message>
    if args[0] and args[1]:
        try:
            chat_id = int(args[0])
            text = args[1]
            await client.send_message(chat_id, text)
            await event.reply("✅ Message sent.")
        except Exception as e:
            log_error(f"Direct .say error: {repr(e)}", e)
            await event.reply("❌ Error during sending.")
        return
    # Case 2: .say (no arguments)
    entries = await recent_chats.get_last_active_chats_verbose(10, client)
    if not entries:
        await event.reply("⚠️ No recent chat found.")
        return
    numbered = "\n".join(f"{i+1}. {name} — `{cid}`" for i, (cid, name) in enumerate(entries))
    numbered += "\n\n✏️ Reply with the number to choose the chat."
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
    # Interactive /say step
    if user_id == TRAINER_ID and user_id in say_sessions:
        stripped = text.strip()
        if stripped.isdigit():
            index = int(stripped) - 1
            choices = say_sessions[user_id]
            if 0 <= index < len(choices):
                selected_chat_id = choices[index][0]
                say_proxy.set_target(user_id, selected_chat_id)
                del say_sessions[user_id]
                await event.reply(
                    "✅ Chat selected.\n\nNow send me the *message*, a *photo*, a *file*, *audio* or any other content to forward.",
                    parse_mode="md"
                )
                return
        await event.reply("❌ Invalid selection. Send a correct number.")
        return
    # Blocked user
    if blocklist.is_blocked(user_id) and user_id != TRAINER_ID:
        return
    # Trainer reply to forwarded message
    if user_id == TRAINER_ID and message.is_reply:
        reply_msg_id = message.reply_to_msg_id
        original = plugin_instance.get_target(reply_msg_id)
        if original:
            await client.send_message(
                original["chat_id"],
                text,
                reply_message_id=original["message_id"]
            )
            await event.reply("✅ Reply sent.")
        else:
            await event.reply("⚠️ No message to reply to found.")
        return
    # Pass to plugin via auto-response system for autonomous userbot interactions
    try:
        await request_llm_delivery(
            message=message,
            interface=client,
            context=context_memory,
            reason="telethon_userbot_autonomous"
        )
    except Exception as e:
        log_error(
            f"auto-response delivery failed for telethon userbot: {e}",
            e,
        )

async def main():
    def telegram_notify(chat_id: int, message: str, reply_to_message_id: int = None):
        async def send():
            try:
                await client.send_message(
                    chat_id,
                    message,
                    reply_message_id=reply_to_message_id
                )
                log_debug(f"[notify] Telegram message sent to {chat_id}")
            except Exception as e:
                log_error(f"[notify] Failed to send Telegram message: {repr(e)}", e)
        import asyncio
        asyncio.create_task(send())
    
    # Initialize core system with notify function
    await core_initializer.initialize_all(notify_fn=telegram_notify)
    
    log_info("🧞‍♀️ Rekku Userbot (Telethon) is online.")
    
    # Register this interface with the core
    core_initializer.register_interface("telegram_userbot")
    
    client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
