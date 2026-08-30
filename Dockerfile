# FROM python:3.11-slim
# Pinned: the floating :ubuntu tag now resolves to 26.04, which dropped the
# python3.12 packages installed below, so the build fails on every architecture.
FROM mcr.microsoft.com/devcontainers/base:ubuntu-24.04

# Metadata for the image
LABEL org.opencontainers.image.title="GetSciPapers" \
	org.opencontainers.image.source="https://github.com/hoanganhduc/getscipapers" \
	org.opencontainers.image.description="A Python package to get and request scientific papers from various sources" \
	org.opencontainers.image.licenses="GPL-3.0" \
	org.opencontainers.image.authors="Duc A. Hoang <anhduc.hoang1990@gmail.com>"

# Install system dependencies for general use, Python 3.12, Chrome/ChromeDriver, and Docker
RUN apt-get update && \
	apt-get install -y --no-install-recommends \
	  build-essential \
	  git \
	  curl \
	  wget \
	  procps \
	  gnupg \
	  ufw \
	  # Python 3.12 and pip dependencies
	  python3.12 \
	  python3.12-venv \
	  python3.12-dev \
	  python3-pip \
	  python-is-python3 \
	  python3-build \
	  python3-setuptools \
	  # Dependencies for Chrome and ChromeDriver
	  libglib2.0-0 \
	  libnss3 \
	  libfontconfig1 \
	  libx11-xcb1 \
	  libxi6 \
	  libxcomposite1 \
	  libxdamage1 \
	  libxrandr2 \
	  libxtst6 \
	  libxss1 \
	  libatk1.0-0 \
	  libatk-bridge2.0-0 \
	  libgtk-3-0 \
	  fonts-liberation \
	  xdg-utils \
	  unzip \
	  libqpdf-dev && \
	rm -rf /var/lib/apt/lists/*

# Google Chrome and Chrome for Testing publish linux/amd64 builds only, and
# Ubuntu has no working chromium package on arm64 -- chromium-browser there is
# a snap stub that cannot run in a container. Other architectures therefore get
# an image without a browser; everything except the Selenium-driven paths
# (Z-Library login, the browser download route) works the same.
# TARGETARCH is supplied by buildx.
ARG TARGETARCH

# Install Google Chrome
RUN if [ "$TARGETARCH" = "amd64" ]; then \
		wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add - && \
		echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list && \
		apt-get update && \
		apt-get install -y --no-install-recommends google-chrome-stable && \
		rm -rf /var/lib/apt/lists/*; \
	else \
		echo "Skipping Google Chrome: no build for ${TARGETARCH:-this architecture}"; \
	fi

# Install latest ChromeDriver
RUN if [ "$TARGETARCH" = "amd64" ]; then \
		LATEST_CHROMEDRIVER_VERSION=$(curl -sS https://googlechromelabs.github.io/chrome-for-testing/last-known-good-versions-with-downloads.json | python3 -c "import sys, json; print(json.load(sys.stdin)['channels']['Stable']['version'])") && \
		wget -q "https://edgedl.me.gvt1.com/edgedl/chrome/chrome-for-testing/${LATEST_CHROMEDRIVER_VERSION}/linux64/chromedriver-linux64.zip" && \
		unzip chromedriver-linux64.zip && \
		mv chromedriver-linux64/chromedriver /usr/local/bin/ && \
		chmod +x /usr/local/bin/chromedriver && \
		rm -rf chromedriver-linux64 chromedriver-linux64.zip; \
	else \
		echo "Skipping ChromeDriver: no build for ${TARGETARCH:-this architecture}"; \
	fi

# # Create a non-root user and group
# RUN adduser --system --group --home /home/vscode --uid 1000 vscode && \
# 	adduser vscode sudo && \
# 	echo "vscode ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers

# Clone and install getscipapers
WORKDIR /app
RUN git clone https://github.com/hoanganhduc/getscipapers.git . && \
	pip install -r requirements.txt --break-system-packages && \
	python -m build && \
	pip install -e . --break-system-packages && \
	rm -rf build/ dist/ *.egg-info/ && \
	find . -type d -name __pycache__ -exec rm -rf {} + && \
	find . -type f -name "*.pyc" -delete

# Switch to non-root user for initialization
USER vscode
WORKDIR /home/vscode

# Keep the container running
CMD ["tail", "-f", "/dev/null"]