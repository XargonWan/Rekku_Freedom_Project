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
        lsb-release ca-certificates fonts-liberation \
        fonts-noto-cjk fonts-noto-color-emoji && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

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

RUN useradd -m -s /bin/bash rekku

COPY automation_tools/start.sh /start.sh
RUN chmod +x /start.sh && chown rekku:rekku /start.sh /app -R

RUN pip install python-telegram-bot==20.6
RUN pip install --upgrade pip setuptools

USER rekku
ENTRYPOINT ["/start.sh"]
