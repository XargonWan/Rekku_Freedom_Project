# llm_engines/manual.py

from core import say_proxy, message_map
from core.telegram_utils import truncate_message
from core.config import OWNER_ID
from core.ai_plugin_base import AIPluginBase
import json
from telegram.constants import ParseMode
from core.logging_utils import log_debug, log_info, log_warning, log_error

class ManualAIPlugin(AIPluginBase):

    def __init__(self, notify_fn=None):
        from core.notifier import set_notifier

        # Initialize the persistent mapping table
        message_map.init_table()

        if notify_fn:
            log_debug("[manual] Using custom notification function.")
            set_notifier(notify_fn)
        else:
            log_debug("[manual] No notification function provided, using fallback.")
            set_notifier(lambda chat_id, message: log_info(f"[NOTIFY fallback] {message}"))

    def track_message(self, trainer_message_id, original_chat_id, original_message_id):
        """Persist the mapping for a forwarded message."""
        message_map.add_mapping(trainer_message_id, original_chat_id, original_message_id)

    def get_target(self, trainer_message_id):
        return message_map.get_mapping(trainer_message_id)

    def clear(self, trainer_message_id):
        message_map.delete_mapping(trainer_message_id)

    def get_rate_limit(self):
        return (80, 10800, 0.5)

    async def handle_incoming_message(self, bot, message, prompt):
        """Compatibility wrapper for legacy usage."""
        return await self.generate_response(prompt)

    async def generate_response(self, prompt: dict) -> str:
        """Return a placeholder JSON action waiting for manual input."""
        response = {
            "type": "message",
            "interface": "telegram",
            "payload": {
                "text": "\U0001f570\ufe0f Waiting for manual input.",
                "target": prompt.get("input", {}).get("payload", {}).get("source", {}).get("chat_id"),
                "thread_id": prompt.get("input", {}).get("payload", {}).get("source", {}).get("thread_id"),
            },
        }
        return json.dumps(response, ensure_ascii=False)


PLUGIN_CLASS = ManualAIPlugin
