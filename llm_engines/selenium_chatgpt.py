# llm_engines/selenium_chatgpt.py

import time
import asyncio
import json
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from telegram import Bot
from core.ai_plugin_base import AIPluginBase
from core.config import OWNER_ID, BOT_TOKEN


class SeleniumChatGPTPlugin(AIPluginBase):

    def __init__(self):
        self.driver = self._get_driver()
        self.bot = Bot(token=BOT_TOKEN)

    def _get_driver(self):
        options = Options()
        options.add_argument("--user-data-dir=./selenium_profile")
        options.add_argument("--profile-directory=Default")
        return webdriver.Chrome(options=options)

    def _notify_owner(self, text):
        asyncio.run(self.bot.send_message(chat_id=OWNER_ID, text=text))

    def _wait_for_user_confirmation(self):
        self._notify_owner("⏸️ In attesa... clicca '✔️ Fatto' su Telegram quando hai risolto login/captcha.")
        input("Premi INVIO quando hai completato il login o il captcha...")

    def login_if_needed(self):
        self.driver.get("https://chat.openai.com")

        if "login" in self.driver.current_url.lower():
            self._notify_owner("⚠️ Login richiesto su ChatGPT. Accedi e risolvi eventuali captcha.")
            self._wait_for_user_confirmation()

        if "captcha" in self.driver.page_source.lower():
            self._notify_owner("⚠️ Captcha rilevato su ChatGPT. Risolvilo manualmente.")
            self._wait_for_user_confirmation()

    def paste_and_send(self, prompt_text):
        textarea = self.driver.find_element(By.TAG_NAME, "textarea")
        textarea.send_keys(prompt_text)
        textarea.send_keys(Keys.ENTER)

    def wait_for_response(self, timeout=30):
        for _ in range(timeout * 2):
            bubbles = self.driver.find_elements(By.CLASS_NAME, "markdown")
            if bubbles:
                last = bubbles[-1].text.strip()
                if last:
                    return last
            time.sleep(0.5)
        return "⚠️ Nessuna risposta trovata."

    def send_prompt_and_get_response(self, prompt_text):
        self.login_if_needed()
        self.paste_and_send(prompt_text)
        return self.wait_for_response()

    def get_target(self, trainer_message_id):
        return None

    def clear(self, trainer_message_id):
        pass

    async def handle_incoming_message(self, bot, message, prompt):
        try:
            print(f"[DEBUG/selenium] Prompt ricevuto da chat_id={message.chat_id}")
            formatted_prompt = self._format_prompt_as_text(prompt)
            response = self.send_prompt_and_get_response(formatted_prompt)

            await bot.send_message(
                chat_id=message.chat_id,
                text=response,
                reply_to_message_id=message.message_id
            )
        except Exception as e:
            print(f"[ERROR/selenium] Errore durante la risposta: {e}")
            await bot.send_message(
                chat_id=message.chat_id,
                text="⚠️ Errore nel plugin Selenium ChatGPT."
            )

    def _format_prompt_as_text(self, prompt: dict) -> str:
        ctx = "\n".join(f"{m['username']}: {m['text']}" for m in prompt.get("context", []))
        mem = "\n".join(f"- {m}" for m in prompt.get("memories", []))
        msg = prompt["message"]["text"]

        return (
            "CONTEXT:\n" + (ctx or "Nessuno") +
            "\n\nMEMORIES:\n" + (mem or "Nessuna") +
            "\n\nUSER:\n" + msg
        )

    async def generate_response(self, messages):
        formatted_prompt = self._format_prompt_as_text_from_messages(messages)
        return self.send_prompt_and_get_response(formatted_prompt)

    def _format_prompt_as_text_from_messages(self, messages):
        parts = []
        for m in messages:
            role = m.get("role", "user")
            content = m.get("content", "")
            parts.append(f"{role.upper()}: {content}")
        return "\n".join(parts)


PLUGIN_CLASS = SeleniumChatGPTPlugin
