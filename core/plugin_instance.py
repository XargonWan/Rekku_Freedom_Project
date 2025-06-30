# core/plugin_instance.py

import importlib
from core.config import set_current_model, get_current_model, set_active_llm, get_active_llm
from core.prompt_engine import load_identity_prompt, build_json_prompt
import json

plugin = None
rekku_identity_prompt = None  # visibile ai plugin o altri moduli

def load_plugin(name: str, notify_fn=None):
    global plugin, rekku_identity_prompt, _active_llm

    try:
        current = get_active_llm()
        if current == name and plugin is not None:
            print(f"[DEBUG/plugin] ⚠️ Plugin già caricato: {plugin.__class__.__name__}")
            return
        else:
            print(f"[DEBUG/plugin] 🔄 Cambio plugin da {current} a {name}")
    except Exception:
        print("[DEBUG/plugin] Nessun plugin attivo, procedo con caricamento.")

    try:
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
    _active_llm = name
    print(f"[DEBUG/plugin] Plugin inizializzato: {plugin.__class__.__name__}")

    if name != "manual":
        rekku_identity_prompt = load_identity_prompt()
        print("[DEBUG/plugin] Prompt identitario caricato.")

    # ✅ Solo ora salviamo nel DB
    set_active_llm(name)
    print(f"[DEBUG/config] 💾 Salvato plugin attivo nel DB: {name}")


async def handle_incoming_message(bot, message, context_memory):
    if plugin is None:
        raise RuntimeError("Nessun plugin LLM caricato.")

    prompt = await build_json_prompt(message, context_memory)

    print("[DEBUG] 🌐 PROMPT JSON costruito per il plugin:")
    print(json.dumps(prompt, indent=2, ensure_ascii=False))

    return await plugin.handle_incoming_message(bot, message, prompt)


def get_supported_models():
    if plugin is None:
        raise RuntimeError("Plugin non caricato.")
    if hasattr(plugin, "get_supported_models"):
        return plugin.get_supported_models()
    return []


def get_current_model():
    if plugin is None:
        raise RuntimeError("Plugin non caricato.")
    if hasattr(plugin, "get_current_model"):
        return plugin.get_current_model()
    return None


def set_current_model(name):
    if plugin is None:
        raise RuntimeError("Plugin non caricato.")
    if hasattr(plugin, "set_current_model"):
        return plugin.set_current_model(name)
    raise NotImplementedError("Il plugin non supporta il cambio modello.")


def get_target(message_id):
    if plugin is None:
        return None
    if hasattr(plugin, "get_target"):
        return plugin.get_target(message_id)
    return None
