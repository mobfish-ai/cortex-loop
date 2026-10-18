#!/usr/bin/env python3
"""Mechanical concurrency contract for Cortex task ledgers and Workers.

This fixture deliberately uses barriers/process locks. Final-state-only tests can
accidentally pass under a globally serialized implementation, which is precisely
the regression this contract is intended to prevent.
"""
import argparse
import importlib.machinery
import importlib.util
import json
import os
import signal
import shlex
import subprocess
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ENGINE = ROOT / "bin/cortex-loop"
loader = importlib.machinery.SourceFileLoader("cortex_loop_concurrent", str(ENGINE))
spec = importlib.util.spec_from_loader(loader.name, loader)
loop = importlib.util.module_from_spec(spec)
loader.exec_module(loop)


def check(label, condition, detail=""):
    if not condition:
        raise AssertionError("%s%s" % (label, (": " + detail) if detail else ""))
    print("PASS ", label)


HEADER = (
    "| id | title | status | depends_on | success_criteria | failure_modes | "
    "artifact_paths | short_test | next_advance_after | fails | updated_at | "
    "evidence | leverage | cost_estimate | resource_class | role |\n"
    "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|\n"
)


def row(task_id, title=None):
    return (
        "| %s | %s | pending | - | artifact exists | empty artifact | "
        "reports/%s.md | test -s reports/%s.md | - | 0 | - | - | high | S | "
        "local-only | - |\n"
    ) % (task_id, title or task_id, task_id.lower(), task_id.lower())


def add_args(task_id):
    return argparse.Namespace(
        line="parallel", id=task_id, title="atomic %s" % task_id,
        depends_on="-", success_criteria="artifact exists",
        failure_modes="empty artifact", artifact_paths="reports/%s.md" % task_id.lower(),
        short_test="test -s reports/%s.md" % task_id.lower(), leverage="high",
        cost_estimate="S", resource_class="local-only", role="-",
    )


def has_task(line, task_id):
    return any(task.get("id") == task_id for task in loop.load_tasks(line))


with tempfile.TemporaryDirectory(prefix=".cortex-concurrency-", dir=ROOT) as tmp:
    sandbox = Path(tmp)
    directions = sandbox / "directions"
    line_dir = directions / "parallel"
    line_dir.mkdir(parents=True)
    tasks_file = line_dir / "TASKS.md"
    tasks_file.write_text(HEADER + row("T1") + row("T2"))
    loop.DIRECTIONS = str(directions)

    # 1. Different rows must update concurrently without whole-file lost update.
    start = threading.Barrier(3)
    results = []
    result_lock = threading.Lock()

    def update(task_id, evidence):
        start.wait()
        result = loop.set_cells(
            str(tasks_file), task_id,
            {"status": "running", "evidence": evidence},
            expected_status="pending",
        )
        with result_lock:
            results.append((task_id, result))

    workers = [
        threading.Thread(target=update, args=("T1", "reports/t1.md")),
        threading.Thread(target=update, args=("T2", "reports/t2.md")),
    ]
    for worker in workers:
        worker.start()
    start.wait()
    for worker in workers:
        worker.join(timeout=5)
    check("different-task ledger updates both commit", sorted(results) == [("T1", True), ("T2", True)])
    after = {task["id"]: task for task in loop.load_tasks("parallel")}
    check("different-task ledger updates lose neither row",
          after["T1"]["evidence"] == "reports/t1.md"
          and after["T2"]["evidence"] == "reports/t2.md")

    # 2. Same-row status transition is CAS: pending -> running has one winner.
    loop.set_cells(str(tasks_file), "T1", {"status": "pending", "evidence": "-"})
    start = threading.Barrier(3)
    cas_results = []

    def claim(evidence):
        start.wait()
        won = loop.set_cells(
            str(tasks_file), "T1",
            {"status": "running", "evidence": evidence},
            expected_status="pending",
        )
        with result_lock:
            cas_results.append((evidence, won))

    claimers = [
        threading.Thread(target=claim, args=("claim-a",)),
        threading.Thread(target=claim, args=("claim-b",)),
    ]
    for claimer in claimers:
        claimer.start()
    start.wait()
    for claimer in claimers:
        claimer.join(timeout=5)
    winners = [evidence for evidence, won in cas_results if won]
    final_t1 = loop._task_or_error("parallel", "T1")
    check("same-task ledger CAS has exactly one winner", len(winners) == 1, repr(cas_results))
    check("same-task CAS preserves winner state",
          final_t1["status"] == "running" and final_t1["evidence"] == winners[0])

    # 3. Worker flock excludes the same task but not another task. Use a separate
    # process because acquire_task_lock is intentionally re-entrant in one process.
    lock_line = "fixture-%s" % sandbox.name
    holder_code = """
import importlib.machinery, importlib.util, sys, time
p, line, task = sys.argv[1:4]
l = importlib.machinery.SourceFileLoader('holder_loop', p)
s = importlib.util.spec_from_loader(l.name, l)
m = importlib.util.module_from_spec(s); l.exec_module(m)
print('ACQUIRED' if m.acquire_task_lock(line, task) else 'REJECTED', flush=True)
time.sleep(30)
"""
    probe_code = """
import importlib.machinery, importlib.util, sys
p, line, task = sys.argv[1:4]
l = importlib.machinery.SourceFileLoader('probe_loop', p)
s = importlib.util.spec_from_loader(l.name, l)
m = importlib.util.module_from_spec(s); l.exec_module(m)
print('ACQUIRED' if m.acquire_task_lock(line, task) else 'REJECTED')
"""
    holder = subprocess.Popen(
        ["python3", "-c", holder_code, str(ENGINE), lock_line, "T1"],
        cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    try:
        check("first Worker acquires task lock", holder.stdout.readline().strip() == "ACQUIRED")
        same = subprocess.run(
            ["python3", "-c", probe_code, str(ENGINE), lock_line, "T1"],
            cwd=ROOT, text=True, capture_output=True, timeout=5,
        )
        other = subprocess.run(
            ["python3", "-c", probe_code, str(ENGINE), lock_line, "T2"],
            cwd=ROOT, text=True, capture_output=True, timeout=5,
        )
        check("same-task Worker lock rejects duplicate", same.returncode == 0 and same.stdout.strip() == "REJECTED")
        check("different-task Worker lock remains available", other.returncode == 0 and other.stdout.strip() == "ACQUIRED")
    finally:
        holder.terminate()
        try:
            holder.wait(timeout=5)
        except subprocess.TimeoutExpired:
            holder.kill()
            holder.wait(timeout=5)

    # When the outer task-run exits unexpectedly, the adapter grandchild inherits the same flock;
    # while it is still working, the next tick must not rerun a live running task as an orphan.
    child_pidfile = sandbox / "adapter-shell.pid"
    orphan_holder_code = """
import importlib.machinery, importlib.util, shlex, sys
p, line, task, pidfile = sys.argv[1:5]
l = importlib.machinery.SourceFileLoader('orphan_loop', p)
s = importlib.util.spec_from_loader(l.name, l)
m = importlib.util.module_from_spec(s); l.exec_module(m)
assert m.acquire_task_lock(line, task)
m.run('printf %s > %s; sleep 30' % ('$$', shlex.quote(pidfile)), timeout=40)
"""
    orphan = subprocess.Popen(
        ["python3", "-c", orphan_holder_code, str(ENGINE), lock_line, "T3",
         str(child_pidfile)], cwd=ROOT, text=True,
    )
    deadline = time.time() + 5
    while time.time() < deadline and not child_pidfile.exists():
        time.sleep(0.05)
    check("adapter shell starts under inherited task lock", child_pidfile.exists())
    child_pid = int(child_pidfile.read_text().strip())
    orphan.terminate()
    orphan.wait(timeout=5)
    inherited = subprocess.run(
        ["python3", "-c", probe_code, str(ENGINE), lock_line, "T3"],
        cwd=ROOT, text=True, capture_output=True, timeout=5,
    )
    check("orphan adapter keeps same-task lock after parent exits",
          inherited.stdout.strip() == "REJECTED")
    os.killpg(child_pid, signal.SIGTERM)
    deadline = time.time() + 5
    released = False
    while time.time() < deadline:
        probe = subprocess.run(
            ["python3", "-c", probe_code, str(ENGINE), lock_line, "T3"],
            cwd=ROOT, text=True, capture_output=True, timeout=5,
        )
        if probe.stdout.strip() == "ACQUIRED":
            released = True
            break
        time.sleep(0.05)
    check("task lock releases when orphan adapter exits", released)

    # 4. task-add validates a private candidate first. While the gate is blocked,
    # readers must see no T3; a rejected candidate must never be published.
    saved_run = loop.run
    gate_entered = threading.Event()
    gate_release = threading.Event()
    gate_observations = {}

    def blocking_gate(command, timeout=60):
        parts = shlex.split(command)
        candidate = Path(parts[parts.index("check-path") + 1])
        gate_observations["candidate_has_t3"] = any(
            task.get("id") == "T3" for _, task in loop.read_table(str(candidate))[2]
        )
        gate_observations["live_has_t3"] = any(
            task.get("id") == "T3" for task in loop.load_tasks("parallel")
        )
        gate_entered.set()
        check("task-add gate released by fixture", gate_release.wait(timeout=5))
        return 0, "PASS fixture gate"

    loop.run = blocking_gate
    add_result = []
    add_thread = threading.Thread(target=lambda: add_result.append(loop.cmd_task_add(add_args("T3"))))
    add_thread.start()
    check("task-add reaches private pre-publication gate", gate_entered.wait(timeout=5))
    check("task-add candidate contains complete new task", gate_observations.get("candidate_has_t3") is True)
    check("task-add does not expose candidate before gate", gate_observations.get("live_has_t3") is False
          and not has_task("parallel", "T3"))
    gate_release.set()
    add_thread.join(timeout=5)
    check("task-add publishes only after gate passes", add_result == [0]
          and loop._task_or_error("parallel", "T3")["status"] == "pending")

    loop.run = lambda _command, timeout=60: (1, "FAIL injected gate")
    rejected = loop.cmd_task_add(add_args("T4"))
    check("task-add rejected candidate is never published",
          rejected == 1 and not has_task("parallel", "T4"))

    # Concurrent valid adds each re-read under the ledger lock; neither may erase
    # the other even though both candidates were built from an older snapshot.
    loop.run = lambda _command, timeout=60: (0, "PASS fixture gate")
    start = threading.Barrier(3)
    add_results = []

    def concurrent_add(task_id):
        start.wait()
        result = loop.cmd_task_add(add_args(task_id))
        with result_lock:
            add_results.append((task_id, result))

    adders = [
        threading.Thread(target=concurrent_add, args=("T5",)),
        threading.Thread(target=concurrent_add, args=("T6",)),
    ]
    for adder in adders:
        adder.start()
    start.wait()
    for adder in adders:
        adder.join(timeout=5)
    ids = [task["id"] for task in loop.load_tasks("parallel")]
    check("concurrent task-add publishes both rows without loss",
          sorted(add_results) == [("T5", 0), ("T6", 0)]
          and ids.count("T5") == 1 and ids.count("T6") == 1)
    loop.run = saved_run

    # 5. Cheap adapter account health is another shared write surface. Concurrent
    # failures for different accounts must merge into one valid JSON document.
    compat_lib = ROOT / "bin/cortex-loop-adapters/_openai_compat_lib.sh"
    cheap_state = sandbox / "cheap-account-state.json"
    mark_command = 'source "$1"; oc_mark_failure "$2" "$3" "$4"'
    markers = []
    for idx in range(8):
        account = "acct-a" if idx % 2 == 0 else "acct-b"
        markers.append(subprocess.Popen(
            ["bash", "-c", mark_command, "fixture", str(compat_lib),
             str(cheap_state), account, "MiniMax-%s" % account],
            cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        ))
    marker_results = [marker.communicate(timeout=10) for marker in markers]
    check("cheap account state concurrent writers all exit cleanly",
          all(marker.returncode == 0 for marker in markers), repr(marker_results))
    cheap_data = json.loads(cheap_state.read_text())
    check("cheap account state JSON merges concurrent accounts",
          cheap_data.get("acct-a", {}).get("fail_count") == 4
          and cheap_data.get("acct-b", {}).get("fail_count") == 4)

print("concurrent execution contract: PASS")
