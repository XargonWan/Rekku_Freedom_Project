#!/usr/bin/with-contenv bash
set -Eeuo pipefail

LOGFILE=/var/log/selkies.log
exec >>"$LOGFILE" 2>&1

echo "[init-selkies] Starting Selkies display"

DISPLAY="${DISPLAY:-:1}"
export DISPLAY

# Launch Xvfb if not already running
if ! pgrep -f "Xvfb $DISPLAY" >/dev/null; then
    echo "[init-selkies] launching Xvfb on $DISPLAY"
    Xvfb "$DISPLAY" -screen 0 1280x720x24 &
    sleep 2
fi

# Launch the XFCE desktop
if ! pgrep -f startxfce4 >/dev/null; then
    echo "[init-selkies] starting XFCE4 session"
    startxfce4 &
    sleep 2
fi

# require PASSWORD for VNC access
if [ -z "${PASSWORD:-}" ]; then
    echo "[init-selkies] ERROR: PASSWORD not set" >&2
    exit 1
fi

# Start x11vnc on the Xvfb display
if ! ss -lnt | grep -q ':5900'; then
    echo "[init-selkies] launching x11vnc on $DISPLAY"
    x11vnc -display "$DISPLAY" -forever -rfbport 5900 -shared -noxdamage -noshm -passwd "$PASSWORD" &
    sleep 2
fi

if ss -lnt | grep -q ':6901'; then
    echo "[init-selkies] existing websockify found on 6901, killing"
    pkill -f 'websockify.*6901' || true
    sleep 1
fi

echo "[init-selkies] starting websockify on port 6901"
websockify --web=/usr/share/novnc/ 0.0.0.0:6901 localhost:5900 &

echo "[init-selkies] done"
