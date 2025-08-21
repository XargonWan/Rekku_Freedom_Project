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
from typing import Dict, Set

# Track human participants per group chat to detect 1:1 conversations
_GROUP_CHAT_HUMANS: Dict[int, Set[int]] = {}


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


async def is_message_for_bot(message, bot, bot_username: str = None) -> bool:
    """
    Check if a message is directed to the bot considering:
    - Explicit @mention of the bot
    - Reply to a message from the bot
    - Mention of Rekku aliases in the text
    - Private messages (always considered directed to bot)
    
    Args:
        message: Telegram message object
        bot: Telegram bot instance
        bot_username: Bot username (optional, will be detected if not provided)
    
    Returns:
        bool: True if message is directed to the bot
    """
    # Private messages are always for the bot
    if message.chat.type == "private":
        log_debug("[mention] Private message - directed to bot")
        return True
    
    # Group/supergroup messages need specific checks
    if message.chat.type in ["group", "supergroup"]:
        text = message.text or message.caption or ""
        
        bot_id = None
        # Get bot username and id if not provided
        if not bot_username:
            try:
                bot_user = await bot.get_me() if hasattr(bot, 'get_me') else None
                if bot_user:
                    if hasattr(bot_user, 'username') and bot_user.username:
                        bot_username = bot_user.username.lower()
                    bot_id = getattr(bot_user, 'id', None)
                else:
                    from core.config import BOT_USERNAME
                    bot_username = BOT_USERNAME.lower()
            except Exception as e:
                log_debug(f"[mention] Failed to get bot username: {e}")
                from core.config import BOT_USERNAME
                bot_username = BOT_USERNAME.lower()
        if bot_id is None:
            if hasattr(bot, 'id'):
                bot_id = bot.id
            elif hasattr(bot, 'user') and hasattr(bot.user, 'id'):
                bot_id = bot.user.id

        # Detect 1:1 chats: only one human participant besides the bot
        user = getattr(message, 'from_user', None)
        if user and not getattr(user, 'is_bot', False):
            chat_id = getattr(message.chat, 'id', None)
            if chat_id is not None:
                humans = _GROUP_CHAT_HUMANS.setdefault(chat_id, set())
                humans.add(user.id)
                human_ids = {uid for uid in humans if uid != bot_id}
                if len(human_ids) <= 1:
                    log_debug("[mention] 1:1 group chat detected - directed to bot")
                    return True
        
        # Check for explicit @mention of the bot
        if message.entities:
            for entity in message.entities:
                if entity.type == "mention":
                    mention_text = text[entity.offset:entity.offset + entity.length].lower()
                    if mention_text == f"@{bot_username}":
                        log_debug(f"[mention] Explicit bot mention found: {mention_text}")
                        return True
        
        # Check if replying to a message from the bot
        if message.reply_to_message and message.reply_to_message.from_user:
            replied_user = message.reply_to_message.from_user
            log_debug(f"[mention] Checking reply to user ID: {replied_user.id}, username: {replied_user.username}")
            
            # Check by user ID (most reliable)
            try:
                # Try async get_me first
                if hasattr(bot, 'get_me'):
                    try:
                        import asyncio
                        if asyncio.iscoroutinefunction(bot.get_me):
                            # If it's async, we can't call it here, fall back to other methods
                            log_debug("[mention] bot.get_me is async, trying alternative methods")
                        else:
                            bot_user = bot.get_me()
                            if bot_user and replied_user.id == bot_user.id:
                                log_debug(f"[mention] Reply to bot message detected (by ID: {bot_user.id})")
                                return True
                    except Exception as e:
                        log_debug(f"[mention] bot.get_me failed: {e}")
                
                # Alternative: check if bot object has an id attribute
                if hasattr(bot, 'id') and replied_user.id == bot.id:
                    log_debug(f"[mention] Reply to bot message detected (by bot.id: {bot.id})")
                    return True
                    
                # Alternative: check if bot object has a user attribute
                if hasattr(bot, 'user') and hasattr(bot.user, 'id') and replied_user.id == bot.user.id:
                    log_debug(f"[mention] Reply to bot message detected (by bot.user.id: {bot.user.id})")
                    return True
                    
            except Exception as e:
                log_debug(f"[mention] Exception in ID check: {e}")
            
            # Fallback: check by username
            if replied_user.username and bot_username:
                if replied_user.username.lower() == bot_username.lower():
                    log_debug(f"[mention] Reply to bot message detected (by username: {replied_user.username})")
                    return True
            
            # Additional fallback: check common bot usernames if we don't have bot_username
            if replied_user.username and not bot_username:
                common_bot_names = ['rekku_freedom_project', 'rekku_the_bot', 'rekkubot']
                if replied_user.username.lower() in common_bot_names:
                    log_debug(f"[mention] Reply to bot message detected (by common name: {replied_user.username})")
                    return True
            
            log_debug(f"[mention] Reply detected but not to bot (replied to: {replied_user.username or replied_user.id})")
        
        # Check for Rekku aliases in text
        if is_rekku_mentioned(text):
            log_debug("[mention] Rekku alias mentioned in text")
            return True
        
        log_debug("[mention] No bot mention detected in group message")
        return False
    
    # For other chat types, default to True (channels, etc.)
    log_debug(f"[mention] Unknown chat type {message.chat.type} - assuming directed to bot")
    return True
