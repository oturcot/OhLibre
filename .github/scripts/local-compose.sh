#!/usr/bin/env bash
set -euo pipefail

file="$1"
grep -Fxq '    image: ghcr.io/oturcot/ohlibre:latest' "$file"
sed 's|^    image: ghcr.io/oturcot/ohlibre:latest$|    image: ohlibre:local\
    pull_policy: never|' "$file"
