import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.common.exceptions import (
    NoSuchElementException,
    TimeoutException,
    ElementNotInteractableException,
)
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import json
from typing import Dict, Optional
import threading
from core.ai_plugin_base import AIPluginBase
from core.notifier import notify_owner, set_notifier
from core.logging_utils import log_debug, log_info, log_warning, log_error
import asyncio
import os
import subprocess

# Cache the last response per Telegram chat to avoid duplicates
previous_responses: Dict[int, str] = {}
response_cache_lock = threading.Lock()


def get_previous_response(chat_id: int) -> str:
    """Return the cached response for the given Telegram chat."""
    with response_cache_lock:
        return previous_responses.get(chat_id, "")


def update_previous_response(chat_id: int, new_text: str) -> None:
    """Store ``new_text`` for ``chat_id`` inside the cache."""
    with response_cache_lock:
        previous_responses[chat_id] = new_text


def has_response_changed(chat_id: int, new_text: str) -> bool:
    """Return True if ``new_text`` is different from the cached value."""
    with response_cache_lock:
        old = previous_responses.get(chat_id)
    return old != new_text


def strip_non_bmp(text: str) -> str:
    """Return ``text`` with characters above the BMP removed."""
    return "".join(ch for ch in text if ord(ch) <= 0xFFFF)


def _send_text_to_textarea(driver, textarea, text: str) -> None:
    """Inject ``text`` into the ChatGPT prompt area via JavaScript."""
    clean_text = strip_non_bmp(text)
    log_debug(f"[DEBUG] Length before sending: {len(clean_text)}")
    preview = clean_text[:120] + ("..." if len(clean_text) > 120 else "")
    log_debug(f"[DEBUG] Text preview: {preview}")

    script = (
        "arguments[0].focus();"
        "arguments[0].innerText = arguments[1];"
        "arguments[0].dispatchEvent(new Event('input', {bubbles: true}));"
    )
    driver.execute_script(script, textarea, clean_text)

    actual = driver.execute_script("return arguments[0].innerText;", textarea) or ""
    log_debug(f"[DEBUG] Length actually present in textarea: {len(actual)}")
    if actual != clean_text:
        log_error(
            f"[ERROR] Text truncated: expected {len(clean_text)} chars, found {len(actual)}"
        )


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


def wait_for_response_change(
    driver, previous_text: str, timeout: int = 40
) -> Optional[str]:
    """Poll the last markdown block until its text differs from ``previous_text``."""

    log_debug("🕓 Waiting for new markdown content...")
    end_time = time.time() + timeout

    try:
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "div.markdown"))
        )
    except TimeoutException:
        log_warning("❌ Timeout while waiting for new response")
        return None

    while time.time() < end_time:
        try:
            elements = driver.find_elements(By.CSS_SELECTOR, "div.markdown")
            if elements:
                latest_text = elements[-1].get_attribute("textContent").strip()
                if latest_text and latest_text != previous_text:
                    log_debug("🟢 New markdown found and different from previous.")
                    return latest_text
                log_debug("🟡 Still same text, waiting...")
        except Exception as e:
            log_warning(f"❌ Error during markdown check: {e}")
        time.sleep(1)

    log_warning("❌ Timeout while waiting for new response")
    return None


def process_prompt_in_chat(
    driver, chat_id: str | None, prompt_text: str, previous_text: str
) -> Optional[str]:
    """Send a prompt to a ChatGPT chat and return the newly generated text."""
    if chat_id:
        log_debug(f"[selenium][STEP] Opening chat {chat_id}")
        driver.get(f"https://chat.openai.com/chat/{chat_id}")
    else:
        log_debug("[selenium][STEP] Using currently open chat")

    try:
        textarea = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.ID, "prompt-textarea"))
        )
    except TimeoutException:
        log_error("[selenium][ERROR] prompt textarea not found")
        return None


    try:
        textarea.click()
        textarea.send_keys(Keys.CONTROL + "a")
        textarea.send_keys(Keys.DELETE)

        clean_text = strip_non_bmp(prompt_text)
        textarea.send_keys(clean_text)

        current_value = textarea.get_attribute("value") or ""
        if current_value != clean_text:
            log_warning("[selenium][WARN] Textarea mismatch, retrying with ActionChains")
            ActionChains(driver).click(textarea).send_keys(clean_text).perform()
            current_value = textarea.get_attribute("value") or ""
            if current_value != clean_text:
                log_error("[selenium][ERROR] Prompt text truncated after send_keys")

        submit_btn = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.ID, "composer-submit-button"))
        )
        submit_btn.click()
        log_debug("📨 Prompt sent")
    except ElementNotInteractableException as e:
        log_warning(f"[selenium][ERROR] textarea not interactable: {e}")
        return None
    except Exception as e:
        log_error(f"[selenium][ERROR] failed to send prompt: {e}", e)
        return None

    log_debug("🔍 Waiting for response block...")
    try:
        response_text = wait_for_response_change(driver, previous_text)
    except Exception as e:
        log_error(f"[selenium][ERROR] waiting for response failed: {e}", e)
        return None

    if response_text is None:
        return None
    if not response_text or response_text == previous_text:
        log_debug("🟡 No new response, skipping")
        return None
    log_debug("📝 New response text extracted")
    return response_text.strip()


def rename_and_send_prompt(driver, chat_info, prompt_text: str) -> Optional[str]:
    """Rename the active chat and send ``prompt_text``. Return the new response."""
    try:
        chat_name = (
            chat_info.chat.title
            or getattr(chat_info.chat, "full_name", "")
            or str(chat_info.chat_id)
        )
        is_group = chat_info.chat.type in ("group", "supergroup")
        emoji = "💬" if is_group else "💌"
        thread = (
            f"/Thread {chat_info.message_thread_id}" if getattr(chat_info, "message_thread_id", None) else ""
        )
        new_title = f"⚙️{emoji} Telegram/{chat_name}{thread} - 1"
        log_debug(f"[selenium][STEP] renaming chat to: {new_title}")

        options_btn = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "button[data-testid='history-item-0-options']"))
        )
        options_btn.click()
        script = (
            "const buttons = Array.from(document.querySelectorAll('[data-testid=\"share-chat-menu-item\"]'));"
            " const rename = buttons.find(b => b.innerText.trim() === 'Rename');"
            " if (rename) rename.click();"
        )
        driver.execute_script(script)
        rename_input = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "[role='textbox']"))
        )
        rename_input.clear()
        rename_input.send_keys(strip_non_bmp(new_title))
        rename_input.send_keys(Keys.ENTER)
        log_debug("[DEBUG] Rename field found and edited")
    except Exception as e:
        log_warning(f"[selenium][ERROR] rename failed: {e}")

    try:
        textarea = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.ID, "prompt-textarea"))
        )
    except TimeoutException:
        log_error("[selenium][ERROR] prompt textarea not found")
        return None

    try:
        _send_text_to_textarea(driver, textarea, prompt_text)
        textarea.send_keys(Keys.ENTER)
    except Exception as e:
        log_error(f"[selenium][ERROR] failed to send prompt: {e}")
        return None

    previous_text = get_previous_response(chat_info.chat_id)
    log_debug("🔍 Waiting for response block...")
    try:
        response_text = wait_for_response_change(driver, previous_text)
    except Exception as e:
        log_error(f"[selenium][ERROR] waiting for response failed: {e}")
        return None

    if not response_text:
        log_debug("🟡 No new response, skipping")
        return None
    update_previous_response(chat_info.chat_id, response_text)
    log_debug("📝 New response text extracted")
    return response_text.strip()





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

        log_debug("[selenium][STEP] opening ChatGPT")

        try:
            driver.get("https://chat.openai.com")
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "main"))
            )
        except TimeoutException:
            log_warning("[selenium][ERROR] ChatGPT UI failed to load")
            _notify_gui("❌ Selenium error: ChatGPT UI not ready. Open UI")
            return

        try:
            prompt_text = json.dumps(prompt, ensure_ascii=False)
            response_text = rename_and_send_prompt(driver, message, prompt_text)
        except Exception as e:
            log_error(f"[selenium][ERROR] failed to send prompt: {e}", e)
            response_text = "⚠️ Error reading response"
        if not response_text:
            response_text = "⚠️ No response received"

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

