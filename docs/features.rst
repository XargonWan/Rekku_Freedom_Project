Features
========

.. image:: res/features.png
    :alt: Rekku Features Overview
    :width: 600px
    :align: center


The project exposes several core capabilities that are configured via chat
commands.

Adaptive Intelligence
---------------------

Rekku can operate with different language models:

* ``manual`` – forwards prompts to the trainer for manual replies.
* ``openai_chatgpt`` – uses the OpenAI API.
* ``google_cli`` – queries Google's Gemini models via the ``gemini`` command‑line tool.
* ``selenium_chatgpt`` – drives a real ChatGPT session via Selenium.

Switch between engines at runtime with ``/llm``.

Automatic Forwarding
--------------------

Messages are forwarded to the trainer when Rekku is mentioned, in small groups,
or via private chat.

Chat Link Resolver
------------------

Rekku stores chat and thread identifiers in a central resolver. Interfaces can
target conversations using either numeric IDs or human‑readable names, and the
``update_chat_name`` action refreshes the stored titles when they change.

Multi-Interface Support
-----------------------

Communication is handled by pluggable interfaces. Connectors are available for
Telegram, Discord, Reddit, a local CLI, a web UI and an experimental X (Twitter)
client. Each interface registers its actions independently and can be enabled or
removed without affecting the others.

Plugin Architecture
-------------------

LLM engines and other actions are provided through plugins. Built-in examples
include:

* ``terminal`` – run shell commands from chat.
* ``event`` – schedule reminders stored in the database.
* ``message_plugin`` – send text to any registered interface.
* ``reddit_plugin`` – create posts and comments on Reddit.
* ``time_plugin`` – inject current date, time and location.
* ``weather_plugin`` – add the local weather as static context.
* ``selenium_elevenlabs`` – generate speech audio via ElevenLabs.

Context Memory
--------------

With ``/context`` enabled, the last ten messages are injected into prompts.

Miscellaneous Commands
----------------------

Other useful commands include ``/say`` to send messages to any chat, ``/block``
and ``/unblock`` for user management, ``/model`` to switch models, and
``/last_chats`` to list recent conversations.
