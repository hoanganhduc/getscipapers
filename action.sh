#!/bin/bash

GITHUB_REPO="hoanganhduc/getscipapers"

gh repo edit "$GITHUB_REPO" --default-branch docker
gh workflow run build-docker.yml --repo "$GITHUB_REPO"
gh repo edit "$GITHUB_REPO" --default-branch master