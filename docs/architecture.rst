Architecture Overview
=====================

The codebase is organized into a few key packages:

``core``
    Core services such as the message queue, context management and database
    access.

``interface``
    Chat interfaces for Telegram, Discord and Telethon userbot.

``llm_engines``
    Backend implementations for different language models.

``plugins``
    Action plugins like ``terminal`` and ``event`` that extend Rekku's
    behaviour.

The main entry point is ``main.py`` which initialises the database and starts the
Telegram bot along with the selected LLM engine.
