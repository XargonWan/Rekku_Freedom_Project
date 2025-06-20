# core/blocklist.py

import json
import os

BLOCKLIST_FILE = "data/blocklist.json"
blocked_users = set()

def _load_blocklist():
    global blocked_users
    if os.path.exists(BLOCKLIST_FILE):
        with open(BLOCKLIST_FILE, "r") as f:
            try:
                data = json.load(f)
                blocked_users = set(data)
            except json.JSONDecodeError:
                blocked_users = set()
    else:
        blocked_users = set()

def _save_blocklist():
    with open(BLOCKLIST_FILE, "w") as f:
        json.dump(list(blocked_users), f)

def block_user(user_id: int):
    blocked_users.add(user_id)
    _save_blocklist()

def unblock_user(user_id: int):
    blocked_users.discard(user_id)
    _save_blocklist()

def is_blocked(user_id: int) -> bool:
    return user_id in blocked_users

def get_block_list() -> list:
    return list(blocked_users)

# Carica all'avvio
_load_blocklist()
