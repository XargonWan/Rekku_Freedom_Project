from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException
from core.ai_plugin_base import AIPluginBase
from core.notifier import notify_owner
import asyncio


class SeleniumChatGPTPlugin(AIPluginBase):
    def __init__(self, notify_fn=None):
        self.notify_fn = notify_fn
        self.driver = None
        self._init_driver()

    def _init_driver(self):
        chrome_options = Options()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')

        self.driver = webdriver.Chrome(options=chrome_options)
        self.driver.get("https://chat.openai.com")

    def _ensure_logged_in(self):
        current_url = self.driver.current_url
        if "login" in current_url:
            notify_owner("🔐 Login necessario. Completa manualmente il login nel browser.")
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
                notify_owner("❌ Errore Selenium: Sidebar non trovata (CAPTCHA o login richiesto)")
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
        self.notify_fn = fn

PLUGIN_CLASS = SeleniumChatGPTPlugin
