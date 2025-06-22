# getscipapers

## Description

**getscipapers** is a Python package for searching and requesting scientific papers from various sources. This project is a work in progress and primarily intended for my personal use. It is not a comprehensive solution for accessing scientific papers. Parts of the code were developed with assistance from [GitHub Copilot](https://github.com/features/copilot).

## Prerequisites

* **(Optional)** Install [IPFS Kubo](https://docs.ipfs.tech/install/command-line/) to access the [Nexus Search](https://www.reddit.com/r/science_nexus) database:
  ```bash
  wget https://dist.ipfs.tech/kubo/v0.35.0/kubo_v0.35.0_linux-amd64.tar.gz
  tar -xvzf kubo_v0.35.0_linux-amd64.tar.gz
  cd kubo
  sudo ./install.sh
  ```
  Verify installation:
  ```bash
  ipfs --version
  ```
  Alternatively, you can interact with the Nexus Telegram bot. To do so, create a Telegram account and obtain your API ID and API hash from [my.telegram.org](https://my.telegram.org/).

* **(Optional)** Obtain free API keys from [Elsevier](https://dev.elsevier.com/), [Wiley](https://onlinelibrary.wiley.com/library-info/resources/text-and-datamining), or [IEEE](https://developer.ieee.org/getting_started) (IEEE support not yet implemented).

* **(Optional)** Create accounts at [Sci-Net](https://sci-net.xyz), [AbleSci](https://ablesci.com), [Science Hub Mutual Aid](https://www.pidantuan.com/) (not yet implemented), or [Facebook](https://www.facebook.com/) to request papers. For Facebook, join the relevant group after creating your account.

* Install [Python](https://www.python.org) (version 3.10 or later).

## Installation

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

If you want to use the Nexus Search database, start the IPFS daemon in one terminal:

```bash
ipfs daemon --init
```

In another terminal, use the `getscipapers` command to search for and request scientific papers. For usage details, run:

```bash
getscipapers --help
```

## Remarks

* This package is under active development and may not function as expected.
* Many features in the `ablesci`, `scinet`, and `facebook` modules rely on Selenium and may break if the target websites change.
* The `nexus` module may not work reliably when using a proxy (the default configuration). Issues such as `307 Temporary Redirect` errors may occur, and downloads may fail if the Nexus Search server or Telegram bot is unavailable.