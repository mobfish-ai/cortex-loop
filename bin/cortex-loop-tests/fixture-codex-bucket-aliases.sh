#!/usr/bin/env bash
# Static, quota-free fixture for the two Codex loop aliases.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LUNA="$ROOT/bin/cortex-loop-adapters/acp-native-codex-luna.sh"
SPARK="$ROOT/bin/cortex-loop-adapters/acp-native-codex-spark.sh"

[[ -x "$LUNA" && -x "$SPARK" ]]

LUNA_OUT="$(bash "$LUNA" --check-ready)"
SPARK_RC=0
SPARK_OUT="$(bash "$SPARK" --check-ready 2>&1)" || SPARK_RC=$?

[[ "$LUNA_OUT" == *"executor=acp-native:codex-luna"* ]]
[[ "$LUNA_OUT" == *"model=gpt-5.6-luna"* ]]
[[ "$LUNA_OUT" == *"quota_bucket=codex-luna"* ]]
[[ "$LUNA_OUT" != *"codex-spark"* ]]
[[ "$SPARK_RC" == "3" ]]
[[ "$SPARK_OUT" == *"executor=acp-native:codex-spark"* ]]
[[ "$SPARK_OUT" == *"model=gpt-5.3-codex-spark"* ]]
[[ "$SPARK_OUT" == *"quota_bucket=codex-spark"* ]]
[[ "$SPARK_OUT" == *"quota_status=exhausted"* ]]
[[ "$SPARK_OUT" != *"codex-luna"* ]]

# Exhausted path (no Codex spend) must still echo bound-run identity fields.
TMPDIR_FIXTURE="$(mktemp -d "${TMPDIR:-/tmp}/codex-bucket-fixture.XXXXXX")"
PROMPT_FIXTURE="$TMPDIR_FIXTURE/prompt-spark-1.txt"
RESULT_FIXTURE="$TMPDIR_FIXTURE/result-spark-1.txt"
printf 'fixture\n' > "$PROMPT_FIXTURE"
SPARK_FOOTER_RC=0
CORTEX_INSTANCE_ID=spark-1 \
CORTEX_SESSION_ID=sess-spark-1 \
CORTEX_WORKTREE_ID=wt-spark-1 \
CORTEX_LEASE_ID=lease-spark-1 \
bash "$SPARK" "$PROMPT_FIXTURE" "$RESULT_FIXTURE" || SPARK_FOOTER_RC=$?
[[ "$SPARK_FOOTER_RC" == "3" ]]
[[ "$(<"$RESULT_FIXTURE")" == *"quota_status=exhausted"* ]]
[[ "$(<"$RESULT_FIXTURE")" == *"instance_id=spark-1"* ]]
[[ "$(<"$RESULT_FIXTURE")" == *"session_id=sess-spark-1"* ]]
[[ "$(<"$RESULT_FIXTURE")" == *"worktree_id=wt-spark-1"* ]]
[[ "$(<"$RESULT_FIXTURE")" == *"lease_id=lease-spark-1"* ]]
[[ "$(<"$RESULT_FIXTURE")" == *"execution_path=codex-cli"* ]]
rm -rf "$TMPDIR_FIXTURE"

printf 'codex bucket fixture: PASS (luna=available, spark=blocked-quota, aliases isolated)\n'
