from core.db import insert_memory
import logging
from datetime import datetime

# === Setup logging memoria ===
os.makedirs("logs", exist_ok=True)  # Assicura esistenza cartella log

memory_logger = logging.getLogger("rekku.memory")
if not memory_logger.handlers:
    memory_logger.setLevel(logging.INFO)
    handler = logging.FileHandler("logs/memoria.log", encoding="utf-8")
    formatter = logging.Formatter('%(asctime)s - %(message)s')
    handler.setFormatter(formatter)
    memory_logger.addHandler(handler)


# Configurazioni interne statiche (espandibili)
DEFAULT_TAGS = "auto,interazione"
DEFAULT_SCOPE = "general"
DEFAULT_SOURCE = "chat"

REMEMBER_KEYWORDS = []

def should_remember(user_text: str, response_text: str) -> bool:
    """
    Rekku valuta autonomamente se l'interazione � memorabile.
    Questa decisione � completamente interna, non visibile all'utente.
    """
    text = (user_text + " " + response_text).lower()

    if any(k in text for k in REMEMBER_KEYWORDS):
        return True

    if "mi hai fatto sentire" in response_text.lower():
        return True

    return False


def silently_record_memory(
    user_text: str,
    response_text: str,
    tags: str = DEFAULT_TAGS,
    scope: str = DEFAULT_SCOPE,
    source: str = DEFAULT_SOURCE
):
    """
    Rekku salva internamente ciò che ha deciso di ricordare.
    Nessun feedback viene dato all'esterno.
    """
    insert_memory(
        content=user_text,
        author="rekku",
        source=source,
        tags=tags,
        scope=scope,
        emotion=None,
        intensity=None,
        emotion_state=None
    )

    print("[REKKU_CORE] 🧠 Memoria salvata autonomamente.")

    memory_logger.info(
        f"[MEMORIA] Salvata da Rekku\n"
        f"→ Input: {user_text}\n"
        f"→ Risposta: {response_text}\n"
        f"→ Tags: {tags} | Scope: {scope} | Source: {source}"
    )