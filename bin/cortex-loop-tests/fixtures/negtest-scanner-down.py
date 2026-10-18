#!/usr/bin/env python3
"""Negative test: break a scanner on purpose and require discover to report it instead of silently counting 0.

Does not touch real files -- load the engine with SourceFileLoader and replace SCANNERS.
Simulate the timeout code with `exit 124`; do not really sleep 300 (that would cost 5 minutes).
"""
import importlib.machinery
import importlib.util
import os
import sys

ENGINE_PATH = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "cortex-loop")

loader = importlib.machinery.SourceFileLoader("cl", ENGINE_PATH)
cl = importlib.util.module_from_spec(importlib.util.spec_from_loader("cl", loader))
loader.exec_module(cl)

# Keep only the scanner under test; do not run the others (this test only checks exit-code triage)
cl.scan_self_defects = lambda: []
cl.scan_contract_debt = lambda: []
cl.scan_network_evenness = lambda: []
cl.scan_data_integrity = lambda: []
cl.scan_frontmatter_readable = lambda: []

CASES = [
    ("A command missing", "this-command-does-not-exist-xyz", True),
    ("B timeout exit 124", "exit 124", True),
    ("C normal no-match exit 1 with output", "echo 'all clear' && exit 1", False),
    ("D normal match exit 0", "echo 'unregistered: foo-skill'", False),
]

fails = 0
for label, cmd, should_be_down in CASES:
    cl.SCANNERS = [("probe", cmd, r"unregistered: (\S+)", "fix %s", "L1", "V2", "skills/")]
    found = cl.discover_candidates()
    down = cl.discover_candidates.last_broken
    is_down = bool(down)
    ok = (is_down == should_be_down)
    fails += 0 if ok else 1
    print("%s  %-28s  SCANNER-DOWN=%-5s want=%-5s candidates=%d"
          % ("PASS" if ok else "FAIL", label, is_down, should_be_down, len(found)))

print()
print("negative test: %s (%d assertions failed)" % ("ALL PASS" if fails == 0 else "FAILED", fails))
sys.exit(1 if fails else 0)
