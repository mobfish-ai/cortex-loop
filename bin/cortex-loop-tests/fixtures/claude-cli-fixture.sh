#!/usr/bin/env bash
set -euo pipefail

if [[ "${1:-}" == "--version" ]]; then
  printf 'claude-fixture 0.0.0\n'
  exit 0
fi

marker="${PWD}/fixture-claude-marker.txt"
printf 'fixture-claude-wrote-marker\n' >"$marker"
printf 'FIXTURE_MARKER_WRITTEN path=%s\n' "$marker"
