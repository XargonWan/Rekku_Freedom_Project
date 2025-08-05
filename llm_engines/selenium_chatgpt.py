import asyncio
import os
import re
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


def _extract_chat_id(url: str) -> Optional[str]:
    """Extract chat identifier from ChatGPT URL."""
    if not url or not isinstance(url, str):
        return None
    patterns = [
        r"/chat/([^/?#]+)",
        r"/c/([^/?#]+)",
        r"chat\\.openai\\.com/chat/([^/?#]+)",
        r"chat\\.openai\\.com/c/([^/?#]+)",
    ]
    for pattern in patterns:
        m = re.search(pattern, url)
        if m:
            return m.group(1)
    return None


class NodriverElementWrapper:
    """Minimal wrapper to provide a selenium-like API."""

    def __init__(self, element):
        self._el = element

    async def clear(self) -> None:
        try:
            await self._el.evaluate(
                "el => { el.value=''; el.dispatchEvent(new Event('input',{bubbles:true})); }"
            )
        except Exception as e:  # pragma: no cover - best effort
            log_error(f"[selenium] failed to clear textarea: {e}")

    async def send_keys(self, text: str) -> None:
        try:
            if text == Keys.ENTER:
                await self._el.evaluate(
                    "el => { el.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',code:'Enter',bubbles:true}));"
                    "el.dispatchEvent(new KeyboardEvent('keyup',{key:'Enter',code:'Enter',bubbles:true})); }"
                )
            else:
                escaped = (
                    text.replace("\\", "\\\\")
                    .replace("'", "\\'")
                    .replace("\n", "\\n")
                )
                await self._el.evaluate(
                    "el => { el.value='" + escaped + "'; el.dispatchEvent(new Event('input',{bubbles:true})); }"
                )
        except Exception as e:  # pragma: no cover - best effort
            log_error(f"[selenium] failed to send keys: {e}")
 
class NodriverSeleniumWrapper:
    """Expose a very small selenium-like surface over nodriver."""

    def __init__(self, tab):
        self._tab = tab

    async def get(self, url: str) -> None:
        await self._tab.get(url)

    async def find_element(self, by: str, selector: str):
        css = self._to_css(by, selector)
        if not css:
            return None
        el = await self._tab.select(css, timeout=20)
        return NodriverElementWrapper(el) if el else None

    async def find_elements(self, by: str, selector: str):
        css = self._to_css(by, selector)
        if not css:
            return []
        els = await self._tab.select_all(css, timeout=1)
        return [NodriverElementWrapper(e) for e in els]

    def _to_css(self, by: str, selector: str) -> str | None:
        if by == By.ID:
            return f"#{selector}"
        if by == By.CSS_SELECTOR:
            return selector
        return None

    @property
    def current_url(self) -> str:
        return self._tab.url


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
        browser = await uc.start(
            headless=False,
            user_data_dir=profile_dir,
            browser_args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        tab = await browser.get("about:blank")
        self._browser = browser
        self._driver = NodriverSeleniumWrapper(tab)
        return self._driver

    async def _wait_for_response(self, driver, prev_count: int) -> str:
        start = asyncio.get_event_loop().time()
        while asyncio.get_event_loop().time() - start < 20:
            elems = await driver.find_elements(
                By.CSS_SELECTOR, "div[data-message-author-role='assistant']"
            )
            if len(elems) > prev_count:
                last = elems[-1]
                text = await last.get_attribute("innerText")
                if not text:
                    text = last.text
                return text.strip()
            await asyncio.sleep(1)
        raise TimeoutError("assistant reply not found")

    async def ask(self, prompt: str, chat_url: str) -> tuple[str, str]:
        driver = await self._ensure_driver()
        await driver.get(chat_url)
        textarea = await driver.find_element(By.ID, "prompt-textarea")
        if textarea is None:
            raise RuntimeError("prompt textarea not found")
        await textarea.clear()
        await textarea.send_keys(prompt)
        await textarea.send_keys(Keys.ENTER)
        prev = len(
            await driver.find_elements(
                By.CSS_SELECTOR, "div[data-message-author-role='assistant']"
            )
        )
        reply = await self._wait_for_response(driver, prev)
        log_debug("[selenium] received reply of %d chars" % len(reply))
        return reply, driver.current_url

    async def handle_incoming_message(self, bot, message, prompt: dict) -> str:
        """Process an incoming message using the ChatGPT web UI."""
        chat_id = getattr(message, "chat_id", None)
        thread_id = getattr(message, "message_thread_id", None)

        if isinstance(prompt, dict):
            input_payload = prompt.get("input", {}).get("payload", {})
            user_prompt = input_payload.get("text", "")
            if chat_id is None:
                chat_id = (
                    input_payload.get("source", {}).get("chat_id")
                )
            if thread_id is None:
                thread_id = (
                    input_payload.get("source", {}).get("message_thread_id")
                )
        else:
            user_prompt = str(prompt)

        if not user_prompt or chat_id is None:
            log_warning("[selenium] Missing prompt or chat_id")
            return ""

        conv = await chat_link_store.get_link(chat_id, thread_id)
        url = f"https://chat.openai.com/c/{conv}" if conv else "https://chat.openai.com"
        try:
            reply, final_url = await self.ask(user_prompt, url)
        except Exception as e:  # pragma: no cover - best effort
            if conv:
                log_warning(
                    f"[selenium] stored chat {conv} failed ({e}), using new chat"
                )
                reply, final_url = await self.ask(user_prompt, "https://chat.openai.com")
                conv = None
            else:
                log_error(f"[selenium] error handling message: {e}")
                return ""

        if conv is None:
            new_id = _extract_chat_id(final_url)
            if new_id:
                await chat_link_store.save_link(chat_id, thread_id, new_id)

        if bot and reply:
            try:
                await bot.send_message(
                    chat_id=chat_id,
                    text=reply,
                    reply_to_message_id=getattr(message, "message_id", None),
                )
            except Exception as e:  # pragma: no cover - network issues
                log_error(f"[selenium] Failed to send message via bot: {e}")

        return reply


async def clean_chat_link(chat_id: int) -> bool:
    """Remove stored link for given Telegram chat."""
    return await chat_link_store.remove(chat_id, None)


PLUGIN_CLASS = SeleniumChatGPTClient
