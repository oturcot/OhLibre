#!/usr/bin/env bash
set -euo pipefail

script="$(dirname "$0")/release-version.sh"
git() { printf '%s\n' "${TEST_TAGS:-}"; }
export -f git

check() {
  expected="$1"
  shift
  actual="$(bash "$script" "$@")"
  [[ "$actual" == "$expected" ]] || {
    echo "Expected $expected, got $actual for $*" >&2
    exit 1
  }
}

check 0.1.0 patch 0.4.0 ""
check 0.4.0 promotion 0.4.0 ""
check 0.4.3 promotion 0.4.0 0.4.2
check 0.5.0 promotion 0.5.0 0.4.2
check 1.0.0 major 1.0.0 0.4.2
check 0.5.0 minor 0.5.0 0.4.2
check 0.1.0 minor 0.4.0 ""
check 2.0.0 custom 0.4.0 0.4.2 2.0.0
export TEST_TAGS=$'0.4.3-beta.0\n0.4.3-beta.2\n0.4.2-beta.9'
check 0.4.3-beta.3 beta 0.4.0 0.4.2
if bash "$script" custom 0.4.0 0.4.2 0.4.2 >/dev/null 2>&1 ||
   bash "$script" promotion invalid 0.4.2 >/dev/null 2>&1 ||
   bash "$script" minor 0.4.0 0.4.2 >/dev/null 2>&1 ||
   bash "$script" promotion 1.1.0 0.4.2 >/dev/null 2>&1; then
  echo "An invalid version was accepted." >&2
  exit 1
fi
echo "Release version tests passed."
