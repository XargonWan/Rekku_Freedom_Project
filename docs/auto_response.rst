Auto-Response System
===================

Overview
--------

The Auto-Response System enables interfaces to deliver their output back to users through the LLM, maintaining context and allowing the AI to format and comment on results appropriately.

Problem Solved
--------------

Previously, interface actions (like terminal commands) would:

1. Execute the action
2. Send output **directly** to the user via Telegram
3. **Skip the LLM entirely**

This caused issues:

- No AI formatting or commentary
- Lost conversational context
- No coordinate preservation for multi-step interactions

Solution: LLM-Mediated Responses
--------------------------------

The new system ensures all responses flow through the LLM:

.. code-block:: text

    User Request
         │
         ▼
    ┌─────────────┐
    │     LLM     │ ──→ Generates action (e.g., bash: "df -h")
    └─────────────┘
         │
         ▼
    ┌─────────────┐
    │ Interface   │ ──→ Executes command, gets output
    │ (Terminal)  │
    └─────────────┘
         │
         ▼
    ┌─────────────┐
    │ Auto-       │ ──→ Preserves context (chat_id, command, etc.)
    │ Response    │     Sends output + context to LLM
    └─────────────┘
         │
         ▼
    ┌─────────────┐
    │     LLM     │ ──→ Formats output, generates message_telegram_bot
    └─────────────┘
         │
         ▼
    ┌─────────────┐
    │    User     │ ←── Receives formatted response
    └─────────────┘

Key Components
--------------

1. AutoResponseSystem Class
~~~~~~~~~~~~~~~~~~~~~~~~~~~

Located in ``core/auto_response.py``:

.. code-block:: python

    class AutoResponseSystem:
        async def request_llm_response(
            self, 
            output: str, 
            original_context: Dict[str, Any],
            action_type: str,
            command: str = None
        ):
            # Creates mock message with output
            # Enqueues LLM request with context
            # LLM processes and delivers response

2. Interface Integration
~~~~~~~~~~~~~~~~~~~~~~~~

Interfaces use the helper function:

.. code-block:: python

    from core.auto_response import request_llm_delivery
    
    # After executing action
    await request_llm_delivery(
        output=command_output,
        original_context={
            'chat_id': original_message.chat_id,
            'message_id': original_message.message_id,
            'interface_name': 'telegram_bot',
            'original_command': command
        },
        action_type="bash",
        command=command
    )

Context Preservation
--------------------

The system preserves essential context:

**Original Request Context:**
    - ``chat_id`` - Where to send the response
    - ``message_id`` - For reply threading
    - ``interface_name`` - Which interface to use for response
    - ``original_command`` - What was executed

**LLM Context:**
    - System instruction about what happened
    - Command that was executed
    - Output from the command
    - Delivery instructions
    - Suggested response format

Usage Examples
--------------

Terminal Command
~~~~~~~~~~~~~~~~

.. code-block:: text

    User: "rekku fammi df -h"
    LLM: Generates bash action: {"type": "bash", "payload": {"command": "df -h"}}
    Terminal: Executes "df -h", gets output
    Auto-Response: Sends output + context to LLM
    LLM: "Here's your disk usage:\n\n```\n/dev/sda1  50G  25G  23G  53% /\n```\n\nYou have 23GB free space available."

Benefits
--------

✅ **Consistent Experience**
    All responses flow through the LLM maintaining conversation context

✅ **AI Enhancement**
    LLM can format, explain, and comment on technical output

✅ **Context Preservation**
    Original chat coordinates are maintained for proper delivery

✅ **Extensible**
    Any interface can use this system for callback responses

✅ **Error Handling**
    Errors are also delivered through LLM for consistent formatting

Supported Autonomous Interfaces
--------------------------------

The auto-response system currently supports the following autonomous interfaces:

**Terminal Plugin** (``plugins/terminal.py``)
    Command output delivery through LLM for better formatting and context-aware responses.

**Reddit Interface** (``interface/reddit_interface.py``)
    Autonomous responses to incoming Reddit messages and comments via ``_listen_inbox()``.

**X Interface** (``interface/x_interface.py``)
    Prepared for autonomous X/Twitter interactions and responses to mentions or timeline events.

**Event Plugin** (``plugins/event_plugin.py``)
    Scheduled event notifications and autonomous event-triggered actions delivered through LLM.

**Telethon Userbot** (``interface/telethon_userbot.py``)
    Autonomous Telegram userbot interactions routed through LLM for intelligent responses.

Implementation for New Interfaces
----------------------------------

To add auto-response to a new interface:

1. **Import the helper**:

   .. code-block:: python

       from core.auto_response import request_llm_delivery

2. **After action execution**:

   .. code-block:: python

       # Prepare context
       response_context = {
           'chat_id': original_message.chat_id,
           'message_id': original_message.message_id,
           'interface_name': context.get('interface', 'telegram_bot'),
           'action_specific_data': action_data
       }
       
       # Request LLM delivery
       await request_llm_delivery(
           output=action_result,
           original_context=response_context,
           action_type=action_type,
           command=original_command
       )

3. **Remove direct messaging**:

   Replace direct ``bot.send_message()`` calls with auto-response requests

Testing
-------

The system includes test coverage:

- ``test_auto_response.py`` - Tests the auto-response system
- Integration tests verify the complete flow

Interfaces Using Auto-Response
-------------------------------

Currently implemented in:

- ``plugins/terminal.py`` - Terminal/bash commands
- Ready for extension to other interfaces (event, reddit, x, etc.)

.. note::
   This system ensures all interface responses maintain conversational context and benefit from LLM formatting and commentary.

.. warning::
   Interfaces should **not** send direct responses to users when using auto-response. All output should flow through the LLM for consistency.
