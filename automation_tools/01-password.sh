#!/usr/bin/with-contenv bash
set -e

HTPASSWD_FILE=/config/.htpasswd

# Ensure /config is writable by the runtime user
chown -R "${PUID:-1000}:${PGID:-1000}" /config || true

if [ ! -f "$HTPASSWD_FILE" ]; then
    USERNAME=${USER:-abc}
    htpasswd -bc "$HTPASSWD_FILE" "$USERNAME" "$PASSWORD"
    chmod 644 "$HTPASSWD_FILE"
fi
