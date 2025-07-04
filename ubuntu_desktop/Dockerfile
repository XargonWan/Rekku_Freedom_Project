FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONPATH=/app
ENV WEBVIEW_PORT=5005
ENV LANG=en_US.UTF-8

# Remove snap and block future installations
RUN apt-get update && apt-get purge -y snapd && rm -rf /var/cache/snapd /snap /etc/systemd/system/snap* \
 && printf '#!/bin/sh\necho "Snap is disabled"\n' > /usr/local/bin/snap \
 && chmod +x /usr/local/bin/snap \
 && echo "alias snap='echo Snap is disabled'" > /etc/profile.d/no-snap.sh \
 && apt-get update && apt-get install -y --no-install-recommends \
    tzdata locales sudo wget curl ca-certificates \
    python3 python3-pip \
    xfce4-session xfce4-settings xfce4-panel xfce4-terminal xfdesktop4 \
    xfwm4 xfconf xfce4-notifyd thunar pm-utils \
    x11vnc xvfb websockify autocutsel xdg-utils exo-utils unzip \
    dbus dbus-x11 systemd systemd-sysv udev \
    fonts-noto fonts-noto-cjk fonts-noto-color-emoji fonts-noto-extra fonts-liberation \
 && sed -i 's/# *en_US.UTF-8 UTF-8/en_US.UTF-8 UTF-8/' /etc/locale.gen \
 && locale-gen \
 && ln -snf /usr/share/zoneinfo/Asia/Tokyo /etc/localtime \
 && echo "Asia/Tokyo" > /etc/timezone \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/*

# Install Google Chrome
RUN wget -O /tmp/chrome.deb https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb \
 && apt-get update && apt-get install -y --no-install-recommends /tmp/chrome.deb \
 && rm /tmp/chrome.deb \
 && apt-get clean \
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

# Install noVNC
RUN mkdir -p /usr/share/novnc \
 && wget -O /tmp/novnc.tar.gz https://github.com/novnc/noVNC/archive/v1.4.0.tar.gz \
 && tar xzf /tmp/novnc.tar.gz -C /usr/share/novnc --strip-components=1 \
 && rm /tmp/novnc.tar.gz

# Create user and sudoers entry
RUN useradd -m -s /bin/bash rekku \
 && usermod -aG sudo rekku \
 && echo 'rekku ALL=(ALL:ALL) ALL' > /etc/sudoers.d/rekku \
 && chmod 0440 /etc/sudoers.d/rekku


WORKDIR /app
COPY . /app
RUN chmod +x /app/ubuntu_desktop/start.sh \
 && pip3 install --no-cache-dir -r /app/requirements.txt \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/*

VOLUME ["/home/rekku"]
EXPOSE 5005
CMD ["/app/ubuntu_desktop/start.sh"]
