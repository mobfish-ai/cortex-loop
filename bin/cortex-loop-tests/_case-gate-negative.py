#!/usr/bin/env python3
"""E14 -- a TASKS row missing failure_modes (negative space) -> the contract gate must FAIL.

Positive and negative bounds are the core of the loop_tasks contract: writing only "what counts as done"
and not "what counts as cheating" is a half contract. An executor can then wave an empty document past
the completion gate. If the gate cannot stop a half contract, the mechanical gate is decoration.

Isolation: copy the real ledger into a temporary CORTEX_ROOT and break the copy. The real TASKS.md is not written.
"""

import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _engine import check, finish  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GATE = os.path.join(ROOT, "bin", "knowledge-contract-gate.py")
REAL_TASKS = os.path.join(ROOT, "brain-network", "directions", "loop-ops", "TASKS.md")
REL = "brain-network/directions/gatecheck/TASKS.md"

sandbox = tempfile.mkdtemp(prefix="cortex-gate-neg.")


def run_gate(root):
    env = dict(os.environ, CORTEX_ROOT=root)
    proc = subprocess.run(["python3", GATE, "check-path", REL],
                          capture_output=True, text=True, env=env, timeout=120)
    return proc.returncode, proc.stdout + proc.stderr


try:
    target = os.path.join(sandbox, REL)
    os.makedirs(os.path.dirname(target))
    shutil.copy2(REAL_TASKS, target)

    # (1) an unmodified copy must PASS (prove the fixture itself is good, or the later red is meaningless)
    code, out = run_gate(sandbox)
    check("unmodified copy gate PASS", code == 0 and '"status": "PASS"' in out, out.strip()[-300:])

    # (2) blank one row's failure_modes -> must FAIL
    with open(target, encoding="utf-8") as fh:
        lines = fh.read().split("\n")
    hit = None
    header = None
    failure_idx = None
    for idx, line in enumerate(lines):
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if line.strip().startswith("|") and "id" in cells and "failure_modes" in cells:
            header = cells
            failure_idx = cells.index("failure_modes")
            continue
        if (header and line.strip().startswith("|") and len(cells) == len(header)
                and cells[0] not in ("id", "") and set("".join(cells)) - set("-: ")):
            cells[failure_idx] = "-"
            lines[idx] = "| " + " | ".join(cells) + " |"
            hit = idx
            break
    check("found a task row and broke its failure_modes", hit is not None)
    with open(target, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))

    code, out = run_gate(sandbox)
    check("missing failure_modes -> gate exit code is non-zero", code != 0, "exit code %d" % code)
    check("gate names the half contract", "failure_modes empty (half contract)" in out, out.strip()[-300:])
    check("gate verdict FAIL", '"status": "FAIL"' in out, out.strip()[-300:])

    # (3) also check the twin negative-space clause: done with no evidence is a fake completion
    with open(target, encoding="utf-8") as fh:
        text = fh.read()
    lines = text.split("\n")
    repaired_half_contract = False
    blanked_done = False
    evidence_idx = header.index("evidence")
    status_idx = header.index("status")
    for idx, line in enumerate(lines):
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if not line.strip().startswith("|") or len(cells) != len(header):
            continue
        if idx == hit:
            cells[failure_idx] = "minimal negative space"
            lines[idx] = "| " + " | ".join(cells) + " |"
            repaired_half_contract = True
        elif not blanked_done and cells[status_idx] == "done":
            cells[evidence_idx] = ""
            lines[idx] = "| " + " | ".join(cells) + " |"
            blanked_done = True
    check("half contract repaired and a done row had evidence blanked",
          repaired_half_contract and blanked_done)
    with open(target, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    code, out = run_gate(sandbox)
    check("done with no evidence -> gate FAIL", code != 0 and "done without evidence" in out,
          out.strip()[-300:])
finally:
    shutil.rmtree(sandbox, ignore_errors=True)
    print("    cleanup: temporary CORTEX_ROOT removed; the real ledger was not opened for write")

finish()
