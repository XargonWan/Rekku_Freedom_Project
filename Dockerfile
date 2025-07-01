FROM python:3.13-slim

ENV CHROME_BIN=/usr/bin/chromium
ENV CHROMEDRIVER_PATH=/usr/bin/chromedriver
ENV DISPLAY=:0
ENV WEBVIEW_PORT=5005

# Installa Chrome + dipendenze + VNC stack
RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium \
    chromium-driver \
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
    wget \
    curl \
    unzip \
    xvfb \
    x11vnc \
    fluxbox \
    xfce4 \
    dbus \
    udev \
    python3-pyqt5 \
    websockify \
    python3-distutils \
    && rm -rf /var/lib/apt/lists/* && \
    echo 'PRETTY_NAME="Ubuntu 22.04.4 LTS"' > /etc/os-release && \
    echo 'NAME="Ubuntu"' >> /etc/os-release && \
    echo 'VERSION_ID="22.04"' >> /etc/os-release && \
    echo 'VERSION="22.04.4 LTS (Jammy Jellyfish)"' >> /etc/os-release && \
    echo 'VERSION_CODENAME=jammy' >> /etc/os-release && \
    echo 'ID=ubuntu' >> /etc/os-release && \
    echo 'ID_LIKE=debian' >> /etc/os-release && \
    echo 'HOME_URL="https://www.ubuntu.com/"' >> /etc/os-release && \
    echo 'SUPPORT_URL="https://help.ubuntu.com/"' >> /etc/os-release && \
    echo 'BUG_REPORT_URL="https://bugs.launchpad.net/ubuntu/"' >> /etc/os-release && \
    echo 'UBUNTU_CODENAME=jammy' >> /etc/os-release && \
    echo 'LOGO=ubuntu-logo' >> /etc/os-release && \
    echo 'DISTRIB_ID=Ubuntu' > /etc/lsb-release && \
    echo 'DISTRIB_RELEASE=22.04' >> /etc/lsb-release && \
    echo 'DISTRIB_CODENAME=jammy' >> /etc/lsb-release && \
    echo 'DISTRIB_DESCRIPTION="Ubuntu 22.04.4 LTS"' >> /etc/lsb-release && \
    echo 'Ubuntu 22.04.4 LTS \n \l' > /etc/issue

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
RUN pip install --no-cache-dir -r requirements.txt

# Copia script avvio VNC + bot
COPY automation_tools/start-vnc.sh /start-vnc.sh
RUN chmod +x /start-vnc.sh

# VOLUME persistente (se desiderato)
VOLUME ["/app/selenium_profile"]

EXPOSE 5005

CMD ["/start-vnc.sh"]