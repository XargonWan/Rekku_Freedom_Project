Interfaces
==========

This guide explains how to add a new chat interface and expose its actions to the
core system.

1. **Create the module**
   Place a new ``*.py`` file under the ``interface/`` directory.  Removing the
   file later cleanly removes the interface from Rekku.

2. **Declare actions**
   Implement ``get_supported_actions`` on the interface class.  The method should
   return a mapping of action names to a schema describing the required and
   optional fields.

3. **Optional prompt instructions**
   If the LLM needs extra guidance for an action, implement
   ``get_prompt_instructions(action_type)`` and return a dictionary of prompt
   snippets.

4. **Register the interface**
   When the interface starts, call ``register_interface`` to make the instance
   discoverable and notify the core initializer that it is active.

.. code-block:: python

   from core.core_initializer import register_interface, core_initializer

   class MyInterface:
       @staticmethod
       def get_interface_id():
           return "myiface"

       @staticmethod
       def get_supported_actions():
           return {
               "message_myiface": {
                   "required_fields": ["text"],
                   "optional_fields": [],
                   "description": "Send a message over MyInterface.",
               }
           }

       async def start(self):
           register_interface("myiface", self)
           core_initializer.register_interface("myiface")

   INTERFACE_CLASS = MyInterface

With these pieces in place the core initializer will automatically collect the
interface's actions and make them available to the LLM.
