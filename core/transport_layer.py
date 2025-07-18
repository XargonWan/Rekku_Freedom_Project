# core/transport_layer.py
"""Universal transport layer for all interfaces."""

import json
from typing import Any, Dict, Optional
from core.logging_utils import log_debug, log_warning, log_error
from core.action_parser import parse_action
from types import SimpleNamespace


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
    
    # Check if text is a JSON action and parse it
    text_stripped = text.strip()
    if text_stripped.startswith('{') and text_stripped.endswith('}'):
        try:
            action = json.loads(text_stripped)
            if isinstance(action, dict) and action.get("type") and action.get("interface") and action.get("payload"):
                log_debug(f"[transport] Detected JSON action, parsing: {action}")
                
                # Create a universal message object for the parser
                message = SimpleNamespace()
                message.chat_id = kwargs.get('chat_id') or (args[0] if args else None)
                message.text = ""
                
                # Extract bot from the interface function (if it's a method)
                bot = getattr(interface_send_func, '__self__', None)
                if bot is None:
                    # Try to get bot from first argument if it's not a method
                    bot = args[0] if args and hasattr(args[0], 'send_message') else None
                
                if bot:
                    await parse_action(action, bot, message)
                    return  # Action processed, don't send as text
                else:
                    log_warning("[transport] Could not extract bot instance for action parsing")
        except (json.JSONDecodeError, Exception) as e:
            log_warning(f"[transport] Failed to parse potential JSON action: {e}")
            # Fall through to normal text sending
    
    # Send as normal text through the interface
    return await interface_send_func(*args, text=text, **kwargs)


async def telegram_safe_send(bot, chat_id: int, text: str, chunk_size: int = 4000, retries: int = 3, delay: int = 2, **kwargs):
    """Telegram-specific wrapper for universal_send with chunking support."""
    log_debug(f"[telegram_transport] Called with text: {text[:100]}...")
    
    if text is None:
        text = ""
    
    # For Telegram, we need to handle chunking and the specific send function
    from core.telegram_utils import _send_with_retry
    import re
    
    # Try to extract JSON from potentially dirty text
    json_extracted = None
    text_stripped = text.strip()
    
    try:
        # Method 1: Check if entire text is JSON
        if text_stripped.startswith('{') and text_stripped.endswith('}'):
            json_extracted = text_stripped
            log_debug(f"[telegram_transport] Method 1: Entire text appears to be JSON")
        else:
            # Method 2: Look for JSON block within the text using regex
            json_pattern = r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}'
            try:
                json_matches = re.findall(json_pattern, text, re.DOTALL)
                
                if json_matches:
                    # Try each match to see if it's a valid action
                    for match in json_matches:
                        try:
                            test_action = json.loads(match.strip())
                            if isinstance(test_action, dict) and test_action.get("type") and test_action.get("interface") and test_action.get("payload"):
                                json_extracted = match.strip()
                                log_debug(f"[telegram_transport] Method 2: Found valid JSON action in text: {json_extracted[:100]}...")
                                break
                        except (json.JSONDecodeError, Exception):
                            continue
            except re.error as regex_error:
                log_warning(f"[telegram_transport] Method 2 regex failed: {regex_error}")
            
            # Method 3: Look for JSON between markers or common patterns
            if not json_extracted:
                patterns = [
                    r'```json\s*(\{.*?\})\s*```',  # Markdown code blocks
                    r'```\s*(\{.*?\})\s*```',      # Plain code blocks
                    r'json\s*[:\s]*(\{.*?\})',     # "json:" followed by JSON
                    r'(\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\})'  # Simple nested JSON pattern
                ]
                
                for pattern in patterns:
                    try:
                        matches = re.findall(pattern, text, re.DOTALL | re.IGNORECASE)
                        for match in matches:
                            try:
                                test_action = json.loads(match.strip())
                                if isinstance(test_action, dict) and test_action.get("type") and test_action.get("interface") and test_action.get("payload"):
                                    json_extracted = match.strip()
                                    log_debug(f"[telegram_transport] Method 3: Found valid JSON action with pattern: {json_extracted[:100]}...")
                                    break
                            except (json.JSONDecodeError, Exception):
                                continue
                        if json_extracted:
                            break
                    except re.error as regex_error:
                        log_warning(f"[telegram_transport] Regex pattern failed: {pattern} - {regex_error}")
                        continue
        
        # If we found JSON, try to parse it
        if json_extracted:
            try:
                action = json.loads(json_extracted)
                log_debug(f"[telegram_transport] JSON parsed successfully: {action}")
                
                if isinstance(action, dict) and action.get("type") and action.get("interface") and action.get("payload"):
                    log_debug(f"[telegram_transport] Valid JSON action detected, parsing: {action}")
                    
                    message = SimpleNamespace()
                    message.chat_id = chat_id
                    message.text = ""
                    
                    await parse_action(action, bot, message)
                    log_debug(f"[telegram_transport] Action processed successfully, not sending as text")
                    return  # Action processed, don't send as text
                else:
                    log_debug(f"[telegram_transport] JSON is not a valid action: type={action.get('type')}, interface={action.get('interface')}, payload={action.get('payload')}")
            except (json.JSONDecodeError, Exception) as e:
                log_warning(f"[telegram_transport] Failed to parse extracted JSON: {e}")
                # Fall through to normal text sending
        else:
            log_debug(f"[telegram_transport] No valid JSON found in text, sending as normal text")
    
    except Exception as e:
        log_error(f"[telegram_transport] Unexpected error during JSON processing: {e}")
        # Fall through to normal text sending
    
    # Send as normal text with chunking
    log_debug(f"[telegram_transport] Sending as normal text with chunking")
    try:
        for i in range(0, len(text), chunk_size):
            chunk = text[i : i + chunk_size]
            await _send_with_retry(bot, chat_id, chunk, retries, delay, **kwargs)
    except Exception as e:
        log_error(f"[telegram_transport] Failed to send text chunks: {e}")
        raise
