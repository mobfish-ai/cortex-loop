#!/usr/bin/env bash
# cortex-loop:requires-env PATH
# MiniMax (api.minimax.io / api.minimaxi.com) is reachable without this script
# setting a proxy. HTTP_PROXY / HTTPS_PROXY are inherited from the caller.
#
# cortex-loop adapter: minimax — cheap text channel, keys from the environment
# Contract: $1=prompt file  $2=result file
#
# Role (important: do not treat it as the primary worker, and do not use it as judge):
#   MiniMax-M2.7 does **well-specified** work -- edit code from a fix-brief, split tasks, write copy,
#   structured fixes. The clearer the spec, the more it resembles filling blanks, the better it fits.
#   NEVER give it judge (quality veto): the rule is "AI has only a veto". A weak model's false veto
#      costs more than a miss -- it bounces good output and spins the loop while looking diligent.
#   NEVER let it write status/done: completion always goes through the mechanical gate (cortex-loop try-complete).
#      Do not trust any LLM that claims it is "done".
#   Split with claude.sh: Claude subscription only for hard reasoning / high stakes (architecture, disputed correctness, wide blast radius).
#      CLAUDE.md says "scripts/cron/automation prefer GLM/Gemini/OpenAI,
#      no Anthropic API" -- this adapter + glm.sh + cheap.sh is that rule
#      applied to unattended cortex-loop. Extra operator decision on 2026-07-30:
#      MiniMax before GLM (all 4 accounts had quota, more than GLM) -- see the fallback chain in cheap.sh.
#
# Multi-key config: see _openai_compat_lib.sh oc_ordered_keys() -- read
#   models.providers.minimax.apiKey + .apiKeys[] (array, new convention)
#   models.providers.minimax-cn.apiKey + .apiKeys[] (direct-connect account, same model id)
#   plus env MINIMAX_API_KEYS (comma-separated, temporary fill-in, using minimax's base_url)
#   Extra account keys go in ~/.openclaw/openclaw.json,
#   Under models.providers.minimax add an "apiKeys": ["sk-...", "sk-...", "sk-..."]
#   array field (keep the existing apiKey field; do not delete it). See this task report section G2.
set -uo pipefail
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
OB1_ROOT="$(cd "$DIR/../.." && pwd)"
# shellcheck source=_openai_compat_lib.sh
source "$DIR/_openai_compat_lib.sh"

PROMPT="$1"; RESULT="$2"

# Hot model switch: env override > model-policy.sh (governance/model-policy.json) > fallback literal
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

# Known pitfall (skills/ce-minimax-api-low-surrogate-fix): emoji / non-BMP characters in the prompt
# make MiniMax's internal UTF-8 to UTF-16 conversion return 400 "no low surrogate in string".
# Filter first (keep cp <= 0x9FFF, including ASCII and CJK U+4E00-U+9FFF, plus U+F000-U+F0FF). Do not wait for the error.
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
    echo "[adapter] no usable MiniMax key (openclaw.json has no models.providers.minimax(-cn).apiKey)" > "$RESULT"
    rm -f "$FILTERED_PROMPT"
    exit 89
fi
TOTAL="$(printf '%s\n' "$ORDERED" | grep -c .)"

# With fewer than 2 keys, "each node prefers a different key" is empty (both nodes fall back to
# fighting over the same key) -- do not stay silent; tell the operator to add keys (they said there are 4
# MiniMax accounts, and openclaw.json currently registers only some of them).
if [[ "$TOTAL" -lt 2 ]]; then
    {
        echo "[adapter] warning: MiniMax currently has only ${TOTAL} usable key(s); multiple nodes will share one key (cannot stagger)."
        echo "[adapter] warning: to add keys, edit ~/.openclaw/openclaw.json -> models.providers.minimax (or minimax-cn) ->"
        echo "[adapter]    add an \"apiKeys\": [\"sk-...\", \"sk-...\"] array field (keep the existing apiKey; do not delete it)."
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
    echo "[adapter] minimax all ${attempts} keys failed: ${summary}"
    echo "[adapter] executor=minimax model=$MODEL rc=97"
} > "$RESULT"
exit 97
