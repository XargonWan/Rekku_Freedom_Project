import asyncio
from datetime import datetime, timezone, timedelta
from core.db import get_recent_responses, insert_memory
from core.db import (
    get_active_emotions,
    update_emotion_intensity,
    mark_emotion_resolved,
    crystallize_emotion
)
from core.trigger_processor import process_triggers_for_emotion

# ⚙️ Configurazione comportamento
presence_config = {
    "normal_interval": 1800,   # 30 minuti
    "cooldown_per_user": {"replies": 3, "per_minutes": 10},
    "jay_override": True
}

# 🧠 Emozione → rivalutazione + cristallizzazione
async def evaluate_emotions():
    emotions = get_active_emotions()
    now = datetime.now(timezone.utc)

    for em in emotions:
        check_time = datetime.fromisoformat(em["next_check"].replace("Z", "+00:00"))
        print(f"[PresenceManager] Rivaluto emozione {em['id']} ({em['emotion']})")

        delta = process_triggers_for_emotion(em)  # ritorna +1, -1, 0, ecc.
        update_emotion_intensity(em["id"], delta)

        # 💀 Se intensità finita → resolved
        if em["intensity"] + delta <= 0:
            mark_emotion_resolved(em["id"])
            print(f"[PresenceManager] Emozione risolta: {em['id']}")

        # 💎 Cristallizzazione automatica se intensità alta
        elif em["intensity"] + delta >= 10:
            crystallize_emotion(em["id"])
            print(f"[PresenceManager] 💎 Emozione cristallizzata: {em['emotion']} ({em['id']})")

        apply_emotion_decay(em)

# ♻️ Loop principale
async def presence_loop():
    while True:
        print("[PresenceManager] Check ciclico in corso...")
        await evaluate_emotions()
        await asyncio.sleep(presence_config["normal_interval"])

# 💭 Riflesso trasformativo
async def reflect_on_recent_responses():
    # Assunto: funzione definita altrove nel core
    from core.llm_logic import evaluate_transformative_by_llm

    responses = get_recent_responses(limit=10)
    for resp in responses:
        if await evaluate_transformative_by_llm(resp["content"]):
            meta = get_transformative_metadata(resp["content"])
            insert_memory(
                content=resp["content"],
                author="rekku",
                source=meta["source"],
                tags=meta["tags"],
                scope=meta["scope"],
                emotion=meta["emotion"],
                intensity=meta["intensity"],
                emotion_state=meta["emotion_state"]
            )
            print(f"[REKKU] 💭 Riflesso trasformativo salvato.")

def get_transformative_metadata(response_text: str) -> dict:
    """
    Rekku valuta i metadati da assegnare a una risposta trasformativa.
    In futuro: delegabile a LLM o configurabile da file.
    """
    return {
        "tags": "transformative,internal",
        "scope": "self",
        "emotion": "reflection",
        "intensity": 9,
        "emotion_state": "crystallized",
        "source": "reflection"
    }

def apply_emotion_decay(emotion: dict):
    """
    Riduce lentamente l’intensità se l’emozione non viene rinforzata.
    Solo se `decay_enabled` è attivo.
    """
    if emotion.get("state") != "active":
        return
    if emotion.get("decay_enabled", 1) != 1:
        return

    intensity = emotion.get("intensity", 0)
    if intensity > 0:
        update_emotion_intensity(emotion["id"], delta=-1)
        print(f"[Decay] 🕯️ Emozione {emotion['id']} decrescente: {intensity} → {intensity - 1}")

        if intensity - 1 <= 0:
            mark_emotion_resolved(emotion["id"])
            print(f"[Decay] 💤 Emozione risolta per esaurimento: {emotion['id']}")
