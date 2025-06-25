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
	  git \
	  curl \
	  wget \
	  procps && \
	rm -rf /var/lib/apt/lists/*

# Delete user with UID 1000 if exists, then create vscode user
RUN if id -u 1000 >/dev/null 2>&1; then \
		userdel -r $(getent passwd 1000 | cut -d: -f1); \
	fi && \
	adduser --system --group --home /home/vscode vscode && \
	adduser vscode sudo && \
	echo "vscode ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers

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
USER vscode
WORKDIR /home/vscode

# Keep the container running
CMD ["tail", "-f", "/dev/null"]