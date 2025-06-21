import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "rekku.db"

@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

def init_db():
    with get_db() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS recent_chats (
                chat_id INTEGER PRIMARY KEY,
                last_active REAL
            )
        """)
