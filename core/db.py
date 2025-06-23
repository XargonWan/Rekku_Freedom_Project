# core/db.py

import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from datetime import datetime, timezone

DB_PATH = Path(__file__).parent.parent / "rekku_memories.db"  # ✅ database unico

@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # ✅ accesso per chiave
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

def init_db():
    with get_db() as db:
        # Tabella recent_chats (per tracciamento delle chat attive)
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

        # Tabella memories (per i ricordi memorizzati)
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

        # Tabella emotion_diary (per gli eventi emozionali)
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

        # Tabella tag_links (per le relazioni tra tag)
        db.execute("""
            CREATE TABLE IF NOT EXISTS tag_links (
                tag TEXT,
                related_tag TEXT
            )
        """)

        # Tabella blocklist (per utenti bloccati)
        db.execute("""
            CREATE TABLE IF NOT EXISTS blocklist (
                user_id INTEGER PRIMARY KEY
            )
        """)

# 🧠 Inserisce una nuova memoria nel database
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

# 💥 Inserisce un nuovo evento emozionale
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

# 🔍 Recupera le emozioni attive
def get_active_emotions():
    with get_db() as db:
        rows = db.execute("""
            SELECT * FROM emotion_diary
            WHERE state = 'active'
        """).fetchall()
        return [dict(row) for row in rows]

# ➕ Modifica l’intensità di un’emozione
def update_emotion_intensity(eid: str, delta: int):
    with get_db() as db:
        db.execute("""
            UPDATE emotion_diary
            SET intensity = intensity + ?
            WHERE id = ?
        """, (delta, eid))

# 💀 Marca un’emozione come risolta
def mark_emotion_resolved(eid: str):
    with get_db() as db:
        db.execute("""
            UPDATE emotion_diary
            SET state = 'resolved'
            WHERE id = ?
        """, (eid,))

# 💎 Cristallizza un'emozione attiva
def crystallize_emotion(eid: str):
    with get_db() as db:
        db.execute("""
            UPDATE emotion_diary
            SET state = 'crystallized'
            WHERE id = ?
        """, (eid,))

# 🔁 Recupera le risposte recenti generate dal bot
def get_recent_responses(since_timestamp: str) -> list[dict]:
    with get_db() as db:
        rows = db.execute("""
            SELECT * FROM memories
            WHERE source = 'rekku' AND timestamp >= ?
            ORDER BY timestamp DESC
        """, (since_timestamp,)).fetchall()
        return [dict(row) for row in rows]


