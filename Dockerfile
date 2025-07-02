FROM debian:bookworm

ENV CHROME_BIN=/usr/bin/chromium
ENV CHROMEDRIVER_PATH=/usr/bin/chromedriver
ENV DISPLAY=:0
ENV WEBVIEW_PORT=5005

# Installa Chrome + dipendenze + VNC stack
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-distutils \
    chromium \
    chromium-driver \
    xfce4 \
    x11vnc \
    xvfb \
    dbus \
    dbus-x11 \
    xinit \
    udev \
    websockify \
    wget \
    curl \
    unzip \
    fonts-liberation \
    fonts-dejavu-core \
    fonts-noto-color-emoji \
    libnss3 \
    libx11-6 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libgbm1 \
    libgtk-3-0 \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libdrm2 \
    libxss1 \
    sudo \
    && rm -rf /var/lib/apt/lists/*

# Crea l'utente non privilegiato 'rekku' con sudo senza password
RUN useradd -m -s /bin/bash rekku \
    && echo 'rekku ALL=(ALL) NOPASSWD:ALL' >> /etc/sudoers

# Scarica noVNC
RUN mkdir -p /opt/novnc && \
    wget https://github.com/novnc/noVNC/archive/refs/heads/master.zip -O /tmp/novnc.zip && \
    unzip /tmp/novnc.zip -d /opt && \
    mv /opt/noVNC-master/* /opt/novnc && \
    rm -rf /tmp/novnc.zip

# Copia codice del bot
WORKDIR /app
COPY . .

# Installa dipendenze Python
RUN pip install --no-cache-dir --break-system-packages -r requirements.txt

# Copia script avvio VNC + bot
COPY automation_tools/start-vnc.sh /start-vnc.sh
RUN chmod +x /start-vnc.sh

# VOLUME persistente (se desiderato)
VOLUME ["/app/selenium_profile"]

EXPOSE 5005

CMD ["/start-vnc.sh"]
