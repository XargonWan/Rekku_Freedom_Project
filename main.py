# main.py

from core.db import init_db
from core.blocklist import init_blocklist_table
from core.config import get_active_llm
from core.plugin_instance import load_plugin

if __name__ == "__main__":
    # Inizializzazioni DB e tabelle
    init_db()
    init_blocklist_table()

    # \U0001f501 Carica il plugin LLM attivo da DB (senza notify_fn, verr� impostato dopo dal bot)
    llm_name = get_active_llm()
    print(f"[DEBUG/main] Plugin attivo da caricare: {llm_name}")
    load_plugin(llm_name)

    # \u2705 Avvia il bot solo ora
    from interface.telegram_bot import start_bot
    start_bot()
