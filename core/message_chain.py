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
from types import SimpleNamespace
from typing import Any, Dict, Optional

from core.logging_utils import log_debug, log_info, log_warning

# Result constants
ACTIONS_EXECUTED = "ACTIONS_EXECUTED"
BLOCKED = "BLOCKED"
FORWARD_AS_TEXT = "FORWARD_AS_TEXT"


async def handle_incoming_message(bot, message: Optional[SimpleNamespace], text: str, *, source: str = "interface", context: Optional[Dict[str, Any]] = None, **kwargs):
    """Main entry point for the message chain.

    Parameters
    - bot: interface bot instance
    - message: SimpleNamespace-like message object (may be None)
    - text: incoming text to process
    - source: 'interface'|'user'|'llm' - origin of the text
    - context: optional context dict to pass to action parser
    - kwargs: additional metadata (e.g., message_thread_id)

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
        message.message_thread_id = kwargs.get('message_thread_id')
        message.date = datetime.utcnow()

    # Mark LLM-origin if source indicates so
    message.from_llm = True if source == 'llm' else getattr(message, 'from_llm', False)

    # Default context
    ctx = context or {}
    ctx['message'] = message

    # Retry/tried set to avoid loops
    tried_texts = set()
    attempt = 0
    max_retries = ctx.get('max_retries', CORRECTOR_RETRIES)

    while True:
        log_debug(
            f"[message_chain] iteration attempt={attempt} source={source} chat={getattr(message,'chat_id',None)}"
        )

        # Quick JSON extraction
        parsed = None
        try:
            parsed = extract_json_from_text(text)
        except Exception as e:
            log_debug(f"[message_chain] extract_json failed: {e}")

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
            log_warning(f"[message_chain] Exhausted {max_retries} correction attempts; blocking chat {getattr(message,'chat_id',None)}")
            return BLOCKED

        if text in tried_texts:
            log_warning('[message_chain] Saw same text previously; aborting to avoid loop')
            return BLOCKED

        tried_texts.add(text)

        # Request correction from LLM via transport-layer middleware
        try:
            corrected = await run_corrector_middleware(text, bot=bot, context=ctx, chat_id=getattr(message, 'chat_id', None))
        except Exception as e:
            log_warning(f"[message_chain] Corrector middleware failed: {e}")
            return BLOCKED

        if not corrected:
            log_debug('[message_chain] Corrector returned no correction this attempt')
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
