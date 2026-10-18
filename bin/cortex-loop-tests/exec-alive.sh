#!/usr/bin/env bash
# Verify that an executor is actually alive. Done means the symptom is gone, not that a file exists.
# Used for self-defect tasks: those change the node environment or remote config and have no single output file.
set -uo pipefail
EXEC="${1:?usage: exec-alive.sh <executor>}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ADAPTER="$ROOT/bin/cortex-loop-adapters/${EXEC}.sh"
[[ -f "$ADAPTER" ]] || { echo "no such executor adapter: $EXEC"; exit 2; }

PROMPT=$(mktemp); RESULT=$(mktemp)
trap 'rm -f "$PROMPT" "$RESULT"' EXIT
echo "Reply with exactly two words: online" > "$PROMPT"

timeout 120 bash "$ADAPTER" "$PROMPT" "$RESULT" >/dev/null 2>&1
rc=$?
body=$(cat "$RESULT" 2>/dev/null)

# Auth/quota failure signatures fail the check even when the exit code is 0
if grep -qiE "not logged in|401|403|unauthorized|authenticat|quota|rate.?limit|$(python3 -c 'import sys; sys.stdout.write("\u8bf7\u5148\u767b\u5f55")')" <<<"$body"; then
  echo "FAIL $EXEC still has an auth/quota failure: $(head -1 <<<"$body")"
  exit 1
fi
[[ $rc -ne 0 ]] && { echo "FAIL $EXEC exit code $rc"; exit 1; }
[[ -z "$body" ]] && { echo "FAIL $EXEC no output"; exit 1; }
echo "PASS $EXEC available"
