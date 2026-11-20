#!/usr/bin/env bash
set -euo pipefail

file="$1"
grep -Fxq '    image: oturcot/ohlibre:latest' "$file"
sed 's|^    image: oturcot/ohlibre:latest$|    image: ohlibre:local\
    pull_policy: never|' "$file"
