"""Chat Link Plugin - Store and resolve mappings between external chats and ChatGPT conversations."""

from __future__ import annotations

from typing import Optional, Dict, Any, Callable, Awaitable, List
import aiomysql
import json

from core.db import get_conn
from core.logging_utils import log_debug, log_error, log_warning, log_info
from core.core_initializer import core_initializer, register_plugin


class ChatLinkError(Exception):
    """Base error for chat link operations."""


class ChatLinkNotFound(ChatLinkError):
    """Raised when a chat link cannot be uniquely resolved."""


class ChatLinkMultipleMatches(ChatLinkError):
    """Raised when more than one chat link matches a lookup."""


class ChatLinkStore:
    """Persistence layer for chat -> ChatGPT conversation links.

    Supports optional tracking of chat and thread names to allow lookup by
    human-readable identifiers. A resolver callback can be registered to
    automatically fetch chat/thread names from interfaces.
    """

    _name_resolvers: Dict[
        str,
        Callable[[int | str, Optional[int | str], Any], Awaitable[Dict[str, Optional[str]]]],
    ] = {}

    def __init__(self) -> None:
        self._table_ensured = False
        self._new_table_ensured = False

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
    def get_name_resolver(cls, interface: str):
        """Get the name resolver for an interface."""
        return cls._name_resolvers.get(interface)

    # ------------------------------------------------------------------
    # Table management
    async def _ensure_table(self) -> None:
        """Create the chatgpt_links table if it doesn't exist."""
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
            except Exception:
                pass
            try:
                await cursor.execute(
                    "ALTER TABLE chatgpt_links ADD COLUMN IF NOT EXISTS message_thread_name TEXT"
                )
            except Exception:
                pass
            await conn.commit()
        conn.close()
        self._table_ensured = True

    async def _ensure_new_table(self) -> None:
        """Create the new chatlink table with improved structure."""
        if self._new_table_ensured:
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
        """Get or create an internal ID for a chat/thread combination."""
        await self._ensure_new_table()
        
        thread_ids = []
        if message_thread_id is not None:
            thread_ids = [str(message_thread_id)]
        
        conn = await get_conn()
        try:
            async with conn.cursor(aiomysql.DictCursor) as cursor:
                # Try to find existing record
                await cursor.execute(
                    """
                    SELECT int_id FROM chatlink
                    WHERE interface = %s AND chat_id = %s
                    """,
                    (interface, str(chat_id))
                )
                row = await cursor.fetchone()
                
                if row:
                    # Update last_contact and names if provided
                    if chat_name or message_thread_name:
                        await cursor.execute(
                            """
                            UPDATE chatlink 
                            SET chat_name = COALESCE(%s, chat_name),
                                message_thread_name = COALESCE(%s, message_thread_name),
                                last_contact = CURRENT_TIMESTAMP
                            WHERE int_id = %s
                            """,
                            (chat_name, message_thread_name, row['int_id'])
                        )
                        await conn.commit()
                    return row['int_id']
                else:
                    # Create new record
                    await cursor.execute(
                        """
                        INSERT INTO chatlink 
                        (interface, chat_id, thread_id, chat_name, message_thread_name)
                        VALUES (%s, %s, %s, %s, %s)
                        """,
                        (interface, str(chat_id), json.dumps(thread_ids), chat_name, message_thread_name)
                    )
                    await conn.commit()
                    return cursor.lastrowid
        finally:
            conn.close()

    async def store_link(
        self,
        chat_id: int | str,
        message_thread_id: Optional[int | str],
        link: str,
        interface: Optional[str] = None,
        *,
        chat_name: Optional[str] = None,
        message_thread_name: Optional[str] = None,
    ) -> None:
        """Store or update a ChatGPT conversation link."""
        await self._ensure_table()
        
        conn = await get_conn()
        async with conn.cursor() as cursor:
            await cursor.execute(
                """
                REPLACE INTO chatgpt_links 
                (interface, chat_id, message_thread_id, link, chat_name, message_thread_name)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (interface, str(chat_id), str(message_thread_id) if message_thread_id else None, 
                 link, chat_name, message_thread_name)
            )
            await conn.commit()
        conn.close()

    async def get_link(
        self,
        chat_id: int | str,
        message_thread_id: Optional[int | str] = None,
        interface: Optional[str] = None,
    ) -> Optional[str]:
        """Get the ChatGPT link for a chat/thread combination."""
        await self._ensure_table()
        
        conn = await get_conn()
        try:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    """
                    SELECT link FROM chatgpt_links
                    WHERE interface = %s AND chat_id = %s AND message_thread_id = %s
                    """,
                    (interface, str(chat_id), str(message_thread_id) if message_thread_id else None)
                )
                row = await cursor.fetchone()
                return row[0] if row else None
        finally:
            conn.close()

    async def resolve_chat_identifier(
        self,
        identifier: str,
        interface: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Resolve a chat identifier (name or ID) to chat records."""
        await self._ensure_table()
        
        conn = await get_conn()
        try:
            async with conn.cursor(aiomysql.DictCursor) as cursor:
                # Try exact chat_id match first
                await cursor.execute(
                    """
                    SELECT * FROM chatgpt_links
                    WHERE interface = %s AND chat_id = %s
                    """,
                    (interface, identifier)
                )
                results = await cursor.fetchall()
                
                if not results:
                    # Try chat name match
                    await cursor.execute(
                        """
                        SELECT * FROM chatgpt_links
                        WHERE interface = %s AND chat_name LIKE %s
                        """,
                        (interface, f"%{identifier}%")
                    )
                    results = await cursor.fetchall()
                
                return list(results)
        finally:
            conn.close()

    async def update_chat_names(
        self,
        chat_id: int | str,
        message_thread_id: Optional[int | str],
        interface: Optional[str] = None,
        *,
        chat_name: Optional[str] = None,
        message_thread_name: Optional[str] = None,
    ) -> int:
        """Update chat and thread names for existing records."""
        await self._ensure_table()
        
        conn = await get_conn()
        try:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    """
                    UPDATE chatgpt_links 
                    SET chat_name = COALESCE(%s, chat_name),
                        message_thread_name = COALESCE(%s, message_thread_name)
                    WHERE interface = %s AND chat_id = %s AND message_thread_id = %s
                    """,
                    (chat_name, message_thread_name, interface, str(chat_id), 
                     str(message_thread_id) if message_thread_id else None)
                )
                affected_rows = cursor.rowcount
                await conn.commit()
                return affected_rows
        finally:
            conn.close()

    async def list_all_links(self, interface: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all stored chat links, optionally filtered by interface."""
        await self._ensure_table()
        
        conn = await get_conn()
        try:
            async with conn.cursor(aiomysql.DictCursor) as cursor:
                if interface:
                    await cursor.execute(
                        """
                        SELECT * FROM chatgpt_links
                        WHERE interface = %s
                        ORDER BY chat_name, message_thread_name
                        """,
                        (interface,)
                    )
                else:
                    await cursor.execute(
                        """
                        SELECT * FROM chatgpt_links
                        ORDER BY interface, chat_name, message_thread_name
                        """
                    )
                return await cursor.fetchall()
        finally:
            conn.close()


class ChatLinkPlugin:
    """Plugin for chat link management."""

    def __init__(self):
        self.store = ChatLinkStore()
        register_plugin("chat_link", self)
        log_info("[chat_link] ChatLinkPlugin initialized and registered")

    def get_supported_action_types(self):
        return ["store_link", "get_link", "resolve_chat", "update_chat_names", "list_links"]

    def get_supported_actions(self):
        return {
            "store_link": {
                "description": "Store or update a ChatGPT conversation link",
                "required_fields": ["chat_id", "link"],
                "optional_fields": ["message_thread_id", "interface", "chat_name", "message_thread_name"],
            },
            "get_link": {
                "description": "Get the ChatGPT link for a chat/thread combination",
                "required_fields": ["chat_id"],
                "optional_fields": ["message_thread_id", "interface"],
            },
            "resolve_chat": {
                "description": "Resolve a chat identifier to chat records",
                "required_fields": ["identifier"],
                "optional_fields": ["interface"],
            },
            "update_chat_names": {
                "description": "Update chat and thread names",
                "required_fields": ["chat_id"],
                "optional_fields": ["message_thread_id", "interface", "chat_name", "message_thread_name"],
            },
            "list_links": {
                "description": "List all stored chat links",
                "required_fields": [],
                "optional_fields": ["interface"],
            },
        }

    def execute_action(self, action: dict, context: dict, bot, original_message):
        action_type = action.get("type")
        payload = action.get("payload", {}) or {}
        
        if action_type == "store_link":
            import asyncio
            asyncio.create_task(self._store_link_action(payload))
            
        elif action_type == "get_link":
            import asyncio
            asyncio.create_task(self._get_link_action(bot, original_message, payload))
            
        elif action_type == "resolve_chat":
            import asyncio
            asyncio.create_task(self._resolve_chat_action(bot, original_message, payload))
            
        elif action_type == "update_chat_names":
            import asyncio
            asyncio.create_task(self._update_names_action(payload))
            
        elif action_type == "list_links":
            import asyncio
            asyncio.create_task(self._list_links_action(bot, original_message, payload))

    async def _store_link_action(self, payload):
        """Execute store link action."""
        try:
            await self.store.store_link(
                chat_id=payload["chat_id"],
                message_thread_id=payload.get("message_thread_id"),
                link=payload["link"],
                interface=payload.get("interface"),
                chat_name=payload.get("chat_name"),
                message_thread_name=payload.get("message_thread_name")
            )
            log_info(f"[chat_link] Stored link for chat {payload['chat_id']}")
        except Exception as e:
            log_error(f"[chat_link] Failed to store link: {e}")

    async def _get_link_action(self, bot, original_message, payload):
        """Execute get link action and send response."""
        try:
            link = await self.store.get_link(
                chat_id=payload["chat_id"],
                message_thread_id=payload.get("message_thread_id"),
                interface=payload.get("interface")
            )
            if link:
                response = f"ChatGPT link: {link}"
            else:
                response = f"No link found for chat {payload['chat_id']}"
            
            await bot.send_message(original_message.chat_id, response)
        except Exception as e:
            log_error(f"[chat_link] Failed to get link: {e}")

    async def _resolve_chat_action(self, bot, original_message, payload):
        """Execute resolve chat action and send response."""
        try:
            results = await self.store.resolve_chat_identifier(
                identifier=payload["identifier"],
                interface=payload.get("interface")
            )
            if results:
                response = f"Found {len(results)} chat(s):\n"
                for result in results:
                    response += f"• {result['chat_name'] or result['chat_id']} ({result['interface']})\n"
            else:
                response = f"No chats found for identifier '{payload['identifier']}'"
            
            await bot.send_message(original_message.chat_id, response)
        except Exception as e:
            log_error(f"[chat_link] Failed to resolve chat: {e}")

    async def _update_names_action(self, payload):
        """Execute update names action."""
        try:
            affected = await self.store.update_chat_names(
                chat_id=payload["chat_id"],
                message_thread_id=payload.get("message_thread_id"),
                interface=payload.get("interface"),
                chat_name=payload.get("chat_name"),
                message_thread_name=payload.get("message_thread_name")
            )
            log_info(f"[chat_link] Updated {affected} chat name records")
        except Exception as e:
            log_error(f"[chat_link] Failed to update names: {e}")

    async def _list_links_action(self, bot, original_message, payload):
        """Execute list links action and send response."""
        try:
            links = await self.store.list_all_links(
                interface=payload.get("interface")
            )
            if links:
                response = f"Found {len(links)} chat link(s):\n"
                for link in links[:10]:  # Limit to first 10
                    name = link['chat_name'] or link['chat_id']
                    response += f"• {name} ({link['interface']})\n"
                if len(links) > 10:
                    response += f"... and {len(links) - 10} more"
            else:
                response = "No chat links found"
            
            await bot.send_message(original_message.chat_id, response)
        except Exception as e:
            log_error(f"[chat_link] Failed to list links: {e}")


PLUGIN_CLASS = ChatLinkPlugin
