FROM selenium/standalone-chrome:latest

# Metadata for the image
LABEL org.opencontainers.image.title="GetSciPapers" \
	org.opencontainers.image.source="https://github.com/hoanganhduc/getscipapers" \
	org.opencontainers.image.description="A Python package to get and request scientific papers from various sources" \
	org.opencontainers.image.licenses="GPL-3.0" \
	org.opencontainers.image.authors="Duc A. Hoang <anhduc.hoang1990@gmail.com>"

# Install Python and system dependencies
USER root
RUN apt-get update && \
	apt-get install -y --no-install-recommends \
	  python3 \
	  python3-pip \
	  python3.12-dev \
	  git \
	  curl \
	  wget \
	  procps \
	  build-essential \
	  libqpdf-dev \
	  zlib1g-dev \
	  libjpeg-dev \
	  libxml2-dev \
	  libxslt1-dev \
	  libffi-dev \
	  pkg-config \
	  libssl-dev \
	  libcairo2-dev \
	  libpng-dev && \
	rm -rf /var/lib/apt/lists/*

# Rename user 'seluser' to 'vscode'
RUN usermod -l vscode seluser && \
	usermod -d /home/vscode -m vscode && \
	groupmod -n vscode seluser

# Set permissions for home directory
RUN mkdir -p /home/vscode/.cache /home/vscode/.config && \
	chown -R vscode:vscode /home/vscode/.cache /home/vscode/.config

# Clone and install getscipapers
WORKDIR /app
RUN git clone https://github.com/hoanganhduc/getscipapers.git . && \
	pip3 install --upgrade pip && \
	pip3 install build && \
	pip3 install -r requirements.txt && \
	python3 -m build && \
	pip3 install -e . && \
	rm -rf build/ dist/ *.egg-info/ && \
	find . -type d -name __pycache__ -exec rm -rf {} + && \
	find . -type f -name "*.pyc" -delete

# Install additional Selenium dependencies
RUN pip3 install selenium webdriver-manager

# Set environment variables for Selenium
ENV DISPLAY=:99 \
	PYTHONDONTWRITEBYTECODE=1 \
	PYTHONUNBUFFERED=1

# Switch to non-root user
USER seluser
WORKDIR /home/seluser

# Keep the container running
CMD ["tail", "-f", "/dev/null"]