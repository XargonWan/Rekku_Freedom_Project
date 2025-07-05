FROM lscr.io/linuxserver/webtop:ubuntu-xfce

# Disable Snap and remove leftovers
RUN apt-get update && \
    apt-get purge -y snapd && \
    rm -rf /var/cache/snapd /snap /var/snap /var/lib/snapd && \
    printf '#!/bin/sh\necho "Snap is disabled"\n' > /usr/local/bin/snap && \
    chmod +x /usr/local/bin/snap && \
    echo "alias snap='echo Snap is disabled'" > /etc/profile.d/no-snap.sh && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Install Python tools and create virtual environment
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        python3 python3-venv python3-pip git curl wget && \
    apt-get clean && rm -rf /var/lib/apt/lists/* && \
    python3 -m venv /app/venv && \
    /app/venv/bin/pip install --no-cache-dir -U pip && \
    /app/venv/bin/pip install --no-cache-dir \
        selenium undetected-chromedriver openai python-dotenv

# Install Google Chrome and matching Chromedriver
RUN wget -O /tmp/chrome.deb https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb && \
    apt-get update && apt-get install -y --no-install-recommends /tmp/chrome.deb && \
    rm /tmp/chrome.deb && \
    CHROME_VERSION=$(google-chrome --version | awk '{print $3}' | cut -d'.' -f1) && \
    DRIVER_VERSION=$(curl -sS https://chromedriver.storage.googleapis.com/LATEST_RELEASE_${CHROME_VERSION}) && \
    wget -O /tmp/chromedriver.zip https://chromedriver.storage.googleapis.com/${DRIVER_VERSION}/chromedriver_linux64.zip && \
    unzip /tmp/chromedriver.zip -d /usr/local/bin && \
    chmod +x /usr/local/bin/chromedriver && \
    rm /tmp/chromedriver.zip && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Fonts for Japanese support
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        fonts-noto-cjk fonts-noto-color-emoji && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

ENV PYTHONPATH=/app \
    TZ=Asia/Tokyo \
    PATH=/app/venv/bin:$PATH

WORKDIR /app
COPY . /app

# Supervisor configuration to run the Rekku bot
RUN mkdir -p /config/logs \
    && chown abc:abc /config/logs \
    && chmod 755 /config/logs

COPY rekku.conf /etc/supervisor/conf.d/rekku.conf

CMD ["/init"]
