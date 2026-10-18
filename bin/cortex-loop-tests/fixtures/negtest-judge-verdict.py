#!/usr/bin/env python3
"""Negative test: the verifier's label itself must be checked mechanically, not taken at face value.

Live root cause on 2026-07-29 (21/25 results died here):
  The ai_judge prompt already says the executor is hard-forbidden from editing files outside bounds,
  so "it did not edit X outside bounds" is never a REJECT reason, and it offers the SCOPE third state.
  The verifier still replied REJECT because "it only added a host: line, did not run generate-taxonomy.py,
  and did not register impeccable in SKILLS-TAXONOMY.md" -- both named paths are outside bounds.

  The previous version only reverse-checked the SCOPE branch (a named path inside bounds -> REJECT).
  The REJECT branch was accepted as-is, so saying the same thing under a different label bypassed the gate.

Lesson: do not rely on the prompt to make the LLM pick the right label; the chosen label must be checked too.
This does not loosen the gate -- unfinished work inside bounds is still REJECT. Out-of-bounds complaints
that the verifier labels REJECT stay REJECT; the system does not relabel them as SCOPE.

This test calls _judge_verdict_from_text directly (pure function, no model, no quota).
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

BOUNDS = "skills/impeccable/"

# (label, raw verifier output, expected verdict)
CASES = [
    # -- red line: do not relabel the verifier (a reverted fix; this case keeps it dead) --
    # I once auto-relabeled "REJECT whose reasons are all outside bounds" to SCOPE, because
    # the 13:34 live tick was still REJECT. That tick ran the pre-fix code (the old log string
    # hits 0 times in the current code). The premise was false, and relabeling the AI is a
    # hidden way to loosen the gate: "the verifier said no" becomes "the system says it is fine".
    # The real evidence went the other way: after the criterion became short_test, the same
    # output and the same verifier went 11:09 REJECT -> 13:41 ACCEPT.
    # This case locks it: a verifier REJECT stays REJECT. The system does not overturn it.
    ("verifier REJECT whose reasons are all outside bounds -> still REJECT (no system override)",
     "REJECT: only added a host: html-master frontmatter line in SKILL.md, "
     "but did not rerun bin/generate-taxonomy.py to rebuild the tree, "
     "and did not register impeccable in skills/SKILLS-TAXONOMY.md",
     "REJECT"),

    # -- unfinished inside bounds -> must stay REJECT (do not loosen) --
    ("generic boilerplate inside bounds -> stay REJECT",
     "REJECT: the content is all textbook template, with no concrete facts about this machine",
     "REJECT"),
    ("named path is inside bounds -> stay REJECT",
     "REJECT: the host field in skills/impeccable/SKILL.md is wrong and points at a missing host",
     "REJECT"),
    ("mixed inside and outside names -> stay REJECT (not entirely outside)",
     "REJECT: skills/impeccable/SKILL.md is incomplete, "
     "and it was not registered in skills/SKILLS-TAXONOMY.md",
     "REJECT"),
    ("REJECT that names no path -> stay REJECT",
     "REJECT: the output is too thin",
     "REJECT"),

    # -- a normal pass and an explicit SCOPE are unchanged --
    ("ACCEPT passes through unchanged",
     "ACCEPT", "ACCEPT"),
    ("explicit SCOPE with paths outside bounds -> SCOPE",
     "SCOPE: skills/SKILLS-TAXONOMY.md bin/generate-taxonomy.py | task definition too narrow",
     "SCOPE"),
    ("explicit SCOPE but the path is inside bounds -> relabel REJECT (existing defense must not regress)",
     "SCOPE: skills/impeccable/SKILL.md | claimed out of scope",
     "REJECT"),
]

fails = 0
for label, raw, want in CASES:
    got, why = cl._judge_verdict_from_text(raw, BOUNDS)
    ok = (got == want)
    fails += 0 if ok else 1
    print("%s  %-44s verdict=%-7s want=%s"
          % ("PASS" if ok else "FAIL", label, got, want))
    if not ok:
        print("       engine reason: %s" % why[:140])

print()
print("verifier-label mechanical check: %s (%d assertions failed)"
      % ("ALL PASS" if fails == 0 else "FAILED", fails))
sys.exit(1 if fails else 0)
