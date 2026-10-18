#!/usr/bin/env bash
# Dimensional-collapse scanner -- the mechanical form of E013 (skills/cortex-loop/ERRORS.md).
#
# Theme (named by the operator on 2026-07-29): real-world state is naturally high-dimensional
# ("no data" != "read error", "fault" != "unreachable", "running" != "just finished"),
# and crushing those into one low-dimensional boolean or status code drops exactly the "why".
# The same day it showed up in 5 unrelated places in the code, all the same mold.
#
# This script does not auto-fix -- a human has to read the context to confirm a real collapse,
# and a hard-coded "auto-fix" would create new false positives. It only **finds candidates** and hands them to a human.
#
# Usage: bash bin/cortex-loop-tests/dimensional-collapse-scan.sh [files...]
#   With no arguments it scans bin/cortex-loop
# Exit code: 0 = no candidates  1 = candidates (not proof of a bug; it means "worth a look")

set -uo pipefail
cd "$(dirname "$0")/../.." || exit 2
TARGETS=("$@")
[[ ${#TARGETS[@]} -eq 0 ]] && TARGETS=(bin/cortex-loop)

FOUND=0

echo "dimensional-collapse candidate scan | E013 signature patterns"
echo "════════════════════════════════════════════════════"

for f in "${TARGETS[@]}"; do
  [[ -f "$f" ]] || continue

  # Signature 1: `X if code == 0 else <falsy>` -- "success but empty" and "failure" share one falsy
  # This is not necessarily a bug (they really are equivalent in many places), but a human should check.
  hits1=$(grep -nE 'if code == 0 else (""|\[\]|None|False)' "$f" || true)
  if [[ -n "$hits1" ]]; then
    echo
    echo "── $f | signature 1: \"success with empty result\" and \"failure\" share one falsy value ──"
    echo "$hits1" | sed 's/^/  /'
    FOUND=1
  fi

  # Signature 2: the same function body has >=2 `return False, ""` (or an equivalent empty falsy)
  # -- it probably crushed several different failure causes into one return value.
  hits2=$(awk '
    /^def / { fn=$0; cnt=0; buf="" }
    /return False, ""/ { cnt++; buf = buf sprintf("    L%d: %s\n", NR, $0) }
    /^def / && prevfn!="" && prevcnt>=2 { print prevfn"\n"prevbuf }
    { prevfn=fn; prevcnt=cnt; prevbuf=buf }
    END { if (cnt>=2) print fn"\n"buf }
  ' "$f" | grep -B1 "L[0-9]*:.*return False" | grep "^def " || true)
  if [[ -n "$hits2" ]]; then
    echo
    echo "── $f | signature 2: >=2 return False,\"\" inside one function (one falsy for several failure causes) ──"
    echo "$hits2" | sed 's/^/  /'
    FOUND=1
  fi

  # Signature 3: an `if X: ... GREEN/OK else: ... RED/FAIL` whose else merges several sources
  # of judgment (joined with "and", or several conditions in one test) -- a coarse screen; a hit is not proof of a bug.
  hits3=$(grep -nE '(RED|FAIL|GREEN|OK)["\x27].*\bif\b.*\band\b' "$f" || true)
  if [[ -n "$hits3" ]]; then
    echo
    echo "── $f | signature 3: a status test joins several conditions with and (check whether they should be reported apart) ──"
    echo "$hits3" | sed 's/^/  /'
    FOUND=1
  fi
done

echo
echo "════════════════════════════════════════════════════"
if [[ $FOUND -eq 1 ]]; then
  echo "candidates found -- not all are bugs; a human should check whether this spot should expand to three states."
  echo "Criterion: how many qualitatively different states does the real world have here? If >=2 were crushed into 1, this item applies."
  exit 1
else
  echo "no candidates."
  exit 0
fi
