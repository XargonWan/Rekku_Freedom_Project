from core.ai_plugin_base import AIPluginBase
from core.prompt_engine import build_prompt
from core.rekku_core_memory import should_remember, silently_record_memory
from core.db import get_db

class LLMTestSimulator(AIPluginBase):

    def __init__(self, prompt=None):
        self.reply_map = {}
        self.identity_prompt = prompt

    def track_message(self, trainer_message_id, original_chat_id, original_message_id):
        self.reply_map[trainer_message_id] = {
            "chat_id": original_chat_id,
            "message_id": original_message_id
        }

    def get_target(self, trainer_message_id):
        return self.reply_map.get(trainer_message_id)

    def clear(self, trainer_message_id):
        self.reply_map.pop(trainer_message_id, None)

    def extract_tags(self, text: str) -> list:
        text = text.lower()
        tags = []
        if "jay" in text: tags.append("jay")
        if "retrodeck" in text: tags.append("retrodeck")
        if "amore" in text or "affetto" in text: tags.append("emozioni")
        return tags

    def search_memories(self, tags=None, scope=None, limit=5):
        if not tags:
            return []

        query = "SELECT content FROM memories WHERE 1=1"
        params = [f"%{tag}%" for tag in tags]
        query += "".join(" AND tags LIKE ?" for _ in tags)

        if scope:
            query += " AND scope = ?"
            params.append(scope)

        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        with get_db() as db:
            return [row[0] for row in db.execute(query, params)]

    def get_supported_models(self):
        return ["simulated-model"]

    def get_current_model(self):
        return "simulated-model"

    def set_current_model(self, model: str):
        if model != "simulated-model":
            raise ValueError("Solo 'simulated-model' è supportato.")

    async def generate_response(self, messages):
        print("\n==================\n🧠 PROMPT SIMULATO\n==================")
        for msg in messages:
            print(f"[{msg.get('role', '').upper()}]\n{msg.get('content', '')}\n")
        print("===== FINE =====\n")
        return "🤖 [Risposta simulata]"

    async def handle_incoming_message(self, bot, message, context_memory):
        user_text = message.text or ""
        messages = build_prompt(
            user_text=user_text,
            identity_prompt=self.identity_prompt,
            extract_tags_fn=self.extract_tags,
            search_memories_fn=self.search_memories
        )
        try:
            response = await self.generate_response(messages)
            await bot.send_message(
                chat_id=message.chat_id,
                text=response,
                reply_to_message_id=message.message_id
            )
            if should_remember(user_text, response):
                silently_record_memory(user_text, response)

        except Exception as e:
            print(f"[ERROR/simulator] Errore nel simulatore: {e}")
            await bot.send_message(
                chat_id=message.chat_id,
                text="⚠️ Errore nella risposta simulata."
            )

PLUGIN_CLASS = LLMTestSimulator
