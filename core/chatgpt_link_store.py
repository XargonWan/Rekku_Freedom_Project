from typing import Optional
from core.db import get_db
from core.logging_utils import log_debug, log_warning

class ChatLinkStore:
    def __init__(self):
        self._ensure_table()

    def _ensure_table(self) -> None:
        with get_db() as db:
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

    def get_link(self, telegram_chat_id: int, thread_id: Optional[int]) -> Optional[str]:
        log_debug(f"[chatlink] Searching for link: telegram_chat_id={telegram_chat_id}, thread_id={thread_id}")
        with get_db() as db:
            row = db.execute(
                """
                SELECT chatgpt_chat_id, is_full
                FROM chatgpt_links
                WHERE telegram_chat_id = ? AND thread_id IS ?
                """,
                (telegram_chat_id, thread_id),
            ).fetchone()
        
        if row:
            log_debug(f"[chatlink] Found row: chatgpt_chat_id={row['chatgpt_chat_id']}, is_full={row['is_full']}")
            if not row["is_full"]:
                log_debug(
                    f"[chatlink] Found mapping {telegram_chat_id}/{thread_id} -> {row['chatgpt_chat_id']}"
                )
                return row["chatgpt_chat_id"]
            else:
                log_debug(f"[chatlink] Found mapping but chat is marked as full")
        else:
            log_debug(f"[chatlink] No row found for {telegram_chat_id}/{thread_id}")
            
        log_debug(f"[chatlink] No usable mapping for {telegram_chat_id}/{thread_id}")
        return None

    def save_link(self, telegram_chat_id: int, thread_id: Optional[int], chatgpt_chat_id: str) -> None:
        with get_db() as db:
            db.execute(
                """
                INSERT OR REPLACE INTO chatgpt_links
                    (telegram_chat_id, thread_id, chatgpt_chat_id, is_full, updated_at)
                VALUES (?, ?, ?, 0, CURRENT_TIMESTAMP)
                """,
                (telegram_chat_id, thread_id, chatgpt_chat_id),
            )
        log_debug(
            f"[chatlink] Saved mapping {telegram_chat_id}/{thread_id} -> {chatgpt_chat_id}"
        )

    def mark_full(self, chatgpt_chat_id: str) -> None:
        with get_db() as db:
            db.execute(
                "UPDATE chatgpt_links SET is_full=1, updated_at=CURRENT_TIMESTAMP WHERE chatgpt_chat_id=?",
                (chatgpt_chat_id,),
            )
        log_debug(f"[chatlink] Marked chat {chatgpt_chat_id} as full")

    def is_full(self, chatgpt_chat_id: str) -> bool:
        with get_db() as db:
            row = db.execute(
                "SELECT is_full FROM chatgpt_links WHERE chatgpt_chat_id=?",
                (chatgpt_chat_id,),
            ).fetchone()
        result = bool(row and row["is_full"])
        log_debug(f"[chatlink] is_full({chatgpt_chat_id}) -> {result}")
        return result

    def remove(self, telegram_chat_id: int, thread_id: Optional[int]) -> bool:
        """
        Rimuove il collegamento ChatGPT per un dato telegram_chat_id e thread_id.
        Restituisce True se una riga è stata eliminata, altrimenti False.
        """
        with get_db() as db:
            result = db.execute(
                """
                DELETE FROM chatgpt_links
                WHERE telegram_chat_id = ? AND thread_id IS ?
                """,
                (telegram_chat_id, thread_id),
            )
        rows_deleted = result.rowcount > 0
        if rows_deleted:
            log_debug(f"[chatlink] Rimosso il collegamento per telegram_chat_id={telegram_chat_id}, thread_id={thread_id}")
        else:
            log_debug(f"[chatlink] Nessun collegamento trovato per telegram_chat_id={telegram_chat_id}, thread_id={thread_id}")
        return rows_deleted
