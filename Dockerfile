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

# Install Chromium browser for all architectures (no snap)
RUN apt-get update && \
    apt-get install -y --no-install-recommends jq software-properties-common && \
    ARCH="$TARGETARCH" && \
    echo "Building for architecture: $ARCH" && \
    if [ -z "$ARCH" ]; then \
        echo "Warning: TARGETARCH not set, defaulting to amd64" && \
        ARCH=amd64; \
    fi && \
    echo "Installing Chromium for $ARCH from PPA (no snap)..." && \
    add-apt-repository ppa:xtradeb/apps -y && \
    apt-get update && \
    apt-get install -y --no-install-recommends chromium && \
    apt-get clean && rm -rf /var/lib/apt/lists/* && \
    chromium --version && \
    ln -s /usr/bin/chromium /usr/bin/google-chrome && \
    echo "Chromium installed successfully from PPA for $ARCH"

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
COPY automation_tools/cleanup_chromium.sh /usr/local/bin/cleanup_chromium.sh
COPY automation_tools/container_rekku.sh /usr/local/bin/rekku.sh
RUN chmod +x /usr/local/bin/cleanup_chromium.sh /usr/local/bin/rekku.sh

# Copy project code last to leverage layer caching
COPY . /app
ENV PYTHONPATH=/app

# Inject GitVersion tags into the environment
ENV GITVERSION_TAG=$GITVERSION_TAG
RUN echo "$GITVERSION_TAG" > /app/version.txt && \
    echo "Building with tag: $GITVERSION_TAG"

# Create S6 service for Rekku
# Copy S6 service files (rekku)
COPY s6-services/rekku /etc/s6-overlay/s6-rc.d/rekku
RUN chmod +x /etc/s6-overlay/s6-rc.d/rekku/run && \
    mkdir -p /etc/s6-overlay/s6-rc.d/user/contents.d && \
    echo rekku > /etc/s6-overlay/s6-rc.d/user/contents.d/rekku && \
    chown -R abc:abc /etc/s6-overlay/s6-rc.d/rekku

# Create S6 service dependencies
RUN echo 'longrun' > /etc/s6-overlay/s6-rc.d/rekku/type && \
    mkdir -p /etc/s6-overlay/s6-rc.d/user/contents.d && \
    touch /etc/s6-overlay/s6-rc.d/user/contents.d/rekku

# Set permissions for abc user
RUN chown -R abc:abc /app && \
    chown -R abc:abc /etc/s6-overlay/s6-rc.d/rekku

# Expose port 3000 (selkies default)
EXPOSE 3000
