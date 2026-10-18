#!/usr/bin/env bash
# cortex-loop:requires-env PATH
# Note: GLM (open.bigmodel.cn / Zhipu) is reachable directly. This script does not set or clear
# HTTP_PROXY; it inherits the caller environment as-is.
#
# cortex-loop adapter: glm — second choice on the cheap path (fallback after every MiniMax key fails)
# Contract: $1=prompt file  $2=result file
#
# Role (same as minimax.sh: not the primary worker, and not the judge):
#   glm-4-flash does **well-specified** work -- structured fixes, edits that follow a fix-brief, task splits,
#   and copy. CLAUDE.md used to rank GLM first under "scripts/cron/automation prefer GLM".
#   On 2026-07-30 the operator put MiniMax first (more accounts, more quota) and GLM second --
#   so this file is the **fallback**, not the first choice (first choice is minimax.sh; the chain is cheap.sh).
#   NEVER give it judge (quality veto): the rule is "AI has only a veto"; a weak false veto costs more than a miss.
#   NEVER let it write status/done: completion always goes through the mechanical gate (cortex-loop try-complete).
#   Split with claude.sh: Claude subscription only for hard reasoning / high stakes; this adapter stays on the cheap path.
#
# Multi-key config: read models.providers.zhipu.apiKey + .apiKeys[] (array, new convention;
#   the operator currently has 1 GLM key, so this is unused for now; the shape is reserved for more accounts)
#   plus env GLM_API_KEYS (comma-separated, temporary fill-in).
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
    echo "[adapter] no usable GLM key (openclaw.json has no models.providers.zhipu.apiKey)" > "$RESULT"
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
    echo "[adapter] glm all ${attempts} keys failed: ${summary}"
    echo "[adapter] executor=glm model=$MODEL rc=97"
} > "$RESULT"
exit 97
