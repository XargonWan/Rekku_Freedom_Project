plugin = None

def load_plugin(name: str):
    global plugin
    if name == "manual":
        from llm_engines.manual import ManualAIPlugin
        plugin = ManualAIPlugin()
    elif name == "openai_chatgpt":
        from llm_engines.openai_chatgpt import OpenAIAIPlugin
        import os
        plugin = OpenAIAIPlugin(api_key=os.getenv("OPENAI_API_KEY"))
    else:
        raise ValueError(f"LLM '{name}' non supportato")
