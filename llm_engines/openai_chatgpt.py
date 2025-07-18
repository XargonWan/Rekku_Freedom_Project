# llm_engines/openai_chatgpt.py

from core.ai_plugin_base import AIPluginBase
import json
import openai
from core.config import get_user_api_key
from core.logging_utils import log_debug, log_error

class OpenAIPlugin(AIPluginBase):
    def __init__(self, notify_fn=None):
        from core.notifier import set_notifier
        from core.config import get_current_model

        self.reply_map = {}
        if notify_fn:
            set_notifier(notify_fn)
        else:
            set_notifier(lambda chat_id, message: None)

        self._current_model = get_current_model() or "gpt-3.5-turbo"

    def get_supported_models(self):
        return ["gpt-3.5-turbo", "gpt-3.5-turbo-16k", "gpt-4", "gpt-4o"]

    def get_current_model(self):
        return self._current_model

    def set_current_model(self, name):
        if name not in self.get_supported_models():
            raise ValueError(f"Unsupported model: {name}")
        self._current_model = name

    def get_target(self, trainer_message_id):
        return self.reply_map.get(trainer_message_id)

    def clear(self, trainer_message_id):
        self.reply_map.pop(trainer_message_id, None)

    async def handle_incoming_message(self, bot, message, prompt):
        """Compatibility wrapper for legacy usage."""
        return await self.generate_response(prompt)

    async def generate_response(self, prompt: dict) -> str:
        openai.api_key = get_user_api_key()

        messages = [
            {"role": "system", "content": "You are a helpful, precise and concise assistant."}
        ]

        for entry in prompt.get("context", {}).get("messages", []):
            text = entry.get("text")
            if text:
                messages.append({"role": "user", "content": text})

        user_text = prompt.get("input", {}).get("payload", {}).get("text", "")
        messages.append({"role": "user", "content": user_text})

        log_debug(f"[openai] Sending to OpenAI model: {self._current_model}")
        response = openai.ChatCompletion.create(model=self._current_model, messages=messages)
        reply_text = response.choices[0].message.content.strip()

        chat_id = prompt.get("input", {}).get("payload", {}).get("source", {}).get("chat_id")
        thread_id = prompt.get("input", {}).get("payload", {}).get("source", {}).get("thread_id")

        action = {
            "type": "message",
            "interface": "telegram",
            "payload": {"text": reply_text, "target": chat_id, "thread_id": thread_id},
        }
        return json.dumps(action, ensure_ascii=False)

PLUGIN_CLASS = OpenAIPlugin
