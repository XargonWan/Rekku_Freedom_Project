# xubuntu-desktop-fakeuser: container desktop realistico e stealth

FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV DISPLAY=:0
ENV LANG=en_US.UTF-8
ENV LANGUAGE=en_US:en
ENV LC_ALL=en_US.UTF-8
ENV WEBVIEW_PORT=5005

# === Locale + base system ===
RUN apt-get update && apt-get install -y --no-install-recommends \
    sudo dbus-x11 dbus locales wget curl unzip gnupg2 ca-certificates \
    python3 python3-pip python3-distutils \
    xfce4-session xfce4-settings xfce4-panel xfce4-terminal \
    thunar xfdesktop4 xfwm4 xfconf xfce4-notifyd x11vnc xvfb \
    websockify autocutsel xdg-utils exo-utils \
    fonts-noto fonts-noto-cjk fonts-noto-color-emoji fonts-noto-extra fonts-liberation \
    libnss3 libxss1 libxcomposite1 libxdamage1 libxrandr2 libatk1.0-0 libatk-bridge2.0-0 libgtk-3-0 libasound2 \
    libdbus-1-3 libpam-systemd systemd tzdata \
 && locale-gen en_US.UTF-8 \
 && ln -sf /usr/share/zoneinfo/Asia/Tokyo /etc/localtime \
 && echo "Asia/Tokyo" > /etc/timezone \
 && rm -rf /var/lib/apt/lists/*

# === Google Chrome + ChromeDriver ===
RUN wget -q -O /tmp/google-chrome.deb https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb \
 && apt-get update && apt-get install -y /tmp/google-chrome.deb \
 && rm /tmp/google-chrome.deb \
 && CHROME_VERSION=$(google-chrome --version | awk '{print $3}') \
 && CHROME_MAJOR=$(echo $CHROME_VERSION | cut -d. -f1) \
 && DRIVER_VERSION=$(wget -qO- https://chromedriver.storage.googleapis.com/LATEST_RELEASE_${CHROME_MAJOR}) \
 && wget -q -O /tmp/chromedriver.zip https://chromedriver.storage.googleapis.com/${DRIVER_VERSION}/chromedriver_linux64.zip \
 && unzip -q /tmp/chromedriver.zip -d /usr/local/bin \
 && chmod +x /usr/local/bin/chromedriver \
 && rm /tmp/chromedriver.zip \
 && echo '#!/bin/bash\nexec /usr/bin/google-chrome --no-sandbox "$@"' > /usr/local/bin/chrome-launch \
 && chmod +x /usr/local/bin/chrome-launch \
 && xdg-settings set default-web-browser google-chrome.desktop || true

# === User setup ===
RUN useradd -m -s /bin/bash rekku \
 && echo 'rekku ALL=(ALL) NOPASSWD:ALL' >> /etc/sudoers

# === noVNC ===
RUN mkdir -p /opt/novnc \
 && wget https://github.com/novnc/noVNC/archive/refs/heads/master.zip -O /tmp/novnc.zip \
 && unzip /tmp/novnc.zip -d /opt \
 && mv /opt/noVNC-master/* /opt/novnc \
 && rm -rf /tmp/novnc.zip

# === Set hostname realistico ===
RUN echo 'luna-workstation' > /etc/hostname

# === Copy bot + wallpaper ===
COPY main.py requirements.txt /app/
COPY core interface llm_engines config persona /app/
COPY res/rekku_night.png /usr/share/backgrounds/rekku_night.png

# === Python deps ===
RUN pip install --no-cache-dir -r /app/requirements.txt \
 && pip install --no-cache-dir python-dotenv

# === Script di avvio ===
COPY automation_tools/desktop_setup.sh /start.sh
RUN chmod +x /start.sh

WORKDIR /app
EXPOSE 5005

CMD ["/start.sh"]
