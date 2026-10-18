#!/usr/bin/env bash
# cortex-loop adapter: acp-native:codex-luna
#
# Luna owns one explicit model and local quota bucket. The wrapper delegates
# execution to the existing codex.sh contract and never changes AUTH.
set -uo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OB1_ROOT="$(cd "$DIR/../.." && pwd)"
EXECUTOR="acp-native:codex-luna"
MODEL="${CORTEX_CODEX_LUNA_MODEL:-gpt-5.6-luna}"
QUOTA_BUCKET="codex-luna"

check_ready() {
  [[ -x "$OB1_ROOT/bin/codex-validate.sh" ]] || {
    printf 'not-ready: missing codex-validate.sh\n' >&2
    return 127
  }
  [[ -f "$DIR/codex.sh" ]] || {
    printf 'not-ready: missing codex.sh\n' >&2
    return 127
  }
  printf 'ready: executor=%s model=%s quota_bucket=%s quota_status=available\n' \
    "$EXECUTOR" "$MODEL" "$QUOTA_BUCKET"
}

if [[ "${1:-}" == "--check-ready" ]]; then
  check_ready
  exit $?
fi

PROMPT="${1:-}"
RESULT="${2:-}"
if [[ -z "$PROMPT" || ! -f "$PROMPT" || -z "$RESULT" ]]; then
  printf '%s: missing prompt/result path\n' "$EXECUTOR" >&2
  exit 1
fi

mkdir -p "$(dirname "$RESULT")"
TMP="$(mktemp -t cortex-codex-luna.XXXXXX)"
trap 'rm -f "$TMP"' EXIT
export CORTEX_CODEX_INSTANCE="luna"
export CORTEX_CODEX_USAGE_BUCKET="$QUOTA_BUCKET"
export CODEX_QUOTA_BUCKET="$QUOTA_BUCKET"
export CODEX_BUDGET_BUCKET="$QUOTA_BUCKET"
export CODEX_VALIDATE_MODEL="$MODEL"

bash "$DIR/codex.sh" "$PROMPT" "$TMP"
RC=$?
{
  printf '[adapter] executor=%s rc=%s\n' "$EXECUTOR" "$RC"
  printf 'executor=%s\ntool_layer=codex-cli\nbackend=codex\nmodel=%s\nquota_bucket=%s\nquota_status=available\n' \
    "$EXECUTOR" "$MODEL" "$QUOTA_BUCKET"
  printf 'instance_id=%s\nsession_id=%s\nworktree_id=%s\nlease_id=%s\nexecution_path=codex-cli\n' \
    "${CORTEX_INSTANCE_ID:-}" "${CORTEX_SESSION_ID:-}" "${CORTEX_WORKTREE_ID:-}" "${CORTEX_LEASE_ID:-}"
  [[ -s "$TMP" ]] && cat "$TMP"
} > "$RESULT"
exit "$RC"
