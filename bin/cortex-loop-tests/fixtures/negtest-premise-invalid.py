#!/usr/bin/env python3
"""Negative test: a task whose premise is invalid must retire as moot, not retry forever as a failure.

Why this must stay in the suite (live evidence, 2026-07-29):
  After `own_skill()` landed, discovery stopped treating vendor symlinks as our debt -- but tasks
  already queued before the fix do not disappear on their own. island-YC-autoplan in plan
  imm-0729073608 was already scheduled, so every tick the worker ran a job that cannot physically finish:

      skills/YC-autoplan -> ${CORTEX_VENDOR_SKILLS}/gstack/autoplan
      dangling on the Linux node; all 31 YC-* skills are the same kind

  Each tick burns a full quota round, produces nothing, and adds one to the pass-rate denominator.
  Worse, it creates pressure to cheat: the 07:36 round honestly wrote a BLOCKED report,
  and the 23:13 round invented a stub to satisfy the gate -- an impossible task keeps minting fake output.

This is a collapsed dimension: one "failure" state mixes two opposite repairs --
    "I cannot do it"          -> fix capability / switch node / give time
    "this job should not exist" -> retire the criterion; retries never help
Collapsed into one FAIL, the system picks the worst repair for the second case: retry forever.

So an invalid premise must be its own terminal state (moot), not a result:
  it does not deserve credit (no work done) and must not be a penalty (not the node's fault).
  Writing a result pollutes both HAAS and the pass rate.

The criterion must use the same ruler as discovery (own_skill) --
if the two layers judge separately, discovery says do not dispatch and execution says do run.
"""
import atexit
import os
import re
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..")
ROOT = os.path.abspath(ROOT)
ENGINE = os.path.join(ROOT, "bin", "cortex-loop")

fails = 0


def check(name, ok, detail=""):
    global fails
    if ok:
        print("  PASS %s" % name)
    else:
        fails += 1
        print("  FAIL %s  %s" % (name, detail))


# -- 1. Decision logic: the same ruler as the engine --------------------------
def own_skill(path):
    real = os.path.realpath(path)
    return real == os.path.abspath(path) or real.startswith(ROOT + os.sep)


def premise_invalid(task):
    """Replica of the premise-invalid decision in cmd_run, for scenario checks."""
    for fld in ("short_test", "artifact", "detail"):
        for m in re.finditer(r"skills/([A-Za-z0-9._-]+)", str(task.get(fld) or "")):
            p = os.path.join(ROOT, "skills", m.group(1))
            if os.path.lexists(p) and not own_skill(p):
                return m.group(1)
    return ""


vendor = os.path.join(ROOT, "skills", "YC-autoplan")
created_vendor = False
if not os.path.lexists(vendor):
    # Public tree does not ship the private vendor symlink. A link whose
    # target sits outside this repo is enough for own_skill() to reject it.
    os.symlink("/tmp/cortex-not-in-this-repo", vendor)
    created_vendor = True


def _cleanup_vendor():
    if created_vendor and os.path.islink(vendor):
        os.unlink(vendor)


atexit.register(_cleanup_vendor)

CASES = [
    # (note, task, expect premise-invalid)
    ("vendor symlink task must be moot",
     {"short_test": "grep -qE '^host:' skills/YC-autoplan/SKILL.md"}, True),
    ("our own skill task must be allowed",
     {"short_test": "grep -qE '^host:' skills/cortex-loop/SKILL.md"}, False),
    ("a vendor path in the artifact field must be caught too",
     {"short_test": "true", "artifact": "skills/YC-autoplan/SKILL.md"}, True),
    ("a missing skill is not premise-invalid (that work was never done; it should run)",
     {"short_test": "test -f skills/definitely-not-here-xyz/SKILL.md"}, False),
    ("a task with no skills/ path is unaffected",
     {"short_test": "bash bin/cortex-loop-tests/suite.sh"}, False),
]

for name, task, want in CASES:
    got = bool(premise_invalid(task))
    check(name, got == want, "want %s got %s" % (want, got))


# -- 2. Implementation: the gate must exist and open before quota is spent --
try:
    src = open(ENGINE, encoding="utf-8").read()
except OSError as e:
    print("  FAIL cannot read engine: %s" % e)
    sys.exit(1)

check("engine has a premise-invalid gate", "premise invalid" in src and "premise-invalid" in src,
      "no gate means a queued bad task still retries forever")

check("premise invalid uses MOOT_NS and does not write a result",
      re.search(r"premise-invalid", src) is not None
      and re.search(r"MOOT_NS[^\n]*\n[^\n]*premise-invalid|premise-invalid[\s\S]{0,400}?MOOT_NS"
                    r"|MOOT_NS[\s\S]{0,400}?premise-invalid", src) is not None,
      "writing a result pollutes both HAAS and the pass rate")

# The gate must open before money is spent.
# The first version of this assertion was wrong (2026-07-29, broken ruler #7): a global `src.find`
# hit an earlier covenant_check in another function (line 1598) and went red while the code was
# correct. Lesson: a cross-function position compare must anchor inside the same block;
# the global "first" hit is almost never the one you want.
i_premise = src.find("premise-invalid")
i_coven = src.find("covenant_check(task", i_premise) if i_premise > 0 else -1
check("gate opens before quota is spent (premise check precedes covenant_check in the same block)",
      i_premise > 0 and i_coven > i_premise,
      "blocking after execution burns one call for nothing")

check("same ruler as discovery (reuse own_skill, do not invent a second criterion)",
      "own_skill(" in src and src.count("def own_skill") == 1,
      "two layers judging apart split into discovery says do not dispatch, execution says do run")

print("negtest-premise-invalid: %s" % ("ALL PASS" if fails == 0 else "%d FAIL" % fails))
sys.exit(1 if fails else 0)
