Configuring Plugins (ELI5)
==========================

.. graphviz::

   digraph setup {
       rankdir=LR;
       A [label="1. Get API keys/tokens"];
       B [label="2. Fill them in .env"];
       C [label="3. Install dependencies"];
       D [label="4. Run Rekku"];
       A -> B -> C -> D;
   }

This page explains how to enable built-in plugins using plain-language steps.

Reddit
------

1. Create a new app on `https://www.reddit.com/prefs/apps <https://www.reddit.com/prefs/apps>`_.
2. Copy the credentials into your ``.env`` file::

      REDDIT_CLIENT_ID=...
      REDDIT_CLIENT_SECRET=...
      REDDIT_USERNAME=...
      REDDIT_PASSWORD=...
      REDDIT_USER_AGENT=rekku-agent
3. Start the bot. Reddit actions will now work.

Telegram Bot
------------

1. In Telegram, talk to **@BotFather** and create a bot.
2. Paste the given token into ``BOTFATHER_TOKEN`` (or ``TELEGRAM_TOKEN``) in ``.env``.
3. Set ``TRAINER_ID`` to your own Telegram user ID so you can control the bot.
4. Launch Rekku with ``python main.py`` and message your bot.

Telethon Userbot
----------------

1. Visit `https://my.telegram.org <https://my.telegram.org>`_ and log in.
2. Create an API ID and API hash.
3. Add them to ``.env``::

      API_ID=12345
      API_HASH=abcdef123456
      SESSION=rekku_userbot
4. On first run you will be asked for your phone number and a confirmation code to create the session file.

X Interface
-----------

1. Set your X handle in ``.env``::

      X_USERNAME=yourname
2. Timeline and search features rely on ``snscrape`` which may not work on Python 3.12.

Discord Interface
-----------------

1. Create a bot at `https://discord.com/developers/applications <https://discord.com/developers/applications>`_.
2. Add a ``DISCORD_TOKEN`` entry to your ``.env`` with the bot token.
3. The current interface is a stub; expand ``interface/discord_interface.py`` to connect the token and send messages.

