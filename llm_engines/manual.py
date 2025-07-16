# llm_engines/manual.py

from core import say_proxy, message_map
from core.telegram_utils import truncate_message, send_json_preview
from core.config import OWNER_ID
from core.ai_plugin_base import AIPluginBase
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
        from core.notifier import notify_owner

        notify_owner("🚨 Generating the reply...")

        user_id = message.from_user.id
        text = message.text or ""
        log_debug(f"[manual] Message received in manual mode from chat_id={message.chat_id}")

        # === Caso speciale: /say attivo ===
        target_chat = say_proxy.get_target(user_id)
        if target_chat and target_chat != "EXPIRED":
            log_debug(f"[manual] Invio da /say: chat_id={target_chat}")
            await bot.send_message(chat_id=target_chat, text=truncate_message(text))
            say_proxy.clear(user_id)
            return

        # === Invia prompt JSON al trainer (OWNER_ID) se il mittente non è l'owner ===
        if message.from_user.id != OWNER_ID:
            await send_json_preview(bot, prompt)

        # === Inoltra il messaggio originale per facilitare la risposta ===
        sender = message.from_user
        user_ref = f"@{sender.username}" if sender.username else sender.full_name
        await bot.send_message(chat_id=OWNER_ID, text=truncate_message(f"{user_ref}:"))

        sent = await bot.forward_message(
            chat_id=OWNER_ID,
            from_chat_id=message.chat_id,
            message_id=message.message_id
        )
        self.track_message(sent.message_id, message.chat_id, message.message_id)
        log_debug("[manual] Message forwarded and tracked")

    async def generate_response(self, messages):
        """In manual mode the reply is not generated automatically."""
        return "\U0001f570\ufe0f Waiting for manual input."


PLUGIN_CLASS = ManualAIPlugin
