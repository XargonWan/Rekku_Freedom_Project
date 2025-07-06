#!/bin/bash
# Ensure application directory is owned by the bot user
chown -R rekku:rekku /app

# Run the bot as the rekku user
exec su rekku -c 'cd /app && echo "Current user: $(whoami)" && python3 main.py'
