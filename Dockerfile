FROM debian:bookworm

ENV CHROME_BIN=/usr/bin/google-chrome
ENV CHROMEDRIVER_PATH=/usr/local/bin/chromedriver
ENV DISPLAY=:0
ENV WEBVIEW_PORT=5005

# Installa Chrome + dipendenze + VNC stack
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-distutils \
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
    autocutsel \
    xfce4-terminal \
    xdg-utils \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libdrm2 \
    libxss1 \
    sudo \
    && rm -rf /var/lib/apt/lists/*

# Installa Google Chrome stabile e ChromeDriver abbinato
RUN wget -q -O /tmp/google-chrome.deb https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb \
    && apt-get update \
    && apt-get install -y /tmp/google-chrome.deb \
    && rm /tmp/google-chrome.deb \
    && CHROME_VERSION=$(google-chrome --version | awk '{print $3}') \
    && CHROME_MAJOR=$(echo $CHROME_VERSION | cut -d. -f1) \
    && DRIVER_VERSION=$(wget -qO- https://chromedriver.storage.googleapis.com/LATEST_RELEASE_${CHROME_MAJOR}) \
    && wget -q -O /tmp/chromedriver.zip https://chromedriver.storage.googleapis.com/${DRIVER_VERSION}/chromedriver_linux64.zip \
    && unzip -q /tmp/chromedriver.zip -d /usr/local/bin \
    && chmod +x /usr/local/bin/chromedriver \
    && rm /tmp/chromedriver.zip \
    && apt-get purge -y chromium chromium-browser || true \
    && rm -rf /var/lib/apt/lists/*

# Imposta hostname realistico
RUN echo 'luna-workstation' > /etc/hostname

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


EXPOSE 5005

CMD ["/start-vnc.sh"]
