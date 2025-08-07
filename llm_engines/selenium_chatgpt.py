"""
ChatGPT automation using nodriver (replacement for undetected_chromedriver).

This module handles ChatGPT conversation automation using the nodriver library
instead of the deprecated undetected_chromedriver.
"""

import nodriver as uc
import time
import json
import re
import os
import subprocess
import asyncio
from typing import Dict, Optional
from collections import defaultdict
import threading

from core.ai_plugin_base import AIPluginBase
from core.notifier import notify_trainer, set_notifier
from core.logging_utils import log_debug, log_info, log_warning, log_error
from core import recent_chats
from core.db import get_conn
import aiomysql


class ChatLinkStore:
    """Persist mapping between chat sessions and ChatGPT conversations."""

    def __init__(self) -> None:
        self._table_ensured = False

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
                        chat_id TEXT NOT NULL,
                        message_thread_id TEXT,
                        link VARCHAR(2048),
                        PRIMARY KEY (chat_id(255), message_thread_id(255))
                    )
                    """,
                )
                self._table_ensured = True
        finally:
            conn.close()

    async def get_link(self, chat_id: int | str, message_thread_id: Optional[int | str]) -> Optional[str]:
        await self._ensure_table()
        normalized_thread = self._normalize_thread_id(message_thread_id)
        log_debug(f"[chatlink] get_link normalized thread_id={normalized_thread}")
        
        conn = await get_conn()
        try:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    "SELECT link FROM chatgpt_links WHERE chat_id = %s AND message_thread_id = %s",
                    (str(chat_id), normalized_thread),
                )
                row = await cur.fetchone()
                chat = row["link"] if row else None
                log_debug(f"[chatlink] get_link {chat_id}/{normalized_thread} -> {chat}")
                return chat
        finally:
            conn.close()

    async def save_link(self, chat_id: int | str, message_thread_id: Optional[int | str], link: str) -> None:
        await self._ensure_table()
        normalized_thread = self._normalize_thread_id(message_thread_id)
        log_debug(f"[chatlink] save_link normalized thread_id={normalized_thread}")
        
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

    async def remove(self, chat_id: str | int, message_thread_id: Optional[int | str]) -> bool:
        """Remove mapping for given chat."""
        await self._ensure_table()
        normalized_thread = self._normalize_thread_id(message_thread_id)
        log_debug(f"[chatlink] remove normalized thread_id={normalized_thread}")
        
        conn = await get_conn()
        try:
            async with conn.cursor() as cur:
                result = await cur.execute(
                    "DELETE FROM chatgpt_links WHERE chat_id = %s AND message_thread_id = %s",
                    (str(chat_id), normalized_thread),
                )
                await conn.commit()
                rows_deleted = result > 0
        finally:
            conn.close()

        if rows_deleted:
            log_debug(f"[chatlink] Removed link for chat_id={chat_id}, message_thread_id={normalized_thread}")
        else:
            log_debug(f"[chatlink] No link found for chat_id={chat_id}, message_thread_id={normalized_thread}")
        return rows_deleted


# Global instances and configuration
chat_link_store = ChatLinkStore()
previous_responses: Dict[str, str] = {}
response_cache_lock = threading.Lock()
queue_paused = False

GRACE_PERIOD_SECONDS = 3.5
MAX_WAIT_TIMEOUT_SECONDS = 300


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


def _safe_notify(text: str) -> None:
    """Send notification in chunks to avoid message length limits."""
    for i in range(0, len(text), 4000):
        chunk = text[i : i + 4000]
        log_debug(f"[selenium] Notifying chunk length {len(chunk)}")
        try:
            from core.config import TRAINER_ID
            notify_trainer(TRAINER_ID, chunk)
        except Exception as e:
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
        r"chat\\.openai\\.com/c/([^/?#]+)",     # Alternative full URL
        r"chatgpt\\.com/c/([^/?#]+)"            # New domain format
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


class NodriverWrapper:
    """Wrapper to provide selenium-like interface for nodriver."""
    
    def __init__(self, browser):
        self._browser = browser
        self._tab = None
    
    async def get_tab(self):
        """Get current tab."""
        if not self._tab:
            try:
                # Try different methods to get a tab
                if hasattr(self._browser, 'get_tab'):
                    self._tab = await self._browser.get_tab()
                elif hasattr(self._browser, 'tabs') and self._browser.tabs:
                    self._tab = self._browser.tabs[0]
                elif hasattr(self._browser, 'current_tab'):
                    self._tab = self._browser.current_tab
                else:
                    # Fallback - use browser directly
                    self._tab = self._browser
            except Exception as e:
                log_warning(f"[selenium] Error getting tab, using browser directly: {e}")
                self._tab = self._browser
        return self._tab
    
    async def get(self, url):
        """Navigate to URL."""
        tab = await self.get_tab()
        await tab.get(url)
    
    async def find_element_by_id(self, element_id, timeout=10):
        """Find element by ID."""
        tab = await self.get_tab()
        try:
            element = await tab.select(f"#{element_id}", timeout=timeout)
            return NodriverElementWrapper(element, tab) if element else None
        except:
            return None
    
    async def find_elements_by_css_selector(self, selector, timeout=10):
        """Find elements by CSS selector."""
        tab = await self.get_tab()
        try:
            elements = await tab.select_all(selector, timeout=timeout)
            return [NodriverElementWrapper(elem, tab) for elem in elements]
        except:
            return []
    
    async def execute_script(self, script, *args):
        """Execute JavaScript."""
        tab = await self.get_tab()
        return await tab.evaluate(script)
    
    async def save_screenshot(self, filename):
        """Save screenshot."""
        tab = await self.get_tab()
        try:
            screenshot_data = await tab.screenshot()
            with open(filename, 'wb') as f:
                f.write(screenshot_data)
            return True
        except Exception as e:
            log_error(f"[selenium] Screenshot failed: {e}")
            return False
    
    @property
    async def current_url(self):
        """Get current URL."""
        tab = await self.get_tab()
        return await tab.evaluate("window.location.href")
    
    async def quit(self):
        """Quit browser."""
        await self._browser.stop()


class NodriverElementWrapper:
    """Wrapper to provide selenium-like interface for nodriver elements."""
    
    def __init__(self, element, tab):
        self._element = element
        self._tab = tab
    
    async def send_keys(self, text):
        """Send keys to the element."""
        if text == "\n":  # Handle ENTER key
            await self._tab.evaluate("""
                (() => {
                    // Try multiple selectors for the send button
                    const selectors = [
                        'button[data-testid="send-button"]',
                        'button[aria-label="Send prompt"]', 
                        'button[aria-label="Send message"]',
                        'button svg[viewBox="0 0 16 16"]',
                        '[data-testid="send-button"]',
                        'button:has(svg)',
                        'button[type="submit"]'
                    ];
                    
                    for (const selector of selectors) {
                        const btn = document.querySelector(selector);
                        if (btn && !btn.disabled && btn.offsetParent !== null) {
                            btn.click();
                            return '✅ clicked submit button';
                        }
                    }
                    return '❌ submit button not found or disabled';
                })()
            """)
        else:
            # Handle ProseMirror editor
            escaped_text = json.dumps(text)
            await self._tab.evaluate(f"""
                (() => {{
                    const textarea = document.getElementById('prompt-textarea');
                    if (!textarea) return '❌ textarea not found';
                    
                    // Clear existing content
                    textarea.innerHTML = '';
                    
                    // Create a paragraph element with the text
                    const p = document.createElement('p');
                    p.textContent = {escaped_text};
                    textarea.appendChild(p);
                    
                    // Trigger input events
                    textarea.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    textarea.focus();
                    
                    return '✅ text injected into ProseMirror';
                }})()
            """)
    
    async def click(self):
        """Click the element."""
        await self._element.click()
    
    async def get_attribute(self, name):
        """Get attribute value."""
        return await self._element.get_attribute(name)
    
    @property
    async def text(self):
        """Get element text."""
        return await self._element.inner_text()


async def wait_for_response(driver: NodriverWrapper, timeout: int = 120) -> str:
    """Wait for ChatGPT response and return the text once it stabilizes."""

    start_time = time.time()
    log_debug("[selenium] Waiting for assistant response DOM...")
    tab = await driver.get_tab()
    assistant_selector = 'div[data-message-author-role="assistant"]'
    node = None
    # Attendi la comparsa del DOM fino a timeout
    while time.time() - start_time < timeout:
        try:
            nodes = await tab.query_selector_all(assistant_selector)
            if nodes:
                node = nodes[-1]
                break
        except Exception as e:
            log_debug(f"[selenium] Error waiting for assistant DOM: {e}")
        await asyncio.sleep(1)

    if not node:
        log_warning(f"[selenium] Timeout: assistant DOM not found after {timeout}s")
        return ""

        log_debug("[selenium] Assistant DOM found, monitoring response...")
    last_len = -1
    last_text = ""
    stable_cycles = 0
    max_stable_cycles = 3
    cycle_time = 1.0
    total_wait = 0.0

    while total_wait < timeout:
        try:
            current_text = await node.inner_text()
            current_text = current_text.strip() if current_text else ""
            current_len = len(current_text)
            log_debug(f"[selenium] Response block len={current_len} stable_cycles={stable_cycles}")
            if current_len == last_len:
                stable_cycles += 1
            else:
                stable_cycles = 0
                last_len = current_len
                last_text = current_text
            if stable_cycles >= max_stable_cycles:
                log_debug(f"[selenium] Response stabilized after {total_wait:.1f}s, length={current_len}")
                return last_text
        except Exception as e:
            log_warning(f"[selenium] Error monitoring response: {e}")
        await asyncio.sleep(cycle_time)
        total_wait += cycle_time

    log_warning(f"[selenium] Timeout: response not stabilized after {timeout}s, partial text: '{last_text[:100] if last_text else 'None'}...'")
    return last_text if last_text else ""


async def send_prompt_to_chatgpt(driver: NodriverWrapper, prompt_text: str) -> bool:
    """Send prompt to ChatGPT interface."""
    try:
        tab = await driver.get_tab()
        # Clear and type the prompt
        clean_text = strip_non_bmp(prompt_text)
        if len(clean_text) > 4000:
            clean_text = clean_text[:4000]
        escaped_prompt = json.dumps(clean_text)
        # Inject the text
        injection_result = await tab.evaluate(f"""
            (() => {{
                const textarea = document.getElementById('prompt-textarea');
                if (!textarea) return '❌ textarea not found';

                // Clear existing content first
                textarea.innerHTML = '';

                // Create a paragraph element with the text
                const p = document.createElement('p');
                p.textContent = {escaped_prompt};
                textarea.appendChild(p);

                // Focus the textarea first
                textarea.focus();

                // Trigger comprehensive events to activate the interface
                textarea.dispatchEvent(new Event('focus', {{ bubbles: true }}));
                textarea.dispatchEvent(new Event('input', {{ bubbles: true, cancelable: true }}));
                textarea.dispatchEvent(new Event('change', {{ bubbles: true }}));
                textarea.dispatchEvent(new KeyboardEvent('keydown', {{ bubbles: true, key: 'a' }}));
                textarea.dispatchEvent(new KeyboardEvent('keyup', {{ bubbles: true, key: 'a' }}));

                // Wait a moment for React to process (using setTimeout instead of await)
                setTimeout(() => {{
                    // Double-check text is present and trigger final events
                    if (!textarea.textContent.trim()) {{
                        textarea.innerHTML = '<p>' + {escaped_prompt} + '</p>';
                        textarea.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    }}

                    // Final activation events
                    textarea.dispatchEvent(new Event('blur', {{ bubbles: true }}));
                    textarea.dispatchEvent(new Event('focus', {{ bubbles: true }}));
                }}, 100);

                const finalLength = textarea.textContent.length;

                // Check if send button is now enabled
                const sendButton = document.querySelector('button[data-testid="send-button"]') || 
                                 document.querySelector('button[aria-label="Send prompt"]') ||
                                 document.querySelector('button[aria-label="Send message"]');
                const buttonEnabled = sendButton && !sendButton.disabled;

                return '✅ prompt injected: ' + finalLength + ' chars, button enabled: ' + buttonEnabled;
            }})()
        """)
        log_debug(f"[selenium] Prompt injection result: {injection_result}")

        # Click send button - wait for it to be enabled
        submit_result = await tab.evaluate("""
            (() => {
                // Wait for send button to be enabled (max 5 seconds)
                return new Promise((resolve) => {
                    let attempts = 0;
                    const maxAttempts = 50; // 5 seconds with 100ms intervals

                    const checkButton = () => {
                        attempts++;

                        // Try multiple selectors for the send button
                        const selectors = [
                            'button[data-testid="send-button"]',
                            'button[aria-label="Send prompt"]', 
                            'button[aria-label="Send message"]',
                            'button svg[viewBox="0 0 16 16"]',
                            '[data-testid="send-button"]',
                            'button:has(svg)',
                            'button[type="submit"]'
                        ];

                        for (const selector of selectors) {
                            const btn = document.querySelector(selector);
                            if (btn && !btn.disabled && btn.offsetParent !== null) {
                                btn.click();
                                resolve('✅ clicked send button with selector: ' + selector + ' (attempt ' + attempts + ')');
                                return;
                            }
                        }

                        // If button not found or disabled, try again
                        if (attempts < maxAttempts) {
                            setTimeout(checkButton, 100);
                        } else {
                            // Final fallback: look for any button with send-like appearance
                            const buttons = document.querySelectorAll('button');
                            for (const btn of buttons) {
                                if (btn.disabled || btn.offsetParent === null) continue;
                                const text = btn.textContent.toLowerCase();
                                const hasIcon = btn.querySelector('svg');
                                if (text.includes('send') || text.includes('submit') || hasIcon) {
                                    btn.click();
                                    resolve('✅ clicked send button (fallback): ' + text);
                                    return;
                                }
                            }
                            resolve('❌ submit button not found or never enabled after ' + attempts + ' attempts');
                        }
                    };

                    checkButton();
                });
            })()
        """)
        log_debug(f"[selenium] Submit result: {submit_result} (type: {type(submit_result)})")

        if submit_result is None:
            log_error("[selenium] Submit result is None (no output from JS). Prompt not sent.")
            return False
        if isinstance(submit_result, str):
            return submit_result.startswith('✅')
        log_error(f"[selenium] Unexpected submit_result type: {type(submit_result)}")
        return False
    finally:
        pass


async def is_chat_archived(driver: NodriverWrapper, chat_id: str) -> bool:
    """Check if a ChatGPT chat is archived."""
    if not chat_id:
        return False
    
    try:
        chat_url = f"https://chatgpt.com/c/{chat_id}"
        log_debug(f"[selenium] Checking if chat {chat_id} is archived by navigating to {chat_url}")
        await driver.get(chat_url)
        
        # Wait a moment for page to load
        await asyncio.sleep(3)
        
        # Check for archived message
        try:
            tab = await driver.get_tab()
            page_text = await tab.evaluate("document.body.innerText || ''")
            if "this conversation is archived" in page_text.lower():
                log_warning(f"[selenium] Chat {chat_id} is archived")
                return True
            
            # Check if textarea is present (indicates chat is accessible)
            has_textarea = await tab.evaluate("!!document.getElementById('prompt-textarea')")
            if has_textarea:
                log_debug(f"[selenium] Chat {chat_id} is accessible")
                return False
            else:
                log_warning(f"[selenium] Chat {chat_id} may be archived - no textarea found")
                return True
                
        except Exception as e:
            log_warning(f"[selenium] Could not check archived status: {e}")
            return True
            
    except Exception as e:
        log_error(f"[selenium] Error checking if chat {chat_id} is archived: {e}")
        return True


async def check_conversation_full(driver: NodriverWrapper) -> bool:
    """Check if the current conversation has reached maximum length."""
    try:
        tab = await driver.get_tab()
        elements = await tab.query_selector_all("div.text-token-text-error")
        
        for element in elements:
            text = await element.inner_text()
            if text and "maximum length for this conversation" in text:
                return True
    except Exception as e:
        log_warning(f"[selenium] overflow check failed: {e}")
    return False


async def open_new_chat(driver: NodriverWrapper) -> None:
    """Navigate to ChatGPT home to create a new chat with retries."""
    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            log_debug(f"[selenium] Attempt {attempt}/{max_retries} to navigate to ChatGPT home")
            await driver.get("https://chatgpt.com")
            log_debug("[selenium] Successfully navigated to ChatGPT home")
            await asyncio.sleep(2)  # Allow page to load
            return
        except Exception as e:
            log_warning(f"[selenium] Attempt {attempt} failed: {e}")
            if attempt < max_retries:
                await asyncio.sleep(2 * attempt)
            else:
                log_error("[selenium] All attempts to navigate to ChatGPT home failed")
                raise


async def process_prompt_in_chat(
    driver: NodriverWrapper, chat_id: str | None, prompt_text: str, previous_text: str
) -> Optional[str]:
    """Send a prompt to a ChatGPT chat and return the newly generated text."""
    
    if chat_id and await is_chat_archived(driver, chat_id):
        chat_id = None  # Mark chat as invalid

    if not chat_id:
        log_debug("[selenium] Creating a new chat")
        await open_new_chat(driver)

    try:
        # Wait for textarea to be available
        tab = await driver.get_tab()
        textarea_available = False
        for _ in range(10):  # Try for 10 seconds
            has_textarea = await tab.evaluate("""
                (() => {
                    const textarea = document.getElementById('prompt-textarea');
                    return textarea && textarea.offsetParent !== null;
                })()
            """)
            if has_textarea:
                textarea_available = True
                break
            await asyncio.sleep(1)
        
        if not textarea_available:
            log_error("[selenium] Prompt textarea not found")
            return None

        # Send the prompt
        success = await send_prompt_to_chatgpt(driver, prompt_text)
        if not success:
            log_error("[selenium] Failed to send prompt")
            return None

        # Wait for response
        response_text = await wait_for_response(driver)
        
        if response_text and response_text != previous_text:
            log_debug(f"[selenium] New response received: {len(response_text)} chars")
            return response_text.strip()
        else:
            log_warning("[selenium] No new response received")
            return None

    except Exception as e:
        log_error(f"[selenium] Error processing prompt: {e}")
        return None


class SeleniumChatGPTPlugin(AIPluginBase):
    """
    Automate ChatGPT conversations using nodriver.
    
    Migrated from undetected_chromedriver to nodriver for better compatibility.
    """
    
    # Shared locks per chat for concurrent access control
    chat_locks: defaultdict[int, asyncio.Lock] = defaultdict(asyncio.Lock)

    def __init__(self, notify_fn=None):
        """Initialize the plugin without starting browser yet."""
        self.driver: Optional[NodriverWrapper] = None
        self._browser = None
        self._queue: asyncio.Queue = asyncio.Queue()
        self._worker_task: Optional[asyncio.Task] = None
        self._notify_fn = notify_fn or notify_trainer
        
        log_debug(f"[selenium] notify_fn passed: {bool(notify_fn)}")
        set_notifier(self._notify_fn)
        log_info("[selenium] 🔧 Initialized SeleniumChatGPTPlugin (nodriver mode)")

    async def _ensure_driver(self) -> NodriverWrapper:
        """Ensure browser driver is available."""
        if self.driver is None:
            log_debug("[selenium] 🚀 Creating new nodriver browser instance")
            
            # Configure browser launch options
            browser_args = [
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage", 
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
                "--disable-client-side-phishing-detection",
                "--allow-running-insecure-content",
                "--disable-blink-features=AutomationControlled",
                "--disable-component-extensions-with-background-pages",
                "--no-zygote",
                "--single-process"
            ]

            # If CHROME_PROFILE_DIR is set, use it; otherwise let Chromium use its default directory
            profile_dir = os.environ.get('CHROME_PROFILE_DIR')
            if profile_dir:
                try:
                    os.makedirs(profile_dir, mode=0o755, exist_ok=True)
                    test_file = os.path.join(profile_dir, '.test_write')
                    with open(test_file, 'w') as f:
                        f.write('test')
                    os.remove(test_file)
                    log_info(f"[selenium] 💾 Using custom profile: {profile_dir}")
                    browser_args.append(f"--user-data-dir={profile_dir}")
                except Exception as e:
                    log_warning(f"[selenium] Profile directory {profile_dir} not writable: {e}")
                    # Fallback to /tmp only if the custom one is not writable
                    profile_dir = '/tmp/chromium-rekku-session'
                    os.makedirs(profile_dir, mode=0o755, exist_ok=True)
                    log_warning(f"[selenium] 💾 Using temporary profile (won't persist): {profile_dir}")
                    browser_args.append(f"--user-data-dir={profile_dir}")
            else:
                log_info("[selenium] 📁 No forced profile directory, Chromium will use its default")
            # Create nodriver browser
            try:
                # Try different configurations for container environments
                browser_config = {
                    'args': browser_args,
                    'headless': False,
                    'lang': "en-US"
                }
                
                # Add sandbox configuration - try multiple approaches
                try:
                    # First attempt with no_sandbox parameter
                    self._browser = await uc.start(
                        **browser_config,
                        no_sandbox=True
                    )
                except Exception as e1:
                    log_warning(f"[selenium] First attempt failed: {e1}")
                    try:
                        # Second attempt with sandbox=False
                        self._browser = await uc.start(
                            **browser_config,
                            sandbox=False
                        )
                    except Exception as e2:
                        log_warning(f"[selenium] Second attempt failed: {e2}")
                        # Third attempt with basic config only
                        self._browser = await uc.start(**browser_config)
                
                log_debug("[selenium] Browser instance created")
                
                # Wait for browser to be ready
                await asyncio.sleep(3)
                
                # Navigate to ChatGPT - get the first/default tab
                try:
                    # Try different methods to get a tab
                    if hasattr(self._browser, 'get_tab'):
                        tab = await self._browser.get_tab()
                    elif hasattr(self._browser, 'tabs') and self._browser.tabs:
                        tab = self._browser.tabs[0]
                    elif hasattr(self._browser, 'current_tab'):
                        tab = self._browser.current_tab
                    else:
                        # Create new tab if needed
                        tab = await self._browser.get()
                        
                    await tab.get("https://chatgpt.com")
                    await asyncio.sleep(3)  # Allow page to load
                    
                    # Check if we have session data
                    session_check = await tab.evaluate("""
                        (() => {
                            const cookies = document.cookie;
                            const localStorage = Object.keys(window.localStorage || {}).length;
                            const sessionStorage = Object.keys(window.sessionStorage || {}).length;
                            return {
                                hasCookies: cookies.length > 0,
                                localStorageItems: localStorage,
                                sessionStorageItems: sessionStorage,
                                userAgent: navigator.userAgent
                            };
                        })()
                    """)
                    log_debug(f"[selenium] Session data check: {session_check}")
                    
                    if session_check.get('hasCookies') or session_check.get('localStorageItems', 0) > 0:
                        log_info("[selenium] 💾 Found existing session data")
                    else:
                        log_warning("[selenium] ⚠️ No session data found - fresh browser session")
                    
                except Exception as e:
                    log_warning(f"[selenium] Error getting tab: {e}")
                    # Try alternative approach - just use the browser object directly
                    tab = self._browser
                    await tab.get("https://chatgpt.com")
                    await asyncio.sleep(3)
                
                self.driver = NodriverWrapper(self._browser)
                log_debug("[selenium] ✅ Browser driver created successfully")
                
            except Exception as e:
                log_error(f"[selenium] ❌ Failed to create browser: {e}")
                _notify_gui(f"❌ Selenium error: {e}. Check graphics environment.")
                raise
        
        return self.driver

    async def _get_driver(self):
        """Return a valid WebDriver, recreating it if the session is dead."""
        if self.driver is None:
            try:
                return await self._ensure_driver()
            except Exception as e:
                log_error(f"[selenium] Failed to initialize driver: {e}")
                return None
        else:
            try:
                # Simple command to verify the session is still alive
                await self.driver.execute_script("return 1")
                return self.driver
            except Exception as e:
                log_warning(f"[selenium] WebDriver session error: {e}. Restarting")
                try:
                    await self.driver.quit()
                except Exception:
                    pass
                self.driver = None
                self._browser = None
                try:
                    return await self._ensure_driver()
                except Exception as e2:
                    log_error(f"[selenium] Failed to reinitialize driver: {e2}")
                    return None

    async def _ensure_logged_in(self):
        """Check if user is logged in to ChatGPT and provide helpful guidance."""
        try:
            current_url = await self.driver.current_url
            log_debug(f"[selenium] [STEP] Checking login state at {current_url}")
            
            # Check various login indicators
            if current_url and ("login" in current_url or "auth0" in current_url or "auth." in current_url):
                log_warning("[selenium] ❌ Not logged in - on login page")
                _notify_gui("🔐 ChatGPT Login Required! Please log in manually via browser. Open")
                return False
            
            # Check for ChatGPT-specific login indicators
            tab = await self.driver.get_tab()
            
            # Look for login buttons or login indicators
            login_indicators = await tab.evaluate("""
                (() => {
                    // Check for login buttons
                    const loginButtons = document.querySelectorAll('button, a');
                    let hasLoginButton = false;
                    
                    for (const btn of loginButtons) {
                        const text = btn.textContent?.toLowerCase() || '';
                        const href = btn.href?.toLowerCase() || '';
                        if (text.includes('log in') || text.includes('sign in') || 
                            text.includes('login') || href.includes('login')) {
                            hasLoginButton = true;
                            break;
                        }
                    }
                    
                    // Check for user profile indicators
                    const profileIndicators = document.querySelectorAll('[data-testid*="profile"], .user-avatar, .profile-menu');
                    const hasProfile = profileIndicators.length > 0;
                    
                    // Check for textarea (indicates logged in and ready)
                    const hasTextarea = !!document.getElementById('prompt-textarea');
                    
                    // Check page title
                    const title = document.title.toLowerCase();
                    const isLoginPage = title.includes('login') || title.includes('sign in');
                    
                    return {
                        hasLoginButton: hasLoginButton,
                        hasProfile: hasProfile,
                        hasTextarea: hasTextarea,
                        isLoginPage: isLoginPage,
                        title: document.title,
                        url: window.location.href
                    };
                })()
            """)
            
            log_debug(f"[selenium] Login check results: {login_indicators}")
            
            # Simplified login check - if we have textarea, we're good to go
            if hasattr(login_indicators, 'get'):
                has_textarea = login_indicators.get('hasTextarea', False)
                is_login_page = login_indicators.get('isLoginPage', False)
                has_login_button = login_indicators.get('hasLoginButton', False)
            else:
                # Handle case where result might be in different format
                log_debug(f"[selenium] Unexpected login check format: {type(login_indicators)}")
                # Fallback: just check for textarea directly
                has_textarea = await tab.evaluate("!!document.getElementById('prompt-textarea')")
                is_login_page = False
                has_login_button = False
            # Simple logic: if we have textarea, we're logged in
            if has_textarea and not is_login_page:
                log_debug("[selenium] ✅ Logged in and ready (textarea found)")
                return True
            elif is_login_page or has_login_button:
                log_warning("[selenium] ❌ Not logged in - login required")
                _notify_gui("🔐 ChatGPT Login Required! Please log in manually via browser. Open")
                return False
            else:
                # If unclear, be more permissive - just check if we can access ChatGPT
                log_debug("[selenium] ✅ Assuming logged in (no clear login indicators)")
                return True
            
        except Exception as e:
            log_warning(f"[selenium] Could not check login status: {e}")
            _notify_gui("❓ Cannot check ChatGPT login status. Please verify manually. Open")
            return False

    async def _send_response(self, bot, message, response_text: str):
        """Send response through the appropriate interface."""
        try:
            # Try different interface methods based on what's available
            if hasattr(bot, 'send_message'):
                # Standard bot interface (Telegram, Discord, etc.)
                await bot.send_message(
                    chat_id=message.chat_id,
                    text=response_text,
                    reply_to_message_id=getattr(message, 'message_id', None)
                )
            elif hasattr(bot, 'reply'):
                # Simple reply interface
                await bot.reply(message, response_text)
            elif hasattr(bot, 'send'):
                # Generic send interface
                await bot.send(message.chat_id, response_text)
            else:
                # Fallback: try to import the appropriate utils
                try:
                    from core.telegram_utils import safe_send
                    await safe_send(
                        bot,
                        chat_id=message.chat_id,
                        text=response_text,
                        reply_to_message_id=getattr(message, 'message_id', None),
                        event_id=getattr(message, "event_id", None),
                    )
                except ImportError:
                    log_error("[selenium] No suitable method found to send response")
                    raise NotImplementedError("Bot interface not supported")
        except Exception as e:
            log_error(f"[selenium] Failed to send response: {e}")
            raise

    async def handle_incoming_message(self, bot, message, prompt):
        """Queue the message to be processed sequentially."""
        # Extract user_id safely from different message object structures
        user_id = "unknown"
        if hasattr(message, 'from_user') and message.from_user:
            if hasattr(message.from_user, 'id'):
                user_id = message.from_user.id
            elif isinstance(message.from_user, dict):
                user_id = message.from_user.get('id', 'unknown')
        elif hasattr(message, 'user_id'):
            user_id = message.user_id
        
        text = getattr(message, 'text', '') or getattr(message, 'content', '')
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
        """Main worker loop for processing messages."""
        log_info("[selenium] 🔄 Worker loop started")
        
        try:
            while True:
                bot, message, prompt = await self._queue.get()
                while queue_paused:
                    await asyncio.sleep(1)
                    
                log_debug(
                    f"[selenium] [WORKER] Processing chat_id={message.chat_id} message_id={message.message_id}"
                )
                
                try:
                    lock = SeleniumChatGPTPlugin.chat_locks[message.chat_id]
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
                    
        except asyncio.CancelledError:
            log_warning("Worker was cancelled")
            raise
        finally:
            log_info("Worker loop cleaned up")

    async def _process_message(self, bot, message, prompt):
        """Send the prompt to ChatGPT and forward the response."""
        log_debug(f"[selenium][STEP] processing prompt: {prompt}")

        for attempt in range(2):
            driver = await self._get_driver()
            if not driver:
                log_error("[selenium] WebDriver unavailable, aborting")
                _notify_gui("❌ Selenium driver not available. Open UI")
                return

            if not await self._ensure_logged_in():
                return

            log_debug("[selenium][STEP] ensuring ChatGPT is accessible")

            message_thread_id = getattr(message, "message_thread_id", None)
            chat_id = await chat_link_store.get_link(message.chat_id, message_thread_id)
            prompt_text = json.dumps(prompt, ensure_ascii=False)
            
            if not chat_id:
                # Check if we have a path from recent_chats
                path = recent_chats.get_chat_path(message.chat_id)
                if path:
                    # Try to navigate to the saved path
                    try:
                        chat_url = f"https://chatgpt.com{path}"
                        await driver.get(chat_url)
                        await asyncio.sleep(3)
                        
                        # Check if we can access the chat
                        tab = await driver.get_tab()
                        has_textarea = await tab.evaluate("!!document.getElementById('prompt-textarea')")
                        if has_textarea:
                            current_url = await driver.current_url
                            extracted_id = _extract_chat_id(current_url)
                            if extracted_id:
                                await chat_link_store.save_link(message.chat_id, message_thread_id, extracted_id)
                                chat_id = extracted_id
                                log_debug(f"[selenium] Recovered chat from path: {chat_id}")
                        else:
                            log_warning(f"[selenium] Chat path {path} no longer accessible")
                            recent_chats.clear_chat_path(message.chat_id)
                    except Exception as e:
                        log_warning(f"[selenium] Failed to navigate to saved path: {e}")
                        recent_chats.clear_chat_path(message.chat_id)

            if chat_id:
                # Verify existing chat is accessible
                chat_url = f"https://chatgpt.com/c/{chat_id}"
                try:
                    await driver.get(chat_url)
                    await asyncio.sleep(3)
                    
                    tab = await driver.get_tab()
                    has_textarea = await tab.evaluate("!!document.getElementById('prompt-textarea')")
                    if not has_textarea:
                        log_warning(f"[selenium] Existing chat {chat_id} no longer accessible")
                        await chat_link_store.remove(message.chat_id, message_thread_id)
                        recent_chats.clear_chat_path(message.chat_id)
                        chat_id = None
                    else:
                        log_debug(f"[selenium] Successfully accessed existing chat: {chat_id}")
                        
                except Exception as e:
                    log_warning(f"[selenium] Existing chat {chat_id} no longer accessible: {e}")
                    await chat_link_store.remove(message.chat_id, message_thread_id)
                    recent_chats.clear_chat_path(message.chat_id)
                    chat_id = None

            try:
                response_text = None
                
                if chat_id:
                    previous = get_previous_response(str(message.chat_id))
                    response_text = await process_prompt_in_chat(driver, chat_id, prompt_text, previous)
                    if response_text:
                        update_previous_response(str(message.chat_id), response_text)
                else:
                    # Create new chat and send prompt
                    previous = get_previous_response(str(message.chat_id))
                    response_text = await process_prompt_in_chat(driver, None, prompt_text, previous)
                    if response_text:
                        update_previous_response(str(message.chat_id), response_text)
                        # Extract the new chat ID after ChatGPT has responded
                        current_url = await driver.current_url
                        new_chat_id = _extract_chat_id(current_url)
                        log_debug(f"[selenium][DEBUG] New chat created, extracted ID: {new_chat_id}")
                        log_debug(f"[selenium][DEBUG] Current URL: {current_url}")
                        if new_chat_id:
                            await chat_link_store.save_link(message.chat_id, message_thread_id, new_chat_id)
                            log_debug(f"[selenium][DEBUG] Saved link: {message.chat_id}/{message_thread_id} -> {new_chat_id}")
                            _safe_notify(
                                f"⚠️ Couldn't find ChatGPT conversation for chat_id={message.chat_id}, message_thread_id={message_thread_id}.\n"
                                f"A new ChatGPT chat has been created: {new_chat_id}"
                            )
                        else:
                            log_warning("[selenium][WARN] Failed to extract chat ID from URL")

                # Check if conversation is full and needs a new chat
                if await check_conversation_full(driver):
                    current_id = chat_id or _extract_chat_id(await driver.current_url)
                    global queue_paused
                    queue_paused = True
                    
                    await open_new_chat(driver)
                    response_text = await process_prompt_in_chat(driver, None, prompt_text, "")
                    
                    current_url = await driver.current_url
                    new_chat_id = _extract_chat_id(current_url)
                    if new_chat_id:
                        await chat_link_store.save_link(message.chat_id, message_thread_id, new_chat_id)
                        log_debug(f"[selenium][SUCCESS] New chat created for full conversation. Chat ID: {new_chat_id}")
                    queue_paused = False

                if not response_text:
                    response_text = "⚠️ No response received"

                # Send response through the interface (generic approach)
                await self._send_response(bot, message, response_text)
                log_debug(f"[selenium][STEP] response forwarded to {message.chat_id}")
                return

            except Exception as e:
                log_error(f"[selenium] Error processing message: {e}")
                if attempt == 0:
                    log_debug("[selenium] Retrying after error")
                    try:
                        await self.driver.quit()
                    except Exception:
                        pass
                    self.driver = None
                    self._browser = None
                    continue
                _notify_gui(f"❌ Selenium error: {e}. Open UI")
                return

    async def start(self):
        """Start the background worker loop."""
        log_debug("[selenium] 🟢 start() called")
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
                asyncio.create_task(self.driver.quit())
                log_debug("[selenium] Chrome driver closed")
            except Exception as e:
                log_warning(f"[selenium] Failed to close driver: {e}")
            finally:
                self.driver = None
                self._browser = None
        
        # Kill any remaining Chrome processes
        try:
            subprocess.run(["pkill", "-f", "chrome"], capture_output=True, text=True)
            subprocess.run(["pkill", "-f", "chromedriver"], capture_output=True, text=True)
            log_debug("[selenium] Killed remaining Chrome processes")
        except Exception as e:
            log_debug(f"[selenium] Failed to kill processes: {e}")
        
        log_debug("[selenium] Cleanup completed")

    async def stop(self):
        """Stop the worker and cleanup."""
        log_debug("[selenium] 🔴 stop() called")
        
        if self._worker_task:
            self._worker_task.cancel()
            await asyncio.gather(self._worker_task, return_exceptions=True)
        self.cleanup()

    def is_worker_running(self) -> bool:
        """Check if worker is running."""
        return self._worker_task is not None and not self._worker_task.done()

    def _handle_worker_done(self, fut: asyncio.Future):
        if fut.cancelled():
            log_warning("[selenium] Worker task cancelled")
        elif fut.exception():
            log_error(f"[selenium] Worker task crashed: {fut.exception()}", fut.exception())
        # Attempt restart if needed
        try:
            loop = asyncio.get_running_loop()
            if loop.is_running():
                loop.create_task(self.start())
        except RuntimeError:
            pass

    def get_supported_models(self):
        """Return list of supported models."""
        return []  # No specific models for now

    def get_rate_limit(self):
        """Return rate limit information (requests, window_seconds, cooldown)."""
        return (80, 10800, 0.5)

    def set_notify_fn(self, fn):
        """Set notification function."""
        self._notify_fn = fn
        set_notifier(fn)
        if self.driver is None:
            try:
                asyncio.create_task(self._ensure_driver())
            except Exception as e:
                log_error("[selenium] set_notify_fn initialization error", e)
                _notify_gui(f"❌ Selenium error: {e}. Open UI")

    @staticmethod
    async def clean_chat_link(chat_id: int) -> str:
        """Disassociates the chat ID from the ChatGPT chat ID in the database.
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
    """Handles the /clear_chat_link command for any interface."""
    chat_id = message.chat_id
    text = getattr(message, 'text', '') or getattr(message, 'content', '')
    text = text.strip()

    if text == "/clear_chat_link":
        # No arguments provided, ask for confirmation
        confirmation_message = (
            f"⚠️ Do you really want to reset the link for this chat (ID: {chat_id})?\n"
            "Reply with 'yes' to confirm or use /cancel to cancel."
        )
        
        # Send confirmation message using generic method
        try:
            if hasattr(bot, 'send_message'):
                await bot.send_message(chat_id=chat_id, text=confirmation_message)
            elif hasattr(bot, 'send'):
                await bot.send(chat_id, confirmation_message)
            else:
                log_warning("[selenium] Cannot send confirmation message - bot interface not supported")
                return
        except Exception as e:
            log_error(f"[selenium] Failed to send confirmation message: {e}")
            return

        # Wait for the user's response (this would need to be handled by the interface layer)
        # For now, just execute the command directly since we can't generically wait for responses
        result = await SeleniumChatGPTPlugin.clean_chat_link(chat_id)
        try:
            if hasattr(bot, 'send_message'):
                await bot.send_message(chat_id=chat_id, text=result)
            elif hasattr(bot, 'send'):
                await bot.send(chat_id, result)
        except Exception as e:
            log_error(f"[selenium] Failed to send result message: {e}")
    else:
        # Normal handling with arguments
        result = await SeleniumChatGPTPlugin.clean_chat_link(chat_id)
        try:
            if hasattr(bot, 'send_message'):
                await bot.send_message(chat_id=chat_id, text=result)
            elif hasattr(bot, 'send'):
                await bot.send(chat_id, result)
        except Exception as e:
            log_error(f"[selenium] Failed to send result message: {e}")


# Plugin export
PLUGIN_CLASS = SeleniumChatGPTPlugin
