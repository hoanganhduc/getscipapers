FROM python:3.11-slim

# Metadata for the image
LABEL org.opencontainers.image.title="GetSciPapers" \
	org.opencontainers.image.source="https://github.com/hoanganhduc/getscipapers" \
	org.opencontainers.image.description="A Python package to get and request scientific papers from various sources" \
	org.opencontainers.image.licenses="GPL-3.0" \
	org.opencontainers.image.authors="Duc A. Hoang <anhduc.hoang1990@gmail.com>"

# Install system dependencies
RUN apt-get update && \
	apt-get install -y --no-install-recommends \
	  build-essential \
	  git \
	  curl \
	  wget \
	  procps && \
	rm -rf /var/lib/apt/lists/*

# Clone and install getscipapers
WORKDIR /app
RUN git clone https://github.com/hoanganhduc/getscipapers.git . && \
	pip install --upgrade pip && \
	pip install build && \
	pip install -r requirements.txt && \
	python -m build && \
	pip install -e . && \
	rm -rf build/ dist/ *.egg-info/ && \
	find . -type d -name __pycache__ -exec rm -rf {} + && \
	find . -type f -name "*.pyc" -delete

CMD [ "bash" ]
