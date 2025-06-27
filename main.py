# main.py

from interface.telegram_bot import start_bot
from core.db import init_db
from core.blocklist import init_blocklist_table
from core.config import get_active_llm
from core.plugin_instance import plugin, load_plugin
from core.db import get_db

if __name__ == "__main__":
    # Inizializzazioni
    init_db()
    init_blocklist_table()

    # Avvia il bot
    start_bot()

    with get_db() as db:
        rows = db.execute("SELECT content, tags FROM memories LIMIT 10").fetchall()
        for content, tags in rows:
            print("CONTENT:", content)
            print("TAGS:", tags)
