FROM lscr.io/linuxserver/webtop:ubuntu-xfce

# Disabilita snap
RUN apt-get update && \
    apt-get purge -y snapd && \
    rm -rf /var/cache/snapd /snap /var/snap /var/lib/snapd && \
    printf '#!/bin/sh\necho "Snap is disabled"\n' > /usr/local/bin/snap && \
    chmod +x /usr/local/bin/snap && \
    echo "alias snap='echo Snap is disabled'" > /etc/profile.d/no-snap.sh

# Pacchetti di base
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip python3-venv git curl wget unzip \
    lsb-release ca-certificates fonts-liberation \
    fonts-noto-cjk fonts-noto-color-emoji && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# 🔄 PRIMA copia tutto il codice
COPY . /app

# Virtualenv + installazione pacchetti
RUN python3 -m venv /app/venv && \
    /app/venv/bin/pip install --no-cache-dir --upgrade pip setuptools && \
    /app/venv/bin/pip install --no-cache-dir -r /app/requirements.txt

# Variabili
ENV PYTHONPATH=/app \
    TZ=Asia/Tokyo \
    PATH=/app/venv/bin:$PATH

WORKDIR /app

# Copia script di avvio
COPY automation_tools/start.sh /start.sh
RUN chmod +x /start.sh

# Crea utente rekku e assegna permessi
RUN useradd -m -s /bin/bash rekku && \
    chown -R rekku:rekku /app /start.sh /home/rekku

USER rekku
ENTRYPOINT ["/start.sh"]
