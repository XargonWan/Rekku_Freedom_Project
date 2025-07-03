#!/bin/bash

# Imposta hostname realistico
hostname luna-workstation

# Imposta DISPLAY virtuale
export DISPLAY=:0

# Imposta password di root e dell'utente rekku se fornita
if [[ -n "$ROOT_PASSWORD" ]]; then
  echo "root:$ROOT_PASSWORD" | chpasswd
  echo "rekku:$ROOT_PASSWORD" | chpasswd
fi

# Imposta HOME corretto per i processi avviati come rekku
export HOME=/home/rekku

# Avvia display virtuale (Xvfb) con risoluzione standard
su -p rekku -c "Xvfb :0 -screen 0 1280x720x24 &"

# Avvia servizi di sistema per un ambiente desktop più realistico
/lib/udev/udevd --daemon >/dev/null 2>&1 || udevd --daemon >/dev/null 2>&1
udevadm trigger &
dbus-daemon --system --fork

# Avvia l'ambiente desktop XFCE completo
su -p rekku -c "dbus-launch --exit-with-session startxfce4 &"

# Imposta browser e terminale predefiniti
su -p rekku -c "xdg-settings set default-web-browser google-chrome.desktop"
ln -sf /usr/bin/google-chrome /usr/bin/xdg-open
su -p rekku -c "exo-preferred-applications --set TerminalEmulator xfce4-terminal" || true

# Assicura che Selenium sia avviato con interfaccia grafica
export REKKU_SELENIUM_HEADLESS=0

# Finge ambiente desktop XFCE
export XDG_CURRENT_DESKTOP=XFCE
export XDG_SESSION_DESKTOP=XFCE

# Avvia server VNC (condivisione e senza password)
su -p rekku -c "x11vnc -display :0 -forever -nopw -shared -rfbport 5900 -bg -cursor arrow"
# Sincronizza gli appunti tra host e VNC
su -p rekku -c "autocutsel -fork"

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
