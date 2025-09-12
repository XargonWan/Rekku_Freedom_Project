"""Multilingual utilities for detecting mentions of Rekku in free-form text."""

REKKU_ALIASES = [
    # Latin aliases
    "rekku",
    "re-chan",
    "re-cchan",
    "recchan",
    "rekkuchan",
    "rekku-chan",
    "rekuchan",
    "rekku-tan",
    "rekku-san",
    "rekku-sama",
    "rekku-senpai",
    "genietta",
    "genietto",
    "tanukina",
    "tanuki",
    "quella blu",
    "rekuchina",
    "digi",
    "rekkuoricina",
    # Japanese aliases
    "れっく",
    "れっくう",
    "れっくちゃん",
    "れっくたん",
    "れっくさん",
    "れっく様",
    "レック",
    "レックちゃん",
    "レックたん",
    # Cyrillic aliases
    "рекку",
    "рекка",
    "рекчан",
    "реккун",
    "рекушка",
    # Official handle
    "@the_official_rekku",
]

# Pre-compute a lower-case version for faster checks
REKKU_ALIASES_LOWER = [alias.lower() for alias in REKKU_ALIASES]


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


def is_rekku_mentioned(text: str) -> bool:
    """Return ``True`` if ``text`` contains any alias for Rekku."""
    if not text:
        return False
    lowered = text.lower()
    for alias in REKKU_ALIASES_LOWER:
        if alias in lowered:
            log_debug(f"[mention] Rekku alias matched: '{alias}'")
            return True
    return False


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
    - Mention of Rekku aliases in the text
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
    try:
        log_debug(f"[mention] ENTRY: Function called with message.text='{getattr(message, 'text', 'NO_TEXT')}' chat_type='{getattr(message.chat, 'type', 'NO_CHAT_TYPE')}'")
    except Exception as e:
        print(f"ERROR in log_debug: {e}")
        return False, "error_in_function"
    
    # Private messages are always for the bot
    try:
        if message.chat.type == "private":
            log_debug("[mention] Private message detected - always for bot")
            return True, None
    except Exception as e:
        log_debug(f"[mention] Error checking private chat: {e}")
        return False, "error_checking_private"
    
    # Priority 1: Check for Rekku aliases in message text (no async calls)
    if message.text:
        text_lower = message.text.lower()
        log_debug(f"[mention] Checking aliases in text: '{text_lower}'")
        for alias in REKKU_ALIASES:
            if alias.lower() in text_lower:
                log_debug(f"[mention] ✅ Alias found: '{alias}' - message is for bot")
                return True, None
        log_debug(f"[mention] No aliases found in '{text_lower}'")
    
    # Priority 2: Check for @mention (simple string check)
    if message.text and "@" in message.text:
        # Check for @rekku mention
        if "@rekku" in message.text.lower():
            log_debug("[mention] Explicit @rekku mention found - message is for bot")
            return True, None
        # Check for bot username if provided
        if bot_username and f"@{bot_username}" in message.text:
            log_debug(f"[mention] Explicit @mention found: @{bot_username} - message is for bot")
            return True, None
    
    # Priority 3: Check for reply to bot message
    if hasattr(message, 'reply_to_message') and message.reply_to_message:
        reply_sender = getattr(message.reply_to_message, 'from_user', None)
        if reply_sender:
            reply_username = getattr(reply_sender, 'username', None)
            reply_id = getattr(reply_sender, 'id', None)
            log_debug(f"[mention] Reply to message from: {reply_username} (ID: {reply_id})")
            
            # Check if reply is to bot by username
            if reply_username and bot_username and reply_username.lower() == bot_username.lower():
                log_debug("[mention] Reply to bot message (username match) - message is for bot")
                return True, None
            
            # Check if reply is to bot by ID
            if reply_id and hasattr(bot, 'id') and reply_id == bot.id:
                log_debug("[mention] Reply to bot message (ID match) - message is for bot")
                return True, None
    
    # Fallback: Check human count for group chats (only when NO direct mention found)
    if human_count is not None and human_count == 1:
        log_debug("[mention] Single human in chat - treating as message for bot")
        return True, None
    
    # No direct mention found and either multiple humans or unknown count
    if human_count is None:
        log_debug("[mention] No direct mention found and human count unavailable")
        return False, "missing_human_count"
    else:
        log_debug(f"[mention] No direct mention found and multiple humans in chat ({human_count})")
        return False, "multiple_humans"
