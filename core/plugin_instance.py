from core.config import set_current_model, get_current_model
from core.prompt_engine import load_identity_prompt

plugin = None
rekku_identity_prompt = None  # visibile ai plugin o altri moduli

def load_plugin(name: str):
    global plugin, rekku_identity_prompt

    if name == "manual":
        from llm_engines.manual import ManualAIPlugin
        plugin = ManualAIPlugin()
        return  # NON caricare prompt se è manuale

    elif name in ["chatgpt", "openai_chatgpt"]:
        from llm_engines.openai_chatgpt import OpenAIAIPlugin
        import os
        api_key = os.getenv("OPENAI_API_KEY")
        plugin = OpenAIAIPlugin(api_key=api_key)

        # ⚠️ Setta modello di default se non definito
        supported = plugin.get_supported_models()
        if supported:
            current_model = get_current_model()
            if not current_model:
                set_current_model(supported[0])

        rekku_identity_prompt = load_identity_prompt()

    else:
        raise ValueError(f"LLM plugin non valido: {name}")
