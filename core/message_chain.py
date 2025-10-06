# core/message_chain.py
"""Central message chain manager.

This module implements the message loop described by the user:

User -> Interface
Interface -> Message chain

Message chain receives messages (from interfaces or from LLM), tries to extract JSON
and send it to the action parser. If actions are executed the loop ends. If JSON-like
but invalid the message chain will call the corrector middleware (which queries the
active LLM plugin) until corrected JSON is returned or retries are exhausted.

The corrector never sends messages directly to interfaces; it only queries the LLM
via the registered plugin. The message chain marks LLM-origin messages so the
parser will only operate on model outputs.

Return codes:
- ACTIONS_EXECUTED -> actions parsed and executed
- BLOCKED -> message blocked (exhausted retries or explicit ignore)
- FORWARD_AS_TEXT -> not JSON-like; caller may forward plain text to interface
"""

import asyncio
import os
from types import SimpleNamespace
from typing import Any, Dict, Optional

from core.logging_utils import log_debug, log_info, log_warning, log_error

# Result constants
# Result constants
ACTIONS_EXECUTED = 'ACTIONS_EXECUTED'
FORWARD_AS_TEXT = 'FORWARD_AS_TEXT'
BLOCKED = 'BLOCKED'
LLM_FAILED = 'LLM_FAILED'

def get_failed_message_text() -> str:
    """Get the fallback message when LLM fails."""
    return os.getenv('FAILED_MESSAGE_TEXT', 'LLM failed')

async def send_llm_fallback_message(bot, message: SimpleNamespace, failure_reason: str) -> str:
    """Send fallback message when LLM fails and log the failure reason."""
    fallback_text = get_failed_message_text()
    chat_id = getattr(message, 'chat_id', None)
    
    # Log detailed error
    log_error(f"[message_chain] LLM FAILURE - Chat: {chat_id}, Reason: {failure_reason}")
    log_error(f"[message_chain] Sending fallback message: '{fallback_text}'")
    
    # Send fallback message through transport layer
    try:
        from core.transport_layer import universal_send
        await universal_send(
            bot=bot,
            target=chat_id,
            text=fallback_text,
            thread_id=getattr(message, 'thread_id', None),
            is_llm_response=True  # Mark as LLM response so interface handles normally
        )
        log_debug(f"[message_chain] Fallback message sent to chat {chat_id}")
        return fallback_text
    except Exception as e:
        log_error(f"[message_chain] Failed to send fallback message: {e}")
        return fallback_text


async def handle_incoming_message(bot, message: Optional[SimpleNamespace], text: str, *, source: str = "interface", context: Optional[Dict[str, Any]] = None, **kwargs):
    """Main entry point for the message chain.

    Parameters
    - bot: interface bot instance
    - message: SimpleNamespace-like message object (may be None)
    - text: incoming text to process
    - source: 'interface'|'user'|'llm' - origin of the text
    - context: optional context dict to pass to action parser
    - kwargs: additional metadata (e.g., thread_id)

    Returns one of the constants above.
    """
    # Local imports to avoid circular dependencies
    from core.transport_layer import extract_json_from_text, run_corrector_middleware
    from core.action_parser import run_actions, CORRECTOR_RETRIES
    from types import SimpleNamespace
    from datetime import datetime

    if message is None:
        message = SimpleNamespace()
        message.chat_id = kwargs.get('chat_id')
        message.text = ""
        message.original_text = text
        message.thread_id = kwargs.get('thread_id')
        message.date = datetime.utcnow()

    # Mark LLM-origin if source indicates so
    message.from_llm = True if source == 'llm' else getattr(message, 'from_llm', False)

    # Process LLM messages for emotional state updates
    if getattr(message, 'from_llm', False) or source == 'llm':
        try:
            from core.persona_manager import get_persona_manager
            persona_manager = get_persona_manager()
            if persona_manager:
                persona_manager.process_llm_message_for_emotions(text)
        except Exception as e:
            log_debug(f"[message_chain] Error processing LLM emotions: {e}")

    # Default context
    ctx = context or {}
    ctx['message'] = message
    
    # Preserve chat_id in context to avoid losing it during correction
    if hasattr(message, 'chat_id'):
        ctx['chat_id'] = message.chat_id

    # Retry/tried set to avoid loops
    tried_texts = set()
    attempt = 0
    max_retries = ctx.get('max_retries', CORRECTOR_RETRIES)

    while True:
        log_debug(
            f"[message_chain] iteration attempt={attempt} source={source} chat={getattr(message,'chat_id',None)}"
        )

        # Quick JSON extraction with metadata to detect corruption
        parsed = None
        metadata = {}
        try:
            parsed, metadata = extract_json_from_text(text, return_metadata=True)
        except Exception as e:
            log_debug(f"[message_chain] extract_json failed: {e}")

        # Check if JSON was recovered from corruption - needs correction
        if parsed is not None and metadata.get('recovered'):
            log_warning(
                f"[message_chain] JSON recovered from corruption (errors: {metadata.get('error_count', 0)}, "
                f"unparsed: {len(metadata.get('unparsed_content', ''))} chars) - triggering corrector"
            )
            parsed = None  # Force correction path

        if parsed is not None:
            # System messages are produced by the core/system and should NEVER be processed
            # This prevents loops caused by system messages being re-evaluated
            if isinstance(parsed, dict) and 'system_message' in parsed:
                sm = parsed.get('system_message') or {}
                sm_type = sm.get('type') if isinstance(sm, dict) else None
                log_info(
                    f"[message_chain] Blocking system_message type={sm_type} (system-origin payload) - system messages must not enter the processing loop"
                )
                return BLOCKED

            # Build actions list
            if isinstance(parsed, dict) and 'actions' in parsed:
                actions = parsed['actions'] if isinstance(parsed['actions'], list) else None
                if actions is None:
                    log_warning('[message_chain] actions field must be a list')
                    return FORWARD_AS_TEXT
            elif isinstance(parsed, list):
                actions = parsed
            elif isinstance(parsed, dict) and 'type' in parsed:
                actions = [parsed]
            else:
                log_warning(f"[message_chain] Unrecognized JSON structure: {parsed}")
                return FORWARD_AS_TEXT

            # Execute actions via action_parser
            try:
                await run_actions(actions, ctx, bot, message)
                log_info('[message_chain] Actions executed successfully - loop interrupted')
                return ACTIONS_EXECUTED
            except Exception as e:
                log_warning(f"[message_chain] Failed to run actions: {e}")
                # If action execution fails, don't continue with correction loop
                # This prevents cascading failures and loops
                return BLOCKED

        # Not parsed. If not JSON-like, forward as plain text
        if '{' not in (text or '') and '[' not in (text or ''):
            log_debug('[message_chain] Not JSON-like -> forward as plain text')
            return FORWARD_AS_TEXT

        # JSON-like but invalid -> attempt correction
        # IMPORTANT: Only attempt correction for LLM messages that failed JSON parsing
        # Non-LLM messages and messages that don't require correction should be forwarded as text
        if source != "llm" and not getattr(message, "from_llm", False):
            log_debug("[message_chain] Non-LLM source; messages that don't require correction should not be corrected")
            return FORWARD_AS_TEXT

        # Additional check: if this is already a system error message from corrector, don't re-correct
        if "system_message" in (text or '') and "error" in (text or ''):
            log_debug("[message_chain] Detected system error message from corrector; preventing re-correction loop")
            return BLOCKED

        attempt += 1
        if attempt > max_retries:
            failure_reason = f"Exhausted {max_retries} correction attempts for invalid JSON"
            log_warning(f"[message_chain] {failure_reason}; sending fallback message")
            await send_llm_fallback_message(bot, message, failure_reason)
            return LLM_FAILED

        if text in tried_texts:
            failure_reason = "Correction loop detected - same text repeated"
            log_warning(f'[message_chain] {failure_reason}; sending fallback message')
            await send_llm_fallback_message(bot, message, failure_reason)
            return LLM_FAILED

        tried_texts.add(text)

        # Request correction from LLM via transport-layer middleware
        try:
            corrected = await run_corrector_middleware(text, bot=bot, context=ctx, chat_id=getattr(message, 'chat_id', None))
        except Exception as e:
            failure_reason = f"Corrector middleware exception: {str(e)}"
            log_warning(f"[message_chain] {failure_reason}")
            await send_llm_fallback_message(bot, message, failure_reason)
            return LLM_FAILED

        if not corrected:
            log_debug('[message_chain] Corrector returned no correction this attempt')
            # Check if we're approaching max retries to avoid infinite waiting
            if attempt >= max_retries - 1:
                failure_reason = f"Corrector returned no correction after {attempt} attempts"
                log_warning(f"[message_chain] {failure_reason}; sending fallback message")
                await send_llm_fallback_message(bot, message, failure_reason)
                return LLM_FAILED
            # On no-correction, loop and let retry counter enforce blocking
            await asyncio.sleep(0.5)
            continue

        # Accept corrected text and treat it as LLM-origin for next iteration
        log_debug('[message_chain] Received corrected text from LLM; retrying parse')
        text = corrected
        source = 'llm'
        message.original_text = text
        message.from_llm = True
        # loop continues


# Backwards-compatible alias
handle_message = handle_incoming_message
