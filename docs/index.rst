Rekku Freedom Project Documentation
===================================

.. image:: res/RFP_logo.png
   :width: 200px
   :alt: RFP Logo

Welcome to the **Rekku Freedom Project** documentation. These pages are built
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
   features
   architecture
   llm_engines
   plugins
   contributing
   faq

Building the Documentation
--------------------------

Install the documentation requirements from the repository root and run:

.. code-block:: bash

   sphinx-build -b html docs docs/_build/html

The generated HTML files will be available under ``docs/_build/html``.
