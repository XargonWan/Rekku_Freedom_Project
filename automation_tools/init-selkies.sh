#!/usr/bin/with-contenv bash
set -Eeuo pipefail

LOGFILE=/var/log/selkies.log
# Redirect stdout and stderr to logfile if possible
if touch "$LOGFILE" 2>/dev/null; then
    exec > >(tee -a "$LOGFILE") 2>&1
fi

echo "[init-selkies] starting" >&2

# ensure we can modify required files
if [ ! -w /etc/nginx ]; then
    echo "[init-selkies] ERROR: cannot write to /etc/nginx" >&2
    exit 1
fi

# 1. Read PASSWORD
if [ -z "${PASSWORD:-}" ]; then
    echo "[init-selkies] ERROR: PASSWORD not set" >&2
    exit 1
fi

# 2. Generate or update htpasswd for user abc
HTPASS=/etc/nginx/.htpasswd
if [ ! -f "$HTPASS" ] || ! grep -q '^abc:' "$HTPASS"; then
    echo "[init-selkies] generating $HTPASS" >&2
    htpasswd -cb "$HTPASS" abc "$PASSWORD"
    chmod 600 "$HTPASS"
else
    echo "[init-selkies] existing $HTPASS found" >&2
fi

# 3. SSL certificate generation
SSL_DIR=/config/ssl
CERT="$SSL_DIR/cert.pem"
KEY="$SSL_DIR/cert.key"
mkdir -p "$SSL_DIR"
if [ ! -f "$CERT" ] || [ ! -f "$KEY" ]; then
    echo "[init-selkies] generating self-signed certificates" >&2
    openssl req -new -x509 -nodes -days 3650 -subj "/CN=selkies" -out "$CERT" -keyout "$KEY"
    chmod 600 "$CERT" "$KEY"
else
    echo "[init-selkies] using existing certificates" >&2
fi

# 4. Start websockify
echo "[init-selkies] launching websockify" >&2
exec websockify 127.0.0.1:8082 127.0.0.1:5900
