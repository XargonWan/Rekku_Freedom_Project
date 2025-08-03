# core/auto_response.py
"""
System for automatic LLM-mediated responses from interface actions.
Used when interfaces need to report results back through the LLM instead of directly.
"""

import asyncio
from core.logging_utils import log_debug, log_info, log_warning, log_error
from typing import Dict, Any, Optional


class AutoResponseSystem:
    """Manages automatic responses through LLM for interface actions."""
    
    def __init__(self):
        self._pending_responses = {}
    
    async def request_llm_response(
        self, 
        output: str, 
        original_context: Dict[str, Any],
        action_type: str,
        command: str = None
    ):
        """
        Request LLM to process and deliver output back to the user.
        
        Args:
            output: The result from the action (e.g., terminal output)
            original_context: Context from the original request (chat_id, etc.)
            action_type: The type of action that generated this output
            command: The original command if applicable
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
            mock_message.chat_id = chat_id
            mock_message.message_id = message_id or 0
            mock_message.text = f"Auto-response for {action_type}: {command}" if command else f"Auto-response for {action_type}"
            mock_message.from_user = SimpleNamespace()
            mock_message.from_user.id = chat_id
            mock_message.from_user.username = "auto_response"
            mock_message.from_user.first_name = "AutoResponse"
            
            # Create context memory with the output and instructions
            context_memory = {
                "system_instruction": f"You executed a {action_type} command and got output. Please format and deliver this output to the user.",
                "command_executed": command,
                "command_output": output,
                "delivery_instructions": f"Send the output back to chat {chat_id} using message_{interface_name} action. Format it nicely.",
                "suggested_response": f"Here's the output from your {action_type} command:\n\n```\n{output}\n```"
            }
            
            log_info(f"[auto_response] Requesting LLM to deliver {action_type} output to chat {chat_id}")
            
            # Get bot instance from interfaces
            from core.interfaces import INTERFACE_REGISTRY
            bot = INTERFACE_REGISTRY.get('telegram_bot')
            if not bot:
                log_error("[auto_response] No telegram_bot interface available")
                return
            
            # Enqueue the LLM request
            await enqueue(bot, mock_message, context_memory, priority=True)
            
        except Exception as e:
            log_error(f"[auto_response] Failed to request LLM response: {e}")
            import traceback
            traceback.print_exc()


# Global instance
_auto_response_system = AutoResponseSystem()


async def request_llm_delivery(
    output: str,
    original_context: Dict[str, Any], 
    action_type: str,
    command: str = None
):
    """
    Convenience function to request LLM-mediated delivery of action output.
    
    Args:
        output: The result to deliver
        original_context: Original request context (chat_id, message_id, etc.)
        action_type: Type of action that generated the output
        command: Original command if applicable
    """
    await _auto_response_system.request_llm_response(
        output, original_context, action_type, command
    )
