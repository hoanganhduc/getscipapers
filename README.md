# getscipapers

<div align="center">
  <a href="https://www.buymeacoffee.com/hoanganhduc" target="_blank" rel="noopener noreferrer">
    <img src="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png" alt="Buy Me A Coffee" height="40" style="margin-right: 10px;" />
  </a>
  <a href="https://ko-fi.com/hoanganhduc" target="_blank" rel="noopener noreferrer">
    <img src="https://storage.ko-fi.com/cdn/kofi3.png?v=3" alt="Ko-fi" height="40" />
  </a>
</div>



![Version](https://img.shields.io/github/v/release/hoanganhduc/getscipapers?label=version) ![Pre-release](https://img.shields.io/github/v/tag/hoanganhduc/getscipapers?label=pre-release&sort=semver) ![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python) ![Docker](https://img.shields.io/badge/Docker-ready-blue?logo=docker) ![GitHub](https://img.shields.io/badge/GitHub-Repo-black?logo=github) ![Status](https://img.shields.io/badge/status-work--in--progress-yellow) ![License](https://img.shields.io/github/license/hoanganhduc/getscipapers) ![Papers](https://img.shields.io/badge/Papers-Search-orange?logo=read-the-docs) ![Cloud](https://img.shields.io/badge/Cloud-Ready-blue?logo=cloud)

---

## Table of Contents

1. [Description](#description)
2. [Prerequisites](#prerequisites)
3. [Installation](#installation)
4. [Usage](#usage)
5. [Running in GitHub Codespace](#running-getscipapers-in-github-codespace)
6. [Docker Container](#docker-container-for-running-getscipapers)
7. [Documentation](#documentation)
8. [Remarks](#remarks)



## Description

![Info](https://img.shields.io/badge/-Info-informational?logo=info) ![WIP](https://img.shields.io/badge/-WIP-yellow?logo=rocket) ![Experimental](https://img.shields.io/badge/-Experimental-lightgrey?logo=flask)

**getscipapers** is a Python package designed for searching and requesting scientific papers from multiple sources. This project is a **work in progress** and primarily intended for **personal use**. It is not a comprehensive solution for accessing scientific papers. Portions of the code were developed with assistance from [GitHub Copilot](https://github.com/features/copilot), [ChatGPT Codex](https://openai.com/), and [Claude Code](https://claude.com/claude-code).


## Prerequisites

![Checklist](https://img.shields.io/badge/-Checklist-success?logo=checkmarx) ![Tools](https://img.shields.io/badge/-Tools-blue?logo=tools) ![Keys](https://img.shields.io/badge/-Keys-orange?logo=keybase)

* **(Optional)** ![🧊](https://img.shields.io/badge/IPFS-Kubo-green?logo=ipfs) Install [IPFS Kubo](https://docs.ipfs.tech/install/command-line/) to access the [Nexus Search](https://www.reddit.com/r/science_nexus) database:
  ```bash
  wget https://dist.ipfs.tech/kubo/v0.42.0/kubo_v0.42.0_linux-amd64.tar.gz
  tar -xvzf kubo_v0.42.0_linux-amd64.tar.gz
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

* **(Optional)** ![🗝️](https://img.shields.io/badge/Anna's%20Archive-Membership-orange?logo=archiveofourown) A paid [Anna's Archive](https://annas-archive.org/donate) membership unlocks the fast, quota-free routes. Take the secret key from your account page and put it in `GETSCIPAPERS_ANNA_SECRET_KEY` or a credentials file rather than on the command line. Without a key the Anna's Archive route still works through a real browser; see [the CLI reference](https://hoanganhduc.github.io/getscipapers/cli_reference.html) for what a membership does and does not buy.

* **(Optional)** ![🌐](https://img.shields.io/badge/Browser-Chromium-blue?logo=googlechrome) Install `chromium` and `chromedriver` for the modules that drive a browser. On a Linux host with no display, also install `xvfb`, since the Anna's Archive browser route cannot run headless:
  ```bash
  sudo apt install chromium-browser chromium-chromedriver xvfb
  ```
  Set `CHROMEDRIVER_PATH`, `CHROME_BINARY`, or `CHROMIUM_BINARY` if they live outside the usual locations. Installing the browser does not by itself guarantee access: Anna's Archive gates content behind a DDoS-Guard check that also considers the address the host connects from.

* ![🐍](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python) Install [Python](https://www.python.org) (version 3.10 or later).


## Installation

![Install](https://img.shields.io/badge/-Install-green?logo=addthis) ![Virtualenv](https://img.shields.io/badge/-Virtualenv-blue?logo=python) ![Setup](https://img.shields.io/badge/-Setup-lightgrey?logo=settings)

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


## Usage

![Usage](https://img.shields.io/badge/-Usage-blue?logo=read-the-docs) ![CLI](https://img.shields.io/badge/-CLI-black?logo=gnubash) ![Search](https://img.shields.io/badge/-Search-orange?logo=search)

To use the Nexus Search database, start the IPFS daemon (if this is your first time, run `ipfs init` first) in one terminal:

```bash
ipfs daemon
```

The daemon is expected at `http://127.0.0.1:8080`. Set
`GETSCIPAPERS_IPFS_HTTP_BASE_URL` when the gateway runs elsewhere, such as in a
separate container:

```bash
export GETSCIPAPERS_IPFS_HTTP_BASE_URL=http://ipfs:8080
```

In another terminal, use the `getscipapers` command to search for and request scientific papers. For usage details, run:

```bash
getscipapers --help
```

### Quick CLI examples

Common end-to-end invocations of the CLI:

```bash
# Search by keyword, limit to 5 results, and download PDFs to the default folder
getscipapers getpapers --search "graph neural network" --limit 5

# Download a specific DOI using Unpaywall first (non-interactive to avoid prompts)
GETSCIPAPERS_EMAIL=you@example.com \
getscipapers getpapers --doi 10.1371/journal.pone.0245581 --db unpaywall --non-interactive

# Process a list of DOIs from a text file, saving PDFs to a custom folder
getscipapers getpapers --doi-file dois.txt --download-folder ./pdfs

# Extract DOIs from a PDF without downloading anything
getscipapers getpapers --extract-doi-from-pdf paper.pdf --no-download

# Show metadata only (no downloads) for a single DOI across all services
getscipapers getpapers --doi 10.48550/arXiv.1706.03762 --no-download --verbose

# Use environment-provided credentials and skip prompts entirely
export GETSCIPAPERS_EMAIL=you@example.com
export GETSCIPAPERS_ELSEVIER_API_KEY=your_elsevier_key
getscipapers getpapers --search "quantum error correction" --non-interactive

# Route every service through a JSON-defined proxy or force direct connections
getscipapers getpapers --doi 10.1371/journal.pcbi.1007128 --proxy ./sample_proxy_config.json
getscipapers getpapers --search "graph neural networks" --no-proxy
getscipapers getpapers --search "graph neural networks" --auto-proxy  # fetch a working proxy if one is missing

# Log in to Z-Library using saved credentials (prompts and saves if missing)
getscipapers zlib --login

# Log in to Z-Library without prompting (fails if credentials are missing)
getscipapers zlib --login --non-interactive

# Search Z-Library and download selected books (interactive)
getscipapers zlib --search "deep learning" --download

# Download from Anna's Archive by DOI (uses a browser when no key is configured)
getscipapers anna --doi 10.1038/nature12373

# Download by md5, which skips DOI resolution and the browser entirely
getscipapers anna --md5 a5efa9791b836507541d615ed3f069e9

# Check whether the configured Anna's Archive key logs in
export GETSCIPAPERS_ANNA_SECRET_KEY=your_secret_key
getscipapers anna --user-info
```

### Graphical wrapper

Prefer a point-and-click flow? Launch the Tkinter GUI wrapper (works on both Windows and Linux) and trigger searches or DOI list downloads without remembering every flag:

```bash
getscipapers gui
```

The window exposes the same options as the CLI—database selection (toggle one or many services), metadata-only runs, custom download folders, and verbose logging—and reuses the CLI logic under the hood so behavior stays consistent.

The GUI also shows the running version with author and support links, accepts comma-separated DOIs directly or from a text file, disables actions while background work is in progress, offers **Clear output** and **Open folder** buttons to reset logs or jump to your downloads, and lets you type or browse for a credentials JSON file when you want to point at a custom location. You can likewise toggle proxy usage, browse for a proxy JSON configuration, or let the app automatically fetch a working proxy so every service call follows the same connectivity rule. Settings live in their own tab so search actions stay uncluttered, an **About** tab lists the author, description, source code, donation links, and license, and the output pane now has a **Detailed log** tab with timestamped entries alongside the main console. A dedicated **Remove metadata** control can scrub PDF metadata after downloads, either overwriting the original or writing a cleaned copy alongside it. Inline validation hints appear beside inputs when something is missing, a shared progress bar and toast notifications make long downloads and proxy discovery visible, and **Save/Reload profile** buttons persist your preferred folders, credentials, and proxy settings between sessions.


## Running getscipapers in GitHub Codespace

![GitHub Codespaces](https://img.shields.io/badge/GitHub-Codespaces-blue?logo=github) ![Cloud Dev](https://img.shields.io/badge/Cloud-Dev-blue?logo=cloud) ![Fast](https://img.shields.io/badge/-Fast-lightgrey?logo=zap)

The fastest way to run `getscipapers` is via GitHub Codespaces. This provides a preconfigured environment, eliminating local setup. To use it:

1. ![🍴](https://img.shields.io/badge/-Fork-black?logo=github) Fork the repository to your GitHub account.
2. ![🔐](https://img.shields.io/badge/-Secrets-yellow?logo=github) (Optional) Set up codespace secrets for your API keys and configurations. See [.devcontainer/set-secrets.sh](.devcontainer/set-secrets.sh) for an example using [GitHub CLI](https://cli.github.com/).
3. ![💻](https://img.shields.io/badge/-Codespace-blue?logo=github) Create a new codespace from your forked repository. This will automatically set up the environment with all dependencies installed. You can also use [GitHub CLI](https://cli.github.com/) to create a codespace, for example:

   ```bash
   gh codespace create --repo hoanganhduc/getscipapers --branch master --machine basicLinux32gb
   ```
   ![ℹ️](https://img.shields.io/badge/-Info-informational?logo=info) The `basicLinux32gb` machine type provides 2 cores, 8GB RAM, and 32GB storage. See [GitHub Codespaces documentation](https://docs.github.com/en/codespaces/developing-in-a-codespace/creating-a-codespace-for-a-repository) for more machine types such as `standardLinux32gb`, `premiumLinux`, and `largePremiumLinux`.
4. ![💻](https://img.shields.io/badge/-Terminal-black?logo=gnubash) Once the codespace is ready, open a terminal and run `getscipapers` commands directly.


## Docker Container for Running getscipapers

![Docker](https://img.shields.io/badge/-Docker-blue?logo=docker) ![Container](https://img.shields.io/badge/-Container-green?logo=docker) ![Isolated](https://img.shields.io/badge/-Isolated-lightgrey?logo=lock)


### Overview

![Overview](https://img.shields.io/badge/-Overview-informational?logo=info) ![Docs](https://img.shields.io/badge/-Docs-lightgrey?logo=read-the-docs)

This guide explains how to use `getscipapers` inside a Docker container. The container includes all dependencies, so you can start downloading scientific papers immediately—no manual setup required.


### Quick Start

![Quick Start](https://img.shields.io/badge/-Quick%20Start-yellow?logo=zap) ![Start](https://img.shields.io/badge/-Start-blue?logo=rocket)


#### 1. Pull and Run the Prebuilt Image

![Pull](https://img.shields.io/badge/-Pull-blue?logo=docker) ![Ready](https://img.shields.io/badge/-Ready-green?logo=check)

To get started quickly, pull the latest image from GitHub Container Registry and run it:

```bash
docker pull ghcr.io/hoanganhduc/getscipapers:latest
docker run -it --rm -v $(pwd):/workspace ghcr.io/hoanganhduc/getscipapers:latest
```

This mounts your current directory to `/workspace` inside the container for easy file access.


#### 2. Build and Run Locally

![Build](https://img.shields.io/badge/-Build-blue?logo=docker) ![Local](https://img.shields.io/badge/-Local-green?logo=homeassistant)

The `Dockerfile` lives on the `docker` branch, not on `master`, so check that
branch out first:

```bash
git clone -b docker https://github.com/hoanganhduc/getscipapers.git
cd getscipapers
docker build -t getscipapers .
docker run -it --rm -v $(pwd):/workspace getscipapers
```


#### 3. Run in Detached Mode with Persistent Storage

![Persistent Storage](https://img.shields.io/badge/-Persistent%20Storage-green?logo=storage) ![Detached](https://img.shields.io/badge/-Detached-blue?logo=autorenew)

To keep the container running in the background and ensure downloads and configuration persist:

```bash
docker run -d \
    --name getscipapers-container \
    --restart always \
    -v $HOME/Downloads:/home/getscipaper/Downloads \
    -v $HOME/.config/getscipapers:/home/getscipaper/.config/getscipapers \
    ghcr.io/hoanganhduc/getscipapers:latest
```

This setup saves downloaded papers and settings to your host machine. Adjust folder paths as needed.


### Optional: Integrate with IPFS

![IPFS](https://img.shields.io/badge/IPFS-Kubo-green?logo=ipfs) ![Integration](https://img.shields.io/badge/-Integration-blue?logo=link)

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

This starts the IPFS daemon with persistent storage and required ports. Adjust folder paths as needed.
Point getscipapers at it with `GETSCIPAPERS_IPFS_HTTP_BASE_URL`, since `127.0.0.1` inside the
getscipapers container is that container rather than the daemon.

A Docker Compose file that starts both services together lives on the [`docker`
branch](https://github.com/hoanganhduc/getscipapers/tree/docker), and is documented in
[Docker Compose Guide](https://hoanganhduc.github.io/getscipapers/docker_compose.html).


### Running getscipapers Commands

![CLI](https://img.shields.io/badge/-CLI-black?logo=gnubash) ![Exec](https://img.shields.io/badge/-Exec-blue?logo=terminal)

To run `getscipapers` inside the container:

```bash
docker exec -it getscipapers-container getscipapers --help
```


#### Optional: Create a Convenience Script

![Script](https://img.shields.io/badge/-Script-blue?logo=gnubash) ![Shortcut](https://img.shields.io/badge/-Shortcut-yellow?logo=zap)

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

## Documentation

The repository ships with a comprehensive overview of the architecture, configuration model, and command-line workflows in [docs/PROJECT_DOCUMENTATION.md](docs/PROJECT_DOCUMENTATION.md). Refer to it for details on how each module collaborates to search, request, and download papers across supported services.

For a browsable HTML site, build the Sphinx documentation:

```bash
pip install -r docs/requirements.txt
sphinx-build -b html docs/source docs/_build/html
```

Open `docs/_build/html/index.html` in your browser to explore the CLI usage
guides, configuration notes, and API reference pages generated from the source
modules.


## Remarks

![Remarks](https://img.shields.io/badge/-Remarks-yellow?logo=exclamation) ![Caution](https://img.shields.io/badge/-Caution-red?logo=alert) ![Note](https://img.shields.io/badge/-Note-lightgrey?logo=note)

* This package is a **work in progress** and **may not always function as expected**.
* The code is not yet fully clean or easy to follow.
* Searching with `StcGeck` is slow and generally best avoided, except in specific scenarios (such as when the Nexus bot is maintained). If you do not wish to use `StcGeck`, do not start the IPFS Desktop App or run `ipfs daemon`. In this case, the script will return errors, but `StcGeck` will not be used.
* Many features in the `ablesci`, `scinet`, `libgen`, `wosonhj`, `facebook`, and `anna` modules depend on Selenium and may break if the target websites change.
  * Some features in the `facebook` module may work locally but fail in GitHub Codespace or Docker containers (Docker not yet tested). Logging in from Codespace may trigger Facebook verification due to unfamiliar IP addresses. To resolve this, run the Facebook login for the first time with the `--no-headless` option and use your browser via noVNC to verify your login. Subsequent logins should work without issues. The noVNC access address will look like `https://<your-github-codespace-machine-name>-6080.app.github.dev`.
  * Uploading to `libgen` may occasionally fail; retrying usually resolves the issue.
* Sci-Hub works as a download source, through a split the mirror list now reflects: resolving a DOI and serving the file are separate capabilities, and no single host does both. `sci-hub.vn` answers every path with the same advertisement page and so resolves nothing, yet serves `/storage/` files correctly; `sci-hub.ru` and `sci-hub.su` resolve DOIs behind an intermittent robot check; `sci-hub.box` serves files but refuses article pages with 403; `sci-hub.ee`, `.al`, `.mk`, and `.vg` resolve but hold no storage. The handler therefore takes the storage path from whichever mirror answers and fetches the bytes from the official host first, and it validates the PDF magic bytes, since an unknown storage bucket answers 200 with the advertisement page rather than an error. The corpus is frozen around 2021; for newer work the `sci-net.xyz` and `sci-net.ru` hosts resolve DOIs and serve files without an account, and succeed on papers no Sci-Hub mirror carries. Note also that mirror domains are frequently abandoned and re-registered by unrelated parties, so a domain that resolves is not necessarily still the service it names.
* Anna's Archive answers every content path behind a DDoS-Guard challenge that no plain HTTP client can pass, so the `anna` module reaches the files another way: it reads the record JSON or the fast-download API with an account cookie, and otherwise launches Chromium and lets it solve the challenge. Whether that last route works is a property of the network path, not of the installation: when this route last solved from this host it cleared in about 40 seconds, while from an address DDoS-Guard holds at the manual captcha the page never leaves the check and the run spends its whole 120-second budget without passing, which is what every recent attempt from this host has done. A longer timeout will not clear a held address; only a different network path can, and the one proxy tried here did not clear it either. Headless Chromium is detected and fails, so the browser route needs a real display or `xvfb-run`. The routes addressed by md5 are the cheap ones, and a resolved DOI is cached, so the second fetch of the same DOI is fast whether or not an account is configured.
* LibGen resolves DOIs and delivers small files reliably; the one large file tested never finished transferring. The five mirrors `libgen.li`, `libgen.vg`, `libgen.la`, `libgen.bz`, and `libgen.gl` all answer with real catalog JSON; `libgen.li` is the one selected; a DOI the catalog carries resolves to an md5 and an entry, while one it does not carry is an ordinary coverage gap. Files whose catalog sizes were 82 kB, 407 kB, and 922 kB arrived byte-exact with a `%PDF` header. A 48 MB file did not: every attempt broke mid-stream with `IncompleteRead` after a fraction of the file had arrived, at a point that moved from run to run, so no size marks the point where transfers stop working. The server reports the full `Content-Length` and the bytes that do arrive begin with `%PDF`, so the catalog entry, the md5, and the download link are all correct and only the stream fails. The fallback sources tried after LibGen, including Sci-Hub, `libgen.xyz`, 100k Torrent, `libgen.pw`, Anna's Archive, and Randombook, failed on that same file, so `getpapers --db libgen` ends with `PDF file is not available on LibGen`. That is one observed case, not a known boundary.
* The `nexus` module may not work reliably when using a proxy. Issues such as `307 Temporary Redirect` errors may occur, and downloads may fail if the Nexus Search server or Telegram bot is unavailable.
* The first time you log in to Telegram (for using Nexus Search bots), you may be required to enter a verification code and password.
