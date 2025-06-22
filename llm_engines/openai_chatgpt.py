import openai
from core.ai_plugin_base import AIPluginBase

class OpenAIAIPlugin(AIPluginBase):
    def __init__(self, api_key):
        self.api_key = api_key
        openai.api_key = api_key
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

    async def generate_response(self, messages):
        # messages = [{"role": "user", "content": "ciao"}]
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=messages
        )
        return response.choices[0].message["content"]

    async def handle_incoming_message(self, bot, message, context_memory):
        text = message.text or ""
        messages = [{"role": "user", "content": text}]
        response = await self.generate_response(messages)
        if response:
            await bot.send_message(
                chat_id=message.chat_id,
                text=response,
                reply_to_message_id=message.message_id
            )