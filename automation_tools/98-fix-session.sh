#!/bin/# Remove corrupted X lock and authority files
rm -f /home/rekku/.Xauthority /home/rekku/.X*-lock

# Fix .htpasswd permissions if it exists
if [ -f /config/.htpasswd ]; then
  chmod 644 /config/.htpasswd
  echo "[fix-session] ✅ .htpasswd permissions fixed"
else
  echo "[fix-session] ⚠️ .htpasswd not found"
fi

echo "[fix-session] ✅ Done"fix-session] 🔧 Starting session fix..."

# Fix ownership and permissions
chown -R 1000:1000 /home/rekku /config
chmod -R u+rwX,g+rwX,o+rX /home/rekku /config

# Remove corrupted X lock and authority files
rm -f /home/rekku/.Xauthority /home/rekku/.X*-lock

# Fix permessi .htpasswd se esiste
if [ -f /config/.htpasswd ]; then
  chmod 644 /config/.htpasswd
  echo "[fix-session] ✅ .htpasswd permissions fixed"
else
  echo "[fix-session] ⚠️ .htpasswd not found"
fi

echo "[fix-session] ✅ Done"
