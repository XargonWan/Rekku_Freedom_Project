FROM lscr.io/linuxserver/webtop:ubuntu-xfce

# Basic packages and Snap removal
RUN apt-get update && \
    apt-get purge -y snapd && \
    rm -rf /var/cache/snapd /snap /var/snap /var/lib/snapd && \
    printf '#!/bin/sh\necho "Snap is disabled"\n' > /usr/local/bin/snap && \
    chmod +x /usr/local/bin/snap && \
    echo "alias snap='echo Snap is disabled'" > /etc/profile.d/no-snap.sh && \
    apt-get install -y --no-install-recommends software-properties-common && \
    add-apt-repository -y ppa:deadsnakes/ppa && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
      python3.12 python3.12-venv python3.12-distutils \
      git curl wget unzip \
      apache2-utils websockify openssl x11vnc \
      lsb-release ca-certificates fonts-liberation \
      fonts-noto-cjk fonts-noto-color-emoji xfonts-base && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Install Google Chrome (let undetected-chromedriver handle compatibility)
RUN wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /etc/apt/trusted.gpg.d/google-chrome.gpg && \
    echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list && \
    apt-get update && \
    apt-get install -y google-chrome-stable && \
    apt-get clean && rm -rf /var/lib/apt/lists/* && \
    google-chrome --version

# Configure user abc with UID/GID 1000 and custom home
RUN usermod -u 1000 abc && groupmod -g 1000 abc && \
    usermod -d /home/rekku abc && mkdir -p /home/rekku && \
    chown -R abc:abc /home/rekku

# Copy project code
COPY requirements.txt /app/requirements.txt
WORKDIR /app

# Python venv
RUN python3.12 -m venv /app/venv && \
    /app/venv/bin/pip install --no-cache-dir --upgrade pip setuptools && \
    /app/venv/bin/pip install --no-cache-dir -r requirements.txt

# LinuxServer hooks
COPY automation_tools/rekku.sh /etc/cont-init.d/99-rekku.sh
COPY automation_tools/98-fix-session.sh /etc/cont-init.d/98-fix-session.sh
COPY automation_tools/01-password.sh /etc/cont-init.d/01-password.sh
COPY automation_tools/cleanup_chrome.sh /etc/cont-init.d/97-cleanup-chrome.sh
COPY automation_tools/s6-rc.d/rekku /etc/s6-overlay/s6-rc.d/rekku
COPY automation_tools/s6-rc.d/x11vnc /etc/s6-overlay/s6-rc.d/x11vnc
COPY automation_tools/s6-rc.d/websockify /etc/s6-overlay/s6-rc.d/websockify

# Copy project code last to leverage layer caching
COPY . /app

# ENV
ENV PYTHONPATH=/app \
    TZ=Asia/Tokyo \
    PATH=/app/venv/bin:$PATH \
    HOME=/home/rekku \
    PUID=1000 \
    PGID=1000

# Inject GitVersion tags into the environment
ARG GITVERSION_TAG
ENV GITVERSION_TAG=$GITVERSION_TAG

# Example usage of the tag (optional, for demonstration)
RUN echo "Building with tag: $GITVERSION_TAG"

# Save the GitVersion tag to a version file
RUN echo "$GITVERSION_TAG" > /app/version.txt

COPY automation_tools/container_rekku.sh /app/rekku.sh
RUN chmod +x /etc/cont-init.d/99-rekku.sh /etc/cont-init.d/01-password.sh \
        /etc/cont-init.d/98-fix-session.sh \
        /etc/cont-init.d/97-cleanup-chrome.sh \
        /etc/s6-overlay/s6-rc.d/rekku/run \
        /etc/s6-overlay/s6-rc.d/x11vnc/run \
        /etc/s6-overlay/s6-rc.d/websockify/run \
        /app/rekku.sh \
    && mkdir -p /home/rekku /config /etc/s6-overlay/s6-rc.d/user/contents.d \
    && ln -sfn ../rekku /etc/s6-overlay/s6-rc.d/user/contents.d/rekku \
    && ln -sfn ../x11vnc /etc/s6-overlay/s6-rc.d/user/contents.d/x11vnc \
    && ln -sfn ../websockify /etc/s6-overlay/s6-rc.d/user/contents.d/websockify \
    && chown -R abc:abc /app /home/rekku /config

EXPOSE 3000 6901


