#!/usr/bin/env bash
# 验证某个执行器是否真的活着 —— 完成判据是「症状消失」，不是「文件存在」。
# 用于 self-defect 类任务：这类任务改的是节点环境/远程配置，没有单一产出文件。
set -uo pipefail
EXEC="${1:?用法: exec-alive.sh <executor>}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ADAPTER="$ROOT/bin/cortex-loop-adapters/${EXEC}.sh"
[[ -f "$ADAPTER" ]] || { echo "无此执行器 adapter: $EXEC"; exit 2; }

PROMPT=$(mktemp); RESULT=$(mktemp)
trap 'rm -f "$PROMPT" "$RESULT"' EXIT
echo "只回两个字：在线" > "$PROMPT"

timeout 120 bash "$ADAPTER" "$PROMPT" "$RESULT" >/dev/null 2>&1
rc=$?
body=$(cat "$RESULT" 2>/dev/null)

# 认证/额度类故障的特征串命中即判失败（即使退出码是 0 也不放过）
if grep -qiE "not logged in|401|403|unauthorized|authenticat|quota|rate.?limit|请先登录" <<<"$body"; then
  echo "FAIL $EXEC 仍有认证/额度故障: $(head -1 <<<"$body")"
  exit 1
fi
[[ $rc -ne 0 ]] && { echo "FAIL $EXEC 退出码 $rc"; exit 1; }
[[ -z "$body" ]] && { echo "FAIL $EXEC 无输出"; exit 1; }
echo "PASS $EXEC 可用"
