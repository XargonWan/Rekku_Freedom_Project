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

# Install ChromeDriver (integrating the logic from install_chromedriver.sh)
RUN DEST="/usr/local/bin/chromedriver" && \
    ARCH="$TARGETARCH" && \
    if [ "$ARCH" = "arm64" ]; then \
        echo "Installing ChromeDriver for Chromium on ARM64..." && \
        # For ARM64 Chromium, we need to install chromedriver manually
        CHROME_VERSION=$(chromium --version | sed -nre 's/^Chromium ([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+).*/\1/p') && \
        echo "Detected Chromium version: $CHROME_VERSION" && \
        MAJOR=$(echo "$CHROME_VERSION" | cut -d. -f1) && \
        MINOR=$(echo "$CHROME_VERSION" | cut -d. -f2) && \
        BUILD=$(echo "$CHROME_VERSION" | cut -d. -f3) && \
        if [ "$MAJOR" -ge 115 ]; then \
            REGEX="^${MAJOR}\\\\.${MINOR}\\\\.${BUILD}\\\\." && \
            URL=$(wget -qO- https://googlechromelabs.github.io/chrome-for-testing/known-good-versions-with-downloads.json \
                | jq -r '.versions[] | select(.version | test("'"$REGEX"'")) | .downloads.chromedriver[] | select(.platform == "linux64") | .url' \
                | tail -1) && \
            if [ -z "$URL" ]; then \
                echo "❌ No matching ChromeDriver URL found for version $CHROME_VERSION" && \
                exit 1; \
            fi && \
            VERSION=$(echo "$URL" | sed -nre 's!.*/([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)/.*!\1!p') && \
            SRCFILE=chromedriver-linux64/chromedriver; \
        else \
            SHORT="${BUILD}" && \
            VERSION=$(wget -qO- "https://chromedriver.storage.googleapis.com/LATEST_RELEASE_${SHORT}") && \
            URL="https://chromedriver.storage.googleapis.com/${VERSION}/chromedriver_linux64.zip" && \
            SRCFILE=chromedriver; \
        fi && \
        echo "📦 Installing ChromeDriver version ${VERSION} for Chromium ${CHROME_VERSION}" && \
        TMPDIR=$(mktemp -d) && \
        ZIPFILE="${TMPDIR}/chromedriver.zip" && \
        wget -q -O "$ZIPFILE" "$URL" && \
        unzip -q "$ZIPFILE" -d "$TMPDIR" && \
        mv "${TMPDIR}/${SRCFILE}" "$DEST" && \
        chmod +x "$DEST" && \
        rm -rf "$TMPDIR" && \
        echo "✅ ChromeDriver installed to ${DEST}"; \
    else \
        VERSION_STRING=$(google-chrome --version) && \
        CVER=$(echo "$VERSION_STRING" | sed -nre 's/^Google Chrome ([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)\s*$/\1/p') && \
        if [ -z "$CVER" ]; then \
            echo "❌ Failed to parse Chrome version: $VERSION_STRING" && \
            exit 1; \
        fi && \
        MAJOR=$(echo "$CVER" | cut -d. -f1) && \
        MINOR=$(echo "$CVER" | cut -d. -f2) && \
        BUILD=$(echo "$CVER" | cut -d. -f3) && \
        if [ "$MAJOR" -ge 115 ]; then \
            REGEX="^${MAJOR}\\\\.${MINOR}\\\\.${BUILD}\\\\." && \
            URL=$(wget -qO- https://googlechromelabs.github.io/chrome-for-testing/known-good-versions-with-downloads.json \
                | jq -r '.versions[] | select(.version | test("'"$REGEX"'")) | .downloads.chromedriver[] | select(.platform == "linux64") | .url' \
                | tail -1) && \
            if [ -z "$URL" ]; then \
                echo "❌ No matching ChromeDriver URL found" && \
                exit 1; \
            fi && \
            VERSION=$(echo "$URL" | sed -nre 's!.*/([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)/.*!\1!p') && \
            SRCFILE=chromedriver-linux64/chromedriver; \
        else \
            SHORT="${BUILD}" && \
            VERSION=$(wget -qO- "https://chromedriver.storage.googleapis.com/LATEST_RELEASE_${SHORT}") && \
            URL="https://chromedriver.storage.googleapis.com/${VERSION}/chromedriver_linux64.zip" && \
            SRCFILE=chromedriver; \
        fi && \
        echo "📦 Installing ChromeDriver version ${VERSION} for Chrome ${CVER}" && \
        TMPDIR=$(mktemp -d) && \
        ZIPFILE="${TMPDIR}/chromedriver.zip" && \
        wget -q -O "$ZIPFILE" "$URL" && \
        unzip -q "$ZIPFILE" -d "$TMPDIR" && \
        mv "${TMPDIR}/${SRCFILE}" "$DEST" && \
        chmod +x "$DEST" && \
        rm -rf "$TMPDIR" && \
        echo "✅ ChromeDriver installed to ${DEST}"; \
    fi

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

# Create autostart script to run rekku
RUN mkdir -p /defaults && \
    echo '#!/bin/bash' > /defaults/autostart && \
    echo '# Clean up any Chrome processes from previous sessions' >> /defaults/autostart && \
    echo '/usr/local/bin/cleanup_chrome.sh' >> /defaults/autostart && \
    echo '# Start Rekku application' >> /defaults/autostart && \
    echo 'exec /usr/local/bin/rekku.sh run --as-service' >> /defaults/autostart && \
    chmod +x /defaults/autostart

# Set permissions for abc user
RUN chown -R abc:abc /app /defaults

# Expose port 3000 (selkies default)
EXPOSE 3000
