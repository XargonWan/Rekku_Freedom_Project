FROM lscr.io/linuxserver/webtop:ubuntu-xfce

# Basic packages and Snap removal
RUN apt-get update && \
    apt-get purge -y snapd && \
    rm -rf /var/cache/snapd /snap /var/snap /var/lib/snapd && \
    printf '#!/bin/sh\necho \"Snap is disabled\"\n' > /usr/local/bin/snap && \
    chmod +x /usr/local/bin/snap && \
    echo \"alias snap='echo Snap is disabled'\" > /etc/profile.d/no-snap.sh && \
    apt-get install -y --no-install-recommends \
      python3 python3-pip python3-venv git curl wget unzip \
      lsb-release ca-certificates fonts-liberation \
      fonts-noto-cjk fonts-noto-color-emoji xfonts-base && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Install Google Chrome
RUN wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /etc/apt/trusted.gpg.d/google-chrome.gpg && \
    echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list && \
    apt-get update && \
    apt-get install -y google-chrome-stable unzip curl

# Install ChromeDriver matching Chrome version
RUN CHROME_VERSION=$(google-chrome --version | grep -oP '\d+\.\d+\.\d+') && \
    DRIVER_VERSION=$(curl -s "https://chromedriver.storage.googleapis.com/LATEST_RELEASE_${CHROME_VERSION}") && \
    curl -s -o /tmp/chromedriver.zip "https://chromedriver.storage.googleapis.com/${DRIVER_VERSION}/chromedriver_linux64.zip" && \
    unzip /tmp/chromedriver.zip -d /usr/local/bin && \
    chmod +x /usr/local/bin/chromedriver && \
    rm /tmp/chromedriver.zip

# Copy project code
COPY . /app
COPY .env /app/.env
WORKDIR /app

# Python venv
RUN python3 -m venv /app/venv && \
    /app/venv/bin/pip install --no-cache-dir --upgrade pip setuptools && \
    /app/venv/bin/pip install --no-cache-dir -r requirements.txt

# ENV
ENV PYTHONPATH=/app \
    TZ=Asia/Tokyo \
    PATH=/app/venv/bin:$PATH \
    HOME=/home/rekku \
    PUID=1000 \
    PGID=1000

# LinuxServer hooks
COPY automation_tools/rekku.sh /etc/cont-init.d/99-rekku.sh
COPY automation_tools/98-fix-session.sh /etc/cont-init.d/98-fix-session.sh
COPY automation_tools/01-password.sh /etc/cont-init.d/01-password.sh
COPY automation_tools/init-selkies.sh /etc/s6-overlay/s6-rc.d/init-selkies/run
COPY automation_tools/init-selkies.type /etc/s6-overlay/s6-rc.d/init-selkies/type
COPY automation_tools/container_rekku.sh /app/rekku.sh
RUN chmod +x /etc/cont-init.d/99-rekku.sh /etc/cont-init.d/01-password.sh \
        /etc/s6-overlay/s6-rc.d/init-selkies/run /etc/cont-init.d/98-fix-session.sh \
        /app/rekku.sh \
    && mkdir -p /home/rekku /config /etc/s6-overlay/s6-rc.d/user/contents.d \
    && ln -sfn ../init-selkies /etc/s6-overlay/s6-rc.d/user/contents.d/init-selkies \
    && chown -R 1000:1000 /app /home/rekku /config

USER root

# Install tools for generating basic auth
RUN apt-get update && \
    apt-get install -y --no-install-recommends apache2-utils websockify openssl x11vnc && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

