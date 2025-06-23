from core.db import insert_memory

# \U0001f527 Configurazioni interne statiche (espandibili)
DEFAULT_TAGS = "auto,interazione"
DEFAULT_SCOPE = "jay"
DEFAULT_SOURCE = "chat"

REMEMBER_KEYWORDS = [
    "jay", "prometto", "giuramento", "famiglia",
    "retrodeck", "tanuki", "sei importante"
]

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
    Rekku salva internamente ci� che ha deciso di ricordare.
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
    print("[REKKU_CORE] \U0001f9e0 Memoria salvata autonomamente.")