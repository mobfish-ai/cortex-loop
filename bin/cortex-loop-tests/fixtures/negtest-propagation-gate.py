#!/usr/bin/env python3
"""Negative test: propagation gate v2 and node_load release.

The gate runs real scenarios in a temporary git repo and does not touch the real repo:
  A file has history and is committed (clean)     -> allow
  B file has history but was edited and not committed -> block (the class v1 missed)
  C file was only git add, not commit (the old real1/R2 state) -> block
  D file was never in git (untracked)             -> block
"""
import os
import subprocess
import sys
import tempfile

def sh(cwd, cmd):
    return subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True)

def gate(root, artifact):
    """Replica of the propagation-gate v2 criterion in the engine."""
    dirty = sh(root, "git status --porcelain -- %s" % artifact).stdout
    seen = sh(root, "git log -1 --oneline -- %s" % artifact).stdout
    return not (dirty.strip() or not seen.strip())

def gate_v1(root, artifact):
    """The v1 criterion, used to prove v1 really misses B."""
    seen = sh(root, "git log -1 --oneline -- %s" % artifact).stdout
    return bool(seen.strip())

tmp = tempfile.mkdtemp(prefix="gate-test-")
sh(tmp, "git init -q && git config user.email t@t && git config user.name t")

# A: has history and is clean
open(os.path.join(tmp, "a.md"), "w").write("host: x\n")
sh(tmp, "git add a.md && git commit -q -m init")

# B: has history but was edited and not committed (the v1 hole)
open(os.path.join(tmp, "b.md"), "w").write("no host\n")
sh(tmp, "git add b.md && git commit -q -m init-b")
open(os.path.join(tmp, "b.md"), "w").write("host: x\n")      # edited, not committed

# C: added but not committed
open(os.path.join(tmp, "c.md"), "w").write("host: x\n")
sh(tmp, "git add c.md")

# D: untracked
open(os.path.join(tmp, "d.md"), "w").write("host: x\n")

CASES = [("A committed and clean", "a.md", True),
         ("B has history but uncommitted edit", "b.md", False),
         ("C added but not committed", "c.md", False),
         ("D never entered git", "d.md", False)]

fails = 0
print("propagation gate v2 vs v1")
for label, f, expect in CASES:
    v2 = gate(tmp, f)
    v1 = gate_v1(tmp, f)
    ok = (v2 == expect)
    fails += 0 if ok else 1
    print("  %s  %-22s v2=%-5s want=%-5s   (v1=%s%s)"
          % ("PASS" if ok else "FAIL", label, v2, expect, v1,
             "  <- v1 misses this" if v1 != expect else ""))

print()
print("propagation-gate negative test: %s (%d assertions failed)" % ("ALL PASS" if fails == 0 else "FAILED", fails))
sys.exit(1 if fails else 0)
