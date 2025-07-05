# llm_engines/openai_chatgpt.py

from core.ai_plugin_base import AIPluginBase
import json
import openai  # Assicurati che sia installato
from core.config import get_user_api_key
from core.response_format import text_response, sticker_response

class OpenAIPlugin(AIPluginBase):

    def __init__(self, notify_fn=None):
        from core.notifier import set_notifier
        from core.config import get_current_model

        self.reply_map = {}

        if notify_fn:
            print("[DEBUG/openai] Uso funzione di notifica personalizzata.")
            set_notifier(notify_fn)
        else:
            print("[DEBUG/openai] Nessuna funzione di notifica fornita, uso fallback.")
            set_notifier(lambda chat_id, message: print(f"[NOTIFY fallback] {message}"))

        self._current_model = get_current_model() or "gpt-3.5-turbo"

    def get_supported_models(self):
        return [
            "gpt-3.5-turbo",
            "gpt-3.5-turbo-16k",
            "gpt-4",
            "gpt-4o",
        ]

    def get_current_model(self):
        return self._current_model

    def set_current_model(self, name):
        if name not in self.get_supported_models():
            raise ValueError(f"Modello non supportato: {name}")
        self._current_model = name
        print(f"[DEBUG/openai] Modello attivo aggiornato: {name}")

    def get_target(self, trainer_message_id):
        return self.reply_map.get(trainer_message_id)

    def clear(self, trainer_message_id):
        self.reply_map.pop(trainer_message_id, None)

    async def handle_incoming_message(self, bot, message, prompt):
        """Generate a reply and return it using the unified format."""
        from core.notifier import notify_owner

        notify_owner("🚨 Sto generando la risposta...")

        try:
            response_text = await self.generate_response(prompt)

            return text_response(response_text)

        except Exception as e:
            print(f"[ERROR/OpenAI] Errore durante la risposta: {e}")
            notify_owner(f"❌ Errore OpenAI:\n```\n{e}\n```")

            if bot and message:
                print(f"[ERROR/OpenAI] Failed to deliver reply: {e}")
            return text_response("⚠️ Errore durante la generazione della risposta.")

    async def generate_response(self, prompt):
        from core.config import get_user_api_key

        openai.api_key = get_user_api_key()

        messages = []

        messages.append({
            "role": "system",
            "content": "Sei un assistente utile, preciso e sintetico."
        })

        for entry in prompt.get("context", []):
            messages.append({
                "role": "user",
                "content": entry["text"]
            })

        if prompt.get("memories"):
            memory_text = "\n".join(f"- {m}" for m in prompt["memories"])
            messages.append({
                "role": "system",
                "content": f"[MEMORIE RILEVANTI]\n{memory_text}"
            })

        messages.append({
            "role": "user",
            "content": prompt["message"]["text"]
        })

        print(f"[DEBUG/openai] Invio a OpenAI con modello: {self._current_model}")
        response = openai.ChatCompletion.create(
            model=self._current_model,
            messages=messages
        )
        return response.choices[0].message.content.strip()


PLUGIN_CLASS = OpenAIPlugin
