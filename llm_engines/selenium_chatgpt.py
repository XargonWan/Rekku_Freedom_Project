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
        conn = await get_conn()
        try:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    "SELECT link FROM chatgpt_links WHERE chat_id=%s AND message_thread_id=%s",
                    (str(chat_id), norm),
                )
                row = await cur.fetchone()
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
    """Check if a ChatGPT chat is archived based on the current page content."""
    if not chat_id:
        return False
    
    try:
        # DON'T navigate again - we're already on the chat page
        log_debug(f"[selenium] Checking if current chat {chat_id} is archived (not navigating)")
        
        await asyncio.sleep(2)  # Give time for page to load
        
        # Check for archived message using text content
        try:
            page_text = await driver._tab.evaluate("document.body.innerText")
            if any(phrase in page_text.lower() for phrase in [
                "this conversation is archived",
                "conversation is archived", 
                "archived conversation",
                "no longer available", 
                "not found", 
                "deleted", 
                "unavailable"
            ]):
                log_warning(f"[selenium] Chat {chat_id} appears to be archived")
                return True
                
            # Also check if we can find the textarea (indicates chat is accessible)
            has_textarea = await driver._tab.evaluate("!!document.getElementById('prompt-textarea')")
            if has_textarea:
                log_debug(f"[selenium] Chat {chat_id} is accessible - found textarea")
                return False
            else:
                log_warning(f"[selenium] Chat {chat_id} may not be accessible - no textarea found")
                return True
                
        except Exception as e:
            log_warning(f"[selenium] Could not check page content: {e}")
            return True
            
    except Exception as e:
        log_error(f"[selenium] Error checking if chat {chat_id} is archived: {e}")
        return True


async def wait_for_response(driver, prev_count: int, timeout: int = 120) -> str:
    """Wait for ChatGPT response and return the text once it stabilizes."""
    start_time = time.time()
    last_text = ""
    same_count = 0
    required_stability = 3  # Number of consecutive checks with same text
    
    log_debug(f"[selenium] Waiting for response (prev_count={prev_count})")
    
    while time.time() - start_time < timeout:
        try:
            # Debug: Let's see what elements are actually on the page
            all_markdown = await driver.find_elements(By.CSS_SELECTOR, "div.markdown")
            all_prose = await driver.find_elements(By.CSS_SELECTOR, "div.prose")
            all_markdown_prose = await driver.find_elements(By.CSS_SELECTOR, "div.markdown.prose")
            
            log_debug(f"[selenium] Found elements: markdown={len(all_markdown)}, prose={len(all_prose)}, markdown.prose={len(all_markdown_prose)}")
            
            # Try multiple selectors to find response content
            response_elements = []
            selectors_to_try = [
                "div.markdown.prose",  # Original selector
                "div[data-message-author-role='assistant']", # From HTML file
                ".prose", # Just prose
                "[data-testid*='conversation-turn']", # Alternative
                ".text-base" # Common ChatGPT text class
            ]
            
            for selector in selectors_to_try:
                try:
                    elements = await driver.find_elements(By.CSS_SELECTOR, selector)
                    if len(elements) > prev_count:
                        response_elements = elements
                        log_debug(f"[selenium] Found {len(elements)} elements with selector '{selector}' (prev_count={prev_count})")
                        break
                except Exception:
                    continue
            
            if len(response_elements) > prev_count:
                # Get the latest response (last element)
                latest_element = response_elements[-1]
                text_content = await latest_element.text()
                
                if text_content and text_content.strip() != last_text:
                    last_text = text_content.strip()
                    same_count = 0
                    log_debug(f"[selenium] Response updated: {len(last_text)} chars - '{last_text[:100]}...'")
                elif text_content and text_content.strip() == last_text and last_text:
                    same_count += 1
                    log_debug(f"[selenium] Response stable #{same_count}/{required_stability}: {len(last_text)} chars")
                    if same_count >= required_stability:
                        log_debug(f"[selenium] Response stabilized: {len(last_text)} chars")
                        return last_text
            else:
                log_debug(f"[selenium] Still waiting for response... ({len(response_elements)} elements, need > {prev_count})")
                        
        except Exception as e:
            log_warning(f"[selenium] Error checking response: {e}")
            
        await asyncio.sleep(1)
    
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
            
        # Clear and send the prompt
        await textarea.clear()
        await asyncio.sleep(0.5)
        await textarea.send_keys(prompt_text)
        await asyncio.sleep(1)  # Give more time for text to be processed
        
        # Now try to send the message using multiple strategies
        log_debug("[selenium] Attempting to send message...")
        
        # Strategy 1: Click the send button by ID (most reliable from original version)
        try:
            send_button = await driver.find_element(By.ID, "composer-submit-button")
            if send_button:
                await send_button._el.click()
                log_debug("[selenium] Message sent via composer-submit-button ID")
                return True
        except Exception as e:
            log_warning(f"[selenium] composer-submit-button click failed: {e}")
        
        # Strategy 2: Click the send button by data-testid
        try:
            send_button = await driver.find_element(By.CSS_SELECTOR, '[data-testid="send-button"]')
            if send_button:
                await send_button._el.click()
                log_debug("[selenium] Message sent via data-testid send-button")
                return True
        except Exception as e:
            log_warning(f"[selenium] data-testid send-button click failed: {e}")
        
        # Strategy 3: Click the send button directly via JavaScript
        try:
            result = await driver._tab.evaluate(
                """
                // Look for the specific button selectors from ChatGPT
                const selectors = [
                    '#composer-submit-button',
                    '[data-testid="send-button"]',
                    'button[type="submit"]',
                    'form button:last-child'
                ];
                
                for (const selector of selectors) {
                    const btn = document.querySelector(selector);
                    if (btn && !btn.disabled && btn.offsetParent !== null) {
                        btn.click();
                        console.log('Clicked send button with selector:', selector);
                        return 'success';
                    }
                }
                
                return 'failed';
                """,
            )
            
            if result == 'success':
                log_debug("[selenium] Message sent via JavaScript button click")
                return True
                
        except Exception as e:
            log_warning(f"[selenium] JavaScript send failed: {e}")
        
        log_error("[selenium] All send strategies failed")
        return False
        
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
                # Use JavaScript to find and click the send button directly
                result = await self._tab.evaluate(
                    """
                    // First try to find the send button by common selectors
                    let sendBtn = document.querySelector('[data-testid="send-button"]') ||
                                  document.querySelector('button[type="submit"]') ||
                                  document.querySelector('button:has(svg)') ||
                                  document.querySelector('form button:last-child') ||
                                  document.querySelector('[aria-label*="Send"], [title*="Send"]');
                    
                    if (sendBtn && !sendBtn.disabled) {
                        sendBtn.click();
                        console.log('Clicked send button');
                        return 'button_clicked';
                    }
                    
                    // If no button found, try Enter key on the textarea
                    const textarea = document.getElementById('prompt-textarea');
                    if (textarea) {
                        textarea.focus();
                        // Simulate Ctrl+Enter which is often used to send
                        textarea.dispatchEvent(new KeyboardEvent('keydown', {
                            key: 'Enter',
                            code: 'Enter',
                            ctrlKey: true,
                            bubbles: true
                        }));
                        textarea.dispatchEvent(new KeyboardEvent('keyup', {
                            key: 'Enter', 
                            code: 'Enter',
                            ctrlKey: true,
                            bubbles: true
                        }));
                        console.log('Sent Ctrl+Enter to textarea');
                        return 'ctrl_enter_sent';
                    }
                    
                    return 'failed';
                    """,
                )
                log_debug(f"[selenium] ENTER result: {result}")
                
                # If JavaScript didn't work, try nodriver methods
                if result == 'failed':
                    await self._call("press", "Enter")
                    
            except Exception as e:  # pragma: no cover - best effort
                log_error(f"[selenium] Failed to send ENTER: {e}")
        else:
            try:
                # Try setting the value directly via JavaScript for better reliability
                escaped = text.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n").replace("\r", "")
                await self._tab.evaluate(
                    f"""
                    const el = document.getElementById('prompt-textarea');
                    if (el) {{
                        el.value = '{escaped}';
                        el.innerText = '{escaped}';
                        el.textContent = '{escaped}';
                        el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                        el.focus();
                    }}
                    """,
                )
                log_debug(f"[selenium] Successfully sent {len(text)} characters via JavaScript")
            except Exception as e:  # pragma: no cover - best effort
                log_error(f"[selenium] Failed to send keys: {e}")
                # Try the nodriver methods as fallback
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
            if hasattr(self._el, "text"):
                return await self._el.text()
            if hasattr(self._el, "inner_text"):
                return await self._el.inner_text()
            attr = await self.get_attribute("innerText")
            if attr:
                return attr
        except Exception:
            return ""
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

    def __init__(self, notify_fn=None):
        self._browser = None
        self._driver: NodriverSeleniumWrapper | None = None
        if notify_fn:
            from core.notifier import set_notifier

            log_debug("[selenium] Using custom notifier function")
            set_notifier(notify_fn)

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
            tab = await browser.get("https://chat.openai.com")
            await asyncio.sleep(3)  # Give time for page to load
        except Exception as e:  # pragma: no cover - navigation problems
            log_error(f"[selenium] initial navigation failed: {e}")
            raise

        log_debug("[selenium] Chromium session ready")
        self._browser = browser
        self._driver = NodriverSeleniumWrapper(tab)
        return self._driver

    async def ask(self, prompt: str, chat_url: str) -> tuple[str, str]:
        """Send a prompt to ChatGPT and return the response and final URL."""
        driver = await self._ensure_driver()
        
        try:
            log_debug(f"[selenium] [STEP 1] Navigating to: {chat_url}")
            # Navigate to the chat URL
            await driver.get(chat_url)
            await asyncio.sleep(3)  # Wait for page to load
            
            # Verify we actually navigated to the right place
            current_url = await driver.current_url()
            log_debug(f"[selenium] [STEP 2] Actually navigated to: {current_url}")
            
            # Extract chat ID from URL for validation
            chat_id = None
            if "chat.openai.com" in chat_url:
                # Try both URL formats: /chat/id and /c/id
                for pattern in [r'/chat/([^/?]+)', r'/c/([^/?]+)']:
                    match = re.search(pattern, chat_url)
                    if match:
                        chat_id = match.group(1)
                        break
                        
            if chat_id:
                log_debug(f"[selenium] [STEP 3] Checking if chat {chat_id} is archived")
                if await is_chat_archived(driver, chat_id):
                    log_warning(f"[selenium] Chat {chat_id} is archived, creating new chat")
                    await driver.get("https://chat.openai.com")
                    await asyncio.sleep(3)
                    # Update current URL after fallback
                    current_url = await driver.current_url()
                    log_debug(f"[selenium] [STEP 3b] Fallback navigation to: {current_url}")
            
            log_debug("[selenium] [STEP 4] Counting existing messages using correct selector")
            # Count existing assistant messages using the correct selector from original
            prev_count = 0
            try:
                # Use the exact CSS selector from the original version
                message_elements = await driver.find_elements(By.CSS_SELECTOR, "div.markdown.prose")
                prev_count = len(message_elements)
                log_debug(f"[selenium] Found {prev_count} existing markdown blocks (messages)")
            except Exception as e:
                log_warning(f"[selenium] Could not count existing messages: {e}")
            
            log_debug("[selenium] [STEP 5] Looking for prompt textarea using correct ID")
            # Find the textarea using the correct ID from original version
            textarea = await driver.find_element(By.ID, "prompt-textarea")
            if not textarea:
                log_error("[selenium] Could not find prompt textarea with ID 'prompt-textarea'")
                raise RuntimeError("Textarea not found")
                
            log_debug("[selenium] [STEP 6] Sending prompt to textarea")
            # Send the prompt text to the textarea
            await textarea.send_keys(prompt)
            
            log_debug("[selenium] [STEP 7] Looking for send button")
            # Find the send button using the correct ID and data-testid from the original version
            send_button = None
            try:
                # Try by ID first
                send_button = await driver.find_element(By.ID, "composer-submit-button")
                log_debug("[selenium] Found send button by ID: composer-submit-button")
            except Exception:
                try:
                    # Try by data-testid
                    send_button = await driver.find_element(By.CSS_SELECTOR, '[data-testid="send-button"]')
                    log_debug("[selenium] Found send button by data-testid: send-button")
                except Exception:
                    log_error("[selenium] Could not find send button")
                    raise RuntimeError("Send button not found")
            
            log_debug("[selenium] [STEP 8] Clicking send button")
            # Click the send button
            await send_button._el.click()
            
            log_debug("[selenium] [STEP 8] Waiting for response with timeout")
            # Wait for response with proper timeout
            reply = await wait_for_response(driver, prev_count, timeout=180)
            if not reply:
                raise RuntimeError("No response received from ChatGPT")
                
            # Get final URL
            final_url = await driver.current_url()
            
            log_debug(f"[selenium] Received reply of {len(reply)} chars")
            return reply, final_url
            
        except Exception as e:
            log_error(f"[selenium] Error in ask method: {e}")
            # Try to get current URL even if there was an error
            try:
                final_url = await driver.current_url()
            except:
                final_url = chat_url
            raise RuntimeError(f"ChatGPT interaction failed: {e}")

    async def handle_incoming_message(self, bot, message, prompt: dict) -> str:
        """Process an incoming message using the ChatGPT web UI."""
        chat_id = getattr(message, "chat_id", None)
        thread_id = getattr(message, "message_thread_id", None)

        try:
            # Convert prompt to JSON string
            if isinstance(prompt, dict):
                json_prompt = json.dumps(prompt, ensure_ascii=False)
                input_payload = prompt.get("input", {}).get("payload", {})
                if chat_id is None:
                    chat_id = input_payload.get("source", {}).get("chat_id")
                if thread_id is None:
                    thread_id = input_payload.get("source", {}).get("message_thread_id")
            else:
                json_prompt = str(prompt)

            if not json_prompt or chat_id is None:
                log_warning("[selenium] Missing prompt or chat_id")
                return ""

            # Get existing conversation link
            conv = await chat_link_store.get_link(chat_id, thread_id)
            log_debug(f"[selenium] Retrieved conversation link from DB: {conv}")
            if conv:
                if conv.startswith("http"):
                    url = conv
                    log_debug(f"[selenium] Using full URL from DB: {url}")
                else:
                    # If it's just an ID, construct the URL properly
                    url = f"https://chat.openai.com/c/{conv}"
                    log_debug(f"[selenium] Constructed URL from chat ID '{conv}': {url}")
            else:
                url = "https://chat.openai.com"
                log_debug("[selenium] No existing chat found, creating new chat")

            log_debug(f"[selenium] Final URL to navigate to: {url}")

            # Send prompt and get response
            try:
                reply, final_url = await self.ask(json_prompt, url)
                log_debug(f"[selenium] Ask completed successfully, final URL: {final_url}")
            except Exception as e:
                log_error(f"[selenium] Ask failed with error: {e}")
                if conv:
                    log_warning(f"[selenium] Stored chat failed ({e}), trying new chat")
                    reply, final_url = await self.ask(json_prompt, "https://chat.openai.com")
                else:
                    raise

            # Save the conversation link
            if final_url and final_url != url:
                log_debug(f"[selenium] Saving new chat link: original_url='{url}', final_url='{final_url}'")
                await chat_link_store.save_link(chat_id, thread_id, final_url)
                log_debug(f"[selenium] Saved new chat link: {final_url}")
            else:
                log_debug(f"[selenium] No need to save chat link: final_url='{final_url}', original_url='{url}'")

            # Send response via bot
            if bot and reply:
                try:
                    await bot.send_message(
                        chat_id=chat_id,
                        text=reply,
                        reply_to_message_id=getattr(message, "message_id", None),
                    )
                    log_debug(f"[selenium] Response sent to chat {chat_id}")
                except Exception as e:  # pragma: no cover - network issues
                    log_error(f"[selenium] Failed to send message via bot: {e}")

            return reply

        except Exception as e:
            log_error(f"[selenium] Error handling message: {e}")
            # Let's add more debug info to understand what's happening
            if self._driver:
                try:
                    current_url = await self._driver._tab.evaluate("window.location.href")
                    log_debug(f"[selenium] Current URL when error occurred: {current_url}")
                    page_title = await self._driver._tab.evaluate("document.title")
                    log_debug(f"[selenium] Page title when error occurred: {page_title}")
                    # Check if ChatGPT is loaded properly
                    has_textarea = await self._driver._tab.evaluate("!!document.getElementById('prompt-textarea')")
                    log_debug(f"[selenium] Has prompt textarea: {has_textarea}")
                    has_send_button = await self._driver._tab.evaluate("!!document.querySelector('[data-testid=\"send-button\"]')")
                    log_debug(f"[selenium] Has send button: {has_send_button}")
                except Exception as debug_e:
                    log_debug(f"[selenium] Could not get debug info: {debug_e}")
            return ""


async def clean_chat_link(chat_id: int) -> bool:
    """Remove stored link for given Telegram chat."""
    return await chat_link_store.remove(chat_id, None)


PLUGIN_CLASS = SeleniumChatGPTClient
