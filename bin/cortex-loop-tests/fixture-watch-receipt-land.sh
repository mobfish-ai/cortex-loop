#!/usr/bin/env bash
# Prove watch-receipt-land never dead-loops on empty size / missing files,
# and that a landed receipt trips DONE. Regression for observer-seat E023.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TOOL="$ROOT/bin/watch-receipt-land.sh"
TMP="$(mktemp -d "${TMPDIR:-/tmp}/watch-receipt-land.XXXXXX")"
cleanup() { rm -rf "$TMP"; }
trap cleanup EXIT

[[ -x "$TOOL" ]] || chmod +x "$TOOL"

# 1) empty / missing path must not raise an integer-expression error; --once -> FAILED
out1="$(bash "$TOOL" --once --no-require-tracked --min-bytes 10 \
  MISS="$TMP/does-not-exist.md" 2>&1)" || rc1=$?
rc1="${rc1:-0}"
[[ "$rc1" == "1" ]] || { echo "FAIL missing-path exit=$rc1 out=$out1"; exit 1; }
[[ "$out1" == FAILED* ]] || { echo "FAIL missing-path stdout=$out1"; exit 1; }
[[ "$out1" != *"$(python3 -c 'import sys; sys.stdout.write("\u9700\u8981\u6574\u6570")')"* ]] || { echo "FAIL integer crash: $out1"; exit 1; }

# 2) empty file size coerces to 0, still FAILED, no integer crash
: >"$TMP/empty.md"
out2="$(bash "$TOOL" --once --no-require-tracked --min-bytes 10 \
  EMPTY="$TMP/empty.md" 2>&1)" || rc2=$?
rc2="${rc2:-0}"
[[ "$rc2" == "1" ]] || { echo "FAIL empty-file exit=$rc2 out=$out2"; exit 1; }
[[ "$out2" == FAILED* ]] || { echo "FAIL empty-file stdout=$out2"; exit 1; }
[[ "$out2" != *"$(python3 -c 'import sys; sys.stdout.write("\u9700\u8981\u6574\u6570")')"* ]] || { echo "FAIL empty integer crash: $out2"; exit 1; }

# 3) ready receipt → DONE (no git track required)
cat >"$TMP/ready.md" <<'EOF'
---
verdict: NEEDS_WORK
---
# ready receipt body padding to clear min-bytes gate
xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
EOF
out3="$(bash "$TOOL" --once --no-require-tracked --min-bytes 80 \
  READY="$TMP/ready.md" 2>&1)" || rc3=$?
rc3="${rc3:-0}"
[[ "$rc3" == "0" ]] || { echo "FAIL ready exit=$rc3 out=$out3"; exit 1; }
[[ "$out3" == *"PARTIAL READY_DONE"* ]] || { echo "FAIL ready partial: $out3"; exit 1; }
[[ "$out3" == *"DONE all_receipts"* ]] || { echo "FAIL ready done: $out3"; exit 1; }

# 4) PENDING verdict is not ready even when bytes suffice
cat >"$TMP/pending.md" <<'EOF'
---
verdict: PENDING
---
# pending placeholder padding xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
EOF
out4="$(bash "$TOOL" --once --no-require-tracked --min-bytes 80 \
  PEND="$TMP/pending.md" 2>&1)" || rc4=$?
rc4="${rc4:-0}"
[[ "$rc4" == "1" ]] || { echo "FAIL pending exit=$rc4 out=$out4"; exit 1; }
[[ "$out4" == FAILED* ]] || { echo "FAIL pending stdout=$out4"; exit 1; }

# 5) as_int regression: garbage size path via missing file + multi target
out5="$(bash "$TOOL" --once --no-require-tracked --min-bytes 10 \
  A="$TMP/does-not-exist.md" B="$TMP/ready.md" 2>&1)" || rc5=$?
rc5="${rc5:-0}"
[[ "$rc5" == "1" ]] || { echo "FAIL multi exit=$rc5 out=$out5"; exit 1; }
[[ "$out5" == *"PARTIAL B_DONE"* ]] || { echo "FAIL multi partial: $out5"; exit 1; }
# multi-target prints PARTIAL for ready legs first, then FAILED for the incomplete set
[[ "$out5" == *"FAILED timeout"* ]] || { echo "FAIL multi must fail incomplete: $out5"; exit 1; }
[[ "$out5" != *"DONE all_receipts"* ]] || { echo "FAIL multi must not DONE: $out5"; exit 1; }
[[ "$out5" != *"$(python3 -c 'import sys; sys.stdout.write("\u9700\u8981\u6574\u6570")')"* ]] || { echo "FAIL multi integer crash: $out5"; exit 1; }

# 6) --quiet --once incomplete: exit 1, no FAILED line (poll-safe for monitors)
out6="$(bash "$TOOL" --once --quiet --no-require-tracked --min-bytes 10 \
  MISS="$TMP/does-not-exist.md" 2>&1)" || rc6=$?
rc6="${rc6:-0}"
[[ "$rc6" == "1" ]] || { echo "FAIL quiet exit=$rc6 out=$out6"; exit 1; }
[[ -z "$out6" ]] || { echo "FAIL quiet must be silent on incomplete: [$out6]"; exit 1; }

printf 'watch-receipt-land fixture: PASS (empty-size-safe, pending-gate, multi-partial, quiet-poll)\n'

