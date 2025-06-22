import openai
from core.config import get_current_model, set_current_model
from core.ai_plugin_base import AIPluginBase

class OpenAIAIPlugin(AIPluginBase):
    def __init__(self, api_key, default_model="gpt-4"):
        self.api_key = api_key
        self.default_model = default_model
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

    def get_supported_models(self) -> list[str]:
        return ["gpt-3.5-turbo", "gpt-4", "gpt-4o"]

    def set_current_model(self, model: str):
        if model not in self.get_supported_models():
            raise ValueError(f"Modello non supportato: {model}")
        set_current_model(model)

    def get_current_model(self) -> str:
        return get_current_model() or self.default_model

    async def generate_response(self, messages):
        if not self.api_key:
            raise ValueError("\u26a0\ufe0f Nessuna chiave API disponibile.")

        openai.api_key = self.api_key
        model = self.get_current_model()

        response = openai.ChatCompletion.create(
            model=model,
            messages=messages,
            temperature=0.9,           # 🔥 Creatività viva
            top_p=1.0,                # 🌌 Massima libertà di scelta
            presence_penalty=0.6,     # 🚫 Evita la monotonia nei temi
            frequency_penalty=0.3     # 🔁 Riduce ripetizioni nella forma
        )
        return response.choices[0].message["content"]

    async def handle_incoming_message(self, bot, message, context_memory):
        text = message.text or ""
        messages = [{"role": "user", "content": text}]
        try:
            response = await self.generate_response(messages)
            if response:
                await bot.send_message(
                    chat_id=message.chat_id,
                    text=response,
                    reply_to_message_id=message.message_id
                )
        except Exception as e:
            print(f"[ERROR/chatgpt] Errore durante la generazione della risposta: {e}")
            await bot.send_message(
                chat_id=message.chat_id,
                text="\u26a0\ufe0f Errore nella generazione della risposta. Verifica la tua API key o modello."
            )
