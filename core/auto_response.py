# core/auto_response.py
"""
System for automatic LLM-mediated responses from interface actions.
Used when interfaces need to report results back through the LLM instead of directly.
"""

import asyncio
import json
from core.logging_utils import log_debug, log_info, log_warning, log_error
from typing import Dict, Any, Optional, List
from datetime import datetime
from core.prompt_engine import build_full_json_instructions


class AutoResponseSystem:
    """Manages automatic responses through LLM for interface actions."""
    
    def __init__(self):
        self._pending_responses = {}
    
    async def request_llm_response(
        self,
        output: Optional[str] = None,
        original_context: Optional[Dict[str, Any]] = None,
        action_type: str = "unknown",
        command: str = None,
        action_outputs: Optional[List[Dict[str, Any]]] = None,
    ):
        """
        Request LLM to process and deliver outputs back to the user.

        Args:
            output: The result from a single action (legacy path)
            original_context: Context from the original request (chat_id, etc.)
            action_type: The type of action that generated this output
            command: The original command if applicable
            action_outputs: List of outputs from multiple actions
        """
        try:
            # Import here to avoid circular imports
            from core.message_queue import enqueue
            
            # Build context for LLM
            chat_id = original_context.get('chat_id')
            message_id = original_context.get('message_id')
            interface_name = original_context.get('interface_name', 'telegram_bot')
            
            # Create a mock message object for the LLM request
            from types import SimpleNamespace
            mock_message = SimpleNamespace()
            # Basic identifiers
            mock_message.chat_id = chat_id
            mock_message.message_id = message_id or 0
            if action_outputs is not None:
                mock_message.text = json.dumps(
                    {"action_outputs": action_outputs}, ensure_ascii=False
                )
            else:
                mock_message.text = (
                    f"Auto-response for {action_type}: {command}"
                    if command
                    else f"Auto-response for {action_type}"
                )
            # Populate minimal from_user info
            mock_message.from_user = SimpleNamespace()
            mock_message.from_user.id = chat_id
            mock_message.from_user.username = "auto_response"
            mock_message.from_user.first_name = "AutoResponse"
            mock_message.from_user.full_name = "AutoResponse"

            # Message metadata expected by downstream handlers
            mock_message.date = datetime.utcnow()
            mock_message.reply_to_message = None
            mock_message.message_thread_id = original_context.get(
                "message_thread_id"
            )

            # Provide chat structure expected by message_queue.enqueue
            mock_message.chat = SimpleNamespace()
            mock_message.chat.id = chat_id
            mock_message.chat.title = None
            mock_message.chat.username = None
            mock_message.chat.first_name = "AutoResponse"
            mock_message.chat.type = "private"
            
            full_json = build_full_json_instructions()
            if action_outputs is not None:
                message_block = {"action_outputs": action_outputs}
            else:
                message_block = output
            system_payload = {
                "system_message": {
                    "type": "output",
                    "message": message_block,
                    "full_json_instructions": full_json,
                }
            }

            log_info(
                f"[auto_response] Requesting LLM to deliver {action_type} output to chat {chat_id}"
            )
            
            # Get interface instance dynamically without hardcoding
            from core.core_initializer import INTERFACE_REGISTRY

            interface = INTERFACE_REGISTRY.get(interface_name)
            if not interface:
                log_error(
                    f"[auto_response] No interface '{interface_name}' available"
                )
                return

            bot = getattr(interface, "bot", None)
            if bot is None:
                log_error(
                    f"[auto_response] Interface '{interface_name}' has no bot instance"
                )
                return

            # Enqueue the LLM request
            import json

            await enqueue(
                bot,
                mock_message,
                json.dumps(system_payload, ensure_ascii=False),
                priority=True,
            )
            
        except Exception as e:
            log_error(f"[auto_response] Failed to request LLM response: {e}")
            import traceback
            traceback.print_exc()


# Global instance
_auto_response_system = AutoResponseSystem()


async def request_llm_delivery(
    message=None,
    interface=None,
    context=None,
    reason=None,
    output=None,
    original_context=None,
    action_type=None,
    command=None,
    action_outputs=None,
):
    """
    Unified convenience function to request LLM-mediated delivery.
    
    Supports multiple calling patterns:
    1. Legacy: request_llm_delivery(output, original_context, action_type, command)
    2. New: request_llm_delivery(message, interface, context, reason)
    """
    # Handle legacy calling pattern (terminal plugin style)
    if (action_outputs is not None) and original_context is not None:
        await _auto_response_system.request_llm_response(
            original_context=original_context,
            action_type=action_type or "unknown",
            action_outputs=action_outputs,
        )
        return

    if output is not None and original_context is not None:
        await _auto_response_system.request_llm_response(
            output,
            original_context,
            action_type or "unknown",
            command,
        )
        return
    
    # Handle new calling pattern (interface style)
    if message is not None or interface is not None:
        try:
            import core.plugin_instance as plugin_instance

            log_info(f"[auto_response] Processing {reason or 'autonomous'} request")

            # If we have a message, use it directly with plugin_instance
            import json

            full_json = build_full_json_instructions()
            # Reminders are flagged separately so the scheduler doesn't re-queue them
            if isinstance(context, dict) and context.get("input", {}).get("type") in {"event", "event_reminder"}:
                log_debug("[auto_response] Routing event reminder to LLM")
                system_payload = {
                    "system_message": {
                        "type": "event_reminder",
                        "message": context,
                        "full_json_instructions": full_json,
                    }
                }
            else:
                system_payload = {
                    "system_message": {
                        "type": "output",
                        "message": context,
                        "full_json_instructions": full_json,
                    }
                }

            payload_json = json.dumps(system_payload, ensure_ascii=False)

            if message is not None:
                await plugin_instance.handle_incoming_message(interface, message, payload_json)
            else:
                # For interface-only requests, create synthetic message
                from types import SimpleNamespace

                mock_message = SimpleNamespace()
                mock_message.chat_id = -1  # Default chat
                mock_message.message_id = 0
                mock_message.text = f"Auto-generated message for {reason}"
                mock_message.from_user = SimpleNamespace(
                    id=0, username="auto_response", full_name="AutoResponder"
                )
                mock_message.chat = SimpleNamespace(id=-1, type="private")

                await plugin_instance.handle_incoming_message(
                    interface, mock_message, payload_json
                )
                
        except Exception as e:
            log_error(f"[auto_response] Failed to process {reason}: {e}")
            import traceback
            traceback.print_exc()
        return
    
    log_warning("[auto_response] request_llm_delivery called with insufficient parameters")
