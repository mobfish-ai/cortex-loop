#!/usr/bin/env bash
# cortex-loop:requires-env PATH
# Note: local inference needs no outbound proxy (that is why it is the offline fallback)
# cortex-loop adapter: ollama — local fallback when offline or quota is exhausted
# Contract: $1=prompt file  $2=result file
#
# Role (important: do not treat it as the primary worker):
#   The local small model only does **low-judgment** work -- split an intent into task rows, write alert copy, answer fingerprint probes.
#   NEVER give it judge (quality veto): the rule is "AI has only a veto",
#      and a weak model's false veto costs more than a miss -- it bounces good output and spins the loop while looking diligent.
#   NEVER let it write status: completion is decided only by the mechanical gate.
#
# Model choice: prefer a Chinese-native model (this vault is mostly Chinese; Llama/Gemma/Phi are weaker on Chinese).
#   CORTEX_OLLAMA_MODEL overrides the default; the default is a small Chinese-friendly model.
set -uo pipefail
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
PROMPT="$1"; RESULT="$2"
MODEL="${CORTEX_OLLAMA_MODEL:-qwen3:4b}"

if ! command -v ollama >/dev/null 2>&1; then
  echo "[adapter] ollama is not installed on this machine -- no local fallback" > "$RESULT"
  exit 127
fi
if ! ollama list 2>/dev/null | awk 'NR>1{print $1}' | grep -q "^${MODEL%%:*}"; then
  { echo "[adapter] ollama is installed but model ${MODEL} is missing"
    echo "pull: ollama pull ${MODEL}"; } > "$RESULT"
  exit 126
fi

timeout 900 ollama run "$MODEL" "$(cat "$PROMPT")" > "$RESULT" 2>&1
rc=$?
{ echo; echo "[adapter] executor=ollama model=${MODEL} rc=${rc}"
  echo "[adapter] local fallback output: limited judgment; the mechanical gate still decides completion"; } >> "$RESULT"
exit $rc
