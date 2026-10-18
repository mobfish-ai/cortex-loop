#!/usr/bin/env python3
"""C10 — liveness buffer vs scheduler eligibility.

takeover_ready stays conservative: a node is takeover-ready only after twice
its quiet limit. owns_line is no longer that lock. CLOCK.owner is an affinity
hint. A node with a fresh heartbeat may compete for the short scheduler lease;
git CAS stops two nodes from scheduling the same pass. A process with no swarm
profile still cannot schedule.

In-memory profiles only. No files, refs, or _swarm/ writes.
"""

import os
import sys
from datetime import timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _engine import check, finish, load  # noqa: E402

m = load()
os.environ["CORTEX_NODE"] = "aa-tester"          # sorts first, so "I should take over" holds

def prof(node, can_sleep, hours_ago):
    return {"node": node, "kind": "laptop" if can_sleep == "yes" else "always-on",
            "can_sleep": can_sleep, "owns": "testline",
            "last_seen": m.fmt(m.now() - timedelta(hours=hours_ago))}


ME = prof("aa-tester", "no", 0)
ENTRY = {"line": "testline", "owner": "sleepy-laptop", "enabled": "yes"}

# (1) laptop quiet 6h: inside the 14h limit -> still alive, and must not be taken over
nodes = {"aa-tester": ME, "sleepy-laptop": prof("sleepy-laptop", "yes", 6)}
alive, why = m.node_alive(nodes["sleepy-laptop"])
check("laptop quiet 6h is alive", alive, why)
check("quiet 6h: this node can still compete for the short lease", m.owns_line(ENTRY, nodes) is True)

# (2) laptop quiet 20h: past the 14h limit but not the 28h buffer -> dead, but still not taken over
nodes["sleepy-laptop"] = prof("sleepy-laptop", "yes", 20)
alive, why = m.node_alive(nodes["sleepy-laptop"])
check("laptop quiet 20h is dead", alive is False, why)
check("quiet 20h is still inside the buffer, so no takeover", m.takeover_ready(nodes["sleepy-laptop"]) is False)
check("quiet 20h: this node can still compete for the short lease", m.owns_line(ENTRY, nodes) is True)

# (3) laptop quiet 40h: past the 2x buffer -> takeover
nodes["sleepy-laptop"] = prof("sleepy-laptop", "yes", 40)
check("quiet 40h is past the buffer", m.takeover_ready(nodes["sleepy-laptop"]) is True)
check("quiet 40h is taken over by a live node", m.owns_line(ENTRY, nodes) is True)

# (4) always-on quiet 4h: 3h limit -> dead; the 8h buffer has not passed -> still no takeover (one ruler, two meanings)
srv = {"aa-tester": ME, "srv": prof("srv", "no", 4)}
check("always-on quiet 4h is dead", m.node_alive(srv["srv"])[0] is False)
check("always-on quiet 4h is inside the buffer, so this node can still compete",
      m.takeover_ready(srv["srv"]) is False
      and m.owns_line({"line": "testline", "owner": "srv"}, srv) is True)
srv["srv"] = prof("srv", "no", 9)
check("always-on quiet 9h is past the 2x buffer -> takeover",
      m.owns_line({"line": "testline", "owner": "srv"}, srv) is True)

# (5) owner is self / empty / '-' -> always ours, regardless of the portrait
for owner in ("aa-tester", "", "-"):
    check("owner=%r belongs directly to this node" % owner,
          m.owns_line({"line": "testline", "owner": owner}, {}) is True)

# (6) an owner missing from the roster no longer locks the whole line; a fresh heartbeat may compete.
check("unknown owner: this node can still compete when it has a heartbeat",
      m.owns_line({"line": "testline", "owner": "ghost"}, srv) is True)
# (7) no portrait for this node -> refuse conservatively, so an unregistered process cannot schedule.
check("this node with no portrait cannot be scheduled",
      m.owns_line(ENTRY, {"sleepy-laptop": prof("sleepy-laptop", "yes", 40)}) is False)

print("    this case writes nothing: no _swarm/, no ref, ledger untouched")
finish()
