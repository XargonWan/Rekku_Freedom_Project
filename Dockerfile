FROM ubuntu:22.04

ENV CHROME_BIN=/usr/bin/google-chrome
ENV CHROMEDRIVER_PATH=/usr/local/bin/chromedriver
ENV DISPLAY=:0
ENV WEBVIEW_PORT=5005

# Remove snap and block future installations
RUN apt-get update && apt-get purge -y snapd && rm -rf /var/cache/snapd /snap /var/snap /var/lib/snapd /etc/systemd/system/snap* \
    && printf '#!/bin/sh\necho "Snap is disabled"\n' > /usr/local/bin/snap \
    && chmod +x /usr/local/bin/snap \
    && echo "alias snap='echo Snap is disabled'" > /etc/profile.d/no-snap.sh

# Install base packages and XFCE desktop
RUN apt-get update && apt-get install -y --no-install-recommends \
    tzdata locales sudo wget curl unzip \
    python3 python3-pip python3-distutils python3-venv \
    xfce4 xfce4-terminal \
    x11vnc xvfb websockify autocutsel xdg-utils \
    dbus dbus-x11 udev \
    fonts-noto-color-emoji fonts-noto-cjk fonts-liberation \
    && sed -i 's/# *en_US.UTF-8 UTF-8/en_US.UTF-8 UTF-8/' /etc/locale.gen \
    && locale-gen \
    && ln -snf /usr/share/zoneinfo/Asia/Tokyo /etc/localtime \
    && echo 'Asia/Tokyo' > /etc/timezone \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install Google Chrome
RUN wget -O /tmp/chrome.deb https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb \
    && apt-get update && apt-get install -y --no-install-recommends /tmp/chrome.deb \
    && rm /tmp/chrome.deb \
    && rm -rf /var/lib/apt/lists/*

# Install ChromeDriver matching Chrome version
RUN set -e; \
    CHROME_VERSION=$(google-chrome --version | awk '{print $3}' | cut -d'.' -f1); \
    DRIVER_VERSION=$(curl -fsSL https://chromedriver.storage.googleapis.com/LATEST_RELEASE_${CHROME_VERSION} || \
                    curl -fsSL https://chromedriver.storage.googleapis.com/LATEST_RELEASE); \
    wget -O /tmp/chromedriver.zip https://chromedriver.storage.googleapis.com/${DRIVER_VERSION}/chromedriver_linux64.zip; \
    unzip /tmp/chromedriver.zip -d /usr/local/bin; \
    chmod +x /usr/local/bin/chromedriver; \
    rm /tmp/chromedriver.zip

# Crea l'utente non privilegiato 'rekku' con sudo senza password
RUN useradd -m -s /bin/bash rekku \
    && echo 'rekku ALL=(ALL:ALL) ALL' > /etc/sudoers.d/rekku \
    && chmod 0440 /etc/sudoers.d/rekku

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
RUN python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install --no-cache-dir -r requirements.txt

# Ensure the virtual environment is used for all commands
ENV PATH="/opt/venv/bin:$PATH"

# Copia script avvio VNC + bot
COPY desktop_setup.sh /start.sh
RUN chmod +x /start.sh

# VOLUME persistente (se desiderato)
VOLUME ["/home/rekku"]

EXPOSE 5005

CMD ["/start.sh"]
