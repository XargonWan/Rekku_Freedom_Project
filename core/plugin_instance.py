# core/plugin_instance.py

import importlib
import os
from core.config import set_current_model, get_current_model
from core.prompt_engine import load_identity_prompt

plugin = None
rekku_identity_prompt = None  # visibile ai plugin o altri moduli

def load_plugin(name: str):
    """
    Carica dinamicamente un plugin dalla directory llm_engines/
    Il plugin deve definire una classe `PLUGIN_CLASS`.
    """
    global plugin, rekku_identity_prompt

    try:
        module = importlib.import_module(f"llm_engines.{name}")
    except ModuleNotFoundError:
        raise ValueError(f"LLM plugin non valido: {name}")

    if not hasattr(module, "PLUGIN_CLASS"):
        raise ValueError(f"Il plugin `{name}` non definisce `PLUGIN_CLASS`.")

    plugin_class = getattr(module, "PLUGIN_CLASS")
    plugin = plugin_class()

    # Solo alcuni plugin richiedono il prompt identitario
    if name not in ["manual"]:
        rekku_identity_prompt = load_identity_prompt()

    # Imposta modello di default se serve
    if hasattr(plugin, "get_supported_models"):
        models = plugin.get_supported_models()
        if models:
            current = get_current_model()
            if not current:
                set_current_model(models[0])
