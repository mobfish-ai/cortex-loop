#!/usr/bin/env python3
"""Exercise post-edit network salvage without turning transport failure green."""

import importlib.machinery
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
LOOP_PATH = ROOT / "bin/cortex-loop"
loop = importlib.machinery.SourceFileLoader(
    "cortex_loop_post_edit_salvage", str(LOOP_PATH)
).load_module()


def run(cmd, cwd):
    proc = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True)
    if proc.returncode:
        raise AssertionError(f"command failed rc={proc.returncode}: {cmd}\n{proc.stderr}")
    return proc


def make_repo(base: Path, host: bool) -> Path:
    repo = base / ("edited" if not host else "unchanged")
    repo.mkdir()
    (repo / "bin/cortex-loop-tests").mkdir(parents=True)
    shutil.copy2(ROOT / "bin/cortex-loop-tests/short-test-skill-host-frontmatter.sh",
                 repo / "bin/cortex-loop-tests/short-test-skill-host-frontmatter.sh")
    shutil.copy2(ROOT / "bin/verify-frontmatter.py", repo / "bin/verify-frontmatter.py")
    skill = repo / "skills/demo/SKILL.md"
    skill.parent.mkdir(parents=True)
    initial = "---\nname: demo\ndescription: clean\n---\nbody\n"
    if host:
        initial = initial.replace("description: clean", "host: self\ndescription: clean")
    skill.write_text(initial, encoding="utf-8")
    run(["git", "init", "-q"], repo)
    run(["git", "config", "user.email", "fixture@example.invalid"], repo)
    run(["git", "config", "user.name", "fixture"], repo)
    run(["git", "add", "."], repo)
    run(["git", "commit", "-qm", "fixture base"], repo)
    return repo


def result_file(base: Path, category: str) -> Path:
    path = base / f"{category}.result"
    path.write_text(
        "[adapter] executor=acp-native:mmx-a rc=1\n"
        "tool_layer=acp-native\n"
        "native_tool_events=1\n"
        f"timeout_reason={category}\nerror_category={category}\nexit=1\n",
        encoding="utf-8",
    )
    return path


def attempt(repo: Path, suffix: str) -> dict:
    return {
        "attempt": f"transport-salvage-{suffix}",
        "run_id": f"run-{suffix}",
        "line": "testline",
        "task": "T1",
        "worktree": str(repo),
    }


task = {
    "id": "T1",
    "artifact_paths": "skills/demo/SKILL.md",
    "short_test": "bash bin/cortex-loop-tests/short-test-skill-host-frontmatter.sh skills/demo/SKILL.md",
}

with tempfile.TemporaryDirectory(prefix="cortex-post-edit-salvage-") as tmp:
    base = Path(tmp)
    os.environ["CORTEX_WORKSPACE_ROOT"] = str(base / "state")

    edited_repo = make_repo(base, host=False)
    skill = edited_repo / "skills/demo/SKILL.md"
    skill.write_text(
        "---\nname: demo\nhost: self\ndescription: clean\n---\nbody\n",
        encoding="utf-8",
    )
    edited_attempt = attempt(edited_repo, "edited")
    ok, detail = loop._salvage_post_edit_transport(
        edited_attempt, task, str(result_file(base, "network_timeout")), "network_timeout"
    )
    assert ok, detail
    events = list((base / "state/.attempt/transport-salvage-edited.events.jsonl").open())
    event = json.loads(events[-1])
    assert event["native_tool_edit"] is True
    assert event["short_test_pass"] is True
    assert event["terminal_complete"] is False

    unchanged_repo = make_repo(base, host=True)
    unchanged_attempt = attempt(unchanged_repo, "unchanged")
    ok, detail = loop._salvage_post_edit_transport(
        unchanged_attempt, task, str(result_file(base, "network_error")), "network_error"
    )
    assert not ok and "no post-edit change" in detail

print("PASS post-edit transport salvage: changed artifact short_test visible; unchanged artifact rejected")
