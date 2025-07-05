# llm_engines/manual.py

from core import say_proxy, message_map
from core.config import OWNER_ID
from core.ai_plugin_base import AIPluginBase
import json
from telegram.constants import ParseMode
from core.response_format import text_response

class ManualAIPlugin(AIPluginBase):

    def __init__(self, notify_fn=None):
        from core.notifier import set_notifier

        # Inizializza la tabella di mapping persistente
        message_map.init_table()

        if notify_fn:
            print("[DEBUG/manual] Uso funzione di notifica personalizzata.")
            set_notifier(notify_fn)
        else:
            print("[DEBUG/manual] Nessuna funzione di notifica fornita, uso fallback.")
            set_notifier(lambda chat_id, message: print(f"[NOTIFY fallback] {message}"))

    def track_message(self, trainer_message_id, original_chat_id, original_message_id):
        """Persist the mapping for a forwarded message."""
        message_map.add_mapping(trainer_message_id, original_chat_id, original_message_id)

    def get_target(self, trainer_message_id):
        return message_map.get_mapping(trainer_message_id)

    def clear(self, trainer_message_id):
        message_map.delete_mapping(trainer_message_id)

    async def handle_incoming_message(self, bot, message, prompt):
        from core.notifier import notify_owner

        notify_owner("🚨 Sto generando la risposta...")

        user_id = message.from_user.id
        text = message.text or ""
        print(f"[DEBUG/manual] Messaggio ricevuto in modalità manuale da chat_id={message.chat_id}")

        # === Caso speciale: /say attivo ===
        target_chat = say_proxy.get_target(user_id)
        if target_chat and target_chat != "EXPIRED":
            print(f"[DEBUG/manual] Invio da /say: chat_id={target_chat}")
            await bot.send_message(chat_id=target_chat, text=text)
            say_proxy.clear(user_id)
            return text_response("📝 Messaggio inviato dal trainer.")

        # === Invia prompt JSON al trainer (OWNER_ID) ===
        import json
        from telegram.constants import ParseMode

        prompt_json = json.dumps(prompt, ensure_ascii=False, indent=2)
        if len(prompt_json) > 4000:
            prompt_json = prompt_json[:4000] + "\n... (troncato)"

        await bot.send_message(
            chat_id=OWNER_ID,
            text=f"\U0001f4e6 *Prompt JSON generato:*\n```json\n{prompt_json}\n```",
            parse_mode=ParseMode.MARKDOWN
        )

        # === Inoltra il messaggio originale per facilitare la risposta ===
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
        return text_response("⌛ In attesa di risposta manuale.")

    async def generate_response(self, messages):
        """Manual mode should not generate a reply automatically."""
        print("[DEBUG/manual] \u26a0\ufe0f generate_response() called unexpectedly in manual mode.")
        return ""


PLUGIN_CLASS = ManualAIPlugin
