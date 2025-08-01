Usage Overview
==============

.. image:: res/wiki/usage_overview.png
   :alt: Usage Overview
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
