#!/usr/bin/env python3
"""C11 -- lease CAS: two commits with the same parent pushed to one ref; the second must be rejected.

This is the swarm's split-brain floor: during a partition both nodes think they should take over,
and the git server's fast-forward check is the only judge (same meaning as Redis SETNX, with no extra dependency).
If it fails (for example someone adds --force to push), two nodes advance the same line at once.

Isolation: only refs/swarm/test-<random suffix>, never refs/swarm/lease/*;
cleanup is push --delete on the remote plus update-ref -d locally.

Jitter: write_ref collapses "rejected by CAS" and "network down" into the same False (see report O-01),
so before judging "rejected" we prove the network is up with ls-remote. Network trouble retries or SKIPs,
and one SSL blip is never recorded as CAS working.
"""

import os
import random
import string
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _engine import check, finish, load  # noqa: E402

m = load()
sfx = "".join(random.choice(string.ascii_lowercase + string.digits) for _ in range(8))
REF = "refs/swarm/test-cas-%s" % sfx
LEASE_REF = "refs/swarm/test-lease-%s/testline" % sfx
print("    test namespace: %s (never touch refs/swarm/lease/*)" % REF)


def remote_sha(ref, tries=3):
    """Where the remote ref points. None means the network is down (distinct from "ref missing", which is "").

    Give up only after 3 misses in a row. GitHub egress goes through a Tailscale exit node (since 2026-09-21; the old proxy is retired), and a single SSL_ERROR_SYSCALL is common.
    Treating one blip as "network down" would make the CAS assert a coin flip.
    """
    for _ in range(tries):
        code, out = m.git("ls-remote origin %s" % ref, timeout=120)
        if code == 0:
            rows = [r for r in out.split("\n") if r.strip() and "\t" in r]
            return rows[0].split()[0] if rows else ""
        time.sleep(2)
    return None


def net_down():
    return remote_sha("HEAD") is None


def push_expect_ok(payload, parent, tries=3):
    """A push that should succeed: retry only network failures, never a CAS rejection."""
    for attempt in range(tries):
        ok, sha = m.write_ref(REF, payload, parent=parent)
        if ok:
            return True, sha
        if net_down():
            print("    network blip, retry %d" % (attempt + 1))
            time.sleep(3)
            continue
        return False, sha
    return False, ""


try:
    if net_down():
        print("    SKIP: origin unreachable, the CAS case cannot really run")
        raise SystemExit(2)

    ok0, sha0 = push_expect_ok("holder=setup", None)
    if not ok0:
        print("    SKIP: the test ref cannot be created (credentials or permission), the CAS case cannot really run")
        raise SystemExit(2)

    # Node A and node B both use sha0 as parent -- an exact replay of "racing at the same time"
    okA, shaA = push_expect_ok("holder=nodeA", sha0)
    check("the first node A pushes successfully", okA is True, "if A cannot push, nothing after it matters")

    okB, shaB = m.write_ref(REF, "holder=nodeB", parent=sha0)
    if not shaB:                      # no commit was created = local git blipped, not a CAS rejection
        okB, shaB = m.write_ref(REF, "holder=nodeB", parent=sha0)
    live = remote_sha(REF)
    check("the network is up when B is judged rejected (exclude a false positive)", live is not None, "ls-remote failed -> network down")
    check("node B with the same parent is rejected", okB is False, "B also succeeded = CAS is dead, and both nodes would move one line")
    check("the remote stays on winner A", live == shaA, "remote %r expected %r" % (live, shaA))
    check("A and B are two different commits (each built its own)", shaA != shaB)

    # Retrying with the latest parent must succeed -- otherwise this is a deadlock, not a lock
    okB2, shaB2 = push_expect_ok("holder=nodeB", shaA)
    check("B succeeds when it retries with the latest parent", okB2 is True, "retry also failed = the lock is a deadlock")
    check("after the retry the remote is B", remote_sha(REF) == shaB2)

    # acquire_lease layer: while the lease is valid, another node cannot take it
    m.LEASE_NS = "refs/swarm/test-lease-%s" % sfx

    def lease_expect_ok(node, tries=3):
        """A case that should acquire the lease. A miss can be a dropped fetch (local ref stale ->
        parent stale -> rejected); one retry is enough. Retry only calls that are expected to succeed."""
        os.environ["CORTEX_NODE"] = node
        got, why = False, ""
        for _ in range(tries):
            got, why = m.acquire_lease("testline", ttl_min=60)
            if got:
                break
            time.sleep(3)
        return got, why

    got1, why1 = lease_expect_ok("node-first")
    check("the first node gets the lease", got1 is True, why1)

    os.environ["CORTEX_NODE"] = "node-second"
    got2, why2 = m.acquire_lease("testline", ttl_min=60)
    check("the network is up when the second node is judged unable to take the lease", remote_sha(LEASE_REF) is not None, "network down")
    check("the second node cannot take an unexpired lease", got2 is False, why2)
    check("the refusal names the holder", "node-first" in why2, "actual %r" % why2)

    # An expired lease must be takeable, or one dead node locks the line forever
    expired = "holder=node-first\nexpires=%s\nsince=%s" % (
        m.fmt(m.now() - m.timedelta(minutes=5)), m.fmt(m.now() - m.timedelta(minutes=65)))
    okE, _ = m.write_ref(LEASE_REF, expired, parent=remote_sha(LEASE_REF) or None)
    check("an already-expired lease can be written", okE is True, "could not write the test ref")
    if okE:
        got3, why3 = lease_expect_ok("node-second")
        check("after expiry another node can take the lease", got3 is True, why3)
finally:
    for ref in (REF, LEASE_REF):
        m.git("push origin --delete %s 2>&1" % ref, timeout=180)
        m.git("update-ref -d %s 2>&1" % ref)
    left = m.git("ls-remote origin 'refs/swarm/test-*'", timeout=120)[1].strip()
    local = m.git("for-each-ref --format='%(refname)' refs/swarm/")[1]
    local_test = [r for r in local.split("\n") if "test-" in r]
    print("    cleanup: remote %s | local %s"
          % ("cleared" if sfx not in left else "WARNING left %s" % left,
             "cleared" if not local_test else "WARNING left %s" % local_test))

finish()
