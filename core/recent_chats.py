import time
from collections import OrderedDict

# chat_id: last_active_timestamp
_recent_chats = OrderedDict()
MAX_ENTRIES = 100  # numero massimo di chat da tenere in memoria


def track_chat(chat_id: int):
    """Registra una chat come attiva ora"""
    now = time.time()
    _recent_chats[chat_id] = now
    # Ricostruisci dict ordinato per timestamp decrescente
    sorted_chats = sorted(_recent_chats.items(), key=lambda x: x[1], reverse=True)
    _recent_chats.clear()
    _recent_chats.update(sorted_chats[:MAX_ENTRIES])


def get_last_active_chats(n=10):
    """Ritorna gli ultimi `n` chat_id attivi"""
    return list(_recent_chats.keys())[:n]


def get_last_active_chats_verbose(n=10, bot=None):
    """Ritorna una lista di tuple (chat_id, nome leggibile)"""
    results = []
    for chat_id in get_last_active_chats(n):
        name = str(chat_id)
        if bot:
            try:
                chat = bot.get_chat(chat_id)
                name = chat.title or chat.username or str(chat_id)
            except Exception:
                pass
        results.append((chat_id, name))
    return results
