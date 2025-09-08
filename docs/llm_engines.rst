LLM Engines
===========

The Rekku Freedom Project can operate with multiple language model backends. Use the ``/llm`` command in chat to switch engines at runtime.

Available Engines
-----------------

* ``manual`` – forward prompts to a human trainer (no configuration).
* ``openai_chatgpt`` – access OpenAI's ChatGPT API.  Set ``OPENAI_API_KEY`` and optional ``CHATGPT_MODEL``.
* ``google_cli`` – use Google's Gemini via the ``gemini`` command-line client.  Requires ``GEMINI_API_KEY`` and the ``gemini`` tool.
* ``selenium_chatgpt`` – drive a browser session of ChatGPT.  Use ``CHROMIUM_HEADLESS`` and ``CHATGPT_MODEL``; ``WEBVIEW_HOST``/``WEBVIEW_PORT`` expose the desktop.

Selenium ChatGPT
----------------

The ``selenium_chatgpt`` plugin drives a real ChatGPT session using a browser. A manual login is required the first time.  Set ``CHATGPT_MODEL`` to pick a model and ``CHROMIUM_HEADLESS=0`` (default) to view the browser. ``WEBVIEW_HOST`` and ``WEBVIEW_PORT`` determine the remote desktop address.

Steps:

#. Start the stack with ``docker compose up``.
#. Open ``http://<host>:5006`` in your browser to access the virtual desktop.
#. Log in to ChatGPT and solve any captchas.

Once authenticated, Rekku can interact with ChatGPT in real time. Periodic manual intervention may be required when captchas appear.

Manual
------

The ``manual`` engine simply forwards prompts to a human trainer. It can be useful for debugging or during development.

OpenAI ChatGPT
--------------

The ``openai_chatgpt`` engine calls OpenAI's ChatGPT API using the ``openai`` Python package.
Provide an API key via ``OPENAI_API_KEY`` and optionally set ``CHATGPT_MODEL``.

Google CLI
----------

The ``google_cli`` engine sends prompts to the ``gemini`` command-line tool in order to use Google's Gemini models.  Set ``GEMINI_API_KEY`` and ensure ``gemini`` is installed.

Developing LLM Engines
----------------------

Custom engines live in ``llm_engines/`` and subclass ``AIPluginBase``.  A
minimal engine implements ``generate_response`` and exposes a module-level
``PLUGIN_CLASS``:

.. code-block:: python

   from core.ai_plugin_base import AIPluginBase

   class MyEngine(AIPluginBase):
       async def generate_response(self, messages):
           return "Hello from MyEngine"

   PLUGIN_CLASS = MyEngine

Useful hooks inherited from ``AIPluginBase``:

* ``generate_response(messages)`` – **required**; return LLM output.
* ``get_supported_models()`` – list available model IDs.
* ``get_rate_limit()`` – tuple of rate limit settings.
* ``get_supported_action_types()`` and ``handle_custom_action()`` – declare and
  handle engine-specific actions.
* ``get_supported_actions()`` and ``get_prompt_instructions()`` – supply schema
  data or prompt hints for custom actions.
