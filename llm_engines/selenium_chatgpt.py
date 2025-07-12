import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.common.exceptions import (
    NoSuchElementException,
    TimeoutException,
    ElementNotInteractableException,
)
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import json
import time
import pyperclip
from typing import Dict
from core.ai_plugin_base import AIPluginBase
from core.notifier import notify_owner, set_notifier
from core.logging_utils import log_debug, log_info, log_warning, log_error
import asyncio
import os
import subprocess

# Cache the last response per Telegram chat to avoid duplicates
previous_responses: Dict[int, str] = {}


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


def wait_for_response(driver, before_count: int, timeout: int = 60):
    """Wait for a new ChatGPT response identified by a new copy button.

    Args:
        driver: Selenium WebDriver instance.
        before_count: Number of copy buttons visible before waiting.
        timeout: Maximum time to wait in seconds.

    Returns:
        The parent WebElement containing the response text or None if timeout.
    """
    log_debug(f"[selenium][STEP] wait_for_response starting (count={before_count})")
    try:
        WebDriverWait(driver, timeout).until(
            lambda d: len(
                d.find_elements(By.CSS_SELECTOR, "button[data-testid='copy-turn-action-button']")
            )
            > before_count
        )
        buttons = driver.find_elements(By.CSS_SELECTOR, "button[data-testid='copy-turn-action-button']")
        new_btn = buttons[-1]
        log_debug("[selenium][STEP] new copy button detected")
        parent = new_btn.find_element(By.XPATH, "./ancestor::div[contains(@class,'group')]")
        return parent
    except TimeoutException:
        log_warning("[selenium][ERROR] wait_for_response timeout")
        return None
    except Exception as e:
        log_error(f"[selenium][ERROR] wait_for_response failed: {e}", e)
        return None





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
        """Send the prompt to ChatGPT and forward the response."""
        log_debug(f"[selenium][STEP] processing prompt: {prompt}")

        if self.driver is None:
            self._init_driver()
        if not self._ensure_logged_in():
            return

        driver = self.driver

        log_debug("[selenium][STEP] opening chat.openai.com")
        driver.get("https://chat.openai.com")

        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "main"))
            )
        except TimeoutException:
            log_warning("[selenium][ERROR] ChatGPT UI failed to load")
            _notify_gui("❌ Selenium error: ChatGPT UI not ready. Open UI")
            return

        # === Rename conversation tab ===
        try:
            chat_name = message.chat.title or getattr(message.chat, "full_name", "") or str(message.chat_id)
            is_group = message.chat.type in ("group", "supergroup")
            chat_emoji = "💬" if is_group else "📩"
            thread_part = (
                f"/Thread {message.message_thread_id}" if getattr(message, "message_thread_id", None) else ""
            )
            new_title = f"⚙️{chat_emoji} Telegram/{chat_name}{thread_part} - 1"
            log_debug(f"[selenium][STEP] renaming chat to: {new_title}")

            options_btn = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "button[data-testid='history-item-0-options']"))
            )
            options_btn.click()

            rename_btn = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(text(),'Rename')]"))
            )
            rename_btn.click()

            rename_input = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "textarea"))
            )
            rename_input.send_keys(Keys.CONTROL + "a")
            rename_input.send_keys(Keys.BACK_SPACE)
            rename_input.send_keys(new_title)
            rename_input.send_keys(Keys.ENTER)
        except Exception as e:
            log_warning(f"[selenium][ERROR] rename failed: {e}")

        # === Send prompt ===
        try:
            before_count = len(
                driver.find_elements(By.CSS_SELECTOR, "button[data-testid='copy-turn-action-button']")
            )
            textarea = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.ID, "prompt-textarea"))
            )
            textarea.click()
            prompt_text = json.dumps(prompt, ensure_ascii=False)
            textarea.send_keys(prompt_text)

            send_btn = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.ID, "composer-submit-button"))
            )
            send_btn.click()
            log_debug("[selenium][STEP] prompt submitted")
        except ElementNotInteractableException as e:
            log_warning(f"[selenium][ERROR] textarea not interactable: {e}")
            return
        except Exception as e:
            log_error(f"[selenium][ERROR] failed to submit prompt: {e}", e)
            return

        log_debug("[selenium][STEP] Waiting 10 seconds to allow ChatGPT to generate response")
        time.sleep(10)

        # === Wait for response ===
        response_text = ""
        try:
            container = wait_for_response(driver, before_count)
            if container is None:
                response_text = "⚠️ No response received"
            else:
                copy_buttons = driver.find_elements(By.CSS_SELECTOR, "button[data-testid='copy-turn-action-button']")
                if not copy_buttons:
                    log_error("[selenium][ERROR] No copy buttons found (data-testid='copy-turn-action-button')")
                    raise RuntimeError("No response copy button detected")
                log_debug(f"[selenium][INFO] {len(copy_buttons)} response copy buttons found")
                try:
                    copy_buttons[-1].click()
                    log_debug("[selenium][STEP] Last copy button clicked successfully")
                except Exception as e:
                    log_error(f"[selenium][ERROR] Failed to click copy button: {e}")
                    raise
                try:
                    response_text = pyperclip.paste()
                    log_debug(f"[selenium][STEP] Clipboard read successful, content length: {len(response_text)}")
                except Exception as e:
                    log_error(f"[selenium][ERROR] Clipboard read failed: {e}")
                    raise
                previous = previous_responses.get(message.chat_id)
                if response_text == previous:
                    log_warning(
                        f"[selenium][WARN] Received response is identical to cached one for chat_id={message.chat_id}"
                    )
                    raise TimeoutError("No new response detected")
                previous_responses[message.chat_id] = response_text
                log_debug(f"[selenium][STEP] Response stored in cache for chat_id={message.chat_id}")
            if not response_text:
                response_text = "⚠️ Empty response"
        except Exception as e:
            log_error(f"[selenium][ERROR] failed to read response: {e}", e)
            response_text = "⚠️ Error reading response"

        # === Forward to Telegram ===
        try:
            await bot.send_message(
                chat_id=message.chat_id,
                text=response_text,
                reply_to_message_id=message.message_id,
            )
            log_debug(f"[selenium][STEP] response forwarded to {message.chat_id}")
        except Exception as e:
            log_error(f"[selenium][ERROR] failed to send Telegram message: {e}", e)


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

