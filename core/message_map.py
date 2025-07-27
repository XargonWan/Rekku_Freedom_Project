# core/message_map.py

"""Persistent mapping between trainer forwarded messages and original targets."""

import time
import aiomysql
from core.db import get_conn
from core.logging_utils import log_debug, log_info, log_warning, log_error


async def init_table():
    """Ensure the message_map table exists."""
    conn = await get_conn()
    try:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                CREATE TABLE IF NOT EXISTS message_map (
                    trainer_message_id INTEGER PRIMARY KEY,
                    chat_id INTEGER NOT NULL,
                    message_id INTEGER NOT NULL,
                    timestamp REAL
                )
                """
            )
            await conn.commit()
    finally:
        conn.close()


async def add_mapping(trainer_message_id: int, chat_id: int, message_id: int):
    """Store mapping from trainer message to original chat/message."""
    ts = time.time()
    conn = await get_conn()
    try:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                REPLACE INTO message_map
                    (trainer_message_id, chat_id, message_id, timestamp)
                VALUES (%s, %s, %s, %s)
                """,
                (trainer_message_id, chat_id, message_id, ts),
            )
            await conn.commit()
    finally:
        conn.close()
    log_debug(f"[message_map] Stored mapping {trainer_message_id} -> {chat_id}/{message_id}")


async def get_mapping(trainer_message_id: int):
    """Retrieve mapping if exists."""
    conn = await get_conn()
    try:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                "SELECT chat_id, message_id FROM message_map WHERE trainer_message_id = %s",
                (trainer_message_id,),
            )
            row = await cur.fetchone()
    finally:
        conn.close()
    if row:
        result = {"chat_id": row["chat_id"], "message_id": row["message_id"]}
        log_debug(f"[message_map] Found mapping for {trainer_message_id}: {result}")
        return result
    log_debug(f"[message_map] No mapping for {trainer_message_id}")
    return None


async def delete_mapping(trainer_message_id: int):
    """Remove a mapping."""
    conn = await get_conn()
    try:
        async with conn.cursor() as cur:
            await cur.execute(
                "DELETE FROM message_map WHERE trainer_message_id = %s",
                (trainer_message_id,),
            )
            await conn.commit()
    finally:
        conn.close()
    log_debug(f"[message_map] Deleted mapping for {trainer_message_id}")


async def purge_old_entries(max_age_seconds: int) -> int:
    """Delete mappings older than given age in seconds. Returns number deleted."""
    cutoff = time.time() - max_age_seconds
    conn = await get_conn()
    try:
        async with conn.cursor() as cur:
            result = await cur.execute(
                "DELETE FROM message_map WHERE timestamp < %s",
                (cutoff,),
            )
            await conn.commit()
            deleted = result
    finally:
        conn.close()
    log_debug(f"[message_map] Purged {deleted} entries older than {max_age_seconds} seconds")
    return deleted
