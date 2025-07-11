# core/db.py

import sqlite3
import time
import os
from contextlib import contextmanager
from pathlib import Path
from datetime import datetime, timezone
from logging_utils import log_debug, log_info, log_warning, log_error

DB_PATH = Path(
    os.getenv(
        "MEMORY_DB",
        Path(__file__).parent.parent / "persona" / "rekku_memories.db",
    )
)

@contextmanager
def get_db():
    first_time = not DB_PATH.exists()
    if first_time:
        log_warning(f"{DB_PATH.name} not found, creating new database")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # ✅ key-based access

    if first_time:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
            """
        )
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

def init_db():
    with get_db() as db:
        # recent_chats table (tracks active chats)
        db.execute("""
            CREATE TABLE IF NOT EXISTS recent_chats (
                chat_id INTEGER PRIMARY KEY,
                last_active REAL
            )
        """)

        db.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)

        # memories table (stored memories)
        db.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                content TEXT,
                author TEXT,
                source TEXT,
                tags TEXT,
                scope TEXT,
                emotion TEXT,
                intensity INTEGER,
                emotion_state TEXT
            )
        """)

        # emotion_diary table (emotional events)
        db.execute("""
            CREATE TABLE IF NOT EXISTS emotion_diary (
                id TEXT PRIMARY KEY,
                source TEXT,
                event TEXT,
                emotion TEXT,
                intensity INTEGER,
                state TEXT,
                trigger_condition TEXT,
                decision_logic TEXT,
                next_check TEXT
            )
        """)

        # tag_links table (relationships between tags)
        db.execute("""
            CREATE TABLE IF NOT EXISTS tag_links (
                tag TEXT,
                related_tag TEXT
            )
        """)

        # blocklist table (blocked users)
        db.execute("""
            CREATE TABLE IF NOT EXISTS blocklist (
                user_id INTEGER PRIMARY KEY
            )
        """)

        # message_map table (maps forwarded messages to the original)
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

# 🧠 Insert a new memory into the database
def insert_memory(
    content: str,
    author: str,
    source: str,
    tags: str,
    scope: str = None,
    emotion: str = None,
    intensity: int = None,
    emotion_state: str = None,
    timestamp: str = None
):
    if not timestamp:
        timestamp = datetime.now(timezone.utc).isoformat()

    with get_db() as db:
        db.execute("""
            INSERT INTO memories (timestamp, content, author, source, tags, scope, emotion, intensity, emotion_state)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (timestamp, content, author, source, tags, scope, emotion, intensity, emotion_state))

# 💥 Insert a new emotional event
def insert_emotion_event(
    eid: str,
    source: str,
    event: str,
    emotion: str,
    intensity: int,
    state: str,
    trigger_condition: str,
    decision_logic: str,
    next_check: str
):
    with get_db() as db:
        db.execute("""
            INSERT INTO emotion_diary (id, source, event, emotion, intensity, state, trigger_condition, decision_logic, next_check)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (eid, source, event, emotion, intensity, state, trigger_condition, decision_logic, next_check))

# 🔍 Retrieve active emotions
def get_active_emotions():
    with get_db() as db:
        rows = db.execute("""
            SELECT * FROM emotion_diary
            WHERE state = 'active'
        """).fetchall()
        return [dict(row) for row in rows]

# ➕ Modify the intensity of an emotion
def update_emotion_intensity(eid: str, delta: int):
    with get_db() as db:
        db.execute("""
            UPDATE emotion_diary
            SET intensity = intensity + ?
            WHERE id = ?
        """, (delta, eid))

# 💀 Mark an emotion as resolved
def mark_emotion_resolved(eid: str):
    with get_db() as db:
        db.execute("""
            UPDATE emotion_diary
            SET state = 'resolved'
            WHERE id = ?
        """, (eid,))

# 💎 Crystallize an active emotion
def crystallize_emotion(eid: str):
    with get_db() as db:
        db.execute("""
            UPDATE emotion_diary
            SET state = 'crystallized'
            WHERE id = ?
        """, (eid,))

# 🔁 Retrieve recent responses generated by the bot
def get_recent_responses(since_timestamp: str) -> list[dict]:
    with get_db() as db:
        rows = db.execute("""
            SELECT * FROM memories
            WHERE source = 'rekku' AND timestamp >= ?
            ORDER BY timestamp DESC
        """, (since_timestamp,)).fetchall()
        return [dict(row) for row in rows]


