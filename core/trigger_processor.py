# core/trigger_processor.py

from core.db import get_db
from datetime import datetime, timedelta, timezone

# Intervallo di osservazione per valutare se l\u2019emozione � rinforzata o attenuata
LOOKBACK_MINUTES = 30

def process_triggers_for_emotion(emotion: dict) -> int:
    """
    Valuta gli eventi recenti per determinare se rafforzare, attenuare o ignorare l\u2019emozione.
    Ritorna un delta (es. +1, -1, 0) da applicare all\u2019intensit�.
    """
    emotion_type = emotion["emotion"]
    now = datetime.now(timezone.utc)
    since = now - timedelta(minutes=LOOKBACK_MINUTES)

    # Recupera eventi recenti legati allo stesso scope
    scope = emotion.get("scope", "auto")  # fallback se non definito
    query = """
        SELECT content FROM memories
        WHERE timestamp >= ? AND scope = ?
        ORDER BY timestamp DESC
    """
    with get_db() as db:
        rows = db.execute(query, (since.isoformat(), scope)).fetchall()

    contents = [row[0] for row in rows]

    # Semplice euristica: cerca parole chiave rinforzanti o attenuanti
    reinforce_keywords = {
        "anger": ["odio", "mi hai deluso", "non vali niente", "idiota"],
        "sadness": ["mi manchi", "sei lontana", "sono solo"],
        "joy": ["ti voglio bene", "sei speciale", "grazie", "ce l\u2019abbiamo fatta"],
    }

    soften_keywords = {
        "anger": ["scusa", "non volevo", "ti rispetto"],
        "sadness": ["ci sono", "non sei sola", "ti abbraccio"],
        "joy": ["che noia", "basta", "non importa"],
    }

    delta = 0
    for content in contents:
        text = content.lower()
        if any(k in text for k in reinforce_keywords.get(emotion_type, [])):
            delta += 1
        if any(k in text for k in soften_keywords.get(emotion_type, [])):
            delta -= 1

    print(f"[TriggerProcessor] Delta valutato per {emotion_type}: {delta}")
    return delta
