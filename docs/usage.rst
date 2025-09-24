Usage Overview
==============

.. image:: res/usage_overview.png
   :alt: Usage Overview
   :width: 600px
   :align: center


Rekku operates as a modular AI persona with multiple LLM backends. You can
switch engines on the fly using the ``/llm`` command in your preferred chat
platform. Supported modes include ``manual``, ``openai_chatgpt`` and
``selenium_chatgpt``.

Message forwarding is automatic when Rekku is mentioned or receives a private
message. The ``event`` plugin stores reminders in the configured database and
delivers them when due.

Contextual memory can be toggled with ``/context``. When enabled, the last ten
messages are injected into the prompt sent to the active LLM.

Component Management
--------------------

Rekku automatically discovers and loads components at startup:

**Available Interfaces**
    - ``telegram_bot``: Telegram integration
    - ``discord_interface``: Discord bot support
    - ``reddit_interface``: Reddit posting and monitoring
    - ``webui``: Browser-based interface
    - ``cli``: Command-line interface

**Available Plugins**
    - ``terminal``: Shell command execution
    - ``ai_diary``: Personal memory system
    - ``event``: Scheduled reminders
    - ``weather``: Weather information
    - ``message_plugin``: Cross-platform messaging

**Available LLM Engines**
    - ``openai_chatgpt``: OpenAI API integration
    - ``google_cli``: Google Gemini via CLI
    - ``selenium_chatgpt``: Browser-based ChatGPT
    - ``manual``: Human trainer input

Runtime Commands
----------------

**Engine Management**
    - ``/llm``: List available LLM engines
    - ``/llm <engine_name>``: Switch to a specific engine

**Context Control**
    - ``/context on``: Enable message context injection
    - ``/context off``: Disable message context injection

**System Information**
    - ``/status``: Show system status and active components
    - ``/help``: Display available commands

Configuration
-------------

Components are configured through environment variables in the ``.env`` file:

**Core Settings**
    - ``TRAINER_IDS``: Authorized user IDs for sensitive operations
    - ``NOTIFY_ERRORS_TO_INTERFACES``: Error notification destinations

**Database**
    - ``DB_HOST``, ``DB_USER``, ``DB_PASS``, ``DB_NAME``: MariaDB credentials

**Interface Tokens**
    - ``BOTFATHER_TOKEN``: Telegram bot token
    - ``DISCORD_BOT_TOKEN``: Discord bot token
    - ``REDDIT_*``: Reddit API credentials

**LLM API Keys**
    - ``OPENAI_API_KEY``: OpenAI API access
    - ``GEMINI_API_KEY``: Google Gemini access

The modular architecture ensures that components only load when their required configuration is present, making the system highly flexible and secure.
