#!/usr/bin/env bash
# cortex-loop adapter: acp-lane — L2 headless strategy lane (Grok-first + DECIDE resume)
#
# Contract (same shape as the cheap/claude adapters):
#   $1 = prompt file
#   $2 = result file
#   --check-ready  → readiness probe (exit 0 = usable)
#
# Optional prompt-file header:
#   topic=<id>
#   backend=grok
#   cwd=/tmp/clean-or-scratch   # ob1 root forbidden
#   simulate=1
#   ---
#   <body>
#
# Dispatch hooks:
#   - CLOCK executor=acp-lane (whole line)
#   - or task requires_executor=acp-lane (one task, ahead of CLOCK)
#   - engine: resolve_task_executor + render_prompt injects the header fields
#
# Safety: default cwd=/tmp/grok-scratch; the client blocks the vault root a second time
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
  # dry-run spends no model; it only proves the client can start
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
# vault root forbidden
if [[ "$(cd "$CWD" 2>/dev/null && pwd -P)" == "$(cd "$OB1_ROOT" && pwd -P)" ]]; then
  CWD="/tmp/grok-scratch"
fi
if [[ "${CORTEX_ACP_SIMULATE:-}" == "1" || "${CORTEX_ACP_SIMULATE:-}" == "true" ]]; then
  SIM=1
fi

# Body: after the first ---, otherwise the whole file
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
  args+=( --simulate --simulate-replies $'Simulated adapter finished.\nEvidence path written.\n' )
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
  # usage placeholder: mark UNKNOWN when there are no tokens (IMM-T45 energy-field rule)
  echo "[usage] input_tokens=UNKNOWN output_tokens=UNKNOWN source=acp-lane"
} > "$RESULT_FILE"

echo "status=done exit=$rc" >> "$SPOT"
exit "$rc"
