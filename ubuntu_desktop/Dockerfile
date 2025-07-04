FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONPATH=/app
ENV WEBVIEW_PORT=5005

# Locale and timezone
RUN apt-get update && apt-get install -y --no-install-recommends \
    locales tzdata sudo wget curl ca-certificates \
    && sed -i 's/# *en_US.UTF-8 UTF-8/en_US.UTF-8 UTF-8/' /etc/locale.gen \
    && sed -i 's/# *ja_JP.UTF-8 UTF-8/ja_JP.UTF-8 UTF-8/' /etc/locale.gen \
    && locale-gen \
    && ln -snf /usr/share/zoneinfo/Asia/Tokyo /etc/localtime \
    && echo "Asia/Tokyo" > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

# Install XFCE and utilities
RUN apt-get update && apt-get install -y --no-install-recommends \
    xfce4 x11vnc xvfb dbus-x11 websockify autocutsel \
    fonts-noto-cjk fonts-noto-color-emoji \
    && rm -rf /var/lib/apt/lists/*

# Install Google Chrome
RUN wget -O /tmp/chrome.deb https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb \
    && apt-get update && apt-get install -y --no-install-recommends /tmp/chrome.deb \
    && rm /tmp/chrome.deb \
    && rm -rf /var/lib/apt/lists/*

# Install matching chromedriver
RUN CHROME_VERSION=$(google-chrome --version | awk '{print $3}' | cut -d '.' -f1) \
    && DRIVER_VERSION=$(curl -sS https://chromedriver.storage.googleapis.com/LATEST_RELEASE_${CHROME_VERSION}) \
    && wget -O /tmp/chromedriver.zip https://chromedriver.storage.googleapis.com/${DRIVER_VERSION}/chromedriver_linux64.zip \
    && unzip /tmp/chromedriver.zip -d /usr/local/bin \
    && chmod +x /usr/local/bin/chromedriver \
    && rm /tmp/chromedriver.zip

# Install noVNC
RUN mkdir -p /usr/share/novnc \
    && wget -O /tmp/novnc.tar.gz https://github.com/novnc/noVNC/archive/v1.4.0.tar.gz \
    && tar xzf /tmp/novnc.tar.gz -C /usr/share/novnc --strip-components=1 \
    && rm /tmp/novnc.tar.gz

# Create user rekku with sudo access
RUN useradd -m -s /bin/bash rekku \
    && echo 'rekku ALL=(ALL) NOPASSWD:ALL' >> /etc/sudoers

WORKDIR /app
COPY start.sh /start.sh
RUN chmod +x /start.sh

VOLUME ["/home/rekku"]
EXPOSE 5005
CMD ["/start.sh"]
