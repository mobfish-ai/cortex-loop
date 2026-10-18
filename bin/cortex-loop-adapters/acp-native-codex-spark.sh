#!/usr/bin/env bash
# cortex-loop adapter: acp-native:codex-spark
#
# Spark is a separate accounting bucket from Luna. Bare adapter calls
# require CORTEX_CODEX_SPARK_ALLOW=1 so a Luna lane cannot silently spend
# Spark. bound-run MATRIX (codex, gpt-5.3-codex-spark) sets ALLOW=1 itself.
# quota_status=exhausted without ALLOW is the bucket gate, not vendor quota.
set -uo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OB1_ROOT="$(cd "$DIR/../.." && pwd)"
EXECUTOR="acp-native:codex-spark"
MODEL="${CORTEX_CODEX_SPARK_MODEL:-gpt-5.3-codex-spark}"
QUOTA_BUCKET="codex-spark"

check_ready() {
  [[ -x "$OB1_ROOT/bin/codex-validate.sh" ]] || {
    printf 'not-ready: missing codex-validate.sh\n' >&2
    return 127
  }
  [[ -f "$DIR/codex.sh" ]] || {
    printf 'not-ready: missing codex.sh\n' >&2
    return 127
  }
  if [[ "${CORTEX_CODEX_SPARK_ALLOW:-0}" != "1" ]]; then
    printf 'blocked: executor=%s model=%s quota_bucket=%s quota_status=exhausted\n' \
      "$EXECUTOR" "$MODEL" "$QUOTA_BUCKET" >&2
    return 3
  fi
  printf 'ready: executor=%s model=%s quota_bucket=%s quota_status=operator-override\n' \
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

emit_bound_footer() {
  local rc="$1" quota_status="$2" extra="${3:-}"
  printf '[adapter] executor=%s rc=%s\n' "$EXECUTOR" "$rc"
  printf 'executor=%s\ntool_layer=codex-cli\nbackend=codex\nmodel=%s\nquota_bucket=%s\nquota_status=%s\n' \
    "$EXECUTOR" "$MODEL" "$QUOTA_BUCKET" "$quota_status"
  printf 'instance_id=%s\nsession_id=%s\nworktree_id=%s\nlease_id=%s\nexecution_path=codex-cli\n' \
    "${CORTEX_INSTANCE_ID:-}" "${CORTEX_SESSION_ID:-}" "${CORTEX_WORKTREE_ID:-}" "${CORTEX_LEASE_ID:-}"
  if [[ -n "$extra" ]]; then
    printf '%s\n' "$extra"
  fi
}

mkdir -p "$(dirname "$RESULT")"
if [[ "${CORTEX_CODEX_SPARK_ALLOW:-0}" != "1" ]]; then
  {
    emit_bound_footer 3 exhausted "error=quota_exhausted"
  } > "$RESULT"
  exit 3
fi

TMP="$(mktemp -t cortex-codex-spark.XXXXXX)"
trap 'rm -f "$TMP"' EXIT
export CORTEX_CODEX_INSTANCE="spark"
export CORTEX_CODEX_USAGE_BUCKET="$QUOTA_BUCKET"
export CODEX_QUOTA_BUCKET="$QUOTA_BUCKET"
export CODEX_BUDGET_BUCKET="$QUOTA_BUCKET"
export CODEX_VALIDATE_MODEL="$MODEL"

bash "$DIR/codex.sh" "$PROMPT" "$TMP"
RC=$?
{
  emit_bound_footer "$RC" operator-override
  [[ -s "$TMP" ]] && cat "$TMP"
} > "$RESULT"
exit "$RC"
