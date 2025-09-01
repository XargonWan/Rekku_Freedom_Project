# core/config.py

import os
import json
import asyncio
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

# Resolve the Telegram trainer ID from the mapping if the legacy
# environment variable is missing or set to 0. This keeps backward
# compatibility while allowing NOTIFY_ERRORS_TO_INTERFACES to be the
# single source of truth for trainer IDs.
TELEGRAM_TRAINER_ID = int(os.getenv("TELEGRAM_TRAINER_ID", "0") or 0)
if TELEGRAM_TRAINER_ID == 0:
    TELEGRAM_TRAINER_ID = NOTIFY_ERRORS_TO_INTERFACES.get("telegram_bot", 0)
    if TELEGRAM_TRAINER_ID:
        log_info(f"[config] TELEGRAM_TRAINER_ID resolved from NOTIFY_ERRORS_TO_INTERFACES: {TELEGRAM_TRAINER_ID}")
    else:
        log_warning("[config] TELEGRAM_TRAINER_ID not configured; trainer-only commands will be rejected")
else:
    log_info(f"[config] TELEGRAM_TRAINER_ID loaded from environment: {TELEGRAM_TRAINER_ID}")


def get_trainer_id(interface_name: str) -> int | None:
    """Return the trainer ID for the given interface.

    Prefers the mapping provided by ``NOTIFY_ERRORS_TO_INTERFACES`` and
    falls back to legacy environment variables (e.g. ``TELEGRAM_TRAINER_ID``)
    when necessary.
    """
    trainer_id = NOTIFY_ERRORS_TO_INTERFACES.get(interface_name)
    if trainer_id:
        return trainer_id
    if interface_name == "telegram_bot" and TELEGRAM_TRAINER_ID:
        return TELEGRAM_TRAINER_ID
    return None

BOT_TOKEN = os.getenv("BOTFATHER_TOKEN") or os.getenv("TELEGRAM_TOKEN")
BOT_USERNAME = "rekku_freedom_project"
DISCORD_REACT_ROLES = os.getenv("DISCORD_REACT_ROLES", "true").lower() in ("1", "true", "yes")
DISCORD_NOTIFY_ERRORS_DM = os.getenv("DISCORD_NOTIFY_ERRORS_DM", "false").lower() in (
    "1",
    "true",
    "yes",
)
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

_log_chat_id: int | None = None  # cached Telegram log chat ID

async def get_log_chat_id() -> int | None:
    """Return the configured Telegram log chat ID, if any."""
    global _log_chat_id
    if _log_chat_id is None:
        conn = await get_conn()
        try:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    "SELECT value FROM settings WHERE `setting_key` = 'telegram_log_chat'"
                )
                row = await cur.fetchone()
                if row:
                    try:
                        _log_chat_id = int(row["value"])
                        log_debug(
                            f"[config] 📥 Loaded telegram_log_chat from DB: {_log_chat_id}"
                        )
                    except (ValueError, TypeError):
                        _log_chat_id = None
        except Exception as e:
            log_error(f"[config] ❌ Error in get_log_chat_id(): {repr(e)}")
        finally:
            conn.close()
    return _log_chat_id

async def set_log_chat_id(chat_id: int) -> None:
    """Persist and cache the Telegram log chat ID."""
    global _log_chat_id
    _log_chat_id = chat_id
    from core.db import ensure_core_tables
    await ensure_core_tables()
    conn = await get_conn()
    try:
        async with conn.cursor() as cur:
            await cur.execute(
                "REPLACE INTO settings (`setting_key`, `value`) VALUES (%s, %s)",
                ("telegram_log_chat", str(chat_id)),
            )
            await conn.commit()
            log_debug(
                f"[config] 💾 Saved telegram_log_chat in DB: {chat_id}"
            )
    except Exception as e:
        log_error(f"[config] ❌ Error in set_log_chat_id(): {repr(e)}")
    finally:
        conn.close()

def get_log_chat_id_sync() -> int | None:
    """Synchronous helper to fetch cached log chat ID, loading from DB if needed."""
    global _log_chat_id
    if _log_chat_id is not None:
        return _log_chat_id
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        # Cannot perform blocking DB fetch; return None until explicitly loaded
        return _log_chat_id
    return asyncio.run(get_log_chat_id())

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
