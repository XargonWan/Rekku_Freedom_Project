import os
from core.db import init_db
from core.blocklist import init_blocklist_table
from core.config import get_active_llm
from core.plugin_instance import load_plugin

if __name__ == "__main__":
    # Initialize DB and tables
    init_db()
    init_blocklist_table()

    # 🔄 Load the active LLM plugin from DB (without notify_fn, will be set later by the bot)
    llm_name = get_active_llm()
    print(f"[DEBUG/main] Active plugin to load: {llm_name}")
    load_plugin(llm_name)

    # 🌐 Show where the Webtop/VNC interface is available
    host = os.environ.get("WEBVIEW_HOST", "localhost")
    port = os.environ.get("WEBVIEW_PORT", "3000")
    print(f"[INFO/vnc] Webtop GUI available at: http://{host}:{port}")

    # ✅ Start the bot
    from interface.telegram_bot import start_bot
    start_bot()
