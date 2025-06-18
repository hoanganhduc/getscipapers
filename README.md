# Docker container for running getscipapers

## Description

This Docker container is designed to run the `getscipapers` tool, which allows users to download scientific papers from various sources. The container includes all necessary dependencies and configurations to execute the tool seamlessly.

## Usage

Pull and run the Docker image:

```bash
docker pull ghcr.io/hoanganhduc/getscipapers:latest
docker run -it --rm -v $(pwd):/workspace ghcr.io/hoanganhduc/getscipapers:latest
```

Or build locally:

```bash
docker build -t getscipapers .
docker run -it --rm -v $(pwd):/workspace getscipapers
```

The container will mount your current directory to `/workspace` for file access.