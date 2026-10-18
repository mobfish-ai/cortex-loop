#!/usr/bin/env python3
"""E14 — TASKS 行缺 failure_modes（负空间）→ 合同 gate 必须 FAIL。

正负夹逼是 loop_tasks 合同的核心：只写「怎样算成」不写「怎样算作弊」= 半合同，
执行者可以拿一份空泛文档骗过完成门。gate 拦不住半合同，机械门就成了摆设。

隔离：把真账本**复制**进临时 CORTEX_ROOT 再改坏，真 TASKS.md 一个字节都不动。
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

    # ① 原样复制 → gate 必须 PASS（先证明夹具本身是好的，否则下面的红没有意义）
    code, out = run_gate(sandbox)
    check("未改动的副本 gate PASS", code == 0 and '"status": "PASS"' in out, out.strip()[-300:])

    # ② 把某一行的 failure_modes 挖空 → 必须 FAIL
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
    check("找到并改坏一条任务的 failure_modes", hit is not None)
    with open(target, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))

    code, out = run_gate(sandbox)
    check("缺 failure_modes → gate 退出码非 0", code != 0, "退出码 %d" % code)
    check("gate 点名半合同", "failure_modes empty (half contract)" in out, out.strip()[-300:])
    check("gate 判定 FAIL", '"status": "FAIL"' in out, out.strip()[-300:])

    # ③ 顺带验负空间的孪生条款：done 无 evidence = 假完成
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
            cells[failure_idx] = "凑合的负空间"
            lines[idx] = "| " + " | ".join(cells) + " |"
            repaired_half_contract = True
        elif not blanked_done and cells[status_idx] == "done":
            cells[evidence_idx] = ""
            lines[idx] = "| " + " | ".join(cells) + " |"
            blanked_done = True
    check("半合同已修复且找到 done 行挖空 evidence",
          repaired_half_contract and blanked_done)
    with open(target, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    code, out = run_gate(sandbox)
    check("done 无 evidence → gate FAIL", code != 0 and "done without evidence" in out,
          out.strip()[-300:])
finally:
    shutil.rmtree(sandbox, ignore_errors=True)
    print("    清理：临时 CORTEX_ROOT 已删；真账本未被打开写入")

finish()
