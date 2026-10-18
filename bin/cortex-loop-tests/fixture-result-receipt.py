#!/usr/bin/env python3
"""B1 killer negative test: done must be a traceable run receipt, not a CLI or local illusion."""
import contextlib
import importlib.machinery
import importlib.util
import io
import os
from types import SimpleNamespace


ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
ENGINE = os.path.join(ROOT, "bin", "cortex-loop")
loader = importlib.machinery.SourceFileLoader("cortex_loop_receipt_fixture", ENGINE)
spec = importlib.util.spec_from_loader(loader.name, loader)
cl = importlib.util.module_from_spec(spec)
loader.exec_module(cl)


def check(label, ok, detail=""):
    if not ok:
        raise AssertionError("%s: %s" % (label, detail))
    print("  PASS %s" % label)


def forged_gather_must_fail():
    saved = {name: getattr(cl, name) for name in
             ("fetch_refs", "plan_tasks", "read_ref", "rev_ref")}
    try:
        cl.fetch_refs = lambda: True
        cl.plan_tasks = lambda _plan: [{"id": "T1"}]
        cl.rev_ref = lambda ref: "fixture-sha" if "/result/" in ref or "/claim/" in ref else ""
        cl.read_ref = lambda ref: (
            "task=T1\nnode=forger\nstatus=done\nartifact=x\nfinished=now"
            if "/result/" in ref else "holder=forger"
        )
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = cl.cmd_gather(SimpleNamespace(plan="forged", settle=False))
        check("forged done receipt blocks gather", rc == 1 and "receipt invalid" in buf.getvalue(),
              buf.getvalue())
    finally:
        for name, value in saved.items():
            setattr(cl, name, value)


def run_fixture(task, write_ref, origin_reachable=None, run_fn=None):
    names = ("fetch_refs", "node_profile", "node_id", "cmd_claim", "node_load", "plan_tasks",
             "rev_ref", "read_ref", "fit_score", "covenant_check", "run_adapter", "run",
             "inspection_mode", "verify_value", "haas_score", "write_ref", "artifact_origin_reachable")
    saved = {name: getattr(cl, name) for name in names}
    try:
        cl.fetch_refs = lambda: True
        cl.node_profile = lambda: {"node": "node-a", "executors": "mock"}
        cl.node_id = lambda: "node-a"
        cl.cmd_claim = lambda _args: 0
        cl.node_load = lambda _node: 0
        cl.plan_tasks = lambda _plan: [task]
        cl.rev_ref = lambda ref: "claim-sha" if "/claim/" in ref else ""
        cl.read_ref = lambda ref: "holder=node-a\nsince=2026-07-30T00:00\nexpires=2099-01-01T00:00" if "/claim/" in ref else ""
        cl.fit_score = lambda *_args: (1, "ok")
        cl.covenant_check = lambda *_args: (True, "", "")
        cl.run_adapter = lambda *_args, **_kwargs: "execution text cannot directly become done"
        cl.run = run_fn or (lambda command, **_kwargs: (0, "commit") if "git log -1 --oneline" in command else (0, ""))
        cl.inspection_mode = lambda _node: ("exempt", False, False)
        cl.verify_value = lambda *_args: ("V1", "")
        cl.haas_score = lambda _node: (0.9, {})
        cl.write_ref = write_ref
        if origin_reachable is not None:
            cl.artifact_origin_reachable = origin_reachable
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            cl.cmd_run(SimpleNamespace(plan="p1", executor="mock", max_load=3, ttl_min=60, limit=0))
        return buf.getvalue(), cl.cmd_run.last_progress
    finally:
        for name, value in saved.items():
            setattr(cl, name, value)


def result_write_failure_is_unknown():
    task = {"id": "T1", "source": "fixture", "bounds": "-", "artifact": "-",
            "short_test": "true", "weight": "1", "title": "fixture"}
    calls = {"short_test": 0}
    def run_fn(command, **_kwargs):
        if "&& true" in command:
            calls["short_test"] += 1
            return (1, "not yet") if calls["short_test"] == 1 else (0, "")
        return 0, ""
    def write_ref(ref, *_args, **_kwargs):
        return (True, "claim-sha") if "/claim/" in ref else (False, "ERROR")
    out, progress = run_fixture(task, write_ref, run_fn=run_fn)
    check("result ref write failure does not progress", progress == 0 and "receipt was not written" in out
          and "-> done" not in out, out)


def successful_receipt_carries_world_evidence():
    task = {"id": "T-world", "source": "fixture", "bounds": "-", "artifact": "-",
            "short_test": "true", "weight": "1", "title": "fixture"}
    payloads, calls = [], {"short_test": 0}
    def run_fn(command, **_kwargs):
        if "&& true" in command:
            calls["short_test"] += 1
            return (1, "work remains") if calls["short_test"] == 1 else (0, "")
        return 0, ""
    out, progress = run_fixture(
        task,
        lambda ref, payload, **_kwargs: ((True, "claim-sha") if "/claim/" in ref
                                          else (payloads.append(payload) or True, "sha")),
        run_fn=run_fn,
    )
    receipt = payloads[0] if payloads else ""
    check("done receipt writes replayable world evidence",
          progress == 1 and "-> done" in out and "verification_command=true" in receipt
          and "world_verified_at=-" not in receipt and "world_verified_at=20" in receipt,
          receipt or out)


def local_only_artifact_must_fail():
    task = {"id": "T2", "source": "fixture", "bounds": "artifacts/", "artifact": "artifacts/x.md",
            "short_test": "true", "weight": "1", "title": "fixture"}
    saved_os = (cl.os.path.exists, cl.os.path.isfile, cl.os.path.getsize)
    payloads = []
    calls = {"short_test": 0}
    def run_fn(command, **_kwargs):
        if "&& true" in command:
            calls["short_test"] += 1
            return (1, "not yet") if calls["short_test"] == 1 else (0, "")
        if "git log -1 --oneline" in command:
            return 0, "commit"
        return 0, ""
    try:
        cl.os.path.exists = lambda _path: True
        cl.os.path.isfile = lambda _path: True
        cl.os.path.getsize = lambda _path: 1
        out, progress = run_fixture(
            task,
            lambda ref, payload, **_kwargs: ((True, "claim-sha") if "/claim/" in ref
                                               else (payloads.append(payload) or True, "sha")),
            lambda _artifact: (False, "artifact commit is not yet in origin reachable history"),
            run_fn,
        )
    finally:
        cl.os.path.exists, cl.os.path.isfile, cl.os.path.getsize = saved_os
    check("legacy root-worktree artifact cannot pass", progress == 0
          and "legacy_plan_requires_workspace_migration" in out
          and payloads and "status=failed" in payloads[0]
          and "gate=workspace-required" in payloads[0], out)


def direct_result_is_rejected():
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = cl.cmd_result(SimpleNamespace(plan="p", task="T", status="done", artifact="-"))
    check("direct result done is rejected", rc == 2 and "refusing a direct result" in buf.getvalue(), buf.getvalue())


def plan_source_is_preserved():
    saved = cl.read_ref
    try:
        cl.read_ref = lambda _ref: (
            "task\tT1\ttitle\texec.claude\tskills/\tL1\tyes\tV1\t1\t-\ttrue\t-\tscanner"
        )
        tasks = cl.plan_tasks("p")
        check("candidate source survives plan parsing", len(tasks) == 1 and tasks[0].get("source") == "scanner",
              repr(tasks))
    finally:
        cl.read_ref = saved


def auto_plan_source_is_preserved():
    candidate = {
        "id": "IMM-T1", "title": "auto", "requires": "exec.mock", "bounds": "skills/",
        "min_trust": "L1", "reversible": "yes", "value": "V1", "weight": "1",
        "artifact": "-", "short_test": "true", "approved_by": "-",
        "source": "auto-immune-scanner",
    }
    line = cl.plan_task_line(candidate)
    saved = cl.read_ref
    try:
        cl.read_ref = lambda _ref: line
        tasks = cl.plan_tasks("imm-fixture")
        source = open(ENGINE, encoding="utf-8").read()
        tick_start = source.index('pid = "imm-')
        tick_end = source.index('payload = "\\n".join([', tick_start)
        check("auto immune task source survives tick encoding",
              len(tasks) == 1 and tasks[0].get("source") == "auto-immune-scanner"
              and "lines = [plan_task_line(c) for c in take]" in source[tick_start:tick_end],
              repr(tasks))
    finally:
        cl.read_ref = saved


def valid_receipt(**overrides):
    receipt = {
        "receipt": "run-v1", "plan": "p", "candidate": "T", "candidate_source": "fixture",
        "claim_holder": "node-a", "claim_since": "2026-07-30T00:00", "executor": "mock",
        "gate": "passed", "status": "done", "artifact": "-", "verification_command": "true",
        "world_verified_at": "2026-07-30T00:01", "trigger_kind": "manual",
    }
    receipt.update(overrides)
    return receipt


def incomplete_world_receipts_are_rejected():
    valid, why = cl.receipt_valid(valid_receipt(artifact="artifacts/x.md"), "p", "T")
    check("file receipt without origin commit is rejected", not valid and "origin_commit" in why, why)
    valid, why = cl.receipt_valid(valid_receipt(world_verified_at="-"), "p", "T")
    check("artifact dash receipt without world verification is rejected",
          not valid and "world_verified_at" in why, why)


def gather_rechecks_current_origin():
    saved = {name: getattr(cl, name) for name in
             ("fetch_refs", "plan_tasks", "read_ref", "rev_ref",
              "commit_origin_reachable")}
    try:
        cl.fetch_refs = lambda: True
        cl.plan_tasks = lambda _plan: [{"id": "T"}]
        cl.rev_ref = lambda ref: "fixture-sha" if "/result/" in ref or "/claim/" in ref else ""
        receipt = valid_receipt(artifact="artifacts/x.md", origin_commit="a" * 40)
        cl.read_ref = lambda ref: ("\n".join("%s=%s" % item for item in receipt.items())
                                   if "/result/" in ref else "holder=node-a")
        cl.commit_origin_reachable = lambda _commit: (False, "origin UNKNOWN: offline")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = cl.cmd_gather(SimpleNamespace(plan="p", settle=True))
        check("gather refuses file receipt when origin recheck is unknown",
              rc == 1 and "origin UNKNOWN" in buf.getvalue(), buf.getvalue())
    finally:
        for name, value in saved.items():
            setattr(cl, name, value)


direct_result_is_rejected()
plan_source_is_preserved()
auto_plan_source_is_preserved()
incomplete_world_receipts_are_rejected()
forged_gather_must_fail()
gather_rechecks_current_origin()
result_write_failure_is_unknown()
successful_receipt_carries_world_evidence()
local_only_artifact_must_fail()
print("fixture-result-receipt: ALL PASS")
