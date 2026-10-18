#!/usr/bin/env python3
"""Negative test: _oldest_open_plan really recognizes an old plan that still has work.

Why this must exist (live root cause, 2026-07-29):
  7 of 24 immune plans were never claimed. The autonomous path in cmd_tick unconditionally
  writes a new plan id every tick and only runs the one it just issued; it never looks back
  at an unfinished plan. The same candidates are re-dispatched as new plans, and the pass-rate
  denominator is the result-ref count = (plan, task) pairs -- each reissue of the same job
  takes another slot in the denominator: the numerator stays put and the denominator explodes.

A gate that points the wrong way fails silently:
  - too loose (always returns some plan) -> new gaps can never be issued; the swarm looks busy and idles
  - too tight (always returns None) -> it regresses to the old behavior, the pile stays, and nobody notices
So assertions must pin both directions.

The criterion is three states, not two (high-dimension law):
  already done / this node failed last time (yield to someone else) / otherwise workable
Dropping any state is wrong: treating "some other node failed" as "no work left"
makes one failure a death sentence and throws away swarm fault tolerance (the same bug cmd_claim already fixed).

Does not touch the real ledger or the network: stub list_refs / plan_tasks / read_ref.
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

ME = "testnode"


def stub(plans, results):
    """plans: {pid: [task_id|task_dict,...]} results: {'pid/task': receipt}"""
    cl.node_id = lambda: ME
    cl.list_refs = lambda ns: ["%s/%s" % (cl.PLAN_NS, p) for p in plans]
    cl.plan_tasks = lambda pid: [
        {"id": t} if isinstance(t, str) else t for t in plans.get(pid, [])
    ]
    cl.read_ref = lambda ref: results.get(ref.split("/result/", 1)[-1], "")


# A missing ref is a normal empty state. Do not identify it by an English error string
# (the local Git locale may emit some other language).
_real_rev_ref, _real_git = cl.rev_ref, cl.git
_git_calls = []
cl.rev_ref = lambda ref: None
cl.git = lambda *args, **kwargs: (_git_calls.append(args) or (1, "must-not-run"))
_missing_ref_value = cl.read_ref("refs/swarm/cortex/result/missing")
cl.rev_ref, cl.git = _real_rev_ref, _real_git
if _missing_ref_value != "" or _git_calls:
    print("  BAD  a missing ref must return empty right after rev-parse and must not call cat-file")
    sys.exit(1)
print("  ok   missing ref does not depend on Git locale error text")


# (label, plans, results, expected return)
CASES = [
    ("all done -> no old work, go issue a new plan",
     {"imm-1": ["a", "b"]},
     {"imm-1/a": "status=done\nnode=other", "imm-1/b": "status=done\nnode=%s" % ME},
     None),

    ("an old plan with zero results -> that is the one (the 7 never-claimed live plans)",
     {"imm-1": ["a"]}, {}, "imm-1"),

    ("this node failed last time -> yield to another node; not this node's work",
     {"imm-1": ["a"]}, {"imm-1/a": "status=failed\nnode=%s" % ME}, None),

    ("some other node failed -> this node should take it (one failure is not a death sentence)",
     {"imm-1": ["a"]}, {"imm-1/a": "status=failed\nnode=other"}, "imm-1"),

    ("does scope-gap count as unfinishable? no: only status=done skips; gate is not part of the decision",
     {"imm-1": ["a"]}, {"imm-1/a": "status=done\ngate=scope-gap\nnode=other"}, None),

    ("pick the earliest one, not an arbitrary one (one item per tick, no avalanche)",
     {"imm-0729130809": ["a"], "imm-0729053637": ["a"], "imm-0729100933": ["a"]},
     {}, "imm-0729053637"),

    ("a frozen-discovery S1 cohort beats an older legacy half-done plan",
     {"imm-legacy": [{"id": "a", "discovery_id": "-"}],
      "imm-s1": [{"id": "b", "discovery_id": "d-b"}]},
     {}, "imm-s1"),

    ("a deterministic S1 beats an older model-type frozen discovery",
     {"imm-old-model": [{"id": "a", "discovery_id": "d-a", "source": "frontmatter-gap"}],
      "imm-s1": [{"id": "b", "discovery_id": "d-b", "source": "map-backlink-gap"}]},
     {}, "imm-s1"),

    ("an old plan that is partly done -> return it while one row is still workable",
     {"imm-1": ["a", "b"]},
     {"imm-1/a": "status=done\nnode=other"}, "imm-1"),

    ("an empty plan (tasks did not parse) -> skip it; it is not work",
     {"imm-1": []}, {}, None),

    ("a plan without the imm- prefix (a human-issued real1) is outside autonomous pickup",
     {"real1": ["R1"]}, {}, None),
]

fails = []
for label, plans, results, want in CASES:
    stub(plans, results)
    got = cl._oldest_open_plan()
    if got != want:
        fails.append("%s -- want %r got %r" % (label, want, got))
        print("  BAD  %s -- want %r got %r" % (label, want, got))
    else:
        print("  ok   %s → %r" % (label, got))

if fails:
    print("\n%d assertions failed: %s" % (len(fails), " / ".join(fails)))
    sys.exit(1)


# After an automatic run, gather(settle=True) is unconditional: even if this tick
# finished only some tasks, publish learning for the ones that passed; the same path
# settles automatically when the last batch is complete.
_calls = []
cl.cmd_run = lambda ns: (_calls.append(("run", ns.plan)) or 0)
cl.cmd_gather = lambda ns: (_calls.append(("gather", ns.plan, ns.settle)) or 1)
_run_args = type("RunArgs", (), {"plan": "imm-s1"})()
cl._run_and_gather("imm-s1", _run_args)
if _calls != [("run", "imm-s1"), ("gather", "imm-s1", True)]:
    print("  BAD  automatic execution did not form a run->gather(settle=True) loop: %r" % (_calls,))
    sys.exit(1)
print("  ok   automatic execution forces run->gather(settle=True)")
if _run_args.trigger_kind != "clock-auto":
    print("  BAD  automatic execution receipt did not set trigger_kind=clock-auto")
    sys.exit(1)
print("  ok   automatic execution receipt marks clock-auto; a manual run does not impersonate S1")

print("\nplan reuse and auto-settle criterion: %d scenarios all green" % len(CASES))
