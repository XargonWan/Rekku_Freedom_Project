# core/reaction_handler.py
"""
Reaction handler for bot messages.

This module provides functionality to add reactions to messages when the bot
is mentioned or triggered, if configured via REACT_WHEN_MENTIONED env variable.
"""

import os
from typing import Optional
from types import SimpleNamespace
from core.logging_utils import log_debug, log_info, log_warning
from core.config_manager import config_registry

# Register REACT_WHEN_MENTIONED configuration
REACT_WHEN_MENTIONED = config_registry.get_value(
    "REACT_WHEN_MENTIONED",
    "👀",
    label="React When Mentioned",
    description="Emoji to use as reaction when bot is mentioned. Leave empty to disable. ⚠️ Note: Some interfaces or servers/channels may not support all emojis as reactions.",
    group="core",
    component="core",
)

def _update_react_emoji(value: str | None) -> None:
    global REACT_WHEN_MENTIONED
    REACT_WHEN_MENTIONED = (value or "").strip()

config_registry.add_listener("REACT_WHEN_MENTIONED", _update_react_emoji)


def get_reaction_emoji() -> Optional[str]:
    """
    Get the reaction emoji from REACT_WHEN_MENTIONED configuration.
    
    Returns:
        Optional[str]: The emoji to use as reaction, or None if not configured
    """
    emoji = REACT_WHEN_MENTIONED.strip() if REACT_WHEN_MENTIONED else ""
    if not emoji:
        return None
    return emoji


async def react_when_mentioned(bot, message: SimpleNamespace) -> bool:
    """
    Add a reaction to a message if REACT_WHEN_MENTIONED is configured.
    
    This function should be called when is_message_for_bot returns True.
    It reads the REACT_WHEN_MENTIONED environment variable and, if set,
    adds that emoji as a reaction to the triggering message.
    
    Args:
        bot: The bot instance from the interface
        message: The message object that triggered the bot
        
    Returns:
        bool: True if reaction was added successfully, False otherwise
    """
    # Get the configured emoji
    emoji = get_reaction_emoji()
    
    if not emoji:
        log_debug("[reaction] REACT_WHEN_MENTIONED not configured, skipping reaction")
        return False
    
    log_debug(f"[reaction] Attempting to add reaction '{emoji}' to message")
    
    # Try to determine the interface type and add reaction accordingly
    try:
        # Check if it's a Telegram bot
        if hasattr(bot, 'set_message_reaction'):
            # Telegram interface
            chat_id = getattr(message, 'chat_id', None) or getattr(message.chat, 'id', None)
            message_id = getattr(message, 'message_id', None)
            
            if not chat_id or not message_id:
                log_warning("[reaction] Cannot add reaction: missing chat_id or message_id")
                return False
            
            log_debug(f"[reaction] Adding Telegram reaction '{emoji}' to chat_id={chat_id}, message_id={message_id}")
            await bot.set_message_reaction(
                chat_id=chat_id,
                message_id=message_id,
                reaction=emoji,
                is_big=False
            )
            log_info(f"[reaction] Successfully added reaction '{emoji}' to message {message_id}")
            return True
            
        # Add support for other interfaces here as needed
        # elif hasattr(bot, 'add_reaction'):  # Discord example
        #     ...
        
        else:
            log_warning(f"[reaction] Interface does not support reactions: {type(bot).__name__}")
            return False
            
    except Exception as e:
        log_warning(f"[reaction] Failed to add reaction '{emoji}': {e}")
        return False
