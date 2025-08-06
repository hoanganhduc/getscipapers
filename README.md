# getscipapers ![🐍](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python) ![🐳](https://img.shields.io/badge/Docker-ready-blue?logo=docker) ![🐙](https://img.shields.io/badge/GitHub-Repo-black?logo=github) ![🚧](https://img.shields.io/badge/status-work--in--progress-yellow) ![📝](https://img.shields.io/github/license/hoanganhduc/getscipapers) ![📚](https://img.shields.io/badge/Papers-Search-orange?logo=read-the-docs) ![☁️](https://img.shields.io/badge/Cloud-Ready-blue?logo=cloud)

## Description ![ℹ️](https://img.shields.io/badge/-Info-informational?logo=info) ![🚀](https://img.shields.io/badge/-WIP-yellow?logo=rocket) ![🧪](https://img.shields.io/badge/-Experimental-lightgrey?logo=flask)

**getscipapers** is a Python package for searching and requesting scientific papers from various sources. This project is a **work in progress** and primarily intended for **my personal use**. It is not a comprehensive solution for accessing scientific papers. Parts of the code were developed with assistance from [GitHub Copilot](https://github.com/features/copilot).

## Prerequisites ![✅](https://img.shields.io/badge/-Checklist-success?logo=checkmarx) ![🛠️](https://img.shields.io/badge/-Tools-blue?logo=tools) ![🔑](https://img.shields.io/badge/-Keys-orange?logo=keybase)

* **(Optional)** ![🧊](https://img.shields.io/badge/IPFS-Kubo-green?logo=ipfs) Install [IPFS Kubo](https://docs.ipfs.tech/install/command-line/) to access the [Nexus Search](https://www.reddit.com/r/science_nexus) database:
  ```bash
  wget https://dist.ipfs.tech/kubo/v0.35.0/kubo_v0.35.0_linux-amd64.tar.gz
  tar -xvzf kubo_v0.35.0_linux-amd64.tar.gz
  cd kubo
  sudo ./install.sh
  ```
  ![💻](https://img.shields.io/badge/-Terminal-black?logo=gnubash) Verify installation:
  ```bash
  ipfs --version
  ```
  ![✈️](https://img.shields.io/badge/Telegram-Bot-blue?logo=telegram) Alternatively, you can interact with the Nexus Telegram bot. To do so, create a Telegram account and obtain your API ID and API hash from [my.telegram.org](https://my.telegram.org/).

* **(Optional)** ![🔑](https://img.shields.io/badge/API-Keys-orange?logo=keybase) Obtain free API keys from [Elsevier](https://dev.elsevier.com/), [Wiley](https://onlinelibrary.wiley.com/library-info/resources/text-and-datamining), or [IEEE](https://developer.ieee.org/getting_started) (IEEE support not yet implemented).

* **(Optional)** ![👤](https://img.shields.io/badge/Accounts-Required-lightgrey?logo=accountcircle) Create accounts at [Sci-Net](https://sci-net.xyz), [AbleSci](https://ablesci.com), [Science Hub Mutual Aid](https://www.pidantuan.com/), [Z-Library](https://z-library.sk/) or [Facebook](https://www.facebook.com/) to request or download papers/books. For Facebook, join the relevant group after creating your account.

* ![🐍](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python) Install [Python](https://www.python.org) (version 3.10 or later).

## Installation ![⬇️](https://img.shields.io/badge/-Install-green?logo=addthis) ![🧪](https://img.shields.io/badge/-Virtualenv-blue?logo=python) ![⚙️](https://img.shields.io/badge/-Setup-lightgrey?logo=settings)

It is recommended to use a virtual environment to avoid conflicts with other Python packages. You can use `venv` or `virtualenv`. To set up the environment and install dependencies:

```bash
# Clone the repository
git clone https://github.com/hoanganhduc/getscipapers.git
cd getscipapers

# Create and activate a virtual environment (change the path if desired)
python -m venv ~/.getscipapers
source ~/.getscipapers/bin/activate

# Upgrade pip and install dependencies
pip install --upgrade pip
pip install build
pip install -r requirements.txt

# Build and install the package in editable mode
python -m build
pip install -e .

# Clean up build artifacts
rm -rf build/ dist/ *.egg-info/
find . -type d -name __pycache__ -exec rm -rf {} +
find . -type f -name "*.pyc" -delete
```

## Usage ![📖](https://img.shields.io/badge/-Usage-blue?logo=read-the-docs) ![💻](https://img.shields.io/badge/-CLI-black?logo=gnubash) ![🔍](https://img.shields.io/badge/-Search-orange?logo=search)

If you want to use the Nexus Search database, start the IPFS daemon (if this is the first time running IPFS daemon, run `ipfs init` first) in one terminal:

```bash
ipfs daemon
```

In another terminal, use the `getscipapers` command to search for and request scientific papers. For usage details, run:

```bash
getscipapers --help
```

# Running getscipapers in GitHub Codespace ![💻](https://img.shields.io/badge/GitHub-Codespaces-blue?logo=github) ![☁️](https://img.shields.io/badge/Cloud-Dev-blue?logo=cloud) ![⚡](https://img.shields.io/badge/-Fast-lightgrey?logo=zap)

The fastest way to run `getscipapers` is to use the GitHub Codespaces feature. This allows you to run the tool in a preconfigured environment without needing to set up anything locally. To use it, follow these steps:

1. ![🍴](https://img.shields.io/badge/-Fork-black?logo=github) Fork the repository to your GitHub account.
2. ![🔐](https://img.shields.io/badge/-Secrets-yellow?logo=github) (Optional) Set up codespace secrets for your API keys and other configurations. You can look at the [.devcontainer/set-secrets.sh](.devcontainer/set-secrets.sh) file to see what I did to set up the secrets using [GitHub CLI](https://cli.github.com/).
3. ![💻](https://img.shields.io/badge/-Codespace-blue?logo=github) Create a new codespace from your forked repository. This will automatically set up the environment with all dependencies installed. You can also use [GitHub CLI](https://cli.github.com/) to create a codespace using (for example) the following command:

   ```bash
   gh codespace create --repo hoanganhduc/getscipapers --branch master --machine basicLinux32gb
   ```
   ![ℹ️](https://img.shields.io/badge/-Info-informational?logo=info) For your information, the `basicLinux32gb` machine type allows you to run with 2 cores, 8GB RAM, and 32GB storage. More information about machine types can be found in the [GitHub Codespaces documentation](https://docs.github.com/en/codespaces/developing-in-a-codespace/creating-a-codespace-for-a-repository). Some other machine types you may use are `standardLinux32gb`, `premiumLinux`, and `largePremiumLinux`.
4. ![💻](https://img.shields.io/badge/-Terminal-black?logo=gnubash) Once the codespace is ready, you can open a terminal in the codespace and run `getscipapers` commands directly.

# Docker Container for Running getscipapers ![🐳](https://img.shields.io/badge/-Docker-blue?logo=docker) ![📦](https://img.shields.io/badge/-Container-green?logo=docker) ![🔒](https://img.shields.io/badge/-Isolated-lightgrey?logo=lock)

## Overview ![ℹ️](https://img.shields.io/badge/-Overview-informational?logo=info) ![📄](https://img.shields.io/badge/-Docs-lightgrey?logo=read-the-docs)

This guide explains how to use the `getscipapers` tool inside a Docker container. The container includes all necessary dependencies, so you can start downloading scientific papers immediately—no manual setup required.

## Quick Start ![⚡](https://img.shields.io/badge/-Quick%20Start-yellow?logo=zap) ![🚀](https://img.shields.io/badge/-Start-blue?logo=rocket)

### 1. Pull and Run the Prebuilt Image ![⬇️](https://img.shields.io/badge/-Pull-blue?logo=docker) ![🏗️](https://img.shields.io/badge/-Ready-green?logo=check)

To get started quickly, pull the latest image from GitHub Container Registry and run it:

```bash
docker pull ghcr.io/hoanganhduc/getscipapers:latest
docker run -it --rm -v $(pwd):/workspace ghcr.io/hoanganhduc/getscipapers:latest
```

This mounts your current directory to `/workspace` inside the container, so you can easily access your files.

### 2. Build and Run Locally ![🏗️](https://img.shields.io/badge/-Build-blue?logo=docker) ![🛠️](https://img.shields.io/badge/-Local-green?logo=homeassistant)

If you want to build the image yourself:

```bash
docker build -t getscipapers .
docker run -it --rm -v $(pwd):/workspace getscipapers
```

### 3. Run in Detached Mode with Persistent Storage ![💾](https://img.shields.io/badge/-Persistent%20Storage-green?logo=storage) ![🔄](https://img.shields.io/badge/-Detached-blue?logo=autorenew)

To keep the container running in the background and ensure your downloads and configuration persist:

```bash
docker run -d \
    --name getscipapers-container \
    --restart always \
    -v $HOME/Downloads:/home/getscipaper/Downloads \
    -v $HOME/.config/getscipapers:/home/getscipaper/.config/getscipapers \
    ghcr.io/hoanganhduc/getscipapers:latest
```

This setup saves downloaded papers and settings to your host machine. You can change the folder paths as needed.

## Optional: Integrate with IPFS ![🧊](https://img.shields.io/badge/IPFS-Kubo-green?logo=ipfs) ![🔗](https://img.shields.io/badge/-Integration-blue?logo=link)

To use IPFS with getscipapers, run an IPFS Kubo daemon in a separate container:

```bash
docker pull ipfs/kubo:latest
sudo ufw allow 4001
sudo ufw allow 8080
sudo ufw allow 5001

export ipfs_staging=$HOME/.ipfs
export ipfs_data=$HOME/.ipfs

docker run -d \
    --name ipfs_host \
    --restart always \
    -v $ipfs_staging:/export \
    -v $ipfs_data:/data/ipfs \
    -p 4001:4001 \
    -p 8080:8080 \
    -p 5001:5001 \
    ipfs/kubo:latest
```

This starts the IPFS daemon with persistent storage and the required ports. You can change the folder paths as needed.

## Running getscipapers Commands ![💻](https://img.shields.io/badge/-CLI-black?logo=gnubash) ![⚙️](https://img.shields.io/badge/-Exec-blue?logo=terminal)

To run `getscipapers` inside the container, use:

```bash
docker exec -it getscipapers-container getscipapers --help
```

### Optional: Create a Convenience Script ![📜](https://img.shields.io/badge/-Script-blue?logo=gnubash) ![⚡](https://img.shields.io/badge/-Shortcut-yellow?logo=zap)

For easier access, create a script at `~/.local/bin/getscipapers`:

```bash
#!/bin/bash
CONTAINER_NAME="getscipapers-container"

if [ $# -lt 1 ]; then
    echo "Usage: $0 [arguments...]"
    exit 1
fi

COMMAND=("getscipapers" "$@")

if ! command -v docker &> /dev/null; then
    echo "Error: Docker is not installed"
    exit 1
fi

if ! docker ps -q -f name="$CONTAINER_NAME" | grep -q .; then
    echo "Error: Container '$CONTAINER_NAME' is not running"
    exit 1
fi

docker exec -i "$CONTAINER_NAME" "${COMMAND[@]}"
```

Make it executable:

```bash
chmod +x ~/.local/bin/getscipapers
```

Now you can run `getscipapers` directly from your terminal:

```bash
getscipapers --help
```

---

For more information, see the official documentation or repository.

### Running Locally with Docker ![🐳](https://img.shields.io/badge/-Docker-blue?logo=docker) ![🏠](https://img.shields.io/badge/-Local-green?logo=homeassistant) ![🔒](https://img.shields.io/badge/-Isolated-lightgrey?logo=lock)

You can run **getscipapers** locally using Docker without installing Python or dependencies on your system.

1. ![🐳](https://img.shields.io/badge/-Docker-blue?logo=docker) Ensure Docker is installed.
2. ![⬇️](https://img.shields.io/badge/-Pull-blue?logo=docker) Pull the latest image:

  ```bash
  docker pull ghcr.io/hoanganhduc/getscipapers:latest
  ```

3. ![▶️](https://img.shields.io/badge/-Run-green?logo=playstation) Run the container, mounting a local directory for downloads or configuration:

  ```bash
  docker run --rm -it -v /path/to/local/dir:/data ghcr.io/hoanganhduc/getscipapers:latest --output /data
  ```

  Replace `/path/to/local/dir` with your preferred local directory.

This setup allows you to use **getscipapers** in an isolated environment, keeping your files accessible on your host machine.

## Remarks ![⚠️](https://img.shields.io/badge/-Remarks-yellow?logo=exclamation) ![☢️](https://img.shields.io/badge/-Caution-red?logo=alert) ![📝](https://img.shields.io/badge/-Note-lightgrey?logo=note)

* This package is a **work in progress** and thus **may not function as expected**.
* Many features in the `ablesci`, `scinet`, `libgen`, and `facebook` modules rely on Selenium and may break if the target websites change. In particular, some features in the `facebook` module may work on the local PC but fail in GitHub Codespace and Docker container.
* The `nexus` module may not work reliably when using a proxy (the default configuration). Issues such as `307 Temporary Redirect` errors may occur, and downloads may fail if the Nexus Search server or Telegram bot is unavailable.