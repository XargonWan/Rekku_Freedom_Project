#!/bin/bash

# Imposta DISPLAY virtuale
export DISPLAY=:0

# Avvia display virtuale (Xvfb)
Xvfb :0 -screen 0 1920x1080x24 &

# Avvia servizi di sistema per un ambiente desktop più realistico
/lib/udev/udevd --daemon >/dev/null 2>&1 || udevd --daemon >/dev/null 2>&1
udevadm trigger &
dbus-daemon --system --fork

# Avvia un window manager leggero (Openbox)
openbox-session &

# Assicura che Selenium sia avviato con interfaccia grafica
export REKKU_SELENIUM_HEADLESS=0

# Finge ambiente desktop Ubuntu
export XDG_CURRENT_DESKTOP=LXDE
export XDG_SESSION_DESKTOP=LXDE

# Avvia server VNC (condivisione e senza password)
x11vnc -display :0 -forever -nopw -shared -rfbport 5900 -bg

# Avvia noVNC sulla porta pubblica interna configurabile
# Usa versione "vnc.html" che include UI completa
WEB_PORT="${WEBVIEW_PORT:-5005}"
websockify --web=/opt/novnc "$WEB_PORT" localhost:5900 &

# Stampa URL finale per debug
HOST="${WEBVIEW_HOST:-localhost}"
if [[ "$HOST" == "localhost" || "$HOST" == "127.0.0.1" || "$HOST" == "0.0.0.0" ]]; then
  HOST=$(hostname -I | awk '{print $1}')
fi
echo "[INFO] VNC disponibile su http://$HOST:$WEB_PORT/vnc.html"

# Lancia il bot Python (in parallelo)
exec python main.py
