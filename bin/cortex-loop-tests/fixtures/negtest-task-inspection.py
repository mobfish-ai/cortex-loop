#!/usr/bin/env python3
"""task-show and content-equivalent canonical landing regression."""
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def run(cmd, cwd=None, check=True):
    proc = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, check=False)
    if check and proc.returncode != 0:
        raise AssertionError("command failed rc=%s: %s\n%s\n%s" % (
            proc.returncode, " ".join(map(str, cmd)), proc.stdout, proc.stderr))
    return proc


def oid(repo, rev):
    return run(["git", "rev-parse", rev], cwd=repo).stdout.strip()


def publish_canonical(repo, remote, commit):
    """Transfer object without force-updating canonical, then move fixture ref locally."""
    run(["git", "push", "origin", "%s:refs/cortex-fixture/%s" % (commit, commit)], cwd=repo)
    run(["git", "--git-dir", str(remote), "update-ref", "refs/heads/master", commit])


ROOT = Path(__file__).resolve().parents[3]
with tempfile.TemporaryDirectory(prefix="cortex-task-inspection-") as tmp:
    base = Path(tmp)
    repo = base / "work"
    remote = base / "origin.git"
    repo.mkdir()
    run(["git", "init", "--bare", str(remote)])
    run(["git", "init"], cwd=repo)
    run(["git", "config", "user.name", "Cortex Test"], cwd=repo)
    run(["git", "config", "user.email", "cortex@example.invalid"], cwd=repo)
    run(["git", "remote", "add", "origin", str(remote)], cwd=repo)

    (repo / "bin").mkdir()
    shutil.copy2(ROOT / "bin/cortex-loop", repo / "bin/cortex-loop")
    line_dir = repo / "brain-network/directions/testline"
    check_dir = line_dir / "checks"
    check_dir.mkdir(parents=True)
    check_path = check_dir / "t1.sh"
    check_path.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    artifact = repo / "artifacts/result.md"
    artifact.parent.mkdir()
    artifact.write_text("verified artifact\n", encoding="utf-8")
    tasks = line_dir / "TASKS.md"
    tasks.write_text(
        "| id | title | status | artifact_paths | short_test | next_advance_after | updated_at | fails | evidence |\n"
        "|---|---|---|---|---|---|---|---|---|\n"
        "| T1 | inspect settlement | settling | artifacts/result.md | bash brain-network/directions/testline/checks/t1.sh | - | 2026-08-02T06:00+0800 | 0 | artifacts/result.md |\n",
        encoding="utf-8",
    )
    run(["git", "add", "bin/cortex-loop", "brain-network/directions/testline/TASKS.md",
         "brain-network/directions/testline/checks/t1.sh", "artifacts/result.md"], cwd=repo)
    run(["git", "commit", "-m", "source candidate"], cwd=repo)
    source_oid = oid(repo, "HEAD")
    source_tree = oid(repo, "HEAD^{tree}")

    # Simulate integrator squash/replay: a root commit has the exact same tree but
    # source_oid is not its ancestor. This is the production bug's essential shape.
    squash_oid = run(["git", "commit-tree", source_tree, "-m", "squash replay"], cwd=repo).stdout.strip()
    assert run(["git", "merge-base", "--is-ancestor", source_oid, squash_oid],
               cwd=repo, check=False).returncode != 0
    publish_canonical(repo, remote, squash_oid)
    run(["git", "fetch", "origin", "+refs/heads/master:refs/remotes/origin/master"], cwd=repo)

    engine = [sys.executable, str(repo / "bin/cortex-loop")]
    task_before = tasks.read_bytes()
    origin_before = oid(repo, "refs/remotes/origin/master")
    head_before = oid(repo, "HEAD")

    human = run(engine + ["task-show", "--line", "testline", "--task", "T1"], cwd=repo)
    assert not human.stdout.lstrip().startswith("{")
    assert "testline/T1  [settling]" in human.stdout

    machine = json.loads(run(
        engine + ["task-show", "--line", "testline", "--task", "T1", "--json"],
        cwd=repo).stdout)
    assert machine["schema_version"] == "cortex-loop/task-show-v1"
    assert machine["task"]["status"] == "settling"

    diagnosed = json.loads(run(
        engine + ["task-show", "--line", "testline", "--task", "T1",
                  "--settlement", "--json"], cwd=repo).stdout)["settlement"]
    binding = diagnosed["artifact_paths"][0]
    assert diagnosed["propagation"]["state"] == "LANDED"
    assert binding["canonical"]["state"] == "YES"
    assert binding["canonical"]["proof"] == "content-equivalent"
    assert binding["commit"]["candidate_oid"] == source_oid
    assert binding["canonical"]["landed_oid"] == squash_oid
    assert binding["commit"]["blob_oid"] == binding["canonical"]["blob_oid"]

    # Canonical exists but the exact artifact blob differs: deterministic NO/SETTLING.
    artifact.write_text("different canonical content\n", encoding="utf-8")
    run(["git", "add", "artifacts/result.md"], cwd=repo)
    run(["git", "commit", "-m", "canonical artifact differs"], cwd=repo)
    different_artifact_oid = oid(repo, "HEAD")
    publish_canonical(repo, remote, different_artifact_oid)
    run(["git", "switch", "--detach", source_oid], cwd=repo)
    run(["git", "fetch", "origin", "+refs/heads/master:refs/remotes/origin/master"], cwd=repo)
    mismatch = json.loads(run(
        engine + ["task-show", "--line", "testline", "--task", "T1",
                  "--settlement", "--json"], cwd=repo).stdout)["settlement"]
    assert mismatch["propagation"]["state"] == "SETTLING"
    assert mismatch["artifact_paths"][0]["canonical"]["state"] == "NO"
    assert "canonical 内容不同" in mismatch["artifact_paths"][0]["canonical"]["detail"]

    # Dirty local artifact is a hard BLOCKED even when canonical has an exact blob.
    publish_canonical(repo, remote, squash_oid)
    run(["git", "fetch", "origin", "+refs/heads/master:refs/remotes/origin/master"], cwd=repo)
    artifact.write_text("dirty content\n", encoding="utf-8")
    blocked = json.loads(run(
        engine + ["task-show", "--line", "testline", "--task", "T1",
                  "--settlement", "--json"], cwd=repo).stdout)["settlement"]
    assert blocked["propagation"]["state"] == "BLOCKED"
    assert blocked["artifact_paths"][0]["commit"]["state"] == "NO"
    run(["git", "restore", "--source", source_oid, "--", "artifacts/result.md"], cwd=repo)

    missing = run(engine + ["task-show", "--line", "testline", "--task", "NOPE", "--json"],
                  cwd=repo, check=False)
    assert missing.returncode == 1 and "找不到任务" in missing.stderr

    # Every operation above was task-show/read setup: query itself did not mutate truth.
    assert tasks.read_bytes() == task_before
    assert oid(repo, "HEAD") == head_before
    assert oid(repo, "refs/remotes/origin/master") == squash_oid

    # Artifact matches canonical but check differs: completion must keep settling.
    check_path.write_text("#!/usr/bin/env bash\n# canonical-only difference\nexit 0\n", encoding="utf-8")
    run(["git", "add", "brain-network/directions/testline/checks/t1.sh"], cwd=repo)
    run(["git", "commit", "-m", "canonical check differs"], cwd=repo)
    different_check_oid = oid(repo, "HEAD")
    publish_canonical(repo, remote, different_check_oid)
    run(["git", "switch", "--detach", source_oid], cwd=repo)
    # try-complete reads the local remote-tracking ref and does not fetch.
    run(["git", "fetch", "origin", "+refs/heads/master:refs/remotes/origin/master"], cwd=repo)
    first_complete = run(engine + ["try-complete", "--line", "testline", "--task", "T1"],
                         cwd=repo)
    assert "canonical 内容不同" in first_complete.stdout
    task_after_mismatch = json.loads(run(
        engine + ["task-show", "--line", "testline", "--task", "T1", "--json"],
        cwd=repo).stdout)["task"]
    assert task_after_mismatch["status"] == "settling", \
        "artifact-only proof must not hide a non-landed check"

    # Once canonical is the exact squash/replay tree, both artifact + check prove landed.
    publish_canonical(repo, remote, squash_oid)
    final_complete = run(engine + ["try-complete", "--line", "testline", "--task", "T1"],
                         cwd=repo)
    assert "PASS T1 → done" in final_complete.stdout
    final_task = json.loads(run(
        engine + ["task-show", "--line", "testline", "--task", "T1", "--json"],
        cwd=repo).stdout)["task"]
    assert final_task["status"] == "done"

print("PASS task inspection: JSON tri-state + squash/replay exact-blob landing + all land_paths")
