#!/bin/bash

# Usage: ./set-secrets.sh secrets.json [owner/repo]
#        ./set-secrets.sh --delete [owner/repo]
#        ./set-secrets.sh --create-credentials <output_file>
#        ./set-secrets.sh --encode-base64 <input_json> <output_file>

set -e  # Exit immediately if a command exits with a non-zero status

# Function to create a credentials JSON file from environment variables
create_credentials_json() {
    OUTPUT_FILE="$1"
    OUTPUT_DIR=$(dirname "$OUTPUT_FILE")
    if [ ! -d "$OUTPUT_DIR" ]; then
        mkdir -p "$OUTPUT_DIR"
    fi
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
    chmod 600 "$OUTPUT_FILE"
    echo "Created credentials file at $OUTPUT_FILE"
}

# Function to encode a JSON file to base64 and write to output file
encode_json_base64() {
    INPUT_JSON="$1"
    OUTPUT_FILE="$2"
    if [ ! -f "$INPUT_JSON" ]; then
        echo "Input JSON file $INPUT_JSON does not exist."
        exit 1
    fi
    if ! jq empty "$INPUT_JSON" 2>/dev/null; then
        echo "Input file $INPUT_JSON is not valid JSON."
        exit 1
    fi
    base64 "$INPUT_JSON" > "$OUTPUT_FILE"
    echo "Base64-encoded JSON written to $OUTPUT_FILE"
}

# Function to decode base64-encoded JSON if needed, otherwise copy as is
decode_base64_if_needed() {
    INPUT="$1"
    OUTPUT="$2"
    # Check if input is a file and exists
    if [ -f "$INPUT" ]; then
        # If file is valid JSON, copy it
        if jq empty "$INPUT" 2>/dev/null; then
            cp "$INPUT" "$OUTPUT"
            return
        fi
        # If not valid JSON, try to decode as base64 and check if result is JSON
        if base64 -d "$INPUT" 2>/dev/null | jq empty 2>/dev/null; then
            base64 -d "$INPUT" > "$OUTPUT"
            return
        fi
    else
        # If input is not a file, treat as string
        if echo "$INPUT" | jq empty 2>/dev/null; then
            echo "$INPUT" > "$OUTPUT"
            return
        fi
        if echo "$INPUT" | base64 -d 2>/dev/null | jq empty 2>/dev/null; then
            echo "$INPUT" | base64 -d > "$OUTPUT"
            return
        fi
    fi
    echo "Input is not valid JSON or base64-encoded JSON."
    exit 1
}

# Handle --create-credentials option
if [ $# -eq 2 ] && [ "$1" = "--create-credentials" ]; then
    create_credentials_json "$2"
    exit 0
fi

# Handle --encode-base64 option
if [ $# -eq 3 ] && [ "$1" = "--encode-base64" ]; then
    encode_json_base64 "$2" "$3"
    exit 0
fi

# Print usage if arguments are invalid
if [ $# -lt 1 ] || [ $# -gt 2 ]; then
    echo "Usage: $0 <secrets.json> [owner/repo]"
    echo "       $0 --delete [owner/repo]"
    echo "       $0 --create-credentials <output_file>"
    echo "       $0 --encode-base64 <input_json> <output_file>"
    exit 1
fi

# Handle --delete option to remove all secrets from the repo
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

# Main logic: set secrets from a JSON file
JSON_FILE="$1"

# Set repository argument if provided, otherwise use default
if [ $# -eq 2 ]; then
    REPO_ARG="-r $2"
else
    REPO_ARG="-r hoanganhduc/getscipapers"
fi

# Check for required tools
if ! command -v gh &> /dev/null; then
    echo "GitHub CLI (gh) is not installed."
    exit 1
fi

if ! command -v jq &> /dev/null; then
    echo "jq is not installed."
    exit 1
fi

# Check if JSON file exists
if [ ! -f "$JSON_FILE" ]; then
    echo "File $JSON_FILE does not exist."
    exit 1
fi

# Loop through each key in the JSON file and set it as a GitHub secret
for key in $(jq -r 'keys[]' "$JSON_FILE"); do
    value=$(jq -r --arg k "$key" '.[$k]' "$JSON_FILE")
    echo "Setting secret: $key"
    gh secret set -a codespaces "$key" --body "$value" $REPO_ARG
done

echo "All secrets set."