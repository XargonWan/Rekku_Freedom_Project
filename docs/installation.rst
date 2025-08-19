Installation
============

.. image:: res/installation.png
   :alt: Installation steps
   :width: 600px
   :align: center


The project can be deployed using Docker. Ensure you have `docker` and
`docker compose` installed on your machine. Copy `.env.example` to `.env`
and adjust the values for your environment. Set ``BOTFATHER_TOKEN`` and
optionally configure ``NOTIFY_ERRORS_TO_INTERFACES`` with comma-separated
``interface:trainer_id`` pairs to select which interfaces receive error
notifications.

Build and start the services:

.. code-block:: bash

   docker compose up

A MariaDB instance is started automatically and a daily backup container
writes dumps to ``./backups/``.
