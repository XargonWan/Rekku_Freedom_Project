from telethon import TelegramClient
from core.logging_utils import log_debug, log_error

class TelegramInterface:
    def __init__(self, api_id, api_hash, bot_token):
        self.client = TelegramClient('bot', api_id, api_hash).start(bot_token=bot_token)

    async def send_message(self, chat_id, text):
        """Send a message to a specific chat."""
        from core.transport_layer import universal_send
        try:
            await universal_send(self.client.send_message, chat_id, text=text)
            log_debug(f"[telegram_interface] Message sent to {chat_id}: {text}")
        except Exception as e:
            log_error(f"[telegram_interface] Failed to send message to {chat_id}: {e}")

    @staticmethod
    def get_interface_instructions():
        """Return specific instructions for Telegram interface."""
        return """TELEGRAM INTERFACE INSTRUCTIONS:
- Use chat_id for targets (can be negative for groups/channels)
- For groups with topics, include thread_id to reply in the correct topic
- Keep messages under 4096 characters
- Use markdown formatting if needed: *bold*, _italic_, `code`
- For groups, always reply in the same chat and thread unless specifically instructed otherwise
- Target should be the exact chat_id from input.payload.source.chat_id
- Thread_id should be the exact thread_id from input.payload.source.thread_id (if present)
- Interface should always be "telegram"
"""
