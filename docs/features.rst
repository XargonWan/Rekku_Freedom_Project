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
* ``selenium_chatgpt`` – drives a real ChatGPT session via Selenium.

Switch between engines at runtime with ``/llm``.

Automatic Forwarding
--------------------

Messages are forwarded to the trainer when Rekku is mentioned, in small groups,
or via private chat.

Plugin Architecture
-------------------

LLM engines and other actions are provided through plugins. Available action
plugins include ``terminal`` for shell access and ``event`` for scheduled
reminders.

Context Memory
--------------

With ``/context`` enabled, the last ten messages are injected into prompts.

Miscellaneous Commands
----------------------

Other useful commands include ``/say`` to send messages to any chat, ``/block``
and ``/unblock`` for user management, ``/model`` to switch models, and
``/last_chats`` to list recent conversations.
