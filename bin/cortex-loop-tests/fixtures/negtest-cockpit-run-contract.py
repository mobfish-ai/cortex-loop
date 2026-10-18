#!/usr/bin/env python3
"""Cockpit binding positive and board-only/stale fail-closed checks."""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
RUN_SCHEMA = "cortex-loop/run-contract-v1"


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


with tempfile.TemporaryDirectory(prefix="cortex-cockpit-binding-") as tmp:
    base = Path(tmp)
    repo = base / "repo"
    workspace = base / "workspace"
    (repo / "bin").mkdir(parents=True)
    (repo / "brain-network/directions/testline").mkdir(parents=True)
    (repo / "brain-network/agents/alfred/topics/cso/evidence").mkdir(parents=True)
    (workspace / ".attempt").mkdir(parents=True)
    engine = repo / "bin/cortex-loop"
    cockpit = repo / "bin/control-plane-cockpit.py"
    shutil.copy2(ROOT / "bin/cortex-loop", engine)
    shutil.copy2(ROOT / "bin/control-plane-cockpit.py", cockpit)

    (repo / "brain-network/agents/alfred/topics/cso/CONTROL-BOARD.md").write_text(
        "control_plane_id: alfred-cso\n\n### 窗口清单\n",
        encoding="utf-8",
    )
    (repo / "brain-network/agents/alfred/topics/cso/evidence/EMPTY-QUEUE.jsonl").write_text(
        "", encoding="utf-8"
    )
    (repo / "brain-network/directions/testline/TASKS.md").write_text(
        "| id | title | status | depends_on | success_criteria | failure_modes | "
        "artifact_paths | short_test | next_advance_after | updated_at | fails | evidence |\n"
        "|---|---|---|---|---|---|---|---|---|---|---|---|\n"
        "| T1 | cockpit fixture | running | - | frozen success | frozen failure | "
        "artifacts/result.md | test -f artifacts/result.md | - | 2026-08-23T19:00+0800 | 0 | - |\n",
        encoding="utf-8",
    )

    run_id = "cockpit-run-001"
    attempt = "testline-T1-%s" % run_id
    writable = ["artifacts/result.md"]
    readable = ["bin/cortex-loop"]
    artifacts = ["artifacts/result.md"]
    short_test = "test -f artifacts/result.md"
    goal = {
        "title": "cockpit fixture",
        "success_criteria": "frozen success",
        "failure_modes": "frozen failure",
        "depends_on": "-",
    }
    contract = {
        "writable_paths": writable,
        "read_paths": readable,
        "artifact_paths": artifacts,
        "short_test": short_test,
    }
    claim = {
        "schema_version": "cortex-attempt/claim-v1",
        "attempt": attempt,
        "run_id": run_id,
        "line": "testline",
        "task": "T1",
        "contract_id": hashlib.sha256(
            (RUN_SCHEMA + "\0" + run_id).encode("utf-8")
        ).hexdigest()[:24],
        "goal_digest": digest(goal),
        "contract_digest": digest(contract),
        "executor": "acp-native:mmx-a",
        "writable_paths": writable,
        "read_paths": readable,
        "artifact_paths": artifacts,
        "short_test": short_test,
    }
    (workspace / ".attempt" / (attempt + ".claim.json")).write_text(
        json.dumps(claim), encoding="utf-8"
    )
    env = os.environ.copy()
    env.update({
        "CORTEX_WORKSPACE_ROOT": str(workspace),
        "CORTEX_NODE": "fixture",
        "CORTEX_LOOP_LOG": str(base / "loop.log"),
    })

    canonical = json.loads(run([
        sys.executable, str(engine), "run-contract", "--line", "testline",
        "--task", "T1", "--run-id", run_id,
    ], repo, env).stdout)
    expected_id = claim["contract_id"]

    positive = run([
        sys.executable, str(cockpit), "contract", "--json", "--line", "testline",
        "--task", "T1", "--run-id", run_id, "--contract-id", expected_id,
    ], repo, env)
    binding = json.loads(positive.stdout)
    assert binding["status"] == "VERIFIED"
    assert binding["contract_id"] == canonical["contract_id"]
    assert binding["semantic_digest"] == canonical["semantic_digest"]

    board_only = run([
        sys.executable, str(cockpit), "contract", "--json",
    ], repo, env, check=False)
    board_binding = json.loads(board_only.stdout)
    assert board_only.returncode == 1
    assert board_binding["status"] == "FAIL_UNBOUND"
    assert board_binding["reason"] == "board_only"

    stale = run([
        sys.executable, str(cockpit), "contract", "--json", "--line", "testline",
        "--task", "T1", "--run-id", run_id, "--contract-id", "stale-contract-id",
    ], repo, env, check=False)
    stale_binding = json.loads(stale.stdout)
    assert stale.returncode == 1
    assert stale_binding["status"] == "FAIL_UNBOUND"
    assert stale_binding["reason"] == "stale_binding"

    board = run([
        sys.executable, str(cockpit), "tree", "--json", "--plane", "alfred-cso",
    ], repo, env)
    assert json.loads(board.stdout)["run_contract_binding"]["status"] == "FAIL_UNBOUND"

    board_audit = run([
        sys.executable, str(cockpit), "bind", "--json", "--strict", "--plane", "alfred-cso",
    ], repo, env, check=False)
    assert board_audit.returncode == 1
    assert json.loads(board_audit.stdout)["ok"] is False

print("PASS Cockpit run-contract binding: digest equality + board-only/stale FAIL_EXPECTED")
