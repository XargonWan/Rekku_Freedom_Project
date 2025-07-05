# core/config.py

import os
import json
from dotenv import load_dotenv
from core.db import get_db

load_dotenv()

OWNER_ID = int(os.getenv("OWNER_ID", "123456789"))
BOT_TOKEN = os.getenv("BOTFATHER_TOKEN") or os.getenv("TELEGRAM_TOKEN")
BOT_USERNAME = "rekku_freedom_project"
LLM_MODE = os.getenv("LLM_MODE", "manual")
SELENIUM_PROFILE_DIR = os.getenv("SELENIUM_PROFILE_DIR", "./selenium_profile")
# Directory dove cercare eventuali estensioni da caricare con Selenium
SELENIUM_EXTENSIONS_DIR = os.getenv("SELENIUM_EXTENSIONS_DIR", "./extensions")

if not BOT_TOKEN:
    raise RuntimeError("❌ BOTFATHER_TOKEN mancante. Impostalo in .env o come variabile d'ambiente.")

# === LLM mode persistente ===

_active_llm = None  # variabile globale locale

def get_active_llm():
    global _active_llm
    if _active_llm is None:
        try:
            with get_db() as db:
                row = db.execute("SELECT value FROM settings WHERE key = 'active_llm'").fetchone()
                if row:
                    _active_llm = row[0]
                    print(f"[DEBUG/config] 🧠 Plugin LLM attivo caricato da DB: {_active_llm}")
                else:
                    _active_llm = "manual"
        except Exception as e:
            print(f"[ERROR/config] ❌ Errore get_active_llm(): {e}")
            _active_llm = "manual"
    return _active_llm

def set_active_llm(name: str):
    global _active_llm
    if name == _active_llm:
        print(f"[DEBUG/config] 🔄 LLM già impostato: {name}, nessun aggiornamento necessario.")
        return
    _active_llm = name
    try:
        with get_db() as db:
            db.execute("REPLACE INTO settings (key, value) VALUES (?, ?)", ("active_llm", name))
            db.commit()
            print(f"[DEBUG/config] 💾 Salvato plugin attivo nel DB: {name}")
    except Exception as e:
        print(f"[ERROR/config] ❌ Errore set_active_llm(): {e}")

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

# === Gestione modello globale ===
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
        print(f"[ERROR] Impossibile salvare il modello: {e}")
        