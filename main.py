from interface.telegram_bot import start_bot
from core.db import init_db

if __name__ == "__main__":
    init_db()
    start_bot()

