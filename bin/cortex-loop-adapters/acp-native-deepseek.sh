#!/usr/bin/env bash
# cortex-loop adapter: acp-native:deepseek
#
# DeepSeek uses the same bounded native ACP bridge as the MiniMax adapters.
# This small launcher fixes the backend identity so `doctor`, `serve`, and the
# result footer cannot accidentally report the bridge default (mmx-a).
set -uo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="deepseek"
EXECUTOR="acp-native:deepseek"
MODEL="${CORTEX_DEEPSEEK_MODEL:-deepseek-v4-pro}"
PROMPT_FILE="${1:-}"
RESULT_FILE="${2:-}"

if [[ "${1:-}" == "--check-ready" ]]; then
  export CORTEX_ACP_BACKEND="$BACKEND"
  exec bash "$DIR/acp-native-mmx-a.sh" "$@"
fi

if [[ -z "$PROMPT_FILE" || ! -f "$PROMPT_FILE" || -z "$RESULT_FILE" ]]; then
  printf 'status=MACHINE_BLOCKER\nerror=missing-prompt-or-result\nprovider=%s\nmodel=%s\nexecutor=%s\nexecution_path=none\n' \
    "$BACKEND" "$MODEL" "$EXECUTOR" >&2
  exit 1
fi

INSTANCE_ID="${CORTEX_INSTANCE_ID:-}"
SESSION_ID="${CORTEX_SESSION_ID:-}"
WORKTREE_ID="${CORTEX_WORKTREE_ID:-}"
LEASE_ID="${CORTEX_LEASE_ID:-}"
RECEIPT_PATH="${CORTEX_RECEIPT_PATH:-}"
MARKER_PATH="${CORTEX_MARKER_PATH:-}"

# Materialize the result contract before the provider process starts.  A
# provider/backend can fail before the inner bridge gets far enough to write
# its own footer; the bound runner still needs a binding-shaped result rather
# than an empty file so it can classify the failure precisely.
mkdir -p "$(dirname "$RESULT_FILE")" || exit 1
printf 'executor=%s\nbackend=%s\nmodel=%s\ninstance_id=%s\nsession_id=%s\nworktree_id=%s\nlease_id=%s\nexecution_path=none\nreceipt_path=%s\nresult_path=%s\nmarker_path=%s\n' \
  "$EXECUTOR" "$BACKEND" "$MODEL" "$INSTANCE_ID" "$SESSION_ID" "$WORKTREE_ID" "$LEASE_ID" \
  "$RECEIPT_PATH" "$RESULT_FILE" "$MARKER_PATH" >"$RESULT_FILE"

if [[ "${CORTEX_NATIVE_BOUND_RUN:-}" == "1" ]]; then
  if [[ -z "$INSTANCE_ID" || -z "$SESSION_ID" || -z "$WORKTREE_ID" || -z "$LEASE_ID" ]]; then
    printf 'error=missing-bound-field\nadapter_rc=1\n' >>"$RESULT_FILE"
    exit 1
  fi
  if [[ "${CORTEX_RESULT_PATH:-}" != "$RESULT_FILE" ]]; then
    printf 'error=bound-result-path-mismatch\nadapter_rc=1\n' >>"$RESULT_FILE"
    exit 1
  fi
fi

append_contract() {
  local rc="$1" execution_path="$2" error_value="${3:-none}"
  local changed="unknown"
  if [[ -n "${CORTEX_WORKTREE:-}" && -d "${CORTEX_WORKTREE:-}" ]]; then
    changed="$(git -C "$CORTEX_WORKTREE" status --porcelain=v1 --untracked-files=all 2>/dev/null \
      | python3 -c 'import sys; print(",".join(line[3:] for line in sys.stdin.read().splitlines() if len(line) >= 4) or "none")' \
      || printf 'unknown')"
  fi
  mkdir -p "$(dirname "$RESULT_FILE")"
  {
    printf 'executor=%s\nbackend=%s\nmodel=%s\ninstance_id=%s\nsession_id=%s\nworktree_id=%s\nlease_id=%s\n' \
      "$EXECUTOR" "$BACKEND" "$MODEL" "$INSTANCE_ID" "$SESSION_ID" "$WORKTREE_ID" "$LEASE_ID"
    printf 'execution_path=%s\nreceipt_path=%s\nresult_path=%s\nmarker_path=%s\nchanged_files=%s\n' \
      "$execution_path" "$RECEIPT_PATH" "$RESULT_FILE" "$MARKER_PATH" "$changed"
    if [[ "$rc" -ne 0 ]]; then
      printf 'error=%s\n' "$error_value"
    fi
    printf 'adapter_rc=%s\n' "$rc"
  } >>"$RESULT_FILE"
}

export CORTEX_ACP_BACKEND="$BACKEND"
bash "$DIR/acp-native-mmx-a.sh" "$PROMPT_FILE" "$RESULT_FILE"
rc=$?
if [[ $rc -eq 0 ]]; then
  append_contract "$rc" "acp-native-deepseek" "none"
else
  append_contract "$rc" "none" "acp-native-deepseek"
fi
exit "$rc"
