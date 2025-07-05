FROM lscr.io/linuxserver/webtop:ubuntu-xfce

# Disable Snap and clean up leftovers
RUN apt-get update && \
    apt-get purge -y snapd && \
    rm -rf /var/cache/snapd /snap /var/snap /var/lib/snapd && \
    printf '#!/bin/sh\necho "Snap is disabled"\n' > /usr/local/bin/snap && \
    chmod +x /usr/local/bin/snap && \
    echo "alias snap='echo Snap is disabled'" > /etc/profile.d/no-snap.sh

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        python3 python3-pip python3-venv git curl wget unzip \
        supervisor lsb-release ca-certificates fonts-liberation \
        fonts-noto-cjk fonts-noto-color-emoji && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Install Google Chrome (stable, pinned version)
RUN wget -O /tmp/google-chrome.deb https://dl.google.com/linux/chrome/deb/pool/main/g/google-chrome-stable/google-chrome-stable_116.0.5845.96-1_amd64.deb && \
    apt-get install -y --no-install-recommends /tmp/google-chrome.deb && \
    rm /tmp/google-chrome.deb

# Set up Python virtual environment and install dependencies
RUN python3 -m venv /app/venv && \
    /app/venv/bin/pip install --no-cache-dir -U pip && \
    /app/venv/bin/pip install --no-cache-dir \
        selenium undetected-chromedriver \
        openai python-dotenv \
        chromedriver-autoinstaller

# Environment setup
ENV PYTHONPATH=/app \
    TZ=Asia/Tokyo \
    PATH=/app/venv/bin:$PATH

WORKDIR /app
COPY . /app

# HTTP Basic Auth (handled by webtop image)
ARG ROOT_PASSWORD=rekku
ENV CUSTOM_USER=rekku
ENV PASSWORD=${ROOT_PASSWORD}

# Supervisor logs
RUN mkdir -p /config/logs && \
    chown abc:abc /config/logs && \
    chmod 755 /config/logs

COPY rekku.conf /etc/supervisor/conf.d/rekku.conf

# Default command
CMD ["/init"]
