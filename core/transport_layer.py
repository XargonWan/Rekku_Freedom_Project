# core/transport_layer.py
"""Universal transport layer for all interfaces."""

import json
import re
from typing import Any, Dict, Optional
from core.logging_utils import log_debug, log_warning, log_error, log_info
from core.action_parser import parse_action
from core.telegram_utils import _send_with_retry
from types import SimpleNamespace


def extract_json_from_text(text: str):
    """
    Extract JSON objects or arrays from text.
    
    Args:
        text: The text that may contain JSON
        
    Returns:
        A Python dictionary, list, or None if no valid JSON is found.
    """
    try:
        text = text.strip()
        
        # Handle the common ChatGPT pattern: "json\nCopy\nEdit\n{...}"
        if text.startswith("json\nCopy\nEdit\n"):
            text = text[len("json\nCopy\nEdit\n"):].strip()
            log_debug("[extract_json_from_text] Removed ChatGPT prefix 'json\\nCopy\\nEdit\\n'")
        elif text.startswith("json\n"):
            # Also handle just "json\n" prefix
            lines = text.split('\n')
            if len(lines) >= 4 and lines[1].strip() in ['Copy', ''] and lines[2].strip() in ['Edit', '']:
                # Skip the first 3-4 lines that contain json/Copy/Edit
                text = '\n'.join(lines[3:]).strip()
                log_debug("[extract_json_from_text] Removed ChatGPT prefix lines")
        
        # Check if the entire text is a JSON array
        if text.startswith('[') and text.endswith(']'):
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                pass
        
        # Check if the entire text is a JSON object
        if text.startswith('{') and text.endswith('}'):
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                pass
        
        # Scan greedily for JSON blocks starting from each '{' (backward compatibility)
        start_indices = [i for i, char in enumerate(text) if char == '{']
        for start in start_indices:
            # Try to find the matching closing brace for a complete JSON object
            brace_count = 0
            for end in range(start, len(text)):
                if text[end] == '{':
                    brace_count += 1
                elif text[end] == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        # Found a complete JSON object
                        try:
                            potential_json = text[start:end+1]
                            return json.loads(potential_json)
                        except json.JSONDecodeError:
                            continue
            
            # If complete object search failed, try the rest of the text from this position
            try:
                potential_json = text[start:]
                return json.loads(potential_json)
            except json.JSONDecodeError:
                continue
        
        # Scan for JSON arrays starting from each '['
        array_start_indices = [i for i, char in enumerate(text) if char == '[']
        for start in array_start_indices:
            # Try to find the matching closing bracket for a complete JSON array
            bracket_count = 0
            for end in range(start, len(text)):
                if text[end] == '[':
                    bracket_count += 1
                elif text[end] == ']':
                    bracket_count -= 1
                    if bracket_count == 0:
                        # Found a complete JSON array
                        try:
                            potential_json = text[start:end+1]
                            return json.loads(potential_json)
                        except json.JSONDecodeError:
                            continue
            
            # If complete array search failed, try the rest of the text from this position
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
    json_data = extract_json_from_text(text)
    if json_data:
        log_debug(f"[transport] Detected JSON data, parsing: {json_data}")
        try:
            # Handle new nested actions format
            if isinstance(json_data, dict) and "actions" in json_data:
                actions = json_data["actions"]
                if not isinstance(actions, list):
                    log_warning("[transport] actions field must be a list")
                    return await interface_send_func(*args, text=text, **kwargs)
            # Fallback to legacy array format
            elif isinstance(json_data, list):
                actions = json_data
            # Fallback to legacy single action format
            elif isinstance(json_data, dict) and "type" in json_data:
                actions = [json_data]
            else:
                log_warning(f"[transport] Unrecognized JSON structure: {json_data}")
                return await interface_send_func(*args, text=text, **kwargs)
            
            bot = getattr(interface_send_func, '__self__', None) or (args[0] if args and hasattr(args[0], 'send_message') else None)
            
            if not bot:
                log_warning("[transport] Could not extract bot instance for action parsing")
                return await interface_send_func(*args, text=text, **kwargs)
            
            # Create message context for actions
            message = SimpleNamespace()
            message.chat_id = kwargs.get('chat_id') or (args[0] if args else None)
            message.text = ""
            message.message_thread_id = kwargs.get('message_thread_id')

            # Use centralized action system for all action types
            from core.action_parser import run_actions
            context = {"interface": "telegram"}  # Add more context as needed
            
            await run_actions(actions, context, bot, message)
            log_info(f"[transport] Processed {len(actions)} JSON actions via plugin system")
            return
            
        except Exception as e:
            log_warning(f"[transport] Failed to process JSON actions: {e}")

    # Send as normal text
    return await interface_send_func(*args, text=text, **kwargs)


async def telegram_safe_send(bot, chat_id: int, text: str, chunk_size: int = 4000, retries: int = 3, delay: int = 2, **kwargs):
    """Telegram-specific wrapper for universal_send with chunking support."""
    log_debug(f"[telegram_transport] Called with text: {text[:100]}...")

    if text is None:
        text = ""

    json_data = extract_json_from_text(text)
    if json_data:
        log_debug(f"[telegram_transport] JSON parsed successfully: {json_data}")
    else:
        # Check if text looks like it might contain JSON but failed to parse
        if ('{' in text and '}' in text) or ('[' in text and ']' in text):
            log_warning(f"[telegram_transport] Text contains JSON-like content but failed to parse: {text[:200]}...")
            # Try to extract and log the potential JSON part for debugging
            if '{' in text:
                start_brace = text.find('{')
                log_debug(f"[telegram_transport] JSON-like content starting at position {start_brace}: {text[start_brace:start_brace+100]}...")
        else:
            log_debug("[telegram_transport] No JSON-like content detected, sending as normal text")
    
    if json_data:
        log_debug(f"[telegram_transport] JSON parsed successfully: {json_data}")
        try:
            # Handle new nested actions format
            if isinstance(json_data, dict) and "actions" in json_data:
                actions = json_data["actions"]
                if not isinstance(actions, list):
                    log_warning("[telegram_transport] actions field must be a list")
                    # Fall back to text sending
                    for i in range(0, len(text), chunk_size):
                        chunk = text[i : i + chunk_size]
                        await _send_with_retry(bot, chat_id, chunk, retries, delay, **kwargs)
                    return
            # Fallback to legacy array format
            elif isinstance(json_data, list):
                actions = json_data
            # Fallback to legacy single action format
            elif isinstance(json_data, dict) and "type" in json_data:
                actions = [json_data]
            else:
                log_warning(f"[telegram_transport] Unrecognized JSON structure: {json_data}")
                # Fall back to text sending
                for i in range(0, len(text), chunk_size):
                    chunk = text[i : i + chunk_size]
                    await _send_with_retry(bot, chat_id, chunk, retries, delay, **kwargs)
                return
            
            # Create message context for actions
            message = SimpleNamespace()
            message.chat_id = chat_id
            message.text = ""
            message.message_thread_id = kwargs.get('message_thread_id')

            # Use centralized action system for all action types
            from core.action_parser import run_actions
            context = {"interface": "telegram"}
            
            await run_actions(actions, context, bot, message)
            log_info(f"[telegram_transport] Processed {len(actions)} JSON actions via plugin system")
            return
            
        except Exception as e:
            log_warning(f"[telegram_transport] Failed to process JSON actions: {e}")

    # Send as normal text with chunking
    log_debug(f"[telegram_transport] Sending as normal text with chunking")
    try:
        for i in range(0, len(text), chunk_size):
            chunk = text[i : i + chunk_size]
            await _send_with_retry(bot, chat_id, chunk, retries, delay, **kwargs)
    except Exception as e:
        log_error(f"[telegram_transport] Failed to send text chunks: {e}")
        raise
