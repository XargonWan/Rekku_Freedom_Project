from core.config import set_current_model, get_current_model, OWNER_ID

plugin = None

def load_plugin(name: str):
    global plugin

    if name == "manual":
        from llm_engines.manual import ManualAIPlugin
        plugin = ManualAIPlugin()

    elif name == "chatgpt" or name == "openai_chatgpt":
        from llm_engines.openai_chatgpt import OpenAIAIPlugin
        import os
        api_key = os.getenv("OPENAI_API_KEY")
        plugin = OpenAIAIPlugin(api_key=api_key)

        # ⚠️ Imposta modello di default globale se non già settato
        supported = plugin.get_supported_models()
        if supported:
            current_model = get_current_model()
            if not current_model:
                set_current_model(supported[0])

    else:
        raise ValueError(f"LLM plugin non valido: {name}")
