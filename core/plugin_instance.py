# core/plugin_instance.py

from core.config import get_active_llm, set_active_llm
from core.prompt_engine import load_identity_prompt
import json
from core.prompt_engine import build_json_prompt

plugin = None
rekku_identity_prompt = None

def load_plugin(name: str, notify_fn=None):
    global plugin, rekku_identity_prompt

    # 🔁 Se già caricato ma diverso, sostituiscilo o aggiorna notify_fn
    if plugin is not None:
        current_plugin_name = plugin.__class__.__module__.split(".")[-1]
        if current_plugin_name != name:
            print(f"[DEBUG/plugin] 🔄 Cambio plugin da {current_plugin_name} a {name}")
        else:
            # 🔁 Anche se è lo stesso plugin, aggiorna notify_fn se fornita
            if notify_fn and hasattr(plugin, "set_notify_fn"):
                try:
                    plugin.set_notify_fn(notify_fn)
                    print("[DEBUG/plugin] ✅ notify_fn aggiornata dinamicamente")
                except Exception as e:
                    print(f"[ERROR/plugin] ❌ Impossibile aggiornare notify_fn: {e}")
            else:
                print(f"[DEBUG/plugin] ⚠️ Plugin già caricato: {plugin.__class__.__name__}")
            return

    try:
        import importlib
        module = importlib.import_module(f"llm_engines.{name}")
        print(f"[DEBUG/plugin] Modulo llm_engines.{name} importato con successo.")
    except ModuleNotFoundError as e:
        print(f"[ERROR/plugin] ❌ Impossibile importare llm_engines.{name}: {e}")
        raise ValueError(f"LLM plugin non valido: {name}")

    if not hasattr(module, "PLUGIN_CLASS"):
        raise ValueError(f"Il plugin `{name}` non definisce `PLUGIN_CLASS`.")

    plugin_class = getattr(module, "PLUGIN_CLASS")

    if notify_fn:
        print("[DEBUG/plugin] Funzione notify_fn passata al plugin.")
    else:
        print("[DEBUG/plugin] ⚠️ Nessuna funzione notify_fn fornita.")

    try:
        plugin_args = plugin_class.__init__.__code__.co_varnames
        if "notify_fn" in plugin_args:
            plugin_instance = plugin_class(notify_fn=notify_fn)
        else:
            plugin_instance = plugin_class()
    except Exception as e:
        print(f"[ERROR/plugin] ❌ Errore nell'inizializzazione del plugin: {e}")
        raise

    plugin = plugin_instance
    print(f"[DEBUG/plugin] Plugin inizializzato: {plugin.__class__.__name__}")

    if name != "manual":
        rekku_identity_prompt = load_identity_prompt()
        print("[DEBUG/plugin] Prompt identitario caricato.")

    # Modello predefinito
    if hasattr(plugin, "get_supported_models"):
        try:
            models = plugin.get_supported_models()
            if models:
                from config import get_current_model, set_current_model
                current = get_current_model()
                if not current:
                    set_current_model(models[0])
                    print(f"[DEBUG/plugin] Modello predefinito impostato: {models[0]}")
        except Exception as e:
            print(f"[WARNING/plugin] Errore durante il setup del modello: {e}")

    set_active_llm(name)

async def handle_incoming_message(bot, message, context_memory):
    if plugin is None:
        raise RuntimeError("Nessun plugin LLM caricato.")

    prompt = await build_json_prompt(message, context_memory)

    print("[DEBUG] \U0001f310 PROMPT JSON costruito per il plugin:")
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

