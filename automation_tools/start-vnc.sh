#!/bin/bash

# Imposta DISPLAY virtuale
export DISPLAY=:0

# Imposta password di root e dell'utente rekku se fornita
if [[ -n "$ROOT_PASSWORD" ]]; then
  echo "root:$ROOT_PASSWORD" | chpasswd
  echo "rekku:$ROOT_PASSWORD" | chpasswd
fi

# Avvia display virtuale (Xvfb) con risoluzione standard
su - rekku -c "Xvfb :0 -screen 0 1280x720x24 &"

# Avvia servizi di sistema per un ambiente desktop più realistico
/lib/udev/udevd --daemon >/dev/null 2>&1 || udevd --daemon >/dev/null 2>&1
udevadm trigger &
dbus-daemon --system --fork

# Avvia l'ambiente desktop XFCE completo
su - rekku -c "dbus-launch --exit-with-session startxfce4 &"

# Assicura che Selenium sia avviato con interfaccia grafica
export REKKU_SELENIUM_HEADLESS=0

# Finge ambiente desktop XFCE
export XDG_CURRENT_DESKTOP=XFCE
export XDG_SESSION_DESKTOP=XFCE

# Avvia server VNC (condivisione e senza password)
su - rekku -c "x11vnc -display :0 -forever -nopw -shared -rfbport 5900 -bg -cursor arrow"

# Avvia noVNC sulla porta pubblica interna configurabile
# Usa versione "vnc.html" che include UI completa
WEB_PORT="${WEBVIEW_PORT:-5005}"
su - rekku -c "websockify --web=/opt/novnc \"$WEB_PORT\" localhost:5900 &"

# Stampa URL finale per debug
HOST="${WEBVIEW_HOST:-localhost}"
if [[ "$HOST" == "localhost" || "$HOST" == "127.0.0.1" || "$HOST" == "0.0.0.0" ]]; then
  HOST=$(hostname -I | awk '{print $1}')
fi
echo "[INFO] VNC disponibile su http://$HOST:$WEB_PORT/vnc.html"

# Lancia il bot Python (in parallelo)
exec su - rekku -c "python3 main.py"
