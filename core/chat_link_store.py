"""Store and resolve mappings between external chats and ChatGPT conversations."""

from __future__ import annotations

from typing import Optional, Dict, Any, Callable, Awaitable

import aiomysql

from core.logging_utils import log_debug, log_error, log_warning
from core.db import get_conn


class ChatLinkError(Exception):
    """Base error for chat link operations."""


class ChatLinkNotFound(ChatLinkError):
    """Raised when a chat link cannot be uniquely resolved."""


class ChatLinkMultipleMatches(ChatLinkError):
    """Raised when more than one chat link matches a lookup."""


class ChatLinkStore:
    """Persistence layer for chat -> ChatGPT conversation links.

    Supports optional tracking of chat and thread names to allow lookup by
    human-readable identifiers.  A resolver callback can be registered to
    automatically fetch chat/thread names from interfaces.
    """

    _name_resolver: Optional[
        Callable[[int | str, Optional[int | str], Any], Awaitable[Dict[str, Optional[str]]]]
    ] = None

    def __init__(self) -> None:
        self._table_ensured = False

    # ------------------------------------------------------------------
    # Resolver management
    @classmethod
    def set_name_resolver(
        cls,
        resolver: Callable[[int | str, Optional[int | str], Any], Awaitable[Dict[str, Optional[str]]]],
    ) -> None:
        """Register a callback used to resolve chat and thread names."""

        cls._name_resolver = resolver

    @classmethod
    def _get_resolver(
        cls,
    ) -> Optional[
        Callable[[int | str, Optional[int | str], Any], Awaitable[Dict[str, Optional[str]]]]
    ]:
        return cls._name_resolver

    # ------------------------------------------------------------------
    # Helpers
    def _normalize_thread_id(self, thread_id: Optional[int | str]) -> str:
        """Return ``thread_id`` as a non-null string."""
        return str(thread_id) if thread_id is not None else "0"

    def _normalize_name(self, value: Optional[str]) -> Optional[str]:
        """Return a cleaned name or ``None`` if not provided."""
        if value is None:
            return None
        value = str(value).strip()
        return value if value else None

    async def _update_last_contact(self, chat_id: int | str, thread_id: Optional[int | str]) -> None:
        """Update the ``last_contact`` timestamp for the given chat/thread."""
        normalized = self._normalize_thread_id(thread_id)
        chat_id_str = str(chat_id)
        conn = await get_conn()
        async with conn.cursor() as cursor:
            await cursor.execute(
                "UPDATE chatgpt_links SET last_contact = CURRENT_TIMESTAMP WHERE chat_id = %s AND thread_id = %s",
                (chat_id_str, normalized),
            )
            await conn.commit()
        conn.close()

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
                    thread_id TEXT,
                    chatgpt_link VARCHAR(2048),
                    chat_name TEXT,
                    thread_name TEXT,
                    last_contact TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (chat_id(255), thread_id(255))
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
                    "ALTER TABLE chatgpt_links ADD COLUMN IF NOT EXISTS thread_name TEXT"
                )
            except Exception as e:  # pragma: no cover
                log_warning(f"[chatlink] thread_name column add failed: {e}")
            try:
                await cursor.execute(
                    "ALTER TABLE chatgpt_links ADD COLUMN IF NOT EXISTS last_contact TIMESTAMP"
                )
            except Exception as e:  # pragma: no cover
                log_warning(f"[chatlink] last_contact column add failed: {e}")
            try:
                await cursor.execute(
                    "ALTER TABLE chatgpt_links CHANGE COLUMN link chatgpt_link VARCHAR(2048)"
                )
            except Exception as e:  # pragma: no cover
                log_warning(f"[chatlink] chatgpt_link column rename failed: {e}")
                try:
                    await cursor.execute(
                        "ALTER TABLE chatgpt_links ADD COLUMN IF NOT EXISTS chatgpt_link VARCHAR(2048)"
                    )
                except Exception as e2:  # pragma: no cover
                    log_warning(f"[chatlink] chatgpt_link column add failed: {e2}")
            try:
                await cursor.execute(
                    "ALTER TABLE chatgpt_links CHANGE COLUMN message_thread_id thread_id TEXT"
                )
            except Exception as e:  # pragma: no cover
                log_warning(f"[chatlink] thread_id column rename failed: {e}")
            try:
                await cursor.execute(
                    "ALTER TABLE chatgpt_links CHANGE COLUMN message_thread_name thread_name TEXT"
                )
            except Exception as e:  # pragma: no cover
                log_warning(f"[chatlink] thread_name column rename failed: {e}")
            await conn.commit()
        conn.close()
        self._table_ensured = True

    # ------------------------------------------------------------------
    # CRUD operations
    async def get_link(
        self,
        chat_id: int | str | None = None,
        thread_id: Optional[int | str] = None,
        *,
        chat_name: Optional[str] = None,
        thread_name: Optional[str] = None,
    ) -> Optional[str]:
        """Return the ChatGPT link for the given identifiers."""

        await self._ensure_table()
        conn = await get_conn()
        try:
            async with conn.cursor(aiomysql.DictCursor) as cursor:
                if chat_id is not None:
                    normalized = self._normalize_thread_id(thread_id)
                    chat_id_str = str(chat_id)
                    log_debug(
                        f"[chatlink] Searching for link: chat_id={chat_id_str}, thread_id={normalized}"
                    )
                    await cursor.execute(
                        """
                        SELECT chat_id, thread_id, chatgpt_link, chat_name, thread_name
                        FROM chatgpt_links
                        WHERE chat_id = %s AND thread_id = %s
                        """,
                        (chat_id_str, normalized),
                    )
                elif chat_name is not None:
                    norm_name = self._normalize_name(thread_name)
                    log_debug(
                        f"[chatlink] Searching for link: chat_name={chat_name}, thread_name={norm_name}"
                    )
                    if norm_name is None:
                        await cursor.execute(
                            """
                            SELECT chat_id, thread_id, chatgpt_link, chat_name, thread_name
                            FROM chatgpt_links
                            WHERE chat_name = %s AND thread_name IS NULL
                            """,
                            (chat_name,),
                        )
                    else:
                        await cursor.execute(
                            """
                            SELECT chat_id, thread_id, chatgpt_link, chat_name, thread_name
                            FROM chatgpt_links
                            WHERE chat_name = %s AND thread_name = %s
                            """,
                            (chat_name, norm_name),
                        )
                else:
                    return None
                row = await cursor.fetchone()
        finally:
            conn.close()
        if row:
            chat_id_val = row.get("chat_id")
            thread_id_val = row.get("thread_id")
            await self._update_last_contact(chat_id_val, thread_id_val)
            if (row.get("chat_name") is None or row.get("thread_name") is None) and self._get_resolver():
                try:
                    await self.update_names_from_resolver(chat_id_val, thread_id_val)
                except Exception as e:  # pragma: no cover
                    log_warning(f"[chatlink] resolver update failed during get_link: {e}")
            return row.get("chatgpt_link")
        return None

    async def save_link(
        self,
        chat_id: int | str,
        thread_id: Optional[int | str],
        chatgpt_link: str,
        *,
        chat_name: Optional[str] = None,
        thread_name: Optional[str] = None,
    ) -> None:
        """Persist a mapping between a chat (and optional thread) and a ChatGPT link."""

        await self._ensure_table()
        normalized = self._normalize_thread_id(thread_id)
        chat_id_str = str(chat_id)
        name = self._normalize_name(chat_name)
        thread_name_norm = self._normalize_name(thread_name)
        conn = await get_conn()
        async with conn.cursor() as cursor:
            await cursor.execute(
                """
                INSERT INTO chatgpt_links
                    (chat_id, thread_id, chatgpt_link, chat_name, thread_name, last_contact)
                VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                ON DUPLICATE KEY UPDATE
                    chatgpt_link=VALUES(chatgpt_link),
                    chat_name=VALUES(chat_name),
                    thread_name=VALUES(thread_name),
                    last_contact=CURRENT_TIMESTAMP
                """,
                (chat_id_str, normalized, chatgpt_link, name, thread_name_norm),
            )
            await conn.commit()
        conn.close()
        log_debug(
            f"[chatlink] Saved mapping {chat_id_str}/{normalized} -> {chatgpt_link}"
        )

        # Populate names automatically if resolver available
        if (chat_name is None or thread_name is None) and self._get_resolver():
            try:
                await self.update_names_from_resolver(chat_id, thread_id)
            except Exception as e:  # pragma: no cover - best effort
                log_warning(f"[chatlink] name resolution failed: {e}")

    async def remove(
        self,
        chat_id: int | str | None = None,
        thread_id: Optional[int | str] = None,
        *,
        chat_name: Optional[str] = None,
        thread_name: Optional[str] = None,
    ) -> bool:
        """Remove a mapping. Returns True if a row was deleted."""

        await self._ensure_table()
        conn = await get_conn()
        try:
            async with conn.cursor() as cursor:
                if chat_id is not None:
                    normalized = self._normalize_thread_id(thread_id)
                    chat_id_str = str(chat_id)
                    result = await cursor.execute(
                        """
                        DELETE FROM chatgpt_links
                        WHERE chat_id = %s AND thread_id = %s
                        """,
                        (chat_id_str, normalized),
                    )
                elif chat_name is not None:
                    norm_name = self._normalize_name(thread_name)
                    if norm_name is None:
                        result = await cursor.execute(
                            """
                            DELETE FROM chatgpt_links
                            WHERE chat_name = %s AND thread_name IS NULL
                            """,
                            (chat_name,),
                        )
                    else:
                        result = await cursor.execute(
                            """
                            DELETE FROM chatgpt_links
                            WHERE chat_name = %s AND thread_name = %s
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
        thread_id: Optional[int | str],
        *,
        chat_name: Optional[str] = None,
        thread_name: Optional[str] = None,
    ) -> bool:
        """Update stored chat or thread names. Returns True if a row was updated."""

        if chat_name is None and thread_name is None:
            return False
        await self._ensure_table()
        normalized = self._normalize_thread_id(thread_id)
        chat_id_str = str(chat_id)
        fields = []
        params: list[Any] = []
        if chat_name is not None:
            fields.append("chat_name = %s")
            params.append(self._normalize_name(chat_name))
        if thread_name is not None:
            fields.append("thread_name = %s")
            params.append(self._normalize_name(thread_name))
        params.extend([chat_id_str, normalized])
        query = f"UPDATE chatgpt_links SET {', '.join(fields)} WHERE chat_id = %s AND thread_id = %s"
        conn = await get_conn()
        try:
            async with conn.cursor() as cursor:
                result = await cursor.execute(query, params)
                await conn.commit()
        finally:
            conn.close()
        return result > 0

    async def update_names_from_resolver(
        self,
        chat_id: int | str,
        thread_id: Optional[int | str],
        bot: Any | None = None,
    ) -> bool:
        """Use the registered resolver to update chat/thread names."""

        resolver = self._get_resolver()
        if not resolver:
            return False
        try:
            try:
                result = await resolver(chat_id, thread_id, bot)
            except TypeError:  # resolver might not accept bot
                result = await resolver(chat_id, thread_id)
        except Exception as e:  # pragma: no cover - best effort
            log_warning(f"[chatlink] resolver execution failed: {e}")
            return False
        if not result:
            return False
        return await self.update_names(
            chat_id,
            thread_id,
            chat_name=result.get("chat_name"),
            thread_name=result.get("thread_name"),
        )

    async def resolve(
        self,
        *,
        chat_id: int | str | None = None,
        thread_id: Optional[int | str] = None,
        chat_name: Optional[str] = None,
        thread_name: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Resolve a chat link using any combination of identifiers."""

        await self._ensure_table()
        conn = await get_conn()
        try:
            async with conn.cursor(aiomysql.DictCursor) as cursor:
                clauses = []
                params: list[Any] = []
                if chat_id is not None:
                    clauses.append("chat_id = %s")
                    params.append(str(chat_id))
                if thread_id is not None:
                    clauses.append("thread_id = %s")
                    params.append(self._normalize_thread_id(thread_id))
                if chat_name is not None:
                    clauses.append("chat_name = %s")
                    params.append(chat_name)
                if thread_name is not None:
                    clauses.append("thread_name = %s")
                    params.append(thread_name)
                if not clauses:
                    return None
                query = (
                    "SELECT chat_id, thread_id, chatgpt_link, chat_name, thread_name"
                    f" FROM chatgpt_links WHERE {' AND '.join(clauses)}"
                )
                await cursor.execute(query, params)
                rows = await cursor.fetchall()
        finally:
            conn.close()

        if not rows:
            return None
        if len(rows) > 1:
            raise ChatLinkMultipleMatches()
        row = rows[0]
        await self._update_last_contact(row.get("chat_id"), row.get("thread_id"))
        if (row.get("chat_name") is None or row.get("thread_name") is None) and self._get_resolver():
            try:
                await self.update_names_from_resolver(row.get("chat_id"), row.get("thread_id"))
            except Exception as e:  # pragma: no cover
                log_warning(f"[chatlink] resolver update failed during resolve: {e}")
        return row

    # Backwards compatibility
    async def resolve_chat(
        self, chat_name: str, thread_name: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        return await self.resolve(
            chat_name=chat_name, thread_name=thread_name
        )


__all__ = [
    "ChatLinkStore",
    "ChatLinkError",
    "ChatLinkNotFound",
    "ChatLinkMultipleMatches",
]

