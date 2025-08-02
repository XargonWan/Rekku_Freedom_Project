Project Structure
=================

The Rekku Freedom Project is organized into modular packages. Understanding the layout helps newcomers navigate the codebase.

Repository Layout
-----------------

- ``core`` – foundational services such as configuration, logging, message queue, and database access.
- ``interface`` – chat connectors for platforms like Telegram, Discord, and Reddit.
- ``llm_engines`` – integrations with language model backends.
- ``plugins`` – extend Rekku with action plugins (e.g., terminal, event).
- ``automation_tools`` – helper scripts for development and deployment.
- ``tests`` – automated test suite.

Component Relationships
-----------------------

The diagram below shows how the main components interact.

.. graphviz::

   digraph Rekku {
       rankdir=LR;
       node [shape=box];
       Users -> Interfaces -> Core -> "LLM Engines";
       Core -> Plugins -> "External Services";
       Core -> Database;
   }

