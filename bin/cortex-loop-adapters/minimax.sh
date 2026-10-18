#!/usr/bin/env bash
# cortex-loop:requires-env PATH
# MiniMax (api.minimax.io / api.minimaxi.com) is reachable without this script
# setting a proxy. HTTP_PROXY / HTTPS_PROXY are inherited from the caller.
#
# cortex-loop adapter: minimax — cheap text channel, keys from the environment
# 约定接口：$1=提示词文件  $2=结果文件
#
# 定位（重要，别把它当主力，也别当 judge）：
#   MiniMax-M2.7 干**有明确规格**的活 —— 照 fix-brief 改代码、拆任务、写文案、
#   结构化修复。规格越明确、越像"填空"，越适合它。
#   ⛔ 绝不给它 judge（质量否决）：铁律是「AI 只有否决权」，弱模型误否决的成本
#      高于漏放——会把好产出打回、让环空转，看起来还很尽责。
#   ⛔ 也绝不给它写 status/done：完成判定永远只走机械门（cortex-loop try-complete），
#      不采信任何 LLM 自称"完成"。
#   与 claude.sh 的分工：需强推理/高 stakes（架构决策、正确性有争议、牵一发动全身）
#      才上 Claude 订阅；CLAUDE.md 铁律「脚本/cron/自动化 优先 GLM/Gemini/OpenAI，
#      禁 Anthropic API」——本 adapter + glm.sh + cheap.sh 就是那条铁律在
#      cortex-loop 无人值守场景下的落地面。2026-07-30 operator 追加拍板：
#      MiniMax 优先于 GLM（4 个账号都有额度，比 GLM 更充裕）——见 cheap.sh 的降级链。
#
# 多 key 配置：见 _openai_compat_lib.sh oc_ordered_keys() —— 读
#   models.providers.minimax.apiKey + .apiKeys[]（数组，新约定）
#   models.providers.minimax-cn.apiKey + .apiKeys[]（国内直连账号，同一模型 id）
#   外加 env MINIMAX_API_KEYS（逗号分隔，临时补位用，套用 minimax 的 base_url）
#   Extra account keys go in ~/.openclaw/openclaw.json,
#   在 models.providers.minimax 下加一个 "apiKeys": ["sk-...", "sk-...", "sk-..."]
#   数组字段（与已有的 apiKey 字段并存，不用删旧的）。见本任务报告 §G2 操作步骤。
set -uo pipefail
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
OB1_ROOT="$(cd "$DIR/../.." && pwd)"
# shellcheck source=_openai_compat_lib.sh
source "$DIR/_openai_compat_lib.sh"

PROMPT="$1"; RESULT="$2"

# 模型热切换：env 覆盖 > model-policy.sh(governance/model-policy.json) > 兜底字面量
MODEL="${CORTEX_MINIMAX_MODEL:-}"
if [[ -z "$MODEL" ]]; then
    MODEL="$(bash "$OB1_ROOT/bin/model-policy.sh" get cortex.adapter.cheap.minimax 2>/dev/null)"
fi
MODEL="${MODEL:-MiniMax-M2.7}"

STATE_FILE="${OC_KEY_STATE_FILE:-$HOME/.openclaw/state/cortex-loop-cheap-key-state.json}"
mkdir -p "$(dirname "$STATE_FILE")"
COOLDOWN="${CORTEX_CHEAP_COOLDOWN_SEC:-180}"
TIMEOUT="${CORTEX_MINIMAX_TIMEOUT:-120}"

# Two nodes can prefer different MiniMax accounts so they do not share one
# quota. CORTEX_NODE is the node id (run_adapter exports it). When it is
# unset, this script uses the same alias rules as bin/cortex-loop node_id().
# Nodes listed in CORTEX_MINIMAX_CN_NODES (comma-separated) try the CN
# provider first. Everyone else tries the international provider first.
# CORTEX_MINIMAX_PROVIDERS overrides the order entirely.
NODE="${CORTEX_NODE:-}"
if [[ -z "$NODE" ]]; then
    _host="$(hostname 2>/dev/null | tr '[:upper:]' '[:lower:]')"
    NODE="$_host"
    _aliases="${CORTEX_NODE_ALIASES:-}"
    if [[ -n "$_aliases" ]]; then
        IFS=',' read -ra _pairs <<< "$_aliases"
        for _pair in "${_pairs[@]}"; do
            _key="${_pair%%=*}"
            _name="${_pair#*=}"
            _key="$(printf '%s' "$_key" | tr '[:upper:]' '[:lower:]')"
            _name="$(printf '%s' "$_name" | tr '[:upper:]' '[:lower:]')"
            if [[ -n "$_key" && -n "$_name" && "$_host" == *"$_key"* ]]; then
                NODE="$_name"
                break
            fi
        done
    fi
fi
PROVIDERS_ORDER="minimax,minimax-cn"
if [[ -n "${CORTEX_MINIMAX_CN_NODES:-}" ]]; then
    case ",${CORTEX_MINIMAX_CN_NODES}," in
        *",${NODE},"*) PROVIDERS_ORDER="minimax-cn,minimax" ;;
    esac
fi
PROVIDERS_ORDER="${CORTEX_MINIMAX_PROVIDERS:-$PROVIDERS_ORDER}"

# 已知坑（skills/ce-minimax-api-low-surrogate-fix）：prompt 里的 emoji/非 BMP 字符
# 会让 MiniMax 内部 UTF-8→UTF-16 转换报 "no low surrogate in string" 400 错误。
# 主动过滤一遍（保留 ASCII + CJK 常用区 + 换行/空格/Tab），不等它报错才处理。
FILTERED_PROMPT="$(mktemp /tmp/oc-minimax-prompt.XXXXXX)"
python3 - "$PROMPT" "$FILTERED_PROMPT" <<'PYEOF'
import sys
src, dst = sys.argv[1], sys.argv[2]
with open(src, "r", encoding="utf-8", errors="replace") as f:
    data = f.read()
out = []
for c in data:
    cp = ord(c)
    if cp <= 0x9FFF or (0xF000 <= cp <= 0xF0FF):
        out.append(c)
with open(dst, "w", encoding="utf-8") as f:
    f.write("".join(out))
PYEOF

ORDERED="$(oc_ordered_keys "$PROVIDERS_ORDER" "MINIMAX_API_KEYS" "$STATE_FILE" "$COOLDOWN")"
if [[ -z "$ORDERED" ]]; then
    echo "[adapter] 无可用 MiniMax key（openclaw.json 未配置 models.providers.minimax(-cn).apiKey）" > "$RESULT"
    rm -f "$FILTERED_PROMPT"
    exit 89
fi
TOTAL="$(printf '%s\n' "$ORDERED" | grep -c .)"

# 只有 <2 把 key 时，"两节点各自优先不同 key"这件事名存实亡（两节点会退化成
# 争抢同一把）——不要静默，明确告诉 operator 该补 key 了（operator 提到实际有 4 个
# MiniMax 账号，目前 openclaw.json 只登记了其中的一部分）。
if [[ "$TOTAL" -lt 2 ]]; then
    {
        echo "[adapter] ⚠️ 提示：MiniMax 当前只有 ${TOTAL} 把可用 key，多个节点会共用同一把（无法错峰）。"
        echo "[adapter] ⚠️ 补齐步骤：编辑 ~/.openclaw/openclaw.json → models.providers.minimax（或 minimax-cn）→"
        echo "[adapter]    加一个 \"apiKeys\": [\"sk-...\", \"sk-...\"] 数组字段（与已有 apiKey 并存，不用删旧的）。"
    } >&2
fi

attempts=0
summary=""
success=0
while IFS=$'\t' read -r label base_url key hash; do
    [[ -z "$label" ]] && continue
    attempts=$((attempts + 1))
    if oc_call "$base_url" "$key" "$MODEL" "$FILTERED_PROMPT" "$RESULT" "$TIMEOUT"; then
        oc_mark_success "$STATE_FILE" "$hash"
        { echo; echo "[adapter] executor=minimax model=$MODEL key=${label} attempt=${attempts}/${TOTAL} rc=0"; } >> "$RESULT"
        success=1
        break
    else
        summary="${summary}[${label}:${OC_ERROR_KIND}] "
        oc_mark_failure "$STATE_FILE" "$hash" "$label"
    fi
done <<< "$ORDERED"

rm -f "$FILTERED_PROMPT"

if [[ $success -eq 1 ]]; then
    exit 0
fi

{
    echo "[adapter] minimax 全部 ${attempts} 个 key 失败：${summary}"
    echo "[adapter] executor=minimax model=$MODEL rc=97"
} > "$RESULT"
exit 97
