#!/usr/bin/env bash
# cortex-loop test suite -- it really runs, and it can go red
#
#   bash bin/cortex-loop-tests/suite.sh
#
# Design constraints (the same ones as the engine):
#   1. Zero model calls: always the mock executor or a direct call into engine internals, never claude/codex quota
#   2. Idempotent: the real ledger (CLOCK.md / loop-ops/TASKS.md) is compared byte for byte before and after; one touched byte goes red
#   3. Isolated: groups A/B run in a temporary CORTEX root (symlink the engine so ROOT follows the symlink),
#            the swarm group uses only refs/swarm/test-<random suffix>, then push --delete cleans up
#   4. Exit 0 only when everything is green
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# May point at an engine copy: break a copy and run once to prove "this suite really goes red",
# and also to pass a patched engine through the gate before touching the real engine.
ENGINE="${CORTEX_LOOP_ENGINE:-$ROOT/bin/cortex-loop}"
CASES="$ROOT/bin/cortex-loop-tests"
REAL_CLOCK="$ROOT/brain-network/directions/CLOCK.md"
REAL_TASKS="$ROOT/brain-network/directions/loop-ops/TASKS.md"

PASSED=0; FAILED=0; SKIPPED=0
FAILED_IDS=""
ALL_IDS=""          # collect every case id for the "id uniqueness" self-check at the end

pass() { PASSED=$((PASSED + 1)); ALL_IDS="$ALL_IDS $1"; printf '  ✅ PASS  %-4s %s\n' "$1" "$2"; }
skip() { SKIPPED=$((SKIPPED + 1)); ALL_IDS="$ALL_IDS $1"; printf '  ⏭️  SKIP  %-4s %s\n       ↳ %s\n' "$1" "$2" "$3"; }
fail() {
  FAILED=$((FAILED + 1)); FAILED_IDS="$FAILED_IDS $1"; ALL_IDS="$ALL_IDS $1"
  printf '  ❌ FAIL  %-4s %s\n       ↳ %s\n' "$1" "$2" "$3"
}

# Private companion tools are not part of this export. Absence is a skip,
# not a failure. Callers that pass `need` run the real assertion.
need() { # id desc relpath
  if [[ ! -e "$ROOT/$3" ]]; then
    skip "$1" "$2" "not in this export: $3"
    return 1
  fi
  return 0
}

# Expect red: the command must exit non-zero, and the output must contain the keyword
expect_red() { # id description keyword command...
  local id="$1" desc="$2" want="$3"; shift 3
  local out rc
  out="$("$@" 2>&1)"; rc=$?
  if [[ $rc -eq 0 ]]; then
    fail "$id" "$desc" "expected non-zero exit, got 0; output: ${out:0:200}"
  elif ! printf '%s' "$out" | grep -q -- "$want"; then
    fail "$id" "$desc" "exit code was right but the reason was unclear (expected \"${want}\"): ${out:0:200}"
  else
    pass "$id" "$desc"
  fi
}

expect_green() { # id description keyword command...
  local id="$1" desc="$2" want="$3"; shift 3
  local out rc
  out="$("$@" 2>&1)"; rc=$?
  if [[ $rc -ne 0 ]]; then
    fail "$id" "$desc" "expected exit 0, got ${rc}; output: ${out:0:300}"
  elif ! printf '%s' "$out" | grep -q -- "$want"; then
    fail "$id" "$desc" "exit code was right but output lacks \"${want}\": ${out:0:200}"
  else
    pass "$id" "$desc"
  fi
}

# Run one standalone python case (it asserts itself; exit 0=green 1=red 2=skip)
run_case() { # id description script
  local id="$1" desc="$2" script="$3"
  local out rc
  out="$(python3 "$CASES/$script" 2>&1)"; rc=$?
  case $rc in
    0) pass "$id" "$desc"; printf '%s\n' "$out" | grep -E '^\s+(cleanup|this case|test namespace|profile)' ;;
    2) skip "$id" "$desc" "$(printf '%s' "$out" | grep SKIP | head -1)" ;;
    *) fail "$id" "$desc" "$(printf '%s' "$out" | grep -E '^(assertion failed|Traceback|\s+BAD)' | head -4 | tr '\n' ' ')" ;;
  esac
}

# -- ledger snapshot (concurrent-safe F15 hard insurance, EX17) --
# The old BEFORE/AFTER fingerprint false-failed when launchd / tick refreshed the real ledger concurrently:
# nobody in the suite edited the real ledger, but another process touched mtime, shasum disagreed, and F15 failed.
# Fix: on entry, cp -p the real ledger into $SNAP_DIR (keep the bytes), and at the end compare the live ledger
# with the snapshot byte for byte. snapshot == live means the test did not pollute it (a concurrent mtime touch is OK).
# Every suite edit lands in a copy under $SBX/..., so it is physically impossible to write the real ledger.
SNAP_DIR="$(mktemp -d /tmp/cortex-loop-suite.snap.XXXXXX)"
cp -p "$REAL_CLOCK" "$REAL_TASKS" "$SNAP_DIR/" 2>/dev/null
fingerprint() { shasum -a 256 "$SNAP_DIR/CLOCK.md" "$SNAP_DIR/TASKS.md" 2>/dev/null; }
BEFORE="$(fingerprint)"   # keep the diagnostic; F15 now compares snapshot vs current

# -- temporary CORTEX root --
SBX="$(mktemp -d /tmp/cortex-loop-suite.XXXXXX)"
SBX_ORIGIN="${SBX}.origin.git"
DBX_ORIGIN="${SBX}.defect-origin.git"
# 2026-07-31 fix: LOG used to be a hard-coded constant, so test fixtures (names like testline/gates/A4/D1)
# were all written into the production-shared /tmp/spotlight/cortex-loop.log. Real and fake
# data were mixed, and a human review mistook test noise for "real activity that just happened".
export CORTEX_LOOP_LOG="$SBX/cortex-loop.log"
cleanup() { rm -rf "$SBX" "$SBX_ORIGIN" "$DBX_ORIGIN" "$SNAP_DIR"; }
trap cleanup EXIT

mkdir -p "$SBX/bin" "$SBX/brain-network/directions/testline" "$SBX/tests" "$SBX/artifacts"
# Key trick: symlink the engine so ROOT=dirname(dirname(__file__)) lands in the sandbox,
# and the real ledger is invisible to this test (Python abspath does not resolve the symlink)
ln -s "$ENGINE" "$SBX/bin/cortex-loop"
TASKS="$SBX/brain-network/directions/testline/TASKS.md"

printf 'exit 0\n' > "$SBX/tests/pass.sh"
printf 'echo "acceptance command fails on purpose"\nexit 3\n' > "$SBX/tests/fail.sh"
printf 'real content, non-empty artifact\n' > "$SBX/artifacts/ok.md"
: > "$SBX/artifacts/empty.md"          # 0 bytes -- A2's target

cat > "$SBX/brain-network/directions/CLOCK.md" <<'EOF'
# CLOCK fixture

## column glossary (description table; header has no line, must not be treated as data)

| column | meaning |
|----|------|
| line | direction directory name |
| enabled | yes means tick scans it |

## declarations

| line | enabled | executor | advance_window_min | max_advance_per_day | owner | driver |
|------|---------|----------|--------------------|---------------------|-------|--------|
| testline | yes | mock | 240 | 2 | - | launchd:suite.fixture |
| testline2 | no | mock | 240 | 2 | - | launchd:suite.fixture2 |
EOF

cat > "$TASKS" <<'EOF'
# TASKS fixture

## column glossary (description table; header has no id, must not be treated as data)

| column | meaning | example |
|----|------|------|
| A9 | this row is a note, not a task | done |
| status | status enum | pending |

## ledger

| id | title | status | depends_on | success_criteria | failure_modes | artifact_paths | short_test | next_advance_after | fails | updated_at | evidence |
|----|-------|--------|------------|------------------|---------------|----------------|------------|--------------------|-------|------------|----------|
| A1 | artifact missing | pending | - | has an output file | empty-handed fake completion | artifacts/missing.md | bash tests/pass.sh | - | 0 | 2026-07-28 | - |
| A2 | artifact is an empty file | pending | - | has an output file | empty shell to pad the count | artifacts/empty.md | bash tests/pass.sh | - | 0 | 2026-07-28 | - |
| A3 | short_test fails red | pending | - | acceptance command passes | weaken the acceptance check | artifacts/ok.md | bash tests/fail.sh | - | 0 | 2026-07-28 | - |
| A4 | all-green sample | pending | - | acceptance command passes | fake completion | artifacts/ok.md | bash tests/pass.sh | - | 0 | 2026-07-28 | - |
| A5 | no artifact_paths | pending | - | has an output file | no output but still wants green | - | bash tests/pass.sh | - | 0 | 2026-07-28 | - |
| A6 | no short_test | pending | - | acceptance command passes | no acceptance but still wants green | artifacts/ok.md | - | - | 0 | 2026-07-28 | - |

## field rules (list form, same shape as the real ledger)

1. A cell must not contain a pipe character.
2. The data table must be the last table in the file -- see defect sentinel D-01 in group G.
EOF

# The completion gate includes clean -> commit binding -> origin reachable. The test sandbox also provides a real
# local origin, so "this is not a git repo" cannot bypass the propagation gate. file transport, zero public network.
git init --bare "$SBX_ORIGIN" >/dev/null
git -C "$SBX" init >/dev/null
git -C "$SBX" config user.name "Cortex Suite"
git -C "$SBX" config user.email "cortex-suite@example.invalid"
git -C "$SBX" remote add origin "$SBX_ORIGIN"
git -C "$SBX" add \
  brain-network/directions/CLOCK.md \
  brain-network/directions/testline/TASKS.md \
  artifacts/ok.md artifacts/empty.md tests/pass.sh tests/fail.sh
git -C "$SBX" commit -m "fixture: completion gate baseline" >/dev/null
git -C "$SBX" push -u origin HEAD:main >/dev/null

cl() { python3 "$SBX/bin/cortex-loop" "$@"; }
cell() { # $1=task id  $2=column index (1-based) -> print that cell's value
  awk -F'|' -v id=" $1 " -v n="$2" \
    '$2==id { v=$(n+1); gsub(/^[ \t]+|[ \t]+$/,"",v); print v; exit }' "$TASKS"
}

echo "cortex-loop test suite"
echo "sandbox CORTEX root: $SBX"
echo
echo "── A - completion gate (try-complete) ────────────────────────────────"

expect_red A1 "artifact missing -> refuse done" "artifact missing" \
  cl try-complete --line testline --task A1
[[ "$(cell A1 3)" == "pending" ]] \
  && pass A1b "A1 status stays pending after failure (no half-green write)" \
  || fail A1b "A1 status must not change after failure" "actual status=$(cell A1 3)"

expect_red A2 "artifact is a 0-byte empty file -> refuse done" "empty file" \
  cl try-complete --line testline --task A2
[[ "$(cell A2 3)" == "pending" ]] \
  && pass A2b "A2 status stays pending after failure" \
  || fail A2b "A2 status must not change after failure" "actual status=$(cell A2 3)"

expect_red A3 "short_test exit code non-zero -> refuse done" "exit code 3" \
  cl try-complete --line testline --task A3
[[ "$(cell A3 3)" == "pending" ]] \
  && pass A3b "A3 status stays pending after failure" \
  || fail A3b "A3 status must not change after failure" "actual status=$(cell A3 3)"

expect_green A4 "all green -> status=done" "PASS A4" \
  cl try-complete --line testline --task A4
[[ "$(cell A4 3)" == "done" ]] \
  && pass A4b "A4 status landed as done" \
  || fail A4b "A4 status should be done" "actual status=$(cell A4 3)"
[[ "$(cell A4 12)" == "artifacts/ok.md" ]] \
  && pass A4c "A4 evidence was written back as the artifact path" \
  || fail A4c "A4 evidence should be written back" "actual evidence=$(cell A4 12)"
[[ -n "$(cell A4 11)" && "$(cell A4 11)" != "2026-07-28" ]] \
  && pass A4d "A4 updated_at was refreshed" \
  || fail A4d "A4 updated_at should be refreshed" "actual updated_at=$(cell A4 11)"

expect_red A5 "no artifact_paths -> refuse done immediately" "no artifact_paths" \
  cl try-complete --line testline --task A5
expect_red A6 "no short_test -> refuse done immediately" "no short_test" \
  cl try-complete --line testline --task A6

echo
echo "── B - ledger read/write (regression guard) ──────────────────────────"

# B6: one file holds 3 tables (leading glossary + data + trailing glossary); only the table whose header has the key counts
OUT="$(cl status 2>&1)"
if printf '%s' "$OUT" | grep -q 'done=1 pending=5'; then
  pass B6 "a multi-table file counts only the table whose header contains id (6 tasks, glossary not mixed in)"
else
  fail B6 "a multi-table file counts only the key table" "status output is wrong (expected done=1 pending=5): ${OUT:0:200}"
fi
expect_red B6b "A9 in the description table is not a task" "task not found A9" \
  cl try-complete --line testline --task A9

# B7: CLOCK's key is line, not id; the wrong key silently reads 0 rows
if printf '%s' "$OUT" | grep -q 'testline .*enabled=yes .*executor=mock' \
   && printf '%s' "$OUT" | grep -q 'testline2 .*enabled=no'; then
  pass B7 "CLOCK is read with line as the key (both declarations, not 0 rows)"
else
  fail B7 "CLOCK uses line as the key" "declaration rows were not read: ${OUT:0:200}"
fi

run_case B8 "list_refs really returns the ref list and does not silently fall back to a file snapshot" "_case-refs.py"

echo
echo "── C - swarm ─────────────────────────────────────────────────────────"
run_case C9  "node self-portrait fields are complete; can_sleep in {yes,no}" "_case-swarm-profile.py"
run_case C10 "quiet inside the buffer is not taken over / past the buffer is taken over" "_case-takeover.py"
run_case C11 "lease CAS: a second push with the same parent must be rejected" "_case-lease-cas.py"

echo
echo "── D - safety guard ──────────────────────────────────────────────────"
run_case D12 "write_ref never pushes an empty or illegal sha (guards against deleting the remote ref)" "_case-write-ref-guard.py"

echo
echo "── I - fit_score glob matching (2026-07-29 section 3.1) ──────────────"
run_case I17 "fit_score glob matching: zero regression on old tasks + new wildcards really match" "_case-fit-score-glob.py"
run_case I18 "net.github.fast/slow cap: pure-function boundaries + live probe is mutually exclusive" "_case-net-github-latency.py"
run_case I19 "last_seen reads the beat ref: reproduce the old contradiction and prove the new reading fixed it" "_case-beat-ref-precise.py"

echo
echo "── E - contract gate ─────────────────────────────────────────────────"
if need E13 "all three contracts (CLOCK / INTENT / TASKS) gate PASS" bin/knowledge-contract-gate.py; then
GATE_OK=1; GATE_WHY=""
for contract in \
  brain-network/directions/CLOCK.md \
  brain-network/directions/loop-ops/INTENT.md \
  brain-network/directions/loop-ops/TASKS.md
do
  g_out="$(cd "$ROOT" && python3 bin/knowledge-contract-gate.py check-path "$contract" 2>&1)"
  if [[ $? -ne 0 ]] || ! printf '%s' "$g_out" | grep -q '"status": "PASS"'; then
    GATE_OK=0; GATE_WHY="$GATE_WHY $contract:$(printf '%s' "$g_out" | grep -o '"parse_errors".*' | head -c 120)"
  fi
done
[[ $GATE_OK -eq 1 ]] \
  && pass E13 "all three contracts (CLOCK / INTENT / TASKS) gate PASS" \
  || fail E13 "all three contract gates should PASS" "$GATE_WHY"
fi

if need E14 "TASKS missing failure_modes (negative space) -> gate must FAIL" bin/knowledge-contract-gate.py; then
run_case E14 "TASKS missing failure_modes (negative space) -> gate must FAIL" "_case-gate-negative.py"
fi

echo
echo "── G - known engine defect sentinel (not scored red/green; it shouts when fixed) ──"
# D-01: read_table returns the header of the **last table in the file**, not the header of the table that matched the key.
# Effect: if TASKS.md puts a description table after the ledger, set_cell raises ValueError,
#       and try-complete / submit / tick --auto all die with a traceback (not a red result, a crash).
# This sentinel does not change the engine; it pins the current behavior. When the engine is fixed it asks to promote this to a positive assert.
DBX="$SBX/defect-d01"
mkdir -p "$DBX/bin" "$DBX/brain-network/directions/testline" "$DBX/tests" "$DBX/artifacts"
ln -s "$ENGINE" "$DBX/bin/cortex-loop"
printf 'exit 0\n' > "$DBX/tests/pass.sh"
printf 'non-empty\n' > "$DBX/artifacts/ok.md"
printf '| line | enabled | executor | owner | driver |\n|---|---|---|---|---|\n| testline | yes | mock | - | launchd:x |\n' \
  > "$DBX/brain-network/directions/CLOCK.md"
cat > "$DBX/brain-network/directions/testline/TASKS.md" <<'EOF'
| id | title | status | depends_on | success_criteria | failure_modes | artifact_paths | short_test | next_advance_after | fails | updated_at | evidence |
|----|-------|--------|------------|------------------|---------------|----------------|------------|--------------------|-------|------------|----------|
| D1 | a description table follows the ledger | pending | - | acceptance passes | fake completion | artifacts/ok.md | bash tests/pass.sh | - | 0 | 2026-07-28 | - |

## field rules (tail description table)

| field | rule |
|------|------|
| id | task id |
EOF
git init --bare "$DBX_ORIGIN" >/dev/null
git -C "$DBX" init >/dev/null
git -C "$DBX" config user.name "Cortex Suite"
git -C "$DBX" config user.email "cortex-suite@example.invalid"
git -C "$DBX" remote add origin "$DBX_ORIGIN"
git -C "$DBX" add \
  brain-network/directions/CLOCK.md \
  brain-network/directions/testline/TASKS.md \
  artifacts/ok.md tests/pass.sh
git -C "$DBX" commit -m "fixture: defect sentinel baseline" >/dev/null
git -C "$DBX" push -u origin HEAD:main >/dev/null
D_OUT="$(python3 "$DBX/bin/cortex-loop" try-complete --line testline --task D1 2>&1)"; D_RC=$?
D_STATUS="$(awk -F'|' '$2==" D1 "{gsub(/^[ \t]+|[ \t]+$/,"",$4); print $4}' \
  "$DBX/brain-network/directions/testline/TASKS.md")"
DEFECTS=0
if [[ $D_RC -ne 0 ]] && printf '%s' "$D_OUT" | grep -q 'column not in table: status'; then
  DEFECTS=1
  printf '  DEFECT D-01 still present (expected): a description table after the data table -> set_cell raises ValueError and try-complete crashes\n'
  printf '       -> reproduce: group G fixture in bash bin/cortex-loop-tests/suite.sh; cause is read_table using the last table header\n'
elif [[ $D_RC -eq 0 && "$D_STATUS" == "done" ]]; then
  pass G16 "D-01 is fixed (a tail description table no longer breaks set_cell) -> promote this sentinel to a positive assert"
else
  fail G16 "D-01 changed but is neither fixed nor the original symptom" "rc=$D_RC status=$D_STATUS output: ${D_OUT:0:200}"
fi

echo
echo "── H - E013 negative tests (a dead gate does not report itself; an assert must prove it is alive) ──"
# Two lessons from the same day: a gate that is green on the happy path gets slapped by a negative test.
# The SCANNER-DOWN criterion was welded shut by an extra condition once, and propagation gate v1 also missed once.
# Pin them in the suite; do not leave them to live and die under /tmp.
if H_OUT="$(python3 "$CASES/fixtures/negtest-scanner-down.py" "$ENGINE" 2>&1)"; then
  pass H01 "SCANNER-DOWN criterion: 4 scenarios green (missing command / timeout / clean miss / clean hit)"
else
  fail H01 "SCANNER-DOWN criterion regression" "${H_OUT: -300}"
fi
if H_OUT="$(python3 "$CASES/fixtures/negtest-propagation-gate.py" 2>&1)"; then
  pass H02 "propagation gate v2: 4 scenarios green, and v1 is shown to miss 'history exists but the edit was not committed'"
else
  fail H02 "propagation gate criterion regression" "${H_OUT: -300}"
fi
# Six-laws three gates: check not only that something was blocked, but that the right law blocked it.
# A wrong gate order or criterion can block for the wrong reason, and the next edit then removes the wrong gate.
# Destructively verified: removing the C3 human-signature sub-gate immediately yields 1 FAIL and exit code 1.
if H_OUT="$(python3 "$CASES/fixtures/negtest-six-laws-gate.py" "$ENGINE" 2>&1)"; then
  pass H04 "six-laws gates C1/C2/C3: 7 scenarios green, each blocked by the correct law"
else
  fail H04 "six-laws gates regression (covenant_check)" "${H_OUT: -300}"
fi
# Three value laws: value cannot be self-reported. Declaring V3 while the output lands in reports/ must be demoted to V1.
# Destructively verified: removing the verify_value demotion immediately yields 5 FAIL and exit code 1.
if H_OUT="$(python3 "$CASES/fixtures/negtest-value-laws.py" "$ENGINE" 2>&1)"; then
  pass H05 "value laws V1/V2/V3: 10 scenarios green (bluff is rejected, honesty passes, rank only falls)"
else
  fail H05 "value laws regression (verify_value)" "${H_OUT: -300}"
fi
# The judge's label itself must be checked mechanically. 21/25 results once died here:
# the prompt said "an edit outside bounds is not a REJECT reason", and the judge still returned REJECT.
# Destructively verified: removing the REJECT inverse check immediately yields 1 FAIL and exit code 1.
# The dashboard's machine-readable output is the first link of the self-heal chain. When it breaks, the human view still looks fine (GLASSBOX G1).
if need H09 "dashboard v2 (four-question front page, shared metrics/EXPECTATIONS, UNKNOWN is not fake-green, S2 shadow evidence)" bin/cortex-dashboard.sh; then
if H_OUT="$(python3 "$CASES/fixtures/negtest-dashboard-json.py" 2>&1)"; then
  pass H09 "dashboard v2 (four-question front page, shared metrics/EXPECTATIONS, UNKNOWN is not fake-green, S2 shadow evidence)"
else
  fail H09 "dashboard JSON contract regression" "${H_OUT: -300}"
fi
fi
if H_OUT="$(python3 "$CASES/fixtures/negtest-judge-verdict.py" "$ENGINE" 2>&1)"; then
  pass H08 "judge-label check: 8 scenarios green (out of bounds becomes SCOPE; in bounds is not loosened)"
else
  fail H08 "judge-label check regression (_judge_verdict_from_text)" "${H_OUT: -300}"
fi
# One tick's time budget: too short and a real task never finishes (the heartbeat keeps jumping, output stays zero, harder to see than a death),
# too long and one tick wedges the clock slot forever. 300s was hidden all day behind a permanently red health check; the old code exited at 49s,
# so it never reached this cap. The moment health goes green the cap becomes the new ceiling (22:14 to 22:19, every tick status=15/TERM).
# Destructively verified: putting the real file back to 300 immediately yields 1 FAIL and exit code 1.
if H_OUT="$(python3 "$CASES/fixtures/negtest-tick-time-budget.py" 2>&1)"; then
  pass H10 "one-tick time budget, three states (too short / too long / unknown): 7 scenarios + two systemd failure kinds stay distinct"
else
  fail H10 "one-tick time budget regression (TimeoutStartSec vs clock period)" "${H_OUT: -300}"
fi
# Load rate and idle rate need numerator and denominator in the same window. The old denominator was "ticks due today" and the numerator was all-history
# deduped result counts. The swarm only started on 07-28, so that day both were about today and the defect was invisible (66% idle looked reasonable).
# The lie shows up across midnight: at 00:15 the next day the denominator resets to 1 while the numerator still carries yesterday's 31, capping load at 100% and idle at 0%.
# No task ran, yet the board shows full load. That is the worst fail-open: greenest when it should alarm, and prettier the longer nothing is produced.
# Destructively verified: putting the numerator back to all-history immediately yields 2 FAIL and exit code 1.
if need H11 "load-rate units share one window (no fail-open across midnight; numerator uses committerdate, not a date guessed from the id)" bin/cortex-dashboard.sh; then
if H_OUT="$(python3 "$CASES/fixtures/negtest-load-window.py" 2>&1)"; then
  pass H11 "load-rate units share one window (no fail-open across midnight; numerator uses committerdate, not a date guessed from the id)"
else
  fail H11 "load rate / idle rate same-window regression" "${H_OUT: -300}"
fi
fi
# A broken premise is not a failure. own_skill() fixed discovery, but tasks queued before the fix do not vanish on their own:
# island-YC-autoplan ran a dangling vendor symlink on the Linux side every tick, burned quota, produced nothing,
# and added a count to the pass-rate denominator. Worse, it created pressure to cheat: one round honestly wrote a BLOCKED report,
# and a later round invented a stub to satisfy the gate. A task that cannot be finished keeps producing fake output.
# So it must retire as moot (no points added, none deducted), not retry forever as FAIL.
# Destructively verified: removing premise-invalid from the engine immediately yields 3 FAIL and exit code 1.
if H_OUT="$(python3 "$CASES/fixtures/negtest-premise-invalid.py" 2>&1)"; then
  pass H12 "a broken premise retires as moot (5 scenarios + the gate opens before quota is burned + the same ruler as discovery)"
else
  fail H12 "broken-premise gate regression (vendor symlink task retries forever)" "${H_OUT: -300}"
fi
if H_OUT="$(python3 "$CASES/fixture-result-receipt.py" 2>&1)"; then
  pass H13 "run-v1 receipt (source/claim/origin/world all present; a write failure does not advance)"
else
  fail H13 "run-v1 receipt contract regression" "${H_OUT: -300}"
fi
if H_OUT="$(python3 "$CASES/fixture-discovery-learning.py" 2>&1)"; then
  pass H14 "S1 lineage (stable discovery cohort, passed-only learning, idempotent)"
else
  fail H14 "S1 discovery/learning lineage regression" "${H_OUT: -300}"
fi
if need H15 "S1 metric contract (an ACTIVE target must carry baseline/window/sample/approval)" bin/cortex-metrics.py; then
if H_OUT="$(python3 bin/cortex-metrics.py --validate-contract 2>&1)"; then
  pass H15 "S1 metric contract (an ACTIVE target must carry baseline/window/sample/approval)"
else
  fail H15 "S1 metric contract invalid" "${H_OUT: -300}"
fi
fi
if need H16 "metric-contract negative test (an unapproved threshold cannot activate)" bin/cortex-metrics.py; then
if H_OUT="$(python3 "$CASES/fixtures/negtest-metric-contract.py" 2>&1)"; then
  pass H16 "metric-contract negative test (an unapproved threshold cannot activate)"
else
  fail H16 "metric-contract negative-test regression" "${H_OUT: -300}"
fi
fi
if need H17 "G2 cumulative record and rolling cohort stay separate; three terminal states are not mixed" bin/cortex-metrics.py; then
if H_OUT="$(python3 "$CASES/fixtures/negtest-metric-window.py" 2>&1)"; then
  pass H17 "G2 cumulative record and rolling cohort stay separate; three terminal states are not mixed"
else
  fail H17 "G2 window-definition regression" "${H_OUT: -300}"
fi
fi
if need H18 "G1 frozen discovery cohort (missing source, missing field, or conflict are all UNKNOWN)" bin/cortex-metrics.py; then
if H_OUT="$(python3 "$CASES/fixtures/negtest-g1-discovery-cohort.py" 2>&1)"; then
  pass H18 "G1 frozen discovery cohort (missing source, missing field, or conflict are all UNKNOWN)"
else
  fail H18 "G1 discovery cohort regression" "${H_OUT: -300}"
fi
fi
if need H19 "S2 link-shadow replay is rerunnable (91 cases, promotion explicitly forbidden)" bin/cortex-s2-scm-shadow.py; then
if H_OUT="$(python3 bin/cortex-s2-scm-shadow.py 2>&1)"; then
  H_S2="$(printf '%s' "$H_OUT" | python3 -c \
    'import json,sys; d=json.load(sys.stdin); print("%s|%s|%s|%s" % (d.get("evaluated_cases"), d.get("stage_judgement"), d.get("verdict_vs_inventory_baseline"), str(d.get("promotion","")).split(";",1)[0]))' \
    2>/dev/null)"
  if [[ "$H_S2" == "91|S2_PILOT_EVIDENCE_ONLY|SUPPORTED|FORBIDDEN" ]]; then
    pass H19 "S2 link-shadow replay is rerunnable (91 cases, promotion explicitly forbidden)"
  else
    fail H19 "S2 shadow-result contract drifted" "$H_S2"
  fi
else
  fail H19 "S2 link-shadow replay failed" "${H_OUT: -300}"
fi
fi
if H_OUT="$(python3 "$CASES/fixture-map-backlink-scanner.py" 2>&1)"; then
  pass H20 "B/C reverse edges enter S1 discovery; unattended launchd defaults to MiniMax/cheap"
else
  fail H20 "B/C reverse-edge scanner/executor selection regression" "${H_OUT: -300}"
fi
if H_OUT="$(python3 "$CASES/fixtures/negtest-run-timeout-process-group.py" "$ENGINE" 2>&1)"; then
  pass H21 "executor timeout kills the whole process group (no Codex/MCP orphan holding a pipe)"
else
  fail H21 "executor timeout process-group cleanup regression" "${H_OUT: -300}"
fi
if need H22 "backlink mechanical task runs with zero model calls; the isolated candidate lands exactly on canonical master" bin/cortex-workspace.sh; then
if H_OUT="$(python3 "$CASES/fixture-deterministic-backlink.py" "$ENGINE" 2>&1)"; then
  pass H22 "backlink mechanical task runs with zero model calls; the isolated candidate lands exactly on canonical master"
else
  fail H22 "backlink deterministic execution/propagation regression" "${H_OUT: -300}"
fi
fi
if H_OUT="$(python3 "$CASES/fixtures/negtest-concurrent-execution.py" 2>&1)"; then
  pass H23 "concurrent execution contract (distinct tasks are not dropped; same task is deduped by CAS/worker; task-add pre-publish gate)"
else
  fail H23 "concurrent execution contract regression" "${H_OUT: -500}"
fi
if H_OUT="$(python3 "$CASES/fixtures/negtest-read-ref-tristate.py" 2>&1)"; then
  pass H24 "Git ref read keeps ok/empty/error as three states"
else
  fail H24 "Git ref three-state regression" "${H_OUT: -500}"
fi
if H_OUT="$(python3 "$CASES/fixtures/negtest-fail-cooldown-retry.py" 2>&1)"; then
  pass H25 "after the failure cooldown a retry is allowed; boundaries stay compatible with old receipts"
else
  fail H25 "failure cooldown retry regression" "${H_OUT: -500}"
fi
if need H26 "sparse execution cabin (shared objects, independent index, disk gate, crash recovery)" bin/cortex-workspace.sh; then
if H_OUT="$(bash "$CASES/fixtures/negtest-workspace-broker.sh" 2>&1)"; then
  pass H26 "sparse execution cabin (shared objects, independent index, disk gate, crash recovery)"
else
  fail H26 "sparse execution cabin contract regression" "${H_OUT: -500}"
fi
fi
if need H27 "candidate integration controller (out of bounds / short test refused; master lease-CAS; contention retry)" bin/cortex-integrator.sh; then
if H_OUT="$(bash "$CASES/fixtures/negtest-integration-controller.sh" 2>&1)"; then
  pass H27 "candidate integration controller (out of bounds / short test refused; master lease-CAS; contention retry)"
else
  fail H27 "candidate integration controller regression" "${H_OUT: -500}"
fi
fi
if H_OUT="$(python3 "$CASES/fixtures/negtest-master-landed.py" 2>&1)"; then
  pass H28 "completion meaning (a remote candidate is only settling; done only after landing on canonical master)"
else
  fail H28 "canonical landing completion-gate regression" "${H_OUT: -500}"
fi
if need H29 "delivery-surface gauge (dirty cabin / leftover lock / CAS retry stay three states and do not collapse)" bin/cortex-workspace.sh; then
if H_OUT="$(python3 "$CASES/fixtures/negtest-workspace-observability.py" 2>&1)"; then
  pass H29 "delivery-surface gauge (dirty cabin / leftover lock / CAS retry stay three states and do not collapse)"
else
  fail H29 "workspace delivery-surface gauge regression" "${H_OUT: -500}"
fi
fi
if need H30 "candidate atomic tools (canonical exact synthesis, scope check, immutable publish, idempotent query)" bin/cortex-candidate.sh; then
if H_OUT="$(bash "$CASES/fixtures/negtest-candidate-publish.sh" 2>&1)"; then
  pass H30 "candidate atomic tools (canonical exact synthesis, scope check, immutable publish, idempotent query)"
else
  fail H30 "candidate atomic publish tool regression" "${H_OUT: -500}"
fi
fi
if need H31 "the execution engine wires workspace to candidate to integrator to canonical done" bin/cortex-workspace.sh; then
if H_OUT="$(python3 "$CASES/fixtures/negtest-workspace-runtime.py" 2>&1)"; then
  pass H31 "the execution engine wires workspace to candidate to integrator to canonical done"
else
  fail H31 "workspace runtime end-to-end regression" "${H_OUT: -700}"
fi
fi
if need H32 "agent worktree claim / dirty-edit protection / safe reclaim contract" bin/git-worktree-doctor.py; then
if H_OUT="$(python3 "$CASES/negtest-worktree-claims.py" 2>&1)"; then
  pass H32 "agent worktree claim / dirty-edit protection / safe reclaim contract"
else
  fail H32 "worktree claim and reclaim contract regression" "${H_OUT: -500}"
fi
fi

if need H33 "dashboard watch single foreground / display-only ANSI / Ctrl-C restores the terminal" bin/cortex-dashboard.sh; then
if H_OUT="$(python3 "$CASES/fixtures/negtest-dashboard-watch-safety.py" 2>&1)"; then
  pass H33 "dashboard watch single foreground / display-only ANSI / Ctrl-C restores the terminal"
else
  fail H33 "dashboard watch Ctrl-C safety contract regression" "${H_OUT: -500}"
fi
fi

if need H34 "process tools forbid a shadow binary and forbid a bare pgrep/pkill call" bin/verify-process-tool-safety.py; then
if H_OUT="$(python3 "$ROOT/bin/verify-process-tool-safety.py" 2>&1)"; then
  pass H34 "process tools forbid a shadow binary and forbid a bare pgrep/pkill call"
else
  fail H34 "process-tool PATH safety contract regression" "${H_OUT: -500}"
fi
fi

if H_OUT="$(python3 "$CASES/fixtures/negtest-task-inspection.py" 2>&1)"; then
  pass H35 "task-show human text / JSON / settlement propagation stay a three-state atomic query"
else
  fail H35 "task-show atomic query contract regression" "${H_OUT: -700}"
fi
if need H37 "run-contract-v1 CLI/API semantic projection and drift fail closed" bin/control-plane-cockpit.py; then
if H_OUT="$(python3 "$CASES/fixtures/negtest-run-contract.py" 2>&1)"; then
  pass H37 "run-contract-v1 CLI/API semantic projection and drift fail closed"
else
  fail H37 "run-contract-v1 canonical projection regression" "${H_OUT: -700}"
fi
fi
if need H38 "cockpit run-contract binding and board-only/stale fail closed" bin/control-plane-cockpit.py; then
if H_OUT="$(python3 "$CASES/fixtures/negtest-cockpit-run-contract.py" 2>&1)"; then
  pass H38 "cockpit run-contract binding and board-only/stale fail closed"
else
  fail H38 "cockpit run-contract binding regression" "${H_OUT: -700}"
fi
fi
if need H39 "acp-native:mmx-a safe alias, ACP tool evidence, and timeout budget bridge" bin/_cortex_acp.py; then
if H_OUT="$(python3 "$CASES/fixtures/negtest-acp-native-adapter.py" 2>&1)"; then
  pass H39 "acp-native:mmx-a safe alias, ACP tool evidence, and timeout budget bridge"
else
  fail H39 "acp-native:mmx-a adapter bridge regression" "${H_OUT: -700}"
fi
fi
if need H40 "ACP tool round cap is configurable, and low/high caps plus illegal config fail closed" bin/_cortex_acp.py; then
if H_OUT="$(python3 "$CASES/fixtures/negtest-acp-tool-rounds.py" 2>&1)"; then
  pass H40 "ACP tool round cap is configurable, and low/high caps plus illegal config fail closed"
else
  fail H40 "ACP tool round cap configuration regression" "${H_OUT: -700}"
fi
fi
if need H41 "candidate companion fails closed, and artifact/candidate/terminal stay a three-state projection" bin/git-commit-preflight.py; then
if H_OUT="$(python3 "$CASES/fixtures/negtest-candidate-companion.py" 2>&1)"; then
  pass H41 "candidate companion fails closed, and artifact/candidate/terminal stay a three-state projection"
else
  fail H41 "candidate companion and delivery three-state regression" "${H_OUT: -700}"
fi
fi
if need H36 "guardrail production-event loop (atomic / idempotent / narrow meaning / real wiring)" bin/cortex-authorization-incident.sh; then
if H_OUT="$(python3 "$CASES/fixtures/negtest-guardrail-production.py" 2>&1)"; then
  pass H36 "guardrail production-event loop (atomic / idempotent / narrow meaning / real wiring)"
else
  fail H36 "guardrail production-event loop regression" "${H_OUT: -700}"
fi
fi
# SCOPE is the third state. An under-specified judge criterion is why 21/25 results were rejected that day (the mechanical gate passed,
# and everything died at the AI judge, always because "a file outside bounds still needs editing", which C1 forbids).
# The fix is a criterion plus a third state, so the third state itself needs an anti-abuse assert: SCOPE that names no path,
# or that names a path actually inside bounds, is always demoted to REJECT.
# Destructively verified: removing the "a named path must be outside bounds" check immediately yields 3 FAIL and exit code 1.
if H_OUT="$(python3 "$CASES/fixtures/negtest-judge-scope.py" "$ENGINE" 2>&1)"; then
  pass H06 "ai_judge SCOPE third state: 12 scenarios green (including 4 anti-abuse demotions and a fail-closed regression guard)"
else
  fail H06 "ai_judge criterion / third-state regression" "${H_OUT: -300}"
fi
# Plan reuse: emitting a new plan every tick inflates the denominator while the numerator stays put, so the pass rate must slide.
# A gate pointed the wrong way fails silently (too loose and a new gap can never be emitted; too tight and it degrades back to the old behavior
# with nobody noticing), so both directions must be pinned.
# Destructively verified: treating "some other node failed" as nothing to do immediately yields 1 FAIL and exit code 1.
if H_OUT="$(python3 "$CASES/fixtures/negtest-plan-churn.py" "$ENGINE" 2>&1)"; then
  pass H07 "plan-reuse criterion: 9 scenarios green (three states: skip done / yield this node's failed / the rest is workable)"
else
  fail H07 "plan-reuse criterion regression (_oldest_open_plan)" "${H_OUT: -300}"
fi
# Asset health: ROOT is a str, but the scanner used Path arithmetic, so discovery died with TypeError.
# Count drift (>2% or >3 files) and a stale reference or updated_at must be reversible, low trust, and read-only.
if H_OUT="$(python3 "$CASES/fixtures/negtest-asset-health.py" "$ENGINE" 2>&1)"; then
  pass H42 "asset health Path(ROOT) + count drift + expiry threshold (read-only, reversible, L1)"
else
  fail H42 "asset health scan regression (scan_asset_health)" "${H_OUT: -700}"
fi
# Candidate scan, not scored red or green. A hit is not proof of a bug; it means "a human should look" (the script's own design).
DC_OUT="$(bash "$CASES/dimensional-collapse-scan.sh" "$ENGINE" 2>&1)"; DC_RC=$?
if [[ $DC_RC -eq 0 ]]; then
  skip H03 "dimensional-collapse candidate scan" "no candidates"
else
  N_HITS="$(printf '%s' "$DC_OUT" | grep -c '^  [0-9]')"
  skip H03 "dimensional-collapse candidate scan" "${N_HITS:-?} candidates (neither red nor green; a human checks whether expanding them is worth it, see E013)"
fi

echo
echo "── F - idempotence proof (concurrent-safe F15) ───────────────────────"
# concurrent-safe F15: snapshot vs current (a concurrent mtime refresh of the real ledger does not false-fail)
SNAP_FP="$(shasum -a 256 "$SNAP_DIR/CLOCK.md" "$SNAP_DIR/TASKS.md" 2>/dev/null | awk '{print $1}')"
NOW_FP="$(shasum -a 256 "$REAL_CLOCK" "$REAL_TASKS" 2>/dev/null | awk '{print $1}')"
if [[ "$SNAP_FP" == "$NOW_FP" ]]; then
  pass F15 "real ledger bytes match the snapshot taken at suite entry; a concurrent mtime refresh does not false-fail"
else
  fail F15 "the test polluted the real ledger" "snapshot=$SNAP_FP now=$NOW_FP"
fi

# -- suite self-check: case ids must be unique --
# Measured 2026-07-29: two different tests both used H06, so the output showed two H06 lines. A human scanning it
# thinks the same case ran twice, when in fact **one test's red can be hidden by another test's green of the same id**.
# The suite itself has to be tested (this is the answer to "who checks the measuring stick").
DUP_IDS="$(printf '%s\n' "$ALL_IDS" | tr ' ' '\n' | grep -v '^$' | sort | uniq -d | tr '\n' ' ')"
if [[ -n "${DUP_IDS// /}" ]]; then
  fail Z99 "duplicate case ids (a red can be hidden by a green of the same name)" "duplicates: $DUP_IDS"
else
  pass Z99 "case ids are globally unique"
fi

echo
echo "════════════════════════════════════════════════════════════════════"
printf 'total: %d PASS | %d FAIL | %d SKIP | %d known defects\n' \
  "$PASSED" "$FAILED" "$SKIPPED" "${DEFECTS:-0}"
if [[ $FAILED -gt 0 ]]; then
  echo "red cases: $FAILED_IDS"
  exit 1
fi
[[ $SKIPPED -gt 0 ]] && echo "(SKIP present: usually the network is unreachable, neither green nor red; see the note above)"
echo "all green"
exit 0
