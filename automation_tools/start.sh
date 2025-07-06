#!/bin/bash
cd /app
echo "Current user: $(whoami)"
exec python3 main.py
