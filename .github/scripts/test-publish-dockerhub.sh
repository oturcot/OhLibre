#!/usr/bin/env bash
set -euo pipefail

script="$(dirname "$0")/publish-dockerhub.sh"
MOCK_LOG="$(mktemp)"
export MOCK_LOG
trap 'rm -f "$MOCK_LOG"' EXIT

curl() {
  if [[ "$*" == *'auth.docker.io/token'* ]]; then
    printf '{"token":"test"}'
  elif [[ "$MOCK_PUBLIC" != yes ]]; then
    echo 'anonymous access denied' >&2
    return 22
  fi
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
export MOCK_PUBLIC=yes
if bash "$script" example/ohlibre 0.1.0 /unused 2>/dev/null; then
  echo "Registry failures must not be treated as a missing channel." >&2
  exit 1
fi
if grep -q 'imagetools create' "$MOCK_LOG"; then
  echo "Registry failures must not update tags." >&2
  exit 1
fi

: > "$MOCK_LOG"
export MOCK_CHANNEL=missing
bash "$script" example/ohlibre 0.1.0 /unused >/dev/null
grep -q -- '--tag example/ohlibre:latest' "$MOCK_LOG"
: > "$MOCK_LOG"
bash "$script" example/ohlibre 0.1.0-beta.1 /unused >/dev/null
grep -q -- '--tag example/ohlibre:beta' "$MOCK_LOG"
: > "$MOCK_LOG"
bash "$script" example/ohlibre 0.1.0 /unused 0.2.0 >/dev/null
if grep -q -- '--tag example/ohlibre:latest' "$MOCK_LOG"; then
  echo "An older release must not move the latest tag backwards." >&2
  exit 1
fi
export MOCK_PUBLIC=no
if bash "$script" example/ohlibre 0.1.0 /unused >/dev/null 2>&1; then
  echo "A private Docker Hub image must not be reported as published." >&2
  exit 1
fi
echo "Docker Hub publication tests passed."
