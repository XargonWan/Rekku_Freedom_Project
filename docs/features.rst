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

Chat Link Resolver
------------------

Rekku stores chat and thread identifiers in a central resolver. Interfaces can
target conversations using either numeric IDs or human‑readable names, and the
``update_chat_name`` action refreshes the stored titles when they change.

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

Bio Management
--------------

Rekku maintains detailed user profiles called "bios" that store personal information,
preferences, and interaction history. This feature helps Rekku remember user details
and provide more personalized responses.

**Key Features:**

* **Persistent Storage**: User bios are stored in a dedicated database table with fields
  for known names, likes, dislikes, personal information, past events, feelings,
  contacts, and social accounts.

* **Consistency Validation**: The system validates bio updates for consistency, checking
  for contradictory information like age or location mismatches.

* **Update Limits**: To prevent abuse, updates are limited to 3 fields per update,
  with a minimum 1-hour gap between updates and a daily limit of 5 updates.

* **Privacy Controls**: Each bio includes privacy settings to control how information
  is shared.

**Usage Example:**

When interacting with a user named Takeshi, Rekku can access his bio to recall
that he enjoys programming and dislikes spicy food, providing more relevant
conversations.

**Database Schema:**

.. code-block:: sql

   CREATE TABLE bio (
       id VARCHAR(255) PRIMARY KEY,
       known_as TEXT,
       likes TEXT,
       not_likes TEXT,
       information TEXT,
       past_events TEXT,
       feelings TEXT,
       contacts TEXT,
       social_accounts TEXT,
       privacy TEXT,
       created_at VARCHAR(50),
       last_accessed VARCHAR(50),
       last_update TIMESTAMP,
       update_count INT
   );

AI Diary
--------

The AI Diary is a modular plugin that provides Rekku with persistent memory of
interactions and activities. This plugin is completely self-contained and can be
removed without affecting the core system.

**Key Features:**

* **Modular Design**: The diary plugin is fully self-contained with internal
  configuration and dedicated database storage.

* **Automatic Entry Creation**: After each action execution, the system creates
  diary entries summarizing activities, involved parties, tags, and emotions.

* **Static Injection**: Recent diary entries are injected into prompts when space
  allows, providing context from previous interactions.

* **User Access**: Authorized users (trainers) can view diary entries using the
  ``/diary`` command.

* **Fail-Safe Operation**: The plugin automatically disables itself in case of
  errors, ensuring the core system continues functioning.

**Database Schema:**

.. code-block:: sql

   CREATE TABLE ai_diary (
       id INT AUTO_INCREMENT PRIMARY KEY,
       content TEXT NOT NULL,
       timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
       tags JSON,
       involved JSON,
       emotions JSON,
       interface VARCHAR(50),
       chat_id VARCHAR(255),
       thread_id VARCHAR(255),
       INDEX idx_timestamp (timestamp),
       INDEX idx_interface_chat (interface, chat_id)
   );

**Usage Example:**

After helping Takeshi with a coding task, Rekku automatically creates a diary entry:

.. code-block:: text

   === Rekku's Recent Diary ===

   📅 2024-01-15 14:30:22
   Helped Takeshi with bio update and security improvements
   #tags: bio, security, helpful
   #involved: Takeshi
   #emotions: helpful(8), focused(7)
   #context: telegram/123456/2

   === End Diary ===

**Plugin Management:**

The diary plugin can be enabled/disabled dynamically:

.. code-block:: python

   from plugins.ai_diary import is_plugin_enabled, enable_plugin, disable_plugin

   # Check status
   if is_plugin_enabled():
       print("Plugin active")

   # Disable manually
   disable_plugin()

   # Re-enable (tests database connection)
   success = enable_plugin()

**Configuration:**

Each LLM engine has its own configuration for diary integration:

* **OpenAI**: Up to 2000 characters for diary content
* **Selenium ChatGPT**: Up to 1500 characters
* **Google CLI**: Up to 1200 characters
* **Manual**: Up to 800 characters

This ensures optimal performance across different interfaces while maintaining
contextual awareness.
