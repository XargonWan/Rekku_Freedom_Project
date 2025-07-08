#!/usr/bin/with-contenv bash
set -Eeuo pipefail

LOGFILE=/var/log/selkies.log
# Redirect stdout and stderr to logfile if possible
if touch "$LOGFILE" 2>/dev/null; then
    exec > >(tee -a "$LOGFILE") 2>&1
fi

if [ "$(id -u)" != "0" ] && [ ! -w /etc/nginx ]; then
    echo "Insufficient privileges to modify /etc/nginx" >&2
    exit 1
fi

# 1. Read PASSWORD
: "${PASSWORD:?PASSWORD environment variable not set}"

HTPASS=/etc/nginx/.htpasswd
if [ ! -f "$HTPASS" ]; then
    htpasswd -cb "$HTPASS" abc "$PASSWORD"
    chmod 600 "$HTPASS"
fi

SSL_DIR=/config/ssl
mkdir -p "$SSL_DIR"
CERT="$SSL_DIR/cert.pem"
KEY="$SSL_DIR/cert.key"
if [ ! -f "$CERT" ] || [ ! -f "$KEY" ]; then
    openssl req -new -x509 -nodes -days 3650 \
        -subj "/CN=selkies" \
        -out "$CERT" \
        -keyout "$KEY"
    chmod 600 "$CERT" "$KEY"
fi

exec websockify 127.0.0.1:8082 127.0.0.1:5900
