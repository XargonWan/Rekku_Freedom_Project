#!/usr/bin/with-contenv bash
set -Eeuo pipefail

LOGFILE=/config/logs/selkies.log
mkdir -p "$(dirname "$LOGFILE")"
echo "[SELKIES INIT] Starting..." >> "$LOGFILE"

DISPLAY="${DISPLAY:-:1}"
export DISPLAY

# Launch Xvfb if not already running
if ! pgrep -f "Xvfb $DISPLAY" >/dev/null; then
    echo "[init-selkies] launching Xvfb on $DISPLAY" >> "$LOGFILE"
    Xvfb "$DISPLAY" -screen 0 1280x720x24 &
    sleep 2
fi

# Launch the XFCE desktop
if ! pgrep -f startxfce4 >/dev/null; then
    echo "[init-selkies] starting XFCE4 session" >> "$LOGFILE"
    startxfce4 &
    sleep 2
fi

echo "[init-selkies] done" >> "$LOGFILE"
