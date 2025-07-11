# core/config.py

import os
import json
try:
    from dotenv import load_dotenv  # type: ignore
except Exception:  # pragma: no cover - fallback when dotenv not installed
    def load_dotenv(*args, **kwargs):
        return False
from core.db import get_db
from logging_utils import log_debug, log_info, log_warning, log_error

# ✅ Load all environment variables from .env
load_dotenv(dotenv_path="/app/.env", override=False)

OWNER_ID = int(os.getenv("OWNER_ID", "123456789"))
BOT_TOKEN = os.getenv("BOTFATHER_TOKEN") or os.getenv("TELEGRAM_TOKEN")
BOT_USERNAME = "rekku_freedom_project"
LLM_MODE = os.getenv("LLM_MODE", "manual")

if not BOT_TOKEN:
    raise RuntimeError("❌ BOTFATHER_TOKEN missing. Set it in .env or as an environment variable.")

# === Persistent LLM mode ===

_active_llm = None  # local global variable

def get_active_llm():
    global _active_llm
    if _active_llm is None:
        try:
            with get_db() as db:
                row = db.execute("SELECT value FROM settings WHERE key = 'active_llm'").fetchone()
                if row:
                    _active_llm = row[0]
                    log_debug(f"[config] 🧠 Active LLM plugin loaded from DB: {_active_llm}")
                else:
                    _active_llm = "manual"
        except Exception as e:
            log_error(f"[config] ❌ Error in get_active_llm(): {e}")
            _active_llm = "manual"
    return _active_llm

def set_active_llm(name: str):
    global _active_llm
    if name == _active_llm:
        log_debug(f"[config] 🔄 LLM already set: {name}, no update needed.")
        return
    _active_llm = name
    try:
        with get_db() as db:
            db.execute("REPLACE INTO settings (key, value) VALUES (?, ?)", ("active_llm", name))
            db.commit()
            log_debug(f"[config] 💾 Saved active plugin in DB: {name}")
    except Exception as e:
        log_error(f"[config] ❌ Error in set_active_llm(): {e}")

def list_available_llms():
    engines_dir = os.path.join(os.path.dirname(__file__), "../llm_engines")
    return sorted(
        fname.removesuffix(".py")
        for fname in os.listdir(engines_dir)
        if fname.endswith(".py") and not fname.startswith("__")
    )

# === OpenAI API Key ===
def get_user_api_key():
    return os.getenv("OPENAI_API_KEY")

# === Global model management ===
MODEL_FILE = os.path.join(os.path.dirname(__file__), "model_config.json")

def get_current_model():
    if os.path.exists(MODEL_FILE):
        try:
            with open(MODEL_FILE, "r", encoding="utf-8") as f:
                return json.load(f).get("model")
        except Exception:
            return None
    return None

def set_current_model(model: str):
    try:
        with open(MODEL_FILE, "w", encoding="utf-8") as f:
            json.dump({"model": model}, f, indent=2)
    except Exception as e:
        log_error(f"Unable to save model: {e}")
        