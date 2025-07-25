# core/db.py

import os
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pymysql
from pymysql.cursors import DictCursor
import aiomysql

from core.logging_utils import log_debug, log_info, log_warning, log_error

# Database connection parameters
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_USER = os.getenv("DB_USER", "rekku")
DB_PASS = os.getenv("DB_PASS", "rekku")
DB_NAME = os.getenv("DB_NAME", "rekku")


def get_conn():
    """Return a live MariaDB connection."""
    return pymysql.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASS,
        database=DB_NAME,
        cursorclass=DictCursor,
        autocommit=False,
    )

@contextmanager
def get_db():
    """Context manager that yields a connection wrapper for MariaDB."""

    conn = get_conn()

    class _Wrapper:
        def __init__(self, connection):
            self.conn = connection

        def execute(self, query, params=None):
            if params is None:
                params = ()
            with self.conn.cursor() as cur:
                cur.execute(query, params)
                return cur

        def commit(self):
            self.conn.commit()

    wrapper = _Wrapper(conn)
    try:
        yield wrapper
        conn.commit()
    finally:
        conn.close()

async def init_db() -> None:
    """Asynchronously initialize essential MariaDB tables."""
    conn = await aiomysql.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASS,
        db=DB_NAME,
        autocommit=True,
    )
    async with conn.cursor() as cur:
        # memories table
        await cur.execute(
            """
            CREATE TABLE IF NOT EXISTS memories (
                id INT AUTO_INCREMENT PRIMARY KEY,
                timestamp DATETIME NOT NULL,
                content TEXT NOT NULL,
                author VARCHAR(100),
                source VARCHAR(100),
                tags TEXT,
                scope VARCHAR(50),
                emotion VARCHAR(50),
                intensity INT,
                emotion_state VARCHAR(50)
            )
            """
        )

        # emotion_diary table
        await cur.execute(
            """
            CREATE TABLE IF NOT EXISTS emotion_diary (
                id VARCHAR(100) PRIMARY KEY,
                source VARCHAR(100),
                event TEXT,
                emotion VARCHAR(50),
                intensity INT,
                state VARCHAR(50),
                trigger_condition TEXT,
                decision_logic TEXT,
                next_check DATETIME
            )
            """
        )

        # scheduled_events table
        await cur.execute(
            """
            CREATE TABLE IF NOT EXISTS scheduled_events (
                id INT AUTO_INCREMENT PRIMARY KEY,
                `date` DATE NOT NULL,
                `time` TIME,
                repeat VARCHAR(20) DEFAULT 'none',
                description TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                delivered BOOLEAN DEFAULT FALSE,
                created_by VARCHAR(100) DEFAULT 'rekku',
                UNIQUE KEY unique_event (`date`, `time`, description(100))
            )
            """
        )
    conn.close()

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
        db.execute(
            """
            INSERT INTO memories (timestamp, content, author, source, tags, scope, emotion, intensity, emotion_state)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (timestamp, content, author, source, tags, scope, emotion, intensity, emotion_state),
        )

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
        db.execute(
            """
            INSERT INTO emotion_diary (id, source, event, emotion, intensity, state, trigger_condition, decision_logic, next_check)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                eid,
                source,
                event,
                emotion,
                intensity,
                state,
                trigger_condition,
                decision_logic,
                next_check,
            ),
        )

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
            SET intensity = intensity + %s
            WHERE id = %s
        """, (delta, eid))

# 💀 Mark an emotion as resolved
def mark_emotion_resolved(eid: str):
    with get_db() as db:
        db.execute("""
            UPDATE emotion_diary
            SET state = 'resolved'
            WHERE id = %s
        """, (eid,))

# 💎 Crystallize an active emotion
def crystallize_emotion(eid: str):
    with get_db() as db:
        db.execute("""
            UPDATE emotion_diary
            SET state = 'crystallized'
            WHERE id = %s
        """, (eid,))

# 🔁 Retrieve recent responses generated by the bot
def get_recent_responses(since_timestamp: str) -> list[dict]:
    with get_db() as db:
        rows = db.execute("""
            SELECT * FROM memories
            WHERE source = 'rekku' AND timestamp >= %s
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
            VALUES (%s, %s, %s, %s)
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
            "SELECT repeat FROM scheduled_events WHERE id = %s",
            (event_id,),
        ).fetchone()
        
        if event_row:
            repeat_type = event_row['repeat']
            
            if repeat_type == "none":
                # One-time event - mark as delivered
                db.execute(
                    "UPDATE scheduled_events SET delivered = 1 WHERE id = %s",
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
                    "UPDATE scheduled_events SET delivered = 1 WHERE id = %s",
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


