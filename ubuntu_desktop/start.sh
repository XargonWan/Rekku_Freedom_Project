#!/bin/bash
set -e

export DISPLAY=:0
export HOME=/home/rekku
export PYTHONPATH=/app
WEBVIEW_PORT=${WEBVIEW_PORT:-5005}
WEBVIEW_HOST=${WEBVIEW_HOST:-localhost}

# set optional root and user password
if [ -n "$ROOT_PASSWORD" ]; then
  echo "root:$ROOT_PASSWORD" | chpasswd
  echo "rekku:$ROOT_PASSWORD" | chpasswd
fi

# start Xvfb display
Xvfb :0 -screen 0 1280x720x24 &

# start dbus and udev silently
if command -v dbus-daemon >/dev/null 2>&1; then
  dbus-daemon --system --fork || true
fi
if command -v udevd >/dev/null 2>&1; then
  (udevd --daemon >/dev/null 2>&1 || /lib/systemd/systemd-udevd --daemon >/dev/null 2>&1 || true)
fi

# start XFCE session
su - rekku -c "dbus-launch --exit-with-session startxfce4 &" >/tmp/xfce.log 2>&1

# set chrome as default browser
su - rekku -c "xdg-settings set default-web-browser google-chrome.desktop" || true

# if wallpaper available set it
if [ -f /usr/share/backgrounds/rekku_night.png ]; then
  su - rekku -c "DISPLAY=:0 xfconf-query --channel xfce4-desktop --property /backdrop/screen0/monitor0/image-path --set /usr/share/backgrounds/rekku_night.png" || true
fi

# start x11vnc and clipboard sync
su - rekku -c "x11vnc -display :0 -forever -nopw -shared -rfbport 5900 -bg"
su - rekku -c "autocutsel -fork"

# start websockify
su - rekku -c "websockify \"${WEBVIEW_PORT}\" localhost:5900 --web=/usr/share/novnc &"

# resolve host for final url
HOST="$WEBVIEW_HOST"
if [[ "$HOST" == "localhost" || "$HOST" == "0.0.0.0" || -z "$HOST" ]]; then
  HOST=$(hostname -I | awk '{print $1}')
fi

echo "VNC URL: http://$HOST:${WEBVIEW_PORT}/vnc.html"

# launch main application
exec su - rekku -c "export PYTHONPATH=/app && python3 /app/main.py"

