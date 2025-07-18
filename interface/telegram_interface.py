from telethon import TelegramClient
from core.logging_utils import log_debug, log_error

class TelegramInterface:
    def __init__(self, api_id, api_hash, bot_token):
        self.client = TelegramClient('bot', api_id, api_hash).start(bot_token=bot_token)

    async def send_message(self, chat_id, text):
        """Send a message to a specific chat."""
        try:
            await self.client.send_message(chat_id, text)
            log_debug(f"[telegram_interface] Message sent to {chat_id}: {text}")
        except Exception as e:
            log_error(f"[telegram_interface] Failed to send message to {chat_id}: {e}")

    @staticmethod
    def get_interface_instructions():
        """Return specific instructions for Telegram interface."""
        return "Use chat_id for targets and plain text for messages."
