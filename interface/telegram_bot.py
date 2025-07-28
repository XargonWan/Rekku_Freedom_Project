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
from core.config import BOT_TOKEN, BOT_USERNAME, TRAINER_ID
# Import mention detector to recognize Rekku aliases even without explicit @username
from core.mention_utils import is_rekku_mentioned, is_message_for_bot
import core.plugin_instance as plugin_instance
from core.weather import start_weather_updater, update_weather
import traceback
from telethon import TelegramClient
from core.action_parser import initialize_core

# Load variables from .env
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
    """Given a message (presumably a reply to a forwarded message),
    try to reconstruct the original chat_id and message_id."""

    if hasattr(message, "forward_from_chat") and hasattr(message, "forward_from_message_id"):
        if message.forward_from_chat and message.forward_from_message_id:
            return message.forward_from_chat.id, message.forward_from_message_id

    tracked = plugin_instance.get_target(message.message_id)
    if tracked:
        return tracked["chat_id"], tracked["message_id"]

    return None, None

# === Block commands ===

async def block_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != TRAINER_ID:
        return
    try:
        to_block = int(context.args[0])
        blocklist.block_user(to_block)
        log_debug(f"User {to_block} blocked.")
        await update.message.reply_text(f"\U0001f6ab User {to_block} blocked.")
    except (IndexError, ValueError):
        await update.message.reply_text("❌ Use: /block <user_id>")

async def block_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != TRAINER_ID:
        return
    blocked = blocklist.get_block_list()
    log_debug("Blocked users list requested.")
    if not blocked:
        await update.message.reply_text("\u2705 No users blocked.")
    else:
        await update.message.reply_text("\U0001f6ab Blocked users:\n" + "\n".join(map(str, blocked)))

async def unblock_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != TRAINER_ID:
        return
    try:
        to_unblock = int(context.args[0])
        blocklist.unblock_user(to_unblock)
        log_debug(f"User {to_unblock} unblocked.")
        await update.message.reply_text(f"\u2705 User {to_unblock} unblocked.")
    except (IndexError, ValueError):
        await update.message.reply_text("❌ Use: /unblock <user_id>")

async def purge_mappings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != TRAINER_ID:
        return
    # Ensure table exists even if manual plugin never loaded
    await message_map.init_table()
    try:
        days = int(context.args[0]) if context.args else 7
    except ValueError:
        await update.message.reply_text("❌ Use: /purge_map [days]")
        return
    deleted = await message_map.purge_old_entries(days * 86400)
    await update.message.reply_text(
        f"\U0001f5d1 Removed {deleted} mappings older than {days} days."
    )


async def handle_incoming_response(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not await ensure_plugin_loaded(update):
        return

    if update.effective_user.id != TRAINER_ID:
        log_debug("Message ignored: not from TRAINER_ID")
        return

    message = update.message
    if not message:
        log_debug("❌ No message present, aborting.")
        return

    media_type = detect_media_type(message)
    log_debug(f"✅ handle_incoming_response: media_type = {media_type}; reply_to = {bool(message.reply_to_message)}")

    # === 1. Prova target da response_proxy (es. /say)
    target = response_proxy.get_target(TRAINER_ID)
    log_debug(f"Initial target from response_proxy = {target}")

    # === 2. If replying to a message, search in plugin mapping
    if not target and message.reply_to_message:
        reply = message.reply_to_message
        log_debug(f"Reply to trainer_message_id={reply.message_id}")
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
                log_debug(f"Found target via plugin_instance.get_target({mid}): {target}")
                break
        if not target:
            log_debug("❌ No mapping found in plugin")

    # === 3. Fallback from /say
    if not target:
        fallback = say_proxy.get_target(TRAINER_ID)
        log_debug(f"Fallback from say_proxy = {fallback}")
        if fallback and fallback != "EXPIRED":
            target = {
                "chat_id": fallback,
                "message_id": None,
                "type": media_type
            }
            log_debug(f"Target set from say_proxy: {target}")
        elif fallback == "EXPIRED":
            await message.reply_text("⏳ Timeout expired, run /say again.")
            return

    # === 4. If still nothing, abort
    if not target:
        log_error("No target found for sending.")
        await message.reply_text("⚠️ No recipient detected. Use /say or reply to a forwarded message.")
        return

    # === 5. Send content
    chat_id = target["chat_id"]
    reply_to = target["message_id"]
    content_type = target["type"]

    log_debug(f"Sending media_type={content_type} to chat_id={chat_id}, reply_to={reply_to}")
    success, feedback = await send_content(context.bot, chat_id, message, content_type, reply_to)

    await message.reply_text(feedback)

    if success:
        log_debug("✅ Sending successful. Cleaning proxy.")
        response_proxy.clear_target(TRAINER_ID)
        say_proxy.clear(TRAINER_ID)
    else:
        log_error("Sending failed.")


# === Generic command for sticker/audio/photo/file/video ===

async def handle_response_command(update: Update, context: ContextTypes.DEFAULT_TYPE, content_type: str):

    if not await ensure_plugin_loaded(update):
        return

    if update.effective_user.id != TRAINER_ID:
        return

    message = update.message
    if not message.reply_to_message:
        await message.reply_text("⚠️ You must use this command in reply to a message forwarded by Rekku.")
        return

    chat_id, message_id = resolve_forwarded_target(message.reply_to_message)

    if not chat_id or not message_id:
        await message.reply_text("❌ Invalid message for this command.")
        return

    response_proxy.set_target(TRAINER_ID, chat_id, message_id, content_type)
    log_debug(f"Target {content_type} set: chat_id={chat_id}, message_id={message_id}")
    await safe_send(
        context.bot,
        chat_id=TRAINER_ID,
        text=f"📎 Send me the {content_type.upper()} file to use as response."
    )  # [FIX]

async def cancel_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != TRAINER_ID:
        return
    if response_proxy.has_pending(TRAINER_ID):
        response_proxy.clear_target(TRAINER_ID)
        say_proxy.clear(TRAINER_ID)
        log_debug("Response sending cancelled.")
        await update.message.reply_text("❌ Sending cancelled.")
    else:
        await update.message.reply_text("⚠️ No active send to cancel.")


async def test_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    log_debug("/test received")
    await update.message.reply_text("✅ Test OK")

async def last_chats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != TRAINER_ID:
        return

    entries = await recent_chats.get_last_active_chats_verbose(10, context.bot)
    if not entries:
        await update.message.reply_text("⚠️ No recent chat found.")
        return

    lines = [f"[{name}](tg://user?id={cid}) — `{cid}`" for cid, name in entries]
    await update.message.reply_text(
        "\U0001f553 Last active chats:\n" + "\n".join(lines),
        parse_mode="Markdown"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    log_info(f"[telegram_bot] Received message update: {update}")

    if not await ensure_plugin_loaded(update):
        return

    message = update.message
    if not message or not message.from_user:
        log_debug("Message ignored (empty or no sender)")
        return

    user = message.from_user
    user_id = user.id
    username = user.full_name
    usertag = f"@{user.username}" if user.username else "(no tag)"
    text = message.text or ""
    
    log_info(f"[telegram_bot] Processing message from {username} ({user_id}): {text}")

    # Track context
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
    await recent_chats.track_chat(message.chat_id, chat_meta)
    log_debug(f"context_memory[{message.chat_id}] = {list(context_memory[message.chat_id])}")

    # Interactive /say step
    if message.chat.type == "private" and user_id == TRAINER_ID and context.user_data.get("say_choices"):
        await handle_say_step(update, context)
        return

    log_debug(f"Message from {user_id} ({message.chat.type}): {text}")

    # Blocked user
    if await blocklist.is_blocked(user_id) and user_id != TRAINER_ID:
        log_debug(f"User {user_id} is blocked. Ignoring message.")
        return

    # trainer reply to forwarded message
    if message.chat.type == "private" and user_id == TRAINER_ID and message.reply_to_message:
        reply_msg_id = message.reply_to_message.message_id
        log_debug(f"Reply to trainer_message_id={reply_msg_id}")
        original = plugin_instance.get_target(reply_msg_id)
        if original:
            log_debug(f"Trainer replies to message {original}")
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

    # === FILTER: Only respond if mentioned or in reply
    log_debug(f"[telegram_bot] Checking if message is for bot: chat_type={message.chat.type}, "
              f"text='{text[:50]}{'...' if len(text) > 50 else ''}', "
              f"reply_to={message.reply_to_message is not None}")
    
    if message.reply_to_message:
        log_debug(f"[telegram_bot] Reply to message from user ID: {message.reply_to_message.from_user.id if message.reply_to_message.from_user else 'None'}, "
                  f"username: {message.reply_to_message.from_user.username if message.reply_to_message.from_user else 'None'}")
    
    is_for_bot = await is_message_for_bot(message, context.bot)
    log_debug(f"[telegram_bot] is_message_for_bot result: {is_for_bot}")
    
    if not is_for_bot:
        log_debug("Ignoring message: no Rekku mention detected.")
        return

    # === Forward to centralized queue
    try:
        await message_queue.enqueue(context.bot, message, context_memory)
    except Exception as e:
        log_error(f"message_queue enqueue failed: {repr(e)}", e)
        await message.reply_text("⚠️ Error processing message.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from core.context import get_context_state
    from core.config import get_active_llm

    if update.effective_user.id != TRAINER_ID:
        return

    context_status = "active ✅" if get_context_state() else "inactive ❌"
    llm_mode = await get_active_llm()

    help_text = (
        f"🧞‍♀️ *Rekku – Available Commands*\n\n"
        "*🧠 Context Mode*\n"
        f"`/context` – Enable/disable history in forwarded messages, currently *{context_status}*\n\n"
        "*✏️ /say Command*\n"
        "`/say` – Select a chat from recent ones\n"
        "`/say <id> <message>` – Send a message directly to a chat\n\n"
        "*🧩 Manual Mode*\n"
        "Reply to a forwarded message with text or content (stickers, photos, audio, files, etc.)\n"
        "`/cancel` – Cancel a pending send\n\n"
        "*🧱 User Management*\n"
        "`/block <user_id>` – Block a user\n"
        "`/unblock <user_id>` – Unblock a user\n"
        "`/block_list` – List blocked users\n\n"
        "*⚙️ LLM Mode*\n"
        f"`/llm` – Show and select current engine (active: `{llm_mode}`)\n"
    )

    # Add /model if supported
    try:
        models = plugin_instance.get_supported_models()
        if models:
            current_model = plugin_instance.get_current_model() or models[0]
            help_text += f"`/model` – View or set active model (active: `{current_model}`)\n"
    except Exception:
        pass
        current_model = None
        try:
            models = plugin_instance.get_supported_models()
            if models:
                current_model = plugin_instance.get_current_model() or models[0]
                help_text += f"`/model` – View or set active model (active: `{current_model}`)\n"
        except Exception:
            pass
            try:
                current_model = plugin_instance.get_current_model()
            except Exception:
                pass

        if current_model:
            help_text += f"`/model` – View or set active model (active: `{current_model}`)\n"
        else:
            help_text += "`/model` – View or set active model\n"

    help_text += (
        "\n*📋 Misc*\n"
        "`/last_chats` – Last active chats\n"
        "`/purge_map [days]` – Purge old mappings\n"
        "`/clean_chat_link <chat_id>` – Remove the link between a Telegram chat and ChatGPT.\n"
    )

    await update.message.reply_text(help_text, parse_mode="Markdown")

def escape_markdown(text):
    return re.sub(r'([_*\[\]()~`>#+=|{}.!-])', r'\\\1', text)

async def last_chats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != TRAINER_ID:
        return

    entries = await recent_chats.get_last_active_chats_verbose(10, context.bot)
    if not entries:
        await update.message.reply_text("⚠️ No recent chat found.")
        return

    lines = [f"[{escape_markdown(name)}](tg://user?id={cid}) — `{cid}`" for cid, name in entries]
    await update.message.reply_text(
        "\U0001f553 Last active chats:\n" + "\n".join(lines),
        parse_mode="Markdown"
    )

async def manage_chat_id_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != TRAINER_ID:
        return

    args = context.args
    if not args:
        entries = await recent_chats.get_last_active_chats_verbose(20, context.bot)
        if not entries:
            await update.message.reply_text("⚠️ No chat found.")
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
            await update.message.reply_text("Usage: /manage_chat_id reset <id|this>")
            return
        if args[1] == "this":
            cid = update.effective_chat.id
        else:
            try:
                cid = int(args[1])
            except ValueError:
                await update.message.reply_text("Invalid ID")
                return
        await recent_chats.reset_chat(cid)
        await update.message.reply_text(f"✅ Reset mapping for `{cid}`.", parse_mode="Markdown")
    else:
        await update.message.reply_text("Usage: /manage_chat_id [reset <id>|reset this>")

async def say_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != TRAINER_ID:
        return

    args = context.args
    bot = context.bot

    # Case 1: /say <chat_id> <message>
    if len(args) >= 2:
        try:
            chat_id = int(args[0])
            text = truncate_message(" ".join(args[1:]))
            await safe_send(bot, chat_id=chat_id, text=text)  # [FIX]
            await update.message.reply_text("✅ Message sent.")
        except Exception as e:
            log_error(f"Error /say direct: {repr(e)}", e)
            await update.message.reply_text("❌ Error sending.")
        return

    # Case 2: /say @username -> select private chat
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
            log_error(f"Error /say @username: {repr(e)}", e)
            await update.message.reply_text(
                f"❌ Cannot send to {username}. They must start the chat with the bot first."
            )
        return

    # Case 3: /say (no arguments) -> show recent chats
    all_entries = await recent_chats.get_last_active_chats_verbose(20, bot)
    entries = all_entries[:10]
    if not entries:
        await update.message.reply_text("⚠️ No recent chat found.")
        return

    # Save list in memory and show options
    numbered = "\n".join(
        f"{i+1}. {escape_markdown(name)} — `{cid}`"
        for i, (cid, name) in enumerate(entries)
    )

    # Additional list of recent private chats
    privates = [(cid, name) for cid, name in all_entries if cid > 0][:5]
    if privates:
        private_lines = "\n".join(
            f"{i+1}. {escape_markdown(name)} — `{cid}`"
            for i, (cid, name) in enumerate(privates)
        )
        numbered += "\n\n🔒 Recent private chats:\n" + private_lines

    numbered += "\n\n✏️ Reply with the number to choose the chat."

    say_proxy.clear(update.effective_user.id)  # Ensure cleanup before choice
    context.user_data["say_choices"] = entries

    await update.message.reply_text(numbered, parse_mode="Markdown")

async def handle_say_step(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not await ensure_plugin_loaded(update):
        return

    user_id = update.effective_user.id
    message = update.message

    target_chat = say_proxy.get_target(user_id)

    if target_chat == "EXPIRED":
        await message.reply_text("⏳ Time expired. Use /say again.")
        return

    # If target not yet chosen, always try to interpret text as number
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
                        "✅ Chat selected.\n\nNow send me the *message*, a *photo*, a *file*, an *audio* or any other content to forward.",
                        parse_mode="Markdown"
                    )
                    return
            except Exception:
                pass

        await message.reply_text("❌ Invalid selection. Send a correct number.")
        return

    # Chat selected → forward content through plugin
    if target_chat:
        log_debug(f"Forwarding via plugin_instance.handle_incoming_message (chat_id={target_chat})")
        try:
            await plugin_instance.handle_incoming_message(context.bot, message, context.user_data)
            response_proxy.clear_target(TRAINER_ID)
            say_proxy.clear(TRAINER_ID)
        except Exception as e:
            log_error(
                f"Error during plugin_instance.handle_incoming_message in /say: {e}",
                e,
            )
            await message.reply_text("❌ Error sending message.")

async def llm_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    log_info(f"[telegram_bot] LLM command received from user {update.effective_user.id}")
    
    if update.effective_user.id != TRAINER_ID:
        log_warning(f"[telegram_bot] LLM command rejected: user {update.effective_user.id} != TRAINER_ID {TRAINER_ID}")
        return

    args = context.args
    log_info(f"[telegram_bot] LLM command args: {args}")
    
    current = await get_active_llm()
    available = list_available_llms()

    if not args:
        msg = f"*Active LLM:* `{current}`\n\n*Available:*"
        msg += "\n" + "\n".join(f"• `{name}`" for name in available)
        msg += "\n\nTo change: `/llm <name>`"
        await update.message.reply_text(msg, parse_mode="Markdown")
        return

    choice = args[0]
    if choice not in available:
        await update.message.reply_text(f"❌ LLM `{choice}` not found.")
        return

    try:
        from core.config import set_active_llm
        await set_active_llm(choice)
        
        # Reload system with new LLM
        from core.core_initializer import core_initializer
        await core_initializer.initialize_all(notify_fn=telegram_notify)
        
        await update.message.reply_text(f"✅ LLM mode dynamically updated to `{choice}`.")
    except Exception as e:
        await update.message.reply_text(f"❌ Error loading plugin: {e}")

async def model_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != TRAINER_ID:
        return

    try:
        models = plugin_instance.get_supported_models()
    except Exception:
        await update.message.reply_text("⚠️ This plugin does not support model selection.")
        return

    if not models:
        await update.message.reply_text("⚠️ No models available for this plugin.")
        return

    if not context.args:
        current = plugin_instance.get_current_model() or models[0]
        msg = f"*Available models:*\n" + "\n".join(f"• `{m}`" for m in models)
        msg += f"\n\nActive model: `{current}`"
        msg += "\n\nTo change: `/model <name>`"
        await update.message.reply_text(msg, parse_mode="Markdown")
        return

    choice = context.args[0]
    if choice not in models:
        await update.message.reply_text(f"❌ Model `{choice}` not valid.")
        return

    try:
        plugin_instance.set_current_model(choice)
        await update.message.reply_text(f"✅ Model updated to `{choice}`.")
    except Exception as e:
        await update.message.reply_text(f"❌ Error changing model: {e}")

def telegram_notify(chat_id: int, message: str, reply_to_message_id: int = None):
    import html
    import re
    from telegram import Bot
    from telegram.error import TelegramError
    from telegram.constants import ParseMode

    log_debug(f"[telegram_notify] → CALLED with chat_id={chat_id}")
    log_debug(f"[telegram_notify] → MESSAGE:\n{message}")

    bot = Bot(token=BOT_TOKEN)

    # Make URLs clickable
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
            log_debug(f"[notify] ✅ Telegram message sent to {chat_id}")
        except TelegramError as e:
            log_error(f"[notify] ❌ Telegram error: {repr(e)}", e)
        except Exception as e:
            log_error(f"[notify] ❌ Other error in send(): {repr(e)}", e)

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        loop.create_task(send())
    else:
        asyncio.run(send())

# === Startup ===


async def plugin_startup_callback(application):
    """Launch plugin start() once the bot's event loop is ready."""
    # Start pending async plugins
    from core.core_initializer import core_initializer
    await core_initializer.start_pending_async_plugins()

    # Also try to start the main LLM plugin if it has a start method
    plugin_obj = plugin_instance.get_plugin()
    if plugin_obj and hasattr(plugin_obj, "start"):
        try:
            if asyncio.iscoroutinefunction(plugin_obj.start):
                await plugin_obj.start()
            else:
                plugin_obj.start()
            log_debug("[plugin] Plugin start executed")
        except Exception as e:
            log_error(f"[plugin] Error during post_init start: {repr(e)}", e)

    # Start the queue loop after the application is ready
    application.create_task(message_queue.start_queue_loop())


async def start_bot():
    log_info("[telegram_bot] start_bot() function called")
    
    # Log system state at startup and initialize with Telegram notify function
    try:
        log_info("[telegram_bot] Importing core_initializer...")
        from core.core_initializer import core_initializer
        log_info("[telegram_bot] Initializing core components...")
        await core_initializer.initialize_all(notify_fn=telegram_notify)
        log_info("[telegram_bot] Core components initialized successfully")
    except Exception as e:
        log_error(f"[telegram_bot] Error in core initialization: {repr(e)}")
        raise

    # 🌀 Weather fetch immediately and periodic loop
    try:
        log_info("[telegram_bot] Fetching initial weather...")
        await update_weather()
        log_info("[telegram_bot] Starting weather updater...")
        start_weather_updater()
        log_info("[telegram_bot] Weather components initialized")
    except Exception as e:
        log_error(f"[telegram_bot] Error in weather initialization: {repr(e)}")
        raise

    try:
        log_info("[telegram_bot] Building Telegram application...")
        app = (
            ApplicationBuilder()
            .token(BOT_TOKEN)
            .post_init(plugin_startup_callback)
            .build()
        )
        log_info("[telegram_bot] Telegram application built successfully")
        log_info(f"[telegram_bot] TRAINER_ID configured as: {TRAINER_ID}")
        log_info(f"[telegram_bot] BOT_TOKEN configured: {'Yes' if BOT_TOKEN else 'No'}")

        log_info("[telegram_bot] Adding command handlers...")
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
            log_warning(f"Active plugin does not support models: {e}")

        app.add_handler(CommandHandler("say", say_command))
        app.add_handler(CommandHandler("cancel", cancel_response))
        log_info("[telegram_bot] Adding MessageHandler for general messages...")
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        log_info("[telegram_bot] Adding MessageHandler for TRAINER_ID say steps...")

        app.add_handler(MessageHandler(
            filters.Chat(TRAINER_ID) & (
                filters.TEXT | filters.PHOTO | filters.AUDIO | filters.VOICE |
                filters.VIDEO | filters.Document.ALL
            ),
            handle_say_step
        ))
        log_info("[telegram_bot] Adding MessageHandler for TRAINER_ID incoming responses...")

        app.add_handler(MessageHandler(
            filters.Chat(TRAINER_ID) & (
                filters.Sticker.ALL | filters.PHOTO | filters.AUDIO |
                filters.VOICE | filters.VIDEO | filters.Document.ALL
            ),
            handle_incoming_response
        ))
        log_info("[telegram_bot] All handlers added successfully")

        log_info("🧞‍♀️ Rekku is online.")
        
        # Register this interface with the core
        log_info("[telegram_bot] Registering interface with core...")
        from core.core_initializer import core_initializer
        core_initializer.register_interface("telegram_bot")
        log_info("[telegram_bot] Interface registered with core")
    except Exception as e:
        log_error(f"[telegram_bot] Error building Telegram application: {repr(e)}")
        raise

    # Plugin startup is handled by plugin_startup_callback
    # No need for fallback as the callback ensures proper async startup

    try:
        log_info("[telegram_bot] Starting Telegram application initialization...")
        # Use async initialization instead of run_polling to avoid event loop conflicts
        await app.initialize()
        log_info("[telegram_bot] Telegram application initialized")
        
        await app.start()
        log_info("[telegram_bot] Telegram application started")
        
        # Keep running until interrupted
        log_info("[telegram_bot] Starting polling...")
        await app.updater.start_polling()
        log_info("[telegram_bot] Polling started successfully")
        
        # This keeps the application running
        log_info("[telegram_bot] Bot is now running and listening for messages...")
        await asyncio.Event().wait()  # Wait forever until interrupted
    except Exception as e:
        log_error(f"[telegram_bot] Error in bot polling: {repr(e)}")
        raise
    finally:
        log_info("[telegram_bot] Shutting down Telegram application...")
        await app.stop()
        await app.shutdown()
        log_info("[telegram_bot] Telegram application shutdown completed")

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
            log_error(f"[telegram_bot] Failed to send message to {chat_id}: {repr(e)}")

    @staticmethod
    def get_interface_instructions():
        """Return specific instructions for Telegram interface."""
        return """TELEGRAM INTERFACE INSTRUCTIONS:
- Use chat_id for targets (can be negative for groups/channels)
- For groups with topics, include thread_id to reply in the correct topic, but don't use the thread_id if not specified in the input, else the message will fail to be delivered.
- Keep messages under 4096 characters
- Use Markdown formatting:
    * **bold** → `**bold**`
    * __italic__ → `__italic__`
    * --underline-- → `--underline--`
    * ~~strikethrough~~ → `~~strikethrough~~`
    * `monospace` → `` `monospace` ``
    * ```code block``` → triple backticks (```)
    * [inline URL](https://example.com) → standard Markdown link
- Escape special characters using a backslash if needed: `_ * [ ] ( ) ~ ` > # + - = | { } . !`
- For groups, always reply in the same chat and thread unless specifically instructed otherwise
- Target should be the exact chat_id from input.payload.source.chat_id
- Thread_id should be the exact thread_id from input.payload.source.thread_id (if present)
- Interface should always be "telegram_bot"
- REPLYING TO MESSAGES: When responding to a user's message in the same chat, the message will automatically appear as a reply. Simply use the same target chat_id as the original message.
- CROSS-CHAT MESSAGES: To send to a different chat than where the message came from, specify a different target chat_id. These won't appear as replies but as new messages.
"""

