#!/usr/bin/env bash
set -euo pipefail

script="$(dirname "$0")/publish-ghcr.sh"
MOCK_LOG="$(mktemp)"
export MOCK_LOG
trap 'rm -f "$MOCK_LOG"' EXIT

curl() {
  local output=""
  while (($#)); do
    if [[ "$1" == --output ]]; then output="$2"; shift; fi
    if [[ "$1" == *'/tags/list' ]]; then printf 401; return; fi
    shift
  done
  printf '{"token":"test"}' > "$output"
  printf 200
}
docker() {
  printf '%s\n' "$*" >> "$MOCK_LOG"
  if [[ "$*" == *'imagetools inspect --raw'* ]]; then
    if [[ "$*" == *':latest' ]]; then
      case "$MOCK_CHANNEL" in
        error) echo 'registry unavailable' >&2; return 1 ;;
        missing) echo 'manifest unknown' >&2; return 1 ;;
      esac
    fi
    printf '%s\n' '{"manifests":[{"platform":{"os":"linux","architecture":"amd64"}},{"platform":{"os":"linux","architecture":"arm64"}}]}'
  fi
}
export -f curl docker

export MOCK_CHANNEL=error
if bash "$script" ghcr.io/example/ohlibre 0.1.0 /unused 2>/dev/null; then
  echo "Registry failures must not be treated as a missing channel." >&2
  exit 1
fi
if grep -q 'imagetools create' "$MOCK_LOG"; then
  echo "Registry failures must not update tags." >&2
  exit 1
fi

: > "$MOCK_LOG"
export MOCK_CHANNEL=missing
bash "$script" ghcr.io/example/ohlibre 0.1.0 /unused >/dev/null
grep -q -- '--tag ghcr.io/example/ohlibre:latest' "$MOCK_LOG"
echo "GHCR publication tests passed."
