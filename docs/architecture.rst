Architecture Overview
=====================

.. image:: res/architecture.png
    :alt: Rekku Architecture Diagram
    :width: 600px
    :align: center


The Rekku Freedom Project is composed of a small set of reusable services.
Each part of the stack can be swapped or extended without touching the rest.

The most relevant packages are:

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


The main entry point is ``main.py`` which initialises the database, loads the
selected LLM engine and starts the configured chat interfaces.

System Flow
-----------

The following diagram shows the typical message path inside the project:

.. graphviz::

   digraph G {
       rankdir=LR;
       User -> Interface -> "Message Queue" -> "Plugin Manager" -> "LLM Engine";
       "LLM Engine" -> "Action Plugins";
       "Action Plugins" -> Interface -> User;
   }

1. Messages arrive via an interface such as Telegram or Reddit.
2. They are pushed onto the asynchronous message queue for processing.
3. The plugin manager routes the message to the active LLM engine.
4. Generated actions are executed by additional plugins or sent back directly
   through the interface.

Interfaces, LLM engines and action plugins all implement thin base classes and
can be replaced independently.
