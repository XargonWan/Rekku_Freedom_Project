Interfaces
==========

This guide explains how to add a new chat interface and expose its actions to the
core system.

.. note::
   Full interface documentation is available on the project's `Read the Docs`_ wiki.

.. _Read the Docs: https://rekku.readthedocs.io

Available Interfaces
--------------------

The repository currently includes the following interfaces:

* ``cli`` – local command-line interface (no configuration).
* ``discord_interface`` – Discord bot connector.  Set ``DISCORD_BOT_TOKEN`` in ``.env``.
* ``reddit_interface`` – asynchronous Reddit client.  Requires ``REDDIT_CLIENT_ID``, ``REDDIT_CLIENT_SECRET``, ``REDDIT_USERNAME``, ``REDDIT_PASSWORD`` and ``REDDIT_USER_AGENT``.
* ``telegram_bot`` – Telegram bot interface.  Provide ``BOTFATHER_TOKEN`` (or ``TELEGRAM_TOKEN``) and trainer ID ``TELEGRAM_TRAINER_ID``.
* ``telethon_userbot`` – userbot using Telethon.  Set ``API_ID``, ``API_HASH`` and ``SESSION``.
* ``webui`` – FastAPI-based web interface.  ``WEBUI_HOST`` and ``WEBUI_PORT`` control binding.
* ``x_interface`` – experimental X (Twitter) integration.  Configure ``X_USERNAME`` for timeline features.

Discord Bot Setup
-----------------

Follow these steps to connect Rekku to Discord:

1. Create an application in the `Discord Developer Portal <https://discord.com/developers/applications>`_.
2. Under **Bot**, add a bot and copy its token.
3. Enable the **Message Content Intent** and any other privileged intents your bot needs.
4. In **OAuth2 → URL Generator**, select the ``bot`` scope and invite the bot to your server with the desired permissions.
5. Store the token in an ``.env`` file or environment variable named ``DISCORD_BOT_TOKEN``.
6. Start Rekku (for example, ``python main.py``); the ``discord_interface`` module loads automatically and uses the token to connect.

1. **Create the module**
   Place a new ``*.py`` file under the ``interface/`` directory.  The core now
   imports all modules in ``interface/``, ``plugins/`` and ``llm_engines/``
   recursively, so no special naming convention is required. Removing the file
   later cleanly removes the interface from Rekku.

2. **Declare actions**
   Implement ``get_supported_actions`` on the interface class.  The method should
   return a mapping of action names to a schema describing the required and
   optional fields.

3. **Optional prompt instructions**
   If the LLM needs extra guidance for an action, implement
   ``get_prompt_instructions(action_type)`` and return a dictionary of prompt
   snippets.

4. **Register the interface**
   When the interface starts, use ``register_interface`` to store the instance
   and ``core_initializer.register_interface`` to mark it active.

.. code-block:: python

   from core.core_initializer import core_initializer, register_interface

   class MyInterface:
       @staticmethod
       def get_interface_id():
           return "myiface"

       @staticmethod
       def get_supported_actions():
           return {
               "message_myiface": {
                   "required_fields": ["text"],
                   "optional_fields": [],
                   "description": "Send a message over MyInterface.",
               }
           }

       async def start(self):
           register_interface("myiface", self)
           core_initializer.register_interface("myiface")

   INTERFACE_CLASS = MyInterface

With these pieces in place the core initializer will automatically collect the
interface's actions and make them available to the LLM.
