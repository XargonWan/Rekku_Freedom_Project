# llm_engines/openai_chatgpt.py

from core.ai_plugin_base import AIPluginBase
import json
import openai  # Assicurati che sia installato
from core.config import get_user_api_key

class OpenAIPlugin(AIPluginBase):

    def __init__(self):
        self.reply_map = {}

    def get_target(self, trainer_message_id):
        return self.reply_map.get(trainer_message_id)

    def clear(self, trainer_message_id):
        self.reply_map.pop(trainer_message_id, None)

    async def handle_incoming_message(self, bot, message, prompt):
        try:
            response = await self.generate_response(prompt)
            await bot.send_message(
                chat_id=message.chat_id,
                text=response,
                reply_to_message_id=message.message_id
            )
        except Exception as e:
            print(f"[ERROR/OpenAI] Errore durante la risposta: {e}")
            await bot.send_message(
                chat_id=message.chat_id,
                text="⚠️ Errore nella risposta LLM."
            )

    async def generate_response(self, prompt):
        openai.api_key = get_user_api_key()

        # Adatta il prompt al formato richiesto dalle OpenAI API
        messages = []

        # Se vuoi, puoi aggiungere un messaggio system opzionale
        messages.append({
            "role": "system",
            "content": "Sei un assistente utile, preciso e sintetico."
        })

        # Aggiungi i messaggi di contesto
        for entry in prompt.get("context", []):
            messages.append({
                "role": "user",
                "content": entry["text"]
            })

        # Aggiungi eventuali memorie (opzionale, come messaggi system/user)
        if prompt.get("memories"):
            memory_text = "\n".join(f"- {m}" for m in prompt["memories"])
            messages.append({
                "role": "system",
                "content": f"[MEMORIE RILEVANTI]\n{memory_text}"
            })

        # Aggiungi il messaggio corrente dell'utente
        messages.append({
            "role": "user",
            "content": prompt["message"]["text"]
        })

        # Richiesta al modello
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=messages
        )
        return response.choices[0].message.content.strip()


PLUGIN_CLASS = OpenAIPlugin
