# core/plugin_instance.py

from core.config import get_active_llm, set_active_llm
from core.prompt_engine import load_identity_prompt
from core.prompt_engine import build_json_prompt
import asyncio
from types import SimpleNamespace
from datetime import datetime
from core.logging_utils import log_debug, log_info, log_warning, log_error
from core.action_parser import parse_action
from core.json_utils import dumps as json_dumps, sanitize_for_json

# Plugin gestito centralmente in initialize_core_components
plugin = None
rekku_identity_prompt = None

async def load_plugin(name: str, notify_fn=None):
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

    await set_active_llm(name)

async def handle_incoming_message(bot, message, context_memory_or_prompt, interface: str = None):
    """Process incoming messages or pre-built prompts."""

    if plugin is None:
        raise RuntimeError("No LLM plugin loaded.")

    if message is None and isinstance(context_memory_or_prompt, dict):
        prompt = context_memory_or_prompt
        message = SimpleNamespace(
            chat_id="TARDIS / system / events",
            message_id=int(datetime.utcnow().timestamp() * 1000) % 1_000_000,
            text=prompt.get("input", {}).get("payload", {}).get("description", ""),
            date=datetime.utcnow(),
            from_user=SimpleNamespace(id=0, full_name="system", username="system"),
            reply_to_message=None,
            chat=SimpleNamespace(id="TARDIS / system / events", type="private"),
        )
        log_debug("[plugin_instance] Handling pre-built event prompt")
    else:
        message_text = getattr(message, "text", "")
        log_debug(f"[plugin_instance] Received message: {message_text}")
        log_debug(f"[plugin_instance] Context memory: {context_memory_or_prompt}")
        user_id = message.from_user.id if message.from_user else "unknown"
        interface_name = interface if interface else (
            bot.get_interface_id() if hasattr(bot, "get_interface_id") else bot.__class__.__name__
        )
        log_debug(
            f"[plugin] Incoming for {plugin.__class__.__name__}: chat_id={message.chat_id}, user_id={user_id}, text={message_text!r} via {interface_name}"
        )
        if isinstance(context_memory_or_prompt, str):
            try:
                import json

                prompt = json.loads(context_memory_or_prompt)
            except Exception as e:
                log_warning(f"[plugin_instance] Failed to parse direct prompt: {e}")
                prompt = await build_json_prompt(message, {}, interface_name)
        else:
            prompt = await build_json_prompt(message, context_memory_or_prompt, interface_name)

    prompt = sanitize_for_json(prompt)
    log_debug("🌐 JSON PROMPT built for the plugin:")
    try:
        log_debug(json_dumps(prompt))
    except Exception as e:
        log_error(f"Failed to serialize prompt: {e}")

    # Trace handoff to LLM plugin
    try:
        log_info(f"[flow] -> LLM plugin: handing off chat_id={getattr(message, 'chat_id', None)} interface={interface} prompt_len={len(json_dumps(prompt)) if isinstance(prompt, (dict, list)) else len(str(prompt))}")
    except Exception:
        log_info(f"[flow] -> LLM plugin: handing off chat_id={getattr(message, 'chat_id', None)} interface={interface}")

    try:
        result = await plugin.handle_incoming_message(bot, message, prompt)
        # Log that plugin finished processing
        try:
            log_info(f"[flow] <- LLM plugin: completed for chat_id={getattr(message, 'chat_id', None)} result_type={type(result)}")
        except Exception:
            log_info(f"[flow] <- LLM plugin: completed for chat_id={getattr(message, 'chat_id', None)}")
        return result
    except Exception as e:
        log_error(f"[plugin_instance] LLM plugin raised an exception: {e}")
        raise


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

def load_generic_plugin(name: str, notify_fn=None):
    global plugin

    # 🔁 Se il plugin è già caricato, verifica se è lo stesso
    if plugin is not None:
        current_plugin_name = plugin.__class__.__module__.split(".")[-1]
        if current_plugin_name == name:
            log_debug(f"[plugin] ⚠️ Plugin già caricato: {plugin.__class__.__name__}")
            return

    try:
        import importlib
        module = importlib.import_module(f"plugins.{name}_plugin")
        log_debug(f"[plugin] Modulo plugins.{name}_plugin importato con successo.")
    except ModuleNotFoundError as e:
        log_error(f"[plugin] ❌ Impossibile importare plugins.{name}_plugin: {e}", e)
        raise ValueError(f"Plugin non valido: {name}")

    if not hasattr(module, "PLUGIN_CLASS"):
        raise ValueError(f"Il plugin `{name}` non definisce `PLUGIN_CLASS`.")

    plugin_class = getattr(module, "PLUGIN_CLASS")

    try:
        plugin = plugin_class(notify_fn=notify_fn) if notify_fn else plugin_class()
        log_debug(f"[plugin] Plugin inizializzato: {plugin.__class__.__name__}")
    except Exception as e:
        log_error(f"[plugin] ❌ Errore durante l'inizializzazione del plugin: {e}", e)
        raise

    if hasattr(plugin, "start"):
        try:
            if asyncio.iscoroutinefunction(plugin.start):
                loop = asyncio.get_running_loop()
                if loop and loop.is_running():
                    loop.create_task(plugin.start())
                    log_debug("[plugin] Plugin avviato nel loop esistente.")
                else:
                    log_debug("[plugin] Nessun loop in esecuzione; il plugin sarà avviato successivamente.")
            else:
                plugin.start()
                log_debug("[plugin] Plugin avviato.")
        except Exception as e:
            log_error(f"[plugin] ❌ Errore durante l'avvio del plugin: {e}", e)

