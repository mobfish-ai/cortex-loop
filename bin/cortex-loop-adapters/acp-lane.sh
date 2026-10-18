#!/usr/bin/env bash
# cortex-loop adapter: acp-lane — L2 headless 策略 lane（Grok-first + DECIDE 续跑）
#
# 约定接口（与 cheap/claude adapter 同构）：
#   $1 = 提示词文件
#   $2 = 结果文件
#   --check-ready  → 就绪探测（exit 0=可用）
#
# 提示词文件可选头：
#   topic=<id>
#   backend=grok
#   cwd=/tmp/clean-or-scratch   # 禁止 ob1 根
#   simulate=1
#   ---
#   <正文>
#
# 调度挂点：
#   - CLOCK executor=acp-lane（整线）
#   - 或任务 requires_executor=acp-lane（单任务，优先于 CLOCK）
#   - 引擎：resolve_task_executor + render_prompt 注入头字段
#
# 安全：默认 cwd=/tmp/grok-scratch；client 内二次拦截 vault 根
set -uo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
OB1_ROOT="$(cd "$DIR/../.." && pwd)"
CLIENT="${OB1_ROOT}/bin/acp-policy-client.sh"

if [[ "${1:-}" == "--check-ready" ]]; then
  if [[ ! -f "$CLIENT" ]]; then
    printf 'acp-policy-client-missing\n' >&2
    exit 127
  fi
  if [[ ! -x "$CLIENT" ]] && ! head -1 "$CLIENT" | grep -q bash; then
    printf 'acp-policy-client-not-invokable\n' >&2
    exit 127
  fi
  # dry-run 不烧模型，只证明 client 可启动
  out=$(bash "$CLIENT" dry-run --topic adapter-ready --backend grok --prompt "ping" 2>/dev/null) || true
  st=$(printf '%s' "$out" | python3 -c 'import sys,json
try:
  print(json.load(sys.stdin).get("status",""))
except Exception:
  print("")
' 2>/dev/null)
  if [[ "$st" == "dry-run" ]]; then
    printf 'ready: acp-lane + policy-client dry-run\n'
    exit 0
  fi
  printf 'policy-client-dry-run-failed\n' >&2
  exit 89
fi

PROMPT_FILE="${1:-}"
RESULT_FILE="${2:-}"

[ -n "$PROMPT_FILE" ] && [ -f "$PROMPT_FILE" ] || { echo "acp-lane: missing prompt file" >&2; exit 1; }
[ -n "$RESULT_FILE" ] || { echo "acp-lane: missing result path" >&2; exit 1; }
[ -f "$CLIENT" ] || { echo "acp-lane: missing $CLIENT" >&2; exit 127; }

TOPIC="$(sed -n 's/^topic=//p' "$PROMPT_FILE" 2>/dev/null | head -1)"
BACKEND="$(sed -n 's/^backend=//p' "$PROMPT_FILE" 2>/dev/null | head -1)"
CWD="$(sed -n 's/^cwd=//p' "$PROMPT_FILE" 2>/dev/null | head -1)"
SIM="$(sed -n 's/^simulate=//p' "$PROMPT_FILE" 2>/dev/null | head -1)"
TOPIC="${TOPIC:-acp-loop}"
BACKEND="${BACKEND:-${CORTEX_ACP_BACKEND:-grok}}"
CWD="${CWD:-${CORTEX_ACP_CWD:-/tmp/grok-scratch}}"
# vault 根禁止
if [[ "$(cd "$CWD" 2>/dev/null && pwd -P)" == "$(cd "$OB1_ROOT" && pwd -P)" ]]; then
  CWD="/tmp/grok-scratch"
fi
if [[ "${CORTEX_ACP_SIMULATE:-}" == "1" || "${CORTEX_ACP_SIMULATE:-}" == "true" ]]; then
  SIM=1
fi

# 正文：首个 --- 之后，否则全文
BODY=$(awk 'BEGIN{p=0} /^---$/{p=1;next} p{print}' "$PROMPT_FILE")
if [ -z "$BODY" ]; then
  BODY=$(cat "$PROMPT_FILE")
fi

mkdir -p /tmp/spotlight "$CWD" 2>/dev/null || true
SPOT="/tmp/spotlight/acp-lane-$(date +%s)-$$.log"
{
  echo "timestamp=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "executor=acp-lane"
  echo "tool_layer=acp-lane"
  echo "topic=$TOPIC"
  echo "backend=$BACKEND"
  echo "cwd=$CWD"
  echo "status=starting"
} > "$SPOT"

args=( run --topic "$TOPIC" --backend "$BACKEND" --cwd "$CWD" --prompt "$BODY" )
if [ "$SIM" = "1" ] || [ "$SIM" = "true" ]; then
  args+=( --simulate --simulate-replies $'模拟 adapter 完成。\n证据路径已写入。\n' )
fi

set +e
out=$(bash "$CLIENT" "${args[@]}" 2>>"$SPOT")
rc=$?
set -e

{
  echo "[adapter] executor=acp-lane rc=${rc}"
  echo "tool_layer=acp-lane"
  echo "executor=acp-lane"
  echo "topic=$TOPIC"
  echo "backend=$BACKEND"
  echo "cwd=$CWD"
  echo "exit=$rc"
  echo "spotlight=$SPOT"
  echo "client_json=$out"
  echo "timestamp=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  # usage 占位：无 token 时标 UNKNOWN（IMM-T45 能量字段纪律）
  echo "[usage] input_tokens=UNKNOWN output_tokens=UNKNOWN source=acp-lane"
} > "$RESULT_FILE"

echo "status=done exit=$rc" >> "$SPOT"
exit "$rc"
