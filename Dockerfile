FROM lscr.io/linuxserver/webtop:ubuntu-xfce

# Disable Snap and remove leftovers
RUN apt-get update && \
    apt-get purge -y snapd && \
    rm -rf /var/cache/snapd /snap /var/snap /var/lib/snapd && \
    printf '#!/bin/sh\necho "Snap is disabled"\n' > /usr/local/bin/snap && \
    chmod +x /usr/local/bin/snap && \
    echo "alias snap='echo Snap is disabled'" > /etc/profile.d/no-snap.sh

# Install base tools and supervisor
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        python3 python3-venv python3-pip git curl wget \
        supervisor lsb-release ca-certificates unzip && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Create virtual environment and install Python deps
RUN python3 -m venv /app/venv && \
    /app/venv/bin/pip install --no-cache-dir -U pip && \
    /app/venv/bin/pip install --no-cache-dir \
        selenium undetected-chromedriver openai python-dotenv

# Install Google Chrome 116 and Chromedriver 116
RUN set -e; \
    apt-get update; \
    apt-get install -y --no-install-recommends fonts-liberation; \
    wget -O /tmp/google-chrome.deb https://dl.google.com/linux/chrome/deb/pool/main/g/google-chrome-stable/google-chrome-stable_116.0.5845.96-1_amd64.deb; \
    apt-get install -y --no-install-recommends /tmp/google-chrome.deb; \
    rm /tmp/google-chrome.deb; \
    apt-get clean; \
    rm -rf /var/lib/apt/lists/*; \
    wget -O /tmp/chromedriver.zip https://chromedriver.storage.googleapis.com/116.0.5845.96/chromedriver_linux64.zip; \
    unzip -q /tmp/chromedriver.zip -d /usr/local/bin; \
    chmod +x /usr/local/bin/chromedriver; \
    rm /tmp/chromedriver.zip

# Fonts for Japanese language and emoji
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        fonts-noto-cjk fonts-noto-color-emoji && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Environment setup
ENV PYTHONPATH=/app \
    TZ=Asia/Tokyo \
    PATH=/app/venv/bin:$PATH

WORKDIR /app
COPY . /app

# Imposta utente e password per accesso HTTP basic auth
ARG ROOT_PASSWORD=rekku
ENV CUSTOM_USER=rekku
ENV PASSWORD=${ROOT_PASSWORD}

# Supervisor config for the Rekku bot
RUN mkdir -p /config/logs \
    && chown abc:abc /config/logs \
    && chmod 755 /config/logs

COPY rekku.conf /etc/supervisor/conf.d/rekku.conf

# CMD lasciato come da immagine base per usare /init
CMD ["/init"]
