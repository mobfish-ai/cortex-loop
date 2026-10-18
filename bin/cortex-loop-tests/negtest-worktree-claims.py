#!/usr/bin/env python3
"""Claim/reclaim contract: claims and dirt block; clean release preserves branch."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path


DOCTOR = Path(__file__).resolve().parents[1] / "git-worktree-doctor.py"


def run(args: list[str], env: dict[str, str], cwd: Path | None = None, ok: int | None = 0) -> subprocess.CompletedProcess:
    proc = subprocess.run(args, cwd=cwd, env=env, text=True, capture_output=True, check=False)
    if ok is not None and proc.returncode != ok:
        raise AssertionError(f"rc={proc.returncode} stdout={proc.stdout} stderr={proc.stderr}")
    return proc


with tempfile.TemporaryDirectory(prefix="cortex-worktree-claims-") as raw:
    base = Path(raw)
    repo = base / "repo"
    parent = base / "managed"
    repo.mkdir(); parent.mkdir()
    run(["git", "init", "-q", "-b", "master"], os.environ.copy(), repo)
    run(["git", "config", "user.name", "fixture"], os.environ.copy(), repo)
    run(["git", "config", "user.email", "fixture@example.invalid"], os.environ.copy(), repo)
    (repo / "seed.txt").write_text("seed\n", encoding="utf-8")
    run(["git", "add", "seed.txt"], os.environ.copy(), repo)
    run(["git", "commit", "-q", "-m", "seed"], os.environ.copy(), repo)
    clean = parent / "clean"
    dirty = parent / "dirty"
    run(["git", "worktree", "add", "-q", "-b", "clean-branch", str(clean)], os.environ.copy(), repo)
    run(["git", "worktree", "add", "-q", "-b", "dirty-branch", str(dirty)], os.environ.copy(), repo)
    (dirty / "dirty.txt").write_text("keep\n", encoding="utf-8")
    receipt_root = parent / ".receipts"
    receipt_root.mkdir()
    (receipt_root / "clean.json").write_text(json.dumps({
        "schema_version": "cortex.lean-worktree-receipt/v1", "target": str(clean.resolve()),
        "state": "completed", "active": False, "receipt_finalized_at": "2026-01-01T00:00:00Z",
        "thin_worktree": True, "workspace_bytes": 1024, "sparse_patterns": ["/seed.txt"],
        "cache_policy": {"mode": "none", "paths": [], "read_only": True},
    }), encoding="utf-8")
    env = os.environ.copy()
    env["CORTEX_REPO_ROOT"] = str(repo)
    env["CORTEX_WORKTREE_TEST_NO_PROCESS_SCAN"] = "1"
    common = [str(DOCTOR), "--worktree-parent", str(parent), "--canonical", "master"]
    claimed = run(["python3", *common, "--claim", str(clean), "--owner", "fixture", "--task", "T1"], env)
    assert json.loads(claimed.stdout)["owner"] == "fixture"
    refused = run(["python3", *common, "--reclaim", str(clean)], env, ok=None)
    assert refused.returncode == 3 and "claimed_by=fixture" in refused.stdout
    run(["python3", *common, "--release-claim", str(clean), "--owner", "fixture"], env)
    reclaimed = run(["python3", *common, "--reclaim", str(clean)], env)
    result = json.loads(reclaimed.stdout)
    assert result["state"] == "RECLAIMED" and result["branch_preserved"] == "clean-branch"
    assert not clean.exists()
    assert run(["git", "show-ref", "--verify", "refs/heads/clean-branch"], env, repo).returncode == 0
    dirty_refused = run(["python3", *common, "--reclaim", str(dirty)], env, ok=None)
    assert dirty_refused.returncode == 3 and "dirty_count=1" in dirty_refused.stdout

print("PASS: worktree claim/reclaim contract")
