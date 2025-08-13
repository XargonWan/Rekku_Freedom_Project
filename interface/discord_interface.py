# interface/discord_interface.py (esempio)
"""Example Discord interface using the universal transport layer."""

from core.logging_utils import log_debug, log_error
from core.transport_layer import universal_send


class DiscordInterface:
    def __init__(self, bot_token):
        # Initialize Discord client
        pass

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

    @staticmethod
    def get_interface_instructions():
        """Return specific instructions for Discord interface."""
        return (
            "DISCORD INTERFACE INSTRUCTIONS:\n"
            "- Use channel_id for targets.\n"
            "- Markdown is supported, but avoid advanced features not supported by Discord.\n"
            "- Messages sent to the same channel as the source will appear as replies when possible.\n"
            "- Provide plain text or Markdown in the 'text' field."
        )
