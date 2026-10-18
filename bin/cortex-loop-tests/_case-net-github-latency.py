#!/usr/bin/env python3
"""I18 -- net.github.fast/slow cap (2026-07-29 section 3.2).

Two layers:
  1. Classification boundaries of the pure function _github_latency_caps() (no real network, all 4 quadrants)
  2. Live check: this machine's node_capabilities() must contain net.github and
     exactly one fast/slow mark (not both, and not neither, once connected)

Layer 2 is why this case exists: prove the live probe actually attaches the label, not merely that the pure
function is correct and never called (the pitfall SCANNER-DOWN gate v1 hit the same day --
the gate existed but nothing checked that it would really fire).

Read-only: node_capabilities() only probes, and writes no files.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _engine import check, finish, load  # noqa: E402

m = load()

# -- layer 1: pure-function boundaries (4 quadrants) --
THRESH = m.NET_GITHUB_FAST_THRESHOLD_S

check("down -> empty labels (must not report either fast or slow)",
      m._github_latency_caps(False, 0.1) == [])
check("down -> do not report net.github even when latency is tiny",
      "net.github" not in m._github_latency_caps(False, 0.1))

caps_fast = m._github_latency_caps(True, THRESH - 0.5)
check("up + latency < threshold -> net.github + net.github.fast",
      set(caps_fast) == {"net.github", "net.github.fast"}, "actual %r" % caps_fast)

caps_slow = m._github_latency_caps(True, THRESH + 0.5)
check("up + latency >= threshold -> net.github + net.github.slow",
      set(caps_slow) == {"net.github", "net.github.slow"}, "actual %r" % caps_slow)

caps_edge = m._github_latency_caps(True, THRESH)
check("boundary (exactly the threshold) is slow (< is the only fast test, not <=)",
      set(caps_edge) == {"net.github", "net.github.slow"}, "actual %r" % caps_edge)

# -- layer 2: live probe (this machine is a laptop; the historical anchor is slow, but do not hard-code identity,
#    only assert the labels are consistent -- so this case does not become another hard-coded guess) --
real_caps = set(m.node_capabilities())
has_fast = "net.github.fast" in real_caps
has_slow = "net.github.slow" in real_caps
check("live probe: net.github is present (this machine can reach github; precondition)",
      "net.github" in real_caps, "actual caps subset: %s" %
      sorted(c for c in real_caps if c.startswith("net.")))
check("live probe: fast and slow hit exactly one, no more and no less (mutually exclusive)",
      has_fast != has_slow, "fast=%s slow=%s" % (has_fast, has_slow))

finish()
