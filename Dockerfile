FROM debian:bookworm

ENV CHROME_BIN=/usr/bin/google-chrome
ENV CHROMEDRIVER_PATH=/usr/local/bin/chromedriver
ENV DISPLAY=:0
ENV WEBVIEW_PORT=5005

# === Installa Chrome + VNC + Fonts ===
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip python3-distutils \
    xfce4 xfce4-terminal x11vnc xvfb xinit dbus dbus-x11 udev sudo \
    websockify wget curl unzip xdg-utils \
    fonts-liberation fonts-dejavu-core fonts-noto fonts-noto-cjk fonts-noto-color-emoji \
    libnss3 libx11-6 libxcomposite1 libxdamage1 libxrandr2 libgbm1 libgtk-3-0 libasound2 \
    libatk-bridge2.0-0 libatk1.0-0 libdrm2 libxss1 \
    autocutsel \
    && rm -rf /var/lib/apt/lists/*

# === Installa Google Chrome stabile e ChromeDriver compatibile ===
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
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/bin/google-chrome /usr/local/bin/google-chrome \
    && echo '#!/bin/bash\nexec /usr/bin/google-chrome --no-sandbox "$@"' > /usr/local/bin/chrome-launch \
    && chmod +x /usr/local/bin/chrome-launch \
    && xdg-settings set default-web-browser google-chrome.desktop || true

# === Imposta hostname realistico ===
RUN echo 'luna-workstation' > /etc/hostname

# === Crea utente non privilegiato ===
RUN useradd -m -s /bin/bash rekku \
    && echo 'rekku ALL=(ALL) NOPASSWD:ALL' >> /etc/sudoers

# === Scarica noVNC ===
RUN mkdir -p /opt/novnc && \
    wget https://github.com/novnc/noVNC/archive/refs/heads/master.zip -O /tmp/novnc.zip && \
    unzip /tmp/novnc.zip -d /opt && \
    mv /opt/noVNC-master/* /opt/novnc && \
    rm -rf /tmp/novnc.zip

# === Bot code ===
WORKDIR /app
COPY . .

# === Copia wallpaper statico da repo ===
COPY res/rekku_night.png /usr/share/backgrounds/rekku_night.png

# === Python deps ===
RUN pip install --no-cache-dir --break-system-packages -r requirements.txt

# === Script di avvio ===
COPY automation_tools/desktop-setup.sh /desktop-setup.sh
RUN chmod +x /desktop-setup.sh

EXPOSE 5005

CMD ["/desktop-setup.sh"]
