import chromedriver_autoinstaller
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import NoSuchElementException
from core.ai_plugin_base import AIPluginBase
from core.notifier import notify_owner, set_notifier
import asyncio
import os
import subprocess
import glob
import time
import zipfile
import urllib.request
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

def _install_webstore_extension(ext_id: str, name: str) -> str | None:
    """Download and unpack a Chrome Web Store extension if missing.

    Returns the directory path containing the unpacked extension or ``None`` if
    the download fails. The function never raises to avoid breaking Selenium
    startup when network access is unavailable.
    """
    target_dir = os.path.join(SELENIUM_EXTENSIONS_DIR, name)
    manifest = os.path.join(target_dir, "manifest.json")
    if os.path.isfile(manifest):
        print(f"[DEBUG/selenium] Estensione {name} già presente")
        return target_dir

    os.makedirs(target_dir, exist_ok=True)
    url = (
        "https://clients2.google.com/service/update2/crx?response=redirect"
        f"&prodversion=123.0&x=id%3D{ext_id}%26installsource%3Dondemand%26uc"
    )
    crx_path = os.path.join(target_dir, f"{ext_id}.crx")
    try:
        print(f"[DEBUG/selenium] Scaricamento estensione {name} da {url}")
        urllib.request.urlretrieve(url, crx_path)
        with zipfile.ZipFile(crx_path) as zf:
            zf.extractall(target_dir)
        os.remove(crx_path)
        print(f"[DEBUG/selenium] Extension {name} installed")
        return target_dir
    except Exception as e:
        print(f"[ERROR/selenium] Unable to install {name}: {e}")
        # Remove partial files to avoid loading errors
        try:
            shutil.rmtree(target_dir)
        except Exception:
            pass
        return None


def _notify_gui(message: str = ""):
    """Send a notification with the VNC URL, optionally prefixed."""
    url = _build_vnc_url()
    text = f"{message} {url}".strip()
    print(f"[DEBUG/selenium] Invio notifica VNC: {text}")
    try:
        notify_owner(text)
    except Exception as e:
        print(f"[ERROR/selenium] notify_owner failed: {e}")


STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
Object.defineProperty(navigator, 'languages', {get: () => ['en-US','en']});
window.chrome = { runtime: {} };
const getParameter = WebGLRenderingContext.prototype.getParameter;
WebGLRenderingContext.prototype.getParameter = function(p){
  if(p === 37445) return 'Intel Inc.';
  if(p === 37446) return 'Intel Iris OpenGL Engine';
  return getParameter.call(this,p);
};
const getChannelData = AudioBuffer.prototype.getChannelData;
AudioBuffer.prototype.getChannelData = function(){
  const data = getChannelData.apply(this, arguments);
  for(let i=0;i<data.length;i+=100){data[i]+=0.0000001;}
  return data;
};
"""


def _get_driver():
    """Return a configured undetected Chrome driver."""

    headless = os.getenv("REKKU_SELENIUM_HEADLESS", "0") != "0"
    options = uc.ChromeOptions()
    if headless:
        options.add_argument("--headless=new")

    ua = os.getenv(
        "SELENIUM_USER_AGENT",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    )
    options.add_argument(f"--user-agent={ua}")

    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--start-maximized")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-infobars")
    options.add_argument("--disable-extensions")
    # Some Chrome versions do not accept experimental options such as
    # 'excludeSwitches'. We prefer not to set them to avoid startup errors
    # that would prevent the VNC notification.

    os.makedirs(PROFILE_DIR, exist_ok=True)

    try:
        driver = uc.Chrome(
            options=options,
            user_data_dir=PROFILE_DIR,
            headless=headless,
            log_level=3,
        )
    except Exception as e:
        if "excludeSwitches" in str(e):
            print(f"[WARN/selenium] excludeSwitches not supported: {e}. Retrying without it.")
            options.experimental_options.pop("excludeSwitches", None)
            options.experimental_options.pop("useAutomationExtension", None)
            driver = uc.Chrome(
                options=options,
                user_data_dir=PROFILE_DIR,
                headless=headless,
                log_level=3,
            )
        else:
            print(f"[ERROR/selenium] Errore avvio Chrome: {e}")
            _notify_gui(f"❌ Errore Selenium: {e}. Apri")
            raise

    try:
        driver.execute_cdp_cmd("Network.setUserAgentOverride", {"userAgent": ua})
    except Exception as e:
        print(f"[WARN/selenium] UA override failed: {e}")

    try:
        driver.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument",
            {"source": STEALTH_JS},
        )
    except Exception as e:
        print(f"[WARN/selenium] Patch fingerprint fallita: {e}")

    if not headless:
        _notify_gui("🔎 Interfaccia grafica disponibile su")

    return driver


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
            try:
                self.driver = _get_driver()
                # Ensure the right ChromeDriver is available
                chromedriver_autoinstaller.install()
            except Exception as e:
                _notify_gui(f"❌ Errore Selenium: {e}. Apri")
                raise

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

