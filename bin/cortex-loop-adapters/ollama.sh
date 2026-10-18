#!/usr/bin/env bash
# cortex-loop:requires-env PATH
# 说明：本地推理，不需要出网代理（这正是它作为断网兜底的价值）
# cortex-loop adapter: ollama — 断网/额度耗尽时的本地兜底
# 约定接口：$1=提示词文件  $2=结果文件
#
# 定位（重要，别把它当主力）：
#   本地小模型只干**低判断力**的活 —— 把意图拆成任务行、写告警文案、应答指纹探针。
#   ⛔ 绝不给它 judge（质量否决）：我们的铁律是「AI 只有否决权」，
#      而弱模型误否决的成本高于漏放 —— 它会把好产出打回、让环空转，看起来还很尽责。
#   ⛔ 也绝不给它写 status：完成判定永远只走机械门。
#
# 模型选择：中文原生优先（本 vault 内容以中文为主，Llama/Gemma/Phi 中文明显弱一档）。
#   CORTEX_OLLAMA_MODEL 可覆盖；默认取一个小尺寸中文友好模型。
set -uo pipefail
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
PROMPT="$1"; RESULT="$2"
MODEL="${CORTEX_OLLAMA_MODEL:-qwen3:4b}"

if ! command -v ollama >/dev/null 2>&1; then
  echo "[adapter] 本机未装 ollama —— 无本地兜底能力" > "$RESULT"
  exit 127
fi
if ! ollama list 2>/dev/null | awk 'NR>1{print $1}' | grep -q "^${MODEL%%:*}"; then
  { echo "[adapter] ollama 已装但没有模型 ${MODEL}"
    echo "拉取：ollama pull ${MODEL}"; } > "$RESULT"
  exit 126
fi

timeout 900 ollama run "$MODEL" "$(cat "$PROMPT")" > "$RESULT" 2>&1
rc=$?
{ echo; echo "[adapter] executor=ollama model=${MODEL} rc=${rc}"
  echo "[adapter] 本地兜底产出：判断力有限，完成与否仍由机械门裁定"; } >> "$RESULT"
exit $rc
