# core/message_map.py

"""Persistent mapping between trainer forwarded messages and original targets."""

import time
from core.db import get_db
from core.logging_utils import log_debug, log_info, log_warning, log_error


def init_table():
    """Ensure the message_map table exists."""
    with get_db() as db:
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS message_map (
                trainer_message_id INTEGER PRIMARY KEY,
                chat_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                timestamp REAL
            )
            """
        )


def add_mapping(trainer_message_id: int, chat_id: int, message_id: int):
    """Store mapping from trainer message to original chat/message."""
    ts = time.time()
    with get_db() as db:
        db.execute(
            """
            INSERT OR REPLACE INTO message_map
                (trainer_message_id, chat_id, message_id, timestamp)
            VALUES (?, ?, ?, ?)
            """,
            (trainer_message_id, chat_id, message_id, ts),
        )
    log_debug(f"[message_map] Stored mapping {trainer_message_id} -> {chat_id}/{message_id}")


def get_mapping(trainer_message_id: int):
    """Retrieve mapping if exists."""
    with get_db() as db:
        row = db.execute(
            "SELECT chat_id, message_id FROM message_map WHERE trainer_message_id = ?",
            (trainer_message_id,),
        ).fetchone()
    if row:
        result = {"chat_id": row["chat_id"], "message_id": row["message_id"]}
        log_debug(f"[message_map] Found mapping for {trainer_message_id}: {result}")
        return result
    log_debug(f"[message_map] No mapping for {trainer_message_id}")
    return None


def delete_mapping(trainer_message_id: int):
    """Remove a mapping."""
    with get_db() as db:
        db.execute("DELETE FROM message_map WHERE trainer_message_id = ?", (trainer_message_id,))
    log_debug(f"[message_map] Deleted mapping for {trainer_message_id}")


def purge_old_entries(max_age_seconds: int) -> int:
    """Delete mappings older than given age in seconds. Returns number deleted."""
    cutoff = time.time() - max_age_seconds
    with get_db() as db:
        cur = db.execute(
            "DELETE FROM message_map WHERE timestamp < ?",
            (cutoff,),
        )
        deleted = cur.rowcount
    log_debug(f"[message_map] Purged {deleted} entries older than {max_age_seconds} seconds")
    return deleted
