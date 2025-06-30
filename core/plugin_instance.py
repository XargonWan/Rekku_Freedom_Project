# core/plugin_instance.py

import importlib
from core.config import set_current_model, get_current_model
from core.prompt_engine import load_identity_prompt
import json
from core.prompt_engine import build_json_prompt

plugin = None
rekku_identity_prompt = None  # visibile ai plugin o altri moduli

def load_plugin(name: str, notify_fn=None):
    global plugin, rekku_identity_prompt

    try:
        module = importlib.import_module(f"llm_engines.{name}")
        print(f"[DEBUG] Modulo llm_engines.{name} importato con successo.")
    except ModuleNotFoundError as e:
        print(f"[ERROR] Impossibile importare llm_engines.{name}: {e}")
        raise ValueError(f"LLM plugin non valido: {name}")

    if not hasattr(module, "PLUGIN_CLASS"):
        raise ValueError(f"Il plugin `{name}` non definisce `PLUGIN_CLASS`.")

    plugin_class = getattr(module, "PLUGIN_CLASS")

    # 👇 Passa notify_fn solo se il costruttore la accetta
    try:
        plugin = plugin_class(notify_fn=notify_fn)
    except TypeError:
        plugin = plugin_class()  # fallback per plugin legacy

    print(f"[DEBUG] Plugin inizializzato: {plugin.__class__.__name__}")

    if name not in ["manual"]:
        rekku_identity_prompt = load_identity_prompt()
        print("[DEBUG] Prompt identitario caricato.")

    if hasattr(plugin, "get_supported_models"):
        try:
            models = plugin.get_supported_models()
            if models:
                current = get_current_model()
                if not current:
                    set_current_model(models[0])
                    print(f"[DEBUG] Modello predefinito impostato: {models[0]}")
        except Exception as e:
            print(f"[WARNING] Errore durante il setup del modello: {e}")

async def handle_incoming_message(bot, message, context_memory):
    if plugin is None:
        raise RuntimeError("Nessun plugin LLM caricato.")

    # ✅ Costruisce prompt JSON standard da context + memorie + messaggio
    prompt = await build_json_prompt(message, context_memory)

    # 🧠 DEBUG: stampa il prompt globale
    print("[DEBUG] 🌐 PROMPT JSON costruito per il plugin:")
    print(json.dumps(prompt, indent=2, ensure_ascii=False))

    # 🔁 Passa prompt già costruito al plugin attivo
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

