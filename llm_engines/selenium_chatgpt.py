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
from selenium.common.exceptions import TimeoutException

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
        import tempfile
        import tarfile
        from selenium.common.exceptions import WebDriverException

        print("[DEBUG] Inizio _get_driver()")

        chrome_bin = os.getenv("CHROME_BIN", "/usr/bin/google-chrome")
        driver_path = os.getenv("CHROMEDRIVER_PATH", "/usr/bin/chromedriver")
        archive_path = os.getenv("SELENIUM_PROFILE_ARCHIVE", "./selenium_profile.tar.gz")

        print(f"[DEBUG] chrome_bin = {chrome_bin}")
        print(f"[DEBUG] driver_path = {driver_path}")
        print(f"[DEBUG] archive_path = {archive_path}")

        if not os.path.isfile(archive_path):
            msg = f"\u274c Archivio profilo Selenium non trovato: {archive_path}"
            print(f"[ERROR] {msg}")
            self._notify_owner(msg)
            raise RuntimeError(msg)

        temp_profile = tempfile.mkdtemp(prefix="selenium_profile_extracted_")
        print(f"[DEBUG] Estrazione archivio Selenium in: {temp_profile}")

        try:
            with tarfile.open(archive_path, "r:gz") as tar:
                tar.extractall(path=temp_profile)
            print("[DEBUG] Estrazione completata.")
        except Exception as e:
            msg = f"\u274c Estrazione profilo fallita: {e}"
            print(f"[ERROR] {msg}")
            self._notify_owner(msg)
            raise RuntimeError(msg)

        for subdir in ["", "Default"]:
            for fname in ["lock", "SingletonLock", "SingletonCookie", "SingletonSocket"]:
                lock_path = os.path.join(temp_profile, subdir, fname)
                try:
                    if os.path.exists(lock_path):
                        os.remove(lock_path)
                        print(f"[DEBUG] Rimosso: {lock_path}")
                except Exception as e:
                    print(f"[WARN] Impossibile rimuovere {lock_path}: {e}")

        options = Options()
        options.binary_location = chrome_bin
        options.add_argument(f"--user-data-dir={temp_profile}")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1280,1024")
        options.add_experimental_option("detach", True)

        if os.getenv("REKKU_SELENIUM_HEADLESS", "1") != "0":
            options.add_argument("--headless=new")
            print("[DEBUG] Modalit� headless attiva.")
        else:
            print("[DEBUG] Avvio Chrome in modalit� GUI")

        print("[DEBUG] Tentativo di creazione del driver Chrome...")
        try:
            driver = webdriver.Chrome(service=Service(driver_path), options=options)
            print("[DEBUG] Driver Chrome creato con successo.")
            print("[DEBUG] Apro https://chat.openai.com...")
            driver.get("https://chat.openai.com")
            print("[DEBUG] Navigazione iniziale completata.")
            time.sleep(2)
            return driver
        except WebDriverException as e:
            msg = "\u274c Errore avviando Chrome. Controlla CHROME_BIN e CHROMEDRIVER_PATH."
            print(f"[ERROR] {msg}")
            self._notify_owner(msg)
            raise e

    async def _notify_owner_async(self, text):
        await self.bot.send_message(chat_id=OWNER_ID, text=text)

    def _notify_owner(self, text):
        try:
            loop = asyncio.get_running_loop()
            asyncio.create_task(self._notify_owner_async(text))
        except RuntimeError:
            # No running loop
            asyncio.run(self._notify_owner_async(text))

    def _wait_for_user_confirmation(self):
        self._notify_owner("⏸️ In attesa... clicca '✔️ Fatto' su Telegram quando hai risolto login/captcha.")
        input("Premi INVIO quando hai completato il login o il captcha...")

    def login_if_needed(self):
        global login_waiting
        print("[DEBUG/selenium] Entrato in login_if_needed")

        try:
            print("[DEBUG/selenium] Navigo su https://chat.openai.com")
            self.driver.get("https://chat.openai.com")
        except Exception as e:
            print(f"[ERROR/selenium] Errore durante il self.driver.get: {e}")
            self._notify_owner(f"❌ Errore caricando la pagina iniziale: {e}")
            raise e

        try:
            page_text = self.driver.page_source.lower()
            current_url = self.driver.current_url.lower()
            print(f"[DEBUG/selenium] URL corrente: {current_url}")
        except Exception as e:
            print(f"[ERROR/selenium] Errore ottenendo lo stato della pagina: {e}")
            raise

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
        else:
            print("[DEBUG/selenium] Nessun login richiesto. Continuo.")

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

            chat_path = self._build_chat_path_from_message(message)
            self.login_if_needed()
            self.go_to_chat_by_path(chat_path)
            self.paste_and_send(formatted_prompt)
            response = self.wait_for_response()

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
    
    def _build_chat_path_from_message(self, message):
        parts = ["Telegram"]
        if message.chat.type == "private":
            parts.append("DM")
            parts.append(message.from_user.first_name or str(message.from_user.id))
        elif message.chat.type in ("group", "supergroup"):
            if message.chat.title:
                parts.append(message.chat.title)
            # (Opzionale: ulteriore sottosezione, es. thread)
            if hasattr(message, "message_thread_id") and message.message_thread_id:
                parts.append(f"Thread {message.message_thread_id}")
        else:
            parts.append(str(message.chat.id))  # fallback grezzo
        return " / ".join(parts)
    
    def go_to_chat_by_path(self, chat_path: str):
        from datetime import datetime
        from pathlib import Path

        print(f"[DEBUG/selenium] Navigo nella chat con path: {chat_path}")
        parts = [p.strip().lower() for p in chat_path.split("/") if p.strip()]
        print(f"[DEBUG/selenium] Parti attese del path: {parts}")

        try:
            if "chat.openai.com" not in self.driver.current_url:
                print("[DEBUG/selenium] URL non corretto, ricarico pagina giusta.")
                self.driver.get("https://chat.openai.com/chat")
                time.sleep(2)

            # Prova a trovare la sidebar principale
            try:
                sidebar = WebDriverWait(self.driver, 20).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, 'nav[data-testid="left-nav"]'))
                )
            except TimeoutException:
                # Dump di emergenza per debug
                timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
                html_path = f"debug_failed_sidebar_{timestamp}.html"
                screenshot_path = f"debug_failed_sidebar_{timestamp}.png"
                Path(html_path).write_text(self.driver.page_source)
                self.driver.save_screenshot(screenshot_path)
                print(f"[DEBUG/selenium] Dump salvato in: {html_path}, {screenshot_path}")
                raise Exception("\u274c Sidebar non trovata nella UI di ChatGPT.")

            current_node = sidebar
            for depth, part in enumerate(parts):
                print(f"[DEBUG/selenium] Cerco livello {depth}: '{part}'")
                links = current_node.find_elements(By.TAG_NAME, "a")
                found = False
                for link in links:
                    label = link.text.strip().lower()
                    if part in label:
                        print(f"[DEBUG/selenium] \u2192 Match livello {depth}: {label}")
                        self.driver.execute_script("arguments[0].scrollIntoView(true);", link)
                        time.sleep(0.3)
                        self.driver.execute_script("arguments[0].click();", link)
                        time.sleep(1.5)
                        found = True
                        break
                if not found:
                    raise Exception(f"\u274c Livello '{part}' non trovato nella sidebar.")

            print("[DEBUG/selenium] \u2705 Chat selezionata con successo.")

        except Exception as e:
            error = f"\u274c Errore nella selezione della chat '{chat_path}': {e}"
            print(f"[ERROR/selenium] {error}")
            self._notify_owner(f"\u26a0\ufe0f Impossibile trovare la chat:\n`{chat_path}`\n\nErrore: {e}")
            raise

PLUGIN_CLASS = SeleniumChatGPTPlugin
