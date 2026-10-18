#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
MARKER="/tmp/cortex-cheap-tool-smoke.txt"
RESULT="/tmp/cortex-cheap-tool-smoke.result"

rm -f "$MARKER" "$RESULT"
bash "$ROOT/bin/cortex-loop-adapters/cheap.sh" \
  "$ROOT/bin/cortex-loop-tests/fixtures/cheap-tool-smoke.prompt" "$RESULT"

test -f "$MARKER"
test "$(tr -d '\r\n' < "$MARKER")" = "CORTEX_TOOL_EXECUTION_OK"
grep -q 'tool_layer=claude-code' "$RESULT"
echo "PASS cheap adapter performed a real Write+Read through MiniMax coding-agent layer"
