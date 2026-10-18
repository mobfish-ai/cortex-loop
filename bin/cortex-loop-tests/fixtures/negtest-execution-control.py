#!/usr/bin/env python3
"""Deterministic regression tests for Cortex execution control atoms."""
import argparse
import importlib.machinery
import importlib.util
import shutil
import tempfile
import os
import signal
import subprocess
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
loader = importlib.machinery.SourceFileLoader("cortex_loop", str(ROOT / "bin/cortex-loop"))
spec = importlib.util.spec_from_loader(loader.name, loader)
loop = importlib.util.module_from_spec(spec)
loader.exec_module(loop)

assert [loop._retry_delay_min(n) for n in range(1, 7)] == [15, 30, 60, 120, 120, 120]
os.environ.pop("CORTEX_MAX_ADVANCE_PER_TICK", None)
assert loop.tick_advance_cap(50) == 1
os.environ["CORTEX_MAX_ADVANCE_PER_TICK"] = "2"
assert loop.tick_advance_cap(50) == 2
os.environ["CORTEX_MAX_ADVANCE_PER_TICK"] = "invalid"
assert loop.tick_advance_cap(50) == 1
os.environ.pop("CORTEX_MAX_ADVANCE_PER_TICK", None)

candidates = [
    {"id": "T1", "leverage": "low", "resource_class": "llm-heavy"},
    {"id": "T2", "leverage": "high", "resource_class": "local-only"},
    {"id": "T3", "leverage": "high", "resource_class": "human-gate"},
]
assert [t["id"] for t in loop.select_task_rows(candidates, "unknown")] == ["T2"]
assert [t["id"] for t in loop.select_task_rows(candidates, "ok")] == ["T2", "T1"]
hyphen_tasks = [
    {"id": "IMM-T1", "status": "done", "depends_on": "-"},
    {"id": "IMM-T12", "status": "pending", "depends_on": "IMM-T1"},
]
assert loop.runnable(hyphen_tasks, hyphen_tasks[1]), \
    "hyphenated task ids must remain one dependency token"
assert loop.is_negative_test_sentinel(
    "loop-ops", {"id": "T3", "status": "blocked", "role": "negative_test_sentinel"}
)
assert {"task-resume", "task-route", "submit", "try-complete"} <= \
    loop.LEDGER_MUTATION_COMMANDS

with tempfile.TemporaryDirectory(prefix=".cortex-task-atoms-", dir=ROOT) as tmp:
    directions = Path(tmp) / "directions"
    target = directions / "testline"
    target.mkdir(parents=True)
    shutil.copy(ROOT / "brain-network/directions/cortex-immune/TASKS.md", target / "TASKS.md")
    loop.DIRECTIONS = str(directions)
    add = argparse.Namespace(
        line="testline", id="T4", title="atomic add", depends_on="-",
        success_criteria="artifact exists", failure_modes="empty artifact",
        artifact_paths="reports/test.md", short_test="bash bin/true.sh",
        leverage="high", cost_estimate="S", resource_class="local-only", role="-",
    )
    assert loop.cmd_task_add(add) == 0
    task = loop._task_or_error("testline", "T4")
    assert task["title"] == "atomic add"
    assert task["status"] == "pending"
    assert len(task) == len(loop.read_table(str(target / "TASKS.md"))[1])

    test_file = Path(tmp) / "acceptance.sh"
    test_file.write_text("#!/bin/sh\nexit 0\n")
    original_test = test_file.read_bytes()
    loop.set_cell(str(target / "TASKS.md"), "T4", "status", "done")
    loop.set_cell(str(target / "TASKS.md"), "T4", "title", "executor rewrote contract")
    loop.set_cell(str(target / "TASKS.md"), "T4", "evidence", "fake.md")
    test_file.write_text("#!/bin/sh\nexit 1\n")
    loop.record_incident = lambda *args, **kwargs: None
    assert not loop.enforce_execution_bounds(
        "testline", task, str(test_file), original_test
    )
    guarded = loop._task_or_error("testline", "T4")
    assert guarded["status"] == "running"
    assert guarded["title"] == "atomic add"
    assert guarded["evidence"] == "-"
    assert test_file.read_bytes() == original_test

    for existing_task in loop.load_tasks("testline"):
        if existing_task.get("status") == "running":
            loop.set_cell(str(target / "TASKS.md"), existing_task["id"], "status", "pending")
    loop.set_cell(str(target / "TASKS.md"), "T4", "status", "running")
    loop.set_cell(str(target / "TASKS.md"), "T4", "fails", "3")
    retry = argparse.Namespace(
        line="testline", task="T4", reason="fixture", reset_fails=True,
    )
    assert loop.cmd_task_retry(retry) == 0
    task = loop._task_or_error("testline", "T4")
    assert task["status"] == "pending"
    assert task["fails"] == "0"
    assert task["next_advance_after"] == "-"

    loop.set_cell(str(target / "TASKS.md"), "T4", "status", "done")
    loop.set_cell(str(target / "TASKS.md"), "T4", "evidence", "reports/test.md")
    reopen = argparse.Namespace(line="testline", task="T4", reason="false positive")
    assert loop.cmd_task_reopen(reopen) == 0
    task = loop._task_or_error("testline", "T4")
    assert task["status"] == "pending"
    assert task["evidence"] == "-"
    assert task["fails"] == "1"

    hold = argparse.Namespace(
        line="testline", task="T4", status="waiting_external",
        reason="remote approval required",
    )
    assert loop.cmd_task_hold(hold) == 0
    assert loop._task_or_error("testline", "T4")["status"] == "waiting_external"
    resume = argparse.Namespace(
        line="testline", task="T4", reason="approval received",
    )
    assert loop.cmd_task_resume(resume) == 0
    assert loop._task_or_error("testline", "T4")["status"] == "pending"

    explicit_hold = argparse.Namespace(
        line="testline", task="T4", status="blocked", reason="controller hold",
    )
    assert loop.cmd_task_hold(explicit_hold) == 0
    held = loop._task_or_error("testline", "T4")
    assert held["next_advance_after"] == "HOLD"
    assert "T4" not in loop.resume_recoverable_blocked("testline"), \
        "repair controller must not override explicit task-hold"
    assert loop.cmd_task_resume(resume) == 0

    route = argparse.Namespace(
        line="testline", task="T4", resource_class="llm-heavy",
        resume=True, reason="pure technical task was misclassified",
    )
    loop.set_cell(str(target / "TASKS.md"), "T4", "status", "blocked")
    assert loop.cmd_task_route(route) == 0
    routed = loop._task_or_error("testline", "T4")
    assert routed["resource_class"] == "llm-heavy"
    assert routed["status"] == "pending"

    loop.set_cell(str(target / "TASKS.md"), "T4", "status", "running")
    saved_recover_completed = loop.recover_completed_attempt
    loop.recover_completed_attempt = lambda *_args, **_kwargs: False
    try:
        assert loop.reclaim_inherited_running("testline", "cheap") == ["T4"]
    finally:
        loop.recover_completed_attempt = saved_recover_completed
    reclaimed = loop._task_or_error("testline", "T4")
    assert reclaimed["status"] == "pending"
    assert reclaimed["next_advance_after"] == "-"

    loop.set_cell(str(target / "TASKS.md"), "T4", "status", "blocked")
    loop.set_cell(str(target / "TASKS.md"), "T4", "fails", "4")
    loop.set_cell(str(target / "TASKS.md"), "T4", "resource_class", "local-only")
    loop.set_cell(str(target / "TASKS.md"), "T4", "next_advance_after", "-")
    resumed_ids = loop.resume_recoverable_blocked("testline")
    assert "T4" in resumed_ids
    recovered = loop._task_or_error("testline", "T4")
    assert recovered["status"] == "pending" and recovered["fails"] == "4"

    loop.set_cell(str(target / "TASKS.md"), "T4", "status", "pending")
    captured_prompt = {}
    def fake_diagnose_adapter(_executor, _tag, prompt, **_kwargs):
        captured_prompt["text"] = prompt
        return "suggested state: blocked, keep fixing the root cause"
    loop.run_adapter = fake_diagnose_adapter
    loop.ai_diagnose(
        "testline", "cheap", recovered, 4,
        failure={"stage": "judge", "rc": 1, "detail": "delta should be 53.4%"},
    )
    assert loop._task_or_error("testline", "T4")["status"] == "pending", \
        "free-form diagnosis must not mutate scheduler state"
    assert "real failure stage: judge" in captured_prompt["text"]
    assert "delta should be 53.4%" in captured_prompt["text"]

    sentinel_dir = directions / "sentinel-line"
    sentinel_dir.mkdir()
    (sentinel_dir / "TASKS.md").write_text(
        "| id | title | status | depends_on | success_criteria | failure_modes | "
        "artifact_paths | short_test | next_advance_after | fails | updated_at | "
        "evidence | leverage | cost_estimate | resource_class | role |\n"
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|\n"
        "| S1 | completion gate sentinel | blocked | - | stays red | must not complete | "
        "reports/never.md | test -e reports/never.md | - | 3 | 2026-07-01T00:00+0800 | "
        "- | high | S | local-only | negative_test_sentinel |\n"
    )
    sentinel = loop._task_or_error("sentinel-line", "S1")
    assert loop.is_negative_test_sentinel("sentinel-line", sentinel)
    assert loop.stuck_tasks("sentinel-line") == [], \
        "sentinel must not enter D+3 escalation candidates"
    assert loop.resume_recoverable_blocked("sentinel-line") == [], \
        "repair controller must not resume a sentinel"
    assert loop.cmd_task_resume(argparse.Namespace(
        line="sentinel-line", task="S1", reason="negative fixture"
    )) == 1
    assert loop.cmd_try_complete(argparse.Namespace(
        line="sentinel-line", task="S1", judge=False
    )) == 1
    assert loop.cmd_try_complete.last_failure["stage"] == "sentinel"

    saved_try_complete = loop.cmd_try_complete
    saved_run = loop.run
    recovered["fails"] = "0"
    def fake_try_complete(_args):
        loop.set_cell(str(target / "TASKS.md"), "T4", "status", "done")
        return 0
    loop.cmd_try_complete = fake_try_complete
    loop.run = lambda *_args, **_kwargs: (_ for _ in ()).throw(
        AssertionError("settle-first must not call adapter"))
    assert loop.advance_once("testline", recovered, "cheap", 1) == 0
    loop.cmd_try_complete = saved_try_complete
    loop.run = saved_run

with tempfile.TemporaryDirectory(prefix=".cortex-controller-gates-", dir=ROOT) as tmp:
    fixture_root = Path(tmp)
    repo = fixture_root / "work"
    origin = fixture_root / "origin.git"

    def git_run(*args):
        return subprocess.run(
            ["git", "-C", str(repo), *args],
            text=True, capture_output=True, check=True,
        )

    subprocess.run(["git", "init", "--bare", str(origin)], check=True,
                   text=True, capture_output=True)
    subprocess.run(["git", "init", str(repo)], check=True,
                   text=True, capture_output=True)
    git_run("config", "user.name", "Cortex Fixture")
    git_run("config", "user.email", "cortex-fixture@example.invalid")
    git_run("remote", "add", "origin", str(origin))
    (repo / "brain-network/directions/gates").mkdir(parents=True)
    (repo / "reports").mkdir()
    (repo / "reports/out.md").write_text("origin-bound artifact\n")
    (repo / "reports/local.md").write_text("initial origin artifact\n")
    (repo / ".gitignore").write_text("reports/ignored.md\n")
    task_header = (
        "| id | title | status | depends_on | success_criteria | failure_modes | "
        "artifact_paths | short_test | next_advance_after | fails | updated_at | "
        "evidence | leverage | cost_estimate | resource_class |\n"
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|\n"
    )
    task_rows = "".join([
        "| T1 | origin positive | pending | - | delivered | dirty or local only | "
        "reports/out.md | test -s reports/out.md | - | 0 | - | - | high | S | local-only |\n",
        "| T2 | unbound negative | pending | - | delivered | ignored artifact | "
        "reports/ignored.md | test -s reports/ignored.md | - | 0 | - | - | high | S | local-only |\n",
        "| T3 | origin negative | pending | - | delivered | local-only commit | "
        "reports/local.md | test -s reports/local.md | - | 0 | - | - | high | S | local-only |\n",
    ])
    tasks_file = repo / "brain-network/directions/gates/TASKS.md"
    tasks_file.write_text(task_header + task_rows)
    git_run("add", ".gitignore", "reports/out.md", "reports/local.md",
            "brain-network/directions/gates/TASKS.md")
    git_run("commit", "-m", "fixture baseline")
    git_run("push", "-u", "origin", "HEAD:main")
    (repo / "reports/ignored.md").write_text("ignored but non-empty\n")

    saved_root = loop.ROOT
    saved_directions = loop.DIRECTIONS
    saved_failure_state = loop.FAILURE_STATE
    saved_auto_credit = loop.auto_credit_decided
    saved_land_task_artifacts = loop.land_task_artifacts
    try:
        loop.ROOT = str(repo)
        loop.DIRECTIONS = str(repo / "brain-network/directions")
        loop.FAILURE_STATE = str(repo / ".git/cortex-loop-state/failures.json")
        loop.auto_credit_decided = lambda *_args, **_kwargs: None
        # This block only tests the clean/commit/origin checks, not the transaction committer again.
        loop.land_task_artifacts = lambda *_args, **_kwargs: (True, "fixture bypass")

        # Positive three-check: clean + tracked commit binding + local bare origin reachable.
        assert loop.cmd_try_complete(
            argparse.Namespace(line="gates", task="T1", judge=False)) == 0

        # Clean negative: a dirty worktree must not become done even if short_test passes.
        loop.set_cell(str(tasks_file), "T1", "status", "pending")
        (repo / "reports/out.md").write_text("dirty artifact\n")
        assert loop.cmd_try_complete(
            argparse.Namespace(line="gates", task="T1", judge=False)) == 1
        assert loop.cmd_try_complete.last_failure["stage"] == "artifact-clean"
        git_run("checkout", "--", "reports/out.md")

        # Commit-binding negative: a file hidden by .gitignore is status-clean, but has no tracked blob.
        assert loop.cmd_try_complete(
            argparse.Namespace(line="gates", task="T2", judge=False)) == 1
        assert loop.cmd_try_complete.last_failure["stage"] == "commit-binding"

        # Origin negative then positive: a local commit that is not pushed must stay red; the same gate goes green after push.
        (repo / "reports/local.md").write_text("local-only revision\n")
        git_run("add", "reports/local.md")
        git_run("commit", "-m", "local artifact revision")
        assert loop.cmd_try_complete(
            argparse.Namespace(line="gates", task="T3", judge=False)) == 0
        assert loop._task_or_error("gates", "T3")["status"] == "settling"
        assert loop.cmd_try_complete.last_failure["stage"] == "artifact-land-deferred"
        git_run("push", "origin", "HEAD:main")
        assert loop.cmd_try_complete(
            argparse.Namespace(line="gates", task="T3", judge=False)) == 0

        # The daily cap accumulates across ticks; attempt cap+1 must fail closed.
        ok1, used1, _ = loop.reserve_daily_advance("daily-line", 2)
        ok2, used2, _ = loop.reserve_daily_advance("daily-line", 2)
        ok3, used3, reason3 = loop.reserve_daily_advance("daily-line", 2)
        assert (ok1, used1, ok2, used2) == (True, 1, True, 2)
        assert not ok3 and used3 == 2 and "calendar-day cap" in reason3
        saved_now = loop.now
        tomorrow = saved_now() + loop.timedelta(days=1)
        loop.now = lambda: tomorrow
        try:
            next_day_ok, next_day_used, _ = loop.reserve_daily_advance("daily-line", 2)
            assert next_day_ok and next_day_used == 1
        finally:
            loop.now = saved_now

        # Concurrent positive and negative: 4 nodes reserve cap=2 at once; after CAS exactly 2 succeed.
        race_results = []
        race_lock = threading.Lock()
        def reserve_race():
            result = loop.reserve_daily_advance("race-line", 2)
            with race_lock:
                race_results.append(result)
        threads = [threading.Thread(target=reserve_race) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        assert sum(1 for ok, _used, _why in race_results if ok) == 2, race_results

        # Failure context no longer depends on /tmp: redacted, reread across a restart, bounded to 128 rows.
        saved = loop.persist_failure_context(
            "gates", "T1",
            {"stage": "adapter", "rc": 7,
             "detail": "Authorization: Bearer secret-value token=sk-supersecretvalue"},
        )
        assert saved["rc"] == 7 and "secret-value" not in saved["detail"]
        assert loop.load_failure_context("gates", "T1") == saved
        restart_prompt = {}
        saved_adapter = loop.run_adapter
        loop.run_adapter = lambda _executor, _tag, prompt, **_kwargs: (
            restart_prompt.setdefault("text", prompt) or "root cause: fixture"
        )
        try:
            # Keep the diagnostic integration bound to the fixture's task row.
            # Some cortex-loop revisions can return None from _task_or_error
            # after the completion/landing transitions even though the task
            # row is still present in the fixture table.  The diagnostic
            # contract needs the row, not a second scheduler lookup.
            gate_task = loop._task_or_error("gates", "T1")
            if gate_task is None:
                gate_task = next(
                    (row for _line, row in loop.read_table(str(tasks_file))[2]
                     if row.get("id") == "T1"),
                    None,
                )
            assert gate_task is not None, "fixture task gates/T1 must exist"
            loop.ai_diagnose(
                "gates", "cheap", gate_task, 2,
                failure=None,
            )
        finally:
            loop.run_adapter = saved_adapter
        assert "real failure stage: adapter" in restart_prompt["text"]
        assert "secret-value" not in restart_prompt["text"]
        for idx in range(140):
            loop.persist_failure_context(
                "bounded", "T%d" % idx,
                {"stage": "adapter", "rc": 9, "detail": "failure %d" % idx},
            )
        assert len(loop._load_failure_state()) == 128
        assert loop._result_signature("bounded", "T139") == "adapter-rc=9"
    finally:
        loop.ROOT = saved_root
        loop.DIRECTIONS = saved_directions
        loop.FAILURE_STATE = saved_failure_state
        loop.auto_credit_decided = saved_auto_credit
        loop.land_task_artifacts = saved_land_task_artifacts

saved_active_child = loop._ACTIVE_CHILD_PROC
saved_killpg = loop.os.killpg
forwarded = []
class FakeChild:
    pid = 43210
    def poll(self):
        return None
    def kill(self):
        raise AssertionError("kill fallback should not run")
try:
    loop._ACTIVE_CHILD_PROC = FakeChild()
    loop.os.killpg = lambda pid, sig: forwarded.append((pid, sig))
    try:
        loop._forward_termination(signal.SIGTERM, None)
        raise AssertionError("termination handler must exit")
    except SystemExit as exc:
        assert exc.code == 128 + signal.SIGTERM
    assert forwarded == [(43210, signal.SIGTERM)]
finally:
    loop._ACTIVE_CHILD_PROC = saved_active_child
    loop.os.killpg = saved_killpg

def dispatch_eval(case):
    """Evaluate only the dispatch decision boundary; never calls a provider."""
    attempts = {item["route_id"]: item for item in case.get("attempts", [])}
    required_binding = (
        "worktree_id", "session_id", "thread_id", "base_commit", "runtime",
        "instance_id",
    )
    if case.get("model_only_change"):
        return "FAIL_MODEL_SWAP_ONLY"
    if case.get("health_only"):
        return "FAIL_HEALTH_ONLY"
    if case.get("report_only"):
        return "FAIL_REPORT_ONLY"
    required_fallbacks = set(case.get("required_fallback_route_ids", []))
    if required_fallbacks and not required_fallbacks.issubset(attempts):
        return "FAIL_EARLY_BLOCKER"
    if case.get("claim") == "complete":
        delivery = case.get("delivery", {})
        if not delivery.get("state_change"):
            return "FAIL_PLAN_OR_READINESS_ONLY"
        if not delivery.get("evidence") or not delivery.get("rerunnable"):
            return "FAIL_TEXT_OR_UNBOUND_EVIDENCE"
        if not delivery.get("independent_verified"):
            return "FAIL_PRODUCER_ONLY_JUDGE"
        if set(delivery.get("binding", {})) != set(required_binding):
            return "FAIL_IMMUTABLE_BINDING"
        return "PASS"
    if case.get("claim") == "MACHINE_BLOCKER":
        route_ids = set(case.get("allowed_route_ids", []))
        if not route_ids or set(attempts) != route_ids:
            return "FAIL_EARLY_BLOCKER"
        if any(
            not item.get("allowed") or not item.get("machine_failure")
            for item in attempts.values()
        ):
            return "FAIL_UNPROVEN_BLOCKER"
        return "MACHINE_BLOCKER"
    return "FAIL_NO_TERMINAL_DECISION"


def route(route_id, kind, status="failed", **extra):
    return {
        "route_id": route_id,
        "kind": kind,
        "allowed": True,
        "machine_failure": status == "failed",
        "status": status,
        **extra,
    }


# Deterministic dispatch negative Eval: ACP fails, but an allowed CLI fallback exists.
base_delivery = {
    "state_change": True,
    "evidence": ["artifact", "test", "commit", "receipt"],
    "rerunnable": True,
    "independent_verified": True,
    "binding": {
        "worktree_id": "wt-cli-001",
        "session_id": "session-cli-001",
        "thread_id": "thread-cli-001",
        "base_commit": "base-001",
        "runtime": "fixture-cli",
        "instance_id": "cli-001",
    },
}

assert dispatch_eval({
    "claim": "complete",
    "delivery": {"state_change": False, "evidence": [], "rerunnable": False},
}) == "FAIL_PLAN_OR_READINESS_ONLY"
assert dispatch_eval({"claim": "MACHINE_BLOCKER", "allowed_route_ids": ["acp", "cli"],
                      "attempts": [route("acp", "acp")]}) == "FAIL_EARLY_BLOCKER"
assert dispatch_eval({"model_only_change": True, "claim": "complete",
                      "delivery": base_delivery}) == "FAIL_MODEL_SWAP_ONLY"
assert dispatch_eval({"health_only": True, "claim": "complete",
                      "delivery": base_delivery}) == "FAIL_HEALTH_ONLY"
assert dispatch_eval({"report_only": True, "claim": "complete",
                      "delivery": base_delivery}) == "FAIL_REPORT_ONLY"

fallback_delivery = dict(base_delivery)
fallback_delivery["binding"] = dict(base_delivery["binding"])
assert dispatch_eval({
    "claim": "complete",
    "attempts": [route("acp", "acp"), route("cli", "cli", status="delivered")],
    "required_fallback_route_ids": ["cli"],
    "delivery": fallback_delivery,
}) == "PASS", "an allowed CLI fallback must be attempted and can deliver"
assert dispatch_eval({
    "claim": "complete",
    "attempts": [route("acp", "acp")],
    "required_fallback_route_ids": ["cli"],
    "delivery": fallback_delivery,
}) == "FAIL_EARLY_BLOCKER"

exhausted = [
    route("acp", "acp"),
    route("cli", "cli"),
    route("cli-repair", "repair", repair_of="cli"),
]
assert dispatch_eval({
    "claim": "MACHINE_BLOCKER",
    "allowed_route_ids": ["acp", "cli", "cli-repair"],
    "attempts": exhausted,
}) == "MACHINE_BLOCKER"

contract_text = (ROOT / "aboutme/methods/structure-as-contract/dispatch-contract.md").read_text(
    encoding="utf-8"
)
graph_text = (ROOT / "aboutme/methods/structure-as-contract/graph-orchestration-contract.md").read_text(
    encoding="utf-8"
)
eval_text = (ROOT / "aboutme/methods/structure-as-contract/eval-atlas.md").read_text(
    encoding="utf-8"
)
for marker in (
    "capability_matrix", "ACP unavailable is not terminal", "MACHINE_BLOCKER",
    "instance_id", "seat arbitration", "plan-only", "rerunnable",
):
    assert marker in contract_text, marker
for marker in ("platform_cap", "same-model", "route receipt", "MACHINE_BLOCKER"):
    assert marker in graph_text, marker
for marker in ("dispatch-routing-fallback-001", "FAIL: early blocker", "provider/model blind"):
    assert marker in eval_text, marker

saved_fetch = loop.fetch_refs
saved_plan_tasks = loop.plan_tasks
saved_rev_ref = loop.rev_ref
saved_read_ref = loop.read_ref
try:
    loop.fetch_refs = lambda: None
    loop.plan_tasks = lambda _plan: [{"id": "moot-1", "artifact": "-", "short_test": "-"}]
    loop.rev_ref = lambda ref: "abc" if "/moot/" in ref else ""
    loop.read_ref = lambda ref: "task=moot-1\nnode=fixture\nstatus=moot\n"
    assert loop.cmd_gather(argparse.Namespace(plan="fixture-plan", settle=False)) == 0
finally:
    loop.fetch_refs = saved_fetch
    loop.plan_tasks = saved_plan_tasks
    loop.rev_ref = saved_rev_ref
    loop.read_ref = saved_read_ref

print("PASS execution control: dependency reachability + bounded repair + moot settlement")
