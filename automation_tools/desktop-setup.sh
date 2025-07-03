#!/bin/bash

# === Imposta hostname realistico ===
hostname luna-workstation

# === Imposta DISPLAY virtuale ===
export DISPLAY=:0

# === Imposta password di root e dell'utente rekku (se fornita) ===
if [[ -n "$ROOT_PASSWORD" ]]; then
  echo "root:$ROOT_PASSWORD" | chpasswd
  echo "rekku:$ROOT_PASSWORD" | chpasswd
fi

# === Imposta HOME corretto per processi avviati come rekku ===
export HOME=/home/rekku

# === Avvia display virtuale con risoluzione standard ===
su -p rekku -c "Xvfb :0 -screen 0 1280x720x24 &"

# === Avvia servizi di sistema realistici ===
/lib/udev/udevd --daemon >/dev/null 2>&1 || udevd --daemon >/dev/null 2>&1
udevadm trigger &
dbus-daemon --system --fork

# === Avvia ambiente desktop XFCE ===
su -p rekku -c "dbus-launch --exit-with-session startxfce4 &"

# === Imposta browser predefinito e terminale ===
su -p rekku -c "xdg-settings set default-web-browser google-chrome.desktop"
ln -sf /usr/local/bin/google-chrome /usr/bin/xdg-open
su -p rekku -c "exo-preferred-applications --set TerminalEmulator xfce4-terminal" || true

# === Finge ambiente desktop XFCE ===
export XDG_CURRENT_DESKTOP=XFCE
export XDG_SESSION_DESKTOP=XFCE

# === Imposta wallpaper (da /usr/share) ===
WALLPAPER_PATH="/usr/share/backgrounds/rekku_night.png"
if [[ -f "$WALLPAPER_PATH" ]]; then
  echo "[INFO] Imposto wallpaper da $WALLPAPER_PATH"
  su -p rekku -c "xfconf-query --channel xfce4-desktop \
                  --property /backdrop/screen0/monitor0/image-path \
                  --set \"$WALLPAPER_PATH\"" || echo "[WARN] Impossibile impostare wallpaper"
else
  echo "[WARN] Wallpaper non trovato: $WALLPAPER_PATH"
fi

# === Assicura che Selenium usi GUI ===
export REKKU_SELENIUM_HEADLESS=0

# === Avvia VNC server ===
su -p rekku -c "x11vnc -display :0 -forever -nopw -shared -rfbport 5900 -bg -cursor arrow"

# === Clipboard bidirezionale ===
su -p rekku -c "autocutsel -fork -selection PRIMARY"
su -p rekku -c "autocutsel -fork -selection CLIPBOARD"

# === Avvia noVNC (con UI completa) ===
WEB_PORT="${WEBVIEW_PORT:-5005}"
su -p rekku -c "websockify --web=/opt/novnc \"$WEB_PORT\" localhost:5900 &"

# === Mostra URL di accesso ===
HOST="${WEBVIEW_HOST:-localhost}"
if [[ "$HOST" == "localhost" || "$HOST" == "127.0.0.1" || "$HOST" == "0.0.0.0" ]]; then
  HOST=$(hostname -I | awk '{print $1}')
fi
echo "[INFO] VNC disponibile su http://$HOST:$WEB_PORT/vnc.html"

# === Avvia il bot Python (in parallelo) ===
exec su -p rekku -c "cd /app && python3 main.py"
