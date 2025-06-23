# llm_engines/openai_chatgpt.py

from core import say_proxy
from core.context import get_context_state
from core.config import OWNER_ID
from core.ai_plugin_base import AIPluginBase
from core.prompt_engine import build_prompt
from core.db import get_db
import json
from core.prompt_engine import search_memories



class ManualAIPlugin(AIPluginBase):

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

    async def handle_incoming_message(self, bot, message, context_memory):
        user_id = message.from_user.id
        text = message.text or ""
        print(f"[DEBUG/manual] Messaggio ricevuto in modalit� manuale da chat_id={message.chat_id}")

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

        # === Prompt simulato ===
        messages = build_prompt(
            user_text=text,
            identity_prompt=self.identity_prompt,
            extract_tags_fn=self.extract_tags,
            search_memories_fn=search_memories
        )
        prompt_json = json.dumps(messages, ensure_ascii=False, indent=2)
        if len(prompt_json) > 4000:
            prompt_json = prompt_json[:4000] + "\n... (troncato)"

        await bot.send_message(
            chat_id=OWNER_ID,
            text=f"\U0001f4dc Prompt generato:\n```json\n{prompt_json}\n```",
            parse_mode="Markdown"
        )

        # === Inoltro messaggio ===
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
        return "\U0001f570\ufe0f Risposta in attesa di input manuale."


PLUGIN_CLASS = ManualAIPlugin
