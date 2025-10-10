Installation
============

.. image:: res/installation.png
   :alt: Installation steps
   :width: 600px
   :align: center


The project can be deployed using Docker. Ensure you have `docker` and
`docker compose` installed on your machine. Copy `.env.example` to `.env`
and adjust the values for your environment. Set ``BOTFATHER_TOKEN`` and
optionally configure ``NOTIFY_ERRORS_TO_INTERFACES`` with comma-separated
``interface:trainer_id`` pairs to select which interfaces receive error
notifications.

Build and start the services:

.. code-block:: bash

   docker compose up

A MariaDB instance is started automatically and a daily backup container
writes dumps to ``./backups/``.

Modular Architecture
--------------------

Synthetic Heart follows a modular architecture where components are automatically discovered and loaded:

**Core System**
    Handles message processing, action execution, and component orchestration.

**Interfaces** (``interface/``)
    Platform integrations (Telegram, Discord, Reddit, etc.) that handle communication.

**Plugins** (``plugins/``)
    Action providers that extend functionality (terminal, weather, AI diary, etc.).

**LLM Engines** (``llm_engines/``)
    AI backend implementations (OpenAI, Google Gemini, manual input, etc.).

This design ensures that new features can be added by simply placing compatible modules in the appropriate directories without modifying the core codebase.
