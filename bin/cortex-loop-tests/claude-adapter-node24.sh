#!/usr/bin/env bash
# Fail-closed Node 24 / Node 22 contract for claude.sh. Does not call the live CLI.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ADAPTER="$ROOT/bin/cortex-loop-adapters/claude.sh"
WORKDIR="$(mktemp -d -t claude-adapter-node24.XXXXXX)"
cleanup() { rm -rf "$WORKDIR"; }
trap cleanup EXIT

write_bin() {
  local path="$1"
  local output="$2"
  mkdir -p "$(dirname "$path")"
  printf '#!/bin/sh\necho %s\n' "$output" >"$path"
  chmod +x "$path"
}

write_bin "$WORKDIR/ok/node" "v24.19.0"
write_bin "$WORKDIR/ok/pnpm" "11.7.0"
write_bin "$WORKDIR/ok/claude" "Claude Code 2.0.0"
write_bin "$WORKDIR/v22/node" "v22.22.0"
write_bin "$WORKDIR/v22/pnpm" "11.7.0"
write_bin "$WORKDIR/v22/claude" "Claude Code 2.0.0"

export CORTEX_CLAUDE_BIN="$WORKDIR/ok/claude"
export CORTEX_PNPM_BIN="$WORKDIR/ok/pnpm"
export CORTEX_NODE24_BIN="$WORKDIR/ok/node"
OUT="$("$ADAPTER" --check-ready)"
printf '%s\n' "$OUT" | grep -q 'READY executor=claude backend=cli node=v24.19.0 pnpm=11.7.0' || {
  printf 'expected Node24 READY, got:\n%s\n' "$OUT" >&2
  exit 1
}
printf '%s\n' "$OUT" | grep -qE 'auth=(keychain|long-lived|env|missing|unknown)' || {
  printf 'expected auth= field, got:\n%s\n' "$OUT" >&2
  exit 1
}

export CORTEX_NODE24_BIN="$WORKDIR/v22/node"
export CORTEX_PNPM_BIN="$WORKDIR/v22/pnpm"
export CORTEX_CLAUDE_BIN="$WORKDIR/v22/claude"
set +e
ERR="$("$ADAPTER" --check-ready 2>&1)"
RC=$?
set -e
[[ "$RC" -eq 75 ]] || { printf 'expected rc=75 for Node22, got %s\n%s\n' "$RC" "$ERR" >&2; exit 1; }
printf '%s\n' "$ERR" | grep -q 'node22-forbidden' || {
  printf 'expected node22-forbidden, got:\n%s\n' "$ERR" >&2
  exit 1
}

printf 'PASS claude adapter Node24 gate\n'
