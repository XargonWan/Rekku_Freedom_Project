#!/bin/bash

# Imposta DISPLAY virtuale
export DISPLAY=:0
export HOME=/home/rekku
export PYTHONPATH=/app

# Imposta timezone corretto
ln -sf /usr/share/zoneinfo/Asia/Tokyo /etc/localtime
echo "Asia/Tokyo" > /etc/timezone

# Avvia display virtuale (Xvfb) con risoluzione standard
su -p rekku -c "Xvfb :0 -screen 0 1280x720x24 &"
sleep 2

# Avvia servizi di sistema
/lib/udev/udevd --daemon >/dev/null 2>&1 || udevd --daemon >/dev/null 2>&1
udevadm trigger &
dbus-daemon --system --fork

# Avvia XFCE desktop session
su -p rekku -c "dbus-launch --exit-with-session startxfce4 &"
sleep 3

# Imposta applicazioni predefinite
su -p rekku -c "xdg-settings set default-web-browser google-chrome.desktop" || true
ln -sf /usr/bin/google-chrome /usr/bin/xdg-open

# Imposta wallpaper (usando xfconf-query con --create)
su -p rekku -c "xfconf-query --channel xfce4-desktop --property /backdrop/screen0/monitor0/image-path --create --type string --set /usr/share/backgrounds/rekku_night.png" || echo '[WARN] Impossibile impostare wallpaper'

# Clipboard sync
su -p rekku -c "autocutsel -fork -selection PRIMARY"
su -p rekku -c "autocutsel -fork -selection CLIPBOARD"

# Avvia server VNC
su -p rekku -c "x11vnc -display :0 -forever -nopw -shared -rfbport 5900 -bg -cursor arrow"

# Avvia noVNC
WEB_PORT="${WEBVIEW_PORT:-5005}"
su -p rekku -c "websockify --web=/opt/novnc \"$WEB_PORT\" localhost:5900 &"

# Mostra URL di accesso
HOST="${WEBVIEW_HOST:-localhost}"
if [[ "$HOST" == "localhost" || "$HOST" == "127.0.0.1" || "$HOST" == "0.0.0.0" ]]; then
  HOST=$(hostname -I | awk '{print $1}')
fi
echo "[INFO] VNC disponibile su http://$HOST:$WEB_PORT/vnc.html"

# Lancia il bot
exec su -p rekku -c "cd /app && python3 main.py"
