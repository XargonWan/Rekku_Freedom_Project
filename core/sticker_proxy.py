# core/sticker_proxy.py

import time

# user_id: { chat_id, message_id, expires_at }
pending_sticker_targets = {}

TIMEOUT_SECONDS = 60

def set_target(user_id, chat_id, message_id):
    expires_at = time.time() + TIMEOUT_SECONDS
    pending_sticker_targets[user_id] = {
        "chat_id": chat_id,
        "message_id": message_id,
        "expires_at": expires_at
    }

def get_target(user_id):
    entry = pending_sticker_targets.get(user_id)
    if not entry:
        return None
    if time.time() > entry["expires_at"]:
        clear_target(user_id)
        return "EXPIRED"
    return entry

def clear_target(user_id):
    pending_sticker_targets.pop(user_id, None)

def has_pending(user_id):
    return user_id in pending_sticker_targets
