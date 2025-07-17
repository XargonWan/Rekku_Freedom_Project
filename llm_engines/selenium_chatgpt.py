import undetected_chromedriver as uc
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.common.exceptions import (
    NoSuchElementException,
    TimeoutException,
    ElementNotInteractableException,
    SessionNotCreatedException,
    WebDriverException,
)
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import json
import re
from typing import Dict, Optional
from collections import defaultdict
import threading
from core.ai_plugin_base import AIPluginBase
from core.notifier import notify_owner, set_notifier
from core.telegram_utils import safe_send
from core.logging_utils import log_debug, log_info, log_warning, log_error
import asyncio
import os
import subprocess
from core.chatgpt_link_store import ChatLinkStore
from core import recent_chats

# ---------------------------------------------------------------------------
# Constants

GRACE_PERIOD_SECONDS = 3
MAX_WAIT_TIMEOUT_SECONDS = 5 * 60  # hard ceiling

# Cache the last response per Telegram chat to avoid duplicates
previous_responses: Dict[int, str] = {}
response_cache_lock = threading.Lock()

# Persistent mapping between Telegram chats and ChatGPT conversations
chat_link_store = ChatLinkStore()
queue_paused = False


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
        "arguments[0].dispatchEvent(new KeyboardEvent('keydown', {bubbles: true}));"
        "arguments[0].dispatchEvent(new KeyboardEvent('keyup', {bubbles: true}));"
        )
    driver.execute_script(script, textarea, clean_text)

    actual = driver.execute_script("return arguments[0].innerText;", textarea) or ""
    log_debug(f"[DEBUG] Length actually present in textarea: {len(actual)}")
    if actual != clean_text:
        log_debug(
            f"[selenium][DEBUG] textarea mismatch: expected {len(clean_text)} chars, found {len(actual)}"
        )


def paste_and_send(textarea, prompt_text: str) -> None:
    """Robustly send ``prompt_text`` to ``textarea`` in chunks with retries."""
    import textwrap

    clean = strip_non_bmp(prompt_text)
    if len(clean) > 4000:
        clean = clean[:4000]

    chunks = textwrap.wrap(clean, 200)
    log_debug(f"[selenium] Sending prompt in {len(chunks)} chunks")

    for attempt in range(1, 4):
        if attempt > 1:
            log_warning(f"[selenium] send_keys retry {attempt}/3")
        try:
            textarea.send_keys(Keys.CONTROL + "a")
            textarea.send_keys(Keys.DELETE)
            time.sleep(0.2)

            for idx, chunk in enumerate(chunks, start=1):
                log_debug(
                    f"[selenium] -> chunk {idx}/{len(chunks)} ({len(chunk)} chars)"
                )
                textarea.send_keys(chunk)
                time.sleep(0.05)

            final_value = textarea.get_attribute("value") or ""
            log_debug(f"[selenium] Final textarea length {len(final_value)}")
            if final_value != clean:
                log_warning(
                    f"[selenium] textarea length mismatch: expected {len(clean)} got {len(final_value)}"
                )
            return
        except Exception as e:
            log_warning(f"[selenium] send_keys attempt {attempt} failed: {e}")

    # Fallback if all attempts failed
    log_warning("[selenium] Falling back to ActionChains")
    try:
        ActionChains(textarea._parent).click(textarea).send_keys(clean).perform()
    except Exception as e:  # pragma: no cover - best effort
        log_warning(f"[selenium] Fallback send failed: {e}")


# ---------------------------------------------------------------------------
# Queue utilities for sequential prompt processing

_prompt_queue: asyncio.Queue = asyncio.Queue()
_queue_lock = asyncio.Lock()
_queue_worker: asyncio.Task | None = None


def wait_for_markdown_block_to_appear(driver, prev_count: int, timeout: int = 10) -> bool:
    """Return ``True`` once a new markdown block appears."""
    end_time = time.time() + timeout
    while time.time() < end_time:
        try:
            count = len(driver.find_elements(By.CSS_SELECTOR, "div.markdown"))
            if count > prev_count:
                log_debug(f"[selenium] Markdown count {prev_count} -> {count}")
                return True
        except Exception as e:  # pragma: no cover - best effort
            log_warning(f"[selenium] Markdown wait error: {e}")
        time.sleep(0.5)
    log_warning("[selenium] Timeout waiting for response start")
    return False


def wait_until_response_stabilizes(
    driver: webdriver.Remote,
    max_total_wait: int = 300,
    no_change_grace: float = 3.5,
) -> str:
    """Return the last markdown text once its length stops growing."""
    selector = "div.markdown.prose"
    start = time.time()
    last_len = -1
    last_change = start
    final_text = ""

    while True:
        if time.time() - start >= max_total_wait:
            log_warning("[WARNING] Timeout while waiting for new response")
            return final_text

        try:
            elems = driver.find_elements(By.CSS_SELECTOR, selector)
            if not elems:
                time.sleep(0.5)
                continue
            text = elems[-1].text or ""
        except Exception as e:  # pragma: no cover - best effort
            log_warning(f"[selenium] Response wait error: {e}")
            time.sleep(0.5)
            continue

        current_len = len(text)
        changed = current_len != last_len
        log_debug(f"[DEBUG] len={current_len} changed={changed}")

        if changed:
            last_len = current_len
            last_change = time.time()
            final_text = text
        elif time.time() - last_change >= no_change_grace:
            elapsed = time.time() - start
            log_debug(
                f"[DEBUG] Response stabilized with length {current_len} after {elapsed:.1f}s"
            )
            return text

        time.sleep(0.5)



def _send_prompt_with_confirmation(textarea, prompt_text: str) -> None:
    """Send text and wait for ChatGPT to start replying."""
    driver = textarea._parent
    prev_blocks = len(driver.find_elements(By.CSS_SELECTOR, "div.markdown"))
    for attempt in range(1, 4):
        try:
            paste_and_send(textarea, prompt_text)
            textarea.send_keys(Keys.ENTER)
            if wait_for_markdown_block_to_appear(driver, prev_blocks):
                wait_until_response_stabilizes(driver)
                return
            log_warning(f"[selenium] No response after attempt {attempt}")
        except Exception as e:  # pragma: no cover - best effort
            log_warning(f"[selenium] Send attempt {attempt} failed: {e}")
    log_warning("[selenium] Fallback via ActionChains")
    try:
        ActionChains(driver).click(textarea).send_keys(prompt_text).send_keys(Keys.ENTER).perform()
        if wait_for_markdown_block_to_appear(driver, prev_blocks):
            wait_until_response_stabilizes(driver)
    except Exception as e:  # pragma: no cover - best effort
        log_warning(f"[selenium] Fallback send failed: {e}")


async def _queue_worker_loop() -> None:
    """Background worker that processes queued prompts sequentially."""
    global _queue_worker
    while not _prompt_queue.empty():
        textarea, text = await _prompt_queue.get()
        log_debug("[selenium] Dequeued prompt")
        async with _queue_lock:
            log_debug("[selenium] Send lock acquired")
            await asyncio.to_thread(_send_prompt_with_confirmation, textarea, text)
            log_debug("[selenium] Prompt completed")
        _prompt_queue.task_done()
        log_debug("[selenium] Task done")
    _queue_worker = None


async def enqueue_prompt(textarea, prompt_text: str) -> None:
    """Enqueue ``prompt_text`` for sequential sending to ChatGPT."""
    await _prompt_queue.put((textarea, prompt_text))
    log_debug(f"[selenium] Prompt enqueued (size={_prompt_queue.qsize()})")
    global _queue_worker
    if _queue_worker is None or _queue_worker.done():
        _queue_worker = asyncio.create_task(_queue_worker_loop())


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

# [FIX] helper to avoid Telegram message length limits
def _safe_notify(text: str) -> None:
    for i in range(0, len(text), 4000):
        chunk = text[i : i + 4000]
        log_debug(f"[selenium] Notifying chunk length {len(chunk)}")
        try:
            notify_owner(chunk)
        except Exception as e:  # pragma: no cover - best effort
            log_error(f"[selenium] notify_owner failed: {e}", e)

def _notify_gui(message: str = ""):
    """Send a notification with the VNC URL, optionally prefixed."""
    url = _build_vnc_url()
    text = f"{message} {url}".strip()
    log_debug(f"[selenium] Invio notifica VNC: {text}")
    _safe_notify(text)


def _extract_chat_id(url: str) -> Optional[str]:
    """Estrae l'ID della chat dall'URL di ChatGPT."""
    log_debug(f"[selenium][DEBUG] Extracting chat ID from URL: {url}")
    
    # Pattern più flessibili per diversi formati di URL ChatGPT
    patterns = [
        r"/chat/([^/?#]+)",           # Formato standard: /chat/uuid
        r"/c/([^/?#]+)",              # Formato alternativo: /c/uuid  
        r"chat\.openai\.com/chat/([^/?#]+)",  # URL completo
        r"chat\.openai\.com/c/([^/?#]+)"      # URL completo alternativo
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            chat_id = match.group(1)
            log_debug(f"[selenium][DEBUG] Extracted chat ID: {chat_id}")
            return chat_id
    
    log_debug(f"[selenium][DEBUG] No chat ID found in URL: {url}")
    return None


def _check_conversation_full(driver) -> bool:
    try:
        elems = driver.find_elements(By.CSS_SELECTOR, "div.text-token-text-error")
        for el in elems:
            text = (el.get_attribute("innerText") or "").strip()
            if "maximum length for this conversation" in text:
                return True
    except Exception as e:  # pragma: no cover - best effort
        log_warning(f"[selenium] overflow check failed: {e}")
    return False


def _open_new_chat(driver) -> None:
    try:
        # Prima prova a cliccare il pulsante new chat se è visibile
        try:
            btn = WebDriverWait(driver, 2).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "a[data-testid='new-chat-button']"))
            )
            btn.click()
            log_debug("[selenium] Clicked new-chat-button")
            return
        except TimeoutException:
            log_debug("[selenium] New chat button not visible, navigating to home")
            
        # Se non è visibile, vai alla home page e poi clicca
        driver.get("https://chat.openai.com")
        btn = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "a[data-testid='new-chat-button']"))
        )
        btn.click()
        log_debug("[selenium] Navigated to home and clicked new-chat-button")
    except Exception as e:
        log_warning(f"[selenium] New chat button not clicked: {e}")
        # Fallback: naviga direttamente alla home che dovrebbe creare una nuova chat
        driver.get("https://chat.openai.com")


def go_to_chat_by_path(driver, chat_path: str) -> bool:
    """Try to open a chat from the sidebar matching ``chat_path``."""
    try:
        xpath = f"//nav//a[span[contains(text(), '{chat_path}')]]"
        elem = WebDriverWait(driver, 3).until(
            EC.element_to_be_clickable((By.XPATH, xpath))
        )
        elem.click()
        log_debug(f"[selenium] Reused chat via path: {chat_path}")
        return True
    except Exception:
        log_debug(f"[selenium] Chat path not found: {chat_path}")
        return False


def wait_for_response_change(
    driver, previous_text: str, timeout: int = 30
) -> Optional[str]:
    """Return new markdown text once it stays unchanged for 2 seconds."""

    log_debug("🕓 Waiting for new markdown content...")

    try:
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "div.markdown"))
        )
    except TimeoutException:
        log_warning("❌ Timeout while waiting for new response")
        return None

    end_time = time.time() + timeout
    last_seen_text = previous_text
    last_change = time.time()

    while time.time() < end_time:
        try:
            elements = driver.find_elements(By.CSS_SELECTOR, "div.markdown")
            if not elements:
                time.sleep(0.5)
                continue

            latest_text = elements[-1].get_attribute("textContent") or ""
            latest_text = latest_text.strip()

            changed = latest_text != last_seen_text
            log_debug(
                f"[selenium][DEBUG] len={len(latest_text)} changed={changed}"
            )

            if changed:
                last_seen_text = latest_text
                last_change = time.time()
            else:
                if (
                    latest_text
                    and latest_text != previous_text
                    and time.time() - last_change >= 2
                ):
                    log_debug(
                        f"🟢 Response stabilized with length {len(latest_text)}"
                    )
                    log_debug(f"[selenium][DEBUG] final text: {latest_text[:120]}...")
                    return latest_text

        except Exception as e:
            log_warning(f"❌ Error during markdown check: {e}")

        time.sleep(0.5)

    log_warning("❌ Timeout while waiting for new response")
    return None


def process_prompt_in_chat(
    driver, chat_id: str | None, prompt_text: str, previous_text: str
) -> Optional[str]:
    """Send a prompt to a ChatGPT chat and return the newly generated text."""
    if chat_id:
        chat_url = f"https://chat.openai.com/chat/{chat_id}"
        log_debug(f"[selenium][STEP] Opening chat {chat_id} at {chat_url}")
        driver.get(chat_url)
        current_url = driver.current_url
        log_debug(f"[selenium][DEBUG] Current URL after navigation: {current_url}")
        if chat_id not in current_url:
            log_warning(f"[selenium][WARN] URL mismatch: expected {chat_id}, got {current_url}")
    else:
        log_debug("[selenium][STEP] Using currently open chat")
        log_debug(f"[selenium][DEBUG] Current URL: {driver.current_url}")

    try:
        textarea = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.ID, "prompt-textarea"))
        )
    except TimeoutException:
        log_error("[selenium][ERROR] prompt textarea not found")
        return None


    for attempt in range(1, 4):  # [FIX][retry] retry up to 3 times
        try:
            textarea.click()
            textarea.send_keys(Keys.CONTROL + "a")
            textarea.send_keys(Keys.DELETE)

            paste_and_send(textarea, prompt_text)

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
            # [FIX][wait] give ChatGPT up to 90s to show the markdown block
            WebDriverWait(driver, 90).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div.markdown"))
            )
        except TimeoutException:
            log_warning("[selenium][WARN] No response container appeared")
            response_text = ""
        else:
            try:
                response_text = wait_until_response_stabilizes(driver)
            except Exception as e:
                log_error(f"[selenium][ERROR] waiting for response failed: {e}", e)
                return None

        if response_text and response_text != previous_text:
            log_debug("📝 New response text extracted")
            return response_text.strip()

        log_warning(f"[selenium][retry] Empty response attempt {attempt}")
        time.sleep(2)

    # [FIX][retry] all attempts exhausted - capture screenshot and notify
    os.makedirs("screenshots", exist_ok=True)
    fname = f"screenshots/chat_{chat_id or 'unknown'}_no_response.png"
    try:
        driver.save_screenshot(fname)
        log_warning(f"[selenium] Saved screenshot to {fname}")
    except Exception as e:
        log_warning(f"[selenium] Failed to save screenshot: {e}")
    notify_owner(
        f"\u26A0\uFE0F No response received for chat_id={chat_id}. Screenshot: {fname}"
    )
    return None


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
        recent_chats.set_chat_path(chat_info.chat_id, new_title)
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
        paste_and_send(textarea, prompt_text)
        textarea.send_keys(Keys.ENTER)
    except Exception as e:
        log_error(f"[selenium][ERROR] failed to send prompt: {e}")
        return None

    previous_text = get_previous_response(chat_info.chat_id)
    log_debug("🔍 Waiting for response block...")
    try:
        response_text = wait_until_response_stabilizes(driver)
    except Exception as e:
        log_error(f"[selenium][ERROR] waiting for response failed: {e}")
        return None

    if not response_text or response_text == previous_text:
        log_debug("🟡 No new response, skipping")
        return None
    update_previous_response(chat_info.chat_id, response_text)
    log_debug("📝 New response text extracted")
    return response_text.strip()





class SeleniumChatGPTPlugin(AIPluginBase):
    # [FIX] shared locks per Telegram chat
    chat_locks: defaultdict[int, asyncio.Lock] = defaultdict(asyncio.Lock)
    def __init__(self, notify_fn=None):
        """Initialize the plugin without starting Selenium yet."""
        self.driver = None
        self._queue: asyncio.Queue = asyncio.Queue()
        self._worker_task = None
        self._notify_fn = notify_fn or notify_owner
        log_debug(f"[selenium] notify_fn passed: {bool(notify_fn)}")
        set_notifier(self._notify_fn)

    def cleanup(self):
        """Clean up resources when the plugin is stopped."""
        log_debug("[selenium] Starting cleanup...")
        
        # Stop the worker task
        if self._worker_task and not self._worker_task.done():
            self._worker_task.cancel()
            log_debug("[selenium] Worker task cancelled")
        
        # Close the driver
        if self.driver:
            try:
                self.driver.quit()
                log_debug("[selenium] Chrome driver closed")
            except Exception as e:
                log_warning(f"[selenium] Failed to close driver: {e}")
            finally:
                self.driver = None
        
        # Kill any remaining Chrome processes
        try:
            subprocess.run(["pkill", "-f", "chrome"], capture_output=True, text=True)
            subprocess.run(["pkill", "-f", "chromedriver"], capture_output=True, text=True)
            log_debug("[selenium] Killed remaining Chrome processes")
        except Exception as e:
            log_debug(f"[selenium] Failed to kill processes: {e}")
        
        log_debug("[selenium] Cleanup completed")

    async def start(self):
        """Start the background worker loop."""
        log_debug("[selenium] \U0001F7E2 start() called")
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
            log_debug("[selenium] [STEP] Initializing Chrome driver with undetected-chromedriver")

            # Clean up any leftover processes and files from previous runs
            self._cleanup_chrome_remnants()

            # Ensure DISPLAY is set
            if not os.environ.get("DISPLAY"):
                os.environ["DISPLAY"] = ":1"
                log_debug("[selenium] DISPLAY not set, defaulting to :1")

            # Try multiple times with increasing delays
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    log_debug(f"[selenium] Initialization attempt {attempt + 1}/{max_retries}")
                    
                    # Create Chrome options optimized for container environments
                    options = uc.ChromeOptions()
                    
                    # Essential options for Docker containers
                    essential_args = [
                        "--no-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-setuid-sandbox",
                        "--disable-gpu",
                        "--disable-software-rasterizer",
                        "--disable-extensions",
                        "--disable-web-security",
                        "--start-maximized",
                        "--no-first-run",
                        "--disable-default-apps",
                        "--disable-popup-blocking",
                        "--disable-infobars",
                        "--disable-background-timer-throttling",
                        "--disable-backgrounding-occluded-windows",
                        "--disable-renderer-backgrounding",
                        "--memory-pressure-off",
                        "--disable-features=VizDisplayCompositor",
                        "--log-level=3",
                        "--disable-logging",
                        "--remote-debugging-port=0",  # Let Chrome choose port
                        "--disable-background-mode",
                        "--disable-default-browser-check",
                        "--disable-hang-monitor",
                        "--disable-prompt-on-repost",
                        "--disable-sync",
                        "--metrics-recording-only",
                        "--no-default-browser-check",
                        "--safebrowsing-disable-auto-update",
                        "--disable-client-side-phishing-detection"
                    ]
                    
                    for arg in essential_args:
                        options.add_argument(arg)
                    
                    # Use persistent profile directory to maintain login sessions
                    # This preserves ChatGPT login and other site sessions across restarts
                    profile_dir = os.path.expanduser("~/.config/google-chrome-rekku")
                    os.makedirs(profile_dir, exist_ok=True)
                    options.add_argument(f"--user-data-dir={profile_dir}")
                    
                    # Clear any existing driver cache
                    import tempfile
                    import shutil
                    uc_cache_dir = os.path.join(tempfile.gettempdir(), 'undetected_chromedriver')
                    if os.path.exists(uc_cache_dir):
                        shutil.rmtree(uc_cache_dir, ignore_errors=True)
                        log_debug("[selenium] Cleared undetected-chromedriver cache")
                    
                    # Try with automatic configuration first
                    self.driver = uc.Chrome(
                        options=options,
                        headless=False,
                        use_subprocess=False,
                        version_main=None,  # Auto-detect Chrome version
                        suppress_welcome=True,
                        log_level=3,
                        driver_executable_path=None,  # Let UC handle chromedriver
                        browser_executable_path=None,  # Let UC find Chrome
                        user_data_dir=profile_dir
                    )
                    log_debug("[selenium] ✅ Chrome successfully initialized with undetected-chromedriver")
                    return  # Success, exit retry loop
                    
                except Exception as e:
                    log_warning(f"[selenium] Attempt {attempt + 1} failed: {e}")
                    
                    # Clean up before next attempt
                    if self.driver:
                        try:
                            self.driver.quit()
                        except:
                            pass
                        self.driver = None
                    
                    self._cleanup_chrome_remnants()
                    
                    if attempt < max_retries - 1:
                        delay = (attempt + 1) * 2  # 2, 4, 6 seconds
                        log_debug(f"[selenium] Waiting {delay}s before next attempt...")
                        time.sleep(delay)
                    else:
                        # Final attempt with explicit Chrome binary
                        log_debug("[selenium] Final attempt with explicit Chrome binary path...")
                        try:
                            chrome_binary = "/usr/bin/google-chrome-stable"
                            if os.path.exists(chrome_binary):
                                # Create fresh ChromeOptions for fallback attempt
                                fallback_options = uc.ChromeOptions()
                                for arg in essential_args:
                                    fallback_options.add_argument(arg)
                                fallback_options.add_argument(f"--user-data-dir={profile_dir}")
                                
                                self.driver = uc.Chrome(
                                    options=fallback_options,
                                    headless=False,
                                    use_subprocess=False,
                                    version_main=None,
                                    suppress_welcome=True,
                                    log_level=3,
                                    browser_executable_path=chrome_binary,
                                    user_data_dir=profile_dir
                                )
                                log_debug("[selenium] ✅ Chrome initialized with explicit binary path")
                                return
                            else:
                                raise Exception("Chrome binary not found")
                                
                        except Exception as e2:
                            log_error(f"[selenium] ❌ All initialization attempts failed: {e2}")
                            _notify_gui(f"❌ Selenium error: {e2}. Check graphics environment.")
                            raise SystemExit(1)

    def _cleanup_chrome_remnants(self):
        """Clean up Chrome processes and lock files from previous runs while preserving login sessions."""
        try:
            # Kill any existing Chrome processes
            subprocess.run(["pkill", "-f", "chrome"], capture_output=True, text=True)
            subprocess.run(["pkill", "-f", "chromedriver"], capture_output=True, text=True)
            time.sleep(1)  # Wait for processes to terminate
            log_debug("[selenium] Killed existing Chrome processes")
        except Exception as e:
            log_debug(f"[selenium] Failed to kill Chrome processes: {e}")

        try:
            # Remove lock files from Chrome profile directories (preserves session data)
            import glob
            profile_patterns = [
                os.path.expanduser("~/.config/google-chrome*"),
                "/tmp/.com.google.Chrome*",
                "/tmp/chrome_*"
            ]
            
            for pattern in profile_patterns:
                for profile_dir in glob.glob(pattern):
                    # Only remove lock files, NOT the entire profile directory
                    lock_files = [
                        os.path.join(profile_dir, "SingletonLock"),
                        os.path.join(profile_dir, "Default", "SingletonLock"),
                        os.path.join(profile_dir, "lockfile"),
                    ]
                    
                    for lock_file in lock_files:
                        if os.path.exists(lock_file):
                            try:
                                os.remove(lock_file)
                                log_debug(f"[selenium] Removed lock file: {lock_file}")
                            except Exception as e:
                                log_debug(f"[selenium] Could not remove {lock_file}: {e}")
            
            # Remove only temporary profile directories (those with timestamp suffix)
            # This preserves the persistent profile but removes error-created temp ones
            temp_patterns = [
                os.path.expanduser("~/.config/google-chrome-[0-9]*"),
                "/tmp/.com.google.Chrome*",
                "/tmp/chrome_*"
            ]
            
            import shutil
            for pattern in temp_patterns:
                for temp_dir in glob.glob(pattern):
                    try:
                        shutil.rmtree(temp_dir, ignore_errors=True)
                        log_debug(f"[selenium] Removed temporary directory: {temp_dir}")
                    except Exception as e:
                        log_debug(f"[selenium] Could not remove {temp_dir}: {e}")
                                
        except Exception as e:
            log_debug(f"[selenium] Lock file cleanup failed: {e}")

    # [FIX] ensure the WebDriver session is alive before use
    def _get_driver(self):
        """Return a valid WebDriver, recreating it if the session is dead."""
        if self.driver is None:
            self._init_driver()
        else:
            try:
                # simple command to verify the session is still alive
                self.driver.execute_script("return 1")
            except WebDriverException:
                log_warning("[selenium] WebDriver session expired, recreating")
                try:
                    self.driver.quit()
                except Exception:
                    pass
                self.driver = None
                self._init_driver()
        return self.driver

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
        lock = SeleniumChatGPTPlugin.chat_locks.get(message.chat_id)
        if lock and lock.locked():
            log_debug(f"[selenium] Chat {message.chat_id} busy, waiting")
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
            while queue_paused:
                await asyncio.sleep(1)
            log_debug(
                f"[selenium] [WORKER] Processing chat_id={message.chat_id} message_id={message.message_id}"
            )
            try:
                lock = SeleniumChatGPTPlugin.chat_locks[message.chat_id]  # [FIX]
                async with lock:
                    log_debug(f"[selenium] Lock acquired for chat {message.chat_id}")
                    await self._process_message(bot, message, prompt)
                    log_debug(f"[selenium] Lock released for chat {message.chat_id}")
            except Exception as e:
                log_error("[selenium] Worker error", e)
                _notify_gui(f"❌ Selenium error: {e}. Open UI")
            finally:
                self._queue.task_done()
                log_debug("[selenium] [WORKER] Task completed")

    async def _process_message(self, bot, message, prompt):
        """Send the prompt to ChatGPT and forward the response."""
        log_debug(f"[selenium][STEP] processing prompt: {prompt}")

        for attempt in range(2):
            driver = self._get_driver()
            if not self._ensure_logged_in():
                return

            log_debug("[selenium][STEP] ensuring ChatGPT is accessible")

            thread_id = getattr(message, "message_thread_id", None)
            chat_id = chat_link_store.get_link(message.chat_id, thread_id)
            prompt_text = json.dumps(prompt, ensure_ascii=False)
            if not chat_id:
                path = recent_chats.get_chat_path(message.chat_id)
                if path and go_to_chat_by_path(driver, path):
                    chat_id = _extract_chat_id(driver.current_url)
                    if chat_id:  # [FIX] save and notify about recovered chat
                        chat_link_store.save_link(message.chat_id, thread_id, chat_id)
                        _safe_notify(
                            f"\u26A0\uFE0F Couldn't find ChatGPT conversation for Telegram chat_id={message.chat_id}, thread_id={thread_id}.\n"
                            f"A new ChatGPT chat has been created: {chat_id}"
                        )

            log_debug(f"[selenium][DEBUG] Chat ID from store: {chat_id}")
            log_debug(f"[selenium][DEBUG] Telegram chat_id: {message.chat_id}, thread_id: {thread_id}")

            # Solo se non abbiamo un chat_id specifico, andiamo alla home
            if not chat_id:
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
                if chat_id:
                    previous = get_previous_response(message.chat_id)
                    response_text = process_prompt_in_chat(driver, chat_id, prompt_text, previous)
                    if response_text:
                        update_previous_response(message.chat_id, response_text)
                else:
                    _open_new_chat(driver)
                    response_text = rename_and_send_prompt(driver, message, prompt_text)
                    new_chat_id = _extract_chat_id(driver.current_url)
                    log_debug(f"[selenium][DEBUG] New chat created, extracted ID: {new_chat_id}")
                    log_debug(f"[selenium][DEBUG] Current URL: {driver.current_url}")
                    if new_chat_id:
                        chat_link_store.save_link(message.chat_id, thread_id, new_chat_id)
                        log_debug(f"[selenium][DEBUG] Saved link: {message.chat_id}/{thread_id} -> {new_chat_id}")
                        chat_url = f"https://chat.openai.com/chat/{new_chat_id}"
                        driver.get(chat_url)
                        _safe_notify(
                            f"\u26A0\uFE0F Couldn't find ChatGPT conversation for Telegram chat_id={message.chat_id}, thread_id={thread_id}.\n"
                            f"A new ChatGPT chat has been created: {new_chat_id}"
                        )
                    else:
                        log_warning("[selenium][WARN] Failed to extract chat ID from URL")

                if _check_conversation_full(driver):
                    current_id = chat_id or _extract_chat_id(driver.current_url)
                    if current_id:
                        chat_link_store.mark_full(current_id)
                    global queue_paused
                    queue_paused = True
                    _open_new_chat(driver)
                    response_text = rename_and_send_prompt(driver, message, prompt_text)
                    new_chat_id = _extract_chat_id(driver.current_url)
                    if new_chat_id:
                        chat_link_store.save_link(message.chat_id, thread_id, new_chat_id)
                    queue_paused = False

                if not response_text:
                    response_text = "⚠️ No response received"

                await safe_send(
                    bot,
                    chat_id=message.chat_id,
                    text=response_text,
                    reply_to_message_id=message.message_id,
                )  # [FIX][telegram retry]
                log_debug(f"[selenium][STEP] response forwarded to {message.chat_id}")
                return

            except WebDriverException as e:
                log_error("[selenium] WebDriver error", e)
                try:
                    self.driver.quit()
                except Exception:
                    pass
                self.driver = None
                if attempt == 0:
                    log_debug("[selenium] Retrying after driver restart")
                    continue
                _notify_gui(f"❌ Selenium error: {e}. Open UI")
                return
            except Exception as e:
                log_error(f"[selenium][ERROR] failed to process message: {e}", e)
                _notify_gui(f"❌ Selenium error: {e}. Open UI")
                return


    def get_supported_models(self):
        return []  # nessun modello per ora

    def get_rate_limit(self):
        return (80, 10800, 0.5)

    def set_notify_fn(self, fn):
        self._notify_fn = fn
        set_notifier(fn)
        if self.driver is None:
            try:
                self._init_driver()
            except Exception as e:
                log_error("[selenium] set_notify_fn initialization error", e)
                _notify_gui(f"❌ Selenium error: {e}. Open UI")

PLUGIN_CLASS = SeleniumChatGPTPlugin

