import asyncio
from interface.telegram_bot import start_bot
from core.db import init_db
from core.blocklist import init_blocklist_table
from core.presence_manager import presence_loop

async def main():
    # Inizializzazione DB e strutture
    init_db()
    init_blocklist_table()

    # Avvio loop presenza + bot Telegram
    asyncio.create_task(presence_loop())
    await start_bot()

if __name__ == "__main__":
    asyncio.run(main())
