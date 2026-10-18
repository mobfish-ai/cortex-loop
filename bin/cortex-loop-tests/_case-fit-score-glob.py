#!/usr/bin/env python3
"""I17 -- after fit_score switches to glob matching: existing tasks keep the same verdicts, and wildcards really work.

Background: `bin/cortex-loop` fit_score used to subtract requires literally (`need - have`),
so a new task could not write a pattern (such as "model.anthropic.*") and had to fall back to a coarse
token like "exec.claude". After fnmatch, an exact string (how every old task is written) behaves exactly like `==`,
and only new tasks can use wildcards. This case must prove both zero regression and that wildcards really match.

Read-only: writes no files, does not touch the real ledger, and does not use the network.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _engine import check, finish, load  # noqa: E402

m = load()

HAVE = {"exec.claude", "exec.codex", "model.anthropic.claude-opus-5",
        "model.openai.openai-codex", "host.laptop", "net.github",
        "net.github.fast"}


def score(requires_str, have=HAVE, load_=0, max_load=3):
    task = {"requires": requires_str}
    return m.fit_score(task, {"caps": " ".join(have)}, load_, max_load)


# -- zero regression: exact strings on existing tasks must verdict the same before and after --
ok, why = score("-")
check("old form requires=- -> no requirements, claimable", ok is not None, why)

ok, why = score("exec.claude")
check("old form requires=exec.claude (present) -> claimable", ok is not None, why)

ok, why = score("exec.human")
check("old form requires=exec.human (absent) -> rejected for a missing capability", ok is None, why)
check("the refusal names the missing capability as-is (no glob pollution)",
      why == "missing capability exec.human", "actual: %r" % why)

# -- new capability: wildcards really match (they are not a no-op) --
ok, why = score("model.anthropic.*")
check("new form model.anthropic.* matches model.anthropic.claude-opus-5",
      ok is not None, why)

ok, why = score("model.google.*")
check("a wildcard must not pass everything -- a missing provider is still refused", ok is None, why)

ok, why = score("net.github.fast")
check("exact string net.github.fast (present) -> claimable", ok is not None, why)

ok, why = score("net.github.slow")
check("exact string net.github.slow (absent; this node is fast) -> refused", ok is None, why)

# -- mixed: one requires list with both an exact string and a wildcard must satisfy both --
ok, why = score("exec.claude model.anthropic.*")
check("mixed requires (exact + wildcard) all satisfied -> claimable", ok is not None, why)

ok, why = score("exec.claude model.openai.gpt-*")
check("mixed requires whose wildcard half misses -> refused as a whole", ok is None, why)

finish()
