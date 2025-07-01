from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException
from core.ai_plugin_base import AIPluginBase
from core.notifier import notify_owner, set_notifier
from core.config import SELENIUM_PROFILE_DIR
import asyncio
import os

WEBVIEW_HOST = os.getenv("WEBVIEW_HOST", "localhost")
WEBVIEW_PORT = os.getenv("WEBVIEW_PORT", "5005")
WEBVIEW_URL = f"http://{WEBVIEW_HOST}:{WEBVIEW_PORT}/vnc.html"


class SeleniumChatGPTPlugin(AIPluginBase):
    def __init__(self, notify_fn=None):
        if notify_fn:
            set_notifier(notify_fn)
        self.driver = None
        self._init_driver()

    def _init_driver(self):
        chrome_options = Options()
        headless = os.getenv('REKKU_SELENIUM_HEADLESS', '1') != '0'
        if headless:
            chrome_options.add_argument('--headless=new')
        else:
            notify_owner(f"🔎 Interfaccia grafica disponibile su {WEBVIEW_URL}")
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument(f'--user-data-dir={SELENIUM_PROFILE_DIR}')

        self.driver = webdriver.Chrome(options=chrome_options)
        self.driver.get("https://chat.openai.com")

    def _ensure_logged_in(self):
        current_url = self.driver.current_url
        if "login" in current_url:
            notify_owner(
                f"🔐 Login necessario. Apri {WEBVIEW_URL} per completare la procedura."
            )
            return False
        return True

    async def handle_incoming_message(self, bot, message, prompt_data):
        print("[DEBUG/selenium] Prompt ricevuto:", prompt_data)

        try:
            if not self._ensure_logged_in():
                return

            # Vai nella chat corretta (puoi estendere questa logica)
            await asyncio.sleep(1)
            self.driver.get("https://chat.openai.com")
            await asyncio.sleep(2)

            # Cerca l'elemento sidebar per verificare accesso
            try:
                self.driver.find_element(By.TAG_NAME, "aside")
            except NoSuchElementException:
                notify_owner(
                    f"❌ Errore Selenium: Sidebar non trovata. Apri {WEBVIEW_URL} per risolvere CAPTCHA o login."
                )
                return

            # Simula risposta finta
            await bot.send_message(
                chat_id=message.chat_id,
                text="🤖 (Risposta finta: plugin Selenium operativo)"
            )

        except Exception as e:
            notify_owner(f"❌ Errore Selenium: {e}")

    def get_supported_models(self):
        return []  # nessun modello per ora

    def set_notify_fn(self, fn):
        set_notifier(fn)

PLUGIN_CLASS = SeleniumChatGPTPlugin
