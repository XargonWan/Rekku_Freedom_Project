# core/plugin_instance.py

from core.config import get_active_llm, set_active_llm
from core.prompt_engine import load_identity_prompt
import json
from core.prompt_engine import build_json_prompt
from core.action_parser import parse_action
import asyncio
from core.logging_utils import log_debug, log_info, log_warning, log_error

plugin = None
rekku_identity_prompt = None

def load_plugin(name: str, notify_fn=None):
    global plugin, rekku_identity_prompt

    # 🔁 If already loaded but different, replace it or update notify_fn
    if plugin is not None:
        current_plugin_name = plugin.__class__.__module__.split(".")[-1]
        if current_plugin_name != name:
            log_debug(f"[plugin] 🔄 Cambio plugin da {current_plugin_name} a {name}")
        else:
            # 🔁 Even if it's the same plugin, update notify_fn if provided
            if notify_fn and hasattr(plugin, "set_notify_fn"):
                try:
                    plugin.set_notify_fn(notify_fn)
                    log_debug("[plugin] ✅ notify_fn updated dynamically")
                except Exception as e:
                    log_error(f"[plugin] ❌ Unable to update notify_fn: {e}", e)
            else:
                log_debug(f"[plugin] ⚠️ Plugin already loaded: {plugin.__class__.__name__}")
            return

    try:
        import importlib
        module = importlib.import_module(f"llm_engines.{name}")
        log_debug(f"[plugin] Module llm_engines.{name} imported successfully.")
    except ModuleNotFoundError as e:
        log_error(f"[plugin] ❌ Unable to import llm_engines.{name}: {e}", e)
        raise ValueError(f"Invalid LLM plugin: {name}")

    if not hasattr(module, "PLUGIN_CLASS"):
        raise ValueError(f"Plugin `{name}` does not define `PLUGIN_CLASS`.")

    plugin_class = getattr(module, "PLUGIN_CLASS")

    if notify_fn:
        log_debug("[plugin] notify_fn function passed to plugin.")
    else:
        log_debug("[plugin] ⚠️ No notify_fn function provided.")

    try:
        plugin_args = plugin_class.__init__.__code__.co_varnames
        if "notify_fn" in plugin_args:
            plugin_instance = plugin_class(notify_fn=notify_fn)
        else:
            plugin_instance = plugin_class()
    except Exception as e:
        log_error(f"[plugin] ❌ Error during plugin initialization: {e}", e)
        raise

    plugin = plugin_instance
    log_debug(f"[plugin] Plugin initialized: {plugin.__class__.__name__}")

    if hasattr(plugin, "start"):
        try:
            start_fn = plugin.start
            if asyncio.iscoroutinefunction(start_fn):
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    loop = None
                if loop and loop.is_running():
                    loop.create_task(start_fn())
                    log_debug("[plugin] Plugin start executed on running loop.")
                else:
                    log_debug(
                        "[plugin] No running loop; plugin start will be invoked later."
                    )
            else:
                start_fn()
                log_debug("[plugin] Plugin start executed.")
        except Exception as e:
            log_error(f"[plugin] Error during plugin start: {e}", e)

    if name != "manual":
        rekku_identity_prompt = load_identity_prompt()
        log_debug("[plugin] Identity prompt loaded.")

    # Default model
    if hasattr(plugin, "get_supported_models"):
        try:
            models = plugin.get_supported_models()
            if models:
                from config import get_current_model, set_current_model
                current = get_current_model()
                if not current:
                    set_current_model(models[0])
                    log_debug(f"[plugin] Default model set: {models[0]}")
        except Exception as e:
            log_warning(f"[plugin] Error during model setup: {e}")

    set_active_llm(name)

async def handle_incoming_message(bot, message, context_memory):
    if plugin is None:
        raise RuntimeError("No LLM plugin loaded.")

    user_id = message.from_user.id if message.from_user else "unknown"
    text = message.text or ""
    log_debug(
        f"[plugin] Incoming for {plugin.__class__.__name__}: chat_id={message.chat_id}, user_id={user_id}, text={text!r}"
    )

    prompt = await build_json_prompt(message, context_memory)

    log_debug("🌐 JSON PROMPT built for the plugin:")
    log_debug(json.dumps(prompt, indent=2, ensure_ascii=False))

    if not hasattr(plugin, "generate_response"):
        raise NotImplementedError("generate_response not implemented")

    response = await plugin.generate_response(prompt)

    response_clean = response.strip() if isinstance(response, str) else ""
    if response_clean.startswith("jsonCopyEdit"):
        response_clean = response_clean[len("jsonCopyEdit"):].strip()

    try:
        parsed = json.loads(response_clean)
        if isinstance(parsed, dict) and "type" in parsed and "interface" in parsed and "payload" in parsed:
            log_debug("[plugin] JSON action detected. Executing...")
            await parse_action(parsed, bot, message)
            return
    except Exception as e:
        log_warning(f"[plugin] Response is not a valid action JSON: {e}")

    await bot.send_message(
        chat_id=message.chat.id,
        text=response,
        reply_to_message_id=message.message_id,
    )
    return


def get_supported_models():
    if plugin and hasattr(plugin, "get_supported_models"):
        return plugin.get_supported_models()
    return []


def get_target(message_id):
    if plugin and hasattr(plugin, "get_target"):
        return plugin.get_target(message_id)
    return None

def get_plugin():
    return plugin

