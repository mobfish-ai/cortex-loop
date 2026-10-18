#!/usr/bin/env python3
"""Contract test for workspace/integration statistics without touching production state."""

import json
import os
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
INSPECT = ROOT / "bin" / "cortex-workspace-inspect.py"
BROKER = ROOT / "bin" / "cortex-workspace.sh"


with tempfile.TemporaryDirectory(prefix="cortex-workspace-observe-") as raw:
    root = Path(raw)
    workspace = root / "workspaces"
    repo = root / "repo"
    subprocess.run(["git", "init", "-q", "-b", "master", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "fixture"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "fixture@example.invalid"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "core.fsmonitor", "false"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "maintenance.auto", "false"], check=True)
    (repo / "a.txt").write_text("a\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "a.txt"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "seed"], check=True)
    base = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    env = dict(os.environ)
    env["CORTEX_WORKSPACE_REPO_ROOT"] = str(repo)
    env["CORTEX_WORKSPACE_ROOT"] = str(workspace)
    env["CORTEX_WORKSPACE_MIN_FREE_KB"] = "1"
    subprocess.run([
        str(BROKER), "create", "--attempt", "attempt-a", "--base", base,
        "--allow", "a.txt",
    ], env=env, check=True, stdout=subprocess.DEVNULL)
    owner = workspace / ".locks" / ".owner.dead.fixture"
    owner.mkdir(parents=True)
    (workspace / ".integration").mkdir()
    (workspace / ".candidate").mkdir()
    active = workspace / "attempt-a"
    (active / "a.txt").write_text("dirty\n", encoding="utf-8")
    (owner / "pid").write_text("99999999\n", encoding="utf-8")
    (owner / "hostname").write_text(os.uname().nodename + "\n", encoding="utf-8")
    (owner / "started_at").write_text("2026-08-01T00:00:00Z\n", encoding="utf-8")
    (owner / "token").write_text("fixture-token\n", encoding="utf-8")
    (workspace / ".locks" / "dead.lock").symlink_to(owner.name)
    receipt = {
        "schema_version": "cortex-integrator/receipt-v1", "status": "retryable_cas_conflict",
        "candidate_oid": "1" * 40, "base_oid": "0" * 40,
        "canonical_before": "2" * 40, "landed_commit": "3" * 40,
        "canonical_remote": "origin", "canonical_ref": "refs/heads/master",
        "allowed_paths": ["a.txt"], "short_test": "test -s a.txt",
        "detail": "fixture", "finished_at": "2026-08-01T00:00:00+00:00",
    }
    (workspace / ".integration" / "a.json").write_text(json.dumps(receipt), encoding="utf-8")
    candidate = {
        "schema_version": "cortex-candidate/receipt-v1", "status": "published",
        "attempt": "attempt-a", "candidate_oid": "1" * 40,
        "base_oid": "0" * 40, "remote": "origin",
        "candidate_ref": "refs/cortex/candidate/attempt-a/" + "1" * 40,
        "remote_oid": "1" * 40, "allowed_paths": ["a.txt"],
        "detail": "fixture", "finished_at": "2026-08-01T00:00:00+00:00",
    }
    (workspace / ".candidate" / "a.json").write_text(json.dumps(candidate), encoding="utf-8")
    env["CORTEX_INTEGRATION_RECEIPT_ROOT"] = str(workspace / ".integration")
    env["CORTEX_CANDIDATE_RECEIPT_ROOT"] = str(workspace / ".candidate")
    proc = subprocess.run([str(INSPECT), "--json"], env=env, text=True, capture_output=True)
    assert proc.returncode == 1, proc.stdout + proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["state"] == "ATTENTION"
    assert payload["summary"]["active"] == 1
    assert payload["summary"]["dirty_active"] == 1
    assert payload["summary"]["integration_states"]["retryable_cas_conflict"] == 1
    assert payload["summary"]["candidate_states"]["published"] == 1
    kinds = {item["kind"] for item in payload["problems"]}
    assert {"dirty_active_workspace", "stale_attempt_lock", "integration_retryable"} <= kinds

print("PASS workspace observability: dirty/stale/CAS retry statistics remain distinct")
