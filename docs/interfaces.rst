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
   Implement ``get_action_types`` and ``get_supported_actions`` on the
   interface class. ``get_action_types`` returns a list of fully qualified
   action names (e.g. ``message_discord``) while ``get_supported_actions``
   provides a schema describing the required and optional fields.

   Interfaces may also expose ``get_supported_action_types`` to advertise
   generic capabilities such as ``message``. This lets the action parser map
   high-level types to a concrete interface implementation.

3. **Prompt instructions and validation**
   If the LLM needs extra guidance for an action, implement
   ``get_prompt_instructions(action_type)`` and return a dictionary of prompt
   snippets.  ``validate_payload`` can be used to sanity-check payloads before
   the action is executed.

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
       def get_supported_action_types():
           return ["message"]

       @staticmethod
       def get_action_types():
           return ["message_myiface"]

       @staticmethod
       def get_supported_actions():
           return {
               "message_myiface": {
                   "description": "Send a message over MyInterface.",
                   "required_fields": ["text", "target"],
                   "optional_fields": [],
               }
           }

       @staticmethod
       def get_prompt_instructions(action_name):
           if action_name == "message_myiface":
               return {
                   "description": "Send a message over MyInterface.",
                   "payload": {
                       "text": {"type": "string", "description": "Message text"},
                       "target": {"type": "string", "description": "Destination"},
                   },
               }
           return {}

       @staticmethod
       def validate_payload(action_type, payload):
           errors = []
           if action_type == "message_myiface":
               if "text" not in payload:
                   errors.append("payload.text is required")
               if "target" not in payload:
                   errors.append("payload.target is required")
           return errors

       async def start(self):
           register_interface("myiface", self)
           core_initializer.register_interface("myiface")

   INTERFACE_CLASS = MyInterface

With these pieces in place the core initializer will automatically collect the
interface's actions and make them available to the LLM.  For complete
implementations, see ``interface/telegram_bot.py`` and
``interface/discord_interface.py`` in the repository.
