ARG TARGETPLATFORM
FROM --platform=$TARGETPLATFORM lscr.io/linuxserver/webtop:ubuntu-xfce

ARG TARGETARCH

# Temporarily switch to root to create noVNC directory
RUN mkdir -p /usr/share/novnc && \
    echo '<!DOCTYPE html><html><head><title>noVNC</title></head><body><h1>noVNC placeholder</h1></body></html>' > /usr/share/novnc/vnc.html && \
    echo 'index.html' > /usr/share/novnc/index.html && \
    chmod -R 755 /usr/share/novnc && \
    ls -la /usr/share/novnc && \
    echo "noVNC directory created successfully during build"

# Basic packages and Snap removal
RUN apt-get update && \
    apt-get purge -y snapd && \
    rm -rf /var/cache/snapd /snap /var/snap /var/lib/snapd && \
    printf '#!/bin/sh\necho "Snap is disabled"\n' > /usr/local/bin/snap && \
    chmod +x /usr/local/bin/snap && \
    echo "alias snap='echo Snap is disabled'" > /etc/profile.d/no-snap.sh && \
    apt-get install -y --no-install-recommends \
      software-properties-common \
      python3 python3-venv \
      git curl wget unzip nano vim \
      apache2-utils websockify openssl x11vnc \
      lsb-release ca-certificates fonts-liberation \
      fonts-noto-cjk fonts-noto-color-emoji xfonts-base && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Install browser based on architecture
RUN ARCH="$TARGETARCH" && \
    if [ -z "$ARCH" ]; then \
        echo "Warning: TARGETARCH not set, defaulting to amd64" && \
        ARCH=amd64; \
    fi && \
    if [ "$ARCH" = "amd64" ]; then \
        wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /etc/apt/trusted.gpg.d/google-chrome.gpg && \
        echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list && \
        apt-get update && \
        apt-get install -y google-chrome-stable && \
        apt-get clean && rm -rf /var/lib/apt/lists/* && \
        google-chrome --version; \
    elif [ "$ARCH" = "arm64" ]; then \
        apt-get update && \
        apt-get install -y chromium chromium-driver && \
        apt-get clean && rm -rf /var/lib/apt/lists/* && \
        chromium --version && \
        ln -s /usr/bin/chromium /usr/bin/google-chrome; \
    else \
        echo "Warning: unsupported architecture '$ARCH', defaulting to amd64" && \
        wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /etc/apt/trusted.gpg.d/google-chrome.gpg && \
        echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list && \
        apt-get update && \
        apt-get install -y google-chrome-stable && \
        apt-get clean && rm -rf /var/lib/apt/lists/* && \
        google-chrome --version; \
    fi

# Display configuration
ENV DISPLAY=:1
RUN Xvfb :1 -screen 0 1280x720x24 &

# Keyboard configuration
RUN xvfb-run setxkbmap us

# Copy project code
COPY requirements.txt /app/requirements.txt
WORKDIR /app

# Python venv (necessary for webtop environment)
RUN python3 -m venv /app/venv && \
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
ENV PYTHONPATH=/app

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
