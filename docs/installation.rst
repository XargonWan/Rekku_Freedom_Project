Installation
============

.. image:: res/installation.png
   :alt: Installation steps
   :width: 600px
   :align: center


The project can be deployed using Docker. Ensure you have `docker` and
`docker compose` installed on your machine. Copy `.env.example` to `.env`
and adjust the values for your environment.

Build and start the services:

.. code-block:: bash

   docker compose up

A MariaDB instance is started automatically and a daily backup container
writes dumps to ``./backups/``.
