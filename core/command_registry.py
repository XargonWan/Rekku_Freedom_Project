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
        "`/purge_map [days]` – Purge old mappings\n"
        "`/clean_chat_link <chat_id>` – Remove the link between a Telegram chat and ChatGPT.\n"
        "`/logchat` – Set the current chat as the log chat\n"
    )
    return help_text


# Register default commands
register_command("help", help_command)
