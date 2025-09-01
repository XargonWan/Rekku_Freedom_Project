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

    _name_resolvers: Dict[
        str,
        Callable[[int | str, Optional[int | str], Any], Awaitable[Dict[str, Optional[str]]]],
    ] = {}

    def __init__(self) -> None:
        self._table_ensured = False

    # ------------------------------------------------------------------
    # Resolver management
    @classmethod
    def set_name_resolver(
        cls,
        interface: str,
        resolver: Callable[[int | str, Optional[int | str], Any], Awaitable[Dict[str, Optional[str]]]],
    ) -> None:
        """Register a callback used to resolve chat and thread names for an interface."""

        cls._name_resolvers[interface] = resolver

    @classmethod
    def _get_resolver(
        cls, interface: str
    ) -> Optional[
        Callable[[int | str, Optional[int | str], Any], Awaitable[Dict[str, Optional[str]]]]
    ]:
        return cls._name_resolvers.get(interface)

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
                    interface VARCHAR(32) NOT NULL DEFAULT 'telegram',
                    chat_id TEXT NOT NULL,
                    message_thread_id TEXT,
                    link VARCHAR(2048),
                    chat_name TEXT,
                    message_thread_name TEXT,
                    PRIMARY KEY (interface, chat_id(255), message_thread_id(255))
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
            try:
                await cursor.execute(
                    "ALTER TABLE chatgpt_links ADD COLUMN IF NOT EXISTS interface VARCHAR(32) NOT NULL DEFAULT 'telegram'"
                )
            except Exception as e:  # pragma: no cover
                log_warning(f"[chatlink] interface column add failed: {e}")
            try:
                await cursor.execute(
                    "ALTER TABLE chatgpt_links DROP PRIMARY KEY, ADD PRIMARY KEY (interface, chat_id(255), message_thread_id(255))"
                )
            except Exception as e:  # pragma: no cover
                log_warning(f"[chatlink] primary key update failed: {e}")
            await conn.commit()
        conn.close()
        self._table_ensured = True

    # ------------------------------------------------------------------
    # CRUD operations
    async def get_link(
        self,
        chat_id: int | str | None = None,
        message_thread_id: Optional[int | str] = None,
        interface: str = "telegram",
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
                        f"[chatlink] Searching for link: interface={interface}, chat_id={chat_id_str}, message_thread_id={normalized}"
                    )
                    await cursor.execute(
                        """
                        SELECT link FROM chatgpt_links
                        WHERE interface = %s AND chat_id = %s AND message_thread_id = %s
                        """,
                        (interface, chat_id_str, normalized),
                    )
                elif chat_name is not None:
                    norm_name = self._normalize_name(message_thread_name)
                    log_debug(
                        f"[chatlink] Searching for link: interface={interface}, chat_name={chat_name}, message_thread_name={norm_name}"
                    )
                    if norm_name is None:
                        await cursor.execute(
                            """
                            SELECT link FROM chatgpt_links
                            WHERE interface = %s AND chat_name = %s AND message_thread_name IS NULL
                            """,
                            (interface, chat_name),
                        )
                    else:
                        await cursor.execute(
                            """
                            SELECT link FROM chatgpt_links
                            WHERE interface = %s AND chat_name = %s AND message_thread_name = %s
                            """,
                            (interface, chat_name, norm_name),
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
        interface: str = "telegram",
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
                    (interface, chat_id, message_thread_id, link, chat_name, message_thread_name)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    link=VALUES(link),
                    chat_name=VALUES(chat_name),
                    message_thread_name=VALUES(message_thread_name)
                """,
                (interface, chat_id_str, normalized, link, name, thread_name),
            )
            await conn.commit()
        conn.close()
        log_debug(
            f"[chatlink] Saved mapping {chat_id_str}/{normalized} -> {link}"
        )

        # Populate names automatically if resolver available
        if (chat_name is None or message_thread_name is None) and self._get_resolver(interface):
            try:
                await self.update_names_from_resolver(
                    chat_id, message_thread_id, interface=interface
                )
            except Exception as e:  # pragma: no cover - best effort
                log_warning(f"[chatlink] name resolution failed: {e}")

    async def remove(
        self,
        chat_id: int | str | None = None,
        message_thread_id: Optional[int | str] = None,
        interface: str = "telegram",
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
                        WHERE interface = %s AND chat_id = %s AND message_thread_id = %s
                        """,
                        (interface, chat_id_str, normalized),
                    )
                elif chat_name is not None:
                    norm_name = self._normalize_name(message_thread_name)
                    if norm_name is None:
                        result = await cursor.execute(
                            """
                            DELETE FROM chatgpt_links
                            WHERE interface = %s AND chat_name = %s AND message_thread_name IS NULL
                            """,
                            (interface, chat_name),
                        )
                    else:
                        result = await cursor.execute(
                            """
                            DELETE FROM chatgpt_links
                            WHERE interface = %s AND chat_name = %s AND message_thread_name = %s
                            """,
                            (interface, chat_name, norm_name),
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
        interface: str = "telegram",
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
        params.extend([interface, chat_id_str, normalized])
        query = (
            f"UPDATE chatgpt_links SET {', '.join(fields)} "
            "WHERE interface = %s AND chat_id = %s AND message_thread_id = %s"
        )
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
        message_thread_id: Optional[int | str],
        *,
        interface: str = "telegram",
        bot: Any | None = None,
    ) -> bool:
        """Use the registered resolver to update chat/thread names."""

        resolver = self._get_resolver(interface)
        if not resolver:
            return False
        try:
            try:
                result = await resolver(chat_id, message_thread_id, bot)
            except TypeError:  # resolver might not accept bot
                result = await resolver(chat_id, message_thread_id)
        except Exception as e:  # pragma: no cover - best effort
            log_warning(f"[chatlink] resolver execution failed: {e}")
            return False
        if not result:
            return False
        return await self.update_names(
            chat_id,
            message_thread_id,
            interface,
            chat_name=result.get("chat_name"),
            message_thread_name=result.get("message_thread_name"),
        )

    async def resolve(
        self,
        *,
        chat_id: int | str | None = None,
        message_thread_id: Optional[int | str] = None,
        chat_name: Optional[str] = None,
        message_thread_name: Optional[str] = None,
        interface: str = "telegram",
    ) -> Optional[Dict[str, Any]]:
        """Resolve a chat link using any combination of identifiers."""

        await self._ensure_table()
        conn = await get_conn()
        try:
            async with conn.cursor(aiomysql.DictCursor) as cursor:
                clauses = ["interface = %s"]
                params: list[Any] = [interface]
                if chat_id is not None:
                    clauses.append("chat_id = %s")
                    params.append(str(chat_id))
                if message_thread_id is not None:
                    clauses.append("message_thread_id = %s")
                    params.append(self._normalize_thread_id(message_thread_id))
                if chat_name is not None:
                    clauses.append("chat_name = %s")
                    params.append(chat_name)
                if message_thread_name is not None:
                    clauses.append("message_thread_name = %s")
                    params.append(message_thread_name)
                if len(clauses) == 1:
                    return None
                query = (
                    "SELECT chat_id, message_thread_id, link, chat_name, message_thread_name"
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
        return rows[0]

    # Backwards compatibility
    async def resolve_chat(
        self, chat_name: str, message_thread_name: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        return await self.resolve(
            chat_name=chat_name, message_thread_name=message_thread_name
        )


__all__ = [
    "ChatLinkStore",
    "ChatLinkError",
    "ChatLinkNotFound",
    "ChatLinkMultipleMatches",
]

