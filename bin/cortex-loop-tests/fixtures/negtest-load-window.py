#!/usr/bin/env python3
"""Negative test: load rate and idle rate must take numerator and denominator from the same time window.

Why this must stay in the suite (measured 2026-07-29):
  The denominator in `cortex-dashboard.sh` is "how many ticks should have run from today 00:00 until now",
  but the numerator was the all-history distinct count of `refs/swarm/<shard>/result/`.

      TICKS_DUE  = (now - today 00:00) / 900        <- today
      TICKS_PROD = all result refs, distinct = 31   <- since the beginning

  The swarm started on 2026-07-28, so that day the two happened to be about "today" and the defect
  was completely hidden (66% idle, which looked reasonable). The lie shows up at the day boundary:

      next day 00:15 -> TICKS_DUE = 1, TICKS_PROD still carries yesterday's 31
                      -> LOAD = min(100, 3100) = 100%  ->  idle 0%

  A new day has not run a single task, and the dashboard shows fully loaded.
  This is the worst kind of fail-open: the moment that most needs an alarm is the greenest.
  It also hides itself -- the longer there is no output, the thicker the historical numerator, the better the number looks.

This is the same theme as the one-tick time budget, on the other face:
  that one is a broken ruler (300s kills the work); this one is a wrong dimension (numerator and denominator use different windows).
  Neither crashes the system. Both make a person reading the dashboard think everything is fine.

The fix is not to tune the number (that is cosmetics). Make the numerator follow the denominator's window.
The direction of the criterion matters too: after the fix the number should look worse or stay the same, never better --
if a change makes this metric look better out of nowhere, the first suspect is that the window was widened again.
"""
import os
import re
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..")
DASH = os.path.join(ROOT, "bin", "cortex-dashboard.sh")

fails = 0


def check(name, ok, detail=""):
    global fails
    if ok:
        print("  PASS %s" % name)
    else:
        fails += 1
        print("  FAIL %s  %s" % (name, detail))


# -- 1. Arithmetic: different windows must fail-open at the day boundary --
def load_pct(prod, due):
    due = max(due, 1)
    return min(100, prod * 100 // due)


# Scenario uses the live numbers: numerator 31 and denominator 90 on 2026-07-29
check(
    "on the same day, when the two windows nearly match, the defect is invisible (that is why it hid all day)",
    load_pct(31, 90) == 34,
    "the measured day should be 34% load / 66% idle",
)

# Day boundary: denominator resets, numerator does not -> fully loaded
check(
    "00:15 next day with an all-history numerator -> false full load (the behavior to block)",
    load_pct(31, 1) == 100,
    "the old definition shows 100% load at the start of the next day = fail-open",
)

# Day boundary: same-window numerator (the new day has produced nothing -> 0) -> correctly zero load
check(
    "00:15 next day with a same-window numerator -> correctly 0% load / 100% idle",
    load_pct(0, 1) == 0,
    "after the windows match, a new day with no output must show idle, not full load",
)


# -- 2. Implementation: the numerator in the real file must filter by the window --
try:
    src = open(DASH, encoding="utf-8").read()
except OSError as e:
    print("  FAIL cannot read cortex-dashboard.sh: %s" % e)
    sys.exit(1)

m = re.search(r"TICKS_PROD=\"\$\((.*?)\)\"", src, re.S)
check("cortex-dashboard.sh contains the TICKS_PROD calculation", m is not None,
      "if it cannot be read the definition is UNKNOWN; do not fall open to PASS")

if m:
    body = m.group(1)
    # The numerator must cite the same start variable the denominator uses, and actually filter with it
    check(
        "numerator cites the denominator window start _day_start",
        "_day_start" in body,
        "numerator does not cite _day_start = the two ends use different windows, and the day boundary goes falsely green",
    )
    check(
        "numerator filters by ref commit time (not by a date string baked into the id)",
        "committerdate" in body,
        "guessing the date from MMDD inside a plan id is bypassed by irregular ids (orchestrator / real1 fixtures)",
    )
    check(
        "zero refs produce a single 0 (not a 0\\n0 arithmetic crash)",
        "count_nonempty" in body and "grep -c" not in body,
        "`grep -c . || echo 0` prints two zeros when nothing matches",
    )

check(
    "dashboard has cleared every `grep -c ... || echo 0` double-zero pattern",
    not any(
        re.search(r"grep\s+-c\S*.*\|\|\s*echo\s+0", line)
        for line in src.splitlines()
        if not line.lstrip().startswith("#")
    ),
    "any leftover can become a multi-line integer at midnight or on an empty file",
)

# The denominator definition must stay explicit, so nobody "aligns" it by widening it to all history
m2 = re.search(r"TICKS_DUE=\$\(\(.*?\)\)", src, re.S)
check(
    "denominator is still today's expected tick count, not widened to all history",
    m2 is not None and "_day_start" in m2.group(0) and "900" in m2.group(0),
    "the right way to align the dimension is to tighten the numerator, not to loosen the denominator",
)

print("negtest-load-window: %s" % ("ALL PASS" if fails == 0 else "%d FAIL" % fails))
sys.exit(1 if fails else 0)
