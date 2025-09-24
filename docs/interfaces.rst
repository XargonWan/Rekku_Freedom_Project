Interfaces
==========

Interfaces provide the communication layer between Rekku and external platforms. Like plugins and LLM engines, interfaces are completely modular and automatically discovered at runtime. This ensures that platform integrations are decoupled from the core system and can be developed independently.

Interface Architecture
----------------------

All interfaces follow a consistent architecture:

- **Auto-Discovery**: Interfaces are automatically found in the ``interface/`` directory
- **Standard Interface**: Interfaces extend ``AIPluginBase`` or implement compatible methods
- **Action Providers**: Interfaces can provide actions (sending messages, media, etc.)
- **Security Integration**: Built-in trainer ID validation and rate limiting
- **Platform Abstraction**: Unified message format across different platforms

Available Interfaces
--------------------

* ``cli`` – Local command-line interface for direct interaction (no configuration).
* ``discord_interface`` – Discord bot integration. Requires ``DISCORD_BOT_TOKEN``.
* ``reddit_interface`` – Asynchronous Reddit client for posts, comments, and DMs. Requires Reddit API credentials.
* ``telegram_bot`` – Telegram bot interface with media support. Requires ``BOTFATHER_TOKEN`` and trainer ID.
* ``telethon_userbot`` – Advanced Telegram userbot using Telethon. Requires ``API_ID``, ``API_HASH``, and session.
* ``webui`` – FastAPI-based web interface for browser access. Configurable host/port.
* ``x_interface`` – Experimental X (Twitter) integration with timeline features. Requires ``X_USERNAME``.

Discord Interface
-----------------

The Discord interface provides full bot integration:

**Setup Steps:**

1. Create an application at `Discord Developer Portal <https://discord.com/developers/applications>`_
2. Add a bot user and copy the token
3. Enable required intents (Message Content Intent, etc.)
4. Generate invite URL with bot scope and permissions
5. Set ``DISCORD_BOT_TOKEN`` in environment variables
6. Start Rekku - the interface loads automatically

**Features:**

- Real-time message handling
- Media upload/download support
- Thread and channel management
- Role and permission integration

Telegram Bot Interface
----------------------

The Telegram bot interface offers comprehensive Telegram integration:

**Configuration:**

.. code-block:: bash

   BOTFATHER_TOKEN=your_bot_token
   TRAINER_IDS=telegram_bot:123456789

**Features:**

- Message threading support
- Media handling (photos, documents, voice)
- Inline keyboard and callback support
- Group and private chat handling
- Trainer ID security validation

Reddit Interface
----------------

The Reddit interface enables social media integration:

**Required Credentials:**

.. code-block:: bash

   REDDIT_CLIENT_ID=your_client_id
   REDDIT_CLIENT_SECRET=your_client_secret
   REDDIT_USERNAME=your_username
   REDDIT_PASSWORD=your_password
   REDDIT_USER_AGENT=RekkuFreedomProject/1.0

**Capabilities:**

- Post creation and commenting
- Direct message handling
- Subreddit monitoring
- User interaction tracking

Web UI Interface
----------------

The web interface provides browser-based access:

**Configuration:**

.. code-block:: bash

   WEBUI_HOST=0.0.0.0
   WEBUI_PORT=5006

**Features:**

- Modern web interface
- Real-time chat updates
- File upload support
- Responsive design

Interface Registration System
-----------------------------

Interfaces are automatically discovered and integrated:

1. **Directory Scanning**: Core scans ``interface/`` for Python modules
2. **Class Discovery**: Files checked for ``INTERFACE_CLASS`` or ``PLUGIN_CLASS``
3. **Registration**: Interfaces register with the interface registry
4. **Capability Indexing**: Supported actions and features are cataloged
5. **Security Setup**: Trainer IDs configured from environment variables

Developing Interfaces
---------------------

Creating a new interface requires implementing the interface contract:

.. code-block:: python

   from core.ai_plugin_base import AIPluginBase
   from core.core_initializer import register_interface
   from core.interfaces_registry import get_interface_registry

   class MyInterface(AIPluginBase):
       @staticmethod
       def get_interface_id() -> str:
           """Return unique interface identifier."""
           return "myinterface"

       @staticmethod
       def get_supported_action_types() -> list[str]:
           """Return action types this interface supports."""
           return ["message"]

       @staticmethod
       def get_supported_actions() -> dict:
           """Return action schemas."""
           return {
               "message_myinterface": {
                   "description": "Send a message via MyInterface",
                   "required_fields": ["text", "target"],
                   "optional_fields": ["media"],
               }
           }

       def get_prompt_instructions(self, action_name: str) -> dict:
           """Provide LLM instructions for interface actions."""
           if action_name == "message_myinterface":
               return {
                   "description": "Send a message through MyInterface.",
                   "payload": {
                       "text": {"type": "string", "description": "Message content"},
                       "target": {"type": "string", "description": "Recipient identifier"},
                       "media": {"type": "string", "description": "Optional media URL"}
                   }
               }
           return {}

       def validate_payload(self, action_type: str, payload: dict) -> list[str]:
           """Validate action payloads."""
           errors = []
           if action_type == "message_myinterface":
               if "text" not in payload:
                   errors.append("payload.text is required")
               if "target" not in payload:
                   errors.append("payload.target is required")
           return errors

       async def start(self):
           """Initialize the interface."""
           # Register with core systems
           register_interface("myinterface", self)
           core_initializer.register_interface("myinterface")
           
           # Start your platform connection here
           await self.connect_to_platform()

       async def connect_to_platform(self):
           """Platform-specific connection logic."""
           # Implement platform connection
           pass

       async def handle_incoming_message(self, bot, message, prompt):
           """Handle incoming messages (if this interface also acts as LLM)."""
           # Optional: if interface can also generate responses
           pass

   # Required: Export the interface class
   INTERFACE_CLASS = MyInterface

Interface Actions
-----------------

Interfaces can provide actions that LLMs can invoke:

**Message Sending:**

.. code-block:: json

   {
     "type": "message_telegram_bot",
     "payload": {
       "text": "Hello from Rekku!",
       "chat_id": "123456789"
     }
   }

**Media Handling:**

.. code-block:: json

   {
     "type": "send_media_discord",
     "payload": {
       "file_url": "https://example.com/image.png",
       "channel_id": "987654321"
     }
   }

Security and Validation
-----------------------

**Trainer ID Validation:**

Interfaces validate that sensitive operations come from authorized users:

.. code-block:: bash

   TRAINER_IDS=telegram_bot:123456789,discord_interface:987654321

**Rate Limiting:**

Built-in rate limiting prevents abuse:

- Per-user rate limits
- Burst protection
- Platform-specific constraints

**Input Validation:**

All inputs are validated before processing:

- Payload schema validation
- Type checking
- Content filtering

Best Practices
--------------

**Error Handling**
    Implement comprehensive error handling with user feedback.

**Async Operations**
    Use async methods for all I/O operations.

**Security First**
    Always validate trainer permissions for sensitive actions.

**Platform Limits**
    Respect platform rate limits and content policies.

**Documentation**
    Provide clear action schemas and examples.

For complete implementations, examine ``interface/telegram_bot.py`` or ``interface/discord_interface.py`` in the repository.
