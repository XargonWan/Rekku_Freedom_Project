Synthetic Heart Documentation
===================================

.. image:: res/SyntH_logo.png
   :width: 600px
   :alt: SyntH Logo


Welcome to the **Synthetic Heart** documentation. These pages are built
with Sphinx and hosted on **Read the Docs**. Every push to the repository
triggers a new build of this wiki.

The following sections provide an overview of the project and instructions for
getting started.

.. toctree::
   :maxdepth: 2
   :caption: Contents:

   installation
   usage
   quickstart
   commands
   features
   architecture
   event_id_flow
   auto_response
   chat_links
   persona_manager
   persona_configuration
   llm_engines
   plugins
   validation_system
   ai_diary_personal_memory
   vrm_animations
   interfaces
   matrix_interface
   config_management
   dev_components
   contributing
   faq

Building the Documentation
--------------------------

Install the documentation requirements from the repository root and run:

.. code-block:: bash

   sphinx-build -b html docs docs/_build/html

The generated HTML files will be available under ``docs/_build/html``.
