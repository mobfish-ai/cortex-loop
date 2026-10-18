#!/usr/bin/env bash
# cortex-loop adapter: hive — HIVE-mode sub-agent dispatch executor
# cortex-loop:requires-env PATH
# Contract: $1=prompt file  $2=result file
#
# Purpose: cortex-loop starts a HIVE dispatch through this adapter.
# Prompt file format (hive skill dispatch prompt):
#   task_id=<id>
#   plan_id=<plan>
#   node=<dispatcher>
#   ---
#   <prompt body>
#
# Ad-hoc tasks (task_id starts with adhoc-): write the claim ref at dispatch time,
# without creating a task card first. After the claim is written the adapter returns dispatched immediately.
# The main thread later starts the real sub-agent through the HIVE skill.
set -uo pipefail
PROMPT="$1"; RESULT="$2"
OB1_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

# Parse task metadata from the prompt file
TASK_ID="$(sed -n 's/^task_id=//p' "$PROMPT" 2>/dev/null | head -1)"
PLAN_ID="$(sed -n 's/^plan_id=//p' "$PROMPT" 2>/dev/null | head -1)"
NODE="$(sed -n 's/^node=//p' "$PROMPT" 2>/dev/null | head -1)"
DISPATCHER="${NODE:-orchestrator}"

# Ad-hoc task id format: adhoc-<epoch>-<dispatcher>
if [[ "$TASK_ID" =~ ^adhoc-[0-9]+ ]]; then
  ADHOC_CLAIM="adhoc-claim"
else
  ADHOC_CLAIM=""
fi

# Write a spotlight heartbeat log (for cortex-trace.sh)
mkdir -p /tmp/spotlight
SPOTLIGHT_LOG="/tmp/spotlight/hive-$(date +%s)-${TASK_ID:-unknown}.log"
{
  echo "timestamp=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "executor=hive"
  echo "task_id=${TASK_ID:-unknown}"
  echo "plan_id=${PLAN_ID:-unknown}"
  echo "dispatcher=${DISPATCHER}"
  echo "prompt_file=$PROMPT"
  echo "status=dispatched"
} > "$SPOTLIGHT_LOG"

# Write RESULT immediately (adapter contract: $2 is the result file)
{
  echo "[hive adapter]"
  echo "executor=hive"
  echo "task_id=${TASK_ID:-unknown}"
  echo "plan_id=${PLAN_ID:-unknown}"
  echo "dispatcher=${DISPATCHER}"
  echo "spotlight_log=$SPOTLIGHT_LOG"
  echo "status=dispatched"
  echo "timestamp=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "note=HIVE dispatch recorded — actual sub-agent execution follows via HIVE skill"
} > "$RESULT"

exit 0
