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

# Remove default abc user and its home if present
RUN set -eux; \
    if id -u abc >/dev/null 2>&1; then \
        abc_home=$(getent passwd abc | cut -d: -f6); \
        userdel abc; \
        groupdel abc || true; \
        rm -rf "$abc_home" || true; \
    fi

# 🔄 FIRST copy all the code
COPY . /app

# Virtualenv + package installation
RUN python3 -m venv /app/venv && \
    /app/venv/bin/pip install --no-cache-dir --upgrade pip setuptools && \
    /app/venv/bin/pip install --no-cache-dir -r /app/requirements.txt

# Variables
ENV PYTHONPATH=/app \
    TZ=Asia/Tokyo \
    PATH=/app/venv/bin:$PATH
ENV USER=rekku
ENV HOME=/home/rekku

WORKDIR /app

# Copy cont-init script so Webtop can start normally
COPY automation_tools/start.sh /etc/cont-init.d/99-rekku.sh
RUN chmod +x /etc/cont-init.d/99-rekku.sh

# Create or update rekku user safely
RUN set -eux; \
    if getent group 1000 >/dev/null; then \
        grp=$(getent group 1000 | cut -d: -f1); \
        if [ "$grp" != "rekku" ]; then groupmod -n rekku "$grp"; fi; \
    elif getent group rekku >/dev/null; then \
        groupmod -g 1000 rekku; \
    else \
        groupadd -g 1000 rekku; \
    fi; \
    if getent passwd 1000 >/dev/null; then \
        usr=$(getent passwd 1000 | cut -d: -f1); \
        if [ "$usr" != "rekku" ]; then \
            usermod -l rekku -d /home/rekku -m "$usr"; \
        fi; \
        usermod -u 1000 -g 1000 -s /bin/bash rekku; \
    elif id -u rekku >/dev/null 2>&1; then \
        usermod -u 1000 -g 1000 -d /home/rekku -s /bin/bash -m rekku; \
    else \
        useradd -m -u 1000 -g 1000 -s /bin/bash rekku; \
    fi; \
    mkdir -p /home/rekku; \
    chown -R 1000:1000 /app /home/rekku

USER rekku

