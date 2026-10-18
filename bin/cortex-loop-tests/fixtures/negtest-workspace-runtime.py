#!/usr/bin/env python3
"""Runtime contract: isolated attempts, conflict admission, landed-only completion."""
import argparse
import importlib.machinery
import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[3]
loader = importlib.machinery.SourceFileLoader(
    "cortex_loop_workspace_runtime", str(PROJECT / "bin/cortex-loop"))
spec = importlib.util.spec_from_loader(loader.name, loader)
loop = importlib.util.module_from_spec(spec)
loader.exec_module(loop)


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], text=True,
                          capture_output=True, check=True).stdout.strip()


def task(task_id, artifact):
    return {
        "id": task_id, "title": task_id, "status": "pending", "bounds": artifact,
        "artifact_paths": artifact, "short_test": "test -s %s" % artifact,
        "fails": "0", "updated_at": "-", "resource_class": "llm-heavy",
    }


with tempfile.TemporaryDirectory(prefix="cortex-runtime-") as raw:
    tmp = Path(raw)
    repo, origin, workspaces = tmp / "repo", tmp / "origin.git", tmp / "workspaces"
    subprocess.run(["git", "init", "--bare", str(origin)], check=True,
                   capture_output=True, text=True)
    subprocess.run(["git", "init", "-b", "master", str(repo)], check=True,
                   capture_output=True, text=True)
    subprocess.run(["git", "--git-dir", str(origin), "config",
                    "uploadpack.allowFilter", "true"], check=True)
    subprocess.run(["git", "--git-dir", str(origin), "config",
                    "uploadpack.allowAnySHA1InWant", "true"], check=True)
    git(repo, "config", "user.name", "fixture")
    git(repo, "config", "user.email", "fixture@example.invalid")
    git(repo, "remote", "add", "origin", str(origin))
    (repo / "bin").mkdir()
    for name in ("cortex-workspace.sh", "cortex-integrator.sh",
                 "cortex-candidate.sh", "git-auto-commit.sh",
                 "git-commit-transaction.sh", "git-sync-v4.sh",
                 "git-commit-preflight.py"):
        shutil.copy2(PROJECT / "bin" / name, repo / "bin" / name)
    hooks = repo / "hooks"; hooks.mkdir()
    pre_commit = hooks / "pre-commit"
    pre_commit.write_text(
        "#!/usr/bin/env bash\n"
        "set -eu\n"
        "state=\"$(git rev-parse --git-common-dir)/cortex-hook-ran\"\n"
        "mkdir -p \"$state\"\n"
        "branch=\"$(git branch --show-current | tr / _)\"\n"
        ": > \"$state/$branch\"\n"
        "if git diff --cached | grep -q REJECT_HOOK; then exit 88; fi\n")
    pre_commit.chmod(0o755)
    git(repo, "config", "core.hooksPath", "hooks")
    line_dir = repo / "brain-network/directions/runtime"
    line_dir.mkdir(parents=True)
    header = (
        "| id | title | status | bounds | artifact_paths | short_test | fails | "
        "updated_at | evidence | next_advance_after | resource_class |\n"
        "|---|---|---|---|---|---|---|---|---|---|---|\n")
    rows = "".join(
        "| %s | %s | pending | %s | %s | test -s %s | 0 | - | - | - | llm-heavy |\n"
        % (tid, tid, artifact, artifact, artifact)
        for tid, artifact in (("A", "out/a.md"), ("B", "out/b.md"),
                              ("C", "out/c.md"), ("D", "out/d.md"),
                              ("E", "out/e.md")))
    (line_dir / "TASKS.md").write_text(header + rows)
    (repo / "seed.txt").write_text("root-stable\n")
    git(repo, "add", "bin", "hooks", "brain-network/directions/runtime/TASKS.md", "seed.txt")
    git(repo, "-c", "core.hooksPath=/dev/null", "commit", "-m", "runtime base")
    git(repo, "push", "-u", "origin", "master")
    base = git(repo, "rev-parse", "HEAD")
    root_index = git(repo, "rev-parse", "--path-format=absolute", "--git-path", "index")
    root_index_hash = subprocess.run(["git", "hash-object", root_index], text=True,
                                     capture_output=True, check=True).stdout.strip()
    root_seed_blob = git(repo, "hash-object", "seed.txt")

    saved = (loop.ROOT, loop.DIRECTIONS, loop.FAILURE_STATE)
    old_env = {key: os.environ.get(key) for key in (
        "CORTEX_WORKSPACE_ROOT", "CORTEX_WORKSPACE_MIN_FREE_KB",
        "CORTEX_CANONICAL_PUSH_REF", "CORTEX_CHEAP_AVAILABLE_ACCOUNTS",
        "CORTEX_MAX_WORKERS")}
    try:
        loop.ROOT = str(repo)
        loop.DIRECTIONS = str(repo / "brain-network/directions")
        loop.FAILURE_STATE = str(repo / ".git/cortex-loop-state/failures.json")
        os.environ["CORTEX_WORKSPACE_ROOT"] = str(workspaces)
        os.environ["CORTEX_WORKSPACE_MIN_FREE_KB"] = "1"
        os.environ["CORTEX_CANONICAL_PUSH_REF"] = "refs/heads/master"
        os.environ["CORTEX_CHEAP_AVAILABLE_ACCOUNTS"] = "2"
        os.environ["CORTEX_MAX_WORKERS"] = "3"

        # LIVE-5 regression: the checkout stays on master while the configured
        # canonical push ref is a diverged lab branch. Attempt admission must
        # fetch and freeze the lab tip, then the normal candidate/integrator path
        # must short-test and land against that same ref.
        git(repo, "checkout", "-b", "lab")
        (repo / "lab-anchor.txt").write_text("lab canonical\n")
        git(repo, "add", "lab-anchor.txt")
        git(repo, "commit", "-m", "lab canonical tip")
        lab_tip = git(repo, "rev-parse", "HEAD")
        git(repo, "push", "origin", "HEAD:refs/heads/lab")
        git(repo, "checkout", "master")
        lab_task = task("LAB", "out/lab.md")
        lab_task["short_test"] = "test -s out/lab.md && test -s lab-anchor.txt"
        os.environ["CORTEX_CANONICAL_PUSH_REF"] = "refs/heads/lab"
        lab_ctx = loop.create_workspace_attempt("runtime", lab_task, "cheap")
        assert lab_ctx["base_oid"] == lab_tip, lab_ctx
        assert lab_ctx["base_ref"] == "refs/heads/lab", lab_ctx
        lab_worktree = Path(lab_ctx["worktree"])
        assert git(lab_worktree, "rev-parse", "HEAD") == lab_tip
        (lab_worktree / "out").mkdir(exist_ok=True)
        (lab_worktree / "out/lab.md").write_text("lab artifact\n")
        lab_candidate = loop.commit_workspace_candidate(lab_ctx, lab_task)
        lab_code, lab_receipt = loop.run_workspace_integrator(lab_candidate)
        assert lab_code == 0 and lab_receipt["status"] == "landed", lab_receipt
        assert git(repo, "ls-remote", "origin", "refs/heads/lab").split()[0] == \
            lab_receipt["landed_commit"]
        assert loop._release_workspace_attempt(lab_candidate)[0] == 0
        print("PASS canonical lab base: fetched tip → short_test → landed")
        os.environ["CORTEX_CANONICAL_PUSH_REF"] = "refs/heads/master"
        # Branch checkout/commit above intentionally touched the fixture root
        # index; establish the isolation sentinel after that setup, before the
        # concurrent attempt assertions below.
        root_index = git(repo, "rev-parse", "--path-format=absolute", "--git-path", "index")
        root_index_hash = subprocess.run(["git", "hash-object", root_index], text=True,
                                         capture_output=True, check=True).stdout.strip()

        # The legacy distributed-plan runner may still execute read-only/external
        # actions, but file producers must use this workspace runtime.
        assert loop.legacy_plan_requires_workspace({"artifact": "reports/x.md"})
        assert not loop.legacy_plan_requires_workspace({"artifact": "-"})
        assert not loop.legacy_plan_requires_workspace({})
        migration_receipt = loop.parse_kv(loop.run_receipt_payload(
            "legacy", {"id": "L1", "artifact": "reports/x.md",
                       "short_test": "test -s reports/x.md"},
            {"holder": "fixture", "since": "2026-08-01T00:00:00Z"},
            "cheap", "failed", "workspace-required",
            "legacy_plan_requires_workspace_migration"))
        assert migration_receipt["status"] == "failed"
        assert migration_receipt["gate"] == "workspace-required"
        assert migration_receipt["reason"] == "legacy_plan_requires_workspace_migration"

        # Admission: disjoint can run together; overlap remains pending.
        a, b = task("A", "out/a.md"), task("B", "out/b.md")
        overlap = task("X", "out/")
        overlap["artifact_paths"] = "out/x.md"
        admitted, deferred = loop.admit_disjoint_tasks([a, b, overlap], [], 3)
        assert [item[0]["id"] for item in admitted] == ["A", "B"]
        assert deferred == [(overlap, "write-conflict")]
        capacity, facts = loop.workspace_admission_capacity("cheap")
        assert capacity == 2 and facts["cheap_accounts"] == 2, facts
        os.environ["CORTEX_WORKSPACE_MIN_FREE_KB"] = "999999999999"
        capacity, facts = loop.workspace_admission_capacity("cheap")
        assert capacity == 0 and facts["reason"] == "workspace-disk-gate", facts
        os.environ["CORTEX_WORKSPACE_MIN_FREE_KB"] = "1"

        contexts = {}
        errors = []
        def prepare(item):
            try:
                contexts[item["id"]] = loop.create_workspace_attempt(
                    "runtime", item, "cheap")
            except Exception as exc:  # fixture reports exact concurrent failure
                errors.append(exc)
        threads = [threading.Thread(target=prepare, args=(item,)) for item in (a, b)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        assert not errors, errors
        wa, wb = Path(contexts["A"]["worktree"]), Path(contexts["B"]["worktree"])
        index_a = git(wa, "rev-parse", "--path-format=absolute", "--git-path", "index")
        index_b = git(wb, "rev-parse", "--path-format=absolute", "--git-path", "index")
        assert len({root_index, index_a, index_b}) == 3
        (wa / "out").mkdir(exist_ok=True); (wb / "out").mkdir(exist_ok=True)
        (wa / "out/a.md").write_text("attempt-a\n")
        (wb / "out/b.md").write_text("attempt-b\n")

        candidates = {}
        threads = [
            threading.Thread(target=lambda key, item: candidates.setdefault(
                key, loop.commit_workspace_candidate(contexts[key], item)), args=("A", a)),
            threading.Thread(target=lambda key, item: candidates.setdefault(
                key, loop.commit_workspace_candidate(contexts[key], item)), args=("B", b)),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        assert set(candidates) == {"A", "B"}
        assert subprocess.run(["git", "hash-object", root_index], text=True,
                              capture_output=True, check=True).stdout.strip() == root_index_hash
        assert git(repo, "hash-object", "seed.txt") == root_seed_blob
        assert not (repo / "out/a.md").exists() and not (repo / "out/b.md").exists()
        common_git = Path(git(repo, "rev-parse", "--git-common-dir"))
        if not common_git.is_absolute():
            common_git = repo / common_git
        hook_state = common_git / "cortex-hook-ran"
        assert (hook_state / ("cortex_attempt_" + contexts["A"]["attempt"])).exists()
        assert (hook_state / ("cortex_attempt_" + contexts["B"]["attempt"])).exists()
        for candidate in candidates.values():
            assert candidate["candidate_ref"].startswith("refs/cortex/candidate/")
            assert git(repo, "ls-remote", "origin", candidate["candidate_ref"]).split()[0] \
                == candidate["candidate_oid"]
        assert len(list((workspaces / ".candidate").glob("*.json"))) == 3
        assert not (repo / ".git/cortex-loop-state/attempts").exists()

        # candidate A/B originate from the same base; integrator rebases each delta on
        # latest canonical. Complete A only after B advanced canonical again: landed A
        # remains valid because it is an ancestor, not necessarily the current tip.
        receipts = {}
        for key in ("A", "B"):
            code, receipts[key] = loop.run_workspace_integrator(candidates[key])
            assert code == 0 and receipts[key]["status"] == "landed", receipts[key]
        for key in ("A", "B"):
            rc = loop.cmd_try_complete(argparse.Namespace(
                line="runtime", task=key, judge=False,
                integration=(candidates[key], receipts[key])))
            assert rc == 0 and loop.pick("runtime", key)["status"] == "done"
            assert loop._release_workspace_attempt(candidates[key])[0] == 0
        assert len(list((workspaces / ".integration").glob("*.json"))) == 3
        master_tip_after_ab = git(repo, "ls-remote", "origin", "refs/heads/master").split()[0]

        # Hook rejection proves candidate commits execute hooks; failure preserves the
        # dirty attempt for inspection and never creates a candidate receipt/ref.
        rejected = task("H", "out/h.md")
        ctx_h = loop.create_workspace_attempt("runtime", rejected, "cheap")
        wh = Path(ctx_h["worktree"]); (wh / "out").mkdir(exist_ok=True)
        (wh / "out/h.md").write_text("REJECT_HOOK\n")
        try:
            loop.commit_workspace_candidate(ctx_h, rejected)
            raise AssertionError("rejecting hook did not block candidate commit")
        except RuntimeError as exc:
            assert "controlled commit failed" in str(exc), exc
        assert wh.is_dir() and git(wh, "status", "--porcelain")
        assert (wh / "out/h.md").read_text() == "REJECT_HOOK\n"
        assert git(wh, "rev-parse", "HEAD") == master_tip_after_ab
        assert (hook_state / ("cortex_attempt_" + ctx_h["attempt"])).exists()
        assert not Path(ctx_h["candidate_path"]).exists()

        # Reboot/orphan recovery: a worker can die after writing the sparse worktree
        # but before result/candidate receipts exist. The next tick must continue
        # from that durable worktree instead of opening another LLM attempt.
        d = task("D", "out/d.md")
        ctx_d = loop.create_workspace_attempt("runtime", d, "cheap")
        wd = Path(ctx_d["worktree"]); (wd / "out").mkdir(exist_ok=True)
        (wd / "out/d.md").write_text("attempt-d\n")
        loop.set_cell(str(line_dir / "TASKS.md"), "D", "status", "running")
        assert loop.recover_completed_attempt("runtime", d, "cheap")
        assert loop.pick("runtime", "D")["status"] == "done"
        assert not wd.exists()

        # CAS loser receipt is retryable: task stays settling and active clean workspace
        # is retained. Actual lease race is covered by negtest-integration-controller.sh.
        c = task("C", "out/c.md")
        ctx_c = loop.create_workspace_attempt("runtime", c, "cheap")
        wc = Path(ctx_c["worktree"]); (wc / "out").mkdir(exist_ok=True)
        (wc / "out/c.md").write_text("attempt-c\n")
        candidate_c = loop.commit_workspace_candidate(ctx_c, c)
        loop.set_cell(str(line_dir / "TASKS.md"), "C", "status", "settling")
        real_integrator = loop.run_workspace_integrator
        loop.run_workspace_integrator = lambda _candidate: (75, {
            "schema_version": "cortex-integrator/receipt-v2",
            "status": "retryable_cas_conflict", "exit_code": 75,
            "candidate_oid": candidate_c["candidate_oid"],
            "landed_commit": None, "canonical_ref": "refs/heads/master",
            "detail": "canonical advanced",
        })
        try:
            handled, rc = loop.retry_workspace_integration("runtime", c)
        finally:
            loop.run_workspace_integrator = real_integrator
        assert handled and rc == 0
        assert loop.pick("runtime", "C")["status"] == "settling"
        assert wc.is_dir() and git(wc, "status", "--porcelain") == ""
        events = [json.loads(line) for line in Path(
            loop._attempt_events_path(candidate_c)).read_text().splitlines()]
        assert events[-1]["cas_retry_count"] == 1
        assert events[-1]["queue_wait_ms"] is None and events[-1]["run_ms"] is None
        assert isinstance(events[-1]["integration_ms"], int)

        # Content conflicts are bounded separately from CAS/network retries:
        # the same candidate patch cannot converge against an unchanged
        # canonical artifact forever.  One retry remains settling; the second
        # produces an explicit machine blocker and preserves the worktree.
        e = task("E", "out/e.md")
        ctx_e = loop.create_workspace_attempt("runtime", e, "cheap")
        we = Path(ctx_e["worktree"]); (we / "out").mkdir(exist_ok=True)
        (we / "out/e.md").write_text("attempt-e\n")
        candidate_e = loop.commit_workspace_candidate(ctx_e, e)
        loop.set_cell(str(line_dir / "TASKS.md"), "E", "status", "settling")
        conflict_receipt = {
            "schema_version": "cortex-integrator/receipt-v2",
            "status": "retryable_content_conflict", "exit_code": 75,
            "candidate_oid": candidate_e["candidate_oid"],
            "landed_commit": None, "canonical_ref": "refs/heads/master",
            "detail": "candidate conflicts with latest canonical",
        }
        loop.run_workspace_integrator = lambda _candidate: (75, conflict_receipt)
        try:
            handled, rc = loop.retry_workspace_integration("runtime", e)
            assert handled and rc == 0
            assert loop.pick("runtime", "E")["status"] == "settling"
            handled, rc = loop.retry_workspace_integration("runtime", e)
            assert handled and rc != 0
            assert loop.pick("runtime", "E")["status"] == "blocked"
            events = [json.loads(line) for line in Path(
                loop._attempt_events_path(candidate_e)).read_text().splitlines()]
            assert events[-1]["integration_status"] == "machine_blocker_content_conflict"
            assert events[-1]["machine_blocker"] == "content_conflict_unresolved"
            assert events[-1]["terminal_complete"] is False
            assert we.is_dir() and git(we, "status", "--porcelain") == ""
        finally:
            loop.run_workspace_integrator = real_integrator
    finally:
        loop.ROOT, loop.DIRECTIONS, loop.FAILURE_STATE = saved
        for key, value in old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

print("negtest-workspace-runtime: PASS")
