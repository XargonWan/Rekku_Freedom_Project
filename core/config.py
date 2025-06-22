import os
import json
from dotenv import load_dotenv

load_dotenv()

OWNER_ID = int(os.getenv("OWNER_ID", "123456789"))
BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
BOT_USERNAME = "Rekku_the_bot"
LLM_MODE = os.getenv("LLM_MODE", "manual")

# === LLM mode persistente ===
LLM_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "llm_mode.txt")

def get_active_llm():
    if os.path.exists(LLM_CONFIG_PATH):
        with open(LLM_CONFIG_PATH, "r") as f:
            return f.read().strip()
    return os.getenv("LLM_MODE", "manual")

def set_active_llm(mode: str):
    with open(LLM_CONFIG_PATH, "w") as f:
        f.write(mode)

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
        