from telegram import Update
from telegram.ext import ContextTypes
from core.config import OWNER_ID
import json
import os
from core.logging_utils import log_debug, log_info, log_warning, log_error

CONFIG_PATH = "config/rekku_config.json"

def load_config() -> dict:
    if not os.path.exists(CONFIG_PATH):
        return {}
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)

def save_config(config: dict):
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2)

def get_context_state() -> bool:
    return load_config().get("context_mode", False)

def set_context_state(state: bool):
    config = load_config()
    config["context_mode"] = state
    save_config(config)

async def context_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return

    current = get_context_state()
    new_state = not current
    set_context_state(new_state)

    state_str = "enabled" if new_state else "disabled"
    await update.message.reply_text(f"🧠 Context mode {state_str}.")

    log_debug(f"Context mode {state_str}.")

