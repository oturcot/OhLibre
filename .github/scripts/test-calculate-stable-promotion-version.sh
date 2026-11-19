#!/usr/bin/env bash
set -euo pipefail

script="$(dirname "${BASH_SOURCE[0]}")/calculate-stable-promotion-version.sh"

assert_version() {
  local expected="$1"
  shift
  local actual
  actual="$(bash "$script" "$@")"
  if [[ "$actual" != "$expected" ]]; then
    echo "Expected $expected, got $actual." >&2
    exit 1
  fi
}

assert_invalid() {
  if bash "$script" "$@" >/dev/null 2>&1; then
    echo "Expected invalid version input to fail." >&2
    exit 1
  fi
}

assert_version "0.1.0" "0.1.1" ""
assert_version "0.1.1" "0.1.1" "0.1.0"
assert_version "0.1.5" "0.1.0" "0.1.4"
assert_version "0.2.0" "0.2.0" "0.1.8"
assert_version "1.0.0" "1.0.0" "0.9.9"
assert_version "0.2.4" "0.1.1" "0.2.3"
assert_invalid "1.2.0" "0.9.9"
assert_invalid "1.0" "0.1.0"
