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
Send a notification to the trainer via the centralized logic in core/notifier.py.
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


def _parse_trainer_ids(raw_value: str) -> dict[str, int]:
    """Parse TRAINER_IDS string into a mapping."""
    mapping = {}
    if not raw_value:
        return mapping
    for entry in raw_value.split(","):
        if ":" in entry:
            interface_name, trainer_id = entry.split(":", 1)
            mapping[interface_name.strip()] = int(trainer_id.strip())
    return mapping


# Parse trainer IDs for all interfaces
TRAINER_IDS = _parse_trainer_ids(os.getenv("TRAINER_IDS", ""))

# Legacy support - keep NOTIFY_ERRORS_TO_INTERFACES for backward compatibility
NOTIFY_ERRORS_TO_INTERFACES = _parse_notify_interfaces(
    os.getenv("NOTIFY_ERRORS_TO_INTERFACES", "")
)

def get_trainer_id(interface_name: str) -> int | None:
    """Return the trainer ID for the given interface.

    Prefers the new TRAINER_IDS mapping, falls back to NOTIFY_ERRORS_TO_INTERFACES.
    """
    # Try new TRAINER_IDS first
    trainer_id = TRAINER_IDS.get(interface_name)
    if trainer_id:
        return trainer_id
    # Fallback to legacy NOTIFY_ERRORS_TO_INTERFACES
    trainer_id = NOTIFY_ERRORS_TO_INTERFACES.get(interface_name)
    if trainer_id:
        return trainer_id
    return None

# LLM Configuration
LLM_MODE = os.getenv("LLM_MODE", "manual")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "YOUR_API_KEY")

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

_log_chat_id: int | None = None  # cached log chat ID
_log_chat_thread_id: int | None = None  # cached log chat thread ID
_log_chat_interface: str | None = None  # cached log chat interface

async def get_log_chat_id() -> int | None:
    """Return the configured log chat ID, if any."""
    global _log_chat_id
    if _log_chat_id is None:
        conn = await get_conn()
        try:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    "SELECT value FROM settings WHERE `setting_key` = 'log_chat_id'"
                )
                row = await cur.fetchone()
                if row:
                    try:
                        _log_chat_id = int(row["value"])
                        log_debug(
                            f"[config] 📥 Loaded log_chat_id from DB: {_log_chat_id}"
                        )
                    except (ValueError, TypeError):
                        _log_chat_id = None
        except Exception as e:
            log_error(f"[config] ❌ Error in get_log_chat_id(): {repr(e)}")
        finally:
            conn.close()
    return _log_chat_id


async def get_log_chat_interface() -> str | None:
    """Return the configured log chat interface, if any."""
    global _log_chat_interface
    if _log_chat_interface is None:
        conn = await get_conn()
        try:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    "SELECT value FROM settings WHERE `setting_key` = 'log_chat_interface'"
                )
                row = await cur.fetchone()
                if row:
                    _log_chat_interface = row["value"]
                    log_debug(
                        f"[config] 📥 Loaded log_chat_interface from DB: {_log_chat_interface}"
                    )
        except Exception as e:
            log_error(f"[config] ❌ Error in get_log_chat_interface(): {repr(e)}")
        finally:
            conn.close()
    return _log_chat_interface

async def set_log_chat_id(chat_id: int) -> None:
    """Persist and cache the log chat ID."""
    global _log_chat_id
    _log_chat_id = chat_id
    from core.db import ensure_core_tables
    await ensure_core_tables()
    conn = await get_conn()
    try:
        async with conn.cursor() as cur:
            await cur.execute(
                "REPLACE INTO settings (`setting_key`, `value`) VALUES (%s, %s)",
                ("log_chat", str(chat_id)),
            )
            await conn.commit()
            log_debug(
                f"[config] 💾 Saved log_chat in DB: {chat_id}"
            )
    except Exception as e:
        log_error(f"[config] ❌ Error in set_log_chat_id(): {repr(e)}")
    finally:
        conn.close()

async def get_log_chat_thread_id() -> int | None:
    """Return the configured log chat thread ID, if any."""
    global _log_chat_thread_id
    if _log_chat_thread_id is None:
        conn = await get_conn()
        try:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    "SELECT value FROM settings WHERE `setting_key` = 'log_chat_thread_id'"
                )
                row = await cur.fetchone()
                if row:
                    try:
                        _log_chat_thread_id = int(row["value"])
                        log_debug(
                            f"[config] 📥 Loaded log_chat_thread_id from DB: {_log_chat_thread_id}"
                        )
                    except (ValueError, TypeError):
                        _log_chat_thread_id = None
        except Exception as e:
            log_error(f"[config] ❌ Error in get_log_chat_thread_id(): {repr(e)}")
        finally:
            conn.close()
    return _log_chat_thread_id

async def set_log_chat_id_and_thread(chat_id: int, thread_id: int | None = None, interface: str = "webui") -> None:
    """Persist and cache the log chat ID, thread ID, and interface."""
    global _log_chat_id, _log_chat_thread_id, _log_chat_interface
    _log_chat_id = chat_id
    _log_chat_thread_id = thread_id
    _log_chat_interface = interface
    from core.db import ensure_core_tables
    await ensure_core_tables()
    conn = await get_conn()
    try:
        async with conn.cursor() as cur:
            await cur.execute(
                "REPLACE INTO settings (`setting_key`, `value`) VALUES (%s, %s)",
                ("log_chat_id", str(chat_id)),
            )
            await cur.execute(
                "REPLACE INTO settings (`setting_key`, `value`) VALUES (%s, %s)",
                ("log_chat_interface", interface),
            )
            if thread_id is not None:
                await cur.execute(
                    "REPLACE INTO settings (`setting_key`, `value`) VALUES (%s, %s)",
                    ("log_chat_thread_id", str(thread_id)),
                )
            else:
                # Remove thread setting if None
                await cur.execute(
                    "DELETE FROM settings WHERE `setting_key` = 'log_chat_thread_id'"
                )
            await conn.commit()
            log_debug(
                f"[config] 💾 Saved log chat in DB: {chat_id}, thread: {thread_id}, interface: {interface}"
            )
    except Exception as e:
        log_error(f"[config] ❌ Error in set_log_chat_id_and_thread(): {repr(e)}")
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


def get_log_chat_interface_sync() -> str | None:
    """Synchronous helper to fetch cached log chat interface."""
    global _log_chat_interface
    if _log_chat_interface is not None:
        return _log_chat_interface
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        # Cannot perform blocking DB fetch; return None until explicitly loaded
        return _log_chat_interface
    return asyncio.run(get_log_chat_interface())

def get_log_chat_thread_id_sync() -> int | None:
    """Synchronous helper to fetch cached log chat thread ID."""
    global _log_chat_thread_id
    if _log_chat_thread_id is not None:
        return _log_chat_thread_id
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        return _log_chat_thread_id
    return asyncio.run(get_log_chat_thread_id())

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

# Telegram Configuration
def get_bot_username():
    """Extract bot username from BOTFATHER_TOKEN automatically."""
    botfather_token = os.getenv("BOTFATHER_TOKEN")
    if botfather_token:
        try:
            # Extract username from token (format: 123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11)
            token_parts = botfather_token.split(':')
            if len(token_parts) == 2:
                return f"@{token_parts[0]}"
        except Exception as e:
            log_warning(f"[config] Could not extract username from BOTFATHER_TOKEN: {e}")
    return "@7654676853"  # Fallback

BOT_USERNAME = get_bot_username()
