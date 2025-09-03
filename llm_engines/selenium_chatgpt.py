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
import logging
from collections import defaultdict
from typing import Optional, Dict
import subprocess
try:
    from dotenv import load_dotenv  # type: ignore
except Exception:  # pragma: no cover - fallback if python-dotenv not installed
    def load_dotenv(*args, **kwargs):
        return False
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
    StaleElementReferenceException,
)
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from urllib3.exceptions import ReadTimeoutError


# Funzioni e classi locali
from core.logging_utils import log_debug, log_error, log_warning, log_info, _LOG_DIR
from core.notifier import set_notifier
import core.recent_chats as recent_chats
from core.ai_plugin_base import AIPluginBase

# Load environment variables for root password and other settings
load_dotenv()

# ChatLinkStore: gestisce la mappatura tra le chat dell'interfaccia e le conversazioni ChatGPT
from core.chat_link_store import ChatLinkStore

# Fallback per notify_trainer se il modulo core.notifier non è disponibile
def notify_trainer(message: str) -> None:
    """Best-effort trainer notification used during tests.

    The real ``notify_trainer`` utility accepts a single message argument, so
    the fallback must mirror that signature to avoid ``TypeError`` when the
    caller provides just the message text.
    """
    log_warning(f"[notify_trainer fallback] {message}")

# ---------------------------------------------------------------------------
# Constants

GRACE_PERIOD_SECONDS = 3
MAX_WAIT_TIMEOUT_SECONDS = 5 * 60  # hard ceiling

# Cache the last response per chat to avoid duplicates
previous_responses: Dict[str, str] = {}
response_cache_lock = threading.Lock()

# Persistent mapping between interface chats and ChatGPT conversations
chat_link_store = ChatLinkStore()
queue_paused = False


def get_previous_response(chat_id: str) -> str:
    """Return the cached response for the given chat."""
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
    # Log the full text to aid debugging and ensure the JSON is not truncated
    # in logs. This may produce very long lines but provides complete
    # visibility into the prompt content.
    log_debug(f"[DEBUG] Text to send: {clean_text}")

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
    # Only warn if the textarea differs noticeably from the injected text
    if abs(len(clean_text) - len(actual)) > 5:
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

    # Try JavaScript injection first
    try:
        _send_text_to_textarea(driver, textarea, clean)
        tag = (textarea.tag_name or "").lower()
        prop = "value" if tag in {"textarea", "input"} else "textContent"
        actual = driver.execute_script(f"return arguments[0].{prop};", textarea) or ""
        if len(actual) >= len(clean) * 0.9:  # Allow some tolerance
            log_debug(f"[selenium] JS injection successful: {len(actual)}/{len(clean)} chars")
            return
    except StaleElementReferenceException:
        log_warning("[selenium] Textarea became stale during JS paste, retrying with send_keys")
    except Exception as e:
        log_warning(f"[selenium] JS injection failed: {e}, falling back to send_keys")

    log_warning(f"[selenium] JS paste failed, falling back to send_keys")

    # Fallback to send_keys with improved logic
    import textwrap
    chunk_size = 1000
    final_val = ""
    for attempt in range(3):
        if attempt:
            log_warning(f"[selenium] send_keys retry {attempt}/3")
        try:
            # Re-locate textarea if it became stale
            try:
                textarea.clear()
                time.sleep(0.1)  # Brief pause after clear
            except StaleElementReferenceException:
                log_warning("[selenium] Textarea stale, attempting to re-locate")
                textarea = driver.find_element(By.ID, "prompt-textarea")
                textarea.clear()
                time.sleep(0.1)
            
            # Send chunks with better validation
            accumulated_text = ""
            chunks_sent = 0
            total_chunks = len(list(textwrap.wrap(clean, chunk_size)))
            content_was_sent = False
            
            for idx, chunk in enumerate(textwrap.wrap(clean, chunk_size), start=1):
                log_debug(f"[selenium] sending chunk {idx}/{total_chunks} len={len(chunk)}")
                textarea.send_keys(chunk)
                accumulated_text += chunk
                chunks_sent = idx
                time.sleep(0.05)
                
                # Validate every few chunks to catch issues early
                if idx % 5 == 0:
                    current_val = textarea.get_attribute("value") or ""
                    if len(current_val) < len(accumulated_text) * 0.5:  # More lenient threshold
                        log_warning(f"[selenium] Content mismatch detected at chunk {idx}, retrying")
                        break
            
            # If we sent all chunks, consider it potentially successful
            if chunks_sent == total_chunks:
                content_was_sent = True
                log_debug(f"[selenium] All {chunks_sent} chunks sent successfully")
            
            final_val = textarea.get_attribute("value") or ""
            log_debug(f"[selenium] value after send_keys: {len(final_val)} chars")
            
            # Check success conditions with better logic
            if len(final_val) >= len(clean) * 0.9:
                log_debug(f"[selenium] Content successfully inserted ({len(final_val)}/{len(clean)} chars)")
                return
            elif len(final_val) == 0 and content_was_sent:
                log_debug("[selenium] Textarea is empty but all chunks were sent - likely cleared by ChatGPT JS")
                # This is actually success - ChatGPT cleared the textarea after accepting input
                return
            elif len(final_val) == 0:
                log_warning("[selenium] Textarea is empty after sending, possible JS interference")
                # Try alternative approach for next attempt
                chunk_size = max(100, chunk_size // 3)
            elif len(final_val) >= len(clean) * 0.5:
                log_debug(f"[selenium] Accepting partial content as sufficient ({len(final_val)}/{len(clean)} chars)")
                return
            else:
                log_warning(f"[selenium] Partial content inserted ({len(final_val)}/{len(clean)} chars)")
                
        except StaleElementReferenceException as e:
            log_warning(f"[selenium] Stale element on send_keys attempt {attempt}: {e}")
            try:
                textarea = driver.find_element(By.ID, "prompt-textarea")
            except NoSuchElementException:
                log_error("[selenium] Could not re-locate textarea element")
                break
        except Exception as e:
            log_warning(f"[selenium] send_keys attempt {attempt} failed: {e}")
        
        chunk_size = max(200, chunk_size // 2)
    
    # If we still failed, try one more approach with smaller chunks
    if len(final_val) < len(clean) * 0.5:
        log_warning("[selenium] Attempting emergency fallback with very small chunks")
        try:
            textarea.clear()
            for char in clean[:500]:  # Limit to first 500 chars as emergency
                textarea.send_keys(char)
                time.sleep(0.01)
            final_val = textarea.get_attribute("value") or ""
            log_warning(f"[selenium] Emergency fallback result: {len(final_val)} chars")
        except Exception as e:
            log_error(f"[selenium] Emergency fallback failed: {e}")
    
    log_warning(
        f"[selenium] Failed to insert full prompt: expected {len(clean)} chars, got {len(final_val)}"
    )


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


AWAIT_RESPONSE_TIMEOUT = int(os.getenv("AWAIT_RESPONSE_TIMEOUT", "240"))
CORRECTOR_RETRIES = int(os.getenv("CORRECTOR_RETRIES", "2"))


def wait_until_response_stabilizes(
    driver: webdriver.Remote,
    max_total_wait: int = AWAIT_RESPONSE_TIMEOUT,
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
                except StaleElementReferenceException:
                    log_debug("[selenium] Prefer-response button became stale")
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
        except StaleElementReferenceException:
            log_debug("[selenium] Response element became stale, retrying...")
            time.sleep(0.5)
            continue
        except Exception as e:  # pragma: no cover - best effort
            log_warning(f"[selenium] Response wait error: {e}")
            time.sleep(0.5)
            continue

        current_len = len(text)
        changed = current_len != last_len
        log_debug(f"[DEBUG] len={current_len} changed={changed}")

        if current_len > 0 and changed:
            last_len = current_len
            last_change = time.time()
            final_text = text
        elif current_len > 0 and time.time() - last_change >= no_change_grace:
            elapsed = time.time() - start
            log_debug(
                f"[DEBUG] Response stabilized with length {current_len} after {elapsed:.1f}s"
            )
            return text

        time.sleep(0.5)


def _wait_for_button_state(driver, state: str, timeout: int) -> bool:
    """Wait until the submit button matches the desired ``state``."""
    locator = (By.ID, "composer-submit-button")
    max_retries = 3
    
    for retry in range(max_retries):
        try:
            def check_button_state(d):
                try:
                    element = d.find_element(*locator)
                    return element.get_attribute("data-testid") == state
                except StaleElementReferenceException:
                    # Element is stale, return False to trigger retry in outer loop
                    log_debug(f"[selenium] Stale element in check_button_state, retry {retry + 1}")
                    return False
                except NoSuchElementException:
                    log_debug(f"[selenium] Button element not found for state '{state}'")
                    return False
                except Exception as e:
                    log_debug(f"[selenium] Unexpected error in check_button_state: {e}")
                    return False
            
            WebDriverWait(driver, timeout).until(check_button_state)
            return True
        except (TimeoutException, StaleElementReferenceException) as e:
            if retry < max_retries - 1:
                log_debug(f"[selenium] Retry {retry + 1}/{max_retries} for button state '{state}': {str(e)}")
                time.sleep(1)  # Brief pause before retry
                continue
            else:
                log_warning(f"[selenium] Failed to wait for button state '{state}' after {max_retries} retries")
                return False
        except Exception as e:
            log_warning(f"[selenium] Unexpected error waiting for button state '{state}': {str(e)}")
            return False
    
    return False


def wait_for_chatgpt_idle(driver, timeout: int = AWAIT_RESPONSE_TIMEOUT) -> bool:
    """Wait until ChatGPT is ready for a new prompt (textarea is available and no stop button)."""
    if not wait_for_response_completion(driver, timeout):
        log_warning("[selenium] ChatGPT may still be generating during idle wait")

    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "prompt-textarea"))
        )
        log_debug("[selenium] Textarea found, ChatGPT is ready for input")
        return True
    except TimeoutException:
        log_warning("[selenium] Timeout waiting for textarea")
        return False


def wait_for_response_completion(driver, timeout: int = AWAIT_RESPONSE_TIMEOUT) -> bool:
    """Wait until the current response finishes streaming."""
    start_time = time.time()
    end_time = start_time + timeout

    try:
        driver.find_element(By.CSS_SELECTOR, "button[data-testid='stop-button']")
        log_debug(
            f"[selenium] Stop button found, waiting for response to complete with timeout {timeout} seconds"
        )
        try:
            driver.command_executor.set_timeout(timeout)
        except Exception as e:
            log_warning(f"[selenium] Could not apply command timeout: {e}")
    except NoSuchElementException:
        log_debug("[selenium] No stop button found, assuming idle")
        return True

    last_report = 0
    while time.time() < end_time:
        try:
            driver.find_element(By.CSS_SELECTOR, "button[data-testid='stop-button']")
            elapsed = int(time.time() - start_time)
            if elapsed // 10 > last_report // 10:
                log_debug(
                    f"[selenium] {elapsed} seconds passed, stop button still present"
                )
                last_report = elapsed
            time.sleep(1)
            continue
        except NoSuchElementException:
            elapsed = int(time.time() - start_time)
            log_debug(
                f"[selenium] Stop button disappeared after {elapsed} seconds, response completed"
            )
            return True
        except (ReadTimeoutError, WebDriverException) as e:
            log_warning(f"[selenium] Polling error while waiting for completion: {e}")
            time.sleep(1)

    log_warning("[selenium] Timeout waiting for response completion")
    return False



def _send_prompt_with_confirmation(textarea, prompt_text: str) -> None:
    """Send text and wait for ChatGPT's reply to finish."""
    driver = textarea._parent
    wait_for_chatgpt_idle(driver)
    for attempt in range(1, 4):
        try:
            log_debug(f"[selenium][STEP] Attempt {attempt} to send prompt")
            # Re-find textarea element in case it became stale
            try:
                textarea = WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.ID, "prompt-textarea"))
                )
            except (TimeoutException, StaleElementReferenceException) as e:
                log_warning(f"[selenium] Could not find textarea on attempt {attempt}: {e}")
                continue
            
            paste_and_send(textarea, prompt_text)
            try:
                send_btn = WebDriverWait(driver, 3).until(
                    EC.element_to_be_clickable(
                        (By.CSS_SELECTOR, "button[data-testid='send-button']")
                    )
                )
                driver.execute_script("arguments[0].click();", send_btn)
                log_debug("[selenium][STEP] Clicked send button")
            except (StaleElementReferenceException, TimeoutException) as e:
                log_warning(f"[selenium] Failed to click send button: {e}")
                try:
                    textarea.send_keys(Keys.ENTER)
                    log_debug("[selenium][STEP] Sent ENTER key as fallback")
                except StaleElementReferenceException:
                    log_warning("[selenium] Textarea became stale, retrying...")
                    continue
            log_debug("[selenium][STEP] Prompt sent, waiting for completion")
            if wait_for_response_completion(driver):
                wait_until_response_stabilizes(driver)
                log_debug("[selenium][STEP] Response stabilized")
                return
            log_warning(f"[selenium] No response after attempt {attempt}")
        except StaleElementReferenceException as e:
            log_warning(f"[selenium] Stale element on attempt {attempt}: {e}")
            continue
        except Exception as e:  # pragma: no cover - best effort
            log_warning(f"[selenium] Send attempt {attempt} failed: {e}")
    log_warning("[selenium] Fallback via ActionChains")
    try:
        ActionChains(driver).click(textarea).send_keys(prompt_text).send_keys(Keys.ENTER).perform()
        log_debug("[selenium][STEP] Fallback ActionChains used to send prompt")
        if wait_for_response_completion(driver):
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

# [FIX] helper to avoid message length limits on certain interfaces
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

    start = time.time()
    attempt = 0
    repeat_failures = 0
    last_response: Optional[str] = None
    while attempt < CORRECTOR_RETRIES and time.time() - start < AWAIT_RESPONSE_TIMEOUT:
        attempt += 1
        try:
            wait_for_chatgpt_idle(driver)
            paste_and_send(textarea, prompt_text)
            tag = (textarea.tag_name or "").lower()
            prop = "value" if tag in {"textarea", "input"} else "textContent"
            final_value = driver.execute_script(
                f"return arguments[0].{prop};", textarea
            ) or ""
            expected_len = len(strip_non_bmp(prompt_text))
            # Allow small discrepancies (e.g., trailing spaces trimmed by ChatGPT)
            if abs(expected_len - len(final_value)) > 5:
                log_warning(
                    f"[selenium] Prompt mismatch after paste: expected {expected_len} chars, got {len(final_value)}"
                )
                time.sleep(1)
                continue

            candidate = final_value.strip()
            if candidate.startswith("```"):
                match = re.match(r"```(?:json)?\n(.*)\n```", candidate, re.DOTALL)
                if match:
                    candidate = match.group(1)
            try:
                json.loads(candidate)
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

        log_debug("🔍 Waiting for response...")
        if not wait_for_response_completion(driver):
            repeat_failures += 1
            log_warning("[selenium][retry] Response did not complete")
        else:
            try:
                response_text = wait_until_response_stabilizes(driver, max_total_wait=5)
            except TimeoutException:
                log_warning("[selenium][WARN] Timeout while waiting for response")
                response_text = None
            else:
                if response_text and response_text != previous_text:
                    if not chat_id:
                        new_chat_id = _extract_chat_id(driver.current_url)
                        if new_chat_id:
                            log_debug(
                                f"[selenium] New chat ID extracted after response: {new_chat_id}"
                            )
                    return response_text.strip()

            if response_text == last_response:
                repeat_failures += 1
            else:
                repeat_failures = 0
            last_response = response_text

        if repeat_failures >= 3:
            log_warning("[selenium] Aborting after repeated empty responses")
            break

        log_warning(f"[selenium][retry] Empty response attempt {attempt}")
        remaining = AWAIT_RESPONSE_TIMEOUT - (time.time() - start)
        if remaining > 0:
            time.sleep(min(5, remaining))

    log_warning(f"[selenium] Aborting after {attempt} attempts")
    screenshots_dir = os.path.join(_LOG_DIR, "screenshots")
    os.makedirs(screenshots_dir, exist_ok=True)
    fname = os.path.join(screenshots_dir, f"chat_{chat_id or 'unknown'}_no_response.png")
    try:
        driver.save_screenshot(fname)
        log_warning(f"[selenium] Saved screenshot to {fname}")
    except Exception as e:
        log_warning(f"[selenium] Failed to save screenshot: {e}")
    notify_trainer(
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
#         new_title = f"⚙️{emoji} Chat/{chat_name}{thread} - 1"
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
    max_retries = 3
    for retry in range(max_retries):
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
            break  # Exit retry loop if we got the info we need
        except StaleElementReferenceException as e:
            if retry < max_retries - 1:
                log_debug(f"[chatgpt_model] Stale element, retry {retry + 1}/{max_retries}: {e}")
                time.sleep(1)
                continue
            else:
                log_warning(f"[chatgpt_model] Failed to get model info after {max_retries} retries")
                return False
        except Exception as e:
            log_warning(f"[chatgpt_model] Error getting current model: {e}")
            return False

        log_debug("[chatgpt_model] Opening dropdown")
        try:
            # Re-locate switcher button to avoid stale element
            switcher_btn = _locate_model_switcher(driver)
            try:
                switcher_btn.find_element(By.XPATH, "./div").click()
            except (StaleElementReferenceException, NoSuchElementException):
                switcher_btn.click()
        except StaleElementReferenceException:
            log_warning("[chatgpt_model] Switcher button became stale, retrying...")
            switcher_btn = _locate_model_switcher(driver)
            switcher_btn.click()
        except Exception as e:
            log_warning(f"[chatgpt_model] Failed to click switcher button: {e}")
            return False
            
        try:
            WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div[role='menu']"))
            )
            log_debug("[chatgpt_model] Dropdown opened")
        except TimeoutException:
            log_warning("[chatgpt_model] Dropdown failed to open")
            return False

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

        try:
            log_debug("[chatgpt_model] Clicking desired model")
            ActionChains(driver).move_to_element(model_elem).click().perform()
            log_info(f"[chatgpt_model] Clicked on model {CHATGPT_MODEL}")
        except StaleElementReferenceException:
            log_warning("[chatgpt_model] Model element became stale, clicking with JS")
            driver.execute_script("arguments[0].click();", model_elem)
        except Exception as e:
            log_warning(f"[chatgpt_model] Failed to click model element: {e}")
            return False
            
        try:
            # Wait and verify the model was selected
            def check_model_selected(d):
                try:
                    switcher = _locate_model_switcher(d)
                    aria_label = switcher.get_attribute("aria-label") or ""
                    return CHATGPT_MODEL in aria_label
                except StaleElementReferenceException:
                    return False
                except Exception:
                    return False
                    
            WebDriverWait(driver, 5).until(check_model_selected)
            log_info(f"[chatgpt_model] Modello selezionato: {CHATGPT_MODEL}")
            return True
        except TimeoutException:
            try:
                new_label = _locate_model_switcher(driver).get_attribute("aria-label") or ""
                log_warning(f"[chatgpt_model] Verifica modello fallita: {new_label}")
            except StaleElementReferenceException:
                log_warning("[chatgpt_model] Could not verify model selection - stale element")
            except Exception as verify_e:
                log_warning(f"[chatgpt_model] Could not verify model selection: {verify_e}")
            return False
        except Exception as click_e:
            log_warning(f"[chatgpt_model] Error during model verification: {click_e}")
            return False
        log_warning(f"[chatgpt_model] Errore selezione modello: {repr(e)}")
        try:
            screenshots_dir = os.path.join(_LOG_DIR, "screenshots")
            os.makedirs(screenshots_dir, exist_ok=True)
            screenshot_path = os.path.join(screenshots_dir, "model_switch_error.png")
            driver.save_screenshot(screenshot_path)
            log_warning(
                f"[chatgpt_model] Saved screenshot {screenshot_path}"
            )
        except Exception as ss:
            log_warning(f"[chatgpt_model] Screenshot failed: {ss}")
        return False

class SeleniumChatGPTPlugin(AIPluginBase):
    # [FIX] shared locks per chat
    chat_locks: defaultdict[int, asyncio.Lock] = defaultdict(asyncio.Lock)
    def __init__(self, notify_fn=None):
        """Initialize the plugin without starting Selenium yet."""
        self.driver = None
        self._queue: asyncio.Queue = asyncio.Queue()
        self._worker_task = None
        self._notify_fn = notify_fn or notify_trainer
        log_debug(f"[selenium] notify_fn passed: {bool(notify_fn)}")
        set_notifier(self._notify_fn)

        # Unique identifier for this instance to isolate Chromium resources
        self.instance_id = os.getenv("RFP_INSTANCE_ID", str(os.getpid()))
        self.profile_dir: Optional[str] = None

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
                log_debug("[selenium] Chromium driver closed")
            except Exception as e:
                log_warning(f"[selenium] Failed to close driver: {e}")
            finally:
                self.driver = None
        
        # Remove any remaining Chromium processes and locks
        self._cleanup_chromium_remnants()

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
            log_warning(
                f"[selenium] Worker task crashed: {fut.exception()}", fut.exception()
            )
        # Attempt restart if needed
        try:
            loop = asyncio.get_running_loop()
            if loop.is_running():
                loop.create_task(self.start())
        except RuntimeError:
            pass

    def _apply_driver_timeouts(self) -> None:
        """Apply environment-based timeouts to the Selenium driver."""
        if not self.driver:
            return
        try:
            self.driver.command_executor.set_timeout(AWAIT_RESPONSE_TIMEOUT)
            self.driver.set_page_load_timeout(AWAIT_RESPONSE_TIMEOUT)
            self.driver.set_script_timeout(AWAIT_RESPONSE_TIMEOUT)
            log_debug(
                f"[selenium] Driver timeouts set to {AWAIT_RESPONSE_TIMEOUT}s"
            )
        except Exception as e:
            log_warning(f"[selenium] Failed to set driver timeouts: {e}")

    def _locate_chromium_binary(self) -> str:
        """Return path to the Chromium executable, checking common locations."""
        chromium_binary = (
            shutil.which("chromium")
            or shutil.which("chromium-browser")
            or "/usr/bin/chromium"
        )
        log_debug(f"[selenium] Using Chromium binary: {chromium_binary}")
        return chromium_binary

    def _get_chromium_major_version(self, binary: str) -> Optional[int]:
        """Return the major version of the given Chromium binary."""
        try:
            output = subprocess.check_output([binary, "--version"], text=True)
            match = re.search(r"(\d+)\.", output)
            if match:
                return int(match.group(1))
        except Exception as e:
            log_warning(f"[selenium] Unable to determine Chromium version: {e}")
        return None

    def _init_driver(self):
        if self.driver is None:
            log_debug("[selenium] [STEP] Initializing Chromium driver with undetected-chromedriver")

            # Clean up any leftover processes and files from previous runs
            self._cleanup_chromium_remnants()

            # Ensure DISPLAY is set
            if not os.environ.get("DISPLAY"):
                os.environ["DISPLAY"] = ":0"
                log_debug("[selenium] DISPLAY not set, defaulting to :0")

            # Precompute logging and service configuration so they remain available
            chromium_level = os.environ.get("CHROMIUM_LOG_LEVEL", "1")
            log_dir = "/app/logs"
            os.makedirs(log_dir, exist_ok=True)
            chromium_log_path = os.path.join(log_dir, "chromium.log")
            uc_log_path = os.path.join(log_dir, "undetected_chromedriver.log")
            selenium_log_path = os.path.join(log_dir, "selenium.log")
            service = Service(log_path=uc_log_path)

            # Ensure Chromium writes verbose logs to the desired location
            os.environ["CHROME_LOG_FILE"] = chromium_log_path
            log_debug(
                f"[selenium] Chromium logs directed to {chromium_log_path} with verbosity {chromium_level}"
            )

            # Configure Python logging for selenium and undetected-chromedriver modules
            formatter = logging.Formatter(
                "[%(asctime)s] [%(levelname)s] [%(filename)s:%(lineno)d] %(message)s",
                "%Y-%m-%d %H:%M:%S",
            )
            for name, path in (
                ("selenium", selenium_log_path),
                ("undetected_chromedriver", uc_log_path),
            ):
                logger = logging.getLogger(name)
                if not any(
                    isinstance(h, logging.FileHandler) and getattr(h, "baseFilename", "") == path
                    for h in logger.handlers
                ):
                    fh = logging.FileHandler(path)
                    fh.setFormatter(formatter)
                    logger.addHandler(fh)
                logger.setLevel(logging.DEBUG)

            # Essential Chromium arguments reused across attempts
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
                "--enable-logging",
                f"--v={chromium_level}",
                "--remote-debugging-port=0",
                "--disable-background-mode",
                "--disable-default-browser-check",
                "--disable-hang-monitor",
                "--disable-prompt-on-repost",
                "--disable-sync",
                "--metrics-recording-only",
                "--no-default-browser-check",
                "--safebrowsing-disable-auto-update",
                "--disable-client-side-phishing-detection",
            ]

            # Use a shared profile directory to maintain login sessions
            config_home = os.getenv(
                "XDG_CONFIG_HOME",
                os.path.join(os.path.expanduser("~"), ".config"),
            )
            profile_dir = os.path.join(config_home, "chromium-rfp")
            self.profile_dir = profile_dir

            chromium_binary = self._locate_chromium_binary()
            chromium_major = self._get_chromium_major_version(chromium_binary)
            if chromium_major:
                log_debug(f"[selenium] Detected Chromium major version {chromium_major}")
            else:
                log_warning("[selenium] Could not detect Chromium version; using default driver")

            # Try multiple times with increasing delays
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    log_debug(f"[selenium] Initialization attempt {attempt + 1}/{max_retries}")

                    # Create Chromium options optimized for container environments
                    options = uc.ChromeOptions()

                    # Configure Chromium/chromedriver logging based on LOGGING_LEVEL
                    os.makedirs(_LOG_DIR, exist_ok=True)
                    log_path = os.path.join(_LOG_DIR, "chromium.log")
                    service_log_path = os.path.join(_LOG_DIR, "chromedriver.log")
                    service = Service(log_path=service_log_path, service_args=["--verbose"])
                    log_debug(
                        f"[selenium] Chromium log -> {log_path}, chromedriver log -> {service_log_path}"
                    )

                    logging_level = os.getenv("LOGGING_LEVEL", "ERROR").upper()
                    level_map = {"DEBUG": 0, "INFO": 0, "WARNING": 1, "ERROR": 2, "CRITICAL": 2}
                    chromium_level = level_map.get(logging_level, 2)

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
                        "--enable-logging",
                        f"--log-level={chromium_level}",
                        f"--log-file={log_path}",
                        "--remote-debugging-port=0",
                        "--disable-background-mode",
                        "--disable-default-browser-check",
                        "--disable-hang-monitor",
                        "--disable-prompt-on-repost",
                        "--disable-sync",
                        "--metrics-recording-only",
                        "--no-default-browser-check",
                        "--safebrowsing-disable-auto-update",
                        "--disable-client-side-phishing-detection",
                    ]
                    for arg in essential_args:
                        options.add_argument(arg)
                    options.add_argument(f"--user-data-dir={profile_dir}")

                    # Clear any existing driver cache
                    import tempfile
                    import shutil
                    uc_cache_dir = os.path.join(tempfile.gettempdir(), 'undetected_chromedriver')
                    if os.path.exists(uc_cache_dir):
                        shutil.rmtree(uc_cache_dir, ignore_errors=True)
                        log_debug("[selenium] Cleared undetected-chromedriver cache")

                    # Try with explicit Chromium binary
                    log_debug(
                        f"[selenium] Calling {chromium_binary} {' '.join(options.arguments)}"
                    )
                    headless_env = os.getenv("CHROMIUM_HEADLESS", "0").lower()
                    headless = headless_env in ("1", "true", "yes")
                    log_debug(
                        f"[selenium] Headless mode {'enabled' if headless else 'disabled'}"
                    )
                    self.driver = uc.Chrome(
                        options=options,
                        service=service,
                        headless=headless,
                        use_subprocess=True,
                        version_main=chromium_major,
                        suppress_welcome=True,
                        log_level=int(chromium_level),
                        driver_executable_path=None,  # Let UC handle chromedriver
                        browser_executable_path=chromium_binary,
                        user_data_dir=profile_dir
                    )
                    self._apply_driver_timeouts()
                    log_debug(
                        "[selenium] ✅ Chromium successfully initialized with undetected-chromedriver"
                    )
                    return  # Success, exit

                except Exception as e:
                    log_warning(f"[selenium] Attempt {attempt + 1} failed: {e}")

                    # Handle specific Python shutdown error
                    if "sys.meta_path is None" in str(e) or "Python is likely shutting down" in str(e):
                        log_warning("[selenium] Python shutdown detected, skipping Chromium initialization")
                        return None

                    # Clean up before next attempt
                    if self.driver:
                        try:
                            self.driver.quit()
                        except:
                            pass
                        self.driver = None

                    self._cleanup_chromium_remnants()

                    if attempt < max_retries - 1:
                        delay = (attempt + 1) * 2  # 2, 4, 6 seconds
                        log_debug(f"[selenium] Waiting {delay}s before next attempt...")
                        time.sleep(delay)
                    else:
                        # Final attempt with explicit Chromium binary
                        log_debug("[selenium] Final attempt with explicit Chromium binary path...")
                        try:
                            if os.path.exists(chromium_binary):
                                # Create fresh ChromiumOptions for fallback attempt
                                fallback_options = uc.ChromeOptions()
                                for arg in essential_args:
                                    fallback_options.add_argument(arg)
                                fallback_options.add_argument(f"--user-data-dir={profile_dir}")
                                log_debug(
                                    f"[selenium] Calling chromium with command: {chromium_binary} {' '.join(fallback_options.arguments)}"
                                )
                                self.driver = uc.Chrome(
                                    options=fallback_options,
                                    service=service,
                                    headless=False,
                                    use_subprocess=True,
                                    version_main=chromium_major,
                                    suppress_welcome=True,
                                    log_level=int(chromium_level),
                                    browser_executable_path=chromium_binary,
                                    user_data_dir=profile_dir
                                )
                                self._apply_driver_timeouts()
                                log_debug(
                                    "[selenium] ✅ Chromium initialized with explicit binary path"
                                )
                                return
                            else:
                                raise Exception("Chromium binary not found")

                        except Exception as e2:
                            log_warning("[selenium] Chromium lock suspected - attempting forced lock cleanup...")
                            self._cleanup_chromium_remnants()
                            try:
                                if os.path.exists(chromium_binary):
                                    fallback_options = uc.ChromeOptions()
                                    for arg in essential_args:
                                        fallback_options.add_argument(arg)
                                    fallback_options.add_argument(f"--user-data-dir={profile_dir}")
                                    log_debug(
                                        f"[selenium] Calling chromium with command: {chromium_binary} {' '.join(fallback_options.arguments)}"
                                    )
                                    self.driver = uc.Chrome(
                                        options=fallback_options,
                                        service=service,
                                        headless=False,
                                        use_subprocess=True,
                                        version_main=chromium_major,
                                        suppress_welcome=True,
                                        log_level=int(chromium_level),
                                        browser_executable_path=chromium_binary,
                                        user_data_dir=profile_dir
                                    )
                                    self._apply_driver_timeouts()
                                    log_debug(
                                        "[selenium] ✅ Chromium initialized after forced lock cleanup"
                                    )
                                    return
                                else:
                                    raise Exception("Chromium binary not found")
                            except Exception as e3:
                                log_error(
                                    f"[selenium] ❌ All initialization attempts failed: {e3}"
                                )
                                _notify_gui(
                                    f"❌ Selenium error: {e3}. Check graphics environment."
                                )
                                # Propagate error without shutting down the whole process
                                raise RuntimeError(
                                    f"Chromium initialization failed after retries: {e3}"
                                )

    def _cleanup_chromium_remnants(self):
        """Clean up Chromium processes and leftover lock files."""
        try:
            parent_pid = str(os.getpid())
            subprocess.run(
                ["pkill", "-P", parent_pid, "-f", "chromium"],
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["pkill", "-P", parent_pid, "-f", "chromedriver"],
                capture_output=True,
                text=True,
            )
            log_debug("[selenium] Issued pkill for chromium and chromedriver owned by this process")
            time.sleep(1)
        except Exception as e:
            log_debug(f"[selenium] Failed to kill chromium processes: {e}")

        try:
            patterns = []
            if self.instance_id:
                patterns.append(f"/tmp/.org.chromium.*{self.instance_id}*")
                patterns.append(f"/tmp/chromium_{self.instance_id}*")

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

        log_debug("[selenium] Chromium lock cleanup complete")
        try:
            root_pwd = os.getenv("ROOT_PASSWORD")
            if not root_pwd:
                log_debug("[selenium] ROOT_PASSWORD not set; skipping /config permission reset")
            else:
                cmds = [
                    ["chown", "-R", "abc:abc", "/config"],
                    ["chmod", "ug+rwx", "-R", "/config"],
                ]
                for cmd in cmds:
                    subprocess.run(
                        ["sudo", "-S", *cmd],
                        input=f"{root_pwd}\n",
                        text=True,
                        check=False,
                    )
        except Exception as e:
            log_debug(f"[selenium] Failed to reset /config permissions: {e}")

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
        try:
            self.driver.find_element(By.TAG_NAME, "textarea")
            log_debug("[selenium] Logged in and ready")
            return True
        except Exception:
            _notify_gui("🔐 Login or challenge detected. Open UI")
            return False

    async def _send_error_message(self, bot, message, error_text="😵‍💫"):
        """Send an error message to the chat."""
        send_params = {
            "chat_id": message.chat_id,
            "text": error_text,
        }
        reply_id = getattr(message, "message_id", None)
        if reply_id is not None:
            send_params["reply_to_message_id"] = reply_id
        message_thread_id = getattr(message, "message_thread_id", None)
        if message_thread_id is not None:
            send_params["message_thread_id"] = message_thread_id
        await bot.send_message(**send_params)
        log_debug(
            f"[selenium][STEP] error response forwarded to {message.chat_id}"
        )

    async def _process_message(self, bot, message, prompt):
        """Send the prompt to ChatGPT and forward the response."""
        log_debug(f"[selenium][STEP] processing prompt: {prompt}")

        max_attempts = 3
        for attempt in range(max_attempts):
            driver = self._get_driver()
            if not driver:
                log_error("[selenium] WebDriver unavailable, aborting")
                _notify_gui("\u274c Selenium driver not available. Open UI")
                await self._send_error_message(bot, message)
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
                    await self._send_error_message(bot, message)
                    return

            if not self._ensure_logged_in():
                if attempt == max_attempts - 1:
                    await self._send_error_message(bot, message)
                    return
                time.sleep(2 * (attempt + 1))
                continue

            log_debug("[selenium][STEP] ensuring ChatGPT is accessible")

            interface_name = (
                bot.get_interface_id() if hasattr(bot, "get_interface_id") else "generic"
            )
            message_thread_id = getattr(message, "message_thread_id", None)
            chat_id = await chat_link_store.get_link(
                message.chat_id, message_thread_id, interface=interface_name
            )
            prompt_text = json.dumps(prompt, ensure_ascii=False)
            if isinstance(prompt, dict) and "system_message" in prompt:
                prompt_text = f"```json\n{prompt_text}\n```"
            if not chat_id:
                path = recent_chats.get_chat_path(message.chat_id)
                if path and go_to_chat_by_path_with_retries(driver, path):
                    chat_id = _extract_chat_id(driver.current_url)
                    if chat_id:
                        await chat_link_store.save_link(
                            message.chat_id,
                            message_thread_id,
                            chat_id,
                            interface=interface_name,
                        )
                        _safe_notify(
                            f"\u26a0\ufe0f Couldn't find ChatGPT conversation for chat_id={message.chat_id}, message_thread_id={message_thread_id}.\n"
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
                    WebDriverWait(driver, 120).until(
                        EC.presence_of_element_located((By.TAG_NAME, "textarea"))
                    )
                    log_debug(f"[selenium] Successfully accessed existing chat: {chat_id}")
                except TimeoutException:
                    log_warning("[selenium] ChatGPT UI not ready after loading existing chat")
                    if attempt == max_attempts - 1:
                        _notify_gui("\u274c ChatGPT UI not ready. Open UI")
                        await self._send_error_message(bot, message)
                        return
                    time.sleep(2 * (attempt + 1))
                    continue
                except Exception as e:
                    log_warning(f"[selenium] Existing chat {chat_id} no longer accessible: {e}")
                    log_info(f"[selenium] Creating new chat to replace inaccessible chat {chat_id}")
                    await chat_link_store.remove(
                        message.chat_id, message_thread_id, interface=interface_name
                    )
                    recent_chats.clear_chat_path(message.chat_id)
                    _open_new_chat(driver)
                    chat_id = None

            log_debug(f"[selenium][DEBUG] Chat ID from store: {chat_id}")
            log_debug(
                f"[selenium][DEBUG] source chat_id: {message.chat_id}, message_thread_id: {message_thread_id}"
            )

            if not chat_id:
                try:
                    driver.get("https://chat.openai.com")
                    WebDriverWait(driver, 180).until(
                        EC.presence_of_element_located((By.TAG_NAME, "textarea"))
                    )
                except TimeoutException:
                    log_warning("[selenium][ERROR] ChatGPT UI failed to become ready")
                    if attempt == max_attempts - 1:
                        _notify_gui("\u274c Selenium error: ChatGPT UI not ready. Open UI")
                        await self._send_error_message(bot, message)
                        return
                    time.sleep(2 * (attempt + 1))
                    continue
                except Exception:
                    log_warning("[selenium][ERROR] ChatGPT UI failed to load")
                    if attempt == max_attempts - 1:
                        _notify_gui("\u274c Selenium error: ChatGPT UI not ready. Open UI")
                        await self._send_error_message(bot, message)
                        return
                    time.sleep(2 * (attempt + 1))
                    continue

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
                            await chat_link_store.save_link(
                                message.chat_id,
                                message_thread_id,
                                new_chat_id,
                                interface=interface_name,
                            )
                            log_debug(
                                f"[selenium][DEBUG] Saved link: {message.chat_id}/{message_thread_id} -> {new_chat_id}"
                            )
                            _safe_notify(
                                f"\u26a0\ufe0f Couldn't find ChatGPT conversation for chat_id={message.chat_id}, message_thread_id={message_thread_id}.\n"
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
                        await chat_link_store.save_link(
                            message.chat_id,
                            message_thread_id,
                            new_chat_id,
                            interface=interface_name,
                        )
                        log_debug(
                            f"[selenium][SUCCESS] New chat created for full conversation. Chat ID: {new_chat_id}"
                        )
                    queue_paused = False

                if not response_text:
                    response_text = json.dumps({"actions": []})

                send_params = {
                    "chat_id": message.chat_id,
                    "text": response_text,
                }
                reply_id = getattr(message, "message_id", None)
                if reply_id is not None:
                    send_params["reply_to_message_id"] = reply_id
                if message_thread_id is not None:
                    send_params["message_thread_id"] = message_thread_id
                await bot.send_message(**send_params)
                log_debug(
                    f"[selenium][STEP] response forwarded to {message.chat_id}"
                )
                return

            except Exception as e:
                log_error(f"[selenium][ERROR] failed to process message: {repr(e)}", e)
                _notify_gui(f"\u274c Selenium error: {e}. Open UI")
                return

    @staticmethod
    async def clean_chat_link(chat_id: int, interface: str) -> str:
        """Remove the association between a chat and a ChatGPT conversation.
        If no link exists for the current chat, creates a new one."""
        try:
            if await chat_link_store.remove(chat_id, None, interface=interface):
                log_debug(f"[clean_chat_link] Chat link removed for chat_id={chat_id}")
                return f"✅ Link for chat_id={chat_id} successfully removed."
            else:
                new_chat_id = f"new_chat_{chat_id}"
                await chat_link_store.save_link(
                    chat_id, None, new_chat_id, interface=interface
                )
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

        interface_name = (
            bot.get_interface_id() if hasattr(bot, "get_interface_id") else "generic"
        )

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
                    result = await SeleniumChatGPTPlugin.clean_chat_link(chat_id, interface_name)
                    await bot.send_message(chat_id=chat_id, text=result)
                else:
                    await bot.send_message(chat_id=chat_id, text="❌ Operation canceled.")
            except asyncio.TimeoutError:
                await bot.send_message(chat_id=chat_id, text="⏳ Timeout. Operation canceled.")
        else:
            result = await SeleniumChatGPTPlugin.clean_chat_link(chat_id, interface_name)
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
                    f"[selenium] [WORKER] Processing chat_id={message.chat_id} "
                    f"message_id={getattr(message, 'message_id', 'unknown')}"
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
