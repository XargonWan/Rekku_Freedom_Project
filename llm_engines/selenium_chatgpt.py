import nodriver as uc
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
import platform
import traceback
from typing import Dict, Optional
from collections import defaultdict
import threading
from core.ai_plugin_base import AIPluginBase
from core.notifier import notify_trainer, set_notifier
from core.telegram_utils import safe_send
from core.logging_utils import log_debug, log_info, log_warning, log_error
import asyncio
import os
import subprocess
from core import recent_chats
from core.db import get_conn
import aiomysql


class NodriverElementWrapper:
    """Wrapper to make nodriver elements compatible with Selenium API"""
    
    def __init__(self, nodriver_element, tab):
        self._element = nodriver_element
        self._tab = tab
        
    async def clear(self):
        """Clear element content"""
        log_debug("[selenium] NodriverElementWrapper.clear() called")
        try:
            if not self._element:
                log_error("[selenium] clear() called with None element")
                return
            if not self._tab:
                log_error("[selenium] clear() called with None tab")
                return
            
            # For textarea, use JavaScript to clear
            log_debug("[selenium] Clearing textarea using JavaScript")
            await self._tab.evaluate("""
                const element = document.getElementById('prompt-textarea');
                if (element) {
                    element.value = '';
                    element.dispatchEvent(new Event('input', { bubbles: true }));
                    console.log('Textarea cleared successfully');
                } else {
                    console.log('Textarea element not found');
                }
            """)
            log_debug("[selenium] clear() completed successfully")
        except Exception as e:
            log_error(f"[selenium] Failed to clear element: {e}")
            raise
            
    async def send_keys(self, text):
        """Send keys to element"""
        log_debug(f"[selenium] NodriverElementWrapper.send_keys() called with text: {text!r}")
        try:
            if not self._element:
                log_error("[selenium] send_keys() called with None element")
                return
            if not self._tab:
                log_error("[selenium] send_keys() called with None tab")
                return
                
            if text == Keys.ENTER:
                # Handle Enter key - submit the form
                log_debug("[selenium] Sending ENTER key via JavaScript")
                await self._tab.evaluate("""
                    const element = document.getElementById('prompt-textarea');
                    if (element) {
                        const form = element.closest('form');
                        if (form) {
                            const submitBtn = form.querySelector('button[type="submit"], button:not([type])');
                            if (submitBtn) {
                                console.log('Clicking submit button');
                                submitBtn.click();
                            } else {
                                console.log('Submit button not found, simulating Enter keypress');
                                element.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', code: 'Enter', bubbles: true}));
                            }
                        }
                    } else {
                        console.log('Textarea element not found for ENTER');
                    }
                """)
            else:
                # Send text to the element
                log_debug(f"[selenium] Sending text to textarea: {text[:50]}...")
                escaped_text = text.replace("'", "\\'").replace('"', '\\"').replace('\n', '\\n')
                await self._tab.evaluate(f"""
                    const element = document.getElementById('prompt-textarea');
                    if (element) {{
                        element.value = '{escaped_text}';
                        element.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        element.dispatchEvent(new Event('change', {{ bubbles: true }}));
                        console.log('Text sent to textarea, length:', element.value.length);
                    }} else {{
                        console.log('Textarea element not found for text input');
                    }}
                """)
            log_debug("[selenium] send_keys() completed successfully")
        except Exception as e:
            log_error(f"[selenium] Failed to send keys: {e}")
            raise
            
    async def click(self):
        """Click the element"""
        try:
            # Use nodriver's click method if available
            await self._element.click()
        except Exception as e:
            log_warning(f"[selenium] Direct click failed: {e}")
            # Fallback to JavaScript click
            try:
                await self._tab.evaluate("""
                    const element = arguments[0];
                    if (element && element.click) {
                        element.click();
                    }
                """, self._element)
            except Exception as e2:
                log_error(f"[selenium] JavaScript click also failed: {e2}")

    async def get_attribute(self, name):
        """Get element attribute"""
        try:
            return await self._element.get_attribute(name)
        except Exception as e:
            log_warning(f"[selenium] Failed to get attribute {name}: {e}")
            return None

    @property
    def text(self):
        """Get element text - this should be awaitable in practice"""
        try:
            return self._element.text
        except Exception as e:
            log_warning(f"[selenium] Failed to get text: {e}")
            return ""


class NodriverSeleniumWrapper:
    """Wrapper class to make nodriver compatible with Selenium API patterns used in the code"""
    
    def __init__(self, nodriver_tab):
        log_debug("[selenium] 🔧 Creating NodriverSeleniumWrapper...")
        log_debug(f"[selenium] 📋 nodriver_tab type: {type(nodriver_tab)}")
        try:
            self._tab = nodriver_tab  # This is actually a Tab, not Browser
            log_debug("[selenium] ✅ NodriverSeleniumWrapper created successfully")
        except Exception as e:
            log_error(f"[selenium] ❌ Failed to create NodriverSeleniumWrapper: {e}")
            raise
        
    async def get(self, url):
        """Navigate to URL"""
        await self._tab.get(url)
        
    async def find_elements(self, by_type, selector):
        """Find elements by various selector types"""
        css_selector = self._convert_selector(by_type, selector)
        if css_selector:
            try:
                elements = await self._tab.select_all(css_selector, timeout=2)
                # Wrap each element to make them Selenium-compatible
                if elements:
                    return [NodriverElementWrapper(elem, self._tab) for elem in elements]
                return []
            except Exception:
                return []
        else:
            log_warning(f"[selenium] Unsupported selector type: {by_type}")
            return []
            
    async def find_element(self, by_type, selector):
        """Find single element by various selector types"""
        log_debug(f"[selenium] find_element called with by_type: {by_type}, selector: {selector}")
        css_selector = self._convert_selector(by_type, selector)
        log_debug(f"[selenium] Converted to CSS selector: {css_selector}")
        if css_selector:
            try:
                log_debug(f"[selenium] Searching for element with CSS: {css_selector}")
                element = await self._tab.select(css_selector, timeout=2)
                log_debug(f"[selenium] Element found: {element is not None}")
                if element:
                    # Wrap the nodriver element to make it Selenium-compatible
                    log_debug("[selenium] Creating NodriverElementWrapper")
                    wrapper = NodriverElementWrapper(element, self._tab)
                    log_debug("[selenium] Wrapper created successfully")
                    return wrapper
                else:
                    log_debug("[selenium] Element not found")
                    return None
            except Exception as e:
                log_warning(f"[selenium] Exception while finding element: {e}")
                return None
        else:
            log_warning(f"[selenium] Unsupported selector type: {by_type}")
            return None
            
    def _convert_selector(self, by_type, selector):
        """Convert Selenium selector types to CSS selectors"""
        if by_type == By.CSS_SELECTOR:
            return selector
        elif by_type == By.ID:
            return f"#{selector}"
        elif by_type == By.TAG_NAME:
            return selector
        elif by_type == By.CLASS_NAME:
            return f".{selector}"
        elif by_type == By.XPATH:
            # XPATH is more complex to convert, we'll try to use nodriver's xpath method
            # For now, log warning and return None for CSS conversion
            log_warning(f"[selenium] XPATH selector will be handled separately: {selector}")
            return None
        elif by_type == By.NAME:
            return f"[name='{selector}']"
        else:
            log_warning(f"[selenium] Unknown selector type: {by_type}")
            return None
            
    @property
    def current_url(self):
        """Get current URL - in nodriver this is a property of the tab"""
        return self._tab.url
        
    async def execute_script(self, script):
        """Execute JavaScript"""
        return await self._tab.evaluate(script)
        
    async def quit(self):
        """Close browser"""
        await self._tab.close()
        
    async def stop(self):
        """Stop the tab"""
        await self._tab.close()
        
    async def save_screenshot(self, filename):
        """Save screenshot"""
        return await self._tab.save_screenshot(filename)


class ChatLinkStore:
    def __init__(self):
        self._table_ensured = False
        # Don't use asyncio.run() in __init__, it breaks the event loop
        # We'll ensure the table exists on first use instead
        pass

    def _normalize_thread_id(self, message_thread_id: Optional[int | str]) -> str:
        """Return ``message_thread_id`` as a string suitable for storage.

        The value ``"0"`` is used to represent chats without a thread."""

        return str(message_thread_id) if message_thread_id is not None else "0"

    async def _ensure_table(self) -> None:
        if self._table_ensured:
            return
            
        conn = await get_conn()
        try:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS chatgpt_links (
                        -- chat_id is stored as text to allow non-numeric identifiers
                        chat_id TEXT NOT NULL,
                        -- message_thread_id is stored as text; "0" means no thread
                        message_thread_id TEXT,
                        link VARCHAR(2048),
                        -- specify key length for TEXT columns
                        PRIMARY KEY (chat_id(255), message_thread_id(255))
                    )
                    """
                )
                self._table_ensured = True
        finally:
            conn.close()

    async def get_link(
        self, chat_id: int | str, message_thread_id: Optional[int | str]
    ) -> Optional[str]:
        await self._ensure_table()  # Ensure table exists before use
        normalized_thread = self._normalize_thread_id(message_thread_id)
        log_debug(
            f"[chatlink] get_link normalized thread_id={normalized_thread}"
        )
        conn = await get_conn()
        try:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    "SELECT link FROM chatgpt_links WHERE chat_id = %s AND message_thread_id = %s",
                    (str(chat_id), normalized_thread),
                )
                row = await cur.fetchone()
                chat = row["link"] if row else None
                log_debug(
                    f"[chatlink] get_link {chat_id}/{normalized_thread} -> {chat}"
                )
                return chat
        finally:
            conn.close()

    async def save_link(
        self, chat_id: int | str, message_thread_id: Optional[int | str], link: str
    ) -> None:
        await self._ensure_table()  # Ensure table exists before use
        normalized_thread = self._normalize_thread_id(message_thread_id)
        log_debug(
            f"[chatlink] save_link normalized thread_id={normalized_thread}"
        )
        conn = await get_conn()
        try:
            async with conn.cursor() as cur:
                await cur.execute(
                    "REPLACE INTO chatgpt_links (chat_id, message_thread_id, link) VALUES (%s, %s, %s)",
                    (str(chat_id), normalized_thread, link),
                )
                await conn.commit()
        finally:
            conn.close()
        log_debug(f"[chatlink] Saved mapping {chat_id}/{normalized_thread} -> {link}")

    async def remove(
        self, chat_id: str | int, message_thread_id: Optional[int | str]
    ) -> bool:
        """Remove mapping for given Telegram chat."""
        await self._ensure_table()  # Ensure table exists before use
        normalized_thread = self._normalize_thread_id(message_thread_id)
        log_debug(
            f"[chatlink] remove normalized thread_id={normalized_thread}"
        )
        conn = await get_conn()
        try:
            async with conn.cursor() as cur:
                result = await cur.execute(
                    """
                    DELETE FROM chatgpt_links
                    WHERE chat_id = %s AND message_thread_id = %s
                    """,
                    (str(chat_id), normalized_thread),
                )
                await conn.commit()
                rows_deleted = result > 0
        finally:
            conn.close()

        if rows_deleted:
            log_debug(
                f"[chatlink] Removed link for chat_id={chat_id}, message_thread_id={normalized_thread}"
            )
        else:
            log_debug(
                f"[chatlink] No link found for chat_id={chat_id}, message_thread_id={normalized_thread}"
            )
        return rows_deleted

# ---------------------------------------------------------------------------
# Constants

GRACE_PERIOD_SECONDS = 3
MAX_WAIT_TIMEOUT_SECONDS = 5 * 60  # hard ceiling

# Cache the last response per Telegram chat to avoid duplicates
previous_responses: Dict[str, str] = {}
response_cache_lock = threading.Lock()

# Persistent mapping between Telegram chats and ChatGPT conversations
chat_link_store = ChatLinkStore()
queue_paused = False


def get_previous_response(chat_id: str) -> str:
    """Return the cached response for the given Telegram chat."""
    with response_cache_lock:
        return previous_responses.get(chat_id, "")


def update_previous_response(chat_id: str, new_text: str) -> None:
    """Store ``new_text`` for ``chat_id`` inside the cache."""
    with response_cache_lock:
        previous_responses[chat_id] = new_text


def has_response_changed(chat_id: str, new_text: str) -> bool:
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
            # Only log mismatch if significant (not just empty vs non-empty due to timing)
            if final_value != clean and len(final_value) > 0 and abs(len(final_value) - len(clean)) > 10:
                log_debug(f"[selenium] Textarea content mismatch: expected {len(clean)} chars, got {len(final_value)} chars")
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


async def wait_until_response_stabilizes_async(
    driver,
    max_total_wait: int = 300,
    no_change_grace: float = 3.5,
) -> str:
    """Return the last markdown text once its length stops growing (async version for nodriver)."""
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
            elems = await driver.find_elements(By.CSS_SELECTOR, selector)
            if not elems:
                await asyncio.sleep(0.5)
                continue
            # Get text from the last element
            text = ""
            if elems:
                # For nodriver, we might need to get text differently
                try:
                    text = await elems[-1].get_attribute('innerText') or ""
                except:
                    try:
                        text = elems[-1].text or ""
                    except:
                        text = ""
        except Exception as e:  # pragma: no cover - best effort
            log_warning(f"[selenium] Response wait error: {e}")
            await asyncio.sleep(0.5)
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

        await asyncio.sleep(0.5)



def _send_prompt_with_confirmation(textarea, prompt_text: str) -> None:
    """Send text and wait for ChatGPT to start replying."""
    driver = textarea._parent
    prev_blocks = len(driver.find_elements(By.CSS_SELECTOR, "div.markdown"))
    log_debug(f"[selenium][STEP] Initial markdown block count: {prev_blocks}")
    for attempt in range(1, 4):
        try:
            log_debug(f"[selenium][STEP] Attempt {attempt} to send prompt")
            paste_and_send(textarea, prompt_text)
            textarea.send_keys(Keys.ENTER)
            log_debug(f"[selenium][STEP] Prompt sent, waiting for response")
            if wait_for_markdown_block_to_appear(driver, prev_blocks):
                log_debug(f"[selenium][STEP] New markdown block detected")
                wait_until_response_stabilizes(driver)
                log_debug(f"[selenium][STEP] Response stabilized")
                return
            log_warning(f"[selenium] No response after attempt {attempt}")
        except Exception as e:  # pragma: no cover - best effort
            log_warning(f"[selenium] Send attempt {attempt} failed: {e}")
    log_warning("[selenium] Fallback via ActionChains")
    try:
        ActionChains(driver).click(textarea).send_keys(prompt_text).send_keys(Keys.ENTER).perform()
        log_debug(f"[selenium][STEP] Fallback ActionChains used to send prompt")
        if wait_for_markdown_block_to_appear(driver, prev_blocks):
            log_debug(f"[selenium][STEP] New markdown block detected after fallback")
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
            from core.config import TRAINER_ID

            notify_trainer(TRAINER_ID, chunk)
        except Exception as e:  # pragma: no cover - best effort
            log_error(f"[selenium] notify_trainer failed: {repr(e)}", e)

def _notify_gui(message: str = ""):
    """Send a notification with the VNC URL, optionally prefixed."""
    url = _build_vnc_url()
    text = f"{message} {url}".strip()
    log_debug(f"[selenium] Invio notifica VNC: {text}")
    _safe_notify(text)


def _extract_chat_id(url: str) -> Optional[str]:
    """Extracts the chat ID from the ChatGPT URL."""
    log_debug(f"[selenium][DEBUG] Extracting chat ID from URL: {url}")

    if not url or not isinstance(url, str):
        log_error("[selenium][ERROR] Invalid URL provided for chat ID extraction.")
        return None

    # More flexible patterns for different ChatGPT URL formats
    patterns = [
        r"/chat/([^/?#]+)",           # Standard format: /chat/uuid
        r"/c/([^/?#]+)",              # Alternative format: /c/uuid  
        r"chat\\.openai\\.com/chat/([^/?#]+)",  # Full URL
        r"chat\\.openai\\.com/c/([^/?#]+)"      # Alternative full URL
    ]

    for pattern in patterns:
        log_debug(f"[selenium][DEBUG] Trying pattern: {pattern}")
        match = re.search(pattern, url)
        if match:
            chat_id = match.group(1)
            log_debug(f"[selenium][DEBUG] Extracted chat ID: {chat_id}")
            return chat_id

    log_error("[selenium][ERROR] No chat ID could be extracted from the URL.")
    return None


async def _check_conversation_full(driver) -> bool:
    try:
        elems = await driver.find_elements(By.CSS_SELECTOR, "div.text-token-text-error")
        for el in elems:
            try:
                text = await el.get_attribute("innerText") or ""
                text = text.strip()
                if "maximum length for this conversation" in text:
                    return True
            except:
                # Fallback to text property if get_attribute fails
                try:
                    text = (el.text or "").strip()
                    if "maximum length for this conversation" in text:
                        return True
                except:
                    pass
    except Exception as e:  # pragma: no cover - best effort
        log_warning(f"[selenium] overflow check failed: {e}")
    return False


async def _open_new_chat(driver) -> None:
    """Navigate to ChatGPT home to create a new chat with retries."""
    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            log_debug(f"[selenium] Attempt {attempt}/{max_retries} to navigate to ChatGPT home")
            await driver.get("https://chat.openai.com")
            log_debug("[selenium] Successfully navigated to ChatGPT home")
            return
        except Exception as e:
            log_warning(f"[selenium] Attempt {attempt} failed: {e}")
            if attempt < max_retries:
                await asyncio.sleep(2 * attempt)  # Exponential backoff
            else:
                log_error("[selenium] All attempts to navigate to ChatGPT home failed")
                raise


async def is_chat_archived(driver, chat_id: str) -> bool:
    """Check if a ChatGPT chat is archived."""
    try:
        chat_url = f"https://chat.openai.com/chat/{chat_id}"
        await driver.get(chat_url)
        # Note: WebDriverWait doesn't work with nodriver, we need to implement our own wait
        # For now, we'll use a simple timeout and check manually
        import time
        start_time = time.time()
        timeout = 5
        while time.time() - start_time < timeout:
            try:
                elements = await driver.find_elements(By.XPATH, "//div[contains(text(), 'This conversation is archived')]")
                if elements:
                    log_warning("[selenium] Chat is archived.")
                    return True
            except:
                pass
            await asyncio.sleep(0.5)
        log_debug("[selenium] Chat is not archived.")
        return False
    except Exception as e:
        log_error(f"[selenium] Error checking if chat is archived: {repr(e)}")
        return False

# Update process_prompt_in_chat to use the new functions
async def process_prompt_in_chat(
    driver, chat_id: str | None, prompt_text: str, previous_text: str
) -> Optional[str]:
    """Send a prompt to a ChatGPT chat and return the newly generated text."""
    if chat_id and await is_chat_archived(driver, chat_id):
        chat_id = None  # Mark chat as invalid

    if not chat_id:
        log_debug("[selenium] Creating a new chat")
        await _open_new_chat(driver)
        # Chat ID will be extracted later from the URL after sending the prompt

    # Some UI experiments may block the textarea with a "I prefer this response"
    # dialog. Dismiss it if present before looking for the textarea.
    try:
        # For nodriver, we need to implement our own wait for elements
        start_time = time.time()
        prefer_btn = None
        while time.time() - start_time < 2:  # 2 second timeout
            try:
                prefer_btn = await driver.find_element(By.CSS_SELECTOR, "[data-testid='paragen-prefer-response-button']")
                if prefer_btn:
                    break
            except:
                pass
            await asyncio.sleep(0.1)
        
        if prefer_btn:
            await prefer_btn.click()
            await asyncio.sleep(2)
    except Exception as e:  # pragma: no cover - best effort
        log_warning(f"[selenium] Failed to click prefer-response button: {e}")

    try:
        # Wait for textarea to be available
        log_debug("[selenium] Starting to wait for textarea...")
        start_time = time.time()
        textarea = None
        while time.time() - start_time < 10:  # 10 second timeout
            try:
                log_debug(f"[selenium] Attempting to find textarea (elapsed: {time.time() - start_time:.1f}s)")
                textarea = await driver.find_element(By.ID, "prompt-textarea")
                if textarea:
                    log_debug("[selenium] Textarea found successfully!")
                    break
                else:
                    log_debug("[selenium] find_element returned None")
            except Exception as search_error:
                log_debug(f"[selenium] find_element raised exception: {search_error}")
            await asyncio.sleep(0.5)
        
        if not textarea:
            log_error("[selenium][ERROR] prompt textarea not found after 10 seconds")
            return None
        else:
            log_debug(f"[selenium] Textarea found, type: {type(textarea)}")
    except Exception as e:
        log_error(f"[selenium][ERROR] Failed to find textarea: {e}")
        return None

    prompt_sent_successfully = False
    for attempt in range(1, 4):  # Retry up to 3 times
        try:
            log_debug(f"[selenium] Attempt {attempt}/3: Starting to send prompt")
            log_debug(f"[selenium] Prompt text length: {len(prompt_text)}")
            
            log_debug("[selenium] Calling textarea.clear()...")
            await textarea.clear()
            log_debug("[selenium] textarea.clear() completed")
            
            log_debug("[selenium] Calling textarea.send_keys() with prompt text...")
            await textarea.send_keys(prompt_text)
            log_debug("[selenium] textarea.send_keys() with text completed")
            
            log_debug("[selenium] Calling textarea.send_keys() with ENTER...")
            await textarea.send_keys(Keys.ENTER)
            log_debug("[selenium] textarea.send_keys() with ENTER completed")
            
            log_debug("[selenium] Prompt sent successfully, breaking from retry loop")
            prompt_sent_successfully = True
            break  # Success, exit retry loop
            
        except Exception as e:
            log_warning(f"[selenium][retry] Failed to send prompt on attempt {attempt}: {e}")
            log_warning(f"[selenium][retry] Exception type: {type(e).__name__}")
            import traceback
            log_debug(f"[selenium][retry] Full traceback: {traceback.format_exc()}")
            await asyncio.sleep(2)
            continue

    # Only wait for response if prompt was sent successfully
    if prompt_sent_successfully:
        log_debug("🔍 Waiting for response block...")
        try:
            # Note: wait_until_response_stabilizes also needs to be updated for nodriver
            response_text = await wait_until_response_stabilizes_async(driver)
        except Exception as e:
            log_warning(f"[selenium][WARN] Error while waiting for response: {e}")
            response_text = None
            
        if response_text and response_text != previous_text:
            # If this was a new chat (no chat_id initially), extract and save the new chat ID
            if not chat_id:
                current_url = driver.current_url
                if hasattr(current_url, '__await__'):
                    current_url = await current_url
                new_chat_id = _extract_chat_id(current_url)
                if new_chat_id:
                    log_debug(f"[selenium] New chat ID extracted after response: {new_chat_id}")
                    # This will be used by the calling function to save the link
            return response_text.strip()
        else:
            log_warning("[selenium] No valid response received after successful prompt send")
    else:
        log_error("[selenium] Failed to send prompt after all retry attempts")

    os.makedirs("screenshots", exist_ok=True)
    fname = f"screenshots/chat_{chat_id or 'unknown'}_no_response.png"
    try:
        await driver.save_screenshot(fname)
        log_warning(f"[selenium] Saved screenshot to {fname}")
    except Exception as e:
        log_warning(f"[selenium] Failed to save screenshot: {e}")
    from core.config import TRAINER_ID

    notify_trainer(
        TRAINER_ID,
        f"\u26A0\uFE0F No response received for chat_id={chat_id}. Screenshot: {fname}"
    )
    return None


# TODO: Chat renaming logic - currently commented out due to unreliable ChatGPT UI changes
# This functionality needs to be reimplemented when ChatGPT's interface stabilizes
# def rename_and_send_prompt(driver, chat_info, prompt_text: str) -> Optional[str]:
#     """Rename the active chat and send ``prompt_text``. Return the new response."""
#     try:
#         chat_name = (
#             chat_info.chat.title
#             or getattr(chat_info.chat, "full_name", "")
#             or str(chat_info.chat_id)
#         )
#         is_group = chat_info.chat.type in ("group", "supergroup")
#         emoji = "💬" if is_group else "💌"
#         thread = (
#             f"/Thread {chat_info.message_thread_id}" if getattr(chat_info, "message_thread_id", None) else ""
#         )
#         new_title = f"⚙️{emoji} Telegram/{chat_name}{thread} - 1"
#         log_debug(f"[selenium][STEP] renaming chat to: {new_title}")
# 
#         options_btn = WebDriverWait(driver, 5).until(
#             EC.element_to_be_clickable((By.CSS_SELECTOR, "button[data-testid='history-item-0-options']"))
#         )
#         options_btn.click()
#         script = (
#             "const buttons = Array.from(document.querySelectorAll('[data-testid=\"share-chat-menu-item\"]'));"
#             " const rename = buttons.find(b => b.innerText.trim() === 'Rename');"
#             " if (rename) rename.click();"
#         )
#         driver.execute_script(script)
#         rename_input = WebDriverWait(driver, 5).until(
#             EC.element_to_be_clickable((By.CSS_SELECTOR, "[role='textbox']"))
#         )
#         rename_input.clear()
#         rename_input.send_keys(strip_non_bmp(new_title))
#         rename_input.send_keys(Keys.ENTER)
#         log_debug("[DEBUG] Rename field found and edited")
#         recent_chats.set_chat_path(chat_info.chat_id, new_title)
#     except Exception as e:
#         log_warning(f"[selenium][ERROR] rename failed: {e}")
# 
#     try:
#         textarea = WebDriverWait(driver, 10).until(
#             EC.element_to_be_clickable((By.ID, "prompt-textarea"))
#         )
#     except TimeoutException:
#         log_error("[selenium][ERROR] prompt textarea not found")
#         return None
# 
#     try:
#         paste_and_send(textarea, prompt_text)
#         textarea.send_keys(Keys.ENTER)
#     except Exception as e:
#         log_error(f"[selenium][ERROR] failed to send prompt: {repr(e)}")
#         return None
# 
#     previous_text = get_previous_response(chat_info.chat_id)
#     log_debug("🔍 Waiting for response block...")
#     try:
#         response_text = wait_until_response_stabilizes(driver)
#     except Exception as e:
#         log_error(f"[selenium][ERROR] waiting for response failed: {repr(e)}")
#         return None
# 
#     if not response_text or response_text == previous_text:
#         log_debug("🟡 No new response, skipping")
#         return None
#     update_previous_response(chat_info.chat_id, response_text)
#     log_debug("📝 New response text extracted")
#     return response_text.strip()





class SeleniumChatGPTPlugin(AIPluginBase):
    # [FIX] shared locks per Telegram chat
    chat_locks: defaultdict[int, asyncio.Lock] = defaultdict(asyncio.Lock)
    def __init__(self, notify_fn=None):
        """Initialize the plugin without starting Selenium yet."""
        log_debug("[selenium] 🚀 Starting plugin initialization...")
        
        try:
            log_debug("[selenium] 🔧 Setting up basic attributes...")
            self.driver = None
            self._browser = None  # Store browser reference for cleanup
            self._queue: asyncio.Queue = asyncio.Queue()
            self._worker_task = None
            self._notify_fn = notify_fn or notify_trainer
            log_debug(f"[selenium] ✅ Basic attributes set. notify_fn passed: {bool(notify_fn)}")
            
            log_debug(f"[selenium] 🎯 Using nodriver (supports all architectures)")
            set_notifier(self._notify_fn)
            log_debug("[selenium] ✅ Plugin initialization completed successfully")
            
        except Exception as e:
            log_error(f"[selenium] ❌ Plugin initialization failed: {e}")
            import traceback
            log_error(f"[selenium] 📜 Traceback: {traceback.format_exc()}")
            raise

    async def cleanup(self):
        """Clean up resources when the plugin is stopped."""
        log_debug("[selenium] Starting cleanup...")
        
        # Stop the worker task
        if self._worker_task and not self._worker_task.done():
            self._worker_task.cancel()
            log_debug("[selenium] Worker task cancelled")
        
        # Close the driver and browser
        if self.driver:
            try:
                await self.driver.stop()
                log_debug("[selenium] nodriver tab closed")
            except Exception as e:
                log_warning(f"[selenium] Failed to close tab: {e}")
            finally:
                self.driver = None
                
        # Close the browser instance
        if self._browser:
            try:
                await self._browser.stop()
                log_debug("[selenium] nodriver browser closed")
            except Exception as e:
                log_warning(f"[selenium] Failed to close browser: {e}")
            finally:
                self._browser = None
        
        # Kill any remaining browser processes
        try:
            subprocess.run(["pkill", "-f", "chrome"], capture_output=True, text=True)
            subprocess.run(["pkill", "-f", "chromium"], capture_output=True, text=True)
            log_debug("[selenium] Killed remaining browser processes")
        except Exception as e:
            log_debug(f"[selenium] Failed to kill processes: {e}")
        
        log_debug("[selenium] Cleanup completed")

    async def stop(self):
        """Cancel worker task and run cleanup."""  # [FIX]
        if self._worker_task:
            self._worker_task.cancel()
            await asyncio.gather(self._worker_task, return_exceptions=True)
        await self.cleanup()

    async def start(self):
        """Start the background worker loop."""
        log_debug("[selenium] 🟢 start() called - beginning plugin startup")
        
        if self.is_worker_running():
            log_debug("[selenium] ⚠️ Worker already running, skipping start")
            return
            
        if self._worker_task is not None and self._worker_task.done():
            log_warning("[selenium] 🔄 Previous worker task ended, restarting")
            
        log_debug("[selenium] 🚀 Creating new worker task...")
        self._worker_task = asyncio.create_task(
            self._worker_loop(), name="selenium_worker"
        )
        self._worker_task.add_done_callback(self._handle_worker_done)
        log_debug("[selenium] ✅ Worker task created successfully")

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

    async def _init_driver(self):
        """Initialize nodriver browser (supports all architectures including ARM64)"""
        if self.driver is None:
            log_debug("[selenium] 🚀 [STEP] Initializing browser with nodriver (multi-architecture support)")

            # Clean up any leftover processes and files from previous runs
            log_debug("[selenium] 🧹 Cleaning up previous browser remnants...")
            self._cleanup_chrome_remnants()
            log_debug("[selenium] ✅ Cleanup completed")

            # Ensure DISPLAY is set
            display = os.environ.get("DISPLAY")
            log_debug(f"[selenium] 🖥️ Current DISPLAY: {display}")
            if not display:
                os.environ["DISPLAY"] = ":1"
                log_debug("[selenium] 📺 DISPLAY not set, defaulting to :1")

            # Try multiple times with increasing delays
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    log_debug(f"[selenium] 🎯 Initialization attempt {attempt + 1}/{max_retries}")
                    
                    # Configure nodriver options
                    log_debug("[selenium] ⚙️ Configuring browser arguments...")
                    browser_args = [
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
                        "--remote-debugging-port=0",
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
                    
                    # Use persistent profile directory to maintain login sessions
                    # Always use Chromium (google-chrome is symlinked to chromium)
                    log_debug("[selenium] 🔍 Using Chromium browser...")
                    profile_dir = os.path.expanduser("~/.config/chromium-rekku")
                    log_debug("[selenium] 🔧 Using Chromium profile directory")
                    
                    log_debug(f"[selenium] 📁 Profile directory: {profile_dir}")
                    os.makedirs(profile_dir, exist_ok=True)
                    browser_args.append(f"--user-data-dir={profile_dir}")
                    
                    # Initialize nodriver with configuration
                    log_debug("[selenium] 🚀 Starting nodriver browser...")
                    browser = await uc.start(
                        headless=False,
                        browser_args=browser_args,
                        user_data_dir=profile_dir
                    )
                    log_debug("[selenium] ✅ nodriver browser created successfully")
                    
                    # Get the first tab (page) from nodriver
                    log_debug("[selenium] 🔄 Getting the first tab...")
                    tab = await browser.get('about:blank')  # This creates/gets a tab
                    log_debug("[selenium] ✅ Tab obtained successfully")
                    
                    # Wrap nodriver tab to maintain Selenium API compatibility
                    log_debug("[selenium] 🔄 Creating Selenium API wrapper...")
                    self.driver = NodriverSeleniumWrapper(tab)
                    log_debug("[selenium] ✅ Wrapper created successfully")
                    
                    # Store browser reference for cleanup
                    self._browser = browser
                    
                    log_debug("[selenium] 🎉 Browser successfully initialized with nodriver")
                    return  # Success, exit retry loop
                    
                except Exception as e:
                    log_warning(f"[selenium] ⚠️ Attempt {attempt + 1} failed: {e}")
                    log_debug(f"[selenium] 📜 Exception details: {type(e).__name__}: {str(e)}")
                    
                    # Handle specific Python shutdown error
                    if "sys.meta_path is None" in str(e) or "Python is likely shutting down" in str(e):
                        log_warning("[selenium] 🔚 Python shutdown detected, skipping browser initialization")
                        return None
                    
                    # Clean up before next attempt
                    log_debug("[selenium] 🧹 Cleaning up failed attempt...")
                    if self.driver:
                        try:
                            await self.driver.stop()
                            log_debug("[selenium] ✅ Driver stopped")
                        except Exception as cleanup_error:
                            log_debug(f"[selenium] ⚠️ Driver cleanup failed: {cleanup_error}")
                        self.driver = None
                    
                    self._cleanup_chrome_remnants()
                    
                    if attempt < max_retries - 1:
                        delay = (attempt + 1) * 2  # 2, 4, 6 seconds
                        log_debug(f"[selenium] ⏱️ Waiting {delay}s before next attempt...")
                        await asyncio.sleep(delay)
                    else:
                        log_error(f"[selenium] ❌ All initialization attempts failed: {e}")
                        _notify_gui(f"❌ Browser error: {e}. Check graphics environment.")
                        log_error("[selenium] 💥 Raising SystemExit due to browser initialization failure")
                        raise SystemExit(1)

    def _cleanup_chrome_remnants(self):
        """Clean up Chromium processes and leftover lock files.
        Note: google-chrome is symlinked to chromium."""
        log_debug("[selenium] 🧹 Starting Chrome cleanup process...")
        
        try:
            # Kill Chromium processes (google-chrome is symlinked to chromium)
            log_debug("[selenium] 🔪 Killing chrome processes...")
            result_chrome = subprocess.run(["pkill", "-f", "chrome"], capture_output=True, text=True)
            log_debug(f"[selenium] 📊 pkill chrome result: returncode={result_chrome.returncode}, stdout='{result_chrome.stdout.strip()}', stderr='{result_chrome.stderr.strip()}'")
            
            log_debug("[selenium] 🔪 Killing chromium processes...")
            result_chromium = subprocess.run(["pkill", "-f", "chromium"], capture_output=True, text=True)
            log_debug(f"[selenium] 📊 pkill chromium result: returncode={result_chromium.returncode}, stdout='{result_chromium.stdout.strip()}', stderr='{result_chromium.stderr.strip()}'")
            
            log_debug("[selenium] 🔪 Killing chromedriver processes...")
            result_chromedriver = subprocess.run(["pkill", "chromedriver"], capture_output=True, text=True)
            log_debug(f"[selenium] 📊 pkill chromedriver result: returncode={result_chromedriver.returncode}, stdout='{result_chromedriver.stdout.strip()}', stderr='{result_chromedriver.stderr.strip()}'")
            
            log_debug("[selenium] ⏱️ Sleeping 1 second after process kills...")
            time.sleep(1)
            log_debug("[selenium] ✅ Process killing completed")
        except Exception as e:
            log_error(f"[selenium] ❌ Failed to kill browser processes: {e}")

        try:
            log_debug("[selenium] 🔍 Starting lock file cleanup...")
            import glob
            patterns = [
                os.path.expanduser("~/.config/google-chrome*"),
                "/tmp/.com.google.Chrome*",
                "/tmp/.org.chromium.*",
                "/tmp/chrome_*",
            ]
            log_debug(f"[selenium] 📋 Cleanup patterns: {patterns}")

            for i, pattern in enumerate(patterns, 1):
                log_debug(f"[selenium] 🔍 Scanning pattern {i}/{len(patterns)}: {pattern}")
                matching_dirs = glob.glob(pattern)
                log_debug(f"[selenium] 📁 Found {len(matching_dirs)} directories matching pattern: {matching_dirs}")
                
                for prof_dir in matching_dirs:
                    log_debug(f"[selenium] 🗂️ Processing directory: {prof_dir}")
                    if not os.path.exists(prof_dir):
                        log_debug(f"[selenium] ⚠️ Directory no longer exists: {prof_dir}")
                        continue
                        
                    for name in [
                        "SingletonLock",
                        "lockfile",
                        "SingletonSocket",
                        "SingletonCookie",
                    ]:
                        path = os.path.join(prof_dir, name)
                        log_debug(f"[selenium] 🔎 Checking lock file: {path}")
                        if os.path.exists(path):
                            try:
                                log_debug(f"[selenium] 🗑️ Removing lock file: {path}")
                                os.remove(path)
                                log_debug(f"[selenium] ✅ Successfully removed: {path}")
                            except Exception as e:
                                log_warning(f"[selenium] ⚠️ Failed to remove {path}: {e}")
                        else:
                            log_debug(f"[selenium] ℹ️ Lock file not found: {path}")
        except Exception as e:
            log_error(f"[selenium] ❌ Lock file cleanup failed: {e}")
            import traceback
            log_error(f"[selenium] 📜 Cleanup traceback: {traceback.format_exc()}")

        log_debug("[selenium] 🎉 Chrome cleanup process completed")

    # [FIX] ensure the WebDriver session is alive before use
    async def _get_driver(self):
        """Return a valid WebDriver, recreating it if the session is dead."""
        if self.driver is None:
            try:
                await self._init_driver()
            except Exception as e:
                log_error(f"[selenium] Failed to initialize driver: {e}")
                return None
        else:
            try:
                # simple command to verify the session is still alive (for nodriver)
                await self.driver._tab.evaluate("true")
            except Exception as e:
                log_warning(f"[selenium] WebDriver session error: {e}. Restarting")
                try:
                    await self.driver.stop()
                except Exception:
                    pass
                self.driver = None
                try:
                    await self._init_driver()
                except Exception as e2:
                    log_error(f"[selenium] Failed to reinitialize driver: {e2}")
                    return None
        return self.driver

    async def _ensure_logged_in(self):
        try:
            # With nodriver, current_url might be a property that needs to be awaited
            current_url = self.driver.current_url
            if hasattr(current_url, '__await__'):
                current_url = await current_url
        except Exception:
            current_url = ""
        log_debug(f"[selenium] [STEP] Checking login state at {current_url}")
        if current_url and ("login" in current_url or "auth0" in current_url):
            log_debug("[selenium] Login required, notifying user")
            _notify_gui("🔐 Login required. Open")
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
        log_debug("[selenium] 🔄 Worker loop started - entering main processing loop")
        try:
            while True:
                log_debug("[selenium] 📥 Waiting for new tasks in queue...")
                bot, message, prompt = await self._queue.get()
                log_debug(f"[selenium] 📨 New task received: chat_id={message.chat_id}")
                
                while queue_paused:
                    log_debug("[selenium] ⏸️ Queue is paused, waiting...")
                    await asyncio.sleep(1)
                    
                log_debug(
                    f"[selenium] 🔧 [WORKER] Processing chat_id={message.chat_id} message_id={message.message_id}"
                )
                try:
                    lock = SeleniumChatGPTPlugin.chat_locks[message.chat_id]  # [FIX]
                    log_debug(f"[selenium] 🔒 Acquiring lock for chat {message.chat_id}")
                    async with lock:
                        log_debug(f"[selenium] ✅ Lock acquired for chat {message.chat_id}")
                        await self._process_message(bot, message, prompt)
                        log_debug(f"[selenium] 🔓 Lock released for chat {message.chat_id}")
                except Exception as e:
                    log_error(f"[selenium] ❌ Worker error: {e}", e)
                    _notify_gui(f"❌ Selenium error: {e}. Open UI")
                finally:
                    self._queue.task_done()
                    log_debug("[selenium] ✅ [WORKER] Task completed")
        except asyncio.CancelledError:  # [FIX]
            log_warning("[selenium] ⚠️ Worker was cancelled")
            raise
        except Exception as e:
            log_error(f"[selenium] 💥 Worker loop crashed: {e}", e)
            raise
        finally:
            log_info("[selenium] 🧹 Worker loop cleaned up")

    async def _process_message(self, bot, message, prompt):
        """Send the prompt to ChatGPT and forward the response."""
        log_debug(f"[selenium][STEP] processing prompt: {prompt}")

        for attempt in range(2):
            driver = await self._get_driver()
            if not driver:
                log_error("[selenium] WebDriver unavailable, aborting")
                _notify_gui("❌ Selenium driver not available. Open UI")
                return
            # [FIX] verify underlying nodriver tab is alive
            try:
                # Test connection with nodriver by checking if we can access the tab
                if not driver._tab:
                    raise Exception("nodriver tab not available")
                # Simple test to verify the browser is responsive
                await driver.execute_script("return true;")
            except Exception as e:
                log_warning(f"[selenium] Driver not responsive ({e}), restarting")
                driver = await self._get_driver()
                if not driver:
                    log_error("[selenium] Failed to restart WebDriver")
                    _notify_gui("❌ Selenium driver not available. Open UI")
                    return
            if not await self._ensure_logged_in():
                return

            log_debug("[selenium][STEP] ensuring ChatGPT is accessible")

            message_thread_id = getattr(message, "message_thread_id", None)
            chat_id = await chat_link_store.get_link(message.chat_id, message_thread_id)
            prompt_text = json.dumps(prompt, ensure_ascii=False)
            if not chat_id:
                path = recent_chats.get_chat_path(message.chat_id)
                if path and await go_to_chat_by_path_with_retries_async(driver, path):
                    current_url = driver.current_url
                    if hasattr(current_url, '__await__'):
                        current_url = await current_url
                    chat_id = _extract_chat_id(current_url)
                    if chat_id:  # [FIX] save and notify about recovered chat
                        await chat_link_store.save_link(message.chat_id, message_thread_id, chat_id)
                        _safe_notify(
                            f"⚠️ Couldn't find ChatGPT conversation for Telegram chat_id={message.chat_id}, message_thread_id={message_thread_id}.\n"
                            f"A new ChatGPT chat has been created: {chat_id}"
                        )
                else:
                    # REGRESSION FIX: If we had a path but couldn't navigate to it (chat archived/deleted)
                    # Clear the old path and create a new chat
                    if path:
                        log_warning(f"[selenium] Chat path {path} no longer accessible (archived/deleted), creating new chat")
                        recent_chats.clear_chat_path(message.chat_id)  # Clear old path
                    await _open_new_chat(driver)
                    # Chat ID will be extracted after sending the prompt
            else:
                # [REGRESSION FIX] We have a chat_id but need to verify it's still accessible
                # Try to navigate to the chat, if it fails, create a new one
                chat_url = f"https://chat.openai.com/c/{chat_id}"
                try:
                    await driver.get(chat_url)
                    # Wait for textarea with custom async wait
                    start_time = time.time()
                    textarea_found = False
                    while time.time() - start_time < 5:  # 5 second timeout
                        try:
                            textarea = await driver.find_element(By.ID, "prompt-textarea")
                            if textarea:
                                textarea_found = True
                                break
                        except:
                            pass
                        await asyncio.sleep(0.5)
                    
                    if not textarea_found:
                        raise Exception("prompt-textarea not found")
                    
                    log_debug(f"[selenium] Successfully accessed existing chat: {chat_id}")
                except Exception as e:
                    log_warning(f"[selenium] Existing chat {chat_id} no longer accessible: {e}")
                    log_info(f"[selenium] Creating new chat to replace inaccessible chat {chat_id}")
                    # Clear the old link and create new chat
                    await chat_link_store.remove(message.chat_id, message_thread_id)
                    recent_chats.clear_chat_path(message.chat_id)
                    await _open_new_chat(driver)
                    chat_id = None  # Will be set after creating new chat

            log_debug(f"[selenium][DEBUG] Chat ID from store: {chat_id}")
            log_debug(f"[selenium][DEBUG] Telegram chat_id: {message.chat_id}, message_thread_id: {message_thread_id}")

            # Only if we don't have a specific chat_id, go to home
            if not chat_id:
                try:
                    await driver.get("https://chat.openai.com")
                    # Wait for main element with custom async wait
                    start_time = time.time()
                    main_found = False
                    while time.time() - start_time < 10:  # 10 second timeout
                        try:
                            main = await driver.find_element(By.TAG_NAME, "main")
                            if main:
                                main_found = True
                                break
                        except:
                            pass
                        await asyncio.sleep(0.5)
                    
                    if not main_found:
                        raise Exception("main element not found")
                        
                except Exception as e:
                    log_warning(f"[selenium][ERROR] ChatGPT UI failed to load: {e}")
                    _notify_gui("❌ Selenium error: ChatGPT UI not ready. Open UI")
                    return

            try:
                if chat_id:
                    previous = get_previous_response(message.chat_id)
                    response_text = await process_prompt_in_chat(driver, chat_id, prompt_text, previous)
                    if response_text:
                        update_previous_response(message.chat_id, response_text)
                else:
                    # Create new chat and send prompt - ID will be available after ChatGPT responds
                    previous = get_previous_response(message.chat_id)
                    response_text = await process_prompt_in_chat(driver, None, prompt_text, previous)
                    if response_text:
                        update_previous_response(message.chat_id, response_text)
                        # Now extract the new chat ID after ChatGPT has responded
                        current_url = driver.current_url
                        if hasattr(current_url, '__await__'):
                            current_url = await current_url
                        new_chat_id = _extract_chat_id(current_url)
                        log_debug(f"[selenium][DEBUG] New chat created, extracted ID: {new_chat_id}")
                        log_debug(f"[selenium][DEBUG] Current URL: {current_url}")
                        if new_chat_id:
                            await chat_link_store.save_link(message.chat_id, message_thread_id, new_chat_id)
                            log_debug(f"[selenium][DEBUG] Saved link: {message.chat_id}/{message_thread_id} -> {new_chat_id}")
                            _safe_notify(
                                f"⚠️ Couldn't find ChatGPT conversation for Telegram chat_id={message.chat_id}, message_thread_id={message_thread_id}.\n"
                                f"A new ChatGPT chat has been created: {new_chat_id}"
                            )
                        else:
                            log_warning("[selenium][WARN] Failed to extract chat ID from URL")

                if await _check_conversation_full(driver):
                    current_url = driver.current_url
                    if hasattr(current_url, '__await__'):
                        current_url = await current_url
                    current_id = chat_id or _extract_chat_id(current_url)
                    global queue_paused
                    queue_paused = True
                    await _open_new_chat(driver)
                    
                    # TODO: Chat renaming was commented out - using standard prompt sending
                    # response_text = rename_and_send_prompt(driver, message, prompt_text)
                    response_text = await process_prompt_in_chat(driver, None, prompt_text, "")
                    
                    current_url = driver.current_url
                    if hasattr(current_url, '__await__'):
                        current_url = await current_url
                    new_chat_id = _extract_chat_id(current_url)
                    if new_chat_id:
                        await chat_link_store.save_link(message.chat_id, message_thread_id, new_chat_id)
                        log_debug(
                            f"[selenium][SUCCESS] New chat created for full conversation. "
                            f"Chat ID: {new_chat_id}"
                        )
                    queue_paused = False

                if not response_text:
                    response_text = "⚠️ No response received"

                await safe_send(
                    bot,
                    chat_id=message.chat_id,
                    text=response_text,
                    reply_to_message_id=message.message_id,
                    event_id=getattr(message, "event_id", None),
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
                log_error(f"[selenium][ERROR] failed to process message: {repr(e)}", e)
                _notify_gui(f"❌ Selenium error: {e}. Open UI")
                return


    def get_supported_models(self):
        return []  # nessun modello per ora

    def get_rate_limit(self):
        return (80, 10800, 0.5)

    def set_notify_fn(self, fn):
        self._notify_fn = fn
        set_notifier(fn)
        # Driver initialization will happen automatically when needed

    async def clean_chat_link(chat_id: int) -> str:
        """Disassociates the Telegram chat ID from the ChatGPT chat ID in the database.
        If no link exists for the current chat, creates a new one.
        """
        try:
            if await chat_link_store.remove(chat_id, None):
                log_debug(f"[clean_chat_link] Chat link removed for chat_id={chat_id}")
                return f"✅ Link for chat_id={chat_id} successfully removed."
            else:
                # No link found, create a new one
                new_chat_id = f"new_chat_{chat_id}"  # Generate a new chat ID (example)
                await chat_link_store.save_link(chat_id, None, new_chat_id)
                log_debug(f"[clean_chat_link] No link found. Created new link: {new_chat_id}")
                return f"⚠️ No link found for chat_id={chat_id}. Created new link: {new_chat_id}."
        except Exception as e:
            log_error(f"[clean_chat_link] Error while removing or creating the link: {repr(e)}", e)
            return f"❌ Error while removing or creating the link: {e}"

    async def handle_clear_chat_link_command(bot, message):
        """Handles the /clear_chat_link command."""
        chat_id = message.chat_id
        text = message.text.strip()

        if text == "/clear_chat_link":
            # No arguments provided, ask for confirmation
            confirmation_message = (
                f"⚠️ Do you really want to reset the link for this chat (ID: {chat_id})?\n"
                "Reply with 'yes' to confirm or use /cancel to cancel."
            )
            await bot.send_message(chat_id=chat_id, text=confirmation_message)

            # Wait for the user's response
            def check_response(response):
                return response.chat_id == chat_id and response.text.lower() in ["yes", "/cancel"]

            try:
                response = await bot.wait_for("message", timeout=60, check=check_response)
                if response.text.lower() == "yes":
                    result = await SeleniumChatGPTPlugin.clean_chat_link(chat_id)
                    await bot.send_message(chat_id=chat_id, text=result)
                else:
                    await bot.send_message(chat_id=chat_id, text="❌ Operation canceled.")
            except asyncio.TimeoutError:
                await bot.send_message(chat_id=chat_id, text="⏳ Timeout. Operation canceled.")
        else:
            # Normal handling with arguments
            result = await SeleniumChatGPTPlugin.clean_chat_link(chat_id)
            await bot.send_message(chat_id=chat_id, text=result)

PLUGIN_CLASS = SeleniumChatGPTPlugin

def go_to_chat_by_path(driver, path: str) -> bool:
    """Navigate to a specific chat using its path."""
    log_warning("[selenium] go_to_chat_by_path is deprecated - use async version")
    return False

async def go_to_chat_by_path_async(driver, path: str) -> bool:
    """Navigate to a specific chat using its path (async version for nodriver)."""
    try:
        chat_url = f"https://chat.openai.com{path}"
        await driver.get(chat_url)
        
        # Wait for textarea with custom timeout
        start_time = time.time()
        while time.time() - start_time < 5:  # 5 second timeout
            try:
                textarea = await driver.find_element(By.ID, "prompt-textarea")
                if textarea:
                    log_debug(f"[selenium] Successfully navigated to chat path: {path}")
                    return True
            except:
                pass
            await asyncio.sleep(0.5)
            
        log_warning(f"[selenium] Timeout while navigating to chat path: {path}")
        return False
    except Exception as e:
        log_error(f"[selenium] Error navigating to chat path: {repr(e)}")
        return False

def go_to_chat_by_path_with_retries(driver, path: str, retries: int = 3) -> bool:
    """Navigate to a specific chat using its path with retries."""
    log_warning("[selenium] go_to_chat_by_path_with_retries is deprecated - use async version")
    return False

async def go_to_chat_by_path_with_retries_async(driver, path: str, retries: int = 3) -> bool:
    """Navigate to a specific chat using its path with retries (async version for nodriver)."""
    for attempt in range(1, retries + 1):
        try:
            chat_url = f"https://chat.openai.com{path}"
            await driver.get(chat_url)
            
            # Wait for textarea with custom timeout
            start_time = time.time()
            textarea_found = False
            while time.time() - start_time < 5:  # 5 second timeout
                try:
                    textarea = await driver.find_element(By.ID, "prompt-textarea")
                    if textarea:
                        textarea_found = True
                        break
                except:
                    pass
                await asyncio.sleep(0.5)
                
            if textarea_found:
                log_debug(f"[selenium] Successfully navigated to chat path: {path} on attempt {attempt}")
                return True
            else:
                log_warning(f"[selenium] Timeout while navigating to chat path: {path} on attempt {attempt}")
        except Exception as e:
            log_error(f"[selenium] Error navigating to chat path on attempt {attempt}: {repr(e)}")

    log_warning(f"[selenium] Failed to navigate to chat path: {path} after {retries} attempts")
    return False
