# core/blocklist.py

from core.db import get_conn
import aiomysql

async def init_blocklist_table():
    conn = await get_conn()
    try:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                CREATE TABLE IF NOT EXISTS blocklist (
                    user_id BIGINT PRIMARY KEY,
                    reason TEXT,
                    blocked_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
    finally:
        conn.close()

async def block_user(user_id: int, reason: str = None):
    conn = await get_conn()
    try:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                REPLACE INTO blocklist (user_id, reason, blocked_at)
                VALUES (%s, %s, NOW())
                """,
                (user_id, reason),
            )
    finally:
        conn.close()

async def unblock_user(user_id: int):
    conn = await get_conn()
    try:
        async with conn.cursor() as cur:
            await cur.execute("DELETE FROM blocklist WHERE user_id = %s", (user_id,))
    finally:
        conn.close()

async def is_blocked(user_id: int) -> bool:
    conn = await get_conn()
    try:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT 1 FROM blocklist WHERE user_id = %s", (user_id,))
            row = await cur.fetchone()
            return row is not None
    finally:
        conn.close()

async def get_block_list() -> list:
    conn = await get_conn()
    try:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT user_id FROM blocklist ORDER BY blocked_at DESC")
            rows = await cur.fetchall()
            return [row["user_id"] for row in rows]
    finally:
        conn.close()

async def get_block_details() -> list[dict]:
    conn = await get_conn()
    try:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("""
                SELECT user_id, reason, blocked_at FROM blocklist
                ORDER BY blocked_at DESC
            """)
            rows = await cur.fetchall()
            return [dict(row) for row in rows]
    finally:
        conn.close()
