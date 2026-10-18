#!/usr/bin/env python3
"""Negative test: the three six-laws gates (covenant_check) really block, and block on the right law.

Why this must exist (operator follow-up, 2026-07-29): writing a rule is not the same as mechanizing it.
The STEER law docs claim which step C1/C2/C3 each constrain, but a doc claim is not a code block.
This test builds three tasks that must be blocked, and asserts:
  (1) they are actually blocked (not allowed through)
  (2) the blocking law is the correct one (not some other gate by accident)
Point (2) matters: if gate order or criteria are wrong, a block can be right for the wrong reason,
and the next edit will tear down the wrong gate.

Does not touch the real ledger: call the engine function with a constructed dict.
"""
import importlib.machinery
import importlib.util
import os
import sys

ENGINE = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "cortex-loop")
loader = importlib.machinery.SourceFileLoader("cl", ENGINE)
cl = importlib.util.module_from_spec(importlib.util.spec_from_loader("cl", loader))
loader.exec_module(cl)

PROF = {"node": "testnode"}

# (label, task, trust, score, expect allow?, law expected to block)
CASES = [
    # -- C1 intent is the bound: output falls outside the authorized allowlist --
    ("C1 output out of bounds",
     {"bounds": "skills/", "artifact": "bin/somewhere-else.sh",
      "min_trust": "L1", "reversible": "yes"},
     "L5", 0.99, False, "C1 intent is the boundary"),

    # Legal C1 exception: artifact="-" is the "no single fixed output" placeholder, not out of bounds.
    # A live run once blocked every governance scan on C1; this must stay in the suite.
    ("C1 placeholder - is not out of bounds",
     {"bounds": "skills/", "artifact": "-",
      "min_trust": "L1", "reversible": "yes"},
     "L5", 0.99, True, ""),

    # -- C2 trust is the measure: node trust is below the task requirement --
    ("C2 trust too low",
     {"bounds": "", "artifact": "skills/x.md",
      "min_trust": "L4", "reversible": "yes"},
     "L1", 0.16, False, "C2 trust is the measure"),

    # -- C3 safety is the floor: two sub-gates for irreversible tasks --
    ("C3 irreversible + trust < L4",
     {"bounds": "", "artifact": "skills/x.md",
      "min_trust": "L1", "reversible": "no", "approved_by": "operator"},
     "L3", 0.80, False, "C3 safety is the floor"),

    ("C3 irreversible + trust ok but no human signature",
     {"bounds": "", "artifact": "skills/x.md",
      "min_trust": "L1", "reversible": "no", "approved_by": "-"},
     "L4", 0.90, False, "C3 safety is the floor"),

    ("C3 irreversible + trust ok + signature -> allow",
     {"bounds": "", "artifact": "skills/x.md",
      "min_trust": "L1", "reversible": "no", "approved_by": "operator"},
     "L4", 0.90, True, ""),

    # -- all-green control: none of the three gates should block --
    ("fully compliant task is allowed",
     {"bounds": "skills/", "artifact": "skills/x.md",
      "min_trust": "L1", "reversible": "yes"},
     "L3", 0.80, True, ""),
]

fails = 0
for label, task, trust, score, want_ok, want_law in CASES:
    ok, law, why = cl.covenant_check(task, PROF, trust, score)
    good = (ok == want_ok) and (want_ok or law == want_law)
    fails += 0 if good else 1
    print("%s  %-32s allow=%-5s want=%-5s  blocked_by=%-12s want=%s"
          % ("PASS" if good else "FAIL", label, ok, want_ok,
             law or "-", want_law or "-"))
    if not good:
        print("       reason: %s" % why)

print()
print("six-laws three-gate negative test: %s (%d assertions failed)"
      % ("ALL PASS" if fails == 0 else "FAILED", fails))
sys.exit(1 if fails else 0)
