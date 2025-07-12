import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
import json
from core.ai_plugin_base import AIPluginBase
from core.notifier import notify_owner, set_notifier
from core.logging_utils import log_debug, log_info, log_warning, log_error
import asyncio
import os
import subprocess


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
            log_warning(f"[selenium] Unable to determine host: {e}")
        if not host:
            host = "localhost"
    url = f"http://{host}:{port}/vnc.html"
    log_debug(f"[selenium] VNC URL built: {url}")
    return url

def _notify_gui(message: str = ""):
    """Send a notification with the VNC URL, optionally prefixed."""
    url = _build_vnc_url()
    text = f"{message} {url}".strip()
    log_debug(f"[selenium] Invio notifica VNC: {text}")
    try:
        notify_owner(text)
    except Exception as e:
        log_error(f"[selenium] notify_owner failed: {e}", e)





class SeleniumChatGPTPlugin(AIPluginBase):
    def __init__(self, notify_fn=None):
        """Initialize the plugin without starting Selenium yet."""
        self.driver = None
        self._queue: asyncio.Queue = asyncio.Queue()
        self._worker_task = None
        if notify_fn:
            set_notifier(notify_fn)

    async def start(self):
        """Start the background worker loop."""
        log_debug("[selenium] start() invoked")
        if self.is_worker_running():
            log_debug("[selenium] Worker already running")
            return
        if self._worker_task is not None and self._worker_task.done():
            log_warning("[selenium] Previous worker task ended, restarting")
        self._worker_task = asyncio.create_task(
            self._worker_loop(), name="selenium_worker"
        )
        self._worker_task.add_done_callback(self._handle_worker_done)
        log_debug("[selenium] Worker task created")

    def is_worker_running(self) -> bool:
        return self._worker_task is not None and not self._worker_task.done()

    def _handle_worker_done(self, fut: asyncio.Future):
        if fut.cancelled():
            log_warning("[selenium] Worker task cancelled")
        elif fut.exception():
            log_error(
                f"[selenium] Worker task crashed: {fut.exception()}", fut.exception()
            )
        # Attempt restart if needed
        try:
            loop = asyncio.get_running_loop()
            if loop.is_running():
                loop.create_task(self.start())
        except RuntimeError:
            pass

    def _init_driver(self):
        if self.driver is None:
            log_debug("[selenium] [STEP] Initializing Chrome driver")
            chrome_path = "/usr/bin/google-chrome-stable"
            profile_dir = os.path.expanduser("/home/rekku/.ucd-profile")
            os.makedirs(profile_dir, exist_ok=True)

            options = uc.ChromeOptions()
            options.add_argument("--disable-blink-features=AutomationControlled")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-setuid-sandbox")
            options.add_argument("--disable-dev-shm-usage")

            try:
                self.driver = uc.Chrome(
                    options=options,
                    headless=False,
                    browser_executable_path=chrome_path,
                    user_data_dir=profile_dir,
                )
                log_debug("[selenium] Chrome driver started")
            except Exception as e:
                log_error(f"[selenium] Failed to start Chrome: {e}", e)
                _notify_gui(f"❌ Errore Selenium: {e}. Apri")
                raise SystemExit(1)

    def _ensure_logged_in(self):
        try:
            current_url = self.driver.current_url
        except Exception:
            current_url = ""
        log_debug(f"[selenium] [STEP] Checking login state at {current_url}")
        if current_url and ("login" in current_url or "auth0" in current_url):
            log_debug("[selenium] Login richiesto, notifico l'utente")
            _notify_gui("🔐 Login necessario. Apri")
            return False
        log_debug("[selenium] Logged in and ready")
        return True

    async def handle_incoming_message(self, bot, message, prompt):
        """Queue the message to be processed sequentially."""
        user_id = message.from_user.id if message.from_user else "unknown"
        text = message.text or ""
        log_debug(
            f"[selenium] [ENTRY] chat_id={message.chat_id} user_id={user_id} text={text!r}"
        )
        await self._queue.put((bot, message, prompt))
        log_debug("[selenium] Message queued for processing")
        if self._queue.qsize() > 10:
            log_warning(
                f"[selenium] Queue size high ({self._queue.qsize()}). Worker might be stalled"
            )

    async def _worker_loop(self):
        log_debug("[selenium] Worker loop started")
        while True:
            bot, message, prompt = await self._queue.get()
            log_debug(
                f"[selenium] [WORKER] Processing chat_id={message.chat_id} message_id={message.message_id}"
            )
            try:
                await self._process_message(bot, message, prompt)
            except Exception as e:
                log_error("[selenium] Worker error", e)
                _notify_gui(f"❌ Errore Selenium: {e}. Apri")
            finally:
                self._queue.task_done()
                log_debug("[selenium] [WORKER] Task completed")

    async def _process_message(self, bot, message, prompt):
        log_debug(f"[selenium] Prompt ricevuto: {prompt}")

        if self.driver is None:
            self._init_driver()
        if not self._ensure_logged_in():
            return
        log_debug("[selenium] Browser ready for prompt")

        # Vai nella chat corretta (puoi estendere questa logica)
        await asyncio.sleep(1)
        log_debug("[selenium] Navigating to https://chat.openai.com")
        self.driver.get("https://chat.openai.com")
        await asyncio.sleep(1)
        try:
            self.driver.find_element(By.TAG_NAME, "aside")
        except NoSuchElementException:
            log_debug("[selenium] Sidebar missing, notifying owner")
            _notify_gui("❌ Selenium error: Sidebar not found. Open UI")
            return
        try:
            textarea = WebDriverWait(self.driver, 10).until(
                lambda d: d.find_element(By.TAG_NAME, "textarea")
            )
            textarea.clear()

            prompt_text = json.dumps(prompt, ensure_ascii=False)
            textarea.send_keys(prompt_text)
            textarea.send_keys(Keys.ENTER)

            prev_count = len(self.driver.find_elements(By.CSS_SELECTOR, ".markdown"))

            WebDriverWait(self.driver, 30).until(
                lambda d: len(d.find_elements(By.CSS_SELECTOR, ".markdown")) > prev_count
            )

            bubbles = self.driver.find_elements(By.CSS_SELECTOR, ".markdown")
            response_text = bubbles[-1].text if bubbles else ""

            if response_text:
                await bot.send_message(
                    chat_id=message.chat_id,
                    text=response_text
                )
            else:
                await bot.send_message(
                    chat_id=message.chat_id,
                    text="⚠️ No response received from ChatGPT."
                )
            log_debug(
                f"[selenium] [RESPONSE] Sent to chat_id={message.chat_id}"
            )
        except TimeoutException:
            log_warning("[selenium] Timeout waiting for ChatGPT response")
            await bot.send_message(
                chat_id=message.chat_id,
                text="⚠️ Timeout waiting for ChatGPT."
            )
        except Exception as e:
            log_error(f"[selenium] Error during interaction: {e}", e)
            await bot.send_message(
                chat_id=message.chat_id,
                text="⚠️ Selenium interaction error."
            )


    def get_supported_models(self):
        return []  # nessun modello per ora

    def set_notify_fn(self, fn):
        set_notifier(fn)
        if self.driver is None:
            try:
                self._init_driver()
            except Exception as e:
                log_error("[selenium] set_notify_fn initialization error", e)
                _notify_gui(f"❌ Errore Selenium: {e}. Apri")

PLUGIN_CLASS = SeleniumChatGPTPlugin

