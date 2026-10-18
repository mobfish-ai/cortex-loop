#!/usr/bin/env bash
# cortex-loop:requires-env PATH HTTP_PROXY HTTPS_PROXY
# Note: the codex CLI also needs an outbound proxy
# cortex-loop adapter: codex — must go through bin/codex-validate.sh (no bare codex exec)
# Contract: $1=prompt file  $2=result file
set -uo pipefail
PROMPT="$1"; RESULT="$2"
OB1_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
WORKDIR="${CORTEX_WORKTREE:-$OB1_ROOT}"
if [[ "${CORTEX_REQUIRE_WORKTREE:-0}" == "1" && -z "${CORTEX_WORKTREE:-}" ]]; then
  printf '[adapter] codex rc=2 reason=missing-CORTEX_WORKTREE\n' > "$RESULT"
  exit 2
fi
[[ -d "$WORKDIR" ]] || { printf '[adapter] codex rc=2 reason=invalid-worktree\n' > "$RESULT"; exit 2; }
if [[ "${CORTEX_REQUIRE_WORKTREE:-0}" == "1" && "$(cd "$WORKDIR" && pwd -P)" == "$(cd "$OB1_ROOT" && pwd -P)" ]]; then
  printf '[adapter] codex rc=2 reason=root-worktree-forbidden\n' > "$RESULT"
  exit 2
fi
TOPIC="cortex-loop-$(basename "$PROMPT" .prompt)"

cd "$WORKDIR" || exit 1
bash "$OB1_ROOT/bin/codex-validate.sh" --stakes cross-file "$TOPIC" "$PROMPT" 25 > /dev/null 2>&1
rc=$?
OUT="/tmp/panel-$TOPIC/codex.out"
if [[ -s "$OUT" ]]; then
  cp "$OUT" "$RESULT"
else
  echo "[adapter] codex produced no output (exit code ${rc})" > "$RESULT"
fi
exit $rc
