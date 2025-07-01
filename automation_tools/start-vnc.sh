#!/bin/bash

# Imposta DISPLAY virtuale
export DISPLAY=:0

# Avvia display virtuale (Xvfb)
Xvfb :0 -screen 0 720x1280x24 &

# Avvia window manager (necessario per Chrome GUI)
fluxbox &

# Avvia server VNC (condivisione e senza password)
x11vnc -display :0 -forever -nopw -shared -rfbport 5900 -bg

# Avvia noVNC sulla porta pubblica interna (5005)
# Usa versione "vnc.html" che include UI completa
websockify --web=/opt/novnc 5005 localhost:5900 &

# Lancia il bot Python (in parallelo)
exec python main.py
