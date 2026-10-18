#!/usr/bin/env python3
"""Negative test of completion semantics: a visible candidate is not canonical master landed."""
import argparse
import importlib.machinery
import importlib.util
import os
import subprocess
import tempfile
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[3]
loader = importlib.machinery.SourceFileLoader(
    "cortex_loop_master_landed_fixture", str(PROJECT / "bin/cortex-loop"))
spec = importlib.util.spec_from_loader(loader.name, loader)
loop = importlib.util.module_from_spec(spec)
loader.exec_module(loop)


def git(repo, *args):
    result = subprocess.run(
        ["git", "-C", str(repo), *args], text=True, capture_output=True, check=True)
    return result.stdout.strip()


with tempfile.TemporaryDirectory(prefix="cortex-master-landed-") as tmp:
    base = Path(tmp)
    origin = base / "origin.git"
    repo = base / "repo"
    subprocess.run(["git", "init", "--bare", str(origin)], check=True,
                   text=True, capture_output=True)
    subprocess.run(["git", "init", str(repo)], check=True,
                   text=True, capture_output=True)
    git(repo, "config", "user.name", "Cortex Fixture")
    git(repo, "config", "user.email", "cortex-fixture@example.invalid")
    git(repo, "checkout", "-b", "master")
    git(repo, "remote", "add", "origin", str(origin))

    tasks_dir = repo / "brain-network/directions/landing"
    reports = repo / "reports"
    tasks_dir.mkdir(parents=True)
    reports.mkdir()
    tasks = tasks_dir / "TASKS.md"
    tasks.write_text(
        "| id | title | status | depends_on | success_criteria | failure_modes | "
        "artifact_paths | short_test | next_advance_after | fails | updated_at | "
        "evidence | leverage | cost_estimate | resource_class |\n"
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|\n"
        "| T1 | canonical landing | pending | - | delivered | candidate only | "
        "reports/result.md | test -s reports/result.md | - | 0 | - | - | high | S | local-only |\n"
    )
    git(repo, "add", "brain-network/directions/landing/TASKS.md")
    git(repo, "commit", "-m", "fixture canonical baseline")
    master_before = git(repo, "rev-parse", "HEAD")
    git(repo, "push", "-u", "origin", "master:master")

    git(repo, "checkout", "-b", "candidate")
    (reports / "result.md").write_text("candidate output\n")
    git(repo, "add", "reports/result.md")
    git(repo, "commit", "-m", "candidate artifact")
    candidate_oid = git(repo, "rev-parse", "HEAD")
    git(repo, "push", "-u", "origin", "candidate:candidate")
    git(repo, "fetch", "origin", "+refs/heads/*:refs/remotes/origin/*")

    saved = {
        "root": loop.ROOT,
        "directions": loop.DIRECTIONS,
        "failure_state": loop.FAILURE_STATE,
        "land": loop.land_task_artifacts,
        "credit": loop.auto_credit_decided,
        "canonical_ref": os.environ.get("CORTEX_CANONICAL_REF"),
    }
    try:
        loop.ROOT = str(repo)
        loop.DIRECTIONS = str(repo / "brain-network/directions")
        loop.FAILURE_STATE = str(repo / ".git/cortex-loop-state/failures.json")
        loop.land_task_artifacts = lambda *_args, **_kwargs: (True, "fixture bypass")
        loop.auto_credit_decided = lambda *_args, **_kwargs: None
        os.environ["CORTEX_CANONICAL_REF"] = "refs/remotes/origin/master"
        args = argparse.Namespace(line="landing", task="T1", judge=False)

        visible, _ = loop.commit_origin_reachable(candidate_oid)
        assert visible, "fixture invalid: candidate should already be reachable on origin/candidate"
        assert loop.cmd_try_complete(args) == 0
        assert loop._task_or_error("landing", "T1")["status"] == "settling"
        pending = loop.cmd_try_complete.last_failure
        assert pending["stage"] == "artifact-land-deferred", pending
        assert pending["delivery_stage"] == "integration-pending", pending
        assert pending["candidate_oid"] == candidate_oid, pending
        assert pending["landed_oid"] == master_before, pending

        # The completion gate allows done only after that same candidate is actually on canonical master.
        git(repo, "push", "origin", "candidate:master")
        git(repo, "fetch", "origin", "+refs/heads/master:refs/remotes/origin/master")
        assert loop.cmd_try_complete(args) == 0
        assert loop._task_or_error("landing", "T1")["status"] == "done"
        delivery = loop.cmd_try_complete.last_delivery[0]
        assert delivery["stage"] == "canonical-landed", delivery
        assert delivery["proof"] == "worktree-content-equivalent", delivery
        assert delivery["rc"] == 0, delivery
        landed = git(repo, "rev-parse", "refs/remotes/origin/master")
        assert delivery["landed_oid"] == landed, delivery
        # This proof matches the worktree blob to canonical. It does not
        # require the delivery record to repeat the pre-image candidate oid.
        assert delivery.get("candidate_oid", "") in ("", candidate_oid), delivery
        receipt = loop.parse_kv(loop.run_receipt_payload(
            "landing-plan", {"id": "T1", "source": "fixture",
                             "artifact": "reports/result.md", "short_test": "true"},
            {"holder": "fixture", "since": "2026-08-01T00:00+0800"},
            "fixture", "done", "passed", origin_commit=candidate_oid,
            candidate_oid=delivery.get("candidate_oid") or "",
            landed_oid=delivery["landed_oid"],
            world_verified_at="2026-08-01T00:01+0800"))
        assert receipt["landed_oid"] == delivery["landed_oid"], receipt
        assert receipt["origin_commit"] == candidate_oid, receipt
        # An empty delivery candidate_oid falls back to the caller-supplied
        # origin commit so the receipt still names a real commit.
        assert receipt["candidate_oid"] == (delivery.get("candidate_oid") or candidate_oid), receipt
    finally:
        loop.ROOT = saved["root"]
        loop.DIRECTIONS = saved["directions"]
        loop.FAILURE_STATE = saved["failure_state"]
        loop.land_task_artifacts = saved["land"]
        loop.auto_credit_decided = saved["credit"]
        if saved["canonical_ref"] is None:
            os.environ.pop("CORTEX_CANONICAL_REF", None)
        else:
            os.environ["CORTEX_CANONICAL_REF"] = saved["canonical_ref"]

# An old local fixture with no origin can only opt in explicitly; the same repo with the switch off must fail closed.
with tempfile.TemporaryDirectory(prefix="cortex-no-origin-") as tmp:
    repo = Path(tmp)
    subprocess.run(["git", "init", str(repo)], check=True,
                   text=True, capture_output=True)
    git(repo, "config", "user.name", "Cortex Fixture")
    git(repo, "config", "user.email", "cortex-fixture@example.invalid")
    (repo / "artifact.md").write_text("local fixture\n")
    git(repo, "add", "artifact.md")
    git(repo, "commit", "-m", "fixture local commit")
    oid = git(repo, "rev-parse", "HEAD")
    saved_root = loop.ROOT
    saved_allow = os.environ.get("CORTEX_ALLOW_NO_ORIGIN_FIXTURE")
    saved_ref = os.environ.get("CORTEX_CANONICAL_REF")
    try:
        loop.ROOT = str(repo)
        os.environ.pop("CORTEX_ALLOW_NO_ORIGIN_FIXTURE", None)
        os.environ.pop("CORTEX_CANONICAL_REF", None)
        assert not loop.commit_canonical_landed(oid)[0]
        os.environ["CORTEX_ALLOW_NO_ORIGIN_FIXTURE"] = "1"
        os.environ["CORTEX_CANONICAL_REF"] = "HEAD"
        landed, binding = loop.commit_canonical_landed(oid)
        assert landed and binding["candidate_oid"] == binding["landed_oid"] == oid
    finally:
        loop.ROOT = saved_root
        if saved_allow is None:
            os.environ.pop("CORTEX_ALLOW_NO_ORIGIN_FIXTURE", None)
        else:
            os.environ["CORTEX_ALLOW_NO_ORIGIN_FIXTURE"] = saved_allow
        if saved_ref is None:
            os.environ.pop("CORTEX_CANONICAL_REF", None)
        else:
            os.environ["CORTEX_CANONICAL_REF"] = saved_ref

print("negtest-master-landed: PASS")
