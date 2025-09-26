# core/transport_layer.py
"""Universal transport layer for all interfaces."""

import json
import re
import asyncio
import contextvars
from typing import Any, Dict, Optional
from types import SimpleNamespace
from core.logging_utils import log_debug, log_warning, log_error, log_info

# Interface-specific utilities are loaded dynamically by interfaces.
# The transport layer provides generic messaging functionality only.

# Store last JSON parsing error details for corrector hints
LAST_JSON_ERROR_INFO: Optional[str] = None

# Track chat_ids for which core initiated a system-message correction request
# Format: {chat_id: timestamp} to allow timeout cleanup
_EXPECTING_SYSTEM_REPLY: dict = {}

def _get_system_reply_timeout():
    """Get the system reply timeout from config, default to 10 minutes."""
    try:
        import os
        timeout = int(os.getenv('AWAIT_RESPONSE_TIMEOUT', '600'))
        return timeout
    except (ValueError, TypeError):
        return 600  # 10 minutes default


def _cleanup_expired_system_replies():
    """Remove expired entries from _EXPECTING_SYSTEM_REPLY."""
    import time
    current_time = time.time()
    timeout = _get_system_reply_timeout()
    expired_keys = [
        chat_id for chat_id, timestamp in _EXPECTING_SYSTEM_REPLY.items()
        if current_time - timestamp > timeout
    ]
    for chat_id in expired_keys:
        del _EXPECTING_SYSTEM_REPLY[chat_id]
        log_debug(f"[transport] Removed expired system reply expectation for chat_id={chat_id} (timeout={timeout}s)")


def _add_system_reply_expectation(chat_id: str):
    """Add a system reply expectation with timestamp."""
    import time
    _cleanup_expired_system_replies()  # Clean up expired ones first
    _EXPECTING_SYSTEM_REPLY[chat_id] = time.time()


def _remove_system_reply_expectation(chat_id: str):
    """Remove a system reply expectation."""
    if chat_id in _EXPECTING_SYSTEM_REPLY:
        del _EXPECTING_SYSTEM_REPLY[chat_id]


def _is_expecting_system_reply(chat_id: str) -> bool:
    """Check if we're expecting a system reply for the given chat_id."""
    _cleanup_expired_system_replies()  # Clean up expired ones first
    return chat_id in _EXPECTING_SYSTEM_REPLY


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


def extract_json_from_text(text: str) -> Optional[Dict]:
    """Extract the first valid JSON object or array from text."""
    if not text:
        return None
    
    # Try to clean up common markdown/formatting issues
    cleaned_text = text.strip()
    
    # Remove markdown code blocks if present
    if cleaned_text.startswith('```json'):
        cleaned_text = cleaned_text[7:]  # Remove ```json
        if cleaned_text.endswith('```'):
            cleaned_text = cleaned_text[:-3]  # Remove ```
        cleaned_text = cleaned_text.strip()
    elif cleaned_text.startswith('```'):
        cleaned_text = cleaned_text[3:]  # Remove ```
        if cleaned_text.endswith('```'):
            cleaned_text = cleaned_text[:-3]  # Remove ```
        cleaned_text = cleaned_text.strip()
    
    # Also try original text in case cleaning broke something
    texts_to_try = [cleaned_text, text.strip()]
    
    decoder = json.JSONDecoder()
    
    for text_variant in texts_to_try:
        log_debug(f"[extract_json_from_text] Trying text variant (length: {len(text_variant)})")
        
        # Scan for JSON objects starting from each '{'
        object_start_indices = [i for i, char in enumerate(text_variant) if char == '{']
        if not object_start_indices:
            log_debug("[extract_json_from_text] No starting braces found in text variant")
            continue
            
        for start in object_start_indices:
            try:
                obj, obj_end = decoder.raw_decode(text_variant[start:])
                obj_end += start
                prefix = text_variant[:start].strip()
                suffix = text_variant[obj_end:].strip()
                if prefix or suffix:
                    log_debug(f"[extract_json_from_text] Extra content detected around JSON object (prefix: {len(prefix)} chars, suffix: {len(suffix)} chars)")
                # Return JSON even if there's extra content - actions can still be executed
                log_debug(f"[extract_json_from_text] Found valid JSON object: {type(obj)}")
                return obj
            except json.JSONDecodeError as e:
                log_debug(f"[extract_json_from_text] JSON decode error at position {start}: {e}")
                continue
        
        # Scan for JSON arrays starting from each '['
        array_start_indices = [i for i, char in enumerate(text_variant) if char == '[']
        for start in array_start_indices:
            try:
                obj, obj_end = decoder.raw_decode(text_variant[start:])
                obj_end += start
                prefix = text_variant[:start].strip()
                suffix = text_variant[obj_end:].strip()
                if prefix or suffix:
                    log_debug(f"[extract_json_from_text] Extra content detected around JSON array (prefix: {len(prefix)} chars, suffix: {len(suffix)} chars)")
                # Return JSON even if there's extra content - actions can still be executed
                log_debug(f"[extract_json_from_text] Found valid JSON array: {type(obj)}")
                return obj
            except json.JSONDecodeError as e:
                log_debug(f"[extract_json_from_text] JSON decode error at position {start}: {e}")
                continue
    
    log_debug("[extract_json_from_text] No valid JSON found in text")
    log_debug(f"[extract_json_from_text] Text content (first 500 chars): {text[:500]}")
    log_debug(f"[extract_json_from_text] Text content (last 500 chars): {text[-500:]}")
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

    # Diagnostic: log interface function and runtime send parameters
    try:
        bot_self = getattr(interface_send_func, '__self__', None)
        log_debug(f"[transport] universal_send called: interface_send_func={interface_send_func} bot_self={bot_self} args={args} kwargs_keys={list(kwargs.keys())}")
    except Exception as _:
        log_debug("[transport] universal_send diagnostic logging failed to inspect interface_send_func")

    # Log LLM response for debugging
    if text:
        preview = text[:200] + "..." if len(text) > 200 else text
        log_info(f"[transport] 🤖 LLM Response: {preview}")
    # Flow trace: record that transport received LLM output
    try:
        log_debug(f"[flow] transport.received -> text_len={len(text)}")
    except Exception:
        pass

    # Extract JSON from text
    json_data = extract_json_from_text(text)
    if json_data:
        log_debug(f"[transport] Detected JSON data, parsing: {json_data}")
        try:
            log_debug(f"[flow] transport.detects_json -> will attempt run_actions")
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

            # Accept int or numeric string chat IDs (some interfaces provide strings)
            if chat_id_value is None or not isinstance(chat_id_value, (int, str)):
                log_warning(f"[transport] Invalid chat_id for action processing: {chat_id_value}")
                return await interface_send_func(*args, text=text, **kwargs)

            # Coerce numeric string to int when possible for internal consistency
            if isinstance(chat_id_value, str) and chat_id_value.strip().lstrip('-').isdigit():
                try:
                    chat_id_value = int(chat_id_value)
                except Exception:
                    # Keep as string if coercion fails
                    pass

            message.chat_id = chat_id_value
            message.text = ""
            message.original_text = text
            message.thread_id = kwargs.get('thread_id')
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

            # Determine current interface from bot
            current_interface = "unknown"  # default fallback
            if hasattr(bot, 'get_interface_id'):
                try:
                    current_interface = bot.get_interface_id()
                except Exception as e:
                    log_debug(f"[transport] Could not get interface_id from bot: {e}")
            
            context = {
                "interface": current_interface,
                "original_chat_id": chat_id_value,
                "original_thread_id": kwargs.get('thread_id'),
                "original_text": text[:500] if text else "",  # Include preview of original text
                "thread_defaults": {
                    "default": None
                }
            }  # Add more context as needed

            # Filter actions to only include those for the current interface
            current_interface_actions = []
            cross_interface_actions = []
            
            for action in actions:
                action_type = action.get("type", "")
                # Check if action belongs to current interface
                if action_type.endswith(f"_{current_interface}"):
                    current_interface_actions.append(action)
                else:
                    cross_interface_actions.append(action)
                    log_debug(f"[transport] Skipping cross-interface action {action_type} (current: {current_interface})")
            
            if cross_interface_actions:
                log_info(f"[transport] Filtered {len(cross_interface_actions)} cross-interface actions, processing {len(current_interface_actions)} for {current_interface}")
            
            # Only process actions for current interface
            if current_interface_actions:
                try:
                    result = await run_actions(current_interface_actions, context, bot, message)
                    processed_actions = result.get("processed", []) if isinstance(result, dict) else current_interface_actions
                except Exception as e:
                    log_warning(f"[transport] Failed to process actions: {e}")
                    processed_actions = []
                finally:
                    log_debug(f"[flow] transport.after_run_actions -> processed_count={len(processed_actions)}")

                log_info(
                    f"[transport] Processed {len(processed_actions)} unique JSON actions via plugin system"
                )
                return
            else:
                # No actions for current interface, send as plain text
                log_debug(f"[transport] No actions for current interface {current_interface}, sending as plain text")
                return await interface_send_func(*args, text=text, **kwargs)

        except Exception as e:
            log_warning(f"[transport] Failed to process JSON actions: {e}")

    # Non-JSON plain text — forward directly. Corrector is only run in llm_to_interface.
    if text and not text.startswith(("[ERROR]", "[WARNING]", "[INFO]", "[DEBUG]")):
        log_debug(f"[flow] transport.non_json -> forwarding plain text (no in-line corrector) chat_id={kwargs.get('chat_id')}")
        return await interface_send_func(*args, text=text, **kwargs)

    # Send as normal text
    log_debug(f"[flow] transport.forward_plain -> calling interface_send_func for chat_id={kwargs.get('chat_id')}")
    return await interface_send_func(*args, text=text, **kwargs)


# Re-entry guard removed: rely solely on the corrector retry counter to avoid loops

async def run_corrector_middleware(text: str, bot=None, context: dict = None, chat_id=None) -> str:
    """Attempt to obtain a corrected LLM output that contains valid JSON actions.

    Strategy:
    - If the text already contains valid JSON, return it immediately.
    - Otherwise, attempt up to CORRECTOR_RETRIES to ask the active LLM plugin to produce
      a corrected reply. If the plugin returns a reply that contains valid JSON, return it.
    - If no correction succeeds, return None to indicate blocking.

    This function is intentionally best-effort and non-blocking for the system: if no
    active LLM plugin is available it will log and return None.
    """
    try:
        # Avoid circular imports at module import time
        from core import action_parser
        from core.logging_utils import log_debug, log_info, log_warning
        from core.prompt_engine import build_full_json_instructions
        from types import SimpleNamespace
    except Exception as e:
        try:
            log_warning(f"[corrector_middleware] Import error: {e}")
        except Exception:
            pass
        return None

    max_retries = getattr(action_parser, 'CORRECTOR_RETRIES', 2)

    # Extract message from context if available
    message = context.get('message') if context else None

    # If already valid JSON, nothing to do
    try:
        if extract_json_from_text(text):
            log_debug = globals().get('log_debug')
            if log_debug:
                log_debug("[corrector_middleware] Input already contains JSON; skipping correction")
            return text
    except Exception:
        pass

    # Don't correct system messages or messages that clearly don't need correction
    if text and ("system_message" in text or text.startswith(("[ERROR]", "[WARNING]", "[INFO]", "[DEBUG]"))):
        log_debug("[corrector_middleware] Text appears to be system message; skipping correction to prevent loops")
        return None

    last_error_hint = LAST_JSON_ERROR_INFO or "Invalid or missing JSON"

    llm_plugin = None  # Store the plugin for later use

    for attempt in range(1, max_retries + 1):
        try:
            # Try to get active plugin instance
            try:
                import core.plugin_instance as plugin_instance
            except Exception:
                plugin_instance = None

            llm_plugin = None
            if plugin_instance is not None:
                # plugin_instance may export get_plugin() or plugin attribute
                llm_plugin = getattr(plugin_instance, 'get_plugin', lambda: None)()
                if llm_plugin is None:
                    llm_plugin = getattr(plugin_instance, 'plugin', None)

            # Log plugin discovery
            try:
                if llm_plugin is None:
                    log_debug(f"[corrector_middleware] attempt {attempt}: no active LLM plugin found")
                else:
                    log_debug(f"[corrector_middleware] attempt {attempt}: using LLM plugin {getattr(llm_plugin, '__class__', llm_plugin)}")
            except Exception:
                pass

            if not llm_plugin or not hasattr(llm_plugin, 'handle_incoming_message'):
                log_warning(f"[corrector_middleware] No active LLM plugin available (attempt {attempt}/{max_retries})")
                # no plugin available — stop trying and indicate failure (do NOT send to interface)
                log_debug("[corrector_middleware] No LLM available; blocking and returning None")
                return None

            # Build a correction payload similar to action_parser.corrector
            full_json = ""
            try:
                full_json = build_full_json_instructions()
            except Exception:
                full_json = {}

            correction_payload = {
                "system_message": {
                    "type": "error",
                    "message": f"CRITICAL ERROR: Your previous response was not valid JSON. You MUST respond with ONLY valid JSON. {last_error_hint}",
                    "your_reply": text,
                    "full_json_instructions": full_json,
                    "required_format": {
                        "actions": [
                            {
                                "type": "message_telegram_bot",
                                "payload": {
                                    "text": "Your message content here",
                                    "target": "-1003098886330",
                                    "thread_id": 2
                                }
                            }
                        ]
                    },
                    "strict_requirements": [
                        "MUST start with { and end with }",
                        "MUST contain 'actions' array",
                        "NO text outside JSON structure",
                        "NO markdown formatting",
                        "NO explanations outside JSON"
                    ]
                }
            }
            correction_prompt = json.dumps(correction_payload, ensure_ascii=False)

            # Construct a lightweight message object expected by plugins
            correction_message = SimpleNamespace()
            correction_message.chat_id = chat_id or getattr(bot, 'chat_id', None) or -1
            correction_message.text = correction_prompt
            correction_message.thread_id = None
            correction_message.date = None
            correction_message.from_user = None
            correction_message.chat = SimpleNamespace(id=correction_message.chat_id, type='private')

            log_debug(f"[corrector_middleware] Requesting correction from LLM (attempt {attempt}/{max_retries})")

            # Mark that we are expecting a system reply for this chat_id so llm_to_interface can
            # consume it without forwarding and avoid re-entry loops.
            try:
                if correction_message.chat_id is not None:
                    _add_system_reply_expectation(str(correction_message.chat_id))
            except Exception:
                pass

            # Call plugin directly and await returned value when available
            try:
                corrected = await llm_plugin.handle_incoming_message(bot, correction_message, correction_prompt)
            except TypeError:
                # Some plugins expect different signature; try fallback
                corrected = await llm_plugin.handle_incoming_message(bot, correction_message, correction_prompt)

            # Log corrected result type/length
            try:
                log_debug(f"[corrector_middleware] LLM returned type={type(corrected)} len={(len(corrected) if isinstance(corrected, str) else 'N/A')}")
            except Exception:
                pass

            if corrected and isinstance(corrected, str):
                log_debug(f"[corrector_middleware] LLM returned text len={len(corrected)}")
                # If corrected contains valid JSON, return it (do not echo to chat)
                try:
                    if extract_json_from_text(corrected):
                        log_info("[corrector_middleware] Received corrected JSON from LLM")
                        return corrected
                except Exception:
                    pass

                # Not valid JSON yet — DO NOT send LLM suggestion to chat (policy)
                log_debug("[corrector_middleware] LLM suggestion is not valid JSON; will retry without echoing to interface")

                # Update text with LLM reply and retry
                text = corrected

            # small backoff between attempts
            await asyncio.sleep(1)

        except Exception as e:
            try:
                log_warning(f"[corrector_middleware] attempt {attempt} failed: {e}")
            except Exception:
                pass
            await asyncio.sleep(1)

    # Exhausted retries — send error message if possible
    log_warning(f"[corrector_middleware] Exhausted {max_retries} attempts without valid JSON; blocking message for chat_id={chat_id}")
    if llm_plugin and hasattr(llm_plugin, '_send_error_message') and message:
        try:
            await llm_plugin._send_error_message(bot, message)
        except Exception as e:
            log_warning(f"[corrector_middleware] Failed to send error message: {e}")
    # Cleanup expectation for this chat in case it wasn't consumed
    try:
        if chat_id is not None:
            _remove_system_reply_expectation(str(chat_id))
    except Exception:
        pass
    return None


async def interface_to_llm(send_to_llm_func, *args, text: str = None, **kwargs):
    """Entry point for messages going from an interface/plugin TO the LLM.

    This is a thin wrapper that records direction and forwards the call to the
    LLM-facing send function provided by a plugin. It does NOT run the
    corrector.
    """
    try:
        log_debug(f"[chain] interface_to_llm called -> send_to_llm_func={send_to_llm_func} kwargs_keys={list(kwargs.keys())}")
    except Exception:
        pass
    return await send_to_llm_func(*args, text=text, **kwargs)


async def llm_to_interface(interface_send_func, *args, text: str = None, **kwargs):
    """Entry point for messages coming FROM the LLM TO an interface.

    Responsibilities:
    - Ensure a single LLM->interface path for all model outputs (centralized diagnostics)
    - Run the corrector middleware (with retries) only for LLM outputs that are non-empty
    - Forward the (possibly corrected) text into the transport via `universal_send`
    """
    if text is None:
        text = ""

    # Extract chat_id for logging
    chat_id = kwargs.get('chat_id')
    if chat_id is None and args:
        maybe = args[1] if len(args) > 1 else None
        chat_id = maybe if isinstance(maybe, (int, str)) else None

    try:
        log_debug(f"[llm_to_interface] Delivering message to chat_id={chat_id}")
        log_debug(f"[llm_to_interface] Message preview: {text[:100]}..." if len(str(text)) > 100 else f"[llm_to_interface] Message: {text}")
    except Exception:
        pass

    # Clean up expired system reply expectations
    _cleanup_expired_system_replies()

    try:
        log_debug(f"[chain] llm_to_interface called -> interface_send_func={interface_send_func}")
    except Exception:
        pass

    # Mark this forwarding attempt explicitly as an LLM response so downstream
    # components and the orchestrator can detect origin without changes to every
    # LLM engine. Engines that already set this can override it.
    try:
        kwargs.setdefault('is_llm_response', True)
    except Exception:
        pass

    # Suppress empty/whitespace LLM replies early — centralize handling here
    if kwargs.get('is_llm_response', False) and (not text or not text.strip()):
        log_debug("[transport] Empty LLM response received; skipping corrector and not forwarding")
        return None

    # If the LLM sent a JSON-like payload that looks like a correction/system message,
    # handle it via the parser orchestrator to avoid echoing it back into the interfaces
    try:
        json_payload = None
        if text and text.strip():
            try:
                json_payload = extract_json_from_text(text)
            except Exception:
                json_payload = None

        # Detect correction/system payloads (top-level "system_message")
        if isinstance(json_payload, dict) and 'system_message' in json_payload:
            try:
                # Determine bot instance from args if present
                bot = args[0] if args and len(args) > 0 else None

                # Attempt to determine chat_id from kwargs or positional args
                chat_id = kwargs.get('chat_id')
                if chat_id is None and len(args) > 1:
                    maybe = args[1]
                    if isinstance(maybe, (int, str)):
                        chat_id = maybe

                # Build lightweight message and context objects for orchestrator
                from types import SimpleNamespace
                from datetime import datetime

                message = SimpleNamespace()
                message.chat_id = chat_id
                message.text = ""
                message.original_text = text
                message.thread_id = kwargs.get('thread_id')
                # Mark this message as originating from the LLM so the orchestrator
                # will process it. This complements the is_llm_response flag.
                message.from_llm = True
                message.date = datetime.utcnow()

                current_interface = kwargs.get('interface') or (getattr(bot, 'get_interface_id', lambda: 'unknown')() if bot else 'unknown')
                corrector_context = {
                    'interface': current_interface,
                    'original_chat_id': chat_id,
                    'original_thread_id': kwargs.get('thread_id'),
                    'original_text': text[:500] if text else ''
                }

                # Delegate to the parser orchestrator (will call corrector middleware as needed)
                from core import action_parser
                orchestrator_result = await action_parser.corrector_orchestrator(text, corrector_context, bot, message)

                if orchestrator_result is True:
                    log_debug('[llm_to_interface] corrector_orchestrator executed actions; not forwarding text')
                    return None
                elif orchestrator_result is False:
                    log_warning('[llm_to_interface] corrector_orchestrator blocked message; not forwarding')
                    return None
                else:
                    log_debug('[llm_to_interface] corrector_orchestrator returned None; forwarding as usual')

            except Exception as e:
                log_warning(f"[llm_to_interface] Orchestrator handling failed: {e}")
                # On failure, avoid forwarding suspicious payload to interface
                return None

    except Exception:
        # Defensive: any unexpected issue parsing LLM output should not crash forwarding
        pass

    # Forward into the neutral universal send which will parse JSON/actions
    # Delegate to central message chain for unified handling of LLM-origin and interface-origin messages
    try:
        from core.message_chain import handle_incoming_message
        # Determine source: if this path was called from llm_to_interface we set is_llm_response
        source = 'llm' if kwargs.get('is_llm_response', False) else 'interface'
        # Build a message object compatible with message_chain
        from types import SimpleNamespace
        from datetime import datetime
        message = SimpleNamespace()
        # Try to extract chat_id from kwargs/args
        chat_id = kwargs.get('chat_id')
        if chat_id is None and args:
            maybe = args[1] if len(args) > 1 else None
            chat_id = maybe if isinstance(maybe, (int, str)) else None
        message.chat_id = chat_id
        message.text = ""
        message.original_text = text
        message.thread_id = kwargs.get('thread_id')
        message.date = datetime.utcnow()
        # If this chat_id is marked as expecting a system/LLM reply from the
        # corrector middleware, consume it here and do not re-enter the message
        # chain. This avoids infinite correction/forwarding loops.
        # However, only consume if the message actually looks like a correction response.
        try:
            if chat_id is not None and _is_expecting_system_reply(str(chat_id)):
                # Check if this is actually a correction response by looking for typical patterns
                is_correction_response = (
                    isinstance(text, str) and (
                        "system_message" in text or
                        text.strip().startswith('{"actions":') or
                        "correction" in text.lower() or
                        "corrected" in text.lower()
                    )
                )
                
                if is_correction_response:
                    _remove_system_reply_expectation(str(chat_id))
                    log_debug(f"[llm_to_interface] Consuming expected system reply for chat_id={chat_id}; not forwarding to message_chain")
                    return None
                else:
                    # This doesn't look like a correction response, might be a normal message
                    # Log a warning and let it through
                    log_warning(f"[llm_to_interface] Expected system reply for chat_id={chat_id} but message doesn't look like correction. Allowing through.")
                    _remove_system_reply_expectation(str(chat_id))  # Clear the expectation anyway
        except Exception:
            pass
        # Pass through to message chain
        result = await handle_incoming_message(bot=getattr(interface_send_func, '__self__', None) or None, message=message, text=text, source=source, context=kwargs.get('context', None), **kwargs)
        if result == 'ACTIONS_EXECUTED' or result == 'BLOCKED':
            # Orchestrator handled or blocked: nothing to forward
            return None
        # Else forward as usual
        return await universal_send(interface_send_func, *args, text=text, **kwargs)
    except Exception as e:
        log_warning(f"[transport] message_chain delegation failed: {e}")
        return await universal_send(interface_send_func, *args, text=text, **kwargs)
