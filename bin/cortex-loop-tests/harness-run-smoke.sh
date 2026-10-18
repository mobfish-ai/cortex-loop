#!/usr/bin/env bash
# Verify the cortex-loop harness-run subcommand really drives the sibling repo cortex-harness/packages/agent-runtime.
# 2026-08-21 HANDOFF Q2 done_when: "start one run from the Skill ... and have a test assertion".
#
# Three states, not two: cortex-harness is a sibling repo (not versioned inside ob1). A machine
# without it, or without a node that satisfies engines(>=24.0.0 <25), is not a defect in this repo -- SKIP, not FAIL.
# Only "the environment is complete but the wiring does not run" is FAIL (a real regression).
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
CORTEX_LOOP="$ROOT/bin/cortex-loop"

HARNESS_DIR="${CORTEX_HARNESS_DIR:-$HOME/cortex-harness}"
if [[ ! -d "$HARNESS_DIR" ]]; then
  echo "SKIP harness-run-smoke: this machine has no ${HARNESS_DIR} (sibling repo not checked out; not a code defect)"
  exit 0
fi

OUT="$(python3 "$CORTEX_LOOP" harness-run --json --timeout 60 "harness-run-smoke test" 2>&1)"
rc=$?

if grep -q '"reason": "node_v24_missing"' <<<"$OUT"; then
  echo "SKIP harness-run-smoke: this machine has no node satisfying cortex-harness engines(>=24.0.0 <25) (not a code defect)"
  exit 0
fi

if [[ $rc -ne 0 ]]; then
  echo "FAIL harness-run-smoke: exit code $rc"
  echo "$OUT"
  exit 1
fi

if ! grep -q '"ok": true' <<<"$OUT"; then
  echo "FAIL harness-run-smoke: ok is not true"
  echo "$OUT"
  exit 1
fi

if ! grep -q '"status": "succeeded"' <<<"$OUT"; then
  echo "FAIL harness-run-smoke: agent-runtime returned result.status != succeeded"
  echo "$OUT"
  exit 1
fi

echo "PASS harness-run-smoke: ob1 -> cortex-harness/agent-runtime wiring is reachable"
