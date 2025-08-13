# core/transport_layer.py
"""Universal transport layer for all interfaces."""

import json
import re
import time
from typing import Any, Dict, Optional
from types import SimpleNamespace
from core.logging_utils import log_debug, log_warning, log_error, log_info
from core.action_parser import parse_action
from core.telegram_utils import _send_with_retry

# Global dictionary to track retry attempts per chat/message thread
_retry_tracker = {}


def _get_retry_key(message):
    """Generate a unique key for tracking retries based on chat/thread."""
    chat_id = getattr(message, 'chat_id', None)
    thread_id = getattr(message, 'message_thread_id', None)
    return f"{chat_id}_{thread_id}"


def _should_retry(message, max_retries: int = 2) -> bool:
    """Check if we should attempt retry for this message context."""
    retry_key = _get_retry_key(message)
    current_time = time.time()
    
    # Clean up old retry entries (older than 5 minutes)
    cutoff_time = current_time - 300  # 5 minutes
    keys_to_remove = [k for k, (count, timestamp) in _retry_tracker.items() 
                      if timestamp < cutoff_time]
    for key in keys_to_remove:
        del _retry_tracker[key]
    
    # Check current retry count
    retry_count, _ = _retry_tracker.get(retry_key, (0, current_time))
    return retry_count < max_retries


def _increment_retry(message):
    """Increment retry count for this message context."""
    retry_key = _get_retry_key(message)
    current_time = time.time()
    retry_count, _ = _retry_tracker.get(retry_key, (0, current_time))
    _retry_tracker[retry_key] = (retry_count + 1, current_time)
    return retry_count + 1


def extract_json_from_text(text: str, processed_messages: set = None):
    """
    Extract JSON objects or arrays from text.
    
    Args:
        text: The text that may contain JSON
        processed_messages: A set to track already processed messages
        
    Returns:
        A Python dictionary, list, or None if no valid JSON is found.
    """
    try:
        text = text.strip()

        # Initialize processed_messages if not provided
        if processed_messages is None:
            processed_messages = set()

        # Check if the message has already been processed
        if text in processed_messages:
            log_debug("[extract_json_from_text] Message already processed, skipping.")
            return None

        # Mark the message as processed
        processed_messages.add(text)
        
        # Don't parse JSON from system/error messages or error reports
        if text.startswith(('[ERROR]', '[WARNING]', '[INFO]', '[DEBUG]')):
            log_debug("[extract_json_from_text] Skipping system message - not JSON")
            return None
            
        # Don't parse JSON from error reports or correction requests
        if any(keyword in text for keyword in ['"error_report"', '"correction_needed"', '🚨 ACTION PARSING ERRORS DETECTED 🚨', 'Please fix these actions']):
            log_debug("[extract_json_from_text] Skipping error report/correction request - not actionable JSON")
            return None
        
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
        if not start_indices:
            log_warning("[extract_json_from_text] No starting braces found in text")
            return None
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
        
        # If complete object search failed and we have start indices, try the rest of the text from the last position
        if start_indices:
            try:
                potential_json = text[start_indices[-1]:]
                return json.loads(potential_json)
            except json.JSONDecodeError:
                pass
        
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
        
        # If complete array search failed and we have array start indices, try the rest of the text from the last position
        if array_start_indices:
            try:
                potential_json = text[array_start_indices[-1]:]
                return json.loads(potential_json)
            except json.JSONDecodeError:
                pass

        # Handle additional cases where JSON is embedded in text
        if 'json' in text.lower():
            start_index = text.lower().find('{')
            end_index = text.rfind('}')
            if start_index != -1 and end_index != -1:
                potential_json = text[start_index:end_index + 1]
                try:
                    return json.loads(potential_json)
                except json.JSONDecodeError:
                    log_warning("[extract_json_from_text] Failed to parse embedded JSON")

        # Log a warning if no JSON is found
        log_warning("[extract_json_from_text] No valid JSON found in text")
    except Exception as e:
        log_warning(f"[extract_json_from_text] Unexpected error: {e}")
        return None


async def _handle_action_errors(errors: list, failed_actions: list, bot, message):
    """Handle action parsing errors by requesting LLM to fix them."""
    
    # Check if we should retry based on the new tracking system
    if not _should_retry(message, max_retries=2):
        retry_key = _get_retry_key(message)
        retry_count, _ = _retry_tracker.get(retry_key, (0, 0))
        log_warning(f"[transport] Max retries ({retry_count}) reached for action correction. Giving up.")
        return
    
    # Validate message has valid chat_id before proceeding
    if not hasattr(message, 'chat_id') or message.chat_id is None:
        log_warning(f"[transport] Cannot request correction: invalid chat_id in message: {getattr(message, 'chat_id', 'None')}")
        return
    
    # Increment retry counter
    retry_count = _increment_retry(message)
    
    # Create error summary for LLM
    error_summary = "\n".join([f"- {error}" for error in errors[:5]])  # Limit to 5 errors
    failed_actions_json = json.dumps(failed_actions, indent=2)
    
    correction_prompt = f"""
🚨 ACTION PARSING ERRORS DETECTED 🚨

The following actions failed to parse:
{failed_actions_json}

Errors encountered:
{error_summary}

Please fix these actions and provide ONLY the corrected JSON. Use the exact interface names and action formats that are available.

Important:
- Fix ONLY the interface field and other structural issues  
- Do not change the intent or payload content
- Return ONLY valid JSON, no explanations
- Use the available interfaces shown in the error messages

Attempt: {retry_count}/2
"""
    
    log_info(f"[transport] Requesting action correction from LLM (attempt {retry_count}/2)")
    
    try:
        # Send correction request back to LLM via the same message flow
        from core import plugin_instance
        
        # Create a mock message for the correction request
        correction_message = SimpleNamespace()
        correction_message.chat_id = message.chat_id  
        correction_message.text = correction_prompt
        correction_message.message_thread_id = getattr(message, 'message_thread_id', None)
        correction_message.date = message.date
        correction_message.from_user = getattr(message, 'from_user', None)
        
        # Send to LLM for correction
        llm_plugin = getattr(plugin_instance, "plugin", None)
        if llm_plugin and hasattr(llm_plugin, 'handle_incoming_message'):
            await llm_plugin.handle_incoming_message(bot, correction_message, correction_prompt)
        else:
            log_warning("[transport] No LLM plugin available for action correction")
            
    except Exception as e:
        log_error(f"[transport] Failed to request action correction: {e}")


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

    # Log LLM response for debugging
    if text:
        preview = text[:200] + "..." if len(text) > 200 else text
        log_info(f"[transport] 🤖 LLM Response: {preview}")

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
            chat_id_value = kwargs.get('chat_id') or (args[0] if args else None)
            
            # Validate chat_id before proceeding
            if chat_id_value is None or not isinstance(chat_id_value, int):
                log_warning(f"[transport] Invalid chat_id for action processing: {chat_id_value}")
                return await interface_send_func(*args, text=text, **kwargs)
                
            message.chat_id = chat_id_value
            message.text = ""
            message.message_thread_id = kwargs.get('message_thread_id')
            from datetime import datetime
            message.date = datetime.utcnow()

            # Use centralized action system for all action types
            from core.action_parser import run_actions
            context = {"interface": "telegram"}  # Add more context as needed
            
            # Collect errors for auto-correction
            errors = []
            processed_actions = []
            
            # Remove duplicate actions
            unique_actions = []
            seen_actions = set()
            for action in actions:
                action_id = str(action)
                if action_id not in seen_actions:
                    unique_actions.append(action)
                    seen_actions.add(action_id)

            # Process actions and collect errors
            try:
                result = await run_actions(unique_actions, context, bot, message)
                if isinstance(result, dict) and "errors" in result:
                    errors.extend(result["errors"])
                    processed_actions.extend(result.get("processed", []))
                else:
                    processed_actions = unique_actions
            except Exception as e:
                errors.append(f"Processing error: {e}")
            
            # If there are errors, try auto-correction (max 2 attempts)
            if errors and hasattr(message, 'chat_id'):
                await _handle_action_errors(errors, unique_actions, bot, message)
            elif errors:
                log_warning(f"[transport] Action errors detected but no valid chat_id for correction: {errors[:3]}")
            
            log_info(f"[transport] Processed {len(processed_actions)} unique JSON actions via plugin system")
            return
            
        except Exception as e:
            log_warning(f"[transport] Failed to process JSON actions: {e}")

    # Send as normal text
    return await interface_send_func(*args, text=text, **kwargs)


async def telegram_safe_send(bot, chat_id: int, text: str, chunk_size: int = 4000, retries: int = 3, delay: int = 2, **kwargs):
    """Telegram-specific wrapper with chunking and retry support.
    
    This function is separate from universal_send because it provides:
    1. Automatic chunking for long messages (4000 chars)
    2. Built-in retry logic with delays
    3. Telegram-specific error handling
    4. Direct bot instance access
    
    For other interfaces, use universal_send which is more generic.
    """
    log_debug(f"[telegram_transport] Called with text: {text[:100]}...")

    if text is None:
        text = ""

    if 'reply_to_message_id' in kwargs and not kwargs['reply_to_message_id']:
        log_warning("[telegram_transport] reply_to_message_id not found. Sending without replying.")
        kwargs.pop('reply_to_message_id')

    # Validate chat_id first
    if chat_id is None or not isinstance(chat_id, int):
        log_error(f"[telegram_transport] Invalid chat_id provided: {chat_id}")
        return None

    # Don't try to parse JSON from system/error messages
    is_system_message = text.startswith(('[ERROR]', '[WARNING]', '[INFO]', '[DEBUG]'))
    
    json_data = None
    if not is_system_message:
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
            if 'event_id' in kwargs:
                message.event_id = kwargs['event_id']

            # Use centralized action system for all action types
            from core.action_parser import run_actions
            context = {"interface": "telegram"}
            if 'event_id' in kwargs:
                context['event_id'] = kwargs['event_id']
            
            # Rimuovi azioni duplicate
            unique_actions = []
            seen_actions = set()
            for action in actions:
                action_id = str(action)  # Converti l'azione in stringa per un confronto semplice
                if action_id not in seen_actions:
                    unique_actions.append(action)
                    seen_actions.add(action_id)

            # Usa il sistema centralizzato per le azioni uniche
            await run_actions(unique_actions, context, bot, message)
            log_info(f"[telegram_transport] Processed {len(unique_actions)} unique JSON actions via plugin system")
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
        log_error(f"[telegram_transport] Failed to send text chunks: {repr(e)}")
        raise
