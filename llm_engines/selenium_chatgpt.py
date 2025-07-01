from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import NoSuchElementException
from core.ai_plugin_base import AIPluginBase
from core.notifier import notify_owner, set_notifier
from core.config import SELENIUM_PROFILE_DIR, SELENIUM_EXTENSIONS_DIR
import asyncio
import os
import subprocess
import glob
import time
import zipfile
import urllib.request
import shutil

def _get_default_host() -> str:
    explicit = os.getenv("WEBVIEW_HOST")
    if explicit and explicit not in {"localhost", "127.0.0.1", "0.0.0.0"}:
        return explicit
    try:
        output = subprocess.check_output(["hostname", "-I"]).decode().strip()
        ip = output.split()[0]
        return ip
    except Exception:
        return "localhost"

WEBVIEW_HOST = _get_default_host()
WEBVIEW_PORT = os.getenv("WEBVIEW_PORT", "5005")
WEBVIEW_URL = f"http://{WEBVIEW_HOST}:{WEBVIEW_PORT}/vnc.html"

# Path assoluto per il profilo Selenium montato dall'host
PROFILE_DIR = os.path.abspath(SELENIUM_PROFILE_DIR)


def _cleanup_profile_locks():
    """Remove Chrome profile lock files that prevent reuse."""
    try:
        for path in glob.glob(os.path.join(PROFILE_DIR, "Singleton*")):
            os.remove(path)
    except Exception:
        pass


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
        print(f"[DEBUG/selenium] Estensione {name} installata")
        return target_dir
    except Exception as e:
        print(f"[ERROR/selenium] Impossibile installare {name}: {e}")
        # Elimina eventuali file parziali per evitare errori di caricamento
        try:
            shutil.rmtree(target_dir)
        except Exception:
            pass
        return None


class SeleniumChatGPTPlugin(AIPluginBase):
    def __init__(self, notify_fn=None):
        if notify_fn:
            set_notifier(notify_fn)
        self.driver = None
        if notify_fn:
            try:
                self._init_driver()
            except Exception as e:
                notify_owner(f"❌ Errore Selenium: {e}")

    def _init_driver(self):
        if self.driver is not None:
            return
        _cleanup_profile_locks()
        chrome_options = Options()
        headless = os.getenv("REKKU_SELENIUM_HEADLESS", "1") != "0"
        if headless:
            chrome_options.add_argument("--headless=new")
        else:
            notify_owner(f"🔎 Interfaccia grafica disponibile su {WEBVIEW_URL}")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        os.makedirs(PROFILE_DIR, exist_ok=True)
        chrome_options.add_argument(f"--user-data-dir={PROFILE_DIR}")
        chrome_options.add_argument(
            "--user-agent=Mozilla/5.0 (X11; Ubuntu; Linux x86_64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
        )
        # Evita che il browser si identifichi come "ChromeHeadless"
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option("useAutomationExtension", False)

        # Evita leak WebRTC
        chrome_options.add_argument("--force-webrtc-ip-handling-policy=disable_non_proxied_udp")
        chrome_options.add_argument("--disable-webrtc-encryption")
        chrome_options.add_argument("--no-rtc-ice-candidates")

        # Carica estensioni anti-fingerprint
        extension_paths = []
        os.makedirs(SELENIUM_EXTENSIONS_DIR, exist_ok=True)

        # Estensioni consigliate
        exts = {
            "fjkmabmdepjfammlbepikblgegnbabhp": "webrtc_control",
            "cjpalhdlnbpafiamejdnhcphjbkeiagm": "ublock_origin",
        }

        for ext_id, name in exts.items():
            path = _install_webstore_extension(ext_id, name)
            if path:
                extension_paths.append(path)

        # Eventuali estensioni fornite manualmente
        if os.path.isdir(SELENIUM_EXTENSIONS_DIR):
            for d in os.listdir(SELENIUM_EXTENSIONS_DIR):
                p = os.path.join(SELENIUM_EXTENSIONS_DIR, d)
                if os.path.isfile(os.path.join(p, "manifest.json")) and p not in extension_paths:
                    extension_paths.append(p)

        if extension_paths:
            chrome_options.add_argument("--load-extension=" + ",".join(extension_paths))
            print(f"[DEBUG/selenium] Estensioni caricate: {extension_paths}")

        self.driver = webdriver.Chrome(options=chrome_options)

        # Nasconde proprieta' webdriver e altre fingerprint
        stealth_js = """
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
            Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
            window.chrome = { runtime: {} };
        """
        try:
            self.driver.execute_cdp_cmd(
                "Page.addScriptToEvaluateOnNewDocument",
                {"source": stealth_js},
            )
            print("[DEBUG/selenium] Patch navigator properties applicata")
        except Exception as e:
            print(f"[ERROR/selenium] Patch webdriver fallita: {e}")
        self.driver.get("https://chat.openai.com")
        # Attende che la pagina sia caricata
        for _ in range(30):
            try:
                ready = self.driver.execute_script("return document.readyState")
                if ready == "complete":
                    break
            except Exception:
                pass
            time.sleep(1)
        # Simula piccolo movimento e tasto per far rilevare input umano
        try:
            ActionChains(self.driver).move_by_offset(5, 5).send_keys(Keys.SHIFT).perform()
            print("[DEBUG/selenium] Input umano simulato")
        except Exception:
            pass
        time.sleep(1)

    def _ensure_logged_in(self):
        try:
            current_url = self.driver.current_url
        except Exception:
            current_url = ""
        if current_url and ("login" in current_url or "auth0" in current_url):
            print("[DEBUG/selenium] Login richiesto, notifico l'utente")
            notify_owner(
                f"🔐 Login necessario. Apri {WEBVIEW_URL} per completare la procedura."
            )
            return False
        return True

    async def handle_incoming_message(self, bot, message, prompt_data):
        print("[DEBUG/selenium] Prompt ricevuto:", prompt_data)

        try:
            if self.driver is None:
                self._init_driver()
            if not self._ensure_logged_in():
                return

            # Vai nella chat corretta (puoi estendere questa logica)
            await asyncio.sleep(1)
            self.driver.get("https://chat.openai.com")
            await asyncio.sleep(1)
            try:
                ActionChains(self.driver).move_by_offset(3, 3).send_keys(Keys.SHIFT).perform()
                print("[DEBUG/selenium] Input umano simulato (handle_message)")
            except Exception:
                pass
            await asyncio.sleep(1)

            # Cerca l'elemento sidebar per verificare accesso
            try:
                self.driver.find_element(By.TAG_NAME, "aside")
            except NoSuchElementException:
                print("[DEBUG/selenium] Sidebar assente, notifica il proprietario")
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
        if self.driver is None:
            try:
                self._init_driver()
            except Exception as e:
                notify_owner(f"❌ Errore Selenium: {e}")

PLUGIN_CLASS = SeleniumChatGPTPlugin
