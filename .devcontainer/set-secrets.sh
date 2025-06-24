#!/bin/bash

# Usage: ./set-secrets.sh secrets.json [owner/repo]
#        ./set-secrets.sh --delete [owner/repo]
#        ./set-secrets.sh --refine secrets.json [output.json]

set -e

replace_vars_in_json() {
    local input_json="$1"
    local output_json="$2"
    local tmp_json
    tmp_json=$(mktemp)

    # Read all env vars into jq format
    env_jq_args=()
    while IFS='=' read -r name value; do
        env_jq_args+=(--arg "$name" "$value")
    done < <(env)

    # Replace $VAR or ${VAR} in all string values
    jq '
      def replace_vars:
        walk(
          if type == "string" then
            gsub("\\$\\{?([A-Za-z_][A-Za-z0-9_]*)\\}?"; 
              (env[.captures[0]] // ""))
          else . end
        );
      replace_vars
    ' "${env_jq_args[@]}" "$input_json" > "$tmp_json"

    mv "$tmp_json" "$output_json"
}

if [ "$1" = "--refine" ]; then
    if [ $# -lt 2 ] || [ $# -gt 3 ]; then
        echo "Usage: $0 --refine <input.json> [output.json]"
        exit 1
    fi
    INPUT_JSON="$2"
    OUTPUT_JSON="${3:-refined.json}"
    if [ ! -f "$INPUT_JSON" ]; then
        echo "File $INPUT_JSON does not exist."
        exit 1
    fi
    replace_vars_in_json "$INPUT_JSON" "$OUTPUT_JSON"
    echo "Refined JSON saved to $OUTPUT_JSON"
    exit 0
fi

if [ $# -lt 1 ] || [ $# -gt 2 ]; then
    echo "Usage: $0 <secrets.json> [owner/repo]"
    echo "       $0 --delete [owner/repo]"
    echo "       $0 --refine <input.json> [output.json]"
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

# Do NOT replace variables in JSON unless --refine is specified
TMP_JSON="$JSON_FILE"

for key in $(jq -r 'keys[]' "$TMP_JSON"); do
    value=$(jq -r --arg k "$key" '.[$k]' "$TMP_JSON")
    echo "Setting secret: $key"
    gh secret set -a codespaces "$key" --body "$value" $REPO_ARG
done

echo "All secrets set."
