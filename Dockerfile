FROM python:3.11-slim

# Metadata for the image
LABEL org.opencontainers.image.title="GetSciPapers"
LABEL org.opencontainers.image.source="https://github.com/hoanganhduc/getscipapers"
LABEL org.opencontainers.image.description="A Python package to get and request scientific papers from various sources"
LABEL org.opencontainers.image.licenses="GPL-3.0"
LABEL org.opencontainers.image.authors="Duc A. Hoang <anhduc.hoang1990@gmail.com>"

# Install system dependencies
RUN apt-get update && apt-get install -y \
	build-essential \
	git \
	curl \
	wget \
	procps \
	&& rm -rf /var/lib/apt/lists/*

# Install IPFS Kubo
# Expose default IPFS ports
EXPOSE 4001 4001/udp 5001 8080

# Create a non-root user and group
RUN adduser --system --group --home /home/getscipaper --uid 1000 getscipaper

# Ensure /home/getscipaper and /home/getscipaper/.ipfs are owned by getscipaper
RUN mkdir -p /home/getscipaper/.ipfs && chown -R getscipaper:getscipaper /home/getscipaper

# Download and install IPFS Kubo
RUN wget https://dist.ipfs.tech/kubo/v0.35.0/kubo_v0.35.0_linux-amd64.tar.gz \
	&& tar -xvzf kubo_v0.35.0_linux-amd64.tar.gz \
	&& cd kubo \
	&& ./install.sh \
	&& cd .. \
	&& rm -rf kubo kubo_v0.35.0_linux-amd64.tar.gz

# Clone and install getscipapers
WORKDIR /app
RUN git clone https://github.com/hoanganhduc/getscipapers.git . \
	&& pip install --upgrade pip \
	&& pip install build \
	&& pip install -r requirements.txt \
	&& python -m build \
	&& pip install -e . \
	&& rm -rf build/ dist/ *.egg-info/ \
	&& find . -type d -name __pycache__ -exec rm -rf {} + \
	&& find . -type f -name "*.pyc" -delete

# Copy custom entrypoint script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Switch to non-root user for initialization
USER getscipaper
WORKDIR /home/getscipaper

# Set IPFS_PATH environment variable
ENV IPFS_PATH /home/getscipaper/.ipfs
RUN ipfs init

# Entrypoint and default command
ENTRYPOINT ["/entrypoint.sh"]
CMD ["bash"]
