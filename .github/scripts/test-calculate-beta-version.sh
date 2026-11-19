#!/usr/bin/env bash
set -euo pipefail

script="$(dirname "${BASH_SOURCE[0]}")/calculate-beta-version.sh"

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

assert_version "0.1.1-beta.0" "0.1.1" "0.1.0" ""
assert_version "0.1.1-beta.3" "0.1.1" "0.1.0" $'0.1.1-beta.0\n0.1.1-beta.2\n0.1.0'
assert_version "0.1.5-beta.0" "0.1.1" "0.1.4" $'0.1.4\n0.1.4-beta.7'
assert_version "0.2.0-beta.0" "0.2.0" "0.1.8" $'0.1.9-beta.4'
assert_version "1.2.0-beta.10" "1.2.3" "" $'1.2.0-beta.9\n1.2.0-beta.2'
