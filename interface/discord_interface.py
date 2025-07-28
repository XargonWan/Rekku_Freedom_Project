# interface/discord_interface.py (esempio)
"""Example Discord interface using the universal transport layer."""

from core.logging_utils import log_debug, log_error
from core.transport_layer import universal_send


class DiscordInterface:
    def __init__(self, bot_token):
        # Initialize Discord client
        pass

    @staticmethod
    def get_supported_action_types() -> list[str]:
        """Return action types supported by this interface."""
        return ["message"]

    @staticmethod
    def get_supported_actions() -> dict:
        """Return a compact description of supported actions."""
        return {
            "message": "Send messages using 'channel_id'. Interface: discord_bot"
        }

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
        return "Use channel_id for targets and plain text for messages."
