LLM Engines
===========

The Rekku Freedom Project supports multiple language model backends through a modular engine system. Engines are automatically discovered and can be switched at runtime using the ``/llm`` command. This design ensures that LLM implementations are completely decoupled from the core system.

Engine Architecture
-------------------

All LLM engines follow a consistent architecture:

- **Auto-Discovery**: Engines are automatically found in the ``llm_engines/`` directory
- **Standard Interface**: All engines extend ``AIPluginBase`` for consistent integration
- **Capability Reporting**: Engines declare their supported models and features
- **Dynamic Switching**: Active engine can be changed without restarting the system
- **Unified Limits**: Engines report their constraints (token limits, modalities, etc.)

Available Engines
-----------------

* ``manual`` – Forward prompts to a human trainer for manual responses (useful for debugging and development).
* ``openai_chatgpt`` – Access OpenAI's ChatGPT API with support for GPT-3.5, GPT-4, and GPT-4o models. Requires ``OPENAI_API_KEY``.
* ``google_cli`` – Use Google's Gemini models via the command-line ``gemini`` tool. Requires ``GEMINI_API_KEY`` and the ``gemini`` CLI tool.
* ``selenium_chatgpt`` – Drive a browser-based ChatGPT session for advanced interaction. Uses ``CHROMIUM_HEADLESS`` and ``CHATGPT_MODEL``; ``WEBVIEW_HOST``/``WEBVIEW_PORT`` expose the desktop interface.

Manual Engine
-------------

The ``manual`` engine forwards all prompts to a human trainer instead of an AI model:

- **Debugging Tool**: Useful for testing interfaces and workflows without API costs
- **Development Aid**: Allows manual inspection of prompts and responses
- **No Configuration**: Works immediately without API keys or external dependencies
- **Trainer Feedback**: Responses are sent back through the normal message flow

OpenAI ChatGPT Engine
---------------------

The ``openai_chatgpt`` engine provides access to OpenAI's models:

- **Model Support**: GPT-3.5-turbo, GPT-4, GPT-4o with automatic capability detection
- **Token Management**: Respects model-specific context limits and token budgets
- **Multimodal**: GPT-4o supports image inputs and analysis
- **Rate Limiting**: Built-in rate limiting and retry logic for API stability

Configuration:

.. code-block:: bash

   OPENAI_API_KEY=your_api_key_here
   CHATGPT_MODEL=gpt-4o  # Optional, defaults to gpt-3.5-turbo

Google CLI Engine
-----------------

The ``google_cli`` engine uses Google's command-line Gemini tool:

- **Local Execution**: Runs Gemini models locally via CLI
- **API Key Required**: Set ``GEMINI_API_KEY`` for authentication
- **Installation Required**: Must install the ``gemini`` CLI tool separately
- **Offline Capable**: Can work without internet once models are cached

Selenium ChatGPT Engine
-----------------------

The ``selenium_chatgpt`` engine controls a real ChatGPT browser session:

- **Full Browser Control**: Uses Selenium to interact with ChatGPT web interface
- **Captcha Handling**: Manual intervention required for initial setup and captchas
- **Visual Desktop**: Optional web interface at ``http://<host>:5006`` for monitoring
- **Model Selection**: Supports different ChatGPT models via ``CHATGPT_MODEL``

Setup Steps:

1. Start the system with ``docker compose up``
2. Access ``http://<host>:5006`` in your browser
3. Complete ChatGPT login and captcha verification
4. Rekku can then interact with ChatGPT in real-time

Engine Registration and Discovery
---------------------------------

LLM engines are automatically discovered through the core initializer:

1. **Directory Scanning**: Core scans ``llm_engines/`` for Python files
2. **Class Inspection**: Files are checked for ``PLUGIN_CLASS`` attribute
3. **Registry Registration**: Engines register with the LLM registry
4. **Capability Indexing**: Engine capabilities are indexed for runtime selection
5. **Dynamic Loading**: Engines can be loaded/unloaded without system restart

Developing LLM Engines
----------------------

Creating a new LLM engine requires extending ``AIPluginBase`` and implementing the core methods:

.. code-block:: python

   from core.ai_plugin_base import AIPluginBase
   from core.transport_layer import llm_to_interface

   class MyEngine(AIPluginBase):
       def __init__(self, notify_fn=None):
           self.notify_fn = notify_fn

       async def handle_incoming_message(self, bot, message, prompt):
           """Process a message and generate response."""
           # Generate response using your LLM
           reply = await self.generate_response(prompt)
           
           # Send response back through the interface
           await llm_to_interface(bot.send_message, chat_id=message.chat_id, text=reply)
           return reply

       async def generate_response(self, messages):
           """Core LLM interaction method."""
           # Implement your model API calls here
           # messages is a list of message objects with role/content
           response = await call_my_llm_api(messages)
           return response

       def get_supported_models(self) -> list[str]:
           """Return available model names."""
           return ["my-model-v1", "my-model-v2"]

       def get_rate_limit(self):
           """Return (requests_per_hour, time_window_seconds, burst_limit)."""
           return (100, 3600, 10)  # 100 requests/hour with 10 burst

   # Required: Export the engine class
   PLUGIN_CLASS = MyEngine

Engine Integration
------------------

Once created, register your engine with the LLM registry:

.. code-block:: python

   from core.llm_registry import get_llm_registry
   get_llm_registry().register_engine_module("my_engine", "llm_engines.my_engine")

Switch to your engine at runtime:

.. code-block:: text

   /llm my_engine

Engine Capabilities
-------------------

Engines report their capabilities to the system:

- **Model List**: Available models and their identifiers
- **Token Limits**: Maximum prompt and response lengths
- **Modalities**: Support for text, images, audio, etc.
- **Rate Limits**: API constraints and throttling requirements
- **Features**: Function calling, streaming, fine-tuning support

These capabilities are used by the prompt engine to construct appropriate prompts and by the interface layer to handle different content types.

Best Practices
--------------

**Error Handling**
    Implement robust error handling with user-friendly messages.

**Rate Limiting**
    Respect API limits and implement backoff strategies.

**Token Management**
    Track token usage and handle context window limitations.

**Async Operations**
    Use async methods for all I/O operations to maintain responsiveness.

**Security**
    Never log API keys or sensitive authentication data.

For complete examples, examine ``llm_engines/openai_chatgpt.py`` or ``llm_engines/selenium_chatgpt.py`` in the repository.
