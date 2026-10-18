#!/usr/bin/env bash
# cortex-loop adapter: whitebox-observer — heterogeneous observer (read-only, veto, no self-certification)
#
# Contract (adapter family):
#   $1 = prompt file (ignored; this script builds its own reading)
#   $2 = result file (markdown report is written here)
#   --out <path>  explicit report output path
#
# Environment:
#   CORTEX_PULSE_STATE_OVERRIDE  override the pulse state file path (for injected tests)
#   CORTEX_ARTIFACT_DIR          ledger artifacts root (default brain-network/directions)
#
# Core rule (no self-certification):
#   The reader uses the whitebox.observer model; the executor uses immune.implementer/cortex.adapter.
#   They must differ, or a shared blind spot means nothing was reviewed.
#   This script only reads. It does not modify any version-controlled file.
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

# K1: u_done mismatch
if [[ -n "$U_DONE_PULSE" && -n "$LEDGER_DONE" ]]; then
  if [[ "$U_DONE_PULSE" != "$LEDGER_DONE" ]]; then
    add_anomaly "K1: u_done mismatch - pulse snapshot u_done=${U_DONE_PULSE}, ledger done=${LEDGER_DONE}; they disagree"
  fi
fi

# K2: u_pending mismatch
if [[ -n "$U_PENDING_PULSE" && -n "$LEDGER_PENDING" ]]; then
  if [[ "$U_PENDING_PULSE" != "$LEDGER_PENDING" ]]; then
    add_anomaly "K2: u_pending mismatch - pulse snapshot u_pending=${U_PENDING_PULSE}, ledger pending=${LEDGER_PENDING}"
  fi
fi

# K3: sentinel signal
if [[ -n "$S_SENTINEL" ]]; then
  if [[ "$S_SENTINEL" == "missing" || "$S_SENTINEL" == "unknown" || -z "$S_SENTINEL" ]]; then
    add_anomaly "K3: sentinel signal abnormal - s_sentinel=${S_SENTINEL:-empty}; cannot judge the counter-test sentinel"
  fi
fi

# K4: L line state
if [[ -n "$L_SAMPLE_STATE" ]]; then
  if [[ "$L_SAMPLE_STATE" == "BASELINE" || "$L_SAMPLE_STATE" == "DEGRADED" || "$L_SAMPLE_STATE" == "UNKNOWN" ]]; then
    add_anomaly "K4: L line not RATIFIED - l_sample_state=${L_SAMPLE_STATE}; ledger has not reached the approved state"
  fi
fi

# K5: pulse state file missing or stale
if [[ ! -f "$STATE_FILE" ]]; then
  add_anomaly "K5: pulse snapshot file missing - path=${STATE_FILE}; cannot cross-check sources"
elif [[ -n "${PULSE_TS:-}" ]]; then
  if command -v stat >/dev/null 2>&1; then
    FILE_AGE=$(($(date +%s) - $(stat -f %m "$STATE_FILE" 2>/dev/null || echo $(date +%s))))
    AGE_MINUTES=$((FILE_AGE / 60))
    if [[ "$AGE_MINUTES" -gt 60 ]]; then
      add_anomaly "K5: pulse snapshot stale - file age=${AGE_MINUTES} minutes, over the 60 minute threshold"
    fi
  fi
fi

# K6: quota status
if [[ "${CORTEX_QUOTA_STATUS:-}" == "exhausted" || "${CORTEX_QUOTA_EXHAUSTED:-}" == "1" ]]; then
  add_anomaly "K6: quota exhausted window - llm-heavy tasks should be refused; quota status=exhausted"
fi

# ── routing ──
SUGGESTIONS=()
add_suggestion() { SUGGESTIONS+=("$1"); }

if (( ${#ANOMALIES[@]} > 0 )); then
  add_suggestion "R1: check whether pulse write timing and ledger count definitions align on every boundary"
  add_suggestion "R2: if the u_done mismatch persists - fix pulse-write atomicity before hanging T3 (clean ACCEPT)"
  add_suggestion "R3: s_sentinel abnormal - check whether T3's status column in CLOCK.md is done (the T3 counter-test sentinel must not go green)"
fi

# Default = something is wrong: still emit a marker when there is no contradiction (this does not mean "all clear")
if (( ${#ANOMALIES[@]} == 0 )); then
  ANOMALIES+=("K0: this scan found no obvious contradiction (that does not mean there is no blind spot; a different model must cross-check)")
fi

# ── write report ──
mkdir -p "$(dirname "$REPORT_FILE")"
{
  echo "# Whitebox Observer Report"
  echo ""
  echo "**generated**: $(date '+%Y-%m-%dT%H:%M:%S%z')"
  echo "**reader model**: ${OBSERVER_MODEL} (whitebox.observer)"
  echo "**executor model**: ${EXECUTOR_MODEL} (immune.implementer)"
  echo "**state source**: ${STATE_FILE}"
  echo ""
  echo "---"
  echo ""
  echo "## suspicion list"
  echo ""
  for a in "${ANOMALIES[@]}"; do
    echo "- ${a}"
  done
  echo ""
  echo "## underlying evidence"
  echo ""
  echo "| dimension | value |"
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
  echo "| quota status | ${CORTEX_QUOTA_STATUS:-${CORTEX_QUOTA_EXHAUSTED:-unknown}} |"
  echo ""
  echo "## suggested routing"
  echo ""
  if (( ${#SUGGESTIONS[@]} > 0 )); then
    for s in "${SUGGESTIONS[@]}"; do
      echo "- ${s}"
    done
  else
    echo "- (no suspicions to route this round)"
  fi
  echo ""
  echo "---"
  echo ""
  echo "**note**: this report was generated by a heterogeneous observer (${OBSERVER_MODEL}), a different model from the executor (${EXECUTOR_MODEL})."
  echo "It only supplies veto power and does not modify any version-controlled file."
} > "$REPORT_FILE"

echo "whitebox-observer: report written to $REPORT_FILE"
echo "suspicion count: ${#ANOMALIES[@]}"
