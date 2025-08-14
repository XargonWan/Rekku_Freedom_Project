#!/bin/bash
echo "[fix-session] 🔧 Starting session fix..."

# Fix ownership and permissions
chown -R 1000:1000 /home/rekku /config
chmod -R u+rwX,g+rwX,o+rX /home/rekku /config

# Create logs directory if it doesn't exist and fix permissions
mkdir -p /config/logs
chown -R 1000:1000 /config/logs
chmod -R 755 /config/logs

# Touch log files to ensure they exist with correct permissions
touch /config/logs/rekku.log
chown 1000:1000 /config/logs/rekku.log
chmod 644 /config/logs/rekku.log

# Remove corrupted X lock and authority files
rm -f /home/rekku/.Xauthority /home/rekku/.X*-lock

# Fix .htpasswd permissions if it exists
if [ -f /config/.htpasswd ]; then
  chmod 644 /config/.htpasswd
  echo "[fix-session] ✅ .htpasswd permissions fixed"
else
  echo "[fix-session] ⚠️ .htpasswd not found"
fi

echo "[fix-session] ✅ Done"
