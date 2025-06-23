# main.py

from interface.telegram_bot import start_bot
from core.db import init_db
from core.blocklist import init_blocklist_table
from core.config import get_active_llm
from core.plugin_instance import plugin, load_plugin

if __name__ == "__main__":
    # Inizializzazioni
    init_db()
    init_blocklist_table()

    # Carica plugin LLM attivo (es. manual, openai_chatgpt, llm_simulator...)
    load_plugin(get_active_llm())

    # Avvia il bot
    start_bot()
