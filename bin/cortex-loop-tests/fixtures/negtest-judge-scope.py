#!/usr/bin/env python3
"""Negative test: the SCOPE third state of ai_judge is not a free pass.

Why this must exist (live root cause, 2026-07-29):
  21 of 25 results were `gate=rejected`. The mechanical gate passed every one of them;
  they all died at the AI verifier. The caller filled `success_criteria` with `task["title"]`
  (a vision sentence) and the prompt never passed `short_test` / `bounds` -- the verifier
  had no objective criterion, invented a maximal reading, and kept demanding edits to files
  outside bounds such as `skills/SKILLS-TAXONOMY.md`. C1 intent is the bound forbids the
  executor from touching paths outside bounds: obeying is a breach, refusing is REJECT.
  Both roads are dead.

The fix is to give a criterion, not to loosen the gate. That is why SCOPE exists
(the work inside bounds is done, but the task definition itself is too narrow).
The third state can be abused: one SCOPE reply would let anything through.
So the code adds a hard check:
  - SCOPE must name a concrete path outside bounds; name none -> downgrade to REJECT
  - every named path must actually be outside bounds; one inside -> downgrade to REJECT

This test stubs run_adapter with verifier replies and checks parse and downgrade.
Destructive check: delete the `if inside:` block and the "named path is actually inside bounds" case FAILs.

Does not touch the real ledger, the network, or model quota: run_adapter is a pure stub.
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

TASK = {
    "id": "island-x", "title": "attach island skill x into the host tree (network link)",
    "success_criteria": "mechanical check: grep -qE '^host:' skills/x/SKILL.md",
    "short_test": "grep -qE '^host:' skills/x/SKILL.md",
    "bounds": "skills/x/",
    "failure_modes": "generic boilerplate",
    "artifact_paths": "skills/x/SKILL.md",
}

# (label, verifier reply, expected verdict, keyword that must appear in the reason)
CASES = [
    ("clean ACCEPT", "ACCEPT", "ACCEPT", ""),

    ("unfinished inside bounds -> REJECT",
     "REJECT: title only, no real content", "REJECT", "title"),

    # This is the rejection that happened six times live -- after the fix it must be SCOPE, not REJECT
    ("only paths outside bounds remain -> SCOPE (no longer a false failed)",
     "SCOPE: skills/SKILLS-TAXONOMY.md skills/html-master/SKILL.md | still needs the registry",
     "SCOPE", "SKILLS-TAXONOMY"),

    # --- the next three are the hard insurance that the third state cannot be abused ---
    ("SCOPE but no path named -> downgrade to REJECT",
     "SCOPE: I think it is still short", "REJECT", "named no path"),

    ("SCOPE but the named path is actually inside bounds -> downgrade to REJECT",
     "SCOPE: skills/x/ERRORS.md | still missing the error log", "REJECT", "inside bounds"),

    ("SCOPE mixes in one in-bounds path -> the whole reply downgrades to REJECT",
     "SCOPE: skills/SKILLS-TAXONOMY.md skills/x/ERRORS.md | both missing",
     "REJECT", "inside bounds"),

    # Fail closed: the verifier itself did not run != the content is fine (existing behavior)
    ("adapter died -> REJECT (fail closed, not fail open)",
     "[ADAPTER_FAILED rc=1]\nAPI Error: 502", "REJECT", "verifier did not run"),

    ("empty output -> REJECT", "", "REJECT", "verifier did not run"),

    # With empty bounds there is no "outside", so SCOPE cannot be checked -> count as fail, do not allow
    ("empty bounds -> SCOPE cannot be checked, downgrade to REJECT",
     "SCOPE: skills/anything.md | something missing", "REJECT", "inside bounds"),
]

fails = []
for label, reply, want_verdict, want_kw in CASES:
    cl.run_adapter = (lambda r: (lambda *a, **k: r))(reply)
    task = dict(TASK)
    if label.startswith("empty bounds"):
        task["bounds"] = ""
    got_verdict, got_reason = cl.ai_judge("testline", "stub", task)
    if got_verdict != want_verdict:
        fails.append("%s -- want %s, got %s (reason: %s)"
                     % (label, want_verdict, got_verdict, got_reason[:120]))
        print("  BAD  %s -- want %s got %s" % (label, want_verdict, got_verdict))
        continue
    if want_kw and want_kw not in got_reason:
        fails.append("%s -- verdict ok but reason lacks %r: %s" % (label, want_kw, got_reason[:120]))
        print("  BAD  %s -- reason missing keyword %r" % (label, want_kw))
        continue
    print("  ok   %s -> %s" % (label, got_verdict))

# Boundaries of pure function _paths_outside_bounds (the foundation of the SCOPE check)
for label, paths, bounds, want in [
    ("any one of several bounds counts as inside", ["skills/x/a.md"], "bin/ skills/x/", []),
    ("actually outside", ["skills/SKILLS-TAXONOMY.md"], "skills/x/", ["skills/SKILLS-TAXONOMY.md"]),
    ("empty bounds = no boundary = everything is inside", ["anything"], "", []),
]:
    got = cl._paths_outside_bounds(paths, bounds)
    if got != want:
        fails.append("_paths_outside_bounds %s -- want %s got %s" % (label, want, got))
        print("  BAD  _paths_outside_bounds %s" % label)
    else:
        print("  ok   _paths_outside_bounds %s" % label)

if fails:
    print("\n%d assertions failed: %s" % (len(fails), " / ".join(fails)))
    sys.exit(1)
print("\nSCOPE third state: %d scenarios all green (including 4 anti-abuse downgrades)" % (len(CASES) + 3))
