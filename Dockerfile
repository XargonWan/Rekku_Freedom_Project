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
      fonts-noto-cjk fonts-noto-color-emoji && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Copy project code
COPY . /app
WORKDIR /app

# Python venv
RUN python3 -m venv /app/venv && \
    /app/venv/bin/pip install --no-cache-dir --upgrade pip setuptools && \
    /app/venv/bin/pip install --no-cache-dir -r /app/requirements.txt

# ENV
ENV PYTHONPATH=/app \
    TZ=Asia/Tokyo \
    PATH=/app/venv/bin:$PATH \
    HOME=/home/rekku

# LinuxServer hooks
COPY automation_tools/rekku.sh /etc/cont-init.d/99-rekku.sh
RUN chmod +x /etc/cont-init.d/99-rekku.sh \
    && mkdir -p /home/rekku \
    && chown -R 1000:1000 /app /home/rekku

USER root

