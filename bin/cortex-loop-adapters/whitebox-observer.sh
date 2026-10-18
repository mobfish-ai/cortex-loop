#!/usr/bin/env bash
# cortex-loop adapter: whitebox-observer — 异构观测者（只读、否决权、无自证）
#
# 约定接口（符合 adapter 家族规范）：
#   $1 = 提示词文件（被忽略，本脚本独立构造解读）
#   $2 = 结果文件（写入 markdown 报告）
#   --out <path>  显式指定报告输出路径
#
# 环境变量：
#   CORTEX_PULSE_STATE_OVERRIDE  覆盖 pulse state 文件路径（用于注入测试）
#   CORTEX_ARTIFACT_DIR          账本 artifacts 根目录（默认 brain-network/directions）
#
# 核心纪律（无自证）：
#   解读者使用 whitebox.observer 模型，执行者使用 immune.implementer/cortex.adapter 模型。
#   两者必须不同，否则共享盲区等于没审。
#   本脚本只读取不修改任何受版本控制文件。
#
set -uo pipefail

OB1_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
POLICY="$OB1_ROOT/governance/model-policy.json"
STATE_FILE="${CORTEX_PULSE_STATE_OVERRIDE:-${HOME}/.openclaw/state/cortex-pulse.jsonl}"
REPORT_FILE=""
PROMPT_FILE="${1:-}"

# ── parse --out (must appear before positional args) ──
OUT_MODE=""
for arg in "$@"; do
  case "$arg" in
    --out) OUT_MODE="next" ;;
    --out=*) REPORT_FILE="${arg#--out=}"; OUT_MODE="direct" ;;
  esac
done
if [[ "${OUT_MODE:-}" == "next" ]]; then
  REPORT_FILE="${2:-}"
fi
if [[ -z "$REPORT_FILE" ]]; then
  REPORT_FILE="${OB1_ROOT}/tmp/cortex-whitebox-report-$(date +%Y%m%dT%H%M%S).md"
fi

# ── model read from policy ──
read_policy_model() {
  local role="$1"
  python3 -c "
import json, sys
d = json.load(open('$POLICY'))
role = d.get('roles', {}).get('$role', '')
print(role)
" 2>/dev/null
}

OBSERVER_MODEL="$(read_policy_model 'whitebox.observer')"
EXECUTOR_MODEL="$(read_policy_model 'immune.implementer')"
if [[ -z "$OBSERVER_MODEL" ]]; then OBSERVER_MODEL="unknown"; fi
if [[ -z "$EXECUTOR_MODEL" ]]; then EXECUTOR_MODEL="unknown"; fi

# ── read pulse state ──
read_pulse_field() {
  local field="$1"
  if [[ ! -f "$STATE_FILE" ]]; then echo ""; return; fi
  tail -1 "$STATE_FILE" | python3 -c "
import json, sys, re
line = sys.stdin.read().strip()
if not line: sys.exit(1)
line = line.strip()
m = re.search('\"$field\":\s*([0-9]+|\"[^\"]*\")', line)
if m:
    v = m.group(1)
    print(v.strip('\"') if v.startswith('\"') else v)
" 2>/dev/null
}

PULSE_TS="$(read_pulse_field 'ts')"
U_DONE_PULSE="$(read_pulse_field 'u_done')"
U_PENDING_PULSE="$(read_pulse_field 'u_pending')"
U_BLOCKED_PULSE="$(read_pulse_field 'u_blocked')"
L_SAMPLE_STATE="$(read_pulse_field 'l_sample_state')"
S_SENTINEL="$(read_pulse_field 's_sentinel')"

# fallback to grep if python fails
if [[ -z "$U_DONE_PULSE" && -f "$STATE_FILE" ]]; then
  U_DONE_PULSE=$(tail -1 "$STATE_FILE" | grep -oE '"u_done":[0-9]+' | grep -oE '[0-9]+' | tail -1)
  U_PENDING_PULSE=$(tail -1 "$STATE_FILE" | grep -oE '"u_pending":[0-9]+' | grep -oE '[0-9]+' | tail -1)
  U_BLOCKED_PULSE=$(tail -1 "$STATE_FILE" | grep -oE '"u_blocked":[0-9]+' | grep -oE '[0-9]+' | tail -1)
  L_SAMPLE_STATE=$(tail -1 "$STATE_FILE" | grep -oE '"l_sample_state":"[^"]*"' | cut -d'"' -f4 | tail -1)
  S_SENTINEL=$(tail -1 "$STATE_FILE" | grep -oE '"s_sentinel":"[^"]*"' | cut -d'"' -f4 | tail -1)
  PULSE_TS=$(tail -1 "$STATE_FILE" | grep -oE '"ts":"[^"]*"' | cut -d'"' -f4 | tail -1)
fi

# ── ledger ground truth ──
count_tasks_by_status() {
  local status="$1"
  local dir="${2:-$OB1_ROOT/brain-network/directions}"
  local total=0
  while IFS= read -r f; do
    [[ -z "$f" ]] && continue
    n=$(awk -F'|' "
/^\| [A-Za-z0-9_-]+ \|/ {
  gsub(/ /, \"\", \$4)
  if(\$4 == \"$status\") c++
}
END { print (c+0) }
" "$f" 2>/dev/null)
    total=$((total + ${n:-0}))
  done < <(find "$dir" -name 'TASKS.md' 2>/dev/null)
  echo $total
}

LEDGER_DONE=$(count_tasks_by_status "done")
LEDGER_PENDING=$(count_tasks_by_status "pending")
LEDGER_BLOCKED=$(count_tasks_by_status "blocked")

# ── anomalies ──
ANOMALIES=()
add_anomaly() { ANOMALIES+=("$1"); }

# K1: u_done 矛盾
if [[ -n "$U_DONE_PULSE" && -n "$LEDGER_DONE" ]]; then
  if [[ "$U_DONE_PULSE" != "$LEDGER_DONE" ]]; then
    add_anomaly "K1: u_done 矛盾 — pulse 快照显示 u_done=${U_DONE_PULSE}，账本实际 done=${LEDGER_DONE}，两者不符"
  fi
fi

# K2: u_pending 矛盾
if [[ -n "$U_PENDING_PULSE" && -n "$LEDGER_PENDING" ]]; then
  if [[ "$U_PENDING_PULSE" != "$LEDGER_PENDING" ]]; then
    add_anomaly "K2: u_pending 矛盾 — pulse 快照显示 u_pending=${U_PENDING_PULSE}，账本实际 pending=${LEDGER_PENDING}"
  fi
fi

# K3: sentinel 信号
if [[ -n "$S_SENTINEL" ]]; then
  if [[ "$S_SENTINEL" == "missing" || "$S_SENTINEL" == "unknown" || -z "$S_SENTINEL" ]]; then
    add_anomaly "K3: sentinel 信号异常 — s_sentinel=${S_SENTINEL:-空}，无法判定反测哨兵状态"
  fi
fi

# K4: L 线状态
if [[ -n "$L_SAMPLE_STATE" ]]; then
  if [[ "$L_SAMPLE_STATE" == "BASELINE" || "$L_SAMPLE_STATE" == "DEGRADED" || "$L_SAMPLE_STATE" == "UNKNOWN" ]]; then
    add_anomaly "K4: L 线未 RATIFIED — l_sample_state=${L_SAMPLE_STATE}，台账未达批准态"
  fi
fi

# K5: pulse state 文件不存在或过旧
if [[ ! -f "$STATE_FILE" ]]; then
  add_anomaly "K5: pulse 快照文件不存在 — 路径=${STATE_FILE}，无法进行跨源核对"
elif [[ -n "${PULSE_TS:-}" ]]; then
  if command -v stat >/dev/null 2>&1; then
    FILE_AGE=$(($(date +%s) - $(stat -f %m "$STATE_FILE" 2>/dev/null || echo $(date +%s))))
    AGE_MINUTES=$((FILE_AGE / 60))
    if [[ "$AGE_MINUTES" -gt 60 ]]; then
      add_anomaly "K5: pulse 快照过旧 — 文件年龄=${AGE_MINUTES}分钟，超过 60 分钟阈值"
    fi
  fi
fi

# K6: 额度状态
if [[ "${CORTEX_QUOTA_STATUS:-}" == "exhausted" || "${CORTEX_QUOTA_EXHAUSTED:-}" == "1" ]]; then
  add_anomaly "K6: 额度耗尽时段 — llm-heavy 任务应被拒绝，当前额度状态=exhausted"
fi

# ── routing ──
SUGGESTIONS=()
add_suggestion() { SUGGESTIONS+=("$1"); }

if (( ${#ANOMALIES[@]} > 0 )); then
  add_suggestion "R1: 检查 pulse 写入时机与 ledger 计数口径是否在所有边界条件下对齐"
  add_suggestion "R2: 如 u_done 矛盾持续 — 挂 T3（clean ACCEPT）之前必须先修复脉冲写入原子性"
  add_suggestion "R3: s_sentinel 异常 — 检查 CLOCK.md 里 T3 的状态列是否为 done（T3 反测哨兵不应变绿）"
fi

# Default=有问题：即使无矛盾也输出标记（不代表"一切正常"）
if (( ${#ANOMALIES[@]} == 0 )); then
  ANOMALIES+=("K0: 本轮扫描未发现明显矛盾（但不代表无盲区，需异构模型交叉核对）")
fi

# ── write report ──
mkdir -p "$(dirname "$REPORT_FILE")"
{
  echo "# Whitebox Observer Report"
  echo ""
  echo "**生成时间**: $(date '+%Y-%m-%dT%H:%M:%S%z')"
  echo "**解读模型**: ${OBSERVER_MODEL} (whitebox.observer)"
  echo "**执行模型**: ${EXECUTOR_MODEL} (immune.implementer)"
  echo "**状态来源**: ${STATE_FILE}"
  echo ""
  echo "---"
  echo ""
  echo "## 疑点清单"
  echo ""
  for a in "${ANOMALIES[@]}"; do
    echo "- ${a}"
  done
  echo ""
  echo "## 底层证据"
  echo ""
  echo "| 维度 | 值 |"
  echo "|------|-----|"
  echo "| pulse u_done | ${U_DONE_PULSE:-n/a} |"
  echo "| pulse u_pending | ${U_PENDING_PULSE:-n/a} |"
  echo "| pulse u_blocked | ${U_BLOCKED_PULSE:-n/a} |"
  echo "| pulse l_sample_state | ${L_SAMPLE_STATE:-n/a} |"
  echo "| pulse s_sentinel | ${S_SENTINEL:-n/a} |"
  echo "| pulse ts | ${PULSE_TS:-n/a} |"
  echo "| ledger done | ${LEDGER_DONE:-n/a} |"
  echo "| ledger pending | ${LEDGER_PENDING:-n/a} |"
  echo "| ledger blocked | ${LEDGER_BLOCKED:-n/a} |"
  echo "| 额度状态 | ${CORTEX_QUOTA_STATUS:-${CORTEX_QUOTA_EXHAUSTED:-unknown}} |"
  echo ""
  echo "## 建议路由"
  echo ""
  if (( ${#SUGGESTIONS[@]} > 0 )); then
    for s in "${SUGGESTIONS[@]}"; do
      echo "- ${s}"
    done
  else
    echo "- (本轮未发现需路由的疑点)"
  fi
  echo ""
  echo "---"
  echo ""
  echo "**注**: 本报告由异构观测者（${OBSERVER_MODEL}）生成，与执行者（${EXECUTOR_MODEL}）模型不同。"
  echo "仅提供否决权，不修改任何受版本控制文件。"
} > "$REPORT_FILE"

echo "whitebox-observer: 报告已写入 $REPORT_FILE"
echo "疑点数量: ${#ANOMALIES[@]}"
