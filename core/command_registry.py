"""Backend registry for slash commands usable by any interface."""

from typing import Awaitable, Callable, Dict, Any
from core.logging_utils import log_debug
import core.plugin_instance as plugin_instance
from core.context import get_context_state
from core.config import get_active_llm

CommandHandler = Callable[..., Awaitable[str]]

_commands: Dict[str, CommandHandler] = {}


def register_command(name: str, handler: CommandHandler) -> None:
    """Register a backend command handler."""
    _commands[name] = handler
    log_debug(f"[command_registry] registered command: {name}")


def list_commands() -> list[str]:
    return list(_commands.keys())


def get_handler(name: str) -> CommandHandler | None:
    return _commands.get(name)


async def execute_command(name: str, *args: Any, **kwargs: Any) -> str:
    handler = get_handler(name)
    if not handler:
        raise ValueError(f"Unknown command: {name}")
    return await handler(*args, **kwargs)


async def help_command() -> str:
    """Generate help text shared across interfaces."""
    context_status = "active ✅" if get_context_state() else "inactive ❌"
    llm_mode = await get_active_llm()

    help_text = (
        "🧞‍♀️ *Rekku – Available Commands*\n\n"
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

    try:
        models = plugin_instance.get_supported_models()
        if models:
            current_model = plugin_instance.get_current_model() or models[0]
            help_text += f"`/model` – View or set active model (active: `{current_model}`)\n"
    except Exception:
        pass

    help_text += (
        "\n*📋 Misc*\n"
        "`/last_chats` – Last active chats\n"
        "`/diary [days]` – View Rekku's diary entries (default: 7 days)\n"
        "`/purge_map [days]` – Purge old mappings\n"
        "`/clean_chat_link <chat_id>` – Remove the link between a chat and conversation.\n"
        "`/logchat` – Set the current chat as the log chat\n"
    )
    return help_text


async def diary_command(days: str = "7") -> str:
    """Get diary entries for the specified number of days."""
    try:
        from plugins.ai_diary import get_recent_entries, format_diary_for_injection, is_plugin_enabled
        
        if not is_plugin_enabled():
            return "📔 Diary plugin is currently disabled or unavailable."
        
        # Parse days argument
        try:
            num_days = int(days) if days else 7
            if num_days <= 0:
                num_days = 7
        except ValueError:
            num_days = 7
        
        # Get recent entries (no char limit for manual viewing)
        entries = get_recent_entries(days=num_days, max_chars=None)
        
        if not entries:
            return f"📔 No diary entries found in the last {num_days} days."
        else:
            response = f"📔 **Rekku's Diary - Last {num_days} days ({len(entries)} entries)**\n\n"
            response += format_diary_for_injection(entries)
            response += f"\n\n_Use `/diary <days>` to view a different time range._"
            return response
    
    except ImportError:
        return "📔 Diary plugin is not installed."
    except Exception as e:
        log_debug(f"[command_registry] Error in diary command: {e}")
        return "❌ Error retrieving diary entries."


def get_help_text() -> str:
    """Get help text for use in generic commands."""
    import asyncio
    try:
        # Run the async help command
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(help_command())
    except Exception as e:
        log_debug(f"[command_registry] Error getting help text: {e}")
        return "Help text unavailable."


# Register default commands
register_command("help", help_command)
register_command("diary", diary_command)
