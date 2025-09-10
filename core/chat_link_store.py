"""Store and resolve mappings between external chats and ChatGPT conversations."""

from __future__ import annotations

from typing import Optional, Dict, Any, Callable, Awaitable

import aiomysql
import json

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
        cls, interface: Optional[str] = None
    ) -> Optional[
        Callable[[int | str, Optional[int | str], Any], Awaitable[Dict[str, Optional[str]]]]
    ]:
        # If not specified, raise error - no automatic fallback
        if interface is None:
            raise ValueError("Interface must be specified - no automatic fallback available")
        return cls._name_resolvers.get(interface)

    # ------------------------------------------------------------------
    # Helpers
    def _normalize_thread_id(self, message_thread_id: Optional[int | str]) -> str:
        """Return ``message_thread_id`` as a non-null string."""
        return str(message_thread_id) if message_thread_id is not None else "0"

    def _normalize_interface(self, interface: str) -> str:
        """Normalize interface names to standard format."""
        # Correct common interface name issues
        corrections = {
            'discord_bot': 'discord',
            'telegram_bot': 'telegram',
            # Add other corrections as needed
        }
        return corrections.get(interface, interface)

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
                    interface VARCHAR(32) NOT NULL,
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
                    "ALTER TABLE chatgpt_links ADD COLUMN IF NOT EXISTS interface VARCHAR(32) NOT NULL"
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

    async def _ensure_new_table(self) -> None:
        """Create the new ``chatlink`` table with improved structure."""
        if hasattr(self, '_new_table_ensured') and self._new_table_ensured:
            return
        conn = await get_conn()
        async with conn.cursor() as cursor:
            # Create new table with improved structure
            await cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS chatlink (
                    int_id INT AUTO_INCREMENT PRIMARY KEY,
                    interface VARCHAR(32) NOT NULL,
                    chat_id TEXT NOT NULL,
                    thread_id JSON NOT NULL DEFAULT ('[]'),
                    chatgpt_link VARCHAR(2048),
                    last_contact TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    chat_name TEXT,
                    message_thread_name TEXT,
                    UNIQUE KEY unique_chat (interface, chat_id(255))
                )
                """
            )
            await conn.commit()
        conn.close()
        self._new_table_ensured = True

    async def get_or_create_internal_id(
        self,
        chat_id: int | str,
        message_thread_id: Optional[int | str],
        interface: Optional[str] = None,
        *,
        chat_name: Optional[str] = None,
        message_thread_name: Optional[str] = None,
    ) -> int:
        """Get or create an internal ID for a chat, managing thread_id as JSON array."""
        if interface is None:
            raise ValueError("Interface must be specified")

        interface = self._normalize_interface(interface)
        await self._ensure_new_table()

        normalized_thread = self._normalize_thread_id(message_thread_id)
        chat_id_str = str(chat_id)
        name = self._normalize_name(chat_name)
        thread_name = self._normalize_name(message_thread_name)

        conn = await get_conn()
        try:
            async with conn.cursor(aiomysql.DictCursor) as cursor:
                # Try to find existing entry for this chat (ignoring specific thread)
                await cursor.execute(
                    """
                    SELECT int_id, thread_id FROM chatlink
                    WHERE interface = %s AND chat_id = %s
                    """,
                    (interface, chat_id_str),
                )
                row = await cursor.fetchone()
                if row:
                    # Entry exists, check if thread is already in the array
                    existing_threads = json.loads(row['thread_id']) if row['thread_id'] else []
                    if normalized_thread not in existing_threads:
                        # Add new thread to the array
                        existing_threads.append(normalized_thread)
                        updated_threads = json.dumps(existing_threads)
                        await cursor.execute(
                            """
                            UPDATE chatlink
                            SET thread_id = %s, last_contact = CURRENT_TIMESTAMP
                            WHERE int_id = %s
                            """,
                            (updated_threads, row['int_id']),
                        )
                        await conn.commit()
                        log_debug(f"[chatlink] Added thread {normalized_thread} to existing chat {chat_id_str}")
                    return row['int_id']

                # Create new entry for this chat
                thread_json = json.dumps([normalized_thread])
                await cursor.execute(
                    """
                    INSERT INTO chatlink
                        (interface, chat_id, thread_id, chat_name, message_thread_name)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (interface, chat_id_str, thread_json, name, thread_name),
                )
                await conn.commit()
                new_id = cursor.lastrowid
                log_debug(f"[chatlink] Created new chat entry {chat_id_str} with thread {normalized_thread}")
                return new_id
        finally:
            conn.close()

    async def update_chatgpt_link(
        self,
        internal_id: int,
        chatgpt_link: str,
    ) -> None:
        """Update the ChatGPT link for an existing internal ID."""
        await self._ensure_new_table()
        conn = await get_conn()
        try:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    """
                    UPDATE chatlink
                    SET chatgpt_link = %s, last_contact = CURRENT_TIMESTAMP
                    WHERE int_id = %s
                    """,
                    (chatgpt_link, internal_id),
                )
                await conn.commit()
        finally:
            conn.close()
        log_debug(f"[chatlink] Updated ChatGPT link for internal_id {internal_id} -> {chatgpt_link}")

    async def update_thread_name(
        self,
        chat_id: int | str,
        message_thread_id: Optional[int | str],
        thread_name: str,
        interface: Optional[str] = None,
    ) -> bool:
        """Update the name of a specific thread in the chat."""
        if interface is None:
            raise ValueError("Interface must be specified")

        interface = self._normalize_interface(interface)
        await self._ensure_new_table()

        normalized_thread = self._normalize_thread_id(message_thread_id)
        chat_id_str = str(chat_id)
        normalized_name = self._normalize_name(thread_name)

        conn = await get_conn()
        try:
            async with conn.cursor(aiomysql.DictCursor) as cursor:
                # Find the chat entry
                await cursor.execute(
                    """
                    SELECT int_id, thread_id FROM chatlink
                    WHERE interface = %s AND chat_id = %s
                    """,
                    (interface, chat_id_str),
                )
                row = await cursor.fetchone()
                if row and row['thread_id']:
                    existing_threads = json.loads(row['thread_id'])
                    if normalized_thread in existing_threads:
                        # For now, just update the general message_thread_name field
                        # In future, could maintain a mapping of thread_id -> name
                        await cursor.execute(
                            """
                            UPDATE chatlink
                            SET message_thread_name = %s, last_contact = CURRENT_TIMESTAMP
                            WHERE int_id = %s
                            """,
                            (normalized_name, row['int_id']),
                        )
                        await conn.commit()
                        log_debug(f"[chatlink] Updated thread name for {chat_id_str}/{normalized_thread} -> {normalized_name}")
                        return True
        finally:
            conn.close()
        return False

    # ------------------------------------------------------------------
    # CRUD operations
    async def get_link(
        self,
        chat_id: int | str | None = None,
        message_thread_id: Optional[int | str] = None,
        interface: Optional[str] = None,
        *,
        chat_name: Optional[str] = None,
        message_thread_name: Optional[str] = None,
    ) -> Optional[str]:
        """Return the ChatGPT link for the given identifiers."""

        # Require interface to be specified
        if interface is None:
            raise ValueError("Interface must be specified")

        interface = self._normalize_interface(interface)

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
        interface: Optional[str] = None,
        *,
        chat_name: Optional[str] = None,
        message_thread_name: Optional[str] = None,
    ) -> None:
        """Persist a mapping between a chat (and optional thread) and a link."""

        # Require interface to be specified
        if interface is None:
            raise ValueError("Interface must be specified")

        interface = self._normalize_interface(interface)

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
        interface: Optional[str] = None,
        *,
        chat_name: Optional[str] = None,
        message_thread_name: Optional[str] = None,
    ) -> bool:
        """Remove a mapping. Returns True if a row was deleted."""

        # Require interface to be specified
        if interface is None:
            raise ValueError("Interface must be specified")

        interface = self._normalize_interface(interface)

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
        interface: Optional[str] = None,
        *,
        chat_name: Optional[str] = None,
        message_thread_name: Optional[str] = None,
    ) -> bool:
        """Update stored chat or thread names. Returns True if a row was updated."""

        if chat_name is None and message_thread_name is None:
            return False

        # Require interface to be specified
        if interface is None:
            raise ValueError("Interface must be specified")
        interface = self._normalize_interface(interface)
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
        interface: Optional[str] = None,
        bot: Any | None = None,
    ) -> bool:
        """Use the registered resolver to update chat/thread names."""

        if interface is None:
            raise ValueError("Interface must be specified for name resolution")
        interface = self._normalize_interface(interface)
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
        interface: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Resolve a chat link using any combination of identifiers."""

        await self._ensure_table()
        conn = await get_conn()
        try:
            async with conn.cursor(aiomysql.DictCursor) as cursor:
                clauses = []
                params: list[Any] = []
                if interface is not None:
                    interface = self._normalize_interface(interface)
                    clauses.append("interface = %s")
                    params.append(interface)
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
                if not clauses:
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

