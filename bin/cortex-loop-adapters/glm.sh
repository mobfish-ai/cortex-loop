#!/usr/bin/env bash
# cortex-loop:requires-env PATH
# 说明：GLM(open.bigmodel.cn / 智谱) 是国内可直连服务商，脚本不主动设置/清空
# HTTP_PROXY，继承调用环境原样传递。
#
# cortex-loop adapter: glm — 廉价执行通道次选（MiniMax 全部 key 失败后的降级目标）
# 约定接口：$1=提示词文件  $2=结果文件
#
# 定位（同 minimax.sh，别当主力，也别当 judge）：
#   glm-4-flash 干**有明确规格**的活 —— 结构化修复、按 fix-brief 改代码、拆任务、
#   写文案。CLAUDE.md 铁律「脚本/cron/自动化 优先 GLM」原本把 GLM 排第一位，
#   2026-07-30 operator 拍板改为 MiniMax 优先（账号更多、额度更充裕）、GLM 次选——
#   本文件因此定位为**降级目标**，不是首选（首选见 minimax.sh，降级链见 cheap.sh）。
#   ⛔ 绝不给它 judge（质量否决）：铁律「AI 只有否决权」，弱模型误否决成本高于漏放。
#   ⛔ 也绝不给它写 status/done：完成判定永远只走机械门（cortex-loop try-complete）。
#   与 claude.sh 的分工：需强推理/高 stakes 才上 Claude 订阅；本 adapter 默认走廉价通道。
#
# 多 key 配置：读 models.providers.zhipu.apiKey + .apiKeys[]（数组，新约定，
#   operator 目前只配了 1 个 GLM key，暂不需要；结构预留以防未来多账号）
#   外加 env GLM_API_KEYS（逗号分隔，临时补位用）。
set -uo pipefail
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
OB1_ROOT="$(cd "$DIR/../.." && pwd)"
# shellcheck source=_openai_compat_lib.sh
source "$DIR/_openai_compat_lib.sh"

PROMPT="$1"; RESULT="$2"

MODEL="${CORTEX_GLM_MODEL:-}"
if [[ -z "$MODEL" ]]; then
    MODEL="$(bash "$OB1_ROOT/bin/model-policy.sh" get cortex.adapter.cheap.glm 2>/dev/null)"
fi
MODEL="${MODEL:-glm-4-flash}"

STATE_FILE="${OC_KEY_STATE_FILE:-$HOME/.openclaw/state/cortex-loop-cheap-key-state.json}"
mkdir -p "$(dirname "$STATE_FILE")"
COOLDOWN="${CORTEX_CHEAP_COOLDOWN_SEC:-180}"
TIMEOUT="${CORTEX_GLM_TIMEOUT:-120}"

ORDERED="$(oc_ordered_keys "zhipu" "GLM_API_KEYS" "$STATE_FILE" "$COOLDOWN")"
if [[ -z "$ORDERED" ]]; then
    echo "[adapter] 无可用 GLM key（openclaw.json 未配置 models.providers.zhipu.apiKey）" > "$RESULT"
    exit 89
fi
TOTAL="$(printf '%s\n' "$ORDERED" | grep -c .)"

attempts=0
summary=""
success=0
while IFS=$'\t' read -r label base_url key hash; do
    [[ -z "$label" ]] && continue
    attempts=$((attempts + 1))
    if oc_call "$base_url" "$key" "$MODEL" "$PROMPT" "$RESULT" "$TIMEOUT"; then
        oc_mark_success "$STATE_FILE" "$hash"
        { echo; echo "[adapter] executor=glm model=$MODEL key=${label} attempt=${attempts}/${TOTAL} rc=0"; } >> "$RESULT"
        success=1
        break
    else
        summary="${summary}[${label}:${OC_ERROR_KIND}] "
        oc_mark_failure "$STATE_FILE" "$hash" "$label"
    fi
done <<< "$ORDERED"

if [[ $success -eq 1 ]]; then
    exit 0
fi

{
    echo "[adapter] glm 全部 ${attempts} 个 key 失败：${summary}"
    echo "[adapter] executor=glm model=$MODEL rc=97"
} > "$RESULT"
exit 97
