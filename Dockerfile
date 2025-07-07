FROM lscr.io/linuxserver/webtop:ubuntu-xfce

# Disable snap
RUN apt-get update && \
    apt-get purge -y snapd && \
    rm -rf /var/cache/snapd /snap /var/snap /var/lib/snapd && \
    printf '#!/bin/sh\necho "Snap is disabled"\n' > /usr/local/bin/snap && \
    chmod +x /usr/local/bin/snap && \
    echo "alias snap='echo Snap is disabled'" > /etc/profile.d/no-snap.sh

# Basic packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip python3-venv git curl wget unzip \
    lsb-release ca-certificates fonts-liberation \
    fonts-noto-cjk fonts-noto-color-emoji && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Remove user abc if exists
RUN if id -u abc >/dev/null 2>&1; then userdel -rf abc; fi

# 🔄 FIRST copy all the code
COPY . /app

# Virtualenv + package installation
RUN python3 -m venv /app/venv && \
    /app/venv/bin/pip install --no-cache-dir --upgrade pip setuptools && \
    /app/venv/bin/pip install --no-cache-dir -r /app/requirements.txt

# Variables
ENV PYTHONPATH=/app \
    TZ=Asia/Tokyo \
    PATH=/app/venv/bin:$PATH \
    USER=rekku \
    HOME=/home/rekku

WORKDIR /app

# Copy startup script
COPY automation_tools/start.sh /start.sh
RUN chmod +x /start.sh

# Create user rekku with fixed UID/GID
RUN set -eux; \
    if getent group rekku >/dev/null 2>&1; then groupdel rekku; fi; \
    groupadd -g 1000 rekku; \
    if id -u rekku >/dev/null 2>&1; then userdel -rf rekku; fi; \
    useradd -m -u 1000 -g 1000 -s /bin/bash rekku

# Ensure permissions for application folders
RUN chown -R rekku:rekku /app /start.sh /home/rekku

USER rekku
ENTRYPOINT ["/start.sh"]
