#!/bin/bash

# Usage: ./set-secrets.sh secrets.json [owner/repo]
#        ./set-secrets.sh --delete [owner/repo]
#        ./set-secrets.sh --create-credentials <output_file>

set -e

create_credentials_json() {
    OUTPUT_FILE="$1"
    cat > "$OUTPUT_FILE" <<EOF
{
    "tg_api_id": "${TG_API_ID}",
    "tg_api_hash": "${TG_API_HASH}",
    "phone": "${PHONE}",
    "bot_username": "${BOT_USERNAME}",
    "scinet_username": "${SCINET_USERNAME}",
    "scinet_password": "${SCINET_PASSWORD}",
    "fb_username": "${FB_USERNAME}",
    "fb_password": "${FB_PASSWORD}",
    "ablesci_username": "${ABLESCI_USERNAME}",
    "ablesci_password": "${ABLESCI_PASSWORD}",
    "email": "${EMAIL}",
    "elsevier_api_key": "${ELSEVIER_API_KEY}",
    "wiley_tdm_token": "${WILEY_TDM_TOKEN}",
    "ieee_api_key": "${IEEE_API_KEY}"
}
EOF
    echo "Created credentials file at $OUTPUT_FILE"
}

if [ $# -eq 2 ] && [ "$1" = "--create-credentials" ]; then
    create_credentials_json "$2"
    exit 0
fi

if [ $# -lt 1 ] || [ $# -gt 2 ]; then
    echo "Usage: $0 <secrets.json> [owner/repo]"
    echo "       $0 --delete [owner/repo]"
    echo "       $0 --create-credentials <output_file>"
    exit 1
fi

if [ "$1" = "--delete" ]; then
    if [ $# -eq 2 ]; then
        REPO_ARG="-r $2"
    else
        REPO_ARG="-r hoanganhduc/getscipapers"
    fi

    if ! command -v gh &> /dev/null; then
        echo "GitHub CLI (gh) is not installed."
        exit 1
    fi

    echo "Fetching all secrets..."
    secrets=$(gh secret list -a codespaces --json name -q '.[].name')
    for key in $secrets; do
        echo "Deleting secret: $key"
        gh secret delete "$key"
    done
    echo "All secrets deleted."
    exit 0
fi

JSON_FILE="$1"

if [ $# -eq 2 ]; then
    REPO_ARG="-r $2"
else
    REPO_ARG="-r hoanganhduc/getscipapers"
fi

if ! command -v gh &> /dev/null; then
    echo "GitHub CLI (gh) is not installed."
    exit 1
fi

if ! command -v jq &> /dev/null; then
    echo "jq is not installed."
    exit 1
fi

if [ ! -f "$JSON_FILE" ]; then
    echo "File $JSON_FILE does not exist."
    exit 1
fi

for key in $(jq -r 'keys[]' "$JSON_FILE"); do
    value=$(jq -r --arg k "$key" '.[$k]' "$JSON_FILE")
    echo "Setting secret: $key"
    gh secret set -a codespaces "$key" --body "$value" $REPO_ARG
done

echo "All secrets set."