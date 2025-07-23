# plugins/message_plugin.py
"""Message plugin for handling text message actions."""

import asyncio
from core.logging_utils import log_debug, log_info, log_warning, log_error
from types import SimpleNamespace


class MessagePlugin:
    """Plugin to handle message-type actions."""

    def __init__(self):
        log_debug("[message_plugin] MessagePlugin initialized")

    @property
    def description(self):
        """Return a description of this plugin."""
        return "Handles text message sending across different interfaces (Telegram, Discord, etc.)"

    def get_supported_action_types(self):
        """Return the action types this plugin supports."""
        return ["message"]

    def get_supported_actions(self):
        """Return ultra-compact instructions for supported actions."""
        return {
            "message": "Send text messages: {\"actions\":[{\"type\":\"message\",\"interface\":\"telegram\",\"payload\":{\"text\":\"...\",\"target\":input.payload.source.chat_id,\"thread_id\":input.payload.source.thread_id}}]} - When target equals source chat_id, message appears as reply to original message."
        }

    async def execute_action(self, action: dict, context: dict, bot, original_message):
        """Execute a message action."""
        try:
            payload = action.get("payload", {})
            interface = action.get("interface", "telegram")
            
            await self._handle_message_action(action, context, bot, original_message)
            
        except Exception as e:
            log_error(f"[message_plugin] Error executing message action: {repr(e)}")

    async def handle_custom_action(self, action_type: str, payload: dict):
        """Handle custom message actions."""
        if action_type == "message":
            log_info(f"[message_plugin] Handling message action with payload: {payload}")
            # This method is called by the centralized action system
            # The actual execution is done via execute_action

    async def _handle_message_action(self, action: dict, context: dict, bot, original_message):
        """Handle message action execution."""
        payload = action.get("payload", {})
        text = payload.get("text", "")
        target = payload.get("target")
        thread_id = payload.get("thread_id")
        interface = action.get("interface", "telegram")
        
        log_debug(f"[message_plugin] Handling message action: {text[:50]}...")
        log_debug(f"[message_plugin] Target: {target}, Thread: {thread_id}, Interface: {interface}")

        # Validate required fields
        if not text:
            log_warning("[message_plugin] Invalid message action: missing text")
            return

        # If target is missing or invalid, use the original message's chat_id as fallback
        if not target:
            target = getattr(original_message, "chat_id", None)
            log_debug(f"[message_plugin] No target specified, using original chat_id: {target}")

        # If thread_id is missing but original message has one, use it as fallback
        if not thread_id and hasattr(original_message, "chat_id"):
            original_thread_id = getattr(original_message, "message_thread_id", None)
            if original_thread_id:
                thread_id = original_thread_id
                log_debug(f"[message_plugin] No thread_id specified, using original thread_id: {thread_id}")

        # Additional validation for target
        if not target:
            log_warning("[message_plugin] No valid target found, cannot send message")
            return

        # Route to appropriate interface
        if interface == "telegram":
            await self._send_telegram_message(bot, target, text, thread_id, original_message)
        else:
            log_warning(f"[message_plugin] Unsupported interface: {interface}")

    async def _send_telegram_message(self, bot, target, text, thread_id, original_message):
        """Send message via Telegram interface."""
        try:
            log_debug(f"[message_plugin] Sending message to {target} (thread_id: {thread_id}) with text: {text[:50]}...")

            # Prepare kwargs for send_message
            send_kwargs = {"chat_id": target, "text": text}
            if thread_id:
                send_kwargs["message_thread_id"] = thread_id

            # Add reply_to_message_id if sending to the same chat as the original message
            if (hasattr(original_message, "chat_id") and 
                hasattr(original_message, "message_id") and 
                target == original_message.chat_id):
                send_kwargs["reply_to_message_id"] = original_message.message_id
                log_debug(f"[message_plugin] Adding reply_to_message_id: {original_message.message_id}")

            await bot.send_message(**send_kwargs)
            log_info(f"[message_plugin] Message successfully sent to {target} (thread: {thread_id}, reply_to: {send_kwargs.get('reply_to_message_id', 'None')})")
            
        except Exception as e:
            error_message = str(e)
            
            # Check if the error is specifically about thread not found
            if thread_id and ("Message thread not found" in error_message or "thread not found" in error_message.lower()):
                log_warning(f"[message_plugin] Thread {thread_id} not found in chat {target}, retrying without thread_id")
                try:
                    # Retry without thread_id but keep reply_to_message_id if applicable
                    fallback_kwargs = {"chat_id": target, "text": text}
                    if (hasattr(original_message, "chat_id") and 
                        hasattr(original_message, "message_id") and 
                        target == original_message.chat_id):
                        fallback_kwargs["reply_to_message_id"] = original_message.message_id
                    
                    await bot.send_message(**fallback_kwargs)
                    log_info(f"[message_plugin] Message successfully sent to {target} (fallback: no thread, reply_to: {fallback_kwargs.get('reply_to_message_id', 'None')})")
                    return  # Success, exit the function
                except Exception as no_thread_error:
                    log_error(f"[message_plugin] Fallback without thread also failed for {target}: {no_thread_error}")
                    # Continue to original fallback logic below
            else:
                log_error(f"[message_plugin] Failed to send message to {target} (thread: {thread_id}): {repr(e)}")
            
            # Try fallback to original chat if target was different
            if hasattr(original_message, "chat_id") and target != original_message.chat_id:
                try:
                    fallback_thread_id = getattr(original_message, "message_thread_id", None)
                    fallback_kwargs = {"chat_id": original_message.chat_id, "text": text}
                    if fallback_thread_id:
                        fallback_kwargs["message_thread_id"] = fallback_thread_id
                    # Always add reply_to_message_id when falling back to original chat
                    if hasattr(original_message, "message_id"):
                        fallback_kwargs["reply_to_message_id"] = original_message.message_id

                    log_debug(f"[message_plugin] Retrying with original chat_id: {original_message.chat_id} (thread: {fallback_thread_id}, reply_to: {fallback_kwargs.get('reply_to_message_id', 'None')})")
                    await bot.send_message(**fallback_kwargs)
                    log_info(f"[message_plugin] Message successfully sent to fallback chat: {original_message.chat_id} (thread: {fallback_thread_id}, reply_to: {fallback_kwargs.get('reply_to_message_id', 'None')})")
                    
                except Exception as fallback_error:
                    log_error(f"[message_plugin] Fallback also failed: {fallback_error}")


# Export the plugin class
__all__ = ["MessagePlugin"]

# Define the plugin class for automatic loading
PLUGIN_CLASS = MessagePlugin
