# plugins/message_plugin.py
"""Message plugin for handling text message actions."""

import asyncio
from core.logging_utils import log_debug, log_info, log_warning, log_error


class MessagePlugin:
    """Plugin to handle message-type actions across multiple interfaces."""

    def __init__(self):
        """Initialize the plugin."""
        self.supported_interfaces = ["telegram"]
        log_debug("[message_plugin] MessagePlugin initialized")

    @property
    def description(self):
        """Return a description of this plugin."""
        return "Handles text message sending across different interfaces (Telegram, Discord, etc.)"

    def get_supported_action_types(self):
        """Return the action types this plugin supports."""
        return ["message"]

    def get_supported_actions(self):
        """Return structured instructions for supported actions."""
        return {
            "message": {
                "description": "Send a text message using a supported chat interface",
                "interfaces": self.supported_interfaces,
                "example": {
                    "type": "message",
                    "interface": self.supported_interfaces[0],
                    "payload": {
                        "text": "Hello!",
                        "target": "123456789",
                        "thread_id": 42,
                    },
                },
            }
        }

    async def execute_action(self, action: dict, context: dict, bot, original_message):
        """Execute a message action."""
        try:
            await self._handle_message_action(action, context, bot, original_message)
            
        except Exception as e:
            log_error(f"[message_plugin] Error executing message action: {repr(e)}")

    async def handle_custom_action(self, action_type: str, payload: dict):
        """Handle custom message actions."""
        if action_type == "message":
            log_info("[message_plugin] Handling message action with payload: " + str(payload))
            # This method is called by the centralized action system
            # The actual execution is done via execute_action

    async def _handle_message_action(self, action: dict, context: dict, bot, original_message):
        """Handle message action execution using the interface registry."""
        from core.interfaces import get_interface_by_name

        payload = action.get("payload", {})
        interface_name = action.get("interface", self.supported_interfaces[0])

        log_debug(f"[message_plugin] Dispatching message via interface: {interface_name}")

        interface = get_interface_by_name(interface_name)
        if not interface:
            log_warning(f"[message_plugin] Unsupported interface: {interface_name}")
            return

        await interface.send_message(payload, original_message)



# Export the plugin class
__all__ = ["MessagePlugin"]

# Define the plugin class for automatic loading
PLUGIN_CLASS = MessagePlugin
