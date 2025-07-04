#!/bin/bash
set -e

export DISPLAY=:0
export HOME=/home/rekku
export PYTHONPATH=/app
WEBVIEW_PORT=${WEBVIEW_PORT:-5005}
WEBVIEW_HOST=${WEBVIEW_HOST:-localhost}

# Remove snap and prevent reinstall if somehow present
if command -v snap >/dev/null 2>&1; then
  apt-get purge -y snapd >/dev/null 2>&1 || true
  rm -rf /var/cache/snapd /snap /var/snap /var/lib/snapd /etc/systemd/system/snap*
  printf '#!/bin/sh\necho "Snap is disabled"\n' > /usr/local/bin/snap
  chmod +x /usr/local/bin/snap
  echo "alias snap='echo Snap is disabled'" > /etc/profile.d/no-snap.sh
fi

# Set passwords if provided
if [ -n "$ROOT_PASSWORD" ]; then
  echo "root:$ROOT_PASSWORD" | chpasswd
  echo "rekku:$ROOT_PASSWORD" | chpasswd
fi

# Ensure Desktop directory exists
mkdir -p /home/rekku/Desktop

# Create chromium wrapper if only Google Chrome is installed
if command -v chromium-browser >/dev/null 2>&1; then
  CHROME_EXEC="$(command -v chromium-browser)"
  cat <<EOF > /usr/local/bin/chromium-browser
#!/bin/bash
exec "$CHROME_EXEC" --no-sandbox "$@"
EOF
  chmod +x /usr/local/bin/chromium-browser
elif command -v google-chrome >/dev/null 2>&1; then
  cat <<'EOF' > /usr/local/bin/chromium-browser
#!/bin/bash
exec /usr/bin/google-chrome --no-sandbox "$@"
EOF
  chmod +x /usr/local/bin/chromium-browser
fi

# Desktop shortcuts
TERM_SRC="/usr/share/applications/xfce4-terminal.desktop"
TERM_DST="/home/rekku/Desktop/xfce4-terminal.desktop"
if [ -f "$TERM_SRC" ]; then
  cp "$TERM_SRC" "$TERM_DST"
  chmod +x "$TERM_DST"
  chown rekku:rekku "$TERM_DST"
fi

CHROME_SRC="/usr/share/applications/chromium-browser.desktop"
CHROME_DST="/home/rekku/Desktop/chromium-browser.desktop"
if [ ! -f "$CHROME_SRC" ]; then
cat <<'LAUNCHER' > "$CHROME_SRC"
[Desktop Entry]
Version=1.0
Name=Chromium
Exec=chromium-browser
Terminal=false
Type=Application
Icon=chromium-browser
Categories=Network;WebBrowser;
LAUNCHER
  chmod 644 "$CHROME_SRC"
fi
cp "$CHROME_SRC" "$CHROME_DST"
chmod +x "$CHROME_DST"
chown rekku:rekku "$CHROME_DST"

# Set Chromium as default browser
if command -v xdg-settings >/dev/null 2>&1; then
  if su - rekku -c "xdg-settings get default-web-browser" >/dev/null 2>&1; then
    su - rekku -c "xdg-settings set default-web-browser chromium-browser.desktop" || true
  fi
fi

# Ensure XFCE shows desktop icons and wallpaper if present
if command -v xfconf-query >/dev/null 2>&1; then
  su - rekku -c "DISPLAY=:0 xfconf-query --channel xfce4-desktop --property /desktop-icons/style --set THUNAR >/dev/null 2>&1 || true"
  if [ -f /usr/share/backgrounds/rekku_night.png ]; then
    su - rekku -c "DISPLAY=:0 xfconf-query --channel xfce4-desktop --property /backdrop/screen0/monitor0/image-path --set /usr/share/backgrounds/rekku_night.png >/dev/null 2>&1 || true"
  fi
  # Reload desktop to apply settings
  su - rekku -c "DISPLAY=:0 xfdesktop --reload >/dev/null 2>&1 &"
fi

# Ensure X11 sockets
mkdir -p /tmp/.X11-unix /tmp/.ICE-unix
chmod 1777 /tmp/.X11-unix /tmp/.ICE-unix

# Launch Xvfb and desktop services
su - rekku -c "Xvfb :0 -screen 0 1280x720x24 &"
dbus-daemon --system --fork >/dev/null 2>&1
su - rekku -c "dbus-launch --exit-with-session xfce4-session &"

# Start VNC and clipboard sync
su - rekku -c "x11vnc -display :0 -forever -nopw -shared -rfbport 5900 -bg"
su - rekku -c "autocutsel -fork -selection PRIMARY"
su - rekku -c "autocutsel -fork -selection CLIPBOARD"
su - rekku -c "websockify ${WEBVIEW_PORT} localhost:5900 --web=/opt/novnc &"

HOST="$WEBVIEW_HOST"
if [[ "$HOST" == "localhost" || "$HOST" == "0.0.0.0" || -z "$HOST" ]]; then
  HOST=$(hostname -I | awk '{print $1}')
fi

echo "VNC URL: http://$HOST:${WEBVIEW_PORT}/vnc.html"

exec su - rekku -c "export PYTHONPATH=/app && python3 /app/main.py"
