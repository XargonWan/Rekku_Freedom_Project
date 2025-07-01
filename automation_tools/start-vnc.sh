#!/bin/bash

# Imposta DISPLAY virtuale
export DISPLAY=:0

# Avvia display virtuale (Xvfb)
Xvfb :0 -screen 0 720x1280x24 &

# Avvia window manager (necessario per Chrome GUI)
fluxbox &

# Assicura che Selenium sia avviato con interfaccia grafica
export REKKU_SELENIUM_HEADLESS=0

# Avvia server VNC (condivisione e senza password)
x11vnc -display :0 -forever -nopw -shared -rfbport 5900 -bg

# Avvia noVNC sulla porta pubblica interna configurabile
# Usa versione "vnc.html" che include UI completa
WEB_PORT="${WEBVIEW_PORT:-5005}"
websockify --web=/opt/novnc "$WEB_PORT" localhost:5900 &

# Lancia il bot Python (in parallelo)
exec python main.py
