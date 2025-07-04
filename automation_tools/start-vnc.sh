#!/bin/bash

# Imposta DISPLAY virtuale
export DISPLAY=:0

# Imposta password di root e dell'utente rekku se fornita
if [[ -n "$ROOT_PASSWORD" ]]; then
  echo "root:$ROOT_PASSWORD" | chpasswd
  echo "rekku:$ROOT_PASSWORD" | chpasswd
fi

# Imposta HOME corretto per i processi avviati come rekku
export HOME=/home/rekku

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

# Ensure terminal launcher on desktop
TERM_DESKTOP_SRC="/usr/share/applications/xfce4-terminal.desktop"
TERM_DESKTOP_DST="/home/rekku/Desktop/xfce4-terminal.desktop"
if [ -f "$TERM_DESKTOP_SRC" ]; then
  cp "$TERM_DESKTOP_SRC" "$TERM_DESKTOP_DST"
  chmod +x "$TERM_DESKTOP_DST"
  chown rekku:rekku "$TERM_DESKTOP_DST"
fi

# Ensure Chromium desktop entry
CHROME_DESKTOP_SRC="/usr/share/applications/chromium-browser.desktop"
CHROME_DESKTOP_DST="/home/rekku/Desktop/chromium-browser.desktop"
if [ ! -f "$CHROME_DESKTOP_SRC" ]; then
cat <<'EOF' > "$CHROME_DESKTOP_SRC"
[Desktop Entry]
Name=Chromium
Exec=chromium-browser
Icon=chromium-browser
Type=Application
Categories=Network;WebBrowser;
EOF
chmod 644 "$CHROME_DESKTOP_SRC"
fi
cp "$CHROME_DESKTOP_SRC" "$CHROME_DESKTOP_DST"
chmod +x "$CHROME_DESKTOP_DST"
chown rekku:rekku "$CHROME_DESKTOP_DST"

# Avvia display virtuale (Xvfb) con risoluzione standard
su -p rekku -c "Xvfb :0 -screen 0 1280x720x24 &"

# Avvia servizi di sistema per un ambiente desktop più realistico
/lib/udev/udevd --daemon >/dev/null 2>&1 || udevd --daemon >/dev/null 2>&1
udevadm trigger &
dbus-daemon --system --fork

# Avvia l'ambiente desktop XFCE completo
su -p rekku -c "dbus-launch --exit-with-session startxfce4 &"

# Assicura che Selenium sia avviato con interfaccia grafica
export REKKU_SELENIUM_HEADLESS=0

# Finge ambiente desktop XFCE
export XDG_CURRENT_DESKTOP=XFCE
export XDG_SESSION_DESKTOP=XFCE

# Avvia server VNC (condivisione e senza password)
su -p rekku -c "x11vnc -display :0 -forever -nopw -shared -rfbport 5900 -bg -cursor arrow"

# Avvia noVNC sulla porta pubblica interna configurabile
# Usa versione "vnc.html" che include UI completa
WEB_PORT="${WEBVIEW_PORT:-5005}"
su -p rekku -c "websockify --web=/opt/novnc \"$WEB_PORT\" localhost:5900 &"

# Stampa URL finale per debug
HOST="${WEBVIEW_HOST:-localhost}"
if [[ "$HOST" == "localhost" || "$HOST" == "127.0.0.1" || "$HOST" == "0.0.0.0" ]]; then
  HOST=$(hostname -I | awk '{print $1}')
fi
echo "[INFO] VNC disponibile su http://$HOST:$WEB_PORT/vnc.html"

# Lancia il bot Python (in parallelo)
exec su -p rekku -c "cd /app && python3 main.py"
