#!/usr/bin/env python3
"""Negative test: value laws V1/V2/V3 are checked mechanically, not self-reported.

Why this must exist: on 2026-07-29 AFR (b) I marked this gap honestly --
C1/C2/C3 already had a negative test (negtest-six-laws-gate.py),
but V1/V2/V3 only checked that the weight table exists, not that demotion actually fires.
"The weight table exists" is not "a claimed V3 is demoted to V1". Same gap the C group had.

Function under test: verify_value(task, artifact):
  Value cannot be self-reported; it is checked mechanically -- look at which directory layer
  the output landed in, and if the claim is higher than the actual layer, demote to the actual.
  It is one-way: demote only, never promote
  (a claim of V1 with output under skills/ stays V1; it is not raised).

Criteria come from VALUE_LAYERS (engine :1686):
  V3 = skills/_shared/ | bin/cortex-loop-adapters/ | brain-network/directions/_swarm/
  V2 = skills/ | bin/ | aboutme/methods/ | execution-recipes/ | work-studio/ | rules/ | brain-network/directions/
  V1 = reports/ | memory/ | /tmp/
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

# (label, claimed value, output path, expected verified layer, expected demoted?)
CASES = [
    # -- core: an inflated claim must be demoted --
    ("claim V3 but output is in reports/ -> demote to V1",
     "V3", "reports/2026-07-29/x.md", "V1", True),
    ("claim V2 but output is in memory/ -> demote to V1",
     "V2", "memory/2026-07-29.md", "V1", True),
    ("claim V3 but output is in skills/ -> demote to V2",
     "V3", "skills/foo/SKILL.md", "V2", True),
    ("claim V3 but output is in /tmp/ -> demote to V1 (scratch is not an asset)",
     "V3", "/tmp/scratch.md", "V1", True),

    # -- an honest claim must pass through unchanged --
    ("V3 output really in skills/_shared/ -> stay V3",
     "V3", "skills/_shared/normalizers.py", "V3", False),
    ("V3 output really in adapters -> stay V3 (a new executor adds swarm capability)",
     "V3", "bin/cortex-loop-adapters/newruntime.sh", "V3", False),
    ("V2 output really in bin/ -> stay V2",
     "V2", "bin/some-tool.sh", "V2", False),
    ("V1 output in reports/ -> stay V1",
     "V1", "reports/2026-07-29/y.md", "V1", False),

    # -- one-way: demote only, never promote (conservative; do not inflate for the caller) --
    ("claim V1 but output is in skills/_shared/ -> stay V1, do not raise it",
     "V1", "skills/_shared/x.py", "V1", False),

    # -- edge: an unknown path falls back to V1, never to a high value --
    ("output on a path the criteria do not cover -> fall back to V1, not V3",
     "V3", "some/unknown/path.md", "V1", True),
]

fails = 0
for label, claimed, artifact, want_level, want_demoted in CASES:
    level, note = cl.verify_value({"value": claimed}, artifact)
    demoted = bool(note)
    good = (level == want_level) and (demoted == want_demoted)
    fails += 0 if good else 1
    print("%s  %-46s level=%-3s want=%-3s  demoted=%-5s want=%s"
          % ("PASS" if good else "FAIL", label, level, want_level,
             demoted, want_demoted))
    if not good and note:
        print("       engine says: %s" % note)

print()
print("value-laws negative test: %s (%d assertions failed)"
      % ("ALL PASS" if fails == 0 else "FAILED", fails))
sys.exit(1 if fails else 0)
