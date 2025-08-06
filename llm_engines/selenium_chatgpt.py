import asyncio
import os
import re
import json
import inspect
import time
from dataclasses import dataclass
from typing import Optional

import aiomysql
import nodriver as uc

from core.db import get_conn
from core.logging_utils import log_debug, log_info, log_warning, log_error
from core.ai_plugin_base import AIPluginBase


class Keys:
    """Simple replacement for selenium Keys."""

    ENTER = "__ENTER__"


@dataclass
class By:
    CSS_SELECTOR: str = "css"
    ID: str = "id"


class ChatLinkStore:
    """Persist mapping between Telegram chats and ChatGPT conversations."""

    def __init__(self) -> None:
        self._table_ensured = False

    def _normalize_thread_id(self, message_thread_id: Optional[int | str]) -> str:
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
        norm = self._normalize_thread_id(message_thread_id)
        log_debug(f"[ChatLinkStore] Searching for chat_id={chat_id}, normalized_thread_id={norm}")
        conn = await get_conn()
        try:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    "SELECT link FROM chatgpt_links WHERE chat_id=%s AND message_thread_id=%s",
                    (str(chat_id), norm),
                )
                row = await cur.fetchone()
                log_debug(f"[ChatLinkStore] Query result: {row}")
                return row["link"] if row else None
        finally:
            conn.close()

    async def save_link(
        self, chat_id: int | str, message_thread_id: Optional[int | str], link: str
    ) -> None:
        await self._ensure_table()
        norm = self._normalize_thread_id(message_thread_id)
        conn = await get_conn()
        try:
            async with conn.cursor() as cur:
                await cur.execute(
                    "REPLACE INTO chatgpt_links (chat_id, message_thread_id, link) VALUES (%s, %s, %s)",
                    (str(chat_id), norm, link),
                )
                await conn.commit()
        finally:
            conn.close()

    async def remove(self, chat_id: int | str, message_thread_id: Optional[int | str]) -> bool:
        await self._ensure_table()
        norm = self._normalize_thread_id(message_thread_id)
        conn = await get_conn()
        try:
            async with conn.cursor() as cur:
                res = await cur.execute(
                    "DELETE FROM chatgpt_links WHERE chat_id=%s AND message_thread_id=%s",
                    (str(chat_id), norm),
                )
                await conn.commit()
                return res > 0
        finally:
            conn.close()


chat_link_store = ChatLinkStore()


async def is_chat_archived(driver, chat_id: str) -> bool:
    """Check if a ChatGPT chat is archived (adapted from original version)."""
    if not chat_id:
        return False
    
    try:
        # Navigate to the chat to check its status (like the original version)
        chat_url = f"https://chatgpt.com/c/{chat_id}"
        log_debug(f"[selenium] Checking if chat {chat_id} is archived by navigating to {chat_url}")
        await driver.get(chat_url)
        
        # Wait a moment for page to load
        await asyncio.sleep(3)
        
        # Check for archived message (adapted from original)
        try:
            # Look for archived indicator in page content
            page_text = await driver._tab.evaluate("document.body.innerText || ''")
            if "this conversation is archived" in page_text.lower():
                log_warning(f"[selenium] Chat {chat_id} is archived")
                return True
            
            # Check if textarea is present (indicates chat is accessible)
            has_textarea = await driver._tab.evaluate("!!document.getElementById('prompt-textarea')")
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


async def get_latest_reply_text(tab) -> str | None:
    """
    Estrae l'ultima risposta dell'assistente da ChatGPT Web DOM usando nodriver.

    Args:
        tab: nodriver.core.Tab — la tab corrente

    Returns:
        str | None: testo markdown dell'ultima risposta dell'LLM, o None se non trovato
    """
    log_debug("[selenium] 🔍 Looking for assistant messages...")
    nodes = await tab.query_selector_all('div[data-message-author-role="assistant"] div.markdown')
    if not nodes:
        log_warning("[selenium] No assistant messages found in DOM.")
        return None

    last = nodes[-1]
    log_debug("[selenium] ✅ Assistant message found. Extracting inner text...")
    text = await last.inner_text()
    return text.strip() if text else None


async def count_response_elements(driver) -> int:
    """Count existing assistant response elements using data-message-author-role attribute."""
    try:
        nodes = await driver._tab.query_selector_all('div[data-message-author-role="assistant"]')
        count = len(nodes)
        log_debug(f"[selenium] Counted {count} existing assistant messages")
        return count
    except Exception as e:
        log_warning(f"[selenium] Failed to count assistant messages: {e}")
        return 0


async def wait_for_response(driver, prev_count: int, timeout: int = 120) -> str:
    """Wait for ChatGPT response and return the text once it stabilizes."""
    start_time = time.time()
    last_text = ""
    last_change_time = time.time()
    stability_threshold = 3.5  # Use original stability threshold
    
    log_debug(f"[selenium] Waiting for response (prev_count={prev_count})")
    
    while time.time() - start_time < timeout:
        try:
            # Count current assistant messages
            current_nodes = await driver._tab.query_selector_all('div[data-message-author-role="assistant"]')
            current_count = len(current_nodes)
            
            log_debug(f"[selenium] Found {current_count} assistant messages (need > {prev_count})")
            
            if current_count > prev_count:
                # Get the latest response text
                latest_text = await get_latest_reply_text(driver._tab)
                
                if latest_text and latest_text.strip():
                    current_text = latest_text.strip()
                    
                    # Check if text has changed (original logic)
                    if current_text != last_text:
                        last_text = current_text
                        last_change_time = time.time()
                        log_debug(f"[selenium] Response updated: {len(last_text)} chars")
                    else:
                        # Text hasn't changed, check if enough time has passed
                        time_since_change = time.time() - last_change_time
                        if time_since_change >= stability_threshold and last_text:
                            log_debug(f"[selenium] *** RESPONSE STABLE FOR {time_since_change:.1f}s *** ({len(last_text)} chars)")
                            return last_text
                        elif last_text:
                            log_debug(f"[selenium] Response stable for {time_since_change:.1f}s/{stability_threshold}s")
                        
                else:
                    log_debug("[selenium] Found assistant message but text is empty, waiting...")
            else:
                log_debug(f"[selenium] Still waiting for response... ({current_count} messages, need > {prev_count})")
                        
        except Exception as e:
            log_warning(f"[selenium] Error checking response: {e}")
            
        await asyncio.sleep(0.5)  # Check frequently but not too frequently
    
    log_warning(f"[selenium] Timeout waiting for response after {timeout}s, last_text: '{last_text[:100] if last_text else 'None'}...'")
    return last_text if last_text else ""


async def send_prompt_to_chatgpt(driver, prompt_text: str) -> bool:
    """Send a prompt to ChatGPT and return True if successful."""
    try:
        # Find the textarea
        textarea = await driver.find_element(By.ID, "prompt-textarea")
        if not textarea:
            log_error("[selenium] Prompt textarea not found")
            return False
            
        # Clear and send the prompt using the original method
        await textarea.clear()
        await asyncio.sleep(0.5)
        await textarea.send_keys(prompt_text)
        await asyncio.sleep(1)  # Give time for text to be processed
        
        # Send Enter key to submit (like original version)
        await textarea.send_keys(Keys.ENTER)
        log_debug("[selenium] Message sent via Enter key")
        return True
        
    except Exception as e:
        log_error(f"[selenium] Failed to send prompt: {e}")
        return False


class NodriverElementWrapper:
    """Minimal wrapper to provide a selenium-like API."""

    def __init__(self, element, tab):
        self._el = element
        self._tab = tab

    async def _call(self, name: str, *args) -> bool:
        """Call an element method if present and await the result if needed."""
        fn = getattr(self._el, name, None)
        if not callable(fn):
            return False
        try:
            result = fn(*args)
            if inspect.isawaitable(result):
                await result
            return True
        except Exception as e:  # pragma: no cover - best effort
            log_error(f"[selenium] {name} failed: {e}")
            return False

    async def clear(self) -> None:
        """Attempt to empty the element's value using available nodriver APIs."""
        try:
            # Try multiple methods to clear the element
            if await self._call("clear"):
                return
            if await self._call("set_value", ""):
                return
            # Use JavaScript as fallback
            await self._tab.evaluate(
                """
                const el = document.getElementById('prompt-textarea');
                if (el) {
                    el.value = '';
                    el.innerText = '';
                    el.textContent = '';
                    el.dispatchEvent(new Event('input', { bubbles: true }));
                    el.dispatchEvent(new Event('change', { bubbles: true }));
                }
                """,
            )
            log_debug("[selenium] Successfully cleared textarea via JavaScript")
        except Exception as e:  # pragma: no cover - best effort
            log_error(f"[selenium] Failed to clear textarea: {e}")

    async def send_keys(self, text: str) -> None:
        """Send text or special keys to the wrapped element."""
        if text == Keys.ENTER:
            try:
                result = await self._tab.evaluate("""
                    (() => {
                        const textarea = document.getElementById('prompt-textarea');
                        if (textarea) {
                            textarea.dispatchEvent(new InputEvent('input', { bubbles: true }));
                            textarea.dispatchEvent(new Event('change', { bubbles: true }));
                            textarea.focus();
                            textarea.blur();
                        }

                        const btn = document.getElementById('composer-submit-button');
                        if (btn && !btn.disabled) {
                            btn.click();
                            return 'clicked #composer-submit-button';
                        }

                        return 'button not found or disabled';
                    })()
                """)
                log_debug(f"[selenium] ENTER result: {result}")
            except Exception as e:
                log_error(f"[selenium] Failed to send ENTER via button click: {e}")
        else:
            try:
                escaped = text.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n").replace("\r", "")
                await self._tab.evaluate(
                    f"""
                    const el = document.getElementById('prompt-textarea');
                    if (el) {{
                        el.value = '{escaped}';
                        el.innerText = '{escaped}';
                        el.textContent = '{escaped}';
                        el.dispatchEvent(new InputEvent('input', {{ bubbles: true }}));
                        el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                        el.focus();
                    }}
                    """,
                )
                log_debug(f"[selenium] Successfully sent {len(text)} characters via JavaScript")
            except Exception as e:
                log_error(f"[selenium] Failed to send keys: {e}")
                if not await self._call("type", text):
                    await self._call("send_keys", text)

    async def get_attribute(self, name: str) -> Optional[str]:
        try:
            if hasattr(self._el, "get_attribute"):
                return await self._el.get_attribute(name)
            if hasattr(self._el, "get_property"):
                return await self._el.get_property(name)
        except Exception:
            return None
        return None

    async def text(self) -> str:
        try:
            # Method 1: Try nodriver's text methods with proper checks
            if hasattr(self._el, "text"):
                text_method = getattr(self._el, "text")
                if callable(text_method):
                    try:
                        result = await text_method()
                        if result and isinstance(result, str):
                            log_debug(f"[selenium] Got text via text() method: '{result[:50]}...'")
                            return result
                    except Exception as e:
                        log_debug(f"[selenium] text() method failed: {e}")
            
            # Method 2: Try inner_text property
            if hasattr(self._el, "inner_text"):
                inner_text_attr = getattr(self._el, "inner_text")
                if callable(inner_text_attr):
                    try:
                        result = await inner_text_attr()
                        if result and isinstance(result, str):
                            log_debug(f"[selenium] Got text via inner_text() method: '{result[:50]}...'")
                            return result
                    except Exception as e:
                        log_debug(f"[selenium] inner_text() method failed: {e}")
                elif isinstance(inner_text_attr, str) and inner_text_attr:
                    log_debug(f"[selenium] Got text via inner_text property: '{inner_text_attr[:50]}...'")
                    return inner_text_attr
            
            # Method 3: Use JavaScript evaluation directly
            try:
                result = await self._tab.evaluate(
                    """
                    (element) => {
                        if (!element) return '';
                        return element.innerText || element.textContent || element.innerHTML || '';
                    }
                    """, self._el
                )
                if result and isinstance(result, str):
                    log_debug(f"[selenium] Got text via JavaScript: '{result[:50]}...'")
                    return result
            except Exception as e:
                log_debug(f"[selenium] JavaScript text extraction failed: {e}")
            
            # Method 4: Fallback to attributes
            attr = await self.get_attribute("innerText")
            if attr and isinstance(attr, str):
                log_debug(f"[selenium] Got text via innerText attribute: '{attr[:50]}...'")
                return attr
            
            attr = await self.get_attribute("textContent")
            if attr and isinstance(attr, str):
                log_debug(f"[selenium] Got text via textContent attribute: '{attr[:50]}...'")
                return attr
                
            log_debug("[selenium] No text content found in element")
            return ""
                
        except Exception as e:
            log_debug(f"[selenium] Error getting text: {e}")
            return ""
 
class NodriverSeleniumWrapper:
    """Expose a very small selenium-like surface over nodriver."""

    def __init__(self, tab):
        self._tab = tab

    async def get(self, url: str) -> None:
        """Navigate the underlying tab to ``url``.

        ``nodriver`` has changed navigation APIs a few times.  Some versions
        expose ``tab.get`` while others use ``tab.goto``.  To remain compatible
        across releases we try both.
        """
        if hasattr(self._tab, "get"):
            await self._tab.get(url)
            return
        if hasattr(self._tab, "goto"):
            await self._tab.goto(url)
            return
        raise AttributeError("tab has neither 'get' nor 'goto' method")

    async def find_element(self, by: str, selector: str):
        css = self._to_css(by, selector)
        if not css:
            return None
        el = await self._tab.select(css, timeout=20)
        return NodriverElementWrapper(el, self._tab) if el else None

    async def find_elements(self, by: str, selector: str):
        css = self._to_css(by, selector)
        if not css:
            return []
        els = await self._tab.select_all(css, timeout=1)
        return [NodriverElementWrapper(e, self._tab) for e in els]

    def _to_css(self, by: str, selector: str) -> str | None:
        if by == By.ID:
            return f"#{selector}"
        if by == By.CSS_SELECTOR:
            return selector
        return None

    async def current_url(self) -> str:
        try:
            return await self._tab.evaluate("window.location.href")
        except Exception:
            return getattr(self._tab, "url", "")


class SeleniumChatGPTClient(AIPluginBase):
    """Minimal ChatGPT browser client powered by nodriver."""

    # Class-level storage for chat locks and queue
    chat_locks = {}
    
    def __init__(self, notify_fn=None):
        self._browser = None
        self._driver: NodriverSeleniumWrapper | None = None
        self._queue = asyncio.Queue()
        self._worker_started = False
        if notify_fn:
            from core.notifier import set_notifier

            log_debug("[selenium] Using custom notifier function")
            set_notifier(notify_fn)

    async def handle_incoming_message(self, bot, message, prompt):
        """Queue the message to be processed sequentially."""
        user_id = message.from_user.id if message.from_user else "unknown"
        text = message.text or ""
        log_debug(
            f"[selenium] [ENTRY] chat_id={message.chat_id} user_id={user_id} text={text!r}"
        )
        
        # Ensure worker is started
        if not self._worker_started:
            asyncio.create_task(self._queue_worker())
            self._worker_started = True
        
        # Check if this chat is busy
        lock = SeleniumChatGPTClient.chat_locks.get(message.chat_id)
        if lock and lock.locked():
            log_debug(f"[selenium] Chat {message.chat_id} busy, waiting")
        
        await self._queue.put((bot, message, prompt))
        log_debug("[selenium] Message queued for processing")
        if self._queue.qsize() > 10:
            log_warning(
                f"[selenium] Queue size high ({self._queue.qsize()}). Worker might be stalled"
            )

    async def _queue_worker(self):
        """Process messages from queue sequentially."""
        log_debug("[selenium] Queue worker started")
        while True:
            try:
                bot, message, prompt = await self._queue.get()
                await self.process_prompt_in_chat(bot, message, prompt)
                self._queue.task_done()
            except Exception as e:
                log_error(f"[selenium] Queue worker error: {e}")
                await asyncio.sleep(1)  # Avoid tight error loops
                
    async def process_prompt_in_chat(self, bot, message, prompt):
        """Process a prompt in the appropriate ChatGPT chat."""
        from core.notifier import notify_trainer
        from core.config import TRAINER_ID

        chat_id = message.chat_id
        message_thread_id = getattr(message, "message_thread_id", None)

        # ✅ CORRETTO: invia tutto il JSON formattato
        user_text = json.dumps(prompt, ensure_ascii=False, indent=2)
        log_debug(f"[selenium] Using full JSON prompt: {user_text[:200]}...")

        # Acquire chat lock
        if chat_id not in SeleniumChatGPTClient.chat_locks:
            SeleniumChatGPTClient.chat_locks[chat_id] = asyncio.Lock()

        async with SeleniumChatGPTClient.chat_locks[chat_id]:
            log_debug(f"[selenium] Processing prompt for chat {chat_id}")
            try:
                chat_url = await self._get_chat_url(chat_id, message_thread_id)
                reply, final_url = await self.ask(user_text, chat_url)
                await chat_link_store.save_link(chat_id, message_thread_id, final_url)

                if bot and message and reply:
                    log_debug(f"[selenium] Sending reply to chat_id={message.chat_id}")
                    await bot.send_message(
                        chat_id=message.chat_id,
                        text=reply,
                        reply_to_message_id=message.message_id
                    )
                return reply

            except Exception as e:
                log_error(f"[selenium] Error processing prompt: {e}")
                notify_trainer(TRAINER_ID, f"❌ Selenium ChatGPT error:\n```\n{e}\n```")
                if bot and message:
                    await bot.send_message(
                        chat_id=message.chat_id,
                        text="⚠️ ChatGPT response error."
                    )
                return "⚠️ Error during response generation."


    async def _get_chat_url(self, chat_id: int, message_thread_id: Optional[int | str]) -> str:
        """Get or create ChatGPT conversation URL for this chat."""
        log_debug(f"[selenium] Looking for chat URL: chat_id={chat_id}, thread_id={message_thread_id}")
        
        # Try to get existing link from database
        stored_link = await chat_link_store.get_link(chat_id, message_thread_id)
        log_debug(f"[selenium] Database returned link: {stored_link}")
        
        if stored_link:
            # Extract chat ID from stored link and check if archived
            extracted_chat_id = self._extract_chat_id(stored_link)
            log_debug(f"[selenium] Extracted chat ID from URL: {extracted_chat_id}")
            if extracted_chat_id:
                driver = await self._ensure_driver()
                is_archived = await is_chat_archived(driver, extracted_chat_id)
                if not is_archived:
                    log_debug(f"[selenium] Using existing chat URL: {stored_link}")
                    return stored_link
                else:
                    log_warning(f"[selenium] Chat {extracted_chat_id} is archived, creating new chat")
                    # Remove archived link
                    await chat_link_store.remove(chat_id, message_thread_id)
            else:
                log_warning(f"[selenium] Could not extract chat ID from {stored_link}, creating new chat")
        
        # Create new chat - just return ChatGPT home URL
        log_debug(f"[selenium] No valid chat found for {chat_id}, will start new conversation")
        return "https://chatgpt.com"
    
    def _extract_chat_id(self, chat_url: str) -> Optional[str]:
        """Extract ChatGPT chat ID from URL."""
        # Match pattern like https://chatgpt.com/c/abcd1234-5678-9abc-def0-123456789abc
        match = re.search(r"/c/([a-f0-9\-]+)", chat_url)
        if match:
            return match.group(1)
        return None

    async def _ensure_driver(self) -> NodriverSeleniumWrapper:
        if self._driver:
            return self._driver

        profile_dir = "/home/rekku/.config/chromium-rekku"
        os.makedirs(profile_dir, exist_ok=True)
        log_info("[selenium] launching Chromium via nodriver")
        try:
            browser = await uc.start(
                headless=False,
                no_sandbox=True,  # Required when running as root (Docker)
                user_data_dir=profile_dir,
                browser_args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-web-security"],
            )
        except Exception as e:  # pragma: no cover - launch problems
            log_error(f"[selenium] failed to start Chromium: {e}")
            raise

        try:
            tab = await browser.get("https://chatgpt.com")
            await asyncio.sleep(3)  # Give time for page to load
        except Exception as e:  # pragma: no cover - navigation problems
            log_error(f"[selenium] initial navigation failed: {e}")
            raise

        log_debug("[selenium] Chromium session ready")
        self._browser = browser
        self._driver = NodriverSeleniumWrapper(tab)
        return self._driver

    async def _get_tab(self):
        """Return the current browser tab."""
        driver = await self._ensure_driver()
        return driver._tab

    async def ask(self, prompt: str, url: str | None = None) -> tuple[str | None, str | None]:
        """
        Sends a prompt to the web, waits for the ChatGPT response until it stabilizes, and returns
        the final text and the current chat URL.
        """
        log_info("[selenium] Sending prompt to ChatGPT…")
        driver = await self._ensure_driver()

        if url:
            log_debug(f"[selenium] Navigating to {url}")
            await driver.get(url)
            await asyncio.sleep(2)  # ⏳ Allow page to fully load

        tab = driver._tab

        # 🔁 Retry until prompt-textarea appears
        textarea = None
        for attempt in range(10):
            textarea = await tab.query_selector("#prompt-textarea")
            if textarea:
                break
            log_debug(f"[selenium] Waiting for prompt-textarea... ({attempt + 1}/10)")
            await asyncio.sleep(0.5)

        if textarea is None:
            log_error("[selenium] Prompt textarea not found after retries")
            url = await tab.url() if tab else "unknown"
            return None, url

        # ✅ Safety check: textarea must be interactable
        log_debug(f"[selenium] Typing {len(prompt)} characters…")
        
        # Clear textarea using JavaScript
        await tab.evaluate("""
            const textarea = document.getElementById('prompt-textarea');
            if (textarea) {
                textarea.value = '';
                textarea.dispatchEvent(new Event('input', { bubbles: true }));
                textarea.focus();
            }
        """)
        
        # Type the prompt using JavaScript
        escaped_prompt = prompt.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n").replace("\r", "")
        result = await tab.evaluate(f"""
            (() => {{
                const textarea = document.getElementById('prompt-textarea');
                if (!textarea) return '❌ textarea missing';

                const text = `{escaped_prompt}`;
                textarea.value = text;
                textarea.innerText = text;
                textarea.textContent = text;

                textarea.dispatchEvent(new InputEvent('input', {{ bubbles: true }}));
                textarea.dispatchEvent(new Event('change', {{ bubbles: true }}));
                textarea.focus();

                return '✅ prompt injected';
            }})()
        """)
        log_debug(f"[selenium] Prompt injection result: {result}")

        # Submit the prompt by clicking the send button
        submit_result = await tab.evaluate("""
            (() => {
                const btn = document.getElementById('composer-submit-button');
                if (btn && !btn.disabled) {
                    btn.click();
                    return 'clicked submit button';
                }
                return 'submit button not found or disabled';
            })()
        """)
        
        log_debug(f"[selenium] Submit result: {submit_result}")

        prev = ""
        stable = 0
        max_iter = 60

        for i in range(max_iter):
            await asyncio.sleep(1.0)
            reply = await get_latest_reply_text(tab)
            if not reply:
                log_debug("[selenium] No reply yet or failed to read assistant response")
                continue

            has_changed = reply != prev
            log_debug(f"[DEBUG] len={len(reply)} changed={has_changed}")

            if not reply.strip():
                continue

            if has_changed:"""  """
                stable = 0
                prev = reply
            else:
                stable += 1

            if stable >= 4:
                # Optional validation
                is_valid_fn = getattr(self, "_is_valid_response", None)
                if callable(is_valid_fn):
                    try:
                        if not is_valid_fn(reply):
                            log_warning("[selenium] Response rejected by validation check.")
                            return None, await tab.url()
                    except Exception as e:
                        log_error(f"[selenium] Error checking response: {e}")
                        return None, await tab.url()

                return prev.strip(), await tab.url()

        log_warning("[selenium] Timeout waiting for assistant response.")
        return None, await tab.url()

async def clean_chat_link(chat_id: int) -> bool:
    """Remove stored link for given Telegram chat."""
    return await chat_link_store.remove(chat_id, None)


PLUGIN_CLASS = SeleniumChatGPTClient
