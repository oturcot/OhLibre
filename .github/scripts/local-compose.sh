#!/usr/bin/env bash
set -euo pipefail

file="$1"
grep -Fxq '    image: your-dockerhub-username/ohlibre:latest' "$file"
sed 's|^    image: your-dockerhub-username/ohlibre:latest$|    image: ohlibre:local\
    pull_policy: never|' "$file"
