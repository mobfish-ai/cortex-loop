#!/usr/bin/env python3
"""B8 -- list_refs / read_ref / read_swarm must really use the ref layer, and must not silently fall back to a file snapshot.

The real regression risk: when the ref layer sees nothing, read_swarm falls back to local _swarm/*.md snapshots,
and that snapshot may be days old. The swarm would then judge liveness from a stale portrait and pretend it can see other nodes.

This case builds a local ref in an independent test namespace (no push, and it does not touch refs/swarm/beat),
asserts the ref layer was actually read, then cleans up with update-ref -d.
"""

import os
import random
import string
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _engine import check, finish, load  # noqa: E402

m = load()
sfx = "".join(random.choice(string.ascii_lowercase + string.digits) for _ in range(8))
NS = "refs/swarm/test-%s" % sfx
REF = "%s/fakenode" % NS
PAYLOAD = "\n".join([
    "node=fakenode",
    "kind=always-on",
    "can_sleep=no",
    "executors=mock",
    "telegram_reach=no",
    "last_seen=%s" % m.fmt(m.now()),
    "owns=testline",
])


def build_local_ref():
    """Plumbing only: create the object and update-ref. Entirely local, no push."""
    code, blob = m.git("hash-object -w --stdin <<'CORTEXEOF'\n%s\nCORTEXEOF" % PAYLOAD)
    if code != 0:
        return False
    blob = blob.strip().split("\n")[-1]
    code, tree = m.git("mktree <<'CORTEXEOF'\n100644 blob %s\tpayload\nCORTEXEOF" % blob)
    if code != 0:
        return False
    tree = tree.strip().split("\n")[-1]
    code, commit = m.git("commit-tree %s -m suite-test" % tree)
    if code != 0:
        return False
    commit = commit.strip().split("\n")[-1]
    return m.git("update-ref %s %s" % (REF, commit))[0] == 0


try:
    check("local test ref can be created", build_local_ref(), "plumbing failed")

    refs = m.list_refs(NS)
    check("list_refs really returns the ref list", refs == [REF], "actual %r" % refs)

    check("read_ref reads the payload back", "node=fakenode" in m.read_ref(REF),
          "read %r" % m.read_ref(REF)[:80])

    # read_swarm prefers refs; point the namespace at the test ns and assert it does not use the file snapshot
    m.BEAT_NS = NS
    m.SWARM = "/nonexistent-swarm-dir-%s" % sfx      # file-snapshot path is deliberately dead
    nodes = m.read_swarm()
    check("read_swarm gets the node from the ref layer", list(nodes) == ["fakenode"], "actual %r" % list(nodes))
    check("ref-layer node fields are complete", nodes.get("fakenode", {}).get("owns") == "testline",
          "actual %r" % nodes.get("fakenode"))

    # Inverse: empty ref layer and empty file snapshot must return empty, not invent a node
    m.BEAT_NS = "refs/swarm/test-empty-%s" % sfx
    check("empty ref and empty snapshot return an empty dict", m.read_swarm() == {})
finally:
    m.git("update-ref -d %s" % REF)
    left = m.git("for-each-ref --format='%(refname)' " + NS)[1].strip()
    print("    cleanup: %s -> %s" % (NS, "cleared" if not left else "left %s" % left))

finish()
