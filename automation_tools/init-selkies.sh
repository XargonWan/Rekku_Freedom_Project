#!/usr/bin/with-contenv bash
set -Eeuo pipefail

LOGFILE=/var/log/selkies.log
exec >>"$LOGFILE" 2>&1

echo "[init-selkies] starting"

# require PASSWORD for VNC access
if [ -z "${PASSWORD:-}" ]; then
    echo "[init-selkies] ERROR: PASSWORD not set" >&2
    exit 1
fi

# Start x11vnc if nothing is listening on :5900
if ! ss -lnt | grep -q ':5900'; then
    echo "[init-selkies] launching x11vnc on :5900"
    x11vnc -display "${DISPLAY:-:0}" -forever -rfbport 5900 -passwd "$PASSWORD" -shared &
    sleep 2
fi

# Ensure websockify can bind to 8082
if lsof -i TCP:8082 >/dev/null 2>&1; then
    echo "[init-selkies] port 8082 busy, killing existing instance"
    pkill -f 'websockify.*8082' || true
    sleep 1
fi

echo "[init-selkies] starting websockify"
nohup websockify 0.0.0.0:8082 127.0.0.1:5900 &

echo "[init-selkies] done"
