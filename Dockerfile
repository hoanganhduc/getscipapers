# FROM python:3.11-slim
FROM mcr.microsoft.com/devcontainers/base:ubuntu

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

# Install Google Chrome
RUN wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add - && \
	echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list && \
	apt-get update && \
	apt-get install -y --no-install-recommends google-chrome-stable && \
	rm -rf /var/lib/apt/lists/*

# Install latest ChromeDriver
RUN LATEST_CHROMEDRIVER_VERSION=$(curl -sS https://googlechromelabs.github.io/chrome-for-testing/last-known-good-versions-with-downloads.json | python3 -c "import sys, json; print(json.load(sys.stdin)['channels']['Stable']['version'])") && \
	wget -q "https://edgedl.me.gvt1.com/edgedl/chrome/chrome-for-testing/${LATEST_CHROMEDRIVER_VERSION}/linux64/chromedriver-linux64.zip" && \
	unzip chromedriver-linux64.zip && \
	mv chromedriver-linux64/chromedriver /usr/local/bin/ && \
	chmod +x /usr/local/bin/chromedriver && \
	rm -rf chromedriver-linux64 chromedriver-linux64.zip

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