import time

# ⏳ Durata di validità per una risposta in attesa
TIMEOUT_SECONDS = 60

# user_id: { chat_id, message_id, type, expires_at }
pending_targets = {}

def set_target(user_id, chat_id, message_id, content_type):
    """
    Registra un target temporaneo per una risposta (es. messaggio in attesa di addestramento).
    """
    expires_at = time.time() + TIMEOUT_SECONDS
    pending_targets[user_id] = {
        "chat_id": chat_id,
        "message_id": message_id,
        "type": content_type,
        "expires_at": expires_at
    }

def get_target(user_id):
    """
    Recupera un target valido (se non scaduto).
    """
    entry = pending_targets.get(user_id)
    if not entry:
        return None
    if time.time() > entry["expires_at"]:
        clear_target(user_id)
        return "EXPIRED"
    return entry

def clear_target(user_id):
    """
    Rimuove un target assegnato.
    """
    pending_targets.pop(user_id, None)

def has_pending(user_id):
    """
    Verifica se un utente ha un target in attesa.
    """
    return user_id in pending_targets
