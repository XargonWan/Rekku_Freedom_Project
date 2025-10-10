# Hardcoded fallback aliases for synth
synth_ALIASES = ["synth", "synthetic heart"]

# Pre-compute a lower-case version for faster checks
synth_ALIASES_LOWER = [alias.lower() for alias in synth_ALIASES]


def get_current_aliases() -> list[str]:
    """Get the current persona's aliases, falling back to hardcoded ones."""
    try:
        from core.persona_manager import get_persona_manager
        persona_manager = get_persona_manager()
        current_persona = persona_manager.get_current_persona()
        if current_persona and current_persona.aliases:
            return current_persona.aliases
    except Exception as e:
        log_debug(f"[mention] Error getting current persona aliases: {e}")
    # Fallback to hardcoded aliases
    return synth_ALIASES


from core.logging_utils import log_debug



async def get_bot_username(bot):
    """Get the bot's username from the bot instance."""
    try:
        if hasattr(bot, 'username'):
            return bot.username
        elif hasattr(bot, 'get_me'):
            me = await bot.get_me()
            return getattr(me, 'username', None)
        else:
            return None
    except Exception as e:
        log_debug(f"[mention] Error getting bot username: {e}")
        return None


def is_synth_mentioned(text: str) -> bool:
    """Return ``True`` if ``text`` contains any alias for synth."""
    if not text:
        return False
    lowered = text.lower()
    aliases = get_current_aliases()
    aliases_lower = [alias.lower() for alias in aliases]
    for alias in aliases_lower:
        if alias in lowered:
            log_debug(f"[mention] synth alias matched: '{alias}'")
            return True
    return False


def get_message_text(message) -> str | None:
    """
    Extract text from a message, checking both text and caption fields.
    Returns None if neither is available.
    """
    return message.text if hasattr(message, 'text') and message.text else \
           message.caption if hasattr(message, 'caption') and message.caption else None


async def is_message_for_bot(
    message,
    bot,
    bot_username: str | None = None,
    human_count: int | None = None,
) -> tuple[bool, str | None]:
    """
    Check if a message is directed to the bot considering:
    - Explicit @mention of the bot
    - Reply to a message from the bot
    - Mention of synth aliases in the text
    - Private messages (always considered directed to bot)
    
    Args:
        message: Message object from the interface
        bot: Bot instance from the interface
        bot_username: Bot username (optional, will be detected if not provided)
        human_count: Number of human participants in the chat (excluding bots).
            If ``None``, interfaces are unable to provide this information
            and the bot will fall back to mention-based activation.
    
    Returns:
        tuple: (is_for_bot, reason)
            - is_for_bot: True if message is directed to the bot
            - reason: Optional string describing why a message was not
              considered for the bot. ``None`` when ``is_for_bot`` is True.
    """
    # First log to ensure function is called
    # Extract text from message (handles both text and caption)
    message_text = get_message_text(message)
    
    try:
        log_debug(f"[mention] ENTRY: Function called with message.text='{message_text}' chat_type='{getattr(message.chat, 'type', 'NO_CHAT_TYPE')}'")
    except Exception as e:
        print(f"ERROR in log_debug: {e}")
        return False, "error_in_function"
    
    # Priority 1: Check for private messages (1:1 chat) - HIGHEST PRIORITY
    try:
        if message.chat.type == "private":
            log_debug("[mention] ✅ Private message detected - PRIORITY 1 - always for bot")
            return True, None
    except Exception as e:
        log_debug(f"[mention] Error checking private chat: {e}")
        return False, "error_checking_private"
    
    # Priority 2: Check for reply to bot message
    if hasattr(message, 'reply_to_message') and message.reply_to_message:
        reply_sender = getattr(message.reply_to_message, 'from_user', None)
        if reply_sender:
            reply_username = getattr(reply_sender, 'username', None)
            reply_id = getattr(reply_sender, 'id', None)
            log_debug(f"[mention] Reply to message from: {reply_username} (ID: {reply_id})")
            
            # Check if reply is to bot by username
            if reply_username and bot_username and reply_username.lower() == bot_username.lower():
                log_debug("[mention] ✅ Reply to bot message (username match) - PRIORITY 2 - message is for bot")
                return True, None
            
            # Check if reply is to bot by ID
            if reply_id and hasattr(bot, 'id') and reply_id == bot.id:
                log_debug("[mention] ✅ Reply to bot message (ID match) - PRIORITY 2 - message is for bot")
                return True, None
    
    # Priority 3: Check for @mention/tag (explicit mentions)
    if message_text and "@" in message_text:
        # Check for @synth mention
        if "@synth" in message_text.lower():
            log_debug("[mention] ✅ Explicit @synth mention found - PRIORITY 3 - message is for bot")
            return True, None
        # Check for bot username if provided
        if bot_username and f"@{bot_username}" in message_text:
            log_debug(f"[mention] ✅ Explicit @mention found: @{bot_username} - PRIORITY 3 - message is for bot")
            return True, None
    
    # Priority 4: Check for synth aliases in message text (activation words)
    if message_text:
        text_lower = message_text.lower()
        log_debug(f"[mention] Checking aliases in text: '{text_lower}'")
        aliases = get_current_aliases()
        for alias in aliases:
            if alias.lower() in text_lower:
                log_debug(f"[mention] ✅ Alias found: '{alias}' - PRIORITY 4 - message is for bot")
                return True, None
        log_debug(f"[mention] No aliases found in '{text_lower}'")
    
    # Priority 5: Check for chat 1:1 using human count (fallback)
    if human_count is not None and human_count == 1:
        log_debug("[mention] ✅ Single human in chat - PRIORITY 5 - treating as message for bot")
        return True, None
    
    # No direct mention found and either multiple humans or unknown count
    if human_count is None:
        log_debug("[mention] No direct mention found and human count unavailable")
        return False, "missing_human_count"
    else:
        log_debug(f"[mention] No direct mention found and multiple humans in chat ({human_count})")
        return False, "multiple_humans"
