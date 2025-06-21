import os
from dotenv import load_dotenv

load_dotenv()
OWNER_ID = int(os.getenv("OWNER_ID", "123456789"))
BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
BOT_USERNAME = "Rekku_the_bot"