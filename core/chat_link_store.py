"""Store and resolve mappings between external chats and ChatGPT conversations."""

from __future__ import annotations

from typing import Optional, Dict, Any

import aiomysql

from core.logging_utils import log_debug, log_error, log_warning
from core.db import get_conn


class ChatLinkStore:
    """Persistence layer for chat -> ChatGPT conversation links.

    Supports optional tracking of chat and thread names to allow lookup by
    human-readable identifiers.
    """

    def __init__(self) -> None:
        self._table_ensured = False

    # ------------------------------------------------------------------
    # Helpers
    def _normalize_thread_id(self, message_thread_id: Optional[int | str]) -> str:
        """Return ``message_thread_id`` as a non-null string."""
        return str(message_thread_id) if message_thread_id is not None else "0"

    def _normalize_name(self, value: Optional[str]) -> Optional[str]:
        """Return a cleaned name or ``None`` if not provided."""
        if value is None:
            return None
        value = str(value).strip()
        return value if value else None

    async def _ensure_table(self) -> None:
        """Create the ``chatgpt_links`` table and new columns if necessary."""
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
                    chat_name TEXT,
                    message_thread_name TEXT,
                    PRIMARY KEY (chat_id(255), message_thread_id(255))
                )
                """
            )
            # Ensure new columns exist for older installations
            try:
                await cursor.execute(
                    "ALTER TABLE chatgpt_links ADD COLUMN IF NOT EXISTS chat_name TEXT"
                )
            except Exception as e:  # pragma: no cover - MariaDB <10.3 lacks IF NOT EXISTS
                log_warning(f"[chatlink] chat_name column add failed: {e}")
            try:
                await cursor.execute(
                    "ALTER TABLE chatgpt_links ADD COLUMN IF NOT EXISTS message_thread_name TEXT"
                )
            except Exception as e:  # pragma: no cover
                log_warning(f"[chatlink] message_thread_name column add failed: {e}")
            await conn.commit()
        conn.close()
        self._table_ensured = True

    # ------------------------------------------------------------------
    # CRUD operations
    async def get_link(
        self,
        chat_id: int | str | None = None,
        message_thread_id: Optional[int | str] = None,
        *,
        chat_name: Optional[str] = None,
        message_thread_name: Optional[str] = None,
    ) -> Optional[str]:
        """Return the ChatGPT link for the given identifiers."""

        await self._ensure_table()
        conn = await get_conn()
        try:
            async with conn.cursor(aiomysql.DictCursor) as cursor:
                if chat_id is not None:
                    normalized = self._normalize_thread_id(message_thread_id)
                    chat_id_str = str(chat_id)
                    log_debug(
                        f"[chatlink] Searching for link: chat_id={chat_id_str}, message_thread_id={normalized}"
                    )
                    await cursor.execute(
                        """
                        SELECT link FROM chatgpt_links
                        WHERE chat_id = %s AND message_thread_id = %s
                        """,
                        (chat_id_str, normalized),
                    )
                elif chat_name is not None:
                    norm_name = self._normalize_name(message_thread_name)
                    log_debug(
                        f"[chatlink] Searching for link: chat_name={chat_name}, message_thread_name={norm_name}"
                    )
                    if norm_name is None:
                        await cursor.execute(
                            """
                            SELECT link FROM chatgpt_links
                            WHERE chat_name = %s AND message_thread_name IS NULL
                            """,
                            (chat_name,),
                        )
                    else:
                        await cursor.execute(
                            """
                            SELECT link FROM chatgpt_links
                            WHERE chat_name = %s AND message_thread_name = %s
                            """,
                            (chat_name, norm_name),
                        )
                else:
                    return None
                row = await cursor.fetchone()
        finally:
            conn.close()
        if row:
            return row.get("link")
        return None

    async def save_link(
        self,
        chat_id: int | str,
        message_thread_id: Optional[int | str],
        link: str,
        *,
        chat_name: Optional[str] = None,
        message_thread_name: Optional[str] = None,
    ) -> None:
        """Persist a mapping between a chat (and optional thread) and a link."""

        await self._ensure_table()
        normalized = self._normalize_thread_id(message_thread_id)
        chat_id_str = str(chat_id)
        name = self._normalize_name(chat_name)
        thread_name = self._normalize_name(message_thread_name)
        conn = await get_conn()
        async with conn.cursor() as cursor:
            await cursor.execute(
                """
                INSERT INTO chatgpt_links
                    (chat_id, message_thread_id, link, chat_name, message_thread_name)
                VALUES (%s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    link=VALUES(link),
                    chat_name=VALUES(chat_name),
                    message_thread_name=VALUES(message_thread_name)
                """,
                (chat_id_str, normalized, link, name, thread_name),
            )
            await conn.commit()
        conn.close()
        log_debug(
            f"[chatlink] Saved mapping {chat_id_str}/{normalized} -> {link}"
        )

    async def remove(
        self,
        chat_id: int | str | None = None,
        message_thread_id: Optional[int | str] = None,
        *,
        chat_name: Optional[str] = None,
        message_thread_name: Optional[str] = None,
    ) -> bool:
        """Remove a mapping. Returns True if a row was deleted."""

        await self._ensure_table()
        conn = await get_conn()
        try:
            async with conn.cursor() as cursor:
                if chat_id is not None:
                    normalized = self._normalize_thread_id(message_thread_id)
                    chat_id_str = str(chat_id)
                    result = await cursor.execute(
                        """
                        DELETE FROM chatgpt_links
                        WHERE chat_id = %s AND message_thread_id = %s
                        """,
                        (chat_id_str, normalized),
                    )
                elif chat_name is not None:
                    norm_name = self._normalize_name(message_thread_name)
                    if norm_name is None:
                        result = await cursor.execute(
                            """
                            DELETE FROM chatgpt_links
                            WHERE chat_name = %s AND message_thread_name IS NULL
                            """,
                            (chat_name,),
                        )
                    else:
                        result = await cursor.execute(
                            """
                            DELETE FROM chatgpt_links
                            WHERE chat_name = %s AND message_thread_name = %s
                            """,
                            (chat_name, norm_name),
                        )
                else:
                    return False
                await conn.commit()
        finally:
            conn.close()
        return result > 0

    async def update_names(
        self,
        chat_id: int | str,
        message_thread_id: Optional[int | str],
        *,
        chat_name: Optional[str] = None,
        message_thread_name: Optional[str] = None,
    ) -> bool:
        """Update stored chat or thread names. Returns True if a row was updated."""

        if chat_name is None and message_thread_name is None:
            return False
        await self._ensure_table()
        normalized = self._normalize_thread_id(message_thread_id)
        chat_id_str = str(chat_id)
        fields = []
        params: list[Any] = []
        if chat_name is not None:
            fields.append("chat_name = %s")
            params.append(self._normalize_name(chat_name))
        if message_thread_name is not None:
            fields.append("message_thread_name = %s")
            params.append(self._normalize_name(message_thread_name))
        params.extend([chat_id_str, normalized])
        query = f"UPDATE chatgpt_links SET {', '.join(fields)} WHERE chat_id = %s AND message_thread_id = %s"
        conn = await get_conn()
        try:
            async with conn.cursor() as cursor:
                result = await cursor.execute(query, params)
                await conn.commit()
        finally:
            conn.close()
        return result > 0

    async def resolve_chat(
        self, chat_name: str, message_thread_name: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Resolve a chat by name returning identifiers and link."""

        await self._ensure_table()
        conn = await get_conn()
        try:
            async with conn.cursor(aiomysql.DictCursor) as cursor:
                norm_name = self._normalize_name(message_thread_name)
                if norm_name is None:
                    await cursor.execute(
                        """
                        SELECT chat_id, message_thread_id, link
                        FROM chatgpt_links
                        WHERE chat_name = %s AND message_thread_name IS NULL
                        """,
                        (chat_name,),
                    )
                else:
                    await cursor.execute(
                        """
                        SELECT chat_id, message_thread_id, link
                        FROM chatgpt_links
                        WHERE chat_name = %s AND message_thread_name = %s
                        """,
                        (chat_name, norm_name),
                    )
                row = await cursor.fetchone()
        finally:
            conn.close()
        return row


__all__ = ["ChatLinkStore"]

