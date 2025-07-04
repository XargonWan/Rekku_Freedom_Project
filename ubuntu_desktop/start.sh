#!/bin/bash
set -e

hostnamectl set-hostname luna-workstation 2>/dev/null || true

export DISPLAY=:0
export HOME=/home/rekku
export PYTHONPATH=/app
export PATH="/opt/venv/bin:$PATH"
export LANG=en_US.UTF-8
WEBVIEW_PORT=${WEBVIEW_PORT:-5005}
WEBVIEW_HOST=${WEBVIEW_HOST:-localhost}

# Ensure Desktop directory exists
mkdir -p /home/rekku/Desktop

# Create chromium wrapper if only Google Chrome is installed
if ! command -v chromium-browser >/dev/null 2>&1 && command -v google-chrome >/dev/null 2>&1; then
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
cat <<'EOF' > "$CHROME_SRC"
[Desktop Entry]
Name=Chromium
Exec=chromium-browser
Icon=chromium-browser
Type=Application
Categories=Network;WebBrowser;
EOF
chmod 644 "$CHROME_SRC"
fi
cp "$CHROME_SRC" "$CHROME_DST"
chmod +x "$CHROME_DST"
chown rekku:rekku "$CHROME_DST"

# Configure passwords if ROOT_PASSWORD is set
if [ -n "$ROOT_PASSWORD" ]; then
  echo "root:$ROOT_PASSWORD" | chpasswd
  echo "rekku:$ROOT_PASSWORD" | chpasswd
fi


# Ensure X11 sockets exist
mkdir -p /tmp/.X11-unix /tmp/.ICE-unix
chmod 1777 /tmp/.X11-unix /tmp/.ICE-unix

# Launch virtual display
su - rekku -c "Xvfb :0 -screen 0 1280x720x24 &"

# Start dbus and udev if available
if command -v dbus-daemon >/dev/null 2>&1; then
  dbus-daemon --system --fork >/dev/null 2>&1 || true
fi
if command -v udevd >/dev/null 2>&1; then
  (udevd --daemon >/dev/null 2>&1 || /lib/systemd/systemd-udevd --daemon >/dev/null 2>&1 || true)
  udevadm trigger >/dev/null 2>&1 || true
fi

# Start XFCE session
su - rekku -c "dbus-launch --exit-with-session startxfce4 &" >/tmp/xfce.log 2>&1

# Set Chrome as default browser
su - rekku -c "xdg-settings set default-web-browser google-chrome.desktop" || true
su - rekku -c "xdg-settings set default-terminal-emulator xfce4-terminal.desktop" || true

# Apply wallpaper if present
if [ -f /usr/share/backgrounds/rekku_night.png ]; then
  su - rekku -c "DISPLAY=:0 xfconf-query --channel xfce4-desktop --property /backdrop/screen0/monitor0/image-path --set /usr/share/backgrounds/rekku_night.png" || true
fi

# Start VNC and clipboard sync
su - rekku -c "x11vnc -display :0 -forever -nopw -shared -rfbport 5900 -bg"
su - rekku -c "autocutsel -fork -selection PRIMARY"
su - rekku -c "autocutsel -fork -selection CLIPBOARD"

# Start noVNC
su - rekku -c "websockify ${WEBVIEW_PORT} localhost:5900 --web=/usr/share/novnc &"

HOST="$WEBVIEW_HOST"
if [[ "$HOST" == "localhost" || "$HOST" == "0.0.0.0" || -z "$HOST" ]]; then
  HOST=$(hostname -I | awk '{print $1}')
fi

echo "VNC URL: http://$HOST:${WEBVIEW_PORT}/vnc.html"

exec su - rekku -c "export PYTHONPATH=/app && python3 /app/main.py"
