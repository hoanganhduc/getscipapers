# getscipapers

## Description

A Python package to get and request scientific papers from various sources. This is still a work in progress and mostly a personal project for my own use. It is not intended to be a complete solution for accessing scientific papers. Additionally, the code is written with the help of AI models available in [GitHub Copilot](https://github.com/features/copilot).

## Prerequisites

* (Optional) Install [IPFS Kubo](https://docs.ipfs.tech/install/command-line/) if you want to access the [Nexus Search](https://www.reddit.com/r/science_nexus) database.
  ```bash
  wget https://dist.ipfs.tech/kubo/v0.35.0/kubo_v0.35.0_linux-amd64.tar.gz # Change the URL to the latest version if needed. For Windows or Mac, use the appropriate version from https://dist.ipfs.tech/kubo/v0.35.0/
  tar -xvzf kubo_v0.35.0_linux-amd64.tar.gz 
  cd kubo
  sudo ./install.sh # Install IPFS Kubo 
  ```
  To test if IPFS Kubo is installed correctly, run:
  ```bash
  ipfs --version
  ```
  You can also interact with the Nexus Telegram bot directly. Create a Telegram account and get API ID and API hash from [my.telegram.org](https://my.telegram.org/) to use the Nexus Telegram bot for requesting papers.
* (Optional) Get free API keys from [Elsevier](https://dev.elsevier.com/), [Wiley](https://onlinelibrary.wiley.com/library-info/resources/text-and-datamining), [IEEE](https://developer.ieee.org/getting_started) (not yet implemented).
* (Optional) Create accounts at [Sci-Net](https://sci-net.xyz), [AbleSci](https://ablesci.com), and [Science Hub Mutual Aid](https://www.pidantuan.com/) (not yet implemented), [Facebook](https://www.facebook.com/) to request papers. (For Facebook, after having an account, you need to request to join the group that you want to post your request to first.)
* Install [Python](https://www.python.org) (version 3.10 or later).

## Installation

It is recommended to use a virtual environment to avoid conflicts with other Python packages. You can use `venv` or `virtualenv` for this purpose. To create a virtual environment, run the following command in your terminal:

```bash
# Clone the repository
git clone https://github.com/hoanganhduc/getscipapers.git 
cd getscipapers
# Create a virtual environment in the ~/.getscipapers directory. 
# You can change the path to your preferred location. 
# Alternatively, you can use `virtualenv ~/.getscipapers` if you have `virtualenv` installed.
python -m venv ~/.getscipapers 
source ~/.getscipapers/bin/activate # Activate the virtual environment
pip install --upgrade pip # Upgrade pip to the latest version
pip install build # Install the build package to build the package
pip install -r requirements.txt # Install the required packages
python -m build # Build the package
pip install -e . # Install the package in editable mode
# Clean up build artifacts
rm -rf build/
rm -rf dist/
rm -rf *.egg-info/
find . -type d -name __pycache__ -exec rm -rf {} +
find . -type f -name "*.pyc" -delete
```

## Usage

In one terminal, start the IPFS daemon by `ipfs daemon --init` if you want to access the Nexus Search database. In another terminal, you can use the `getscipapers` command to search and request scientific papers. For more information on how to use the command, run:

```bash
getscipapers --help # Show help message
```