#!/usr/bin/with-contenv bash
set -e

HTPASSWD_FILE=/config/.htpasswd

# Ensure /config is writable by the runtime user
chown -R "${PUID:-1000}:${PGID:-1000}" /config || true

USERNAME=abc
PASSWD=${PASSWORD:-rekku}

# Create or update the htpasswd entry for abc
if [ ! -f "$HTPASSWD_FILE" ] || ! grep -q "^${USERNAME}:" "$HTPASSWD_FILE"; then
    echo "[01-password] generating $HTPASSWD_FILE for user $USERNAME"
    htpasswd -cb "$HTPASSWD_FILE" "$USERNAME" "$PASSWD"
fi
chmod 644 "$HTPASSWD_FILE"

# Link for nginx if missing
if [ ! -e /etc/nginx/.htpasswd ]; then
    ln -s "$HTPASSWD_FILE" /etc/nginx/.htpasswd
fi
