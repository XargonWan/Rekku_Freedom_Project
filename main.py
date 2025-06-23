# main.py

from interface.telegram_bot import start_bot
from core.db import init_db
from core.blocklist import init_blocklist_table

if __name__ == "__main__":
    init_db()
    init_blocklist_table()
    start_bot()
