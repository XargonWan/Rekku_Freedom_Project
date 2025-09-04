# interface/telegram_bot.py

import os
import re
import asyncio
import subprocess
from telegram import Update, Bot
from telegram.error import TelegramError, RetryAfter, BadRequest, TimedOut
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
from core.telegram_utils import (
    safe_send,
    send_with_thread_fallback,
)
from core.message_sender import (
    send_content,
    detect_media_type,
    extract_response_target,
)
from core.config import (
    get_active_llm,
    set_active_llm,
    list_available_llms,
    get_log_chat_id,
    set_log_chat_id,
    get_log_chat_id_sync,
)
from core.config import BOT_TOKEN, BOT_USERNAME, TELEGRAM_TRAINER_ID
from core.command_registry import execute_command

from core.chat_link_store import (
    ChatLinkStore,
    ChatLinkMultipleMatches,
)
from core.action_parser import corrector
from core.action_parser import ERROR_RETRY_POLICY
from core.prompt_engine import build_full_json_instructions

chat_link_store = ChatLinkStore()
import core.plugin_instance as plugin_instance
import traceback
from core.action_parser import initialize_core
from core.core_initializer import register_interface
from typing import Any
from types import SimpleNamespace

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
        try:
            current = await get_active_llm()
            if current:
                await plugin_instance.load_plugin(current, notify_fn=telegram_notify)
        except Exception as e:  # pragma: no cover - runtime safeguard
            log_warning(f"[telegram_interface] Failed to autoload LLM: {e}")
        if plugin_instance.plugin is None:
            try:
                await plugin_instance.load_plugin("manual", notify_fn=telegram_notify)
                log_warning("[telegram_interface] Falling back to ManualAIPlugin")
            except Exception:
                log_error("No LLM plugin loaded.")
                from core.notifier import notify_trainer
                notify_trainer("⚠️ No LLM plugin active. Use /llm to select one.")
                return False
    return True

def resolve_forwarded_target(message):
    """
    Given a message (presumably a reply to a forwarded message), try to
    reconstruct the original ``chat_id`` and ``message_id`` of the forwarded
    message.
    """

    if hasattr(message, "forward_from_chat") and hasattr(message, "forward_from_message_id"):
        if message.forward_from_chat and message.forward_from_message_id:
            return message.forward_from_chat.id, message.forward_from_message_id

    tracked = plugin_instance.get_target(message.message_id)
    if tracked:
        return tracked["chat_id"], tracked["message_id"]

    return None, None

# === Block commands ===

async def block_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != TELEGRAM_TRAINER_ID:
        return
    try:
        to_block = int(context.args[0])
        blocklist.block_user(to_block)
        log_debug(f"User {to_block} blocked.")
        await update.message.reply_text(f"\U0001f6ab User {to_block} blocked.")
    except (IndexError, ValueError):
        await update.message.reply_text("❌ Use: /block <user_id>")

async def block_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != TELEGRAM_TRAINER_ID:
        return
    blocked = blocklist.get_block_list()
    log_debug("Blocked users list requested.")
    if not blocked:
        await update.message.reply_text("\u2705 No users blocked.")
    else:
        await update.message.reply_text("\U0001f6ab Blocked users:\n" + "\n".join(map(str, blocked)))

async def unblock_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != TELEGRAM_TRAINER_ID:
        return
    try:
        to_unblock = int(context.args[0])
        blocklist.unblock_user(to_unblock)
        log_debug(f"User {to_unblock} unblocked.")
        await update.message.reply_text(f"\u2705 User {to_unblock} unblocked.")
    except (IndexError, ValueError):
        await update.message.reply_text("❌ Use: /unblock <user_id>")

async def purge_mappings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != TELEGRAM_TRAINER_ID:
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


async def logchat_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set the current chat as the log chat."""
    if update.effective_user.id != TELEGRAM_TRAINER_ID:
        return
    chat_id = update.effective_chat.id
    thread_id = update.effective_message.message_thread_id
    try:
        await set_log_chat_id(chat_id)
        confirmation = f"This chat is now set as logchat [{chat_id}, {thread_id}]"
        await safe_send(context.bot, chat_id, confirmation, message_thread_id=thread_id)
    except Exception as e:
        log_error(f"[telegram_interface] Failed to set log chat: {e}")
        await update.message.reply_text("❌ Unable to set log chat.")

async def handle_incoming_response(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not await ensure_plugin_loaded(update):
        return

    if update.effective_user.id != TELEGRAM_TRAINER_ID:
        log_debug("Message ignored: not from TELEGRAM_TRAINER_ID")
        return

    message = update.message
    if not message:
        log_debug("❌ No message present, aborting.")
        return

    media_type = detect_media_type(message)
    log_debug(f"✅ handle_incoming_response: media_type = {media_type}; reply_message_id = {bool(message.reply_to_message)}")

    # === 1. Prova target da response_proxy (es. /say)
    target = response_proxy.get_target(TELEGRAM_TRAINER_ID)
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
        fallback = say_proxy.get_target(TELEGRAM_TRAINER_ID)
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
    reply_message_id = target["message_id"]
    content_type = target["type"]

    log_debug(f"Sending media_type={content_type} to chat_id={chat_id}, reply_message_id={reply_message_id}")
    # Diagnostic: log detailed send_content params
    try:
        log_debug(f"[telegram_interface] Calling send_content with bot={repr(context.bot)}, chat_id={chat_id}, message_id={message.message_id}, content_type={content_type}, reply_message_id={reply_message_id}")
    except Exception:
        log_debug("[telegram_interface] Failed to repr context.bot for diagnostics")
    success, feedback = await send_content(context.bot, chat_id, message, content_type, reply_message_id)

    # Diagnostic: log result from send_content
    log_debug(f"[telegram_interface] send_content returned: success={success}, feedback={feedback}")

    await message.reply_text(feedback)

    if success:
        log_debug("✅ Sending successful. Cleaning proxy.")
        response_proxy.clear_target(TELEGRAM_TRAINER_ID)
        say_proxy.clear(TELEGRAM_TRAINER_ID)
    else:
        log_error("Sending failed.")


# === Generic command for sticker/audio/photo/file/video ===

async def handle_response_command(update: Update, context: ContextTypes.DEFAULT_TYPE, content_type: str):

    if not await ensure_plugin_loaded(update):
        return

    if update.effective_user.id != TELEGRAM_TRAINER_ID:
        return

    message = update.message
    if not message.reply_to_message:
        await message.reply_text("⚠️ You must use this command in reply to a message forwarded by Rekku.")
        return

    chat_id, message_id = resolve_forwarded_target(message.reply_to_message)

    if not chat_id or not message_id:
        await message.reply_text("❌ Invalid message for this command.")
        return

    response_proxy.set_target(TELEGRAM_TRAINER_ID, chat_id, message_id, content_type)
    log_debug(f"Target {content_type} set: chat_id={chat_id}, message_id={message_id}")
    await safe_send(
        context.bot,
        chat_id=TELEGRAM_TRAINER_ID,
        text=f"📎 Send me the {content_type.upper()} file to use as response."
    )  # [FIX]

async def cancel_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != TELEGRAM_TRAINER_ID:
        return
    if response_proxy.has_pending(TELEGRAM_TRAINER_ID):
        response_proxy.clear_target(TELEGRAM_TRAINER_ID)
        say_proxy.clear(TELEGRAM_TRAINER_ID)
        log_debug("Response sending cancelled.")
        await update.message.reply_text("❌ Sending cancelled.")
    else:
        await update.message.reply_text("⚠️ No active send to cancel.")


async def test_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    log_debug("/test received")
    await update.message.reply_text("✅ Test OK")

async def last_chats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != TELEGRAM_TRAINER_ID:
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
        "user_id": user_id,
        "username": username,
        "usertag": usertag,
        "text": text,
        "timestamp": message.date.isoformat()
    })
    chat_meta = message.chat.title or message.chat.username or message.chat.first_name
    await recent_chats.track_chat(message.chat_id, chat_meta)
    log_debug(f"context_memory[{message.chat_id}] = {list(context_memory[message.chat_id])}")

    # Interactive /say step
    if message.chat.type == "private" and user_id == TELEGRAM_TRAINER_ID and context.user_data.get("say_choices"):
        await handle_say_step(update, context)
        return

    log_debug(f"Message from {user_id} ({message.chat.type}): {text}")

    # Blocked user
    if await blocklist.is_blocked(user_id) and user_id != TELEGRAM_TRAINER_ID:
        log_debug(f"User {user_id} is blocked. Ignoring message.")
        return

    # trainer reply to forwarded message
    if message.chat.type == "private" and user_id == TELEGRAM_TRAINER_ID and message.reply_to_message:
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
            log_warning("⚠️ No target found for reply. Ensure plugin mapping is correct.")
            await message.reply_text("⚠️ No message found to reply to.")
        return

    # === Forward to centralized queue
    try:
        await message_queue.enqueue(context.bot, message, context_memory, interface_id="telegram_bot")
    except Exception as e:
        log_error(f"message_queue enqueue failed: {repr(e)}", e)
        await message.reply_text("⚠️ Error processing message.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != TELEGRAM_TRAINER_ID:
        return
    help_text = await execute_command("help")
    await update.message.reply_text(help_text, parse_mode="Markdown")

def escape_markdown(text):
    return re.sub(r'([_*\[\]()~`>#+=|{}.!-])', r'\\\1', text)

async def last_chats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != TELEGRAM_TRAINER_ID:
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
    if update.effective_user.id != TELEGRAM_TRAINER_ID:
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
    if update.effective_user.id != TELEGRAM_TRAINER_ID:
        return

    args = context.args
    bot = context.bot

    # Case 1: /say <chat_id> <message>
    if len(args) >= 2:
        try:
            chat_id = int(args[0])
            text = " ".join(args[1:])
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
            await plugin_instance.handle_incoming_message(context.bot, message, context.user_data, "telegram_bot")
            response_proxy.clear_target(TELEGRAM_TRAINER_ID)
            say_proxy.clear(TELEGRAM_TRAINER_ID)
        except Exception as e:
            log_error(
                f"Error during plugin_instance.handle_incoming_message in /say: {e}",
                e,
            )
            await message.reply_text("❌ Error sending message.")

async def llm_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    log_info(f"[telegram_bot] LLM command received from user {update.effective_user.id}")
    
    if update.effective_user.id != TELEGRAM_TRAINER_ID:
        log_warning(f"[telegram_bot] LLM command rejected: user {update.effective_user.id} != TELEGRAM_TRAINER_ID {TELEGRAM_TRAINER_ID}")
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
    if update.effective_user.id != TELEGRAM_TRAINER_ID:
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

    # Forza la notifica solo al TELEGRAM_TRAINER_ID in privato
    log_debug(f"[telegram_notify] → CALLED con chat_id={chat_id}")
    log_debug(f"[telegram_notify] → MESSAGE:\n{message}")

    bot = Bot(token=BOT_TOKEN)

    # Se il destinatario non è il TELEGRAM_TRAINER_ID, non inviare nulla
    if chat_id != TELEGRAM_TRAINER_ID:
        log_debug(
            f"[telegram_notify] Ignorato: chat_id {chat_id} != TELEGRAM_TRAINER_ID {TELEGRAM_TRAINER_ID}"
        )
        return

    # Make URLs clickable
    url_pattern = re.compile(r"https?://\S+")
    match = url_pattern.search(message or "")
    formatted_message = None
    if match:
        def repl(m):
            url = m.group(0)
            return f'<a href="{html.escape(url)}">{html.escape(url)}</a>'

        formatted_message = url_pattern.sub(repl, html.escape(message))

    targets = [TELEGRAM_TRAINER_ID]
    log_chat_id = get_log_chat_id_sync()
    if log_chat_id and log_chat_id not in targets:
        targets.append(log_chat_id)

    async def send(target: int, reply_id: int | None):
        try:
            await safe_send(
                bot,
                chat_id=target,
                text=formatted_message or message,
                reply_to_message_id=reply_id,
                parse_mode=ParseMode.HTML if formatted_message else None,
                disable_web_page_preview=True,
            )  # [FIX][telegram retry]
            log_debug(f"[notify] ✅ Telegram message sent to {target}")
        except TelegramError as e:
            log_error(f"[notify] ❌ Telegram error: {repr(e)}", e)
        except Exception as e:
            log_error(f"[notify] ❌ Other error in send(): {repr(e)}", e)

    async def runner():
        for tgt in targets:
            await send(tgt, reply_to_message_id if tgt == TELEGRAM_TRAINER_ID else None)

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        loop.create_task(runner())
    else:
        asyncio.run(runner())

# === Startup ===


async def plugin_startup_callback(application):
    """Run pending plugin tasks once the bot's event loop is ready."""
    from core.core_initializer import core_initializer

    # Start any async plugins that were deferred until a loop was available
    await core_initializer.start_pending_async_plugins()

    # Start the queue consumer after the application is ready
    application.create_task(message_queue.run())


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

    try:
        log_info("[telegram_bot] Building Telegram application...")
        app = (
            ApplicationBuilder()
            .token(BOT_TOKEN)
            .post_init(plugin_startup_callback)
            .build()
        )
        log_info("[telegram_bot] Telegram application built successfully")
        log_info(f"[telegram_bot] TELEGRAM_TRAINER_ID configured as: {TELEGRAM_TRAINER_ID}")
        log_info(f"[telegram_bot] BOT_TOKEN configured: {'Yes' if BOT_TOKEN else 'No'}")

        log_info("[telegram_bot] Adding command handlers...")
        app.add_handler(CommandHandler("help", help_command))
        app.add_handler(CommandHandler("block", block_user))
        app.add_handler(CommandHandler("block_list", block_list))
        app.add_handler(CommandHandler("unblock", unblock_user))
        app.add_handler(CommandHandler("purge_map", purge_mappings))
        app.add_handler(CommandHandler("logchat", logchat_command))
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
        log_info("[telegram_bot] Adding MessageHandler for TELEGRAM_TRAINER_ID say steps...")

        app.add_handler(MessageHandler(
            filters.Chat(TELEGRAM_TRAINER_ID) & (
                filters.TEXT | filters.PHOTO | filters.AUDIO | filters.VOICE |
                filters.VIDEO | filters.Document.ALL
            ),
            handle_say_step
        ))
        log_info("[telegram_bot] Adding MessageHandler for TELEGRAM_TRAINER_ID incoming responses...")

        app.add_handler(MessageHandler(
            filters.Chat(TELEGRAM_TRAINER_ID) & (
                filters.Sticker.ALL | filters.PHOTO | filters.AUDIO |
                filters.VOICE | filters.VIDEO | filters.Document.ALL
            ),
            handle_incoming_response
        ))
        log_info("[telegram_bot] All handlers added successfully")

        # The interface will register itself once the Telegram application has
        # been initialized below. Calling core_initializer.register_interface
        # here would run before the interface instance exists and generates a
        # misleading warning about missing action support.
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

        # Register interface instance for plugins. This automatically exposes
        # its actions to the core initializer.
        telegram_interface = TelegramInterface(app.bot)
        register_interface("telegram_bot", telegram_interface)
        log_debug("[telegram_bot] Interface instance registered")

        # Rebuild action schemas and display updated startup summary
        from core.core_initializer import core_initializer
        await core_initializer.refresh_actions_block()
        core_initializer.display_startup_summary()
        
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
    """Interface wrapper providing a standard send_message method for Telegram."""

    def __init__(self, bot: Bot = None):
        """Store the python-telegram-bot ``Bot`` instance."""
        self.bot = bot
        # setattr(self.bot, "get_interface_id", self.get_interface_id)
        # Register resolver to fetch chat/thread names automatically
        async def _resolver(chat_id, message_thread_id, bot_instance=None):
            b = bot_instance or self.bot
            chat_name = None
            thread_name = None
            try:
                chat = await b.getChat(chat_id)
                chat_name = getattr(chat, "title", None) or getattr(chat, "username", None)
            except Exception as e:  # pragma: no cover - network failures
                log_warning(f"[telegram_interface] chat name lookup failed: {e}")
            if message_thread_id:
                try:
                    topic = await b.getForumTopic(chat_id, message_thread_id)
                    thread_name = getattr(topic, "name", None) or getattr(topic, "title", None)
                except Exception as e:  # pragma: no cover
                    log_warning(f"[telegram_interface] thread name lookup failed: {e}")
            return {"chat_name": chat_name, "message_thread_name": thread_name}

        ChatLinkStore.set_name_resolver("telegram", _resolver)

        # Register this interface instance
        from core.core_initializer import register_interface
        register_interface("telegram_bot", self)

    @staticmethod
    def get_interface_id() -> str:
        """Return the unique identifier for this interface."""
        return "telegram_bot"

    @staticmethod
    def get_supported_actions() -> dict:
        """Return schema information for supported actions."""
        return {
            "message_telegram_bot": {
                "required_fields": ["text"],
                "optional_fields": [
                    "target",
                    "chat_name",
                    "message_thread_id",
                    "message_thread_name",
                ],
                "description": "Send a text message via Telegram",
            },
            "audio_telegram_bot": {
                "required_fields": ["audio"],
                "optional_fields": [
                    "target",
                    "chat_name",
                    "message_thread_id",
                    "message_thread_name",
                ],
                "description": "Send a voice message via Telegram",
            },
        }

    @staticmethod
    def get_prompt_instructions(action_name: str) -> dict:
        """Prompt instructions for supported actions."""
        if action_name == "message_telegram_bot":
            return {
                "description": "Send a message via Telegram bot",
                "payload": {
                    "text": {"type": "string", "example": "Hello!", "description": "The message text to send"},
                    "target": {
                        "type": "string",
                        "example": "-123456789",
                        "description": "Numeric chat_id or chat_name of the recipient",
                        "optional": True,
                    },
                    "chat_name": {
                        "type": "string",
                        "example": "Il covo di Rekku",
                        "description": "Alternative to target for specifying the chat by name",
                        "optional": True,
                    },
                    "message_thread_id": {
                        "type": "integer",
                        "example": 456,
                        "description": "Optional thread ID for group chats",
                        "optional": True,
                    },
                    "message_thread_name": {
                        "type": "string",
                        "example": "Generale",
                        "description": "Alternative to message_thread_id to specify the thread by name",
                        "optional": True,
                    },
                    "reply_to_message_id": {
                        "type": "integer",
                        "example": 12345,
                        "description": "Optional ID of the message to reply to",
                        "optional": True,
                    },
                },
            }
        if action_name == "audio_telegram_bot":
            return {
                "description": "Send a voice message via Telegram bot",
                "payload": {
                    "audio": {"type": "string", "example": "/path/to/file.ogg", "description": "Path to the voice file"},
                    "target": {
                        "type": "string",
                        "example": "-123456789",
                        "description": "Numeric chat_id or chat_name of the recipient",
                        "optional": True,
                    },
                    "chat_name": {
                        "type": "string",
                        "example": "Il covo di Rekku",
                        "description": "Alternative to target for specifying the chat by name",
                        "optional": True,
                    },
                    "message_thread_id": {
                        "type": "integer",
                        "example": 456,
                        "description": "Optional thread ID for group chats",
                        "optional": True,
                    },
                },
            }
        return None

    @staticmethod
    def validate_payload(action_type: str, payload: dict) -> list:
        """Validate payload for telegram actions."""
        errors = []

        if action_type == "message_telegram_bot":
            text = payload.get("text")
            if not isinstance(text, str) or not text:
                errors.append("payload.text must be a non-empty string")

        elif action_type == "audio_telegram_bot":
            audio = payload.get("audio")
            if not isinstance(audio, str) or not audio:
                errors.append("payload.audio must be a non-empty string")
        else:
            return []

        target = payload.get("target")
        chat_name = payload.get("chat_name")
        if target is None and chat_name is None:
            errors.append("payload.target or payload.chat_name is required")
        else:
            if target is not None:
                if isinstance(target, dict):
                    chat_id = target.get("chat_id")
                    message_thread_id = target.get("message_thread_id")
                    if chat_id is not None and not isinstance(chat_id, (int, str)):
                        errors.append("payload.target.chat_id must be an int or string")
                    if message_thread_id is not None and not isinstance(message_thread_id, int):
                        errors.append("payload.target.message_thread_id must be an int")
                elif not isinstance(target, (int, str)):
                    errors.append("payload.target must be an int, string or dict")

        message_thread_id = payload.get("message_thread_id")
        if message_thread_id is not None and not isinstance(message_thread_id, int):
            errors.append("payload.message_thread_id must be an int")

        thread_name = payload.get("message_thread_name")
        if thread_name is not None and not isinstance(thread_name, str):
            errors.append("payload.message_thread_name must be a string")

        return errors

    async def _emit_system_error(
        self,
        step: str,
        details: str,
        payload: dict,
        original_message: object | None = None,
    ) -> None:
        try:
            full_json = build_full_json_instructions()
            system_payload = {
                "system_message": {
                    "type": "error",
                    "step": step,
                    "message": details,
                    "full_json_instructions": full_json,
                    "error_retry_policy": ERROR_RETRY_POLICY,
                }
            }
            payload_json = json.dumps(system_payload, ensure_ascii=False)
            msg = SimpleNamespace()
            if original_message and hasattr(original_message, "chat_id"):
                msg.chat_id = original_message.chat_id
                msg.message_thread_id = getattr(original_message, "message_thread_id", None)
            else:
                msg.chat_id = TELEGRAM_TRAINER_ID
                msg.message_thread_id = None
            msg.text = payload_json
            from datetime import datetime
            msg.date = datetime.utcnow()
            msg.from_user = SimpleNamespace(id=TELEGRAM_TRAINER_ID)
            llm = plugin_instance.get_plugin()
            if llm and hasattr(llm, "handle_incoming_message"):
                await llm.handle_incoming_message(self.bot, msg, payload_json)
        except Exception as e:
            log_error(f"[telegram_interface] Failed to emit system error: {e}")

    async def _verify_delivery(
        self,
        sent_message: object | None,
        payload: dict,
        original_message: object | None = None,
    ) -> None:
        log_chat_id = await get_log_chat_id()
        if not log_chat_id:
            log_chat_id = TELEGRAM_TRAINER_ID
        if sent_message is None:
            await self._emit_system_error(
                "retry_exhausted",
                "sendMessage returned no message",
                payload,
                original_message,
            )
            return
        if not log_chat_id:
            return

        retries = 3
        base_delay = 2
        for attempt in range(1, retries + 1):
            try:
                await self.bot.copy_message(
                    chat_id=log_chat_id,
                    from_chat_id=sent_message.chat_id,
                    message_id=sent_message.message_id,
                )
                return
            except RetryAfter as e:
                wait_time = getattr(e, "retry_after", base_delay * attempt)
            except TelegramError as e:
                status = getattr(getattr(e, "response", None), "status_code", None)
                if status in {429, 500, 502, 503} and attempt < retries:
                    wait_time = base_delay * (2 ** (attempt - 1))
                else:
                    await self._emit_system_error(
                        "copy_check",
                        f"copyMessage failed: {e}",
                        payload,
                        original_message,
                    )
                    return
            except Exception as e:
                await self._emit_system_error(
                    "copy_check",
                    f"copyMessage exception: {e}",
                    payload,
                    original_message,
                )
                return
            await asyncio.sleep(wait_time)
        await self._emit_system_error(
            "retry_exhausted",
            "copyMessage failed after retries",
            payload,
            original_message,
        )

    async def send_message(self, payload: dict, original_message: object | None = None) -> None:
        """Send a message using the stored bot.

        Parameters
        ----------
        payload: dict
            Must contain at least ``text`` and ``target``. Optionally may include
            ``message_thread_id``.
        original_message: object | None
            The triggering message; used for reply fallback handling.

        ``message_thread_id`` is the correct Telegram parameter for replies in
        topics and replaces the legacy ``thread_id`` name.
        """

        text = payload.get("text", "")
        target = payload.get("target")
        chat_name = payload.get("chat_name")
        message_thread_id = payload.get("message_thread_id")
        thread_name = payload.get("message_thread_name")

        log_debug(
            f"[telegram_interface] Sending to target={target} chat_name={chat_name} thread_id={message_thread_id} thread_name={thread_name}"
        )

        if not text or (target is None and chat_name is None):
            log_warning("[telegram_interface] Missing text or destination, aborting")
            return

        chat_id = None

        if isinstance(target, dict):
            chat_id = target.get("chat_id")
            message_thread_id = target.get("message_thread_id", message_thread_id)
            thread_name = target.get("message_thread_name", thread_name)
        elif target is not None:
            if isinstance(target, str) and not target.lstrip("-").isdigit():
                chat_name = target
            else:
                try:
                    chat_id = int(target)
                except Exception:
                    chat_name = target

        if chat_id is None or (message_thread_id is None and thread_name is not None):
            try:
                row = await chat_link_store.resolve(
                    chat_id=chat_id,
                    message_thread_id=message_thread_id,
                    chat_name=chat_name,
                    message_thread_name=thread_name,
                )
            except ChatLinkMultipleMatches:
                await corrector(
                    [
                        f"Multiple channels found with name {chat_name}, please repeat your previous message putting the chat_id instead of chat_name",
                    ],
                    [payload],
                    self.bot,
                    original_message,
                )
                return
            if not row:
                await corrector(
                    [
                        f"Channel or thread not found for name {chat_name or thread_name}",
                    ],
                    [payload],
                    self.bot,
                    original_message,
                )
                return
            chat_id = row.get("chat_id", chat_id)
            message_thread_id = row.get("message_thread_id", message_thread_id)

        try:
            target_for_comparison = int(chat_id)
        except (TypeError, ValueError):
            log_warning(f"[telegram_interface] Invalid chat identifier: {chat_id}")
            return

        await chat_link_store.update_names_from_resolver(
            chat_id, message_thread_id, bot=self.bot
        )

        chat_id_int = target_for_comparison

        reply_message_id = None
        if (
            original_message
            and hasattr(original_message, "chat_id")
            and hasattr(original_message, "message_id")
            and chat_id_int == getattr(original_message, "chat_id")
        ):
            reply_message_id = original_message.message_id
            log_debug(f"[telegram_interface] reply_to_message_id: {reply_message_id}")

        fallback_chat_id = None
        fallback_message_thread_id = None
        fallback_reply_to = None
        if (
            original_message
            and hasattr(original_message, "chat_id")
            and chat_id_int != getattr(original_message, "chat_id")
        ):
            fallback_chat_id = original_message.chat_id
            fallback_message_thread_id = getattr(original_message, "message_thread_id", None)
            if hasattr(original_message, "message_id"):
                fallback_reply_to = original_message.message_id

        try:
            sent_message = await send_with_thread_fallback(
                self.bot,
                chat_id_int,
                text,
                parse_mode="Markdown",
                message_thread_id=message_thread_id,  # fixed: correct param is message_thread_id
                reply_to_message_id=reply_message_id,
                fallback_chat_id=fallback_chat_id,
                fallback_message_thread_id=fallback_message_thread_id,
                fallback_reply_to_message_id=fallback_reply_to,
            )
        except BadRequest as e:
            if "chat not found" in str(e).lower():
                await corrector(
                    [f"Chat {chat_id_int} not found"],
                    [payload],
                    self.bot,
                    original_message,
                )
            else:
                await corrector([str(e)], [payload], self.bot, original_message)
            return
        except TelegramError as e:
            await self._emit_system_error("send", f"{e}", payload, original_message)
            return

        await self._verify_delivery(sent_message, payload, original_message)

    async def _convert_to_voice(self, path: str) -> str:
        if path.endswith(".ogg"):
            return path
        ogg_path = path.rsplit(".", 1)[0] + ".ogg"
        cmd = ["ffmpeg", "-y", "-i", path, "-c:a", "libopus", ogg_path]
        try:
            await asyncio.to_thread(subprocess.run, cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            return ogg_path
        except Exception as e:
            log_error(f"[telegram_interface] Audio conversion failed: {e}")
            return path

    async def send_audio(self, payload: dict, original_message: object | None = None) -> None:
        audio = payload.get("audio")
        target = payload.get("target")
        chat_name = payload.get("chat_name")
        message_thread_id = payload.get("message_thread_id")
        thread_name = payload.get("message_thread_name")

        if not audio or (target is None and chat_name is None):
            log_warning("[telegram_interface] Missing audio or destination, aborting")
            return

        chat_id = None

        if isinstance(target, dict):
            chat_id = target.get("chat_id")
            message_thread_id = target.get("message_thread_id", message_thread_id)
            thread_name = target.get("message_thread_name", thread_name)
        elif target is not None:
            if isinstance(target, str) and not target.lstrip("-").isdigit():
                chat_name = target
            else:
                try:
                    chat_id = int(target)
                except Exception:
                    chat_name = target

        if chat_id is None or (message_thread_id is None and thread_name is not None):
            try:
                row = await chat_link_store.resolve(
                    chat_id=chat_id,
                    message_thread_id=message_thread_id,
                    chat_name=chat_name,
                    message_thread_name=thread_name,
                )
            except ChatLinkMultipleMatches:
                await corrector(
                    [
                        f"Multiple channels found with name {chat_name}, please repeat your previous message putting the chat_id instead of chat_name",
                    ],
                    [payload],
                    self.bot,
                    original_message,
                )
                return
            if not row:
                await corrector(
                    [
                        f"Channel or thread not found for name {chat_name or thread_name}",
                    ],
                    [payload],
                    self.bot,
                    original_message,
                )
                return
            chat_id = row.get("chat_id", chat_id)
            message_thread_id = row.get("message_thread_id", message_thread_id)

        try:
            target_for_comparison = int(chat_id)
        except (TypeError, ValueError):
            log_warning(f"[telegram_interface] Invalid chat identifier: {chat_id}")
            return

        await chat_link_store.update_names_from_resolver(
            chat_id, message_thread_id, bot=self.bot
        )

        reply_message_id = None
        if (
            original_message
            and hasattr(original_message, "chat_id")
            and hasattr(original_message, "message_id")
            and target_for_comparison == getattr(original_message, "chat_id")
        ):
            reply_message_id = original_message.message_id

        send_kwargs = {"chat_id": target_for_comparison}
        if message_thread_id is not None:
            send_kwargs["message_thread_id"] = message_thread_id
        if reply_message_id is not None:
            send_kwargs["reply_to_message_id"] = reply_message_id

        try:
            converted = await self._convert_to_voice(audio)
            with open(converted, "rb") as f:
                await self.bot.send_voice(**send_kwargs, voice=f)
            return
        except Exception as e:
            error_message = str(e)
            if message_thread_id and "thread not found" in error_message.lower():
                send_kwargs.pop("message_thread_id", None)
                converted = await self._convert_to_voice(audio)
                with open(converted, "rb") as f:
                    await self.bot.send_voice(**send_kwargs, voice=f)
            else:
                log_error(f"[telegram_interface] Failed to send voice: {e}")

    async def execute_action(
        self, action: dict, context: dict, bot: Any, original_message: object | None = None
    ) -> None:
        """Execute actions for this interface."""
        self.bot = bot  # Set the bot instance
        action_type = action.get("type")
        if action_type == "message_telegram_bot":
            payload = action.get("payload", {})
            await self.send_message(payload, original_message)
        elif action_type == "audio_telegram_bot":
            payload = action.get("payload", {})
            await self.send_audio(payload, original_message)

    @staticmethod
    def get_interface_instructions():
        """Return specific instructions for Telegram interface."""
        return (
            "TELEGRAM INTERFACE INSTRUCTIONS:\n"
            "- Use chat_id or chat_name for targets (chat_id can be negative for groups/channels).\n"
            "- Include message_thread_id or message_thread_name when replying in topics; omit otherwise.\n"
            "- Keep messages under 4096 characters.\n"
            "- Markdown is supported and preferred.\n"
            "- Replying to a message in the same chat will automatically use that message as the reply target.\n"
            "- To send to another chat, specify the other chat's identifier; these will not appear as replies.\n"
            "- When a message originates on Telegram, reply using the message_telegram_bot action; do not switch interfaces unless explicitly asked.\n"
        )

# Register TelegramInterface for discovery by the core
PLUGIN_CLASS = TelegramInterface

