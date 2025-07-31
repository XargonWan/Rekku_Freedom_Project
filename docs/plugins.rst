Plugins
=======

The project includes several optional plugins that implement additional actions
or storage.

Terminal
--------

``plugins/terminal`` exposes a persistent shell accessible from chat. Commands
sent to the bot are executed in a background ``/bin/bash`` process and the
output is returned.

Event
-----

The ``event`` plugin stores scheduled reminders in a MariaDB table. A background
scheduler checks for due events and sends them back to Rekku when the time comes.

Message
-------

``message_plugin`` handles text message actions across multiple interfaces. It is
used internally by other plugins to send replies.
