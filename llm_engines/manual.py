from core import say_proxy
from core.context import get_context_state
from core.config import OWNER_ID
from core.ai_plugin_base import AIPluginBase
import json

class ManualAIPlugin(AIPluginBase):
    def __init__(self):
        self.reply_map = {}

    def track_message(self, trainer_message_id, original_chat_id, original_message_id):
        self.reply_map[trainer_message_id] = {
            "chat_id": original_chat_id,
            "message_id": original_message_id
        }

    def get_target(self, trainer_message_id):
        return self.reply_map.get(trainer_message_id)

    def clear(self, trainer_message_id):
        if trainer_message_id in self.reply_map:
            del self.reply_map[trainer_message_id]

    async def handle_incoming_message(self, bot, message, context_memory):
        user_id = message.from_user.id
        text = message.text or ""
        print(f"[DEBUG/manual] Messaggio ricevuto in modalità manuale da chat_id={message.chat_id}")

        # === Caso speciale: /say attivo ===
        target_chat = say_proxy.get_target(user_id)
        if target_chat and target_chat != "EXPIRED":
            print(f"[DEBUG/manual] Invio da /say: chat_id={target_chat}")
            await bot.send_message(chat_id=target_chat, text=text)
            say_proxy.clear(user_id)
            return

        # === Context attivo ===
        if get_context_state():
            print("[DEBUG/manual] Context attivo, invio cronologia")
            history = list(context_memory.get(message.chat_id, []))
            history_json = json.dumps(history, ensure_ascii=False, indent=2)
            if len(history_json) > 4000:
                history_json = history_json[:4000] + "\n... (troncato)"
            await bot.send_message(
                chat_id=OWNER_ID,
                text=f"[Context]\n```json\n{history_json}\n```",
                parse_mode="Markdown"
            )

        sender = message.from_user
        user_ref = f"@{sender.username}" if sender.username else sender.full_name
        await bot.send_message(chat_id=OWNER_ID, text=f"{user_ref}:")
        sent = await bot.forward_message(
            chat_id=OWNER_ID,
            from_chat_id=message.chat_id,
            message_id=message.message_id
        )
        self.track_message(sent.message_id, message.chat_id, message.message_id)
        print(f"[DEBUG/manual] Messaggio inoltrato e tracciato")

    async def generate_response(self, messages):
        """Nel caso manuale, la risposta non viene generata automaticamente."""
        return "🕰️ Risposta in attesa di input manuale."
