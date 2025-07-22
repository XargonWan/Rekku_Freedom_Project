# core/transport_layer.py
"""Universal transport layer for all interfaces."""

import json
import re
from typing import Any, Dict, Optional
from core.logging_utils import log_debug, log_warning, log_error
from core.action_parser import parse_action
from core.telegram_utils import _send_with_retry
from types import SimpleNamespace


def extract_json_from_text(text: str) -> Optional[Dict[str, Any]]:
    """
    Extract the first valid JSON block from a given text.

    Args:
        text: The input text containing potential JSON.

    Returns:
        A Python dictionary if a valid JSON block is found, otherwise None.
    """
    try:
        # Scan greedily for JSON blocks starting from each '{'
        start_indices = [i for i, char in enumerate(text) if char == '{']
        for start in start_indices:
            try:
                potential_json = text[start:]
                return json.loads(potential_json)
            except json.JSONDecodeError:
                continue

        return None
    except Exception as e:
        log_warning(f"[extract_json_from_text] Unexpected error: {e}")
        return None


async def universal_send(interface_send_func, *args, text: str = None, **kwargs):
    """
    Universal send function that intercepts JSON actions and parses them.
    
    Args:
        interface_send_func: The actual send function of the interface (e.g., bot.send_message)
        *args: Positional arguments for the interface send function
        text: The text to send (required parameter)
        **kwargs: Additional keyword arguments for the interface send function
    """
    if text is None:
        text = ""

    # Extract JSON from text
    action = extract_json_from_text(text)
    if action:
        log_debug(f"[transport] Detected JSON action, parsing: {action}")
        try:
            if not all(k in action for k in ("type", "interface", "payload")):
                log_debug(f"[transport] JSON action missing required fields: {action}")
                return await interface_send_func(*args, text=text, **kwargs)

            message = SimpleNamespace()
            message.chat_id = kwargs.get('chat_id') or (args[0] if args else None)
            message.text = ""

            bot = getattr(interface_send_func, '__self__', None) or (args[0] if args and hasattr(args[0], 'send_message') else None)

            if bot:
                await parse_action(action, bot, message)
                return
            else:
                log_warning("[transport] Could not extract bot instance for action parsing")
        except Exception as e:
            log_warning(f"[transport] Failed to process JSON action: {e}")

    # Send as normal text
    return await interface_send_func(*args, text=text, **kwargs)


async def telegram_safe_send(bot, chat_id: int, text: str, chunk_size: int = 4000, retries: int = 3, delay: int = 2, **kwargs):
    """Telegram-specific wrapper for universal_send with chunking support."""
    log_debug(f"[telegram_transport] Called with text: {text[:100]}...")

    if text is None:
        text = ""

    action = extract_json_from_text(text)
    if action:
        log_debug(f"[telegram_transport] JSON parsed successfully: {action}")
        try:
            if not all(k in action for k in ("type", "interface", "payload")):
                log_debug(f"[telegram_transport] JSON action missing required fields: {action}")
                return

            message = SimpleNamespace()
            message.chat_id = chat_id
            message.text = ""

            await parse_action(action, bot, message)
            log_debug(f"[telegram_transport] Action processed successfully, not sending as text")
            return
        except Exception as e:
            log_warning(f"[telegram_transport] Failed to process JSON action: {e}")

    # Send as normal text with chunking
    log_debug(f"[telegram_transport] Sending as normal text with chunking")
    try:
        for i in range(0, len(text), chunk_size):
            chunk = text[i : i + chunk_size]
            await _send_with_retry(bot, chat_id, chunk, retries, delay, **kwargs)
    except Exception as e:
        log_error(f"[telegram_transport] Failed to send text chunks: {e}")
        raise
