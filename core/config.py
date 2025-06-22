import os
from dotenv import load_dotenv

load_dotenv()
OWNER_ID = int(os.getenv("OWNER_ID", "123456789"))
BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
BOT_USERNAME = "Rekku_the_bot"
LLM_MODE = os.getenv("LLM_MODE", "manual")  # "manual" oppure "chatgpt"

# Modalit� LLM: letta da file o da variabile d'ambiente (priorit� a file)
LLM_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "llm_mode.txt")

def get_active_llm():
    if os.path.exists(LLM_CONFIG_PATH):
        with open(LLM_CONFIG_PATH, "r") as f:
            return f.read().strip()
    return os.getenv("LLM_MODE", "manual")

def set_active_llm(mode: str):
    with open(LLM_CONFIG_PATH, "w") as f:
        f.write(mode)

def list_available_llms():
    engines_dir = os.path.join(os.path.dirname(__file__), "../llm_engines")
    entries = []

    for fname in os.listdir(engines_dir):
        if fname.endswith(".py") and not fname.startswith("__"):
            entries.append(fname.removesuffix(".py"))

    return sorted(entries)