# llm_engines/openai_chatgpt.py

from core.ai_plugin_base import AIPluginBase
import json
import openai  # Assicurati che sia installato
from core.config import get_user_api_key
from core.logging_utils import log_debug, log_info, log_warning, log_error
from core.transport_layer import llm_to_interface

class OpenAIPlugin(AIPluginBase):

    def __init__(self, notify_fn=None):
        from core.notifier import set_notifier
        from core.config import get_current_model

        self.reply_map = {}

        if notify_fn:
            log_debug("[openai] Uso funzione di notifica personalizzata.")
            set_notifier(notify_fn)
        else:
            log_debug("[openai] Nessuna funzione di notifica fornita, uso fallback.")
            set_notifier(lambda chat_id, message: log_info(f"[NOTIFY fallback] {message}"))

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
            raise ValueError(f"Unsupported model: {name}")
        self._current_model = name
        log_debug(f"[openai] Active model updated: {name}")

    def get_target(self, trainer_message_id):
        return self.reply_map.get(trainer_message_id)

    def clear(self, trainer_message_id):
        self.reply_map.pop(trainer_message_id, None)

    async def handle_incoming_message(self, bot, message, prompt):
        from core.notifier import notify_trainer
        notify_trainer("🚨 Generating the reply...")

        try:
            response = await self.generate_response(prompt)

            if bot and message:
                log_debug(f"[openai] Invio risposta a chat_id={message.chat_id}")
                await llm_to_interface(
                    bot.send_message,
                    chat_id=message.chat_id,
                    text=response,
                    reply_to_message_id=getattr(message, 'message_id', None),
                    interface='telegram' if getattr(bot.__class__, '__module__', '').startswith('telegram') else 'generic',
                )

            return response

        except Exception as e:
            log_error(f"[OpenAI] Error while responding: {repr(e)}", e)
            notify_trainer(f"❌ OpenAI error:\n```\n{e}\n```")

            if bot and message:
                await bot.send_message(
                    chat_id=message.chat_id,
                    text="⚠️ LLM response error."
                )
            return "⚠️ Error during response generation."

    async def generate_response(self, prompt):
        from core.config import get_user_api_key

        openai.api_key = get_user_api_key()

        messages = []

        # Include interface information in system message
        interface = prompt.get("input", {}).get("interface", "unknown")
        messages.append({
            "role": "system",
            "content": f"The message comes from the {interface} interface."
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
                "content": f"[RELEVANT MEMORIES]\n{memory_text}"
            })

        # Correct path to the message text
        message_text = prompt.get("input", {}).get("payload", {}).get("text", "")
        messages.append({
            "role": "user",
            "content": message_text
        })

        log_debug(f"[openai] Invio a OpenAI con modello: {self._current_model}")
        response = openai.ChatCompletion.create(
            model=self._current_model,
            messages=messages
        )
        return response.choices[0].message.content.strip()


PLUGIN_CLASS = OpenAIPlugin
