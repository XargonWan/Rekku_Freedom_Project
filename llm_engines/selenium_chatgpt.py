import undetected_chromedriver as uc
from selenium import webdriver
import os
import re
import time
import json
import glob
import shutil
import tempfile
import threading
import asyncio
from collections import defaultdict
from typing import Optional, Dict
import aiomysql
import subprocess
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import (
    NoSuchElementException,
    TimeoutException,
    ElementNotInteractableException,
    SessionNotCreatedException,
    WebDriverException,
)
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


# Funzioni e classi locali
from core.logging_utils import log_debug, log_error, log_warning, log_info
from core.notifier import set_notifier
import core.recent_chats as recent_chats
from core.ai_plugin_base import AIPluginBase

# ChatLinkStore: gestisce la mappatura tra chat Telegram e chat ChatGPT
from core.db import get_conn

class ChatLinkStore:
    def __init__(self):
        self._table_ensured = False

    def _normalize_thread_id(self, message_thread_id: Optional[int | str]) -> str:
        """Return ``message_thread_id`` as a non-null string."""
        return str(message_thread_id) if message_thread_id is not None else "0"

    async def _ensure_table(self) -> None:
        if self._table_ensured:
            return
        conn = await get_conn()
        async with conn.cursor() as cursor:
            await cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS chatgpt_links (
                    chat_id TEXT NOT NULL,
                    message_thread_id TEXT,
                    link VARCHAR(2048),
                    PRIMARY KEY (chat_id(255), message_thread_id(255))
                )
                """
            )
            await conn.commit()
        conn.close()
        self._table_ensured = True

    async def get_link(self, chat_id: int | str, message_thread_id: Optional[int | str]) -> Optional[str]:
        await self._ensure_table()
        normalized = self._normalize_thread_id(message_thread_id)
        chat_id_str = str(chat_id)
        log_debug(f"[chatlink] Searching for link: chat_id={chat_id_str}, message_thread_id={normalized}")
        conn = await get_conn()
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute(
                """
                SELECT link
                FROM chatgpt_links
                WHERE chat_id = %s AND message_thread_id = %s
                """,
                (chat_id_str, normalized),
            )
            row = await cursor.fetchone()
        conn.close()
        if row:
            link_value = row.get("link")
            log_debug(f"[chatlink] Found mapping {chat_id_str}/{normalized} -> {link_value}")
            return link_value
        log_debug(f"[chatlink] No row found for {chat_id_str}/{normalized}")
        return None

    async def save_link(self, chat_id: int | str, message_thread_id: Optional[int | str], link: str) -> None:
        await self._ensure_table()
        normalized = self._normalize_thread_id(message_thread_id)
        chat_id_str = str(chat_id)
        conn = await get_conn()
        async with conn.cursor() as cursor:
            await cursor.execute(
                """
                INSERT INTO chatgpt_links (chat_id, message_thread_id, link)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE link=VALUES(link)
                """,
                (chat_id_str, normalized, link),
            )
            await conn.commit()
        conn.close()
        log_debug(f"[chatlink] Saved mapping {chat_id_str}/{normalized} -> {link}")

    async def remove(self, chat_id: int | str, message_thread_id: Optional[int | str]) -> bool:
        await self._ensure_table()
        normalized = self._normalize_thread_id(message_thread_id)
        chat_id_str = str(chat_id)
        conn = await get_conn()
        async with conn.cursor() as cursor:
            result = await cursor.execute(
                """
                DELETE FROM chatgpt_links
                WHERE chat_id = %s AND message_thread_id = %s
                """,
                (chat_id_str, normalized),
            )
            await conn.commit()
        conn.close()
        rows_deleted = cursor.rowcount > 0
        if rows_deleted:
            log_debug(f"[chatlink] Removed link for chat_id={chat_id_str}, message_thread_id={normalized}")
        else:
            log_debug(f"[chatlink] No link found for chat_id={chat_id_str}, message_thread_id={normalized}")
        return rows_deleted
from core.telegram_utils import safe_send

# Fallback per notify_trainer se non disponibile
def notify_trainer(trainer_id, text):
    log_warning(f"[notify_trainer fallback] trainer_id={trainer_id}: {text}")

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

    tag = (textarea.tag_name or "").lower()
    prop = "value" if tag in {"textarea", "input"} else "textContent"
    script = (
        "arguments[0].focus();"
        f"arguments[0].{prop} = arguments[1];"
        "arguments[0].dispatchEvent(new Event('input', {bubbles: true}));"
    )
    driver.execute_script(script, textarea, clean_text)

    actual = driver.execute_script(f"return arguments[0].{prop};", textarea) or ""
    log_debug(f"[DEBUG] Length actually present in textarea: {len(actual)}")
    if actual != clean_text:
        log_warning(
            f"[selenium] textarea mismatch: expected {len(clean_text)} chars, found {len(actual)}"
        )


def paste_and_send(textarea, prompt_text: str) -> None:
    """Insert ``prompt_text`` into ``textarea`` ensuring full content is present.

    Tries JavaScript injection first (for performance and reliability), then
    verifies the length.  If the content does not match, falls back to a
    chunked ``send_keys`` approach which mimics manual typing.
    """
    driver = textarea._parent
    clean = strip_non_bmp(prompt_text)

    _send_text_to_textarea(driver, textarea, clean)
    tag = (textarea.tag_name or "").lower()
    prop = "value" if tag in {"textarea", "input"} else "textContent"
    actual = driver.execute_script(f"return arguments[0].{prop};", textarea) or ""
    if actual == clean:
        return

    log_warning(
        f"[selenium] JS paste mismatch: expected {len(clean)} chars, got {len(actual)}. Falling back to send_keys"
    )

    import textwrap
    textarea.clear()
    for attempt in range(3):
        if attempt:
            log_warning(f"[selenium] send_keys retry {attempt}/3")
        try:
            textarea.send_keys(Keys.CONTROL, "a")
            textarea.send_keys(Keys.DELETE)
            for chunk in textwrap.wrap(clean, 200):
                textarea.send_keys(chunk)
                time.sleep(0.05)
            final_val = textarea.get_attribute("value") or ""
            if final_val == clean:
                return
        except Exception as e:
            log_warning(f"[selenium] send_keys attempt {attempt} failed: {e}")
    log_warning("[selenium] Failed to insert full prompt")


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
        # Some UI experiments may display a "Which response do you prefer?" dialog
        # that blocks further interaction. If present, automatically click the first
        # "I prefer this response" button so ChatGPT can finalize the output.
        try:
            buttons = driver.find_elements(
                By.CSS_SELECTOR, "[data-testid='paragen-prefer-response-button']"
            )
            if buttons:
                try:
                    buttons[0].click()
                    time.sleep(1)
                    log_debug(
                        "[selenium] Dismissed prefer-response dialog"
                    )
                except Exception as e:  # pragma: no cover - best effort
                    log_warning(
                        f"[selenium] Failed to click prefer-response button: {e}"
                    )
        except Exception:
            pass

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
    log_debug(f"[selenium][STEP] Initial markdown block count: {prev_blocks}")
    for attempt in range(1, 4):
        try:
            log_debug(f"[selenium][STEP] Attempt {attempt} to send prompt")
            paste_and_send(textarea, prompt_text)
            try:
                send_btn = WebDriverWait(driver, 3).until(
                    EC.element_to_be_clickable(
                        (By.CSS_SELECTOR, "button[data-testid='send-button']")
                    )
                )
                driver.execute_script("arguments[0].click();", send_btn)
                log_debug("[selenium][STEP] Clicked send button")
            except Exception as e:
                log_warning(f"[selenium] Failed to click send button: {e}")
                textarea.send_keys(Keys.ENTER)
                log_debug("[selenium][STEP] Sent ENTER key as fallback")
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
            from core.notifier import notify_trainer
            notify_trainer(chunk)
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
    """Navigate to ChatGPT home to create a new chat with retries."""
    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            log_debug(f"[selenium] Attempt {attempt}/{max_retries} to navigate to ChatGPT home")
            driver.get("https://chat.openai.com")
            log_debug("[selenium] Successfully navigated to ChatGPT home")
            return
        except Exception as e:
            log_warning(f"[selenium] Attempt {attempt} failed: {e}")
            if attempt < max_retries:
                time.sleep(2 * attempt)  # Exponential backoff
            else:
                log_error("[selenium] All attempts to navigate to ChatGPT home failed")
                raise


def is_chat_archived(driver, chat_id: str) -> bool:
    """Check if a ChatGPT chat is archived."""
    try:
        chat_url = f"https://chat.openai.com/chat/{chat_id}"
        driver.get(chat_url)
        WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.XPATH, "//div[contains(text(), 'This conversation is archived')]"))
        )
        log_warning("[selenium] Chat is archived.")
        return True
    except TimeoutException:
        log_debug("[selenium] Chat is not archived.")
        return False
    except Exception as e:
        log_error(f"[selenium] Error checking if chat is archived: {repr(e)}")
        return False

# Update process_prompt_in_chat to use the new functions
def process_prompt_in_chat(
    driver, chat_id: str | None, prompt_text: str, previous_text: str
) -> Optional[str]:
    """Send a prompt to a ChatGPT chat and return the newly generated text."""
    if chat_id and is_chat_archived(driver, chat_id):
        chat_id = None  # Mark chat as invalid

    if not chat_id:
        log_debug("[selenium] Creating a new chat")
        _open_new_chat(driver)
        # Chat ID will be extracted later from the URL after sending the prompt

    # Some UI experiments may block the textarea with a "I prefer this response"
    # dialog. Dismiss it if present before looking for the textarea.

    log_info(f"[chatgpt_model] Ensuring model {CHATGPT_MODEL} is active")
    if not ensure_chatgpt_model(driver):
        log_warning(f"[chatgpt_model] Failed to ensure model {CHATGPT_MODEL}")

    try:
        prefer_btn = WebDriverWait(driver, 2).until(
            EC.element_to_be_clickable(
                (By.CSS_SELECTOR, "[data-testid='paragen-prefer-response-button']")
            )
        )
        prefer_btn.click()
        time.sleep(2)
    except TimeoutException:
        pass
    except Exception as e:  # pragma: no cover - best effort
        log_warning(f"[selenium] Failed to click prefer-response button: {e}")

    try:
        textarea = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.ID, "prompt-textarea"))
        )
    except TimeoutException:
        log_error("[selenium][ERROR] prompt textarea not found")
        return None

    for attempt in range(1, 4):  # Retry up to 3 times
        try:
            paste_and_send(textarea, prompt_text)
            tag = (textarea.tag_name or "").lower()
            prop = "value" if tag in {"textarea", "input"} else "textContent"
            final_value = driver.execute_script(f"return arguments[0].{prop};", textarea) or ""
            if final_value != strip_non_bmp(prompt_text):
                log_warning(
                    f"[selenium] Prompt mismatch after paste: expected {len(prompt_text)} chars, got {len(final_value)}"
                )
                time.sleep(1)
                continue
            try:
                json.loads(final_value)
            except Exception:
                log_warning("[selenium] JSON invalid after paste; retrying")
                time.sleep(1)
                continue
            try:
                send_btn = WebDriverWait(driver, 3).until(
                    EC.element_to_be_clickable(
                        (By.CSS_SELECTOR, "button[data-testid='send-button']")
                    )
                )
                driver.execute_script("arguments[0].click();", send_btn)
                log_debug("[selenium][STEP] Clicked send button")
            except Exception as e:
                log_warning(f"[selenium] Failed to click send button: {e}")
                textarea.send_keys(Keys.ENTER)
                log_debug("[selenium][STEP] Sent ENTER key as fallback")
        except ElementNotInteractableException as e:
            log_warning(f"[selenium][retry] Element not interactable: {e}")
            time.sleep(2)
            continue
        except Exception as e:
            log_error(f"[selenium][ERROR] Failed to send prompt: {repr(e)}")
            return None

        log_debug("🔍 Waiting for response block...")
        try:
            response_text = wait_until_response_stabilizes(driver)
        except TimeoutException:
            log_warning("[selenium][WARN] Timeout while waiting for response")
        else:
            if response_text and response_text != previous_text:
                # If this was a new chat (no chat_id initially), extract and save the new chat ID
                if not chat_id:
                    new_chat_id = _extract_chat_id(driver.current_url)
                    if new_chat_id:
                        log_debug(f"[selenium] New chat ID extracted after response: {new_chat_id}")
                        # This will be used by the calling function to save the link
                return response_text.strip()

        log_warning(f"[selenium][retry] Empty response attempt {attempt}")
        time.sleep(2)

    os.makedirs("/config/logs/screenshots", exist_ok=True)
    fname = f"/config/logs/screenshots/chat_{chat_id or 'unknown'}_no_response.png"
    try:
        driver.save_screenshot(fname)
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
    #         EC.element_to_be_clickable((By.CSS_SELECTOR, "[role='textbox']"))
    #     )
    #     rename_input.clear()
    #     rename_input.send_keys(strip_non_bmp(new_title))

    #     rename_input.send_keys(Keys.ENTER)
    #     log_debug("[DEBUG] Rename field found and edited")
    #     recent_chats.set_chat_path(chat_info.chat_id, new_title)
    # except Exception as e:
    #     log_warning(f"[selenium][ERROR] rename failed: {e}")

    # try:
    #     textarea = WebDriverWait(driver, 10).until(
    #         EC.element_to_be_clickable((By.ID, "prompt-textarea"))
    #     )
    # except TimeoutException:
    #     log_error("[selenium][ERROR] prompt textarea not found")
    #     return None

    # try:
    #     paste_and_send(textarea, prompt_text)
    #     textarea.send_keys(Keys.ENTER)
    # except Exception as e:
    #     log_error(f"[selenium][ERROR] failed to send prompt: {repr(e)}")
    #     return None

    # previous_text = get_previous_response(chat_info.chat_id)
    # log_debug("🔍 Waiting for response block...")
    # try:
    #     response_text = wait_until_response_stabilizes(driver)
    # except Exception as e:
    #     log_error(f"[selenium][ERROR] waiting for response failed: {repr(e)}")
    #     return None

    # if not response_text or response_text == previous_text:
    #     log_debug("🟡 No new response, skipping")
    #     return None
    # update_previous_response(chat_info.chat_id, response_text)
    # log_debug("📝 New response text extracted")
    # return response_text.strip()


# Funzione di selezione modello ChatGPT
CHATGPT_MODEL = os.getenv("CHATGPT_MODEL", "GPT-4o")


def _locate_model_switcher(driver, timeout: int = 5):
    """Return the model switcher button using current DOM selectors.

    The ChatGPT interface recently switched to Radix-generated element IDs,
    so we try the previous ``data-testid`` selector first and fall back to
    a more generic XPath search based on the ``radix-`` prefix.
    """
    try:
        return WebDriverWait(driver, timeout).until(
            EC.element_to_be_clickable(
                (By.CSS_SELECTOR, "button[data-testid='model-switcher-dropdown-button']")
            )
        )
    except TimeoutException:
        log_debug("[chatgpt_model] Falling back to Radix model switcher selector")
        return WebDriverWait(driver, timeout).until(
            EC.element_to_be_clickable(
                (
                    By.XPATH,
                    "//button[starts-with(@id,'radix-') and contains(@aria-label,'model')]",
                )
            )
        )


def ensure_chatgpt_model(driver):
    """Ensure the desired ChatGPT model is active before sending a prompt."""
    log_info(f"[chatgpt_model] Verifying active model matches {CHATGPT_MODEL}")
    try:
        log_debug("[chatgpt_model] Locating model switcher button")
        switcher_btn = _locate_model_switcher(driver)
        aria_label = switcher_btn.get_attribute("aria-label") or ""
        log_debug(f"[chatgpt_model] switcher aria-label: {aria_label}")
        match = re.search(r"current model is\s*(.*)", aria_label)
        active_model = match.group(1).strip() if match else ""
        log_info(f"[chatgpt_model] Active model is {active_model}")
        if active_model == CHATGPT_MODEL:
            log_info(f"[chatgpt_model] Desired model {CHATGPT_MODEL} already active")
            return True

        log_debug("[chatgpt_model] Opening dropdown")
        try:
            switcher_btn.find_element(By.XPATH, "./div").click()
        except Exception:
            switcher_btn.click()
        WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "div[role='menu']"))
        )
        log_debug("[chatgpt_model] Dropdown opened")

        try:
            log_debug("[chatgpt_model] Searching main list for model")
            model_elem = WebDriverWait(driver, 3).until(
                EC.element_to_be_clickable(
                    (By.CSS_SELECTOR, f"[data-testid='model-switcher-gpt-{CHATGPT_MODEL}']")
                )
            )
            log_info(f"[chatgpt_model] Found desired model in main list: {CHATGPT_MODEL}")
        except TimeoutException:
            try:
                log_debug("[chatgpt_model] Falling back to Radix selector for model option")
                model_elem = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable(
                        (
                            By.XPATH,
                            f"//div[starts-with(@id,'radix-')]/div//div[contains(., '{CHATGPT_MODEL}')]",
                        )
                    )
                )
                log_info(f"[chatgpt_model] Found desired model via fallback: {CHATGPT_MODEL}")
            except Exception as e:
                try:
                    log_debug("[chatgpt_model] Trying nested provider list")
                    provider_elem = WebDriverWait(driver, 2).until(
                        EC.element_to_be_clickable((By.XPATH, "//div[@role='menu']//div[@role='menuitem'][1]"))
                    )
                    provider_elem.click()
                    model_elem = WebDriverWait(driver, 5).until(
                        EC.element_to_be_clickable(
                            (
                                By.XPATH,
                                f"//div[@role='menu']//div[contains(., '{CHATGPT_MODEL}')]",
                            )
                        )
                    )
                    log_info(
                        f"[chatgpt_model] Found desired model via nested fallback: {CHATGPT_MODEL}"
                    )
                except Exception as inner:
                    log_warning(
                        f"[chatgpt_model] Desired model {CHATGPT_MODEL} not found: {inner}"
                    )
                    try:
                        items = driver.find_elements(By.CSS_SELECTOR, "div[role='menuitem']")
                        names = [i.text for i in items]
                        log_debug(f"[chatgpt_model] Available models: {names}")
                    except Exception:
                        pass
                    return False

        log_debug("[chatgpt_model] Clicking desired model")
        ActionChains(driver).move_to_element(model_elem).click().perform()
        log_info(f"[chatgpt_model] Clicked on model {CHATGPT_MODEL}")
        try:
            WebDriverWait(driver, 5).until(
                lambda d: CHATGPT_MODEL in (
                    _locate_model_switcher(d).get_attribute("aria-label") or ""
                )
            )
            log_info(f"[chatgpt_model] Modello selezionato: {CHATGPT_MODEL}")
            return True
        except TimeoutException:
            new_label = _locate_model_switcher(driver).get_attribute("aria-label") or ""
            log_warning(f"[chatgpt_model] Verifica modello fallita: {new_label}")
            return False
    except Exception as e:
        log_warning(f"[chatgpt_model] Errore selezione modello: {repr(e)}")
        try:
            os.makedirs("/config/logs/screenshots", exist_ok=True)
            driver.save_screenshot("/config/logs/screenshots/model_switch_error.png")
            log_warning(
                "[chatgpt_model] Saved screenshot model_switch_error.png"
            )
        except Exception as ss:
            log_warning(f"[chatgpt_model] Screenshot failed: {ss}")
        return False

class SeleniumChatGPTPlugin(AIPluginBase):
    # [FIX] shared locks per Telegram chat
    chat_locks: defaultdict[int, asyncio.Lock] = defaultdict(asyncio.Lock)
    def __init__(self, notify_fn=None):
        """Initialize the plugin without starting Selenium yet."""
        self.driver = None
        self._queue: asyncio.Queue = asyncio.Queue()
        self._worker_task = None
        self._notify_fn = notify_fn or notify_trainer
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

    async def stop(self):
        """Cancel worker task and run cleanup."""  # [FIX]
        if self._worker_task:
            self._worker_task.cancel()
            await asyncio.gather(self._worker_task, return_exceptions=True)
        self.cleanup()

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
                    
                    # Handle specific Python shutdown error
                    if "sys.meta_path is None" in str(e) or "Python is likely shutting down" in str(e):
                        log_warning("[selenium] Python shutdown detected, skipping Chrome initialization")
                        return None
                    
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
                            log_warning("[selenium] Chrome lock suspected - attempting forced lock cleanup...")
                            self._cleanup_chrome_remnants()
                            try:
                                if os.path.exists(chrome_binary):
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
                                    log_debug("[selenium] ✅ Chrome initialized after forced lock cleanup")
                                    return
                                else:
                                    raise Exception("Chrome binary not found")
                            except Exception as e3:
                                log_error(f"[selenium] ❌ All initialization attempts failed: {e3}")
                                _notify_gui(f"❌ Selenium error: {e3}. Check graphics environment.")
                                raise SystemExit(1)

    def _cleanup_chrome_remnants(self):
        """Clean up Chrome processes and leftover lock files."""
        try:
            subprocess.run(["pkill", "-f", "chrome"], capture_output=True, text=True)
            subprocess.run(["pkill", "chromedriver"], capture_output=True, text=True)
            time.sleep(1)
            log_debug("[selenium] Issued pkill for chrome and chromedriver")
        except Exception as e:
            log_debug(f"[selenium] Failed to kill chrome processes: {e}")

        try:
            import glob
            patterns = [
                os.path.expanduser("~/.config/google-chrome*"),
                "/tmp/.com.google.Chrome*",
                "/tmp/.org.chromium.*",
                "/tmp/chrome_*",
            ]

            for pattern in patterns:
                log_debug(f"[selenium] Scanning {pattern}")
                for prof_dir in glob.glob(pattern):
                    for name in [
                        "SingletonLock",
                        "lockfile",
                        "SingletonSocket",
                        "SingletonCookie",
                    ]:
                        path = os.path.join(prof_dir, name)
                        if os.path.exists(path):
                            try:
                                os.remove(path)
                                log_debug(f"[selenium] Removed lock file: {path}")
                            except Exception as e:
                                log_debug(f"[selenium] Failed to remove {path}: {e}")
        except Exception as e:
            log_debug(f"[selenium] Lock file cleanup failed: {e}")

        log_debug("[selenium] Chrome lock cleanup complete")

    # [FIX] ensure the WebDriver session is alive before use
    def _get_driver(self):
        """Return a valid WebDriver, recreating it if the session is dead."""
        if self.driver is None:
            try:
                self._init_driver()
            except Exception as e:
                log_error(f"[selenium] Failed to initialize driver: {e}")
                return None
        else:
            try:
                # simple command to verify the session is still alive
                self.driver.execute_script("return 1")
            except Exception as e:
                log_warning(f"[selenium] WebDriver session error: {e}. Restarting")
                try:
                    self.driver.quit()
                except Exception:
                    pass
                self.driver = None
                try:
                    self._init_driver()
                except Exception as e:
                    log_error(f"[selenium] Failed to reinitialize driver: {e}")
                    return None
        return self.driver

    def _ensure_logged_in(self):
        try:
            current_url = self.driver.current_url
        except Exception:
            current_url = ""
        log_debug(f"[selenium] [STEP] Checking login state at {current_url}")
        if current_url and ("login" in current_url or "auth0" in current_url):
            log_debug("[selenium] Login required, notifying user")
            _notify_gui("🔐 Login required. Open")
            return False
        log_debug("[selenium] Logged in and ready")
        return True

    async def _process_message(self, bot, message, prompt):
        """Send the prompt to ChatGPT and forward the response."""
        log_debug(f"[selenium][STEP] processing prompt: {prompt}")

        for attempt in range(2):
            driver = self._get_driver()
            if not driver:
                log_error("[selenium] WebDriver unavailable, aborting")
                _notify_gui("\u274c Selenium driver not available. Open UI")
                return
            if (
                not driver.service
                or not getattr(driver.service, "process", None)
                or driver.service.process.poll() is not None
            ):
                log_warning("[selenium] Driver process not running, restarting")
                driver = self._get_driver()
                if not driver:
                    log_error("[selenium] Failed to restart WebDriver")
                    _notify_gui("\u274c Selenium driver not available. Open UI")
                    return
            if not self._ensure_logged_in():
                return

            log_debug("[selenium][STEP] ensuring ChatGPT is accessible")

            message_thread_id = getattr(message, "message_thread_id", None)
            chat_id = await chat_link_store.get_link(message.chat_id, message_thread_id)
            prompt_text = json.dumps(prompt, ensure_ascii=False)
            if not chat_id:
                path = recent_chats.get_chat_path(message.chat_id)
                if path and go_to_chat_by_path_with_retries(driver, path):
                    chat_id = _extract_chat_id(driver.current_url)
                    if chat_id:
                        await chat_link_store.save_link(message.chat_id, message_thread_id, chat_id)
                        _safe_notify(
                            f"\u26a0\ufe0f Couldn't find ChatGPT conversation for Telegram chat_id={message.chat_id}, message_thread_id={message_thread_id}.\n"
                            f"A new ChatGPT chat has been created: {chat_id}"
                        )
                else:
                    if path:
                        log_warning(f"[selenium] Chat path {path} no longer accessible (archived/deleted), creating new chat")
                        recent_chats.clear_chat_path(message.chat_id)
                    _open_new_chat(driver)
            else:
                chat_url = f"https://chat.openai.com/c/{chat_id}"
                try:
                    driver.get(chat_url)
                    WebDriverWait(driver, 5).until(
                        EC.presence_of_element_located((By.ID, "prompt-textarea"))
                    )
                    log_debug(f"[selenium] Successfully accessed existing chat: {chat_id}")
                except Exception as e:
                    log_warning(f"[selenium] Existing chat {chat_id} no longer accessible: {e}")
                    log_info(f"[selenium] Creating new chat to replace inaccessible chat {chat_id}")
                    await chat_link_store.remove(message.chat_id, message_thread_id)
                    recent_chats.clear_chat_path(message.chat_id)
                    _open_new_chat(driver)
                    chat_id = None

            log_debug(f"[selenium][DEBUG] Chat ID from store: {chat_id}")
            log_debug(f"[selenium][DEBUG] Telegram chat_id: {message.chat_id}, message_thread_id: {message_thread_id}")

            if not chat_id:
                try:
                    driver.get("https://chat.openai.com")
                    WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.TAG_NAME, "main"))
                    )
                except Exception:
                    log_warning("[selenium][ERROR] ChatGPT UI failed to load")
                    _notify_gui("\u274c Selenium error: ChatGPT UI not ready. Open UI")
                    return

            try:
                if chat_id:
                    previous = get_previous_response(message.chat_id)
                    response_text = process_prompt_in_chat(driver, chat_id, prompt_text, previous)
                    if response_text:
                        update_previous_response(message.chat_id, response_text)
                else:
                    previous = get_previous_response(message.chat_id)
                    response_text = process_prompt_in_chat(driver, None, prompt_text, previous)
                    if response_text:
                        update_previous_response(message.chat_id, response_text)
                        new_chat_id = _extract_chat_id(driver.current_url)
                        log_debug(f"[selenium][DEBUG] New chat created, extracted ID: {new_chat_id}")
                        log_debug(f"[selenium][DEBUG] Current URL: {driver.current_url}")
                        if new_chat_id:
                            await chat_link_store.save_link(message.chat_id, message_thread_id, new_chat_id)
                            log_debug(f"[selenium][DEBUG] Saved link: {message.chat_id}/{message_thread_id} -> {new_chat_id}")
                            _safe_notify(
                                f"\u26a0\ufe0f Couldn't find ChatGPT conversation for Telegram chat_id={message.chat_id}, message_thread_id={message_thread_id}.\n"
                                f"A new ChatGPT chat has been created: {new_chat_id}"
                            )
                        else:
                            log_warning("[selenium][WARN] Failed to extract chat ID from URL")

                if _check_conversation_full(driver):
                    current_id = chat_id or _extract_chat_id(driver.current_url)
                    global queue_paused
                    queue_paused = True
                    _open_new_chat(driver)
                    response_text = process_prompt_in_chat(driver, None, prompt_text, "")
                    new_chat_id = _extract_chat_id(driver.current_url)
                    if new_chat_id:
                        await chat_link_store.save_link(message.chat_id, message_thread_id, new_chat_id)
                        log_debug(
                            f"[selenium][SUCCESS] New chat created for full conversation. Chat ID: {new_chat_id}"
                        )
                    queue_paused = False

                if not response_text:
                    response_text = "\u26a0\ufe0f No response received"

                await safe_send(
                    bot,
                    chat_id=message.chat_id,
                    text=response_text,
                    reply_to_message_id=message.message_id,
                    message_thread_id=message_thread_id,
                    event_id=getattr(message, "event_id", None),
                )
                log_debug(
                    f"[selenium][STEP] response forwarded to {message.chat_id}"
                )
                return

            except Exception as e:
                log_error(f"[selenium][ERROR] failed to process message: {repr(e)}", e)
                _notify_gui(f"\u274c Selenium error: {e}. Open UI")
                return

    @staticmethod
    async def clean_chat_link(chat_id: int) -> str:
        """Disassociates the Telegram chat ID from the ChatGPT chat ID in the database.
        If no link exists for the current chat, creates a new one."""
        try:
            if await chat_link_store.remove(chat_id, None):
                log_debug(f"[clean_chat_link] Chat link removed for chat_id={chat_id}")
                return f"✅ Link for chat_id={chat_id} successfully removed."
            else:
                new_chat_id = f"new_chat_{chat_id}"
                await chat_link_store.save_link(chat_id, None, new_chat_id)
                log_debug(f"[clean_chat_link] No link found. Created new link: {new_chat_id}")
                return f"⚠️ No link found for chat_id={chat_id}. Created new link: {new_chat_id}."
        except Exception as e:
            log_error(f"[clean_chat_link] Error while removing or creating the link: {repr(e)}", e)
            return f"❌ Error while removing or creating the link: {e}"

    @staticmethod
    async def handle_clear_chat_link_command(bot, message):
        """Handles the /clear_chat_link command."""
        chat_id = message.chat_id
        text = message.text.strip()

        if text == "/clear_chat_link":
            confirmation_message = (
                f"⚠️ Do you really want to reset the link for this chat (ID: {chat_id})?\n"
                "Reply with 'yes' to confirm or use /cancel to cancel."
            )
            await bot.send_message(chat_id=chat_id, text=confirmation_message)

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
            result = await SeleniumChatGPTPlugin.clean_chat_link(chat_id)
            await bot.send_message(chat_id=chat_id, text=result)

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
        try:
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
        except asyncio.CancelledError:  # [FIX]
            log_warning("Worker was cancelled")
            raise
        finally:
            log_info("Worker loop cleaned up")
 
PLUGIN_CLASS = SeleniumChatGPTPlugin

def go_to_chat_by_path(driver, path: str) -> bool:
    """Navigate to a specific chat using its path."""
    try:
        chat_url = f"https://chat.openai.com{path}"
        driver.get(chat_url)
        WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.ID, "prompt-textarea"))
        )
        log_debug(f"[selenium] Successfully navigated to chat path: {path}")
        return True
    except TimeoutException:
        log_warning(f"[selenium] Timeout while navigating to chat path: {path}")
        return False
    except Exception as e:
        log_error(f"[selenium] Error navigating to chat path: {repr(e)}")
        return False

def go_to_chat_by_path_with_retries(driver, path: str, retries: int = 3) -> bool:
    """Navigate to a specific chat using its path with retries."""
    for attempt in range(1, retries + 1):
        try:
            chat_url = f"https://chat.openai.com{path}"
            driver.get(chat_url)
            WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.ID, "prompt-textarea"))
            )
            log_debug(f"[selenium] Successfully navigated to chat path: {path} on attempt {attempt}")
            return True
        except TimeoutException:
            log_warning(f"[selenium] Timeout while navigating to chat path: {path} on attempt {attempt}")
        except Exception as e:
            log_error(f"[selenium] Error navigating to chat path on attempt {attempt}: {repr(e)}")
    log_warning(f"[selenium] Failed to navigate to chat path: {path} after {retries} attempts")
    return False
