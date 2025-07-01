from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException
from core.ai_plugin_base import AIPluginBase
from core.notifier import notify_owner, set_notifier
from core.config import SELENIUM_PROFILE_DIR
import asyncio
import os

def _get_default_host() -> str:
    explicit = os.getenv("WEBVIEW_HOST")
    if explicit:
        return explicit
    try:
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "localhost"

WEBVIEW_HOST = _get_default_host()
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
        chrome_options.add_argument('--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36')
        # Evita che il browser si identifichi come "ChromeHeadless"
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_experimental_option('excludeSwitches', ['enable-automation'])
        chrome_options.add_experimental_option('useAutomationExtension', False)

        self.driver = webdriver.Chrome(options=chrome_options)
        # Nasconde proprieta' webdriver per evitare detection
        try:
            self.driver.execute_cdp_cmd(
                "Page.addScriptToEvaluateOnNewDocument",
                {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"},
            )
        except Exception:
            pass
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
        headless = os.getenv('REKKU_SELENIUM_HEADLESS', '1') != '0'
        if not headless:
            notify_owner(f"🔎 Interfaccia grafica disponibile su {WEBVIEW_URL}")

PLUGIN_CLASS = SeleniumChatGPTPlugin
