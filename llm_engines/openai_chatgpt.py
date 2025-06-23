import openai
from core.config import get_current_model, set_current_model
from core.ai_plugin_base import AIPluginBase
from core.prompt_engine import build_prompt
from core.plugin_instance import rekku_identity_prompt
from core.rekku_core_memory import should_remember, silently_record_memory
from core.rekku_emotion_evaluator import evaluate_emotional_impact
from core.db import get_db


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

    def extract_tags(self, text: str) -> list:
        """
        Estrazione locale di tag: overrideabile dal core.
        """
        text = text.lower()
        tags = []
        if "jay" in text:
            tags.append("jay")
        if "retrodeck" in text:
            tags.append("retrodeck")
        if "amore" in text or "affetto" in text:
            tags.append("emozioni")
        return tags

    def search_memories(self, tags=None, scope=None, limit=5):
        """
        Ricerca semplice nel DB. Funzione fallback per il core.
        """
        if not tags:
            return []

        query = "SELECT content FROM memories WHERE 1=1"
        params = []

        for tag in tags:
            query += " AND tags LIKE ?"
            params.append(f"%{tag}%")

        if scope:
            query += " AND scope = ?"
            params.append(scope)

        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        with get_db() as db:
            return [row[0] for row in db.execute(query, params)]

    async def generate_response(self, messages):
        if not self.api_key:
            raise ValueError("⚠️ Nessuna chiave API disponibile.")

        openai.api_key = self.api_key
        model = self.get_current_model()

        response = openai.ChatCompletion.create(
            model=model,
            messages=messages,
            temperature=0.9,
            top_p=1.0,
            presence_penalty=0.6,
            frequency_penalty=0.3
        )
        return response.choices[0].message["content"]

    async def handle_incoming_message(self, bot, message, context_memory):
        user_text = message.text or ""

        messages = build_prompt(
            user_text=user_text,
            identity_prompt=rekku_identity_prompt,
            extract_tags_fn=self.extract_tags,
            search_memories_fn=self.search_memories
        )

        try:
            response = await self.generate_response(messages)

            if response:
                await bot.send_message(
                    chat_id=message.chat_id,
                    text=response,
                    reply_to_message_id=message.message_id
                )

                if should_remember(user_text, response):
                    silently_record_memory(user_text, response)

                evaluate_emotional_impact(
                    user_text, response, message.from_user.full_name
                )

        except Exception as e:
            print(f"[ERROR/chatgpt] Errore durante la generazione della risposta: {e}")
            await bot.send_message(
                chat_id=message.chat_id,
                text="⚠️ Errore nella generazione della risposta. Controlla API key o modello."
            )
