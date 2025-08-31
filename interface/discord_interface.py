# interface/discord_interface.py (esempio)
"""Example Discord interface using the universal transport layer."""

import os

from core.logging_utils import log_debug, log_error, log_info
from core.transport_layer import universal_send
from core.core_initializer import register_interface
from core.command_registry import execute_command


class DiscordInterface:
    def __init__(self, bot_token):
        # Initialize Discord client
        register_interface("discord_bot", self)
        log_info("[discord_interface] Registered DiscordInterface")

    @staticmethod
    def get_interface_id() -> str:
        """Return the unique identifier for this interface."""
        return "discord_bot"

    @staticmethod
    def get_action_types() -> list[str]:
        """Return action types supported by this interface."""
        return ["message_discord_bot"]

    @staticmethod
    def get_supported_actions() -> dict:
        """Return schema information for supported actions."""
        return {
            "message_discord_bot": {
                "description": "Send a text message to a Discord channel.",
                "required_fields": ["text", "target"],
                "optional_fields": [],
            }
        }

    @staticmethod
    def get_prompt_instructions(action_name: str) -> dict:
        if action_name == "message_discord_bot":
            return {
                "description": "Send a message to a Discord channel.",
                "payload": {
                    "text": {"type": "string", "example": "Hello Discord!", "description": "The message text to send."},
                    "target": {"type": "string", "example": "1234567890", "description": "The channel_id of the recipient."},
                    "reply_to_message_id": {"type": "integer", "example": 987654321, "description": "Optional ID of the message to reply to", "optional": True},
                },
            }
        return {}

    @staticmethod
    def validate_payload(action_type: str, payload: dict) -> list:
        """Validate payload for discord actions."""
        errors: list[str] = []

        if action_type != "message_discord_bot":
            return errors

        text = payload.get("text")
        if not isinstance(text, str) or not text:
            errors.append("payload.text must be a non-empty string")

        target = payload.get("target")
        if target is None:
            errors.append("payload.target is required")
        elif not isinstance(target, (int, str)):
            errors.append("payload.target must be an int or string")

        reply_to = payload.get("reply_to_message_id")
        if reply_to is not None and not isinstance(reply_to, int):
            errors.append("payload.reply_to_message_id must be an int")

        return errors

    async def send_message(self, channel_id, text):
        """Send a message to a Discord channel."""
        try:
            # Use universal_send to automatically handle JSON actions
            await universal_send(self._discord_send, channel_id, text=text)
            log_debug(f"[discord_interface] Message sent to {channel_id}: {text}")
        except Exception as e:
            log_error(f"[discord_interface] Failed to send message to {channel_id}: {repr(e)}")

    async def _discord_send(self, channel_id, text):
        """Internal Discord send method."""
        # Actual Discord API call would go here
        # await self.client.get_channel(channel_id).send(text)
        pass

    async def handle_command(self, command_name: str, *args, **kwargs):
        """Process a slash command via the shared backend."""
        return await execute_command(command_name, *args, **kwargs)

    @staticmethod
    def get_interface_instructions():
        """Return specific instructions for Discord interface."""
        return (
            "DISCORD INTERFACE INSTRUCTIONS:\n"
            "- Use channel_id for targets.\n"
            "- Markdown is supported, but avoid advanced features not supported by Discord.\n"
            "- Messages sent to the same channel as the source will appear as replies when possible.\n"
            "- Use 'reply_message_id' to reply to specific messages.\n"
            "- Provide plain text or Markdown in the 'text' field.\n"
            "- Supports 'ping' and predefined codewords like the Telegram bot."
        )

# Expose class for dynamic loading
INTERFACE_CLASS = DiscordInterface
