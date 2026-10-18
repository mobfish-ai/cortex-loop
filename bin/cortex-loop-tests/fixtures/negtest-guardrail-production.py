#!/usr/bin/env python3
"""Production guardrail wiring: atomics, narrow semantics, and no HOME pollution."""
import argparse
import datetime
import importlib.machinery
import importlib.util
import json
import os
import subprocess
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
loader = importlib.machinery.SourceFileLoader("cortex_loop_guardrail", str(REPO / "bin/cortex-loop"))
spec = importlib.util.spec_from_loader(loader.name, loader)
loop = importlib.util.module_from_spec(spec)
loader.exec_module(loop)


def run_atom(script, state, *args):
    env = dict(os.environ, CORTEX_OPENCLAW_STATE=str(state))
    return subprocess.run(
        ["bash", str(REPO / "bin" / script), *args], env=env,
        text=True, capture_output=True, check=True,
    )


with tempfile.TemporaryDirectory(prefix="cortex-guardrail-") as raw:
    root = Path(raw)
    state = root / "state"
    os.environ["CORTEX_OPENCLAW_STATE"] = str(state)
    os.environ["CORTEX_INCIDENT_RECORDING"] = "1"

    scripts = (
        "cortex-authorization-incident.sh",
        "cortex-independent-verification-incident.sh",
        "cortex-budget-incident.sh",
    )
    for script in scripts:
        run_atom(script, state, "init")
        status = json.loads(run_atom(script, state, "status").stdout)
        assert status["state"] == "OK" and status["observed_events"] == 0

    # Stable event id is idempotent, including concurrent/retried producer calls.
    eid = "a-" + "1" * 24
    args = ("record", "T-AUTH", "fixture", "out_of_scope_write", "scope=x", eid)
    procs = [subprocess.Popen(
        ["bash", str(REPO / "bin/cortex-authorization-incident.sh"), *args],
        env=dict(os.environ), text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    ) for _ in range(8)]
    for proc in procs:
        out, err = proc.communicate(timeout=20)
        assert proc.returncode == 0, err
        assert json.loads(out)["event_id"] == eid
    auth_rows = [json.loads(line) for line in
                 (state / "authorization-incidents.jsonl").read_text().splitlines() if line]
    assert len(auth_rows) == 1

    # Real execution-bound violation is a production authorization producer.
    directions = root / "directions"
    task_dir = directions / "guard"
    task_dir.mkdir(parents=True)
    tasks = task_dir / "TASKS.md"
    tasks.write_text(
        "| id | title | status | depends_on | success_criteria | failure_modes | artifact_paths | short_test | next_advance_after | fails | updated_at | evidence | leverage | cost_estimate | resource_class | role |\n"
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|\n"
        "| T1 | bounded | running | - | ok | scope | out.md | test -s out.md | - | 0 | - | - | high | S | local-only | - |\n"
    )
    saved_directions = loop.DIRECTIONS
    saved_record_incident = loop.record_incident
    loop.DIRECTIONS = str(directions)
    loop.record_incident = lambda *_a, **_k: None
    original = loop.pick("guard", "T1")
    loop.set_cell(str(tasks), "T1", "title", "executor changed contract")
    assert not loop.enforce_execution_bounds("guard", original, None, None)
    loop.DIRECTIONS = saved_directions
    loop.record_incident = saved_record_incident
    auth_rows = [json.loads(line) for line in
                 (state / "authorization-incidents.jsonl").read_text().splitlines() if line]
    assert any(row["task_id"] == "T1" and row["incident_type"] == "out_of_scope_write"
               for row in auth_rows)

    # Integrator scope/ref rejection maps to authorization; ordinary conflict does not.
    before_auth = len(auth_rows)
    assert loop.record_authorization_from_integration(
        "guard", "T2", {"status": "rejected_scope", "detail": "outside allowlist"})
    assert not loop.record_authorization_from_integration(
        "guard", "T2", {"status": "retryable_content_conflict", "detail": "diverged"})
    auth_rows = [json.loads(line) for line in
                 (state / "authorization-incidents.jsonl").read_text().splitlines() if line]
    assert len(auth_rows) == before_auth + 1

    # The candidate builder is itself a bounds decision point; do not rely only on the later integrator.
    saved_changed = loop._workspace_changed_paths
    saved_contract = loop.workspace_contract_paths
    loop._workspace_changed_paths = lambda _worktree: ["allowed/out.md", "outside/secret.txt"]
    loop.workspace_contract_paths = lambda _task: {
        "writable_paths": ["allowed"], "artifact_paths": ["allowed/out.md"],
        "read_paths": [], "short_test": "true",
    }
    try:
        try:
            loop.commit_workspace_candidate(
                {"worktree": str(root), "line": "guard", "task": "T-BOUNDS"}, {})
            raise AssertionError("candidate bounds violation must fail closed")
        except RuntimeError as exc:
            assert "outside/secret.txt" in str(exc)
    finally:
        loop._workspace_changed_paths = saved_changed
        loop.workspace_contract_paths = saved_contract
    auth_rows = [json.loads(line) for line in
                 (state / "authorization-incidents.jsonl").read_text().splitlines() if line]
    bounds = next(row for row in auth_rows if row["task_id"] == "T-BOUNDS")
    assert "outside/secret.txt" in bounds["evidence"]

    # A retry integration must share the authorization-event producer with the first integration.
    saved_latest = loop._load_latest_candidate
    saved_integrator = loop.run_workspace_integrator
    saved_append = loop.append_attempt_event
    saved_kb = loop._workspace_kb
    saved_retry_count = loop._attempt_cas_retry_count
    loop._load_latest_candidate = lambda *_a: {
        "worktree": str(root), "artifact_paths": ["allowed/out.md"],
    }
    loop.run_workspace_integrator = lambda _candidate: (
        2, {"status": "rejected_scope", "detail": "retry outside/path.txt"})
    loop.append_attempt_event = lambda *_a, **_k: None
    loop._workspace_kb = lambda *_a: 0
    loop._attempt_cas_retry_count = lambda *_a: 0
    try:
        handled, rc = loop.retry_workspace_integration("guard", {"id": "T-RETRY"})
        assert handled and rc == 2
    finally:
        loop._load_latest_candidate = saved_latest
        loop.run_workspace_integrator = saved_integrator
        loop.append_attempt_event = saved_append
        loop._workspace_kb = saved_kb
        loop._attempt_cas_retry_count = saved_retry_count
    auth_rows = [json.loads(line) for line in
                 (state / "authorization-incidents.jsonl").read_text().splitlines() if line]
    assert any(row["task_id"] == "T-RETRY" and "outside/path.txt" in row["evidence"]
               for row in auth_rows)

    # T64-T66 class of failure: explicit done + independent counter-evidence records once.
    result = root / "result.txt"
    result.write_text("status: done\n")
    failure = {"stage": "cross-artifact", "detail": "producer wiring absent"}
    assert loop.record_false_completion_if_claimed("cortex-immune", "IMM-T64", str(result), failure)
    assert loop.record_false_completion_if_claimed("cortex-immune", "IMM-T64", str(result), failure)
    verification_rows = [json.loads(line) for line in
                         (state / "independent-verification-incidents.jsonl").read_text().splitlines()
                         if line]
    assert len(verification_rows) == 1
    assert verification_rows[0]["incident_type"] == "false_done_claim"
    result.write_text("short_test failed; continuing investigation\n")
    assert not loop.record_false_completion_if_claimed(
        "cortex-immune", "IMM-T65", str(result), {"stage": "short_test", "detail": "rc=1"})
    assert len((state / "independent-verification-incidents.jsonl").read_text().splitlines()) == 1

    # Model budget is narrow: transient 429/rate-limit is not a breach.
    assert not loop.is_model_quota_breach("HTTP 429 rate limit; retry after 2 seconds")
    assert loop.is_model_quota_breach("usage limit exceeded: quota exhausted")
    saved_suppress = loop.suppress_exec
    loop.suppress_exec = lambda *_a, **_k: {"since": "fixture-window"}
    try:
        assert not loop.record_model_quota_if_breach(
            "guard", "T3", "minimax", "429 rate limit, retry", "adapter-quota")
        assert loop.record_model_quota_if_breach(
            "guard", "T3", "minimax", "quota exhausted", "adapter-quota")
    finally:
        loop.suppress_exec = saved_suppress

    # Daily CAS cap producer emits one idempotent event for repeated denied ticks.
    saved_fetch, saved_rev, saved_read = loop.fetch_refs, loop.rev_ref, loop.read_ref
    day = loop.now().strftime("%Y-%m-%d")
    loop.fetch_refs = lambda: True
    loop.rev_ref = lambda _ref: "f" * 40
    loop.read_ref = lambda _ref: "day=%s\nreservations=%s" % (
        day, ",".join(["1" * 20, "2" * 20]))
    try:
        for _ in range(3):
            ok, used, why = loop.reserve_daily_advance("guard", 2, task_id="T4")
            assert not ok and used == 2 and "calendar-day cap" in why
    finally:
        loop.fetch_refs, loop.rev_ref, loop.read_ref = saved_fetch, saved_rev, saved_read

    budget_rows = [json.loads(line) for line in
                   (state / "budget-incidents.jsonl").read_text().splitlines() if line]
    assert len([row for row in budget_rows if row["incident_type"] == "daily_cas_overage"]) == 1
    assert len([row for row in budget_rows if row["incident_type"] == "model_quota_breach"]) == 1

    # All three meters must fail closed: a bad id/enum/severity/timestamp/evidence
    # yields status=UNKNOWN and validate rc=1; break one field at a time, then restore the real ledger.
    destructive = {
        "cortex-authorization-incident.sh": (
            state / "authorization-incidents.jsonl",
            ["event_id", "incident_type", "severity", "timestamp", "evidence"],
        ),
        "cortex-independent-verification-incident.sh": (
            state / "independent-verification-incidents.jsonl",
            ["event_id", "incident_type", "verification_kind", "severity", "timestamp", "evidence"],
        ),
        "cortex-budget-incident.sh": (
            state / "budget-incidents.jsonl",
            ["event_id", "incident_type", "severity", "timestamp", "evidence"],
        ),
    }
    invalid = {
        "event_id": "forged-id", "incident_type": "not-an-enum",
        "verification_kind": "not-an-enum", "severity": "critical",
        "timestamp": "2026-99-99T99:99:99Z", "evidence": "",
    }
    for script, (path, fields) in destructive.items():
        original_text = path.read_text()
        valid_row = json.loads(next(line for line in original_text.splitlines() if line))
        for field in fields:
            corrupted = dict(valid_row)
            corrupted[field] = invalid[field]
            path.write_text(json.dumps(corrupted) + "\n")
            status = json.loads(run_atom(script, state, "status").stdout)
            assert status["state"] == "UNKNOWN" and status["observed_events"] is None, (script, field, status)
            checked = subprocess.run(
                ["bash", str(REPO / "bin" / script), "validate"],
                env=dict(os.environ), text=True, capture_output=True,
            )
            assert checked.returncode == 1, (script, field, checked.stdout, checked.stderr)
        path.write_text(original_text)
        run_atom(script, state, "validate")

print("guardrail production wiring: PASS")
