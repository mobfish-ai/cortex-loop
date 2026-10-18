#!/usr/bin/env python3
"""Negative test: one tick's time budget must be long enough to finish a real task, and not so long that it jams the clock.

Why this must stay in the suite (live evidence, 2026-07-29):
  The worker `TimeoutStartSec=300` sat behind a red light for a whole day and nobody saw it --
  the old health code stayed RED and exited in 49 seconds, so it never reached the 300s ceiling.
  Once health went green and the node actually started work, 300s became the new ceiling:

      22:14:02  Starting CORTEX cortex-loop tick...
      22:14:08  sync worker | ... | beat=ok
      22:19:08  start operation timed out. Terminating.   <- a full 300s, every tick

  The heartbeat kept beating (ExecStartPre sync takes 6 seconds), and the working `tick --auto`
  was SIGTERM'd every tick. The swarm saw a node that was alive and healthy, while real output
  stayed at zero -- harder to notice than a dead node.

That is the collapse the high-dimension law warns about: one "service failed" state mixes
  `status=1/FAILURE` (the criterion refused to run) and `status=15/TERM` (a healthy run was killed).
Those are opposite repairs -- fix the criterion, or give it time. One "service is red" cannot tell them apart.

Both sides must be blocked:
  floor -- too short = a real task never finishes (what this live run hit)
  ceiling -- >= the clock period = one stuck tick holds the slot forever, and later ticks never enter
"""
import os
import re
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..")
_PRIVATE_UNITS = os.path.join(ROOT, "work-studio", "devops", "dotfiles", "systemd")
_PUBLIC_UNITS = os.path.join(ROOT, "examples", "systemd")
UNIT_DIR = _PRIVATE_UNITS if os.path.isfile(os.path.join(_PRIVATE_UNITS, "cortex-loop.service")) else _PUBLIC_UNITS

# Measured floor for one real tick (worker, 2026-07-29):
#   `openclaw cron list` inside health alone takes 39s, plus git ls-remote + scan ~ 60-90s,
#   and only then does the real task run. Leaving a real task under 3.5 minutes means it gets killed.
FLOOR = 600          # seconds; below this a real task has no fair chance to finish

fails = 0


def judge(timeout, period):
    """Three states, not two: TOO_SHORT / TOO_LONG / OK.

    Not a bool, because "too short" and "too long" have opposite repairs --
    one False does not tell the reader which way to turn the knob.
    """
    if timeout is None or period is None:
        return "UNKNOWN"          # if it cannot be read, say so; do not pretend OK
    if timeout < FLOOR:
        return "TOO_SHORT"
    if timeout >= period:
        return "TOO_LONG"
    return "OK"


# -- 1. The criterion itself must really block (negative: a bad value must be judged bad) --
SCENARIOS = [
    # (timeout, period, expected, note)
    (300,  900, "TOO_SHORT", "the live original: a real task cannot finish, SIGTERM every tick"),
    (599,  900, "TOO_SHORT", "just under the floor"),
    (600,  900, "OK",        "the floor itself must be allowed"),
    (840,  900, "OK",        "60s of slack; one stuck tick costs at most one tick"),
    (900,  900, "TOO_LONG",  "equal to the period: a stuck tick holds the slot forever"),
    (3600, 900, "TOO_LONG",  "far past the period"),
    (None, 900, "UNKNOWN",   "unreadable stays unknown, never falls open to OK"),
]
for timeout, period, want, why in SCENARIOS:
    got = judge(timeout, period)
    if got != want:
        print("FAIL  judge(%s,%s) want %s got %s -- %s" % (timeout, period, want, got, why))
        fails += 1
if not fails:
    print("PASS  time-budget criterion: %d scenarios all green (including 3 bad values that must be blocked)" % len(SCENARIOS))

# -- 2. The criterion must separate "blocked by the criterion" from "killed while running" --
# These two systemd failures look alike, but one needs a criterion fix and one needs time.
JOURNAL_CASES = [
    ("Main process exited, code=exited, status=1/FAILURE", "GATED",
     "criterion refused to run (the old health RED class)"),
    ("Main process exited, code=killed, status=15/TERM",   "KILLED",
     "a healthy run was killed by timeout (this incident's class)"),
]


def classify(line):
    if "status=15/TERM" in line or "timed out" in line:
        return "KILLED"
    if "status=1/FAILURE" in line:
        return "GATED"
    return "UNKNOWN"


for line, want, why in JOURNAL_CASES:
    got = classify(line)
    if got != want:
        print("FAIL  classify want %s got %s -- %s" % (want, got, why))
        fails += 1
if not fails:
    print("PASS  the two systemd failures are distinguishable (gated vs killed; opposite repairs)")

# -- 3. The real files must pass (the git-tracked source of truth, not a copy) --
svc = os.path.join(UNIT_DIR, "cortex-loop.service")
tmr = os.path.join(UNIT_DIR, "cortex-loop.timer")
if not (os.path.isfile(svc) and os.path.isfile(tmr)):
    print("FAIL  systemd source of truth not found: %s" % UNIT_DIR)
    sys.exit(1)


def grab(path, key):
    m = re.search(r"^\s*%s=(\d+)" % key, open(path, encoding="utf-8").read(), re.M)
    return int(m.group(1)) if m else None


t_out = grab(svc, "TimeoutStartSec")
t_per = grab(tmr, "OnUnitActiveSec")
verdict = judge(t_out, t_per)
if verdict != "OK":
    print("FAIL  real file TimeoutStartSec=%s / OnUnitActiveSec=%s -> %s" % (t_out, t_per, verdict))
    print("      floor %ds (a real task must be able to finish); ceiling < period (a stuck tick must not hold the slot)" % FLOOR)
    fails += 1
else:
    print("PASS  real-file time budget is sound: %ds tick cap < %ds clock period, and >= %ds floor"
          % (t_out, t_per, FLOOR))

sys.exit(1 if fails else 0)
