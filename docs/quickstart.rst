Quickstart
==========

.. image:: res/quickstart.png
   :alt: Quickstart screenshot
   :width: 600px
   :align: center


This guide outlines the typical steps to run **Rekku Freedom Project** using Docker.

#. Copy ``.env.example`` to ``.env`` and adjust values as needed. Important
   variables include ``BOTFATHER_TOKEN``, ``TRAINER_ID`` and database
   credentials.
#. Build and start the services:

   .. code-block:: bash

      docker compose up

#. Open the web interface at ``http://<host>:5006`` to perform the initial
   ChatGPT login if you plan to use the ``selenium_chatgpt`` engine.

Database backups are written hourly to ``./backups/``. To tear down the
containers, press :kbd:`Ctrl+C` or run ``docker compose down``.
