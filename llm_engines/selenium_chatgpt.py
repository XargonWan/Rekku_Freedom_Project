# llm_engines/selenium_chatgpt.py

import time
import asyncio
import json
import os
import shutil
import datetime
import traceback
import stat
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from telegram import Bot
from core.ai_plugin_base import AIPluginBase
from core.config import OWNER_ID, BOT_TOKEN
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

login_waiting = False

class SeleniumChatGPTPlugin(AIPluginBase):

    def __init__(self):
        print(f"[DEBUG] OWNER_ID = {OWNER_ID!r} ({type(OWNER_ID)})")
        self.bot = Bot(token=BOT_TOKEN)
        self.driver = self._get_driver()

    def _is_profile_locked(self, path):
        try:
            return any(name.startswith("Singleton") or name == "lock" for name in os.listdir(path))
        except Exception as e:
            print(f"[ERROR] Impossibile accedere a {path}: {e}")
            return False

    def _cleanup_old_backups(self, base="selenium_profile_backup_", max_backups=3):
        backups = sorted([d for d in os.listdir('.') if d.startswith(base)], reverse=True)
        for old in backups[max_backups:]:
            print(f"[INFO] Rimozione vecchio backup: {old}")
            shutil.rmtree(old, ignore_errors=True)

    def _get_driver(self):
        from selenium.common.exceptions import WebDriverException

        options = Options()

        chrome_bin = os.getenv("CHROME_BIN", "/usr/bin/google-chrome")
        driver_path = os.getenv("CHROMEDRIVER_PATH", "/usr/bin/chromedriver")
        from core.config import SELENIUM_PROFILE_DIR as profile_dir

        if not profile_dir or not os.path.exists(profile_dir):
            msg = f"\u274c Profilo Selenium non trovato: {profile_dir}"
            print(f"[ERROR] {msg}")
            print(f"[DEBUG] SELENIUM_PROFILE_DIR={profile_dir}")
            self._notify_owner(msg)
            raise RuntimeError(msg)
        
        for fname in ["lock"] + [f for f in os.listdir(profile_dir) if f.startswith("Singleton")]:
            try:
                os.remove(os.path.join(profile_dir, fname))
                print(f"[DEBUG] Rimosso file lock: {fname}")
            except FileNotFoundError:
                pass
            except Exception as e:
                print(f"[WARN] Impossibile rimuovere {fname}: {e}")

        print(f"[DEBUG] Avvio Chrome con profilo: {profile_dir}")
        options.binary_location = chrome_bin
        options.add_argument(f"--user-data-dir={profile_dir}")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-dev-tools")
        options.add_argument("--window-size=1280,1024")
        options.add_experimental_option("detach", True)

        if os.getenv("REKKU_SELENIUM_HEADLESS", "1") != "0":
            options.add_argument("--headless=new")
        else:
            print("[DEBUG] Avvio Chrome in modalit� GUI")

        try:
            driver = webdriver.Chrome(service=Service(driver_path), options=options)
            print("[DEBUG] Apro https://chat.openai.com...")
            driver.get("https://chat.openai.com")
            time.sleep(2)
        except WebDriverException as e:
            self._notify_owner("\u274c Errore avviando Chrome. Controlla CHROME_BIN e CHROMEDRIVER_PATH.")
            raise e

        return driver

    def _notify_owner(self, text):
        asyncio.run(self.bot.send_message(chat_id=OWNER_ID, text=text))

    def _wait_for_user_confirmation(self):
        self._notify_owner("⏸️ In attesa... clicca '✔️ Fatto' su Telegram quando hai risolto login/captcha.")
        input("Premi INVIO quando hai completato il login o il captcha...")

    def login_if_needed(self):
        global login_waiting
        print("[DEBUG/selenium] Entrato in login_if_needed")

        self.driver.get("https://chat.openai.com")
        page_text = self.driver.page_source.lower()
        current_url = self.driver.current_url.lower()

        if "login" in current_url or "captcha" in page_text or "please enable javascript" in page_text:
            login_waiting = True
            print("[WARN] Login/CAPTCHA richiesto o sessione scaduta.")
            self._notify_owner(
                "⚠️ Il profilo Selenium sembra scaduto o bloccato.\n"
                "Apri manualmente il browser, completa l'accesso a https://chat.openai.com,\n"
                "poi rispondi '✔️ Fatto' su Telegram per continuare."
            )
            print("[DEBUG/selenium] In attesa di conferma dall'owner...")
            while login_waiting:
                time.sleep(2)

    def paste_and_send(self, prompt_text):
        try:
            textarea = WebDriverWait(self.driver, 20).until(
                EC.presence_of_element_located((By.TAG_NAME, "textarea"))
            )
            textarea.send_keys(prompt_text)
            textarea.send_keys(Keys.ENTER)
        except Exception as e:
            self._notify_owner("❌ Impossibile trovare la textarea. Sei sicuro di essere loggato?")
            raise e

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
        global login_waiting

        # 🔐 Se in attesa di login e il messaggio arriva dall'OWNER in privato → sblocca
        if login_waiting and message.chat.type == "private" and message.from_user.id == OWNER_ID:
            login_waiting = False
            await bot.send_message(chat_id=OWNER_ID, text="✅ Accesso confermato. Riprendo l’esecuzione.")
            return

        try:
            print(f"[DEBUG/selenium] Prompt ricevuto da chat_id={message.chat_id}")
            formatted_prompt = self._format_prompt_as_text(prompt)
            print("[DEBUG/selenium] Prompt formattato:")
            print(formatted_prompt)

            response = self.send_prompt_and_get_response(formatted_prompt)

            await bot.send_message(
                chat_id=message.chat_id,
                text=response,
                reply_to_message_id=message.message_id
            )

        except Exception as e:
            error_msg = f"[ERROR/selenium] Errore durante la risposta: {e}"
            print(error_msg)
            traceback.print_exc()
            self._notify_owner(f"❌ Errore nel plugin Selenium:\n```\n{e}\n```")


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
