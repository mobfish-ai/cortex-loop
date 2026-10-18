#!/usr/bin/env python3
"""I19 -- last_seen now reads the beat ref's real time (2026-07-29 section 3.3).

Background (a contradiction measured the same day): node_profile() deliberately flattens last_seen to
hour precision ("a tick inside the hour must not create a git diff"), but every beat_publish() sync
really pushes a new commit. The commit's real time (to the second) and the last_seen text in the payload
(hour precision, which can be almost an hour earlier than the real time) are two different
"when" values. Reading them as one field in one blob produces
"the worker just pushed a heartbeat, but the dashboard shows quiet 0.9h".

This case first reproduces that the old reading really computes a fake long quiet, then proves the new
reading (beat_ref_precise_seen reads the commit's real time) fixed it. Adding a function is not enough;
the function must actually be wired into node_alive() / takeover_ready().

Local refs only, never push: refs/swarm/<swarm>/beat/test-beatprecise-<rand>,
then git update-ref -d. No leftover, and the remote is not touched.
"""

import os
import random
import re
import sys
from datetime import timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _engine import check, finish, load  # noqa: E402

m = load()

NODE = "test-beatprecise-%06d" % random.randint(0, 999999)
REF = "%s/%s" % (m.BEAT_NS, NODE)


def make_local_commit(payload):
    """Create a commit in the real local git (no push) and return the sha."""
    code, blob = m.git("hash-object -w --stdin <<'CORTEXEOF'\n%s\nCORTEXEOF" % payload)
    assert code == 0, "hash-object failed: %s" % blob
    blob = blob.strip().split("\n")[-1]
    code, tree = m.git("mktree <<'CORTEXEOF'\n100644 blob %s\tpayload\nCORTEXEOF" % blob)
    assert code == 0, "mktree failed: %s" % tree
    tree = tree.strip().split("\n")[-1]
    code, commit = m.git("commit-tree %s -m swarm" % tree)
    assert code == 0, "commit-tree failed: %s" % commit
    return commit.strip().split("\n")[-1]


try:
    # Build the contradiction itself: the commit's real time is now, but the payload's
    # last_seen is flattened to the hour and about 50 minutes early (same flattening as node_profile()'s
    # "%Y-%m-%dT%H:00").
    now = m.now()
    stale_last_seen = (now - timedelta(minutes=50)).strftime("%Y-%m-%dT%H:00")
    payload = "node=%s\nlast_seen=%s\ncan_sleep=no\nowns=-\n" % (NODE, stale_last_seen)
    commit = make_local_commit(payload)
    code, _ = m.git("update-ref %s %s" % (REF, commit))
    assert code == 0, "update-ref failed"

    prof = {"node": NODE, "can_sleep": "no", "last_seen": stale_last_seen}

    # -- reproduce the old contradiction: reading only the profile field shows about 0.8h quiet (not seconds) --
    old_quiet = (m.now() - m.parse_ts(prof["last_seen"])).total_seconds() / 3600
    check("old reading (profile last_seen only) really yields about 0.8h quiet -- the contradiction to fix",
          old_quiet > 0.5, "actual %.2fh" % old_quiet)

    # -- new function: beat ref precise time must be within seconds of the real push --
    precise = m.beat_ref_precise_seen(prof)
    check("beat_ref_precise_seen reads a precise time (not None)", precise is not None)
    if precise is not None:
        drift = abs((m.now() - precise).total_seconds())
        check("beat ref precise time is within <10s of the real push (not the flattened hour)",
              drift < 10, "actual drift %.1fs" % drift)

    # -- wired in: node_alive() must use the precise time and must not show the old ~0.8h --
    alive, why = m.node_alive(prof)
    check("after wiring into node_alive() it is alive (it was alive before too, but the reason must change)", alive, why)
    check("node_alive() reason cites beat ref exact time, not profile hour precision",
          "beat ref exact time" in why, "actual: %r" % why)
    quiet_match = re.search(r"quiet ([\d.]+)h", why)
    check("node_alive() quiet is second-precise (<0.05h), no longer the old ~0.8h",
          quiet_match is not None and float(quiet_match.group(1)) < 0.05,
          "actual reason: %r" % why)

    # -- takeover_ready() uses the same ruler: one precise source, not a second reading --
    ready = m.takeover_ready(prof)
    check("takeover_ready() uses the precise time -- heartbeat just pushed, far from the takeover buffer",
          ready is False, "ready=%r" % ready)

    # -- a node with no beat ref must fall back to the profile field, without error and without being judged dead --
    ghost_prof = {"node": "test-beatprecise-no-such-node-ever", "can_sleep": "no",
                  "last_seen": stale_last_seen}
    ghost_precise = m.beat_ref_precise_seen(ghost_prof)
    check("a node that never sent a heartbeat: beat_ref_precise_seen returns None (no exception, no invented time)",
          ghost_precise is None, "actual %r" % ghost_precise)
    ghost_alive, ghost_why = m.node_alive(ghost_prof)
    check("with no beat ref, fall back to profile hour precision (old behavior unchanged, zero regression)",
          "profile hour precision" in ghost_why, "actual: %r" % ghost_why)

finally:
    m.git("update-ref -d %s" % REF)

finish()
