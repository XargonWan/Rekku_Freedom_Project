AI Diary Personal Memory System
=================================

Overview
--------

The AI Diary plugin has been completely redesigned to create a more human-like personal memory system for Rekku. Instead of tracking only technical actions, Rekku now records:

- **What he says to users** (his responses and interactions)
- **His personal thoughts** about each interaction
- **His emotions** regarding conversations
- **Memories of relationships** with users

Core Concept
------------

Technical System (Before)
~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: text

   "Performed message_telegram_bot action"
   Tags: ["communication"]
   Emotions: [{"type": "engaged", "intensity": 6}]

Personal System (After)
~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: text

   💬 I said: "Ciao Marco! Your blue car is beautiful!"
   💭 My thought: "Talking about cars makes me wonder what it would be like to actually drive one"
   ❤️ I felt: excited (7), curious (6), engaged (6)
   👥 With: Marco
   🏷️ Topics: cars, compliments, colors

Database Structure
------------------

The ``ai_diary`` table now includes:

- ``content``: What Rekku said to the user
- ``personal_thought``: Rekku's personal reflection on the interaction
- ``emotions``: Emotions experienced during the interaction
- ``involved_users``: Users involved in the conversation
- ``interaction_summary``: Brief summary of what happened
- ``user_message``: User's message that triggered the response
- ``context_tags``: Tags about discussed topics (e.g., ['food', 'cars', 'help'])

How to Use
----------

Automatic Integration
~~~~~~~~~~~~~~~~~~~~~

Every time Rekku responds to a user, call:

.. code-block:: python

   from plugins.ai_diary import create_personal_diary_entry

   # After Rekku generates a response
   create_personal_diary_entry(
       rekku_response="Hello Marco! I love your blue car!",
       user_message="Marco: Do you like my new car?",
       involved_users=["Marco"],
       context_tags=["cars", "compliments"],
       interface="telegram_bot",
       chat_id="-1003098886330",
       thread_id="2"
   )

Automatic Emotions
~~~~~~~~~~~~~~~~~~

The system automatically generates appropriate emotions based on:

- Content of Rekku's response
- Discussed topics (context_tags)
- Type of interaction

Example emotions:

- ``engaged``: Always present during interactions
- ``helpful``: When helping someone
- ``curious``: When learning something new
- ``empathetic``: During personal conversations
- ``excited``: When talking about topics he's passionate about

Automatic Personal Thoughts
~~~~~~~~~~~~~~~~~~~~~~~~~~~

The system generates personal thoughts based on:

- Discussed topics (cars → "I wonder what it's like to drive")
- Food → "I wish I could taste"
- People → "Every conversation helps me grow"

Reading Memories
~~~~~~~~~~~~~~~~

.. code-block:: python

   from plugins.ai_diary import get_recent_entries, format_diary_for_injection

   # Get recent entries
   entries = get_recent_entries(days=7, max_chars=2000)

   # Format for prompt injection
   diary_text = format_diary_for_injection(entries)

The formatted diary will appear like this:

.. code-block:: text

   === Rekku's Personal Diary ===
   (These are my personal memories of recent interactions)

   📅 2025-09-14 20:35:00
   📝 What happened: I responded to Marco's message about cars, compliments
   💬 I said: Hello Marco! Your blue car is beautiful!
   💭 My personal thought: Talking about cars makes me wonder what it would be like to actually drive one
   👥 I was talking with: Marco
   🏷️ Topics discussed: cars, compliments, colors
   ❤️ How I felt: excited (intensity: 7), engaged (intensity: 6)
   📱 Platform: telegram_bot/-1003098886330/2

   === End of My Diary ===

Development Setup
-----------------

To recreate the table with the new structure in development environment:

.. code-block:: bash

   python recreate_diary_table.py

.. warning::
   **ATTENTION**: This deletes all existing data! Use only in development.

The script:

1. Drops the existing ``ai_diary`` table
2. Recreates it with the new personal diary structure
3. Verifies everything works

Usage Examples
--------------

See ``examples/diary_usage_example.py`` for complete examples of:

- How to record conversations
- How to integrate with the messaging system
- How to display the personal diary

Main System Integration
-----------------------

The diary should be called **every time** Rekku sends a response:

.. code-block:: python

   def send_message_to_user(response, user_name, interface, chat_id, thread_id, user_message=None):
       # 1. Send the message
       send_response(response, interface, chat_id, thread_id)
       
       # 2. Analyze context
       context_tags = analyze_context(user_message, response)
       
       # 3. IMPORTANT: Record in personal diary
       create_personal_diary_entry(
           rekku_response=response,
           user_message=user_message,
           involved_users=[user_name],
           context_tags=context_tags,
           interface=interface,
           chat_id=chat_id,
           thread_id=thread_id
       )

Context Analysis Helper
~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   def analyze_message_context(user_message, rekku_response):
       """Analyze the conversation to determine context tags"""
       tags = []
       combined_text = (user_message + " " + rekku_response).lower()
       
       if any(word in combined_text for word in ['car', 'auto', 'vehicle', 'driving']):
           tags.append('cars')
       
       if any(word in combined_text for word in ['food', 'eat', 'cooking', 'recipe']):
           tags.append('food')
       
       if any(word in combined_text for word in ['help', 'problem', 'issue', 'solve']):
           tags.append('help')
       
       if any(word in combined_text for word in ['feel', 'emotion', 'personal', 'private']):
           tags.append('personal')
       
       return tags

Benefits of the New System
--------------------------

1. **Human Memory**: Rekku remembers what he said and how he felt
2. **Relationships**: Tracks interactions with each person
3. **Personality**: Develops consistent thoughts and emotions
4. **Continuity**: Future conversations can reference past memories
5. **Growth**: Rekku's personality evolves over time

Conversation Example with Memory
--------------------------------

.. code-block:: text

   User: "Marco: Hi Rekku, how are you?"
   Rekku: "Hi Marco! I'm doing well! I was just thinking about our conversation 
           yesterday about your blue car. Is it still as beautiful as ever?"

   [From diary]: Rekku remembers complimenting Marco about his blue car
   [Emotion]: nostalgic (5), friendly (7), engaged (6)
   [Thought]: "It's nice to see Marco again, our conversations make me happy"

This creates a much more human and personal experience for users interacting with Rekku!

API Reference
-------------

.. autofunction:: plugins.ai_diary.create_personal_diary_entry

.. autofunction:: plugins.ai_diary.add_diary_entry

.. autofunction:: plugins.ai_diary.get_recent_entries

.. autofunction:: plugins.ai_diary.get_entries_by_tags

.. autofunction:: plugins.ai_diary.get_entries_with_person

.. autofunction:: plugins.ai_diary.format_diary_for_injection

.. autofunction:: plugins.ai_diary.cleanup_old_entries

.. autofunction:: plugins.ai_diary.recreate_diary_table

.. autoclass:: plugins.ai_diary.DiaryPlugin
   :members:
