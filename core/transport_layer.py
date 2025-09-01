# core/transport_layer.py
"""Universal transport layer for all interfaces."""

import json
import re
from typing import Any, Dict, Optional
from types import SimpleNamespace
from core.logging_utils import log_debug, log_warning, log_error, log_info

# ``core.telegram_utils`` depends on the optional ``telegram`` package.  Import it
# lazily so that the transport layer can still be imported when that dependency is
# missing.  When unavailable the Telegram-specific helpers become no-ops.
try:  # pragma: no cover - import guard
    from core.telegram_utils import _send_with_retry  # type: ignore
except Exception as e:  # pragma: no cover - executed only when telegram missing
    _send_with_retry = None  # type: ignore
    log_warning(f"[transport] telegram utilities unavailable: {e}")

# Store last JSON parsing error details for corrector hints
LAST_JSON_ERROR_INFO: Optional[str] = None



def _format_json_error(text: str, err: json.JSONDecodeError) -> str:
    """Return a helpful message with context around a JSON error."""
    start = max(0, err.pos - 20)
    end = min(len(text), err.pos + 20)
    snippet = text[start:end]
    pointer = " " * (err.pos - start) + "^"
    return (
        f"{err.msg} at line {err.lineno} column {err.colno}\n"
        f"{snippet}\n{pointer}\n"
        "Tip: escape inner quotes with \\\" and ensure proper commas and brackets."
    )


def extract_json_from_text(text: str, processed_messages: set = None):
    """
    Extract JSON objects or arrays from text.
    
    Args:
        text: The text that may contain JSON
        processed_messages: A set to track already processed messages
        
    Returns:
        A Python dictionary, list, or None if no valid JSON is found.
    """
    global LAST_JSON_ERROR_INFO
    LAST_JSON_ERROR_INFO = None

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
        if any(
            keyword in text
            for keyword in [
                '"error_report"',
                '"correction_needed"',
                '🚨 ACTION PARSING ERRORS DETECTED 🚨',
                'Please fix these actions',
                '"system_message"',
            ]
        ):
            log_debug(
                "[extract_json_from_text] Skipping error report/correction request - not actionable JSON"
            )
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

        decoder = json.JSONDecoder()

        # First, attempt to parse the entire text strictly
        try:
            obj, end = decoder.raw_decode(text)
            remainder = text[end:].strip()
            if remainder:
                log_warning("[extract_json_from_text] Extra content detected after JSON block")
                raise json.JSONDecodeError("Extra data", text, end)
            return obj
        except json.JSONDecodeError:
            pass
        
        # Scan greedily for JSON blocks starting from each '{'
        start_indices = [i for i, char in enumerate(text) if char == '{']
        if not start_indices:
            log_warning("[extract_json_from_text] No starting braces found in text")
            return None
        for start in start_indices:
            try:
                obj, obj_end = decoder.raw_decode(text[start:])
            except json.JSONDecodeError:
                continue
            obj_end += start
            prefix = text[:start].strip()
            suffix = text[obj_end:].strip()
            if prefix or suffix:
                log_warning("[extract_json_from_text] Extra content detected around JSON block")
                raise json.JSONDecodeError("Extra data", text, obj_end)
            return obj
        
        # Scan for JSON arrays starting from each '['
        array_start_indices = [i for i, char in enumerate(text) if char == '[']
        for start in array_start_indices:
            try:
                obj, obj_end = decoder.raw_decode(text[start:])
            except json.JSONDecodeError:
                continue
            obj_end += start
            prefix = text[:start].strip()
            suffix = text[obj_end:].strip()
            if prefix or suffix:
                log_warning("[extract_json_from_text] Extra content detected around JSON block")
                raise json.JSONDecodeError("Extra data", text, obj_end)
            return obj

        # Handle additional cases where JSON is embedded in text
        if 'json' in text.lower():
            start_index = text.lower().find('{')
            if start_index != -1:
                try:
                    obj, obj_end = decoder.raw_decode(text[start_index:])
                except json.JSONDecodeError:
                    log_warning("[extract_json_from_text] Failed to parse embedded JSON")
                else:
                    obj_end += start_index
                    prefix = text[:start_index].strip()
                    suffix = text[obj_end:].strip()
                    if prefix or suffix:
                        log_warning("[extract_json_from_text] Extra content detected around JSON block")
                        raise json.JSONDecodeError("Extra data", text, obj_end)
                    return obj

        # Log a warning if no JSON is found
        log_warning("[extract_json_from_text] No valid JSON found in text")
    except json.JSONDecodeError as e:
        LAST_JSON_ERROR_INFO = _format_json_error(text, e)
        log_warning(f"[extract_json_from_text] JSON decoding error: {LAST_JSON_ERROR_INFO}")
        return None
    except Exception as e:
        LAST_JSON_ERROR_INFO = str(e)
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

            bot = getattr(interface_send_func, '__self__', None) or (
                args[0] if args and hasattr(args[0], 'send_message') else None
            )

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
            message.original_text = text
            message.message_thread_id = kwargs.get('thread_id')
            from datetime import datetime
            message.date = datetime.utcnow()

            # Use centralized action system for all action types.  The action
            # parser is optional, so import it lazily and fall back to sending
            # plain text if it's unavailable.
            try:
                from core.action_parser import run_actions  # type: ignore
            except Exception as e:  # pragma: no cover - executed when action_parser missing
                log_warning(f"[transport] action parser unavailable: {e}")
                return await interface_send_func(*args, text=text, **kwargs)

            context = {"interface": "telegram"}  # Add more context as needed

            processed_actions = []

            # Remove duplicate actions
            unique_actions = []
            seen_actions = set()
            for action in actions:
                action_id = str(action)
                if action_id not in seen_actions:
                    unique_actions.append(action)
                    seen_actions.add(action_id)

            # Process actions using centralized system
            try:
                result = await run_actions(unique_actions, context, bot, message)
                if isinstance(result, dict):
                    processed_actions.extend(result.get("processed", []))
                else:
                    processed_actions = unique_actions
            except Exception as e:
                log_warning(f"[transport] Failed to process actions: {e}")

            log_info(
                f"[transport] Processed {len(processed_actions)} unique JSON actions via plugin system"
            )
            return

        except Exception as e:
            log_warning(f"[transport] Failed to process JSON actions: {e}")

    # Trigger corrector for non-JSON responses (excluding system messages)
    if text and not text.startswith(("[ERROR]", "[WARNING]", "[INFO]", "[DEBUG]")):
        try:
            from core.action_parser import corrector  # type: ignore
        except Exception as e:  # pragma: no cover - executed when action_parser missing
            log_warning(f"[transport] corrector unavailable: {e}")
            return await interface_send_func(*args, text=text, **kwargs)

        bot = getattr(interface_send_func, '__self__', None)
        message = SimpleNamespace()
        message.chat_id = kwargs.get('chat_id') or (args[0] if args else None)
        message.text = text
        message.original_text = text
        message.message_thread_id = kwargs.get('thread_id')
        from datetime import datetime
        message.date = datetime.utcnow()
        errors = ["Invalid or missing JSON in LLM response"]
        if LAST_JSON_ERROR_INFO:
            errors.append(LAST_JSON_ERROR_INFO)
        await corrector(errors, [], bot, message)
        return

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
    if text is None:
        text = ""

    if _send_with_retry is None:  # pragma: no cover - executed when telegram missing
        log_warning("[telegram_transport] telegram utilities unavailable; skipping send")
        return None

    log_debug(f"[telegram_transport] Called with text: {text}")

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
            message.original_text = text
            message.message_thread_id = kwargs.get('thread_id')
            if 'event_id' in kwargs:
                message.event_id = kwargs['event_id']

            # Use centralized action system for all action types.  Import
            # ``run_actions`` lazily so the transport layer still works if the
            # action parser (and its optional dependencies) is missing.
            try:
                from core.action_parser import run_actions  # type: ignore
            except Exception as e:  # pragma: no cover - executed when action_parser missing
                log_warning(f"[telegram_transport] action parser unavailable: {e}")
                # Fall back to sending the original text
                for i in range(0, len(text), chunk_size):
                    chunk = text[i : i + chunk_size]
                    await _send_with_retry(bot, chat_id, chunk, retries, delay, **kwargs)
                return

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

    if not json_data and not is_system_message:
        try:
            from core.action_parser import corrector  # type: ignore
        except Exception as e:  # pragma: no cover - executed when action_parser missing
            log_warning(f"[telegram_transport] corrector unavailable: {e}")
            return

        message = SimpleNamespace()
        message.chat_id = chat_id
        message.text = text
        message.original_text = text
        message.message_thread_id = kwargs.get('thread_id')
        if 'event_id' in kwargs:
            message.event_id = kwargs['event_id']
        from datetime import datetime
        message.date = datetime.utcnow()
        errors = ["Invalid or missing JSON in LLM response"]
        if LAST_JSON_ERROR_INFO:
            errors.append(LAST_JSON_ERROR_INFO)
        await corrector(errors, [], bot, message)
        return

    # Send system messages or plain text with chunking
    log_debug(f"[telegram_transport] Sending as normal text with chunking")
    try:
        for i in range(0, len(text), chunk_size):
            chunk = text[i : i + chunk_size]
            await _send_with_retry(bot, chat_id, chunk, retries, delay, **kwargs)
    except Exception as e:
        log_error(f"[telegram_transport] Failed to send text chunks: {repr(e)}")
        raise
