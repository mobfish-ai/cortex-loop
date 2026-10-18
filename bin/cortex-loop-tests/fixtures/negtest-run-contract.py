#!/usr/bin/env python3
"""run-contract-v1 positive projection and semantic-drift fail-closed checks."""
import hashlib
import contextlib
import importlib.machinery
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
from argparse import Namespace
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCHEMA = "cortex-loop/run-contract-v1"


def run(cmd, cwd, env=None, check=True):
    proc = subprocess.run(cmd, cwd=cwd, env=env, text=True,
                          capture_output=True, check=False)
    if check and proc.returncode != 0:
        raise AssertionError("command failed rc=%s\n%s\n%s" % (
            proc.returncode, proc.stdout, proc.stderr))
    return proc


def digest(value):
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True,
                     separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


with tempfile.TemporaryDirectory(prefix="cortex-run-contract-") as tmp:
    base = Path(tmp)
    repo = base / "repo"
    workspace = base / "workspace"
    (repo / "bin").mkdir(parents=True)
    (repo / "brain-network/directions/testline").mkdir(parents=True)
    (workspace / ".attempt").mkdir(parents=True)
    engine = repo / "bin/cortex-loop"
    cockpit = repo / "bin/control-plane-cockpit.py"
    shutil.copy2(ROOT / "bin/cortex-loop", engine)
    shutil.copy2(ROOT / "bin/control-plane-cockpit.py", cockpit)
    origin = base / "origin.git"
    run(["git", "init", "--bare", str(origin)], base)
    run(["git", "init"], repo)
    run(["git", "config", "user.email", "fixture@example.invalid"], repo)
    run(["git", "config", "user.name", "Cortex fixture"], repo)
    run(["git", "commit", "--allow-empty", "-m", "fixture base"], repo)
    run(["git", "remote", "add", "origin", str(origin)], repo)
    run(["git", "push", "origin", "HEAD:refs/heads/master"], repo)

    tasks = repo / "brain-network/directions/testline/TASKS.md"
    tasks.write_text(
        "| id | title | status | depends_on | success_criteria | failure_modes | "
        "artifact_paths | short_test | next_advance_after | updated_at | fails | evidence |\n"
        "|---|---|---|---|---|---|---|---|---|---|---|---|\n"
        "| T1 | contract fixture | running | - | frozen success | frozen failure | "
        "artifacts/result.md | test -f artifacts/result.md | - | 2026-08-23T18:00+0800 | 0 | - |\n",
        encoding="utf-8",
    )

    run_id = "fixture-run-001"
    attempt = "testline-T1-%s" % run_id
    writable = ["artifacts/result.md"]
    readable = ["bin/cortex-loop"]
    artifacts = ["artifacts/result.md"]
    short_test = "test -f artifacts/result.md"
    goal = {
        "title": "contract fixture",
        "success_criteria": "frozen success",
        "failure_modes": "frozen failure",
        "depends_on": "-",
    }
    contract = {
        "writable_paths": sorted(writable),
        "read_paths": sorted(readable),
        "artifact_paths": sorted(artifacts),
        "short_test": short_test,
    }
    claim = {
        "schema_version": "cortex-attempt/claim-v1",
        "attempt": attempt,
        "run_id": run_id,
        "line": "testline",
        "task": "T1",
        "contract_id": hashlib.sha256(
            (SCHEMA + "\0" + run_id).encode("utf-8")
        ).hexdigest()[:24],
        "goal_digest": digest(goal),
        "contract_digest": digest(contract),
        "executor": "acp-native:mmx-a",
        "writable_paths": writable,
        "read_paths": readable,
        "artifact_paths": artifacts,
        "short_test": short_test,
    }
    attempt_worktree = base / "attempt-worktree"
    candidate_root = workspace / ".candidate"
    integration_root = workspace / ".integration"
    (attempt_worktree / "artifacts").mkdir(parents=True)
    (attempt_worktree / "artifacts/result.md").write_text("fixture artifact\n", encoding="utf-8")
    candidate_root.mkdir()
    integration_root.mkdir()
    candidate_path = candidate_root / (attempt + ".json")
    integration_path = integration_root / (attempt + ".json")
    candidate_oid = "a" * 40
    landed_oid = "b" * 40
    claim.update({
        "worktree": str(attempt_worktree),
        "candidate_path": str(candidate_path),
        "integration_receipt": str(integration_path),
    })
    candidate_path.write_text(json.dumps({
        "status": "published", "attempt": attempt, "candidate_oid": candidate_oid,
        "candidate_ref": "refs/cortex/candidate/fixture",
    }), encoding="utf-8")
    integration_receipt = {
        "status": "landed", "attempt": attempt, "candidate_oid": candidate_oid,
        "landed_commit": landed_oid, "canonical_ref": "refs/heads/master",
    }
    integration_path.write_text(json.dumps(integration_receipt), encoding="utf-8")
    (workspace / ".attempt" / (attempt + ".claim.json")).write_text(
        json.dumps(claim), encoding="utf-8"
    )
    env = os.environ.copy()
    env.update({
        "CORTEX_WORKSPACE_ROOT": str(workspace),
        "CORTEX_NODE": "fixture",
        "CORTEX_LOOP_LOG": str(base / "loop.log"),
    })
    cli = run([
        sys.executable, str(engine), "run-contract", "--line", "testline",
        "--task", "T1", "--run-id", run_id,
    ], repo, env)
    cli_contract = json.loads(cli.stdout)
    assert cli_contract["schema_version"] == SCHEMA
    assert cli_contract["contract_id"] == claim["contract_id"]
    assert cli_contract["run_id"] == run_id
    assert cli_contract["executor"] == "acp-native:mmx-a"
    assert cli_contract["semantic_digest"] == digest(cli_contract["semantic"])

    api = run([
        sys.executable, str(engine), "api", "run-contract", "--caller", "fixture",
        "--line", "testline", "--task", "T1", "--run-id", run_id, "--no-fetch",
    ], repo, env)
    api_contract = json.loads(api.stdout)["run_contract"]
    assert api_contract["contract_id"] == cli_contract["contract_id"]
    assert api_contract["run_id"] == cli_contract["run_id"]
    assert api_contract["semantic"] == cli_contract["semantic"]
    assert api_contract["semantic_digest"] == cli_contract["semantic_digest"]
    assert api_contract["provenance"]["source_surface"] == "api"
    assert api_contract["provenance"]["identity_status"] == "IDENTITY_MISMATCH"

    # Live API reads must still calculate caller HAAS; they may not bypass the
    # authorization gate merely to avoid the per-ref git process storm.  The
    # run-contract path must instead place that calculation inside the bounded
    # read-only snapshot, which batch-prefetches result and incident payloads.
    loader = importlib.machinery.SourceFileLoader("cortexloop_run_contract", str(engine))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    loop = importlib.util.module_from_spec(spec)
    loader.exec_module(loop)
    result_ref = "%s/fixture/T1" % loop.RESULT_NS
    refs = {loop.RESULT_NS: [result_ref], loop.INCIDENT_NS: []}
    payloads = {
        result_ref: "node=fixture\ntask=T1\nstatus=done\nkind=self-fixed\n",
    }
    original_list = loop.list_refs
    original_batch = loop.read_refs_batch
    original_read = loop.read_ref
    original_contract = loop._read_run_contract
    batch_calls, reads = [], []

    def fake_list(namespace):
        if loop._REF_LIST_SNAPSHOT is not None and namespace in loop._REF_LIST_SNAPSHOT:
            values = loop._REF_LIST_SNAPSHOT[namespace]
        else:
            values = refs.get(namespace, [])
        return loop.ListRefsResult("ok" if values else "empty", values)

    def fake_batch(requested):
        batch_calls.append(list(requested))
        return {ref: payloads.get(ref, "") for ref in requested}

    def guarded_read(ref):
        reads.append(ref)
        assert loop._REF_SNAPSHOT is not None, "HAAS read escaped run-contract snapshot"
        payload = loop._REF_SNAPSHOT.get(ref, "")
        return loop.ReadRefResult("ok" if payload else "empty", payload)

    try:
        loop.list_refs = fake_list
        loop.read_refs_batch = fake_batch
        loop.read_ref = guarded_read
        loop._read_run_contract = lambda *unused, **unused_kw: {"fixture": "contract"}
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = loop.cmd_api(Namespace(
                verb="run-contract", caller="fixture", no_fetch=True,
                approved_by="", line="testline", task="T1", run_id=run_id,
            ))
        assert rc == 0
        assert json.loads(out.getvalue())["run_contract"] == {"fixture": "contract"}
        assert batch_calls == [[result_ref]]
        assert reads == [result_ref]
    finally:
        loop.list_refs = original_list
        loop.read_refs_batch = original_batch
        loop.read_ref = original_read
        loop._read_run_contract = original_contract

    # Mutating the frozen claim's paths without its digest is a semantic drift,
    # not a best-effort projection; the CLI must fail closed.
    claim["artifact_paths"] = ["artifacts/forged.md"]
    (workspace / ".attempt" / (attempt + ".claim.json")).write_text(
        json.dumps(claim), encoding="utf-8"
    )
    drift = run([
        sys.executable, str(engine), "run-contract", "--line", "testline",
        "--task", "T1", "--run-id", run_id,
    ], repo, env, check=False)
    assert drift.returncode == 1
    assert "FAIL_SEMANTIC_DRIFT" in drift.stdout

    # A landed candidate may release its attempt workspace.  Publish the
    # terminal contract, then prove fresh CLI/API/Cockpit readers with no
    # attempt claim all project the same immutable contract id and digest.
    claim["artifact_paths"] = artifacts
    (workspace / ".attempt" / (attempt + ".claim.json")).write_text(
        json.dumps(claim), encoding="utf-8"
    )
    tasks.write_text(
        tasks.read_text(encoding="utf-8").replace(
            "| T1 | contract fixture | running |",
            "| T1 | contract fixture | done |",
        ), encoding="utf-8"
    )
    # S0o race: integration is durable, but the attempt workspace has already
    # been released before the terminal ref is readable.  That must produce an
    # explicit pending projection, not `artifact_ok=false` as a terminal fact.
    held_worktree = base / "released-attempt-worktree"
    attempt_worktree.rename(held_worktree)
    pending_cli = json.loads(run([
        sys.executable, str(engine), "run-contract", "--line", "testline",
        "--task", "T1", "--run-id", run_id,
    ], repo, env).stdout)
    assert pending_cli["delivery"]["candidate_landed"] is True
    assert pending_cli["delivery"]["terminal_complete"] is False
    assert pending_cli["delivery"]["terminal_ref_pending"] is True
    assert pending_cli["delivery"]["stage"] == "terminal-ref-pending"
    assert pending_cli["delivery"]["artifact_ok"] is None
    attempt_worktree = held_worktree.rename(base / "attempt-worktree")
    claim["worktree"] = str(attempt_worktree)
    (workspace / ".attempt" / (attempt + ".claim.json")).write_text(
        json.dumps(claim), encoding="utf-8"
    )
    previous_workspace = os.environ.get("CORTEX_WORKSPACE_ROOT")
    os.environ["CORTEX_WORKSPACE_ROOT"] = str(workspace)
    try:
        terminal_task = loop._task_or_error("testline", "T1")
        terminal_task["_line"] = "testline"
        terminal_candidate = dict(claim)
        terminal_candidate.update({
            "candidate_oid": candidate_oid,
            "candidate_ref": "refs/cortex/candidate/fixture",
        })
        terminal_ok, terminal_ref = loop._publish_terminal_run_contract(
            terminal_candidate, terminal_task, integration_receipt)
    finally:
        if previous_workspace is None:
            os.environ.pop("CORTEX_WORKSPACE_ROOT", None)
        else:
            os.environ["CORTEX_WORKSPACE_ROOT"] = previous_workspace
    assert terminal_ok, terminal_ref
    assert terminal_ref.startswith(loop.RUN_CONTRACT_NS + "/testline/T1/")
    shutil.rmtree(attempt_worktree)

    reader_workspace = base / "reader-workspace"
    (reader_workspace / ".attempt").mkdir(parents=True)
    reader_env = dict(env, CORTEX_WORKSPACE_ROOT=str(reader_workspace))
    terminal_cli = json.loads(run([
        sys.executable, str(engine), "run-contract", "--line", "testline",
        "--task", "T1", "--run-id", run_id,
    ], repo, reader_env).stdout)
    terminal_api = json.loads(run([
        sys.executable, str(engine), "api", "run-contract", "--caller", "fixture",
        "--line", "testline", "--task", "T1", "--run-id", run_id, "--no-fetch",
    ], repo, reader_env).stdout)["run_contract"]
    terminal_cockpit = json.loads(run([
        sys.executable, str(cockpit), "contract", "--json", "--line", "testline",
        "--task", "T1", "--run-id", run_id, "--contract-id", claim["contract_id"],
    ], repo, reader_env).stdout)
    assert terminal_cli["delivery"]["terminal_complete"] is True
    assert terminal_cli["delivery"]["terminal_evidence"]["candidate_oid"] == candidate_oid
    assert terminal_api["contract_id"] == terminal_cli["contract_id"]
    assert terminal_api["semantic_digest"] == terminal_cli["semantic_digest"]
    assert terminal_cockpit["status"] == "VERIFIED"
    assert terminal_cockpit["contract_id"] == terminal_cli["contract_id"]
    assert terminal_cockpit["semantic_digest"] == terminal_cli["semantic_digest"]

print("PASS run-contract-v1: terminal-ref-pending FAIL_EXPECTED → terminal CLI/API/Cockpit PASS")
