#!/bin/bash

# Ensure application directory is owned by the bot user
chown -R rekku:rekku /app

# Drop privileges and run the bot
exec su -p rekku -c "cd /app && python3 main.py"
