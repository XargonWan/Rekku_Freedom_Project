LLM Engines
===========

The Rekku Freedom Project can operate with multiple language model backends. Use the ``/llm`` command in chat to switch engines at runtime.

Selenium ChatGPT
----------------

The ``selenium_chatgpt`` plugin drives a real ChatGPT session using a browser. A manual login is required the first time.

Steps:

#. Start the stack with ``docker compose up``.
#. Open ``http://<host>:5006`` in your browser to access the virtual desktop.
#. Log in to ChatGPT and solve any captchas.

Once authenticated, Rekku can interact with ChatGPT in real time. Periodic manual intervention may be required when captchas appear.

Manual
------

The ``manual`` engine simply forwards prompts to a human trainer. It can be useful for debugging or during development.

ChatGPT API
-----------

A simpler API-based engine is also provided but has not been fully tested. Contributions are welcome.
