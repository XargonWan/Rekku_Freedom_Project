import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException
from core.ai_plugin_base import AIPluginBase
from core.notifier import notify_owner, set_notifier
import asyncio
import os
import subprocess
import shutil


def _build_vnc_url() -> str:
    """Return the URL to access the noVNC interface."""
    port = os.getenv("WEBVIEW_PORT", "5005")
    host = os.getenv("WEBVIEW_HOST")
    if not host:
        try:
            host = subprocess.check_output(
                "ip route | awk '/default/ {print $3}'",
                shell=True,
            ).decode().strip()
        except Exception as e:
            print(f"[WARN/selenium] Unable to determine host: {e}")
        if not host:
            host = "localhost"
    url = f"http://{host}:{port}/vnc.html"
    print(f"[DEBUG/selenium] VNC URL built: {url}")
    return url

def _notify_gui(message: str = ""):
    """Send a notification with the VNC URL, optionally prefixed."""
    url = _build_vnc_url()
    text = f"{message} {url}".strip()
    print(f"[DEBUG/selenium] Invio notifica VNC: {text}")
    try:
        notify_owner(text)
    except Exception as e:
        print(f"[ERROR/selenium] notify_owner failed: {e}")





class SeleniumChatGPTPlugin(AIPluginBase):
    def __init__(self, notify_fn=None):
        """Initialize the plugin without starting Selenium yet."""
        self.driver = None
        self._queue: asyncio.Queue = asyncio.Queue()
        self._worker_task = asyncio.create_task(self._worker_loop())
        if notify_fn:
            set_notifier(notify_fn)

    def _init_driver(self):
        if self.driver is None:
            chrome_path = shutil.which("google-chrome-stable") or shutil.which("google-chrome") or "google-chrome"
            profile_dir = os.path.expanduser("/home/rekku/.ucd-profile")
            os.makedirs(profile_dir, exist_ok=True)

            headless_flag = os.getenv("REKKU_SELENIUM_HEADLESS")
            headless = "new" if headless_flag and headless_flag != "0" else False

            options = uc.ChromeOptions()
            if headless:
                options.add_argument("--headless=new")
            options.add_argument("--disable-blink-features=AutomationControlled")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument(f"--user-data-dir={profile_dir}")

            try:
                self.driver = uc.Chrome(
                    options=options,
                    headless=headless,
                    browser_executable_path=chrome_path,
                )
            except Exception as e:
                print(f"[ERROR/selenium] Failed to start Chrome: {e}")
                _notify_gui(f"❌ Errore Selenium: {e}. Apri")
                raise SystemExit(1)

    def _ensure_logged_in(self):
        try:
            current_url = self.driver.current_url
        except Exception:
            current_url = ""
        if current_url and ("login" in current_url or "auth0" in current_url):
            print("[DEBUG/selenium] Login richiesto, notifico l'utente")
            _notify_gui("🔐 Login necessario. Apri")
            return False
        return True

    async def handle_incoming_message(self, bot, message, prompt):
        """Queue the message to be processed sequentially."""
        await self._queue.put((bot, message, prompt))

    async def _worker_loop(self):
        while True:
            bot, message, prompt = await self._queue.get()
            try:
                await self._process_message(bot, message, prompt)
            except Exception as e:
                _notify_gui(f"❌ Errore Selenium: {e}. Apri")
            finally:
                self._queue.task_done()

    async def _process_message(self, bot, message, prompt):
        print("[DEBUG/selenium] Prompt ricevuto:", prompt)

        if self.driver is None:
            self._init_driver()
        if not self._ensure_logged_in():
            return

        # Vai nella chat corretta (puoi estendere questa logica)
        await asyncio.sleep(1)
        self.driver.get("https://chat.openai.com")
        await asyncio.sleep(1)
        try:
            self.driver.find_element(By.TAG_NAME, "aside")
        except NoSuchElementException:
            print("[DEBUG/selenium] Sidebar missing, notifying owner")
            _notify_gui("❌ Selenium error: Sidebar not found. Open UI")
            return

        # Simula risposta finta
        await bot.send_message(
            chat_id=message.chat_id,
            text="🤖 (Risposta finta: plugin Selenium operativo)"
        )


    def get_supported_models(self):
        return []  # nessun modello per ora

    def set_notify_fn(self, fn):
        set_notifier(fn)
        if self.driver is None:
            try:
                self._init_driver()
            except Exception as e:
                _notify_gui(f"❌ Errore Selenium: {e}. Apri")

PLUGIN_CLASS = SeleniumChatGPTPlugin

