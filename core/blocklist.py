# core/blocklist.py

from core.db import get_db

def init_blocklist_table():
    with get_db() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS blocklist (
                user_id INTEGER PRIMARY KEY,
                reason TEXT,
                blocked_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

def block_user(user_id: int, reason: str = None):
    with get_db() as db:
        db.execute("""
            INSERT OR REPLACE INTO blocklist (user_id, reason, blocked_at)
            VALUES (?, ?, datetime('now'))
        """, (user_id, reason))

def unblock_user(user_id: int):
    with get_db() as db:
        db.execute("DELETE FROM blocklist WHERE user_id = ?", (user_id,))

def is_blocked(user_id: int) -> bool:
    with get_db() as db:
        row = db.execute("SELECT 1 FROM blocklist WHERE user_id = ?", (user_id,)).fetchone()
        return row is not None

def get_block_list() -> list:
    with get_db() as db:
        rows = db.execute("SELECT user_id FROM blocklist ORDER BY blocked_at DESC").fetchall()
        return [row["user_id"] for row in rows]

def get_block_details() -> list[dict]:
    with get_db() as db:
        rows = db.execute("""
            SELECT user_id, reason, blocked_at FROM blocklist
            ORDER BY blocked_at DESC
        """).fetchall()
        return [dict(row) for row in rows]
