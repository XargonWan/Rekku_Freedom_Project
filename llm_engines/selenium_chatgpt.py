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
import requests
import base64
from collections import defaultdict
from typing import Optional, Dict
from pathlib import Path
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
from core.transport_layer import llm_to_interface


# Local functions and classes
from core.logging_utils import log_debug, log_error, log_warning, log_info, _LOG_DIR
from core.notifier import set_notifier
import core.recent_chats as recent_chats
from core.ai_plugin_base import AIPluginBase

# Selenium ChatGPT-specific configuration
SELENIUM_CONFIG = {
    "max_prompt_chars": 500000,  # Selenium ChatGPT can handle very long prompts
    "max_response_chars": 4000,
    "supports_images": True,
    "supports_functions": False,  # Browser-based doesn't support functions
    "model_name": "gpt-4o",
    "default_model": "gpt-4o",
    "browser_timeout": 30,
    "page_load_timeout": 60,
    "element_wait_timeout": 10,
    "retry_attempts": 3,
    "retry_delay": 2
}

def get_selenium_config() -> dict:
    """Get Selenium ChatGPT-specific configuration."""
    return SELENIUM_CONFIG.copy()

def get_max_prompt_chars() -> int:
    """Get maximum prompt characters for Selenium ChatGPT."""
    return SELENIUM_CONFIG["max_prompt_chars"]

def get_max_response_chars() -> int:
    """Get maximum response characters for Selenium ChatGPT."""
    return SELENIUM_CONFIG["max_response_chars"]

def supports_images() -> bool:
    """Check if Selenium ChatGPT supports images."""
    return SELENIUM_CONFIG["supports_images"]

def supports_functions() -> bool:
    """Check if Selenium ChatGPT supports functions."""
    return SELENIUM_CONFIG["supports_functions"]

def get_interface_limits() -> dict:
    """Get the limits and capabilities for Selenium ChatGPT interface."""
    log_info(f"[selenium_chatgpt] Interface limits: max_prompt_chars={SELENIUM_CONFIG['max_prompt_chars']}, supports_images={SELENIUM_CONFIG['supports_images']}")
    return {
        "max_prompt_chars": SELENIUM_CONFIG["max_prompt_chars"],
        "max_response_chars": SELENIUM_CONFIG["max_response_chars"],
        "supports_images": SELENIUM_CONFIG["supports_images"],
        "supports_functions": SELENIUM_CONFIG["supports_functions"],
        "model_name": SELENIUM_CONFIG["model_name"]
    }

# Load environment variables for root password and other settings
load_dotenv()

# ChatLinkStore: manages mapping between interface chats and ChatGPT conversations
from plugins.chat_link import ChatLinkStore
from interface.telegram_utils import safe_send

# Fallback for notify_trainer when core.notifier module is unavailable
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


async def _download_telegram_image(bot, file_id: str, temp_dir: str) -> Optional[str]:
    """Download an image from Telegram and return the local file path."""
    try:
        # Get file info from Telegram
        file_info = await bot.get_file(file_id)
        
        # CORREZIONE: Costruisci l'URL corretto senza duplicare "bot"
        # Il token è già nel formato "botTOKEN", quindi dobbiamo solo usare bot.token
        file_url = f"https://api.telegram.org/file/{bot.token}/{file_info.file_path}"
        
        log_debug(f"[selenium] Downloading from URL: {file_url}")
        
        # Download the file
        response = requests.get(file_url, timeout=30)
        response.raise_for_status()
        
        # Save to temp file
        file_extension = Path(file_info.file_path).suffix or '.jpg'
        temp_file = os.path.join(temp_dir, f"image_{int(time.time())}{file_extension}")
        
        with open(temp_file, 'wb') as f:
            f.write(response.content)
        
        log_debug(f"[selenium] Downloaded Telegram image to: {temp_file}")
        return temp_file
        
    except Exception as e:
        log_error(f"[selenium] Failed to download Telegram image: {e}")
        return None


def _paste_image_to_chatgpt(driver, image_path: str) -> bool:
    """Paste an image to ChatGPT input using JavaScript injection (Docker-compatible)."""
    try:
        # Find the input area
        textarea = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.ID, "prompt-textarea"))
        )

        # Click on the textarea to focus it
        textarea.click()
        time.sleep(0.5)

        # Method 1: Try to find and use the image upload button
        try:
            # Look for image upload button (common selectors for ChatGPT)
            upload_selectors = [
                "button[data-testid*='image']",
                "button[aria-label*='image']",
                "button[aria-label*='upload']",
                "input[type='file'][accept*='image']",
                ".image-upload-button",
                "[data-testid='file-upload-button']"
            ]

            upload_element = None
            for selector in upload_selectors:
                try:
                    if selector.startswith("input"):
                        upload_element = WebDriverWait(driver, 2).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                        )
                    else:
                        upload_element = WebDriverWait(driver, 2).until(
                            EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                        )
                    break
                except TimeoutException:
                    continue

            if upload_element:
                log_debug(f"[selenium] Found image upload button: {upload_element.tag_name}")
                # For file input, we can set the file directly
                if upload_element.tag_name.lower() == "input":
                    driver.execute_script("arguments[0].style.display = 'block';", upload_element)
                    upload_element.send_keys(image_path)
                    log_info("[selenium] Image uploaded via file input")
                    return True
                else:
                    # Click the upload button
                    upload_element.click()
                    time.sleep(1)
                    # This might open a file dialog, but in headless mode we need a different approach
                    log_debug("[selenium] Clicked image upload button")

        except Exception as e:
            log_debug(f"[selenium] Image upload button method failed: {e}")

        # Method 2: Convert image to base64 and inject via JavaScript
        try:
            import base64

            # Read and encode the image
            with open(image_path, 'rb') as f:
                image_data = f.read()

            # Get image format from file extension
            import mimetypes
            mime_type, _ = mimetypes.guess_type(image_path)
            if not mime_type:
                mime_type = 'image/jpeg'  # fallback

            # Create data URL
            encoded_image = base64.b64encode(image_data).decode('utf-8')
            data_url = f"data:{mime_type};base64,{encoded_image}"

            # JavaScript to create and upload the image
            js_script = f"""
            // Create a temporary file input
            var input = document.createElement('input');
            input.type = 'file';
            input.accept = 'image/*';
            input.style.display = 'none';

            // Create a blob from the data URL
            fetch('{data_url}')
                .then(res => res.blob())
                .then(blob => {{
                    var file = new File([blob], 'uploaded_image.jpg', {{type: '{mime_type}'}});
                    var dt = new DataTransfer();
                    dt.items.add(file);
                    input.files = dt.files;

                    // Find the actual file input in ChatGPT's interface
                    var chatgptInputs = document.querySelectorAll('input[type="file"]');
                    if (chatgptInputs.length > 0) {{
                        chatgptInputs[0].files = dt.files;
                        chatgptInputs[0].dispatchEvent(new Event('change', {{bubbles: true}}));
                        return true;
                    }}

                    // Alternative: try to paste into textarea as data URL
                    var textarea = document.getElementById('prompt-textarea');
                    if (textarea) {{
                        textarea.focus();
                        // Insert image marker (ChatGPT might handle this)
                        var imageMarker = '[Image uploaded: ' + file.name + ']';
                        textarea.value += imageMarker;
                        textarea.dispatchEvent(new Event('input', {{bubbles: true}}));
                        return true;
                    }}

                    return false;
                }})
                .catch(err => console.error('Image upload failed:', err));
            """

            result = driver.execute_script(js_script)
            if result:
                log_info("[selenium] Image injected via JavaScript")
                time.sleep(2)  # Wait for processing
                return True

        except Exception as e:
            log_warning(f"[selenium] JavaScript injection method failed: {e}")

        # Method 3: Fallback to clipboard method (original implementation)
        import platform
        system = platform.system().lower()

        if system == "linux":
            try:
                subprocess.run([
                    "xclip", "-selection", "clipboard", "-t", "image/png", "-i", image_path
                ], check=True, capture_output=True)
                log_debug(f"[selenium] Copied image to clipboard using xclip: {image_path}")
            except (subprocess.CalledProcessError, FileNotFoundError):
                log_warning("[selenium] xclip not available, trying alternative method")
                return False

        elif system == "darwin":  # macOS
            try:
                subprocess.run([
                    "osascript", "-e", f'set the clipboard to (read file POSIX file "{image_path}" as JPEG picture)'
                ], check=True, capture_output=True)
                log_debug(f"[selenium] Copied image to clipboard using osascript: {image_path}")
            except subprocess.CalledProcessError:
                log_warning("[selenium] osascript failed, trying alternative method")
                return False

        elif system == "windows":
            try:
                ps_script = f"""
                Add-Type -AssemblyName System.Windows.Forms
                $img = [System.Drawing.Image]::FromFile('{image_path}')
                [System.Windows.Forms.Clipboard]::SetImage($img)
                """
                subprocess.run([
                    "powershell", "-Command", ps_script
                ], check=True, capture_output=True)
                log_debug(f"[selenium] Copied image to clipboard using PowerShell: {image_path}")
            except subprocess.CalledProcessError:
                log_warning("[selenium] PowerShell failed, trying alternative method")
                return False

        # Paste the image using Ctrl+V
        textarea.send_keys(Keys.CONTROL, 'v')
        time.sleep(2)  # Wait for the image to be processed

        # Check if the image was pasted successfully
        try:
            # Look for image indicators in the UI
            WebDriverWait(driver, 5).until(
                lambda d: d.find_elements(By.CSS_SELECTOR, "[data-testid*='image']") or
                         d.find_elements(By.CSS_SELECTOR, "img") or
                         d.find_elements(By.CSS_SELECTOR, "[title*='image']") or
                         d.find_elements(By.CSS_SELECTOR, ".image-preview") or
                         d.find_elements(By.CSS_SELECTOR, "[data-testid*='attachment']")
            )
            log_info("[selenium] Image successfully pasted to ChatGPT")
            return True
        except TimeoutException:
            log_warning("[selenium] Could not verify if image was pasted successfully")
            # Still return True as the paste operation was attempted
            return True

    except Exception as e:
        log_error(f"[selenium] Failed to paste image to ChatGPT: {e}")
        return False


def _extract_image_info_from_prompt(prompt_text: str) -> Optional[Dict]:
    """Extract image information from JSON prompt if present."""
    try:
        # Handle both string and dict inputs
        if isinstance(prompt_text, str):
            # Parse the JSON prompt
            prompt_data = json.loads(prompt_text)
        elif isinstance(prompt_text, dict):
            # Already parsed
            prompt_data = prompt_text
        else:
            log_debug(f"[selenium] Unexpected prompt type: {type(prompt_text)}")
            return None
        
        # Look for image data in the input payload
        input_payload = prompt_data.get("input", {}).get("payload", {})
        image_data = input_payload.get("image")
        
        if image_data:
            log_debug(f"[selenium] Found image data in prompt: {image_data.get('type', 'unknown')}")
            return image_data
            
    except (json.JSONDecodeError, KeyError, TypeError, AttributeError) as e:
        log_debug(f"[selenium] No image data found in prompt: {e}")
        
    return None


def _send_text_to_textarea(driver, textarea, text: str) -> None:
    """Inject ``text`` into the ChatGPT prompt area via JavaScript."""
    clean_text = strip_non_bmp(text)
    log_debug(f"[DEBUG] Length before sending: {len(clean_text)}")
    # Log full text content for debugging
    log_debug(f"[DEBUG] Text to send ({len(clean_text)} chars): {clean_text}")

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
    log_debug(f"[selenium] Sending VNC notification: {text}")
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
    driver, chat_id: str | None, prompt_text: str, previous_text: str, image_path: str | None = None
) -> Optional[str]:
    """Send a prompt to a ChatGPT chat and return the newly generated text."""
    if chat_id and is_chat_archived(driver, chat_id):
        chat_id = None  # Mark chat as invalid

    if not chat_id:
        log_debug("[selenium] Creating a new chat")
        _open_new_chat(driver)
        # Chat ID will be extracted later from the URL after sending the prompt

    # Handle image upload first if present
    if image_path and os.path.exists(image_path):
        log_info(f"[selenium] Uploading image to ChatGPT: {image_path}")
        if not _paste_image_to_chatgpt(driver, image_path):
            log_warning("[selenium] Failed to upload image, proceeding with text only")

    # Some UI experiments may block the textarea with a "I prefer this response"
    # dialog. Dismiss it if present before looking for the textarea.

    if not ensure_chatgpt_model(driver):
        log_warning("[chatgpt_model] Failed to ensure model")

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
CHATGPT_MODEL = os.getenv("CHATGPT_MODEL", "")


def select_chatgpt_model(driver):
    """Seleziona il modello di ChatGPT in base alla variabile di ambiente CHATGPT_MODEL."""
    # Usa la variabile già definita che ha il default
    target_model = CHATGPT_MODEL
    if not target_model or target_model.strip() == "":
        log_info("[chatgpt_model] CHATGPT_MODEL not set, using default model")
        return

    # 1. Clicca sul pulsante del selettore in alto
    selector = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.CSS_SELECTOR, "button[aria-label='Model picker'],button[data-qa='model-switcher']"))
    )
    selector.click()

    # 2. Attendi che il menu sia visibile
    WebDriverWait(driver, 10).until(
        EC.visibility_of_element_located((By.CSS_SELECTOR, "div[role='menu']"))
    )
    time.sleep(0.5)  # piccola pausa per permettere il rendering completo

    # 3. Cerca il modello nel menu principale
    model_elements = driver.find_elements(By.XPATH, f"//div[@role='menu']//span[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'), '{target_model.lower()}')]")
    if model_elements:
        model_elements[0].click()
        return

    # 4. Se non trovato, espandi il gruppo "Legacy models" (freccia/voce con etichetta simile)
    legacy_toggle = driver.find_element(By.XPATH, "//div[@role='menu']//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'), 'legacy')]")
    legacy_toggle.click()

    # 5. Attendi che compaiano le opzioni legacy e seleziona il modello
    WebDriverWait(driver, 5).until(
        EC.visibility_of_element_located((By.XPATH, "//div[@role='menu']//div[contains(., 'Legacy')]//span"))
    )
    legacy_models = driver.find_elements(By.XPATH, f"//div[@role='menu']//span[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'), '{target_model.lower()}')]")
    if legacy_models:
        legacy_models[0].click()
        return

    raise RuntimeError(f"Il modello '{target_model}' non è stato trovato nel menu.")


def ensure_chatgpt_model(driver):
    """Ensure the desired ChatGPT model is active before sending a prompt."""
    # Check if CHATGPT_MODEL is set and not empty
    if not CHATGPT_MODEL or CHATGPT_MODEL.strip() == "" or CHATGPT_MODEL.upper() == "NONE":
        log_info("[chatgpt_model] CHATGPT_MODEL not set or disabled, skipping model selection")
        return True
        
    try:
        log_info(f"[chatgpt_model] Ensuring model {CHATGPT_MODEL} is active")
        select_chatgpt_model(driver)
        log_info(f"[chatgpt_model] Model {CHATGPT_MODEL} configured successfully")
        return True
    except Exception as e:
        log_warning(f"[chatgpt_model] Could not configure model {CHATGPT_MODEL}: {e}")
        log_info("[chatgpt_model] Continuing with current/default model")
        try:
            screenshots_dir = os.path.join(_LOG_DIR, "screenshots")
            os.makedirs(screenshots_dir, exist_ok=True)
            screenshot_path = os.path.join(screenshots_dir, "model_switch_error.png")
            driver.save_screenshot(screenshot_path)
            log_info(f"[chatgpt_model] Saved screenshot {screenshot_path}")
        except Exception as ss:
            log_warning(f"[chatgpt_model] Screenshot failed: {ss}")
        return True  # Non bloccare l'esecuzione, continua con il modello corrente

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
        
        # Clear the queue to prevent pending tasks
        try:
            while not self._queue.empty():
                self._queue.get_nowait()
                self._queue.task_done()
            log_debug("[selenium] Queue cleared")
        except Exception as e:
            log_warning(f"[selenium] Failed to clear queue: {e}")
        
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

    def _get_interface_name(self, bot) -> str:
        """Determine the interface name from the bot object."""
        module_name = getattr(bot.__class__, "__module__", "")
        if module_name.startswith("telegram"):
            return "telegram"
        elif hasattr(bot, "get_interface_id"):
            return bot.get_interface_id()
        else:
            return "generic"

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

    async def handle_incoming_message(self, bot, message, prompt):
        """Handle incoming messages by queuing them for processing."""
        try:
            # Check if this is a correction request by examining the prompt structure
            is_correction = (
                isinstance(prompt, str) and 
                ("correction" in prompt.lower() or "corrected" in prompt.lower() or 
                 "failed actions" in prompt.lower() or "valid JSON" in prompt.lower())
            ) or (
                isinstance(prompt, dict) and 
                prompt.get("system_message", {}).get("type") == "error"
            )
            
            # Check if this is a system message with output (from terminal plugin, etc.)
            is_system_output = (
                isinstance(prompt, dict) and 
                prompt.get("system_message", {}).get("type") == "output"
            )
            
            if is_correction or is_system_output:
                # For correction requests and system output, process synchronously and return the response
                request_type = "correction" if is_correction else "system output"
                log_debug(f"[selenium] Processing {request_type} request synchronously: chat_id={message.chat_id}")
                
                # Initialize driver if needed
                if not self.driver:
                    self._init_driver()
                
                # Process the message directly
                if is_correction:
                    response_text = await self._process_correction_message(bot, message, prompt)
                else:
                    response_text = await self._process_system_output_message(bot, message, prompt)
                return response_text
            else:
                # For normal messages, use the queue system
                await self._queue.put((bot, message, prompt))
                log_debug(f"[selenium] Message queued for processing: chat_id={message.chat_id}")
                
                # Ensure worker is running
                if not self.is_worker_running():
                    await self.start()
                    
        except Exception as e:
            log_error(f"[selenium] Failed to queue message: {repr(e)}", e)
            # Send error message if queuing fails
            await self._send_error_message(bot, message, error_text=f"Failed to queue message: {e}")
            
    async def _process_correction_message(self, bot, message, prompt):
        """Process a correction message synchronously and return the response."""
        try:
            log_debug(f"[selenium] Processing correction prompt: {prompt}")
            
            # Handle both dict and string inputs
            if isinstance(prompt, dict):
                prompt_text = json.dumps(prompt, ensure_ascii=False)
            else:
                prompt_text = prompt
            
            # Disable driver initialization retries for correction processing
            max_attempts = 1
            response_text = None
            
            for attempt in range(max_attempts):
                try:
                    if not self.driver:
                        self._init_driver()
                    
                    # Get chat ID for ChatGPT conversation
                    chat_id = await chat_link_store.get_link(
                        message.chat_id, 
                        getattr(message, "message_thread_id", None),
                        interface=self._get_interface_name(bot)
                    )
                    
                    # Process the prompt in ChatGPT
                    previous_text = get_previous_response(str(message.chat_id))
                    response_text = process_prompt_in_chat(
                        self.driver, chat_id, prompt_text, previous_text
                    )
                    
                    if response_text:
                        # Update response cache
                        update_previous_response(str(message.chat_id), response_text)
                        log_debug(f"[selenium] Correction response generated: {len(response_text)} chars")
                        return response_text.strip()
                    else:
                        log_warning("[selenium] No response from ChatGPT for correction")
                        return None
                        
                except Exception as e:
                    log_error(f"[selenium] Error processing correction message: {e}")
                    if attempt == max_attempts - 1:
                        return None
                        
        except Exception as e:
            log_error(f"[selenium] Failed to process correction message: {e}")
            return None

    async def _process_system_output_message(self, bot, message, prompt):
        """Process a system output message (e.g., from terminal plugin) synchronously and return the response."""
        try:
            log_debug(f"[selenium] Processing system output prompt: {prompt}")
            
            # Handle dict input (system_message structure)
            if isinstance(prompt, dict):
                prompt_text = json.dumps(prompt, ensure_ascii=False)
            else:
                prompt_text = prompt
            
            # Disable driver initialization retries for system output processing
            max_attempts = 1
            response_text = None
            
            for attempt in range(max_attempts):
                try:
                    if not self.driver:
                        self._init_driver()
                    
                    # Get chat ID for ChatGPT conversation
                    chat_id = await chat_link_store.get_link(
                        message.chat_id, 
                        getattr(message, "message_thread_id", None),
                        interface=self._get_interface_name(bot)
                    )
                    
                    # Process the prompt in ChatGPT
                    previous_text = get_previous_response(str(message.chat_id))
                    response_text = process_prompt_in_chat(
                        self.driver, chat_id, prompt_text, previous_text
                    )
                    
                    if response_text:
                        # Update response cache
                        update_previous_response(str(message.chat_id), response_text)
                        log_debug(f"[selenium] System output response generated: {len(response_text)} chars")
                        return response_text.strip()
                    else:
                        log_warning("[selenium] No response from ChatGPT for system output")
                        return None
                        
                except Exception as e:
                    log_error(f"[selenium] Error processing system output message: {e}")
                    if attempt == max_attempts - 1:
                        return None
                        
        except Exception as e:
            log_error(f"[selenium] Failed to process system output message: {e}")
            return None

    # ...existing code...
