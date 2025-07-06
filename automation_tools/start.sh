#!/bin/bash

# Ensure mounted volumes are writable by the rekku user
chown -R rekku:rekku /app /home/rekku

# Drop privileges and launch the bot as rekku
exec su -p rekku -c "cd /app && python3 main.py"
