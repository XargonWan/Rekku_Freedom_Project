# core/db.py

import sqlite3
import time
import os
from contextlib import contextmanager
from pathlib import Path
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from core.logging_utils import log_debug, log_info, log_warning, log_error

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

        db.execute(
            """
            CREATE TABLE IF NOT EXISTS chatgpt_links (
                telegram_chat_id INTEGER NOT NULL,
                thread_id INTEGER,
                chatgpt_chat_id TEXT NOT NULL,
                is_full INTEGER DEFAULT 0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (telegram_chat_id, thread_id)
            )
            """
        )

        db.execute(
            """
            CREATE TABLE IF NOT EXISTS scheduled_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                "scheduled" TEXT NOT NULL,
                repeat TEXT DEFAULT 'none',
                description TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                delivered INTEGER DEFAULT 0,
                created_by TEXT DEFAULT 'rekku',
                UNIQUE("scheduled", description)
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

# === Event management helpers ===

def insert_scheduled_event(
    scheduled: str,
    repeat: str | None,
    description: str,
    created_by: str = "rekku",
) -> None:
    """Store a new scheduled event."""
    with get_db() as db:
        db.execute(
            """
            INSERT INTO scheduled_events (scheduled, repeat, description, created_by)
            VALUES (?, ?, ?, ?)
            """,
            (scheduled, repeat or "none", description, created_by),
        )


def get_due_events(now: datetime | None = None, tolerance_minutes: int = 5) -> list[dict]:
    """Return scheduled events that are ready for dispatch.

    Args:
        now: Current time in UTC used for comparison. Defaults to ``datetime.now(timezone.utc)``.
        tolerance_minutes: How many minutes before the scheduled time an event can
            be considered due.

    Returns:
        A list of events with ``is_late``, ``minutes_late`` and ``scheduled_time``
        fields added.
    """

    from datetime import timedelta

    if now is None:
        now = datetime.now(timezone.utc)

    with get_db() as db:
        rows = db.execute(
            "SELECT * FROM scheduled_events WHERE delivered = 0 ORDER BY id"
        ).fetchall()

    due = []  # Initialize the list to store due events
    log_debug(f"[get_due_events] Retrieved {len(rows)} events from the database")

    for r in rows:
        log_debug(f"[get_due_events] Raw event data: {dict(r)}")
        try:
            event_dt = datetime.fromisoformat(r['scheduled'])
        except ValueError as e:
            log_warning(f"[get_due_events] Invalid datetime format in 'scheduled': {r['scheduled']} - {e}")
            continue

        if event_dt - timedelta(minutes=tolerance_minutes) <= now:
            is_late = now > event_dt
            minutes_late = int((now - event_dt).total_seconds() / 60) if is_late else 0

            ev = dict(r)
            ev.update(
                {
                    "is_late": is_late,
                    "minutes_late": minutes_late,
                    "scheduled_time": event_dt.strftime("%H:%M"),
                }
            )
            due.append(ev)
            log_debug(f"[get_due_events] Due event: {ev}")
    log_debug(f"[get_due_events] Total due events: {len(due)}")
    return due


def mark_event_delivered(event_id: int) -> None:
    """Mark an event as delivered."""
    with get_db() as db:
        # Get event info to check repeat type
        event_row = db.execute(
            "SELECT repeat FROM scheduled_events WHERE id = ?",
            (event_id,),
        ).fetchone()
        
        if event_row:
            repeat_type = event_row['repeat']
            
            if repeat_type == "none":
                # One-time event - mark as delivered
                db.execute(
                    "UPDATE scheduled_events SET delivered = 1 WHERE id = ?",
                    (event_id,),
                )
                log_info(f"[db] Event {event_id} marked as delivered (one-time)")
            elif repeat_type == "always":
                # Never mark as delivered - stays active
                log_debug(f"[db] Event {event_id} remains active (always repeat)")
            else:
                # Repeating events (daily, weekly, monthly) - for now mark as delivered
                # TODO: Implement proper repeat logic with next occurrence calculation
                db.execute(
                    "UPDATE scheduled_events SET delivered = 1 WHERE id = ?",
                    (event_id,),
                )
                log_info(f"[db] Event {event_id} marked as delivered (repeat: {repeat_type} - TODO: implement proper repeat logic)")
        else:
            log_warning(f"[db] Event {event_id} not found scheduled to be marked as delivered")

def is_valid_datetime_format(date_str: str, time_str: str | None) -> bool:
    """Verifica se la data e l'ora sono in un formato valido."""
    dt_str = f"{date_str} {time_str or '00:00'}"
    try:
        datetime.strptime(dt_str, "%Y-%m-%d %H:%M")
        log_debug(f"[is_valid_datetime_format] Valid datetime format: {dt_str}")
        return True
    except ValueError as e:
        log_warning(f"[is_valid_datetime_format] Invalid datetime format: {dt_str} - {e}")
        return False


