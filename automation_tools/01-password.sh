#!/usr/bin/with-contenv bash
set -e

HTPASSWD_FILE=/config/.htpasswd

# Ensure /config is writable by the runtime user
chown -R "${PUID:-1000}:${PGID:-1000}" /config || true

if [ ! -f "$HTPASSWD_FILE" ]; then
    USERNAME=${USER:-abc}
    if [ -z "${PASSWORD:-}" ]; then
        echo "[01-password] ERROR: PASSWORD not set" >&2
        exit 1
    fi
    htpasswd -cb "$HTPASSWD_FILE" "$USERNAME" "$PASSWORD"
fi
chmod 644 "$HTPASSWD_FILE"

# Link for nginx if missing
if [ ! -e /etc/nginx/.htpasswd ]; then
    ln -s "$HTPASSWD_FILE" /etc/nginx/.htpasswd
fi
