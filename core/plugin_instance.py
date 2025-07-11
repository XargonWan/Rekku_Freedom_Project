# core/plugin_instance.py

from core.config import get_active_llm, set_active_llm
from core.prompt_engine import load_identity_prompt
import json
from core.prompt_engine import build_json_prompt
import asyncio

plugin = None
rekku_identity_prompt = None

def load_plugin(name: str, notify_fn=None):
    global plugin, rekku_identity_prompt

    # 🔁 If already loaded but different, replace it or update notify_fn
    if plugin is not None:
        current_plugin_name = plugin.__class__.__module__.split(".")[-1]
        if current_plugin_name != name:
            print(f"[DEBUG/plugin] 🔄 Cambio plugin da {current_plugin_name} a {name}")
        else:
            # 🔁 Even if it's the same plugin, update notify_fn if provided
            if notify_fn and hasattr(plugin, "set_notify_fn"):
                try:
                    plugin.set_notify_fn(notify_fn)
                    print("[DEBUG/plugin] ✅ notify_fn updated dynamically")
                except Exception as e:
                    print(f"[ERROR/plugin] ❌ Unable to update notify_fn: {e}")
            else:
                print(f"[DEBUG/plugin] ⚠️ Plugin already loaded: {plugin.__class__.__name__}")
            return

    try:
        import importlib
        module = importlib.import_module(f"llm_engines.{name}")
        print(f"[DEBUG/plugin] Module llm_engines.{name} imported successfully.")
    except ModuleNotFoundError as e:
        print(f"[ERROR/plugin] ❌ Unable to import llm_engines.{name}: {e}")
        raise ValueError(f"Invalid LLM plugin: {name}")

    if not hasattr(module, "PLUGIN_CLASS"):
        raise ValueError(f"Plugin `{name}` does not define `PLUGIN_CLASS`.")

    plugin_class = getattr(module, "PLUGIN_CLASS")

    if notify_fn:
        print("[DEBUG/plugin] notify_fn function passed to plugin.")
    else:
        print("[DEBUG/plugin] ⚠️ No notify_fn function provided.")

    try:
        plugin_args = plugin_class.__init__.__code__.co_varnames
        if "notify_fn" in plugin_args:
            plugin_instance = plugin_class(notify_fn=notify_fn)
        else:
            plugin_instance = plugin_class()
    except Exception as e:
        print(f"[ERROR/plugin] ❌ Error during plugin initialization: {e}")
        raise

    plugin = plugin_instance
    print(f"[DEBUG/plugin] Plugin initialized: {plugin.__class__.__name__}")

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
                else:
                    asyncio.run(start_fn())
            else:
                start_fn()
            print("[DEBUG/plugin] Plugin start executed.")
        except Exception as e:
            print(f"[ERROR/plugin] Error during plugin start: {e}")

    if name != "manual":
        rekku_identity_prompt = load_identity_prompt()
        print("[DEBUG/plugin] Identity prompt loaded.")

    # Default model
    if hasattr(plugin, "get_supported_models"):
        try:
            models = plugin.get_supported_models()
            if models:
                from config import get_current_model, set_current_model
                current = get_current_model()
                if not current:
                    set_current_model(models[0])
                    print(f"[DEBUG/plugin] Default model set: {models[0]}")
        except Exception as e:
            print(f"[WARNING/plugin] Error during model setup: {e}")

    set_active_llm(name)

async def handle_incoming_message(bot, message, context_memory):
    if plugin is None:
        raise RuntimeError("No LLM plugin loaded.")

    prompt = await build_json_prompt(message, context_memory)

    print("[DEBUG] \U0001f310 JSON PROMPT built for the plugin:")
    print(json.dumps(prompt, indent=2, ensure_ascii=False))

    return await plugin.handle_incoming_message(bot, message, prompt)


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

