# core/db.py

import os
from datetime import datetime, timezone
import asyncio

import aiomysql

from core.logging_utils import log_debug, log_info, log_warning, log_error

# Database connection parameters
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_USER = os.getenv("DB_USER", "rekku")
DB_PASS = os.getenv("DB_PASS", "rekku")
DB_NAME = os.getenv("DB_NAME", "rekku")

# Log della configurazione del database per debug
log_info(f"[db] Configuration: HOST={DB_HOST}, PORT={DB_PORT}, USER={DB_USER}, DB_NAME={DB_NAME}")
log_debug(f"[db] Password length: {len(DB_PASS)} characters")

_db_initialized = False
_db_init_lock = asyncio.Lock()

async def get_conn() -> aiomysql.Connection:
    """Return an async MariaDB connection using aiomysql."""
    log_debug(
        f"[db] Opening connection to {DB_USER}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    )
    conn = await aiomysql.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASS,
        db=DB_NAME,
        autocommit=True,
    )
    log_debug("[db] Connection opened")
    return conn

async def test_connection() -> bool:
    """Check if the database is reachable."""
    try:
        conn = await get_conn()
        async with conn.cursor() as cur:
            await cur.execute("SELECT 1")
            await cur.fetchone()
        conn.close()
        return True
    except Exception as e:
        print(f"[test_connection] Error: {e}")
        return False

async def init_db() -> None:
    """Asynchronously initialize essential MariaDB tables."""
    conn = await get_conn()
    try:
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
                    recurrence_type VARCHAR(20) DEFAULT 'none',
                    description TEXT NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    delivered BOOLEAN DEFAULT FALSE,
                    created_by VARCHAR(100) DEFAULT 'rekku',
                    UNIQUE KEY unique_event (`date`, `time`, description(100))
                )
                """
            )

            # settings table for configuration values
            await cur.execute(
                """
                CREATE TABLE IF NOT EXISTS settings (
                    `setting_key` VARCHAR(255) PRIMARY KEY,
                    `value` TEXT NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                )
                """
            )

            # recent_chats table for tracking active chats
            await cur.execute(
                """
                CREATE TABLE IF NOT EXISTS recent_chats (
                    chat_id BIGINT PRIMARY KEY,
                    last_active DOUBLE NOT NULL,
                    metadata TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_last_active (last_active)
                )
                """
            )

            # Insert default settings if they don't exist
            await cur.execute(
                """
                INSERT IGNORE INTO settings (`setting_key`, `value`) VALUES ('active_llm', 'manual')
                """
            )
    except Exception as e:
        print(f"[init_db] Error: {e}")
    finally:
        conn.close()


async def ensure_core_tables() -> None:
    """Ensure core tables exist by initializing them once."""
    global _db_initialized
    if _db_initialized:
        return
    async with _db_init_lock:
        if not _db_initialized:
            await init_db()
            _db_initialized = True

# 🧠 Insert a new memory into the database
async def insert_memory(
    content: str,
    author: str,
    source: str,
    tags: str,
    scope: str | None = None,
    emotion: str | None = None,
    intensity: int | None = None,
    emotion_state: str | None = None,
    timestamp: str | None = None,
) -> None:
    if not timestamp:
        timestamp = datetime.now(timezone.utc).isoformat()

    await ensure_core_tables()

    conn = await get_conn()
    try:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO memories (timestamp, content, author, source, tags, scope, emotion, intensity, emotion_state)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (timestamp, content, author, source, tags, scope, emotion, intensity, emotion_state),
            )
    except Exception as e:
        print(f"[insert_memory] Error: {e}")
    finally:
        conn.close()

# 💥 Insert a new emotional event
async def insert_emotion_event(
    eid: str,
    source: str,
    event: str,
    emotion: str,
    intensity: int,
    state: str,
    trigger_condition: str,
    decision_logic: str,
    next_check: str,
) -> None:
    await ensure_core_tables()
    conn = await get_conn()
    try:
        async with conn.cursor() as cur:
            await cur.execute(
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
    except Exception as e:
        print(f"[insert_emotion_event] Error: {e}")
    finally:
        conn.close()

# 🔍 Retrieve active emotions
async def get_active_emotions() -> list[dict]:
    conn = await get_conn()
    try:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                """
                SELECT * FROM emotion_diary
                WHERE state = 'active'
                """
            )
            rows = await cur.fetchall()
    except Exception as e:
        print(f"[get_active_emotions] Error: {e}")
        rows = []
    finally:
        conn.close()
    return [dict(row) for row in rows]

# ➕ Modify the intensity of an emotion
async def update_emotion_intensity(eid: str, delta: int) -> None:
    await ensure_core_tables()
    conn = await get_conn()
    try:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                UPDATE emotion_diary
                SET intensity = intensity + %s
                WHERE id = %s
                """,
                (delta, eid),
            )
    except Exception as e:
        print(f"[update_emotion_intensity] Error: {e}")
    finally:
        conn.close()

# 💀 Mark an emotion as resolved
async def mark_emotion_resolved(eid: str) -> None:
    await ensure_core_tables()
    conn = await get_conn()
    try:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                UPDATE emotion_diary
                SET state = 'resolved'
                WHERE id = %s
                """,
                (eid,),
            )
    except Exception as e:
        print(f"[mark_emotion_resolved] Error: {e}")
    finally:
        conn.close()

# 💎 Crystallize an active emotion
async def crystallize_emotion(eid: str) -> None:
    await ensure_core_tables()
    conn = await get_conn()
    try:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                UPDATE emotion_diary
                SET state = 'crystallized'
                WHERE id = %s
                """,
                (eid,),
            )
    except Exception as e:
        print(f"[crystallize_emotion] Error: {e}")
    finally:
        conn.close()

# 🔁 Retrieve recent responses generated by the bot
async def get_recent_responses(since_timestamp: str) -> list[dict]:
    conn = await get_conn()
    try:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                """
                SELECT * FROM memories
                WHERE source = 'rekku' AND timestamp >= %s
                ORDER BY timestamp DESC
                """,
                (since_timestamp,),
            )
            rows = await cur.fetchall()
    except Exception as e:
        print(f"[get_recent_responses] Error: {e}")
        rows = []
    finally:
        conn.close()
    return [dict(row) for row in rows]

# === Event management helpers ===

async def insert_scheduled_event(
    scheduled: str,
    recurrence_type: str | None,
    description: str,
    created_by: str = "rekku",
) -> None:
    """Store a new scheduled event."""
    await ensure_core_tables()
    conn = await get_conn()
    try:
        async with conn.cursor() as cur:
            await safe_db_execute(
                cur,
                """
                INSERT INTO scheduled_events (scheduled, recurrence_type, description, created_by)
                VALUES (%s, %s, %s, %s)
                """,
                (scheduled, recurrence_type or "none", description, created_by),
                ensure_fn=ensure_core_tables,
            )
    except Exception as e:
        print(f"[insert_scheduled_event] Error: {e}")
    finally:
        conn.close()


async def get_due_events(now: datetime | None = None, tolerance_minutes: int = 5) -> list[dict]:
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

    log_debug(f"[get_due_events] Checking events at UTC {now.isoformat()}")

    query = "SELECT * FROM scheduled_events WHERE delivered = 0 ORDER BY id"
    log_debug(f"[get_due_events] Executing query: {query}")

    conn = await get_conn()
    try:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await safe_db_execute(cur, query, ensure_fn=ensure_core_tables)
            rows = await cur.fetchall()
            log_debug(f"[get_due_events] Retrieved {len(rows)} rows")
            for row in rows:
                log_debug(f"[get_due_events] Row: {dict(row)}")
    except Exception as e:
        log_error(f"[get_due_events] Error executing query: {repr(e)}")
        rows = []
    finally:
        conn.close()
        log_debug("[get_due_events] Connection closed")

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


async def mark_event_delivered(event_id: int) -> None:
    """Mark an event as delivered."""
    await ensure_core_tables()
    conn = await get_conn()
    try:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            # Get event info to check recurrence type
            await safe_db_execute(
                cur,
                "SELECT recurrence_type FROM scheduled_events WHERE id = %s",
                (event_id,),
                ensure_fn=ensure_core_tables,
            )
            event_row = await cur.fetchone()

            if event_row:
                repeat_type = event_row['recurrence_type']

                if repeat_type == "none":
                    # One-time event - mark as delivered
                    await safe_db_execute(
                        cur,
                        "UPDATE scheduled_events SET delivered = 1 WHERE id = %s",
                        (event_id,),
                        ensure_fn=ensure_core_tables,
                    )
                    log_info(f"[db] Event {event_id} marked as delivered (one-time)")
                elif repeat_type == "always":
                    # Never mark as delivered - stays active
                    log_debug(f"[db] Event {event_id} remains active (always recurrence)")
                else:
                    # Repeating events (daily, weekly, monthly)
                    # TODO: Implement proper recurrence logic with next occurrence calculation
                    await safe_db_execute(
                        cur,
                        "UPDATE scheduled_events SET delivered = 1 WHERE id = %s",
                        (event_id,),
                        ensure_fn=ensure_core_tables,
                    )
                    log_info(
                        f"[db] Event {event_id} marked as delivered (recurrence: {repeat_type} - TODO: implement proper recurrence logic)"
                    )
            else:
                log_warning(f"[db] Event {event_id} not found scheduled to be marked as delivered")
    except Exception as e:
        print(f"[mark_event_delivered] Error: {e}")
    finally:
        conn.close()

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


async def safe_db_execute(
    cursor: aiomysql.Cursor,
    query: str,
    params: tuple | list = (),
    ensure_fn=None,
) -> any:
    """Execute a SQL statement and retry once if table missing (error 1146).

    Args:
        cursor: Active aiomysql cursor.
        query: SQL query to execute.
        params: Parameters for the query.
        ensure_fn: Coroutine that creates the missing table if called.

    Returns:
        Result of ``cursor.execute``.
    """
    try:
        log_debug(f"[safe_db_execute] Executing: {query} {params}")
        return await cursor.execute(query, params)
    except aiomysql.Error as e:
        err_code = e.args[0] if e.args else None
        if err_code == 1146 and ensure_fn:
            log_debug(
                f"[safe_db_execute] Table missing for query. Calling ensure_fn()"
            )
            try:
                await ensure_fn()
            except Exception as ensure_exc:  # pragma: no cover - best effort
                log_error(
                    f"[safe_db_execute] ensure_fn failed: {repr(ensure_exc)}"
                )
                raise
            try:
                log_debug("[safe_db_execute] Retrying query after ensure_fn")
                return await cursor.execute(query, params)
            except Exception as retry_exc:
                log_error(
                    f"[safe_db_execute] Retry failed: {repr(retry_exc)}"
                )
                raise
        log_error(f"[safe_db_execute] Query failed: {repr(e)}")
        raise

async def execute_query(query: str, params: tuple = ()) -> list:
    """Execute a SQL query and return the results."""
    try:
        conn = await get_conn()
        async with conn.cursor() as cur:
            await cur.execute(query, params)
            results = await cur.fetchall()
        conn.close()
        return results
    except Exception as e:
        log_error(f"[execute_query] Error executing query: {query}, Error: {e}")
        raise


