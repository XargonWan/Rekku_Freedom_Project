Plugins
=======

.. image:: res/plugins.png
    :alt: Rekku plugin architecture diagram
    :width: 600px
    :align: center


The project includes several optional plugins that implement additional actions
or storage.

.. note::
   For a complete developer guide, see the project's `Read the Docs`_ wiki.

.. _Read the Docs: https://rekku.readthedocs.io

Available Action Plugins
------------------------

* ``bio_manager`` – manage persistent user biographies. Uses database settings ``DB_HOST``, ``DB_USER``, ``DB_PASS`` and ``DB_NAME``.
* ``event`` – schedule and deliver reminders. Requires ``DB_HOST``, ``DB_PORT``, ``DB_USER``, ``DB_PASS``, ``DB_NAME`` and optional ``CORRECTOR_RETRIES``.
* ``message_plugin`` – send text across registered interfaces (no configuration).
* ``reddit_plugin`` – submit posts and comments to Reddit. Requires ``REDDIT_CLIENT_ID``, ``REDDIT_CLIENT_SECRET``, ``REDDIT_USERNAME``, ``REDDIT_PASSWORD`` and ``REDDIT_USER_AGENT``.
* ``selenium_elevenlabs`` – generate speech audio with ElevenLabs. Set ``ELEVENLABS_EMAIL`` and ``ELEVENLABS_PASSWORD`` (``REKKU_SELENIUM_HEADLESS`` controls headless mode).
* ``terminal`` – run shell commands or interactive sessions. Uses ``TELEGRAM_TRAINER_ID`` to authorize access.
* ``time_plugin`` – inject current time and location (no configuration).
* ``weather_plugin`` – provide weather info as static context. Optional ``WEATHER_FETCH_TIME`` sets refresh interval.

Terminal
--------

``plugins/terminal`` exposes a persistent shell accessible from chat. Commands
sent to the bot are executed in a background ``/bin/bash`` process and the
output is returned.

.. note::
   Access is limited to the trainer ID configured via ``TELEGRAM_TRAINER_ID``.

Event
-----

The ``event`` plugin stores scheduled reminders in a MariaDB table. A background
scheduler checks for due events and sends them back to Rekku when the time comes.

.. note::
   Requires database credentials (``DB_HOST``, ``DB_PORT``, ``DB_USER``, ``DB_PASS``, ``DB_NAME``).

All Python modules under ``plugins/``, ``llm_engines/`` and ``interface/`` are
imported recursively on startup. Plugin files no longer need a special naming
scheme. Each plugin registers itself using ``register_plugin`` and notifies the
core initializer with ``core_initializer.register_plugin``.

Reddit Interface
----------------

``reddit_interface`` allows Rekku to read posts, handle direct messages and
manage subreddit subscriptions. Credentials for Reddit must be provided in the
``.env`` file (``REDDIT_CLIENT_ID``, ``REDDIT_CLIENT_SECRET``, ``REDDIT_USERNAME``,
``REDDIT_PASSWORD`` and ``REDDIT_USER_AGENT``).

Reddit Actions
--------------

The ``reddit`` plugin exposes actions for creating posts and comments via
``asyncpraw``.

Developing Plugins
------------------

The plugin system is intentionally lightweight.  New functionality can be
introduced by implementing small classes that inherit from one of the base
types located in ``core``.

Action Plugin
~~~~~~~~~~~~~

Action plugins process the actions returned by an LLM.  Create a new file under
``plugins/`` and subclass ``PluginBase`` or ``AIPluginBase`` if the plugin needs
to interact with language model prompts.  Each plugin is self-contained; removing
the file removes the action from the system.  To participate in the action
registry the plugin must expose a ``PLUGIN_CLASS`` variable and implement
``get_supported_actions``.  Optional prompt guidance can be provided via
``get_prompt_instructions``.

.. code-block:: python

   from core.ai_plugin_base import AIPluginBase
   from core.core_initializer import core_initializer, register_plugin

   class MyActionPlugin(AIPluginBase):
       def __init__(self):
           register_plugin("myplugin", self)
           core_initializer.register_plugin("myplugin")

       def get_supported_actions(self):
           return {
               "my_action": {
                   "required_fields": ["value"],
                   "optional_fields": [],
                   "description": "Do something with 'value'",
               }
           }

       def get_prompt_instructions(self, action_type):
           if action_type == "my_action":
               return {"system": "Describe how to call my_action"}
           return {}

       def handle_incoming_message(self, bot, message, prompt):
           ...  # perform work

   PLUGIN_CLASS = MyActionPlugin

Plugin Flow
-----------

The following diagram and steps illustrate how plugins interact with the system:

.. graphviz::

    digraph plugin_flow {
         rankdir=LR;
         node [shape=box, style=rounded];
         A [label="1. Plugin registers\n→ ACTIVE_INTERFACES"];
         B [label="2. Plugin defines actions\n→ available_actions"];
         C [label="3. Plugin defines instructions\n→ action_instructions"];
         D [label="4. LLM uses available_actions\nto generate JSON"];
         E [label="5. Action parser finds\ncorresponding plugin"];
         F [label="6. Plugin executes logic"];

         A -> B -> C -> D -> E -> F;
    }

**Step-by-step flow:**

1. The plugin registers itself via ``register_plugin``, adding an entry to ``PLUGIN_REGISTRY``.
2. The plugin defines its available actions, which are collected in ``available_actions``.
3. The plugin provides action instructions, stored in ``action_instructions``.
4. The LLM uses ``available_actions`` to generate a JSON action request.
5. The action parser dynamically locates the appropriate plugin for the requested action.
6. The plugin executes its logic to handle the action.

LLM Engine
~~~~~~~~~~

LLM engines live in ``llm_engines/`` and also subclass ``AIPluginBase``.  They
must implement ``generate_response`` to call the external model and return text
or JSON actions.  After placing the module, select it at runtime using the
``/llm`` command.

Interface
~~~~~~~~~

Interfaces provide ingress/egress channels for messages and can also expose
their own actions.  A minimal interface defines action schemas, calls
``register_interface`` to make itself discoverable and then notifies the core
initializer that it is active.

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

Interfaces typically forward incoming messages to
``plugin_instance.handle_incoming_message`` so that the active LLM engine can
process them.
