# core/prompt_engine.py

from core.rekku_tagging import extract_tags, expand_tags
import os
from datetime import datetime
from core.db import get_db


def load_identity_prompt() -> str:
    try:
        with open("persona/prompt.txt", "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        print("[WARN] prompt.txt non trovato. Prompt caratteriale non caricato.")
        return ""

def search_memories(tags=None, scope=None, limit=5):
    if not tags:
        return []

    placeholders = ",".join(["?"] * len(tags))

    query = f"""
        SELECT DISTINCT content
        FROM memories
        WHERE json_valid(tags)
          AND EXISTS (
              SELECT 1
              FROM json_each(memories.tags)
              WHERE json_each.value IN ({placeholders})
          )
    """

    params = tags.copy()

    if scope:
        query += " AND scope = ?"
        params.append(scope)

    query += " ORDER BY timestamp DESC LIMIT ?"
    params.append(limit)

    print("[DEBUG] Query robusta:")
    print(query)
    print("[DEBUG] Parametri:", params)

    try:
        with get_db() as db:
            return [row[0] for row in db.execute(query, params)]
    except Exception as e:
        print(f"[ERROR] Query fallita: {e}")
        return []

def build_prompt(
    user_text: str,
    identity_prompt: str = "",
    extract_tags_fn=extract_tags,
    search_memories_fn=None,
    limit: int = 5,
    log_path: str = "logs/prompt_cycle.log"
) -> list:
    tags = extract_tags_fn(user_text) if extract_tags_fn else []
    expanded_tags = expand_tags(tags) if tags else []
    memories = search_memories_fn(tags=expanded_tags, limit=limit) if search_memories_fn else []

    memory_block = "\n".join(f"- {mem}" for mem in memories) if memories else "Nessuna memoria rilevante trovata."

    messages = []

    if identity_prompt:
        messages.append({"role": "system", "content": identity_prompt})

    messages.append({
        "role": "system",
        "content": f"[MEMORIE RILEVANTI]\n{memory_block}"
    })

    messages.append({"role": "user", "content": user_text.strip()})

    # === LOGGING SU FILE ===
    try:
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        timestamp = datetime.utcnow().isoformat()
        with open(log_path, "a", encoding="utf-8") as log_file:
            log_file.write(f"\n[{timestamp}] --- CICLO DI RAGIONAMENTO ---\n")
            log_file.write(f"> Testo utente: {user_text.strip()}\n")
            log_file.write(f"> Tag estratti: {tags}\n")
            log_file.write(f"> Tag espansi: {expanded_tags}\n")
            log_file.write(f"> Memorie trovate: {len(memories)}\n")
            for msg in messages:
                role = msg.get("role", "").upper()
                content = msg.get("content", "").strip()
                log_file.write(f"[{role}]\n{content}\n\n")
            log_file.write("----------- FINE -----------\n")
    except Exception as e:
        print(f"[WARN] Errore nel logging del prompt: {e}")

    return messages

