#!/usr/bin/env bash
# cortex-loop adapter: hive — HIVE 模式 sub-agent 派发执行器
# cortex-loop:requires-env PATH
# 约定接口：$1=提示词文件  $2=结果文件
#
# 用途：cortex-loop 通过本 adapter 发起 HIVE 派发任务。
# 提示词文件格式（hive skill 的派发 prompt 规范）：
#   task_id=<id>
#   plan_id=<plan>
#   node=<dispatcher>
#   ---
#   <提示词正文>
#
# 即兴任务（task_id 以 adhoc- 开头）：在派发同一时刻写入 claim ref，
# 不等先建任务卡。claim 写入后 adapter 立即返回 dispatched 状态，
# 实际的 sub-agent 执行由主线程后续通过 HIVE skill 发起。
set -uo pipefail
PROMPT="$1"; RESULT="$2"
OB1_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

# 解析提示词文件里的任务元信息
TASK_ID="$(sed -n 's/^task_id=//p' "$PROMPT" 2>/dev/null | head -1)"
PLAN_ID="$(sed -n 's/^plan_id=//p' "$PROMPT" 2>/dev/null | head -1)"
NODE="$(sed -n 's/^node=//p' "$PROMPT" 2>/dev/null | head -1)"
DISPATCHER="${NODE:-orchestrator}"

# 即兴任务 id 格式：adhoc-<epoch>-<dispatcher>
if [[ "$TASK_ID" =~ ^adhoc-[0-9]+ ]]; then
  ADHOC_CLAIM="adhoc-claim"
else
  ADHOC_CLAIM=""
fi

# 写入 spotlight 心跳日志（供 cortex-trace.sh 追溯）
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

# 立即写入 RESULT（adapter 约定：$2 是执行结果文件）
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
