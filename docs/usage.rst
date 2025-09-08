Usage Overview
==============

.. image:: res/usage_overview.png
   :alt: Usage Overview
   :width: 600px
   :align: center


Rekku operates as a modular AI persona with multiple LLM backends. You can
switch engines on the fly using the ``/llm`` command in your preferred chat
platform. Supported modes include ``manual``, ``openai_chatgpt``, ``google_cli``
and ``selenium_chatgpt``.

Message forwarding is automatic when Rekku is mentioned or receives a private
message. The ``event`` plugin stores reminders in the configured database and
delivers them when due. Additional plugins extend behaviour: the
``message_plugin`` sends text to any registered interface, ``time_plugin`` and
``weather_plugin`` inject temporal and environmental context, ``reddit_plugin``
creates posts and comments, and ``selenium_elevenlabs`` generates speech audio.

Contextual memory can be toggled with ``/context``. When enabled, the last ten
messages are injected into the prompt sent to the active LLM.
