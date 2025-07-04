#!/bin/bash
set -e

export DISPLAY=:0
export HOME=/home/rekku
WEBVIEW_PORT=${WEBVIEW_PORT:-5005}
WEBVIEW_HOST=${WEBVIEW_HOST:-localhost}

su -p rekku -c "Xvfb :0 -screen 0 1280x720x24 &"

# Try to start dbus but ignore failures for headless environments
if command -v dbus-daemon >/dev/null 2>&1; then
  dbus-daemon --system --fork || true
fi

# Start XFCE session
su -p rekku -c "startxfce4 &" >/tmp/xfce.log 2>&1

# Start VNC server
su -p rekku -c "x11vnc -display :0 -forever -nopw -shared -rfbport 5900 -bg"

# Clipboard sync
su -p rekku -c "autocutsel -fork"

# Set default wallpaper if available
if [ -f /usr/share/backgrounds/rekku_night.png ]; then
  su -p rekku -c "DISPLAY=:0 xfconf-query -c xfce4-desktop -p /backdrop/screen0/monitor0/image-path -t string -s /usr/share/backgrounds/rekku_night.png" || true
fi

# Start websockify for noVNC
su -p rekku -c "websockify \"${WEBVIEW_PORT}\" localhost:5900 --web=/usr/share/novnc &"

HOST="$WEBVIEW_HOST"
if [[ "$HOST" == "localhost" || "$HOST" == "0.0.0.0" || -z "$HOST" ]]; then
  HOST=$(hostname -I | awk '{print $1}')
fi

echo "VNC URL: http://$HOST:${WEBVIEW_PORT}/vnc.html"

wait -n
