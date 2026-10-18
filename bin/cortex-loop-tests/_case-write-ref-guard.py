#!/usr/bin/env python3
"""D12 -- write_ref must never push when it is given an empty or illegal sha.

This guards a fatal footgun: `git push origin :<ref>` means delete the remote ref.
If commit-tree returns an empty string for any reason, the command becomes `push origin :refs/swarm/...`
and one failed heartbeat can wipe the whole swarm's ref. So "an empty sha does not push" must have a test.

Method: replace the module's git() with a fake recorder that returns a bad sha on cue,
and assert push was never called. No real git, and no side effects.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _engine import check, finish, load  # noqa: E402

m = load()
GOOD = "a" * 40


def make_fake(commit_out):
    calls = []

    def fake_git(cmd, timeout=120):
        calls.append(cmd)
        if cmd.startswith("hash-object"):
            return 0, GOOD
        if cmd.startswith("mktree"):
            return 0, "b" * 40
        if cmd.startswith("commit-tree"):
            return 0, commit_out
        return 0, ""

    return fake_git, calls


for label, commit_out in (("empty sha", ""),
                          ("short sha", "abc123"),
                          ("non-hex", "z" * 40),
                          ("quoted noise", "'%s'" % GOOD)):
    m.git, calls = make_fake(commit_out)
    ok, sha = m.write_ref("refs/swarm/test-guard-never-pushed", "holder=x")
    pushed = [c for c in calls if c.startswith("push")]
    check("%s -> no push" % label, not pushed, "unexpectedly ran %r" % pushed)
    check("%s -> returns (False, '')" % label, (ok, sha) == (False, ""), "actual %r" % ((ok, sha),))

# Inverse: a legal sha must actually reach push (otherwise this guard killed the feature)
m.git, calls = make_fake(GOOD)
ok, sha = m.write_ref("refs/swarm/test-guard-happy", "holder=x")
pushed = [c for c in calls if c.startswith("push")]
check("legal sha -> push is issued", len(pushed) == 1, "actual %r" % calls)
check("after a successful origin push, the same local ref is updated",
      "update-ref refs/swarm/test-guard-happy %s" % GOOD in calls,
      "actual %r" % calls)
check("the push target carries the full sha, not a bare colon",
      pushed and (":refs/" not in pushed[0].split()[2].split(":")[0] + ":")
      and pushed[0].split()[2].startswith(GOOD),
      "actual %r" % (pushed[0] if pushed else None))
check("legal sha -> returns (True, sha)", (ok, sha) == (True, GOOD), "actual %r" % ((ok, sha),))

# Same guard on rev_ref: a missing ref must be None, never an empty string (an empty string builds a delete command)
m.git = load().git                                   # restore the real git
check("rev_ref on a missing ref returns None",
      m.rev_ref("refs/swarm/test-definitely-not-exist-zzz") is None)

finish()
