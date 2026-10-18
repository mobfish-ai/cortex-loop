#!/usr/bin/env bash
# cortex-loop autonomy closed-loop acceptance gate -- answer "did it meet the bar?" with numbers, not adjectives.
#
# Why this exists: the operator asked twice "how well is this actually verified?"
# Answering in prose is grading your own work -- the same observer scoring its own output,
# so the blind spots coincide (epiplexity axiom 1). The criteria must be mechanical, rerunnable, and not spoken by me.
#
# Every criterion reads execution truth (git refs + the task ledger + process/scheduler state),
# never text that "reports itself done".
#
# Usage: bash bin/cortex-loop-tests/autonomy-acceptance.sh [--verbose]
# Exit code: 0 = all pass  1 = something missed the bar  2 = environment cannot judge (**not a pass**)

set -uo pipefail
cd "$(dirname "$0")/../.." || exit 2
VERBOSE=0; [[ "${1:-}" == "--verbose" ]] && VERBOSE=1

SWARM="${CORTEX_SWARM:-cortex}"
PASS=0; FAIL=0; UNKNOWN=0

ok()   { echo "  ✅ $1"; PASS=$((PASS+1)); }
bad()  { echo "  ❌ $1"; FAIL=$((FAIL+1)); }
huh()  { echo "  ⚠️  $1"; UNKNOWN=$((UNKNOWN+1)); }
note() { [[ $VERBOSE -eq 1 ]] && echo "       $1"; return 0; }

echo "cortex-loop autonomy closed-loop acceptance | swarm $SWARM"
echo "════════════════════════════════════════════════════════"

# -- A1 find work on its own --
# Criterion: discover really scans candidates, and they include governance/lowland kinds (not only a hard-coded fixed list)
echo
echo "A1 | find work on its own (not a human-fed task list)"
DISC=$(timeout 600 python3 bin/cortex-loop discover 2>&1)
N_CAND=$(echo "$DISC" | grep -cE '^\| [0-9]+\.[0-9]+ \|')
if [[ $N_CAND -ge 1 ]]; then
  ok "scanned $N_CAND candidates"
else
  bad "scanned no candidates (finding work on its own failed)"
fi
# Governance sources: contract debt / lowland / bad data / frontmatter -- any one counts as wired to EVO governance
if echo "$DISC" | grep -qE 'debt-|lowland-|island-|marker-|fm-'; then
  ok "candidates include EVO governance kinds (contract debt / lowland / bad data / metadata)"
else
  bad "no governance kinds in the candidates -- it only does a fixed list, which is not autonomous governance"
fi

# -- A2 dispatch on its own --
echo
echo "A2 | dispatch on its own (across nodes, not assigned by a human)"
PLANS=$(git ls-remote origin "refs/swarm/$SWARM/plan/*" 2>/dev/null | wc -l | tr -d ' ')
if [[ "${PLANS:-0}" -ge 2 ]]; then
  ok "dispatched $PLANS plans in total"
else
  huh "only ${PLANS:-0} plans (sample too small to judge)"
fi
NODES=$(git ls-remote origin "refs/swarm/$SWARM/beat/*" 2>/dev/null \
        | sed 's|.*/beat/||' | sort -u | wc -l | tr -d ' ')
if [[ "${NODES:-0}" -ge 2 ]]; then
  ok "swarm has $NODES nodes heartbeating"
else
  bad "only ${NODES:-0} nodes -- one node is not a swarm"
fi

# -- A3 finish on its own --
# The hardest item: a shared metric contract plus a traceable receipt. Do not invent a threshold inside this script.
echo
echo "A3 | finish on its own (through the mechanical gate, not a self-report)"
METRICS=$(timeout 180 python3 bin/cortex-metrics.py --json 2>/dev/null)
if [[ $? -ne 0 || -z "$METRICS" ]]; then
  huh "metric contract source is unreadable (cannot judge autonomous completion)"
else
  G2_STATE=$(python3 -c 'import json,sys; print(json.load(sys.stdin)["g2"]["sample_state"])' <<<"$METRICS" 2>/dev/null)
  G2_TARGET=$(python3 -c 'import json,sys; print(json.load(sys.stdin)["g2"]["threshold_state"])' <<<"$METRICS" 2>/dev/null)
  if [[ "$G2_STATE" == "PASS" && "$G2_TARGET" == "RATIFIED" ]]; then
    ok "G2 rolling-window target is ratified and met"
  else
    huh "G2=${G2_STATE}, target=${G2_TARGET}; no ratified threshold or not enough evidence is not a pass"
  fi
fi

# -- A4 self-heal --
echo
echo "A4 | self-heal (it gets back up after failure, without waiting for a human)"
# (1) executor suppression expires on its own  (2) failed tasks are retried (a rising fails count means a re-queue)
SUPP=$(timeout 120 python3 bin/cortex-loop model 2>&1)
if echo "$SUPP" | grep -q 'suppressed'; then
  if echo "$SUPP" | grep -qE '[0-9]+ minutes left'; then
    ok "executor suppression expires on its own (quota-window immune)"
  else
    bad "an executor is suppressed with no expiry -- it would stick forever"
  fi
else
  ok "no executor is suppressed right now"
fi
LEDGERS=$(find brain-network/directions -name TASKS.md 2>/dev/null)
RETRIED=0
for L in $LEDGERS; do
  n=$(awk -F'|' '/^\| [A-Za-z0-9_-]+ \|/ && $11+0 > 0 {c++} END{print c+0}' "$L")
  RETRIED=$((RETRIED + n))
done
if [[ $RETRIED -ge 1 ]]; then
  ok "$RETRIED tasks have been retried after failure (fails>0 and still in the ledger)"
else
  huh "no retry records -- either nothing failed, or a failure was abandoned"
fi

# -- A5 the gate was not loosened (the most important inverse criterion) --
echo
echo "A5 | completion gate was not loosened (the negative sentinel must stay red)"
# T3 is a task buried on purpose that is forever missing its artifact. If it turns green, someone loosened the gate.
SENT=$(grep -E '^\| T3 \|' brain-network/directions/loop-ops/TASKS.md 2>/dev/null \
       | awk -F'|' '{gsub(/ /,"",$4); print $4}')
case "${SENT:-missing}" in
  # ${SENT} must keep the braces: a following parenthesis would otherwise be parsed into the name
  blocked|pending|failed) ok "negative sentinel T3 = ${SENT} (the gate was not loosened)" ;;
  done)                   bad "negative sentinel T3 = done -- **the gate was loosened**, and the system is no longer trustworthy" ;;
  *)                      huh "negative sentinel T3 was not found (the criterion itself is missing)" ;;
esac

# -- A6 unattended --
echo
echo "A6 | unattended (it keeps moving when nobody is here)"
if launchctl print "gui/$(id -u)/${CORTEX_LAUNCHD_LABEL:-com.cortex.loop}" >/dev/null 2>&1; then
  ok "main clock is loaded (launchd)"
else
  bad "main clock is not loaded -- it only moves when a human opens a session"
fi
BEAT="$HOME/.openclaw/state/cortex-loop.launchd.log"
if [[ -f "$BEAT" ]]; then
  AGE=$(( ($(date +%s) - $(stat -f %m "$BEAT")) / 60 ))
  # Threshold 30 minutes = twice the 15 minute interval, leaving room for one miss
  if [[ $AGE -le 30 ]]; then ok "last heartbeat ${AGE} minutes ago"
  else                       bad "last heartbeat ${AGE} minutes ago -- the heartbeat stopped"
  fi
else
  huh "heartbeat log not found (cannot judge liveness)"
fi

# -- verdict --
echo
echo "════════════════════════════════════════════════════════"
echo "PASS $PASS | FAIL $FAIL | cannot judge $UNKNOWN"
if [[ $FAIL -gt 0 ]]; then
  echo "verdict: **missed the bar** -- each ❌ above is a concrete miss"
  exit 1
fi
if [[ $UNKNOWN -gt 0 ]]; then
  # Unable to judge is not a pass -- fail-closed, not fail-open
  echo "verdict: **missed the bar** -- $UNKNOWN items cannot be judged, and a thin sample is not a pass"
  exit 1
fi
echo "verdict: met the bar"
exit 0
