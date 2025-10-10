Synthetic Heart Documentation
===================================

.. raw:: html

   <div align="center">
      <div style="background: #222; border-radius: 12px; padding: 12px; width: 700px; height: 300px; display: flex; align-items: center; justify-content: center; margin: 0 auto;">
         <img src="res/SyntH_logo.png" alt="Synthetic Heart Logo" style="max-width: 100%; max-height: 100%; object-fit: contain;" />
      </div>
   </div>


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
