# core/config.py

import os
import json
try:
    from dotenv import load_dotenv  # type: ignore
except Exception:  # pragma: no cover - fallback when dotenv not installed
    def load_dotenv(*args, **kwargs):
        return False
from core.db import get_conn
import aiomysql
from core.logging_utils import log_debug, log_info, log_warning, log_error
"""
notify_trainer(chat_id: int, message: str) -> None
Invia una notifica al trainer (Telegram) tramite la logica centralizzata in core/notifier.py.
"""

# ✅ Load all environment variables from .env
load_dotenv(dotenv_path="/app/.env", override=False)


def _parse_notify_interfaces(value: str):
    mapping = {}
    for item in value.split(","):
        item = item.strip()
        if not item:
            continue
        if ":" not in item:
            log_warning(
                f"[config] Invalid NOTIFY_ERRORS_TO_INTERFACES entry '{item}' (expected interface:trainer_id)"
            )
            continue
        interface, trainer_id = item.split(":", 1)
        try:
            mapping[interface.strip()] = int(trainer_id.strip())
        except ValueError:
            log_warning(
                f"[config] Invalid trainer ID '{trainer_id}' for interface '{interface}'"
            )
    return mapping


NOTIFY_ERRORS_TO_INTERFACES = _parse_notify_interfaces(
    os.getenv("NOTIFY_ERRORS_TO_INTERFACES", "")
)

TELEGRAM_TRAINER_ID = int(os.getenv("TELEGRAM_TRAINER_ID", "0") or 0)

BOT_TOKEN = os.getenv("BOTFATHER_TOKEN") or os.getenv("TELEGRAM_TOKEN")
BOT_USERNAME = "rekku_freedom_project"
LLM_MODE = os.getenv("LLM_MODE", "manual")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "YOUR_API_KEY")

if not BOT_TOKEN:
    raise RuntimeError("❌ BOTFATHER_TOKEN missing. Set it in .env or as an environment variable.")

# === Persistent LLM mode ===

_active_llm = None  # local global variable

async def get_active_llm():
    global _active_llm
    if _active_llm is None:
        conn = await get_conn()
        try:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute("SELECT value FROM settings WHERE `setting_key` = 'active_llm'")
                row = await cur.fetchone()
                if row:
                    _active_llm = row["value"]
                    log_debug(f"[config] 🧠 Active LLM plugin loaded from DB: {_active_llm}")
                else:
                    _active_llm = "manual"
        except Exception as e:
            log_error(f"[config] ❌ Error in get_active_llm(): {repr(e)}")
        finally:
            conn.close()
    return _active_llm

async def set_active_llm(name: str):
    global _active_llm
    if name == _active_llm:
        log_debug(f"[config] 🔄 LLM already set: {name}, no update needed.")
        return
    _active_llm = name
    from core.db import ensure_core_tables
    await ensure_core_tables()
    conn = await get_conn()
    try:
        async with conn.cursor() as cur:
            await cur.execute(
                "REPLACE INTO settings (`setting_key`, value) VALUES (%s, %s)",
                ("active_llm", name),
            )
            await conn.commit()
            log_debug(f"[config] 💾 Saved active plugin in DB: {name}")
    except Exception as e:
        log_error(f"[config] ❌ Error in set_active_llm(): {repr(e)}")
    finally:
        conn.close()

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
        log_error(f"Unable to save model: {repr(e)}")
