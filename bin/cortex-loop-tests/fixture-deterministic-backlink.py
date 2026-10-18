#!/usr/bin/env python3
"""Deterministic backlink uses the common isolated/canonical delivery plane."""

import importlib.machinery
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


ENGINE = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / "cortex-loop")
PROJECT = ENGINE.resolve().parent.parent
loader = importlib.machinery.SourceFileLoader("cl_backlink", str(ENGINE))
cl = importlib.util.module_from_spec(importlib.util.spec_from_loader("cl_backlink", loader))
loader.exec_module(cl)


def sh(*args, cwd, check=True):
    return subprocess.run(args, cwd=cwd, text=True, capture_output=True, check=check).stdout.strip()


with tempfile.TemporaryDirectory(prefix="cortex-backlink-") as raw:
    tmp = Path(raw)
    root, remote, workspaces = tmp / "repo", tmp / "origin.git", tmp / "workspaces"
    root.mkdir()
    sh("git", "init", "-q", "-b", "master", cwd=root)
    sh("git", "init", "--bare", "-q", str(remote), cwd=root)
    sh("git", "config", "user.name", "fixture", cwd=root)
    sh("git", "config", "user.email", "fixture@example.invalid", cwd=root)
    sh("git", "remote", "add", "origin", str(remote), cwd=root)
    sh("git", "--git-dir", str(remote), "config", "uploadpack.allowFilter", "true", cwd=root)
    (root / "skills/cortex-loop").mkdir(parents=True)
    (root / "skills/fixture").mkdir(parents=True)
    (root / "bin").mkdir()
    for name in ("cortex-workspace.sh", "cortex-candidate.sh", "cortex-integrator.sh",
                 "git-auto-commit.sh", "git-commit-transaction.sh", "git-sync-v4.sh"):
        shutil.copy2(PROJECT / "bin" / name, root / "bin" / name)
    hooks = root / "hooks"; hooks.mkdir()
    (hooks / "pre-commit").write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    (hooks / "pre-commit").chmod(0o755)
    sh("git", "config", "core.hooksPath", "hooks", cwd=root)
    (root / "skills/cortex-loop/MAP.md").write_text("# MAP\n\n[[target]]\n", encoding="utf-8")
    target = root / "skills/fixture/SKILL.md"
    target.write_text("# Target\n", encoding="utf-8")
    verifier = root / "bin/verify-backlinks.py"
    verifier.write_text(
        "import pathlib,sys\n"
        "p=pathlib.Path(sys.argv[2]).read_text()\n"
        "sys.exit(0 if '[[skills/cortex-loop/MAP' in p else 1)\n",
        encoding="utf-8")
    sh("git", "add", ".", cwd=root)
    sh("git", "-c", "core.hooksPath=/dev/null", "commit", "-qm", "fixture", cwd=root)
    sh("git", "push", "-q", "-u", "origin", "master", cwd=root)
    base = sh("git", "rev-parse", "HEAD", cwd=root)

    task = {
        "id": "map-backlink-fixture", "title": "fixture", "status": "pending",
        "bounds": "skills/fixture/SKILL.md",
        "artifact_paths": "skills/fixture/SKILL.md",
        "short_test": "python3 bin/verify-backlinks.py --check-target skills/fixture/SKILL.md skills/cortex-loop/MAP.md",
        "resource_class": "local-only",
    }
    saved_root = cl.ROOT
    old_env = {key: os.environ.get(key) for key in (
        "CORTEX_WORKSPACE_ROOT", "CORTEX_WORKSPACE_MIN_FREE_KB",
        "CORTEX_CANONICAL_PUSH_REF")}
    try:
        cl.ROOT = str(root)
        os.environ["CORTEX_WORKSPACE_ROOT"] = str(workspaces)
        os.environ["CORTEX_WORKSPACE_MIN_FREE_KB"] = "1"
        os.environ["CORTEX_CANONICAL_PUSH_REF"] = "refs/heads/master"
        ctx = cl.create_workspace_attempt("cortex-immune", task, "deterministic.backlink")
        code, detail = cl.apply_deterministic_backlink_in_workspace(ctx["worktree"], task)
        if code != 0:
            raise AssertionError(detail)
        candidate = cl.commit_workspace_candidate(ctx, task)
        integration_code, receipt = cl.run_workspace_integrator(candidate)
        if integration_code != 0 or receipt.get("status") != "landed":
            raise AssertionError(receipt)
        landed = receipt["landed_commit"]
        sh("git", "fetch", "-q", "origin", "master", cwd=root)
        ancestry = subprocess.run(
            ["git", "merge-base", "--is-ancestor", landed, "refs/remotes/origin/master"],
            cwd=root, capture_output=True, check=False)
        if ancestry.returncode != 0:
            raise AssertionError("canonical ancestry unavailable")
        remote_body = sh("git", "show", "origin/master:skills/fixture/SKILL.md", cwd=root)
        if "cortex:map-backlink map-backlink-fixture" not in remote_body:
            raise AssertionError("canonical artifact missing marker")
        if target.read_text(encoding="utf-8") != "# Target\n":
            raise AssertionError("root worktree was mutated")
        changed = sh("git", "diff-tree", "--no-commit-id", "--name-only", "-r", landed,
                     cwd=root).split()
        if changed != ["skills/fixture/SKILL.md"]:
            raise AssertionError("candidate escaped artifact: %r" % changed)
        if cl._release_workspace_attempt(candidate)[0] != 0:
            raise AssertionError("workspace release failed")
        # Refresh only the isolated fixture root, then prove the deterministic edit
        # is idempotent against the newly landed canonical base.
        sh("git", "reset", "--hard", "origin/master", cwd=root)
        ctx2 = cl.create_workspace_attempt("cortex-immune", task, "deterministic.backlink")
        code2, _ = cl.apply_deterministic_backlink_in_workspace(ctx2["worktree"], task)
        if code2 != 3:
            raise AssertionError("rerun was not idempotent: rc=%s" % code2)
        if cl._release_workspace_attempt(ctx2)[0] != 0:
            raise AssertionError("second workspace release failed")
        if base == landed:
            raise AssertionError("no canonical change produced")
    finally:
        cl.ROOT = saved_root
        for key, value in old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

print("fixture-deterministic-backlink: ALL PASS")
