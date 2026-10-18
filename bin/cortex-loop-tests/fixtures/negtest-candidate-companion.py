#!/usr/bin/env python3
"""Candidate companion fail-closed and run-contract delivery-state checks."""

import hashlib
import importlib.machinery
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
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
    return hashlib.sha256(json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")).hexdigest()


with tempfile.TemporaryDirectory(prefix="cortex-candidate-companion-") as tmp:
    base = Path(tmp)
    repo = base / "repo"
    workspace = base / "workspace"
    (repo / "bin").mkdir(parents=True)
    (repo / "brain-network/directions/testline").mkdir(parents=True)
    (workspace / ".attempt").mkdir(parents=True)
    (workspace / ".candidate").mkdir(parents=True)
    (workspace / ".integration").mkdir(parents=True)

    engine = repo / "bin/cortex-loop"
    preflight = repo / "bin/git-commit-preflight.py"
    shutil.copy2(ROOT / "bin/cortex-loop", engine)
    shutil.copy2(ROOT / "bin/git-commit-preflight.py", preflight)
    shutil.copy2(ROOT / "bin/claim-count-gate.sh", repo / "bin/claim-count-gate.sh")
    shutil.copy2(ROOT / "bin/verify-frontmatter.py", repo / "bin/verify-frontmatter.py")
    shutil.copy2(ROOT / "bin/verify-skill-integration.sh", repo / "bin/verify-skill-integration.sh")

    run(["git", "init", "-q"], repo)
    run(["git", "config", "user.email", "fixture@example.invalid"], repo)
    run(["git", "config", "user.name", "fixture"], repo)
    hook = repo / "hooks/pre-commit"
    hook.parent.mkdir(parents=True)
    hook.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    hook.chmod(0o755)
    run(["git", "config", "core.hooksPath", "hooks"], repo)
    skill = repo / "skills/demo/SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("# demo\n", encoding="utf-8")
    run(["git", "add", "hooks/pre-commit", "skills/demo/SKILL.md"], repo)
    run(["git", "commit", "-qm", "fixture base"], repo)
    skill.write_text("# demo\nchanged\n", encoding="utf-8")

    missing = run([
        sys.executable, str(preflight), "--cwd", str(repo),
        "skills/demo/SKILL.md",
    ], repo, check=False)
    # THOV pairing is globally paused. The failure-closed negative for a
    # placeholder companion is asserted below through the active quality and
    # report-governance gates instead of this admission-only preflight.
    assert missing.returncode == 0

    report = repo / "reports/2026-08-24/demo.md"
    report.parent.mkdir(parents=True)
    report.write_text("companion\n", encoding="utf-8")
    paired = run([
        sys.executable, str(preflight), "--cwd", str(repo),
        "skills/demo/SKILL.md", "reports/2026-08-24/demo.md",
    ], repo)
    assert paired.returncode == 0

    docs = repo / "docs/change.md"
    docs.parent.mkdir(parents=True)
    docs.write_text("non-impact\n", encoding="utf-8")
    ordinary = run([
        sys.executable, str(preflight), "--cwd", str(repo), "docs/change.md",
    ], repo)
    assert ordinary.returncode == 0

    task = repo / "brain-network/directions/testline/TASKS.md"
    task.write_text(
        "| id | title | status | depends_on | success_criteria | failure_modes | "
        "artifact_paths | short_test | next_advance_after | updated_at | fails | evidence |\n"
        "|---|---|---|---|---|---|---|---|---|---|---|---|\n"
        "| T1 | companion fixture | pending | - | success | failure | "
        "artifacts/result.md | test -f artifacts/result.md | - | "
        "2026-08-24T08:00+0800 | 1 | - |\n",
        encoding="utf-8",
    )
    run_id = "companion-run-001"
    attempt = "testline-T1-%s" % run_id
    attempt_worktree = workspace / attempt
    (attempt_worktree / "artifacts").mkdir(parents=True)
    (attempt_worktree / "artifacts/result.md").write_text("host: fixture\n", encoding="utf-8")
    claim = {
        "schema_version": "cortex-attempt/claim-v1",
        "attempt": attempt,
        "run_id": run_id,
        "line": "testline",
        "task": "T1",
        "contract_id": hashlib.sha256((SCHEMA + "\0" + run_id).encode()).hexdigest()[:24],
        "goal_digest": digest({
            "title": "companion fixture", "success_criteria": "success",
            "failure_modes": "failure", "depends_on": "-",
        }),
        "contract_digest": digest({
            "writable_paths": ["artifacts/result.md"], "read_paths": [],
            "artifact_paths": ["artifacts/result.md"],
            "short_test": "test -f artifacts/result.md",
        }),
        "executor": "acp-native:mmx-a",
        "writable_paths": ["artifacts/result.md"],
        "read_paths": [],
        "artifact_paths": ["artifacts/result.md"],
        "short_test": "test -f artifacts/result.md",
        "worktree": str(attempt_worktree),
        "candidate_path": str(workspace / ".candidate" / (attempt + ".json")),
        "integration_receipt": str(workspace / ".integration" / (attempt + ".json")),
    }
    (workspace / ".attempt" / (attempt + ".claim.json")).write_text(
        json.dumps(claim), encoding="utf-8"
    )
    (workspace / ".attempt" / (attempt + ".events.jsonl")).write_text(
        json.dumps({
            "machine_blocker": "MACHINE_BLOCKER: candidate requires companion",
            "candidate_landed": False,
        }) + "\n", encoding="utf-8"
    )
    env = os.environ.copy()
    env.update({"CORTEX_WORKSPACE_ROOT": str(workspace), "CORTEX_LOOP_LOG": str(base / "loop.log")})
    os.environ.update({"CORTEX_WORKSPACE_ROOT": str(workspace), "CORTEX_LOOP_LOG": str(base / "loop.log")})
    pending = json.loads(run([
        sys.executable, str(engine), "run-contract", "--line", "testline",
        "--task", "T1", "--run-id", run_id,
    ], repo, env).stdout)
    assert pending["delivery"] == {
        "artifact_ok": True,
        "candidate_landed": False,
        "terminal_complete": False,
        "stage": "artifact-ok",
        "terminal_ref_pending": False,
        "machine_blocker": "MACHINE_BLOCKER: candidate requires companion",
        "candidate_oid": "",
        "integration_status": "",
    }, pending["delivery"]

    Path(claim["candidate_path"]).write_text(json.dumps({
        "status": "published", "candidate_oid": "a" * 40,
        "candidate_ref": "refs/cortex/candidate/testline/%s" % attempt,
    }), encoding="utf-8")
    Path(claim["integration_receipt"]).write_text(json.dumps({"status": "landed"}), encoding="utf-8")
    task.write_text(task.read_text(encoding="utf-8").replace("| T1 | companion fixture | pending |", "| T1 | companion fixture | done |"), encoding="utf-8")
    done = json.loads(run([
        sys.executable, str(engine), "run-contract", "--line", "testline",
        "--task", "T1", "--run-id", run_id,
    ], repo, env).stdout)
    assert done["delivery"]["artifact_ok"] is True
    assert done["delivery"]["candidate_landed"] is True
    # A controller ``done`` cell is necessary but not the reader-facing
    # terminal proof.  Only publication of the immutable terminal contract may
    # assert this third delivery state.
    assert done["delivery"]["terminal_complete"] is False
    assert done["delivery"]["terminal_ref_pending"] is True
    assert done["semantic_digest"] == digest(done["semantic"])

    loader = importlib.machinery.SourceFileLoader("cortex_candidate_loop", str(engine))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    loop = importlib.util.module_from_spec(spec)
    loader.exec_module(loop)

    companion_rel = (
        "reports/2026-08-24/cortex-harness/native-agent-lab/receipts/"
        "candidate-companion.md"
    )
    placeholder = attempt_worktree / companion_rel
    placeholder.parent.mkdir(parents=True, exist_ok=True)
    placeholder.write_text("---\nstatus: living\n---\n\nplaceholder\n", encoding="utf-8")
    governance_copy = repo / companion_rel
    governance_copy.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(placeholder, governance_copy)
    quality_gate = ROOT / "bin/verify-three-horizontal-one-vertical.py"
    governance_gate = ROOT / "bin/report-governance.py"
    governance_env = os.environ.copy()
    governance_env["CORTEX_ROOT"] = str(repo)
    placeholder_gate = run([
        sys.executable, str(quality_gate), "check-path", str(placeholder),
    ], repo, check=False)
    assert placeholder_gate.returncode != 0
    run(["git", "add", companion_rel], repo)
    placeholder_governance = run([
        sys.executable, str(governance_gate), "check-staged",
    ], repo, env=governance_env, check=False)
    assert placeholder_governance.returncode != 0

    adapter_result = base / "adapter.result"
    adapter_result.write_text(
        "executor=acp-native:mmx-a\n"
        "native_session_id=fixture-session\n"
        "native_tool_events=3\n"
        "timeout_reason=none\n"
        "error_category=none\n"
        "exit=0\n",
        encoding="utf-8",
    )
    old_companion = os.environ.get("CORTEX_CANDIDATE_COMPANION")
    old_fixture = os.environ.get("CORTEX_ALLOW_NO_HOOK_FIXTURE")
    os.environ["CORTEX_CANDIDATE_COMPANION"] = companion_rel
    os.environ["CORTEX_ALLOW_NO_HOOK_FIXTURE"] = "1"
    refresh_task = {
        "bounds": "artifacts/result.md",
        "artifact_paths": "artifacts/result.md",
        "short_test": "test -f artifacts/result.md",
    }
    refresh_ctx = {
        "worktree": str(attempt_worktree), "attempt": attempt,
        "run_id": run_id, "line": "testline", "task": "T1",
        "executor": "acp-native:mmx-a", "adapter_result": str(adapter_result),
    }
    sparse_contract = loop.workspace_contract_paths(refresh_task)
    assert "bin/claim-count-gate.sh" in sparse_contract["read_paths"]
    assert "bin/verify-frontmatter.py" in sparse_contract["read_paths"]
    assert "bin/verify-skill-integration.sh" in sparse_contract["read_paths"]
    assert "bin/claim-count-gate.sh" in sparse_contract["materialized_paths"]
    assert "bin/verify-frontmatter.py" in sparse_contract["materialized_paths"]
    assert "bin/verify-skill-integration.sh" in sparse_contract["materialized_paths"]
    assert (repo / "bin/claim-count-gate.sh").is_file()
    for helper in (
        "bin/claim-count-gate.sh",
        "bin/verify-frontmatter.py",
        "bin/verify-skill-integration.sh",
    ):
        materialized_helper = attempt_worktree / helper
        materialized_helper.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(repo / helper, materialized_helper)
        assert materialized_helper.is_file()
    assert loop.refresh_candidate_companion(refresh_ctx, refresh_task) == companion_rel
    complete_gate = run([
        sys.executable, str(quality_gate), "check-path", str(placeholder),
    ], repo)
    assert complete_gate.returncode == 0
    shutil.copy2(placeholder, governance_copy)
    run(["git", "add", companion_rel], repo)
    complete_governance = run([
        sys.executable, str(governance_gate), "check-staged",
    ], repo, env=governance_env)
    assert complete_governance.returncode == 0
    refreshed = placeholder.read_text(encoding="utf-8")
    assert "candidate_companion_refresh=after_adapter" in refreshed
    assert "native_session_id=fixture-session" in refreshed
    if old_companion is None:
        os.environ.pop("CORTEX_CANDIDATE_COMPANION", None)
    else:
        os.environ["CORTEX_CANDIDATE_COMPANION"] = old_companion
    if old_fixture is None:
        os.environ.pop("CORTEX_ALLOW_NO_HOOK_FIXTURE", None)
    else:
        os.environ["CORTEX_ALLOW_NO_HOOK_FIXTURE"] = old_fixture

    loop.workspace_contract_paths = lambda unused_task: {
        "writable_paths": ["artifacts/result.md"],
        "artifact_paths": ["artifacts/result.md"],
        "read_paths": [],
        "materialized_paths": ["artifacts/result.md"],
        "short_test": "true",
    }
    loop._workspace_changed_paths = lambda unused_worktree: ["artifacts/result.md"]

    def fake_run(command, timeout=180):
        if "git-auto-commit.sh" in command:
            return 1, "high-impact delivery omitted an evidence report pathspec"
        return 0, "short_test PASS"

    loop.run = fake_run
    try:
        loop.commit_workspace_candidate({
            "worktree": str(attempt_worktree),
            "workspace_manifest": str(workspace / ".state.json"),
            "line": "testline", "task": "T1", "attempt": attempt,
            "run_id": run_id, "contract_id": claim["contract_id"],
            "base_oid": "b" * 40,
        }, {})
        raise AssertionError("missing companion unexpectedly passed candidate gate")
    except RuntimeError as exc:
        assert "MACHINE_BLOCKER" in str(exc), exc
    event_text = (workspace / ".attempt" / (attempt + ".events.jsonl")).read_text(encoding="utf-8")
    assert "MACHINE_BLOCKER" in event_text

print("PASS candidate companion: placeholder FAIL_EXPECTED + refreshed governance PASS + sparse hook helpers + delivery tri-state")
