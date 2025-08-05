ARG TARGETPLATFORM
FROM --platform=$TARGETPLATFORM ghcr.io/linuxserver/baseimage-selkies:ubuntunoble

ARG TARGETARCH
ARG GITVERSION_TAG

# Set version label
ARG BUILD_DATE
ARG VERSION
LABEL build_version="Rekku Freedom Project version:- ${VERSION} Build-date:- ${BUILD_DATE}"
LABEL maintainer="xargonwan"

# Set title for selkies
ENV TITLE="Rekku Freedom Project"

# Block snap completely
RUN echo 'Package: snapd' > /etc/apt/preferences.d/no-snap && \
    echo 'Pin: release a=*' >> /etc/apt/preferences.d/no-snap && \
    echo 'Pin-Priority: -10' >> /etc/apt/preferences.d/no-snap && \
    apt-get update && \
    apt-get purge -y snapd && \
    apt-get autoremove -y && \
    rm -rf /snap /var/snap /var/lib/snapd && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Basic packages and Python setup
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      python3 python3-venv python3-pip \
      git curl wget unzip nano vim \
      lsb-release ca-certificates \
      htop net-tools iputils-ping && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Install XFCE4 desktop environment
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      xfce4 \
      xfce4-goodies \
      xfce4-terminal \
      thunar \
      mousepad \
      dbus-x11 \
      at-spi2-core \
      pulseaudio \
      pavucontrol && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Install browser based on architecture (no snap)
RUN apt-get update && \
    apt-get install -y --no-install-recommends jq && \
    ARCH="$TARGETARCH" && \
    echo "Building for architecture: $ARCH" && \
    if [ -z "$ARCH" ]; then \
        echo "Warning: TARGETARCH not set, defaulting to amd64" && \
        ARCH=amd64; \
    fi && \
    if [ "$ARCH" = "amd64" ]; then \
        echo "Installing Chrome for AMD64..." && \
        wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /etc/apt/trusted.gpg.d/google-chrome.gpg && \
        echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list && \
        apt-get update && \
        apt-get install -y google-chrome-stable && \
        apt-get clean && rm -rf /var/lib/apt/lists/* && \
        google-chrome --version; \
    elif [ "$ARCH" = "arm64" ]; then \
        echo "Installing Chromium for ARM64 from PPA (no snap)..." && \
        apt-get install -y --no-install-recommends software-properties-common && \
        add-apt-repository ppa:xtradeb/apps -y && \
        apt-get update && \
        apt-get install -y --no-install-recommends chromium && \
        apt-get clean && rm -rf /var/lib/apt/lists/* && \
        chromium --version && \
        ln -s /usr/bin/chromium /usr/bin/google-chrome && \
        echo "Chromium installed successfully from PPA"; \
    else \
        echo "Warning: unsupported architecture '$ARCH', defaulting to amd64" && \
        wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /etc/apt/trusted.gpg.d/google-chrome.gpg && \
        echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list && \
        apt-get update && \
        apt-get install -y google-chrome-stable && \
        apt-get clean && rm -rf /var/lib/apt/lists/* && \
        google-chrome --version; \
    fi

# Note: ChromeDriver not needed with nodriver - it handles browser automation natively
# nodriver supports all architectures including ARM64
RUN echo "✅ Using nodriver - no ChromeDriver installation needed (supports all architectures)"

# Copy project code and setup Python environment
COPY requirements.txt /app/requirements.txt
WORKDIR /app

# Python venv for the application
RUN python3 -m venv /app/venv && \
    /app/venv/bin/pip install --no-cache-dir --upgrade pip setuptools && \
    /app/venv/bin/pip install --no-cache-dir -r requirements.txt

# Copy essential automation scripts
COPY automation_tools/cleanup_chrome.sh /usr/local/bin/cleanup_chrome.sh
COPY automation_tools/container_rekku.sh /usr/local/bin/rekku.sh
RUN chmod +x /usr/local/bin/cleanup_chrome.sh /usr/local/bin/rekku.sh

# Copy project code last to leverage layer caching
COPY . /app
ENV PYTHONPATH=/app

# Inject GitVersion tags into the environment
ENV GITVERSION_TAG=$GITVERSION_TAG
RUN echo "$GITVERSION_TAG" > /app/version.txt && \
    echo "Building with tag: $GITVERSION_TAG"

# Create S6 service for Rekku
RUN mkdir -p /etc/s6-overlay/s6-rc.d/rekku && \
    echo '#!/command/with-contenv bash' > /etc/s6-overlay/s6-rc.d/rekku/run && \
    echo 'set -e' >> /etc/s6-overlay/s6-rc.d/rekku/run && \
    echo '' >> /etc/s6-overlay/s6-rc.d/rekku/run && \
    echo '# Wait for X server to be ready' >> /etc/s6-overlay/s6-rc.d/rekku/run && \
    echo 'echo "Waiting for X server to be ready..."' >> /etc/s6-overlay/s6-rc.d/rekku/run && \
    echo 'while ! su abc -c "DISPLAY=:1 xset q >/dev/null 2>&1"; do' >> /etc/s6-overlay/s6-rc.d/rekku/run && \
    echo '    sleep 2' >> /etc/s6-overlay/s6-rc.d/rekku/run && \
    echo '    echo "Still waiting for X server..."' >> /etc/s6-overlay/s6-rc.d/rekku/run && \
    echo 'done' >> /etc/s6-overlay/s6-rc.d/rekku/run && \
    echo 'echo "X server is ready"' >> /etc/s6-overlay/s6-rc.d/rekku/run && \
    echo '' >> /etc/s6-overlay/s6-rc.d/rekku/run && \
    echo '# Clean up any Chrome processes from previous sessions' >> /etc/s6-overlay/s6-rc.d/rekku/run && \
    echo '/usr/local/bin/cleanup_chrome.sh' >> /etc/s6-overlay/s6-rc.d/rekku/run && \
    echo '' >> /etc/s6-overlay/s6-rc.d/rekku/run && \
    echo '# Start Rekku application' >> /etc/s6-overlay/s6-rc.d/rekku/run && \
    echo 'cd /app' >> /etc/s6-overlay/s6-rc.d/rekku/run && \
    echo 'echo "Starting Rekku Freedom Project..."' >> /etc/s6-overlay/s6-rc.d/rekku/run && \
    echo 'exec s6-setuidgid abc /usr/local/bin/rekku.sh run' >> /etc/s6-overlay/s6-rc.d/rekku/run && \
    chmod +x /etc/s6-overlay/s6-rc.d/rekku/run

# Create S6 service dependencies
RUN echo 'longrun' > /etc/s6-overlay/s6-rc.d/rekku/type && \
    mkdir -p /etc/s6-overlay/s6-rc.d/user/contents.d && \
    touch /etc/s6-overlay/s6-rc.d/user/contents.d/rekku

# Set permissions for abc user
RUN chown -R abc:abc /app && \
    chown -R abc:abc /etc/s6-overlay/s6-rc.d/rekku && \
    mkdir -p /usr/share/novnc && \
    chown -R abc:abc /usr/share/novnc

# Expose port 3000 (selkies default)
EXPOSE 3000
