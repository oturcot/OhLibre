#!/usr/bin/env bash
set -euo pipefail

file="$1"
grep -Fxq '    image: ghcr.io/oturcot/radio-canada-podcast:latest' "$file"
sed 's|^    image: ghcr.io/oturcot/radio-canada-podcast:latest$|    image: radio-canada-podcast:local\
    pull_policy: never|' "$file"
