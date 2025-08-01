Plugins
=======

The project includes several optional plugins that implement additional actions
or storage.

Terminal
--------

``plugins/terminal`` exposes a persistent shell accessible from chat. Commands
sent to the bot are executed in a background ``/bin/bash`` process and the
output is returned.

Bash
----

``bash_plugin`` executes one-off shell commands and returns the output.
Every command is also reported to the configured ``TRAINER_ID`` so that
the trainer can audit activity.

Event
-----

The ``event`` plugin stores scheduled reminders in a MariaDB table. A background
scheduler checks for due events and sends them back to Rekku when the time comes.

Message
-------

``message_plugin`` handles text message actions across multiple interfaces. It is
used internally by other plugins to send replies.

Reddit Interface
----------------

``reddit_interface`` allows Rekku to read posts, handle direct messages and
manage subreddit subscriptions. Credentials for Reddit must be provided in the
``.env`` file.

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
to interact with language model prompts.  At minimum expose a ``PLUGIN_CLASS``
variable so the loader can locate your class.

.. code-block:: python

   from core.ai_plugin_base import AIPluginBase

   class MyActionPlugin(AIPluginBase):
       def handle_incoming_message(self, bot, message, prompt):
           ...  # perform work

   PLUGIN_CLASS = MyActionPlugin

LLM Engine
~~~~~~~~~~

LLM engines live in ``llm_engines/`` and also subclass ``AIPluginBase``.  They
must implement ``generate_response`` to call the external model and return text
or JSON actions.  After placing the module, select it at runtime using the
``/llm`` command.

Interface
~~~~~~~~~

Interfaces provide ingress/egress channels for messages.  A minimal interface
exposes ``start()`` to begin listening and registers itself using
``register_interface`` from ``core.interfaces``.

.. code-block:: python

   from core.interfaces import register_interface

   class MyInterface:
       async def start(self):
           ...
           register_interface("myiface", self)

Interfaces typically forward incoming messages to ``plugin_instance.handle_incoming_message``
so that the active LLM engine can process them.
