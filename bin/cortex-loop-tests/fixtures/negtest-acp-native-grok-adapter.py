#!/usr/bin/env python3
"""Focused contract test and opt-in real Grok Build CLI smoke."""
from __future__ import annotations
import json, os, runpy, subprocess, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ADAPTER = ROOT / "bin/cortex-loop-adapters/acp-native-grok.sh"
BOUND_RUNNER = ROOT / "bin/cortex-native-bound-run.py"

def run(command, *, cwd=None, env=None, check=False):
    return subprocess.run(command, cwd=cwd, env=env, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=check)

def test_contract():
    text = ADAPTER.read_text(encoding="utf-8")
    for needle in (
        'PROVIDER="grok"', 'MODEL="grok-4.6"', 'bash "$CLIENT" run',
        '--cwd "$WORKTREE" --model "$MODEL"',
        '--permission-mode acceptEdits --no-plan --prompt-file "$AUGMENTED"',
        'status": "DRY_RUN"', 'dry-run-never-proves-live',
        'provider_native":False', 'read-only local Python verifier',
        'node24-pnpm11.7',
    ):
        assert needle in text, needle
    assert "cortex-native-matrix-run.py" not in text
    assert "acp-lane.sh" not in text
    assert text.index('BOUND_RESULT_PATH="${CORTEX_RESULT_PATH:-}"') < text.index(
        'MARKER_REL="${CORTEX_GROK_MARKER_REL:-.cortex/grok-native-marker.json}"')
    assert text.index('BOUND_MARKER_PATH="${CORTEX_MARKER_PATH:-}"') < text.index(
        'MARKER="$WORKTREE/$MARKER_REL"')


def write_fake_runtime(root):
    runtime = root / "runtime"
    for name, version in (("node", "v24.19.0"), ("pnpm", "11.7.0")):
        path = runtime / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"#!/bin/sh\nprintf '%s\\n' '{version}'\n", encoding="utf-8")
        path.chmod(0o755)
    grok = runtime / "grok"
    grok.write_text(
        """#!/usr/bin/env python3
import json
import os
import re
import sys
from pathlib import Path

if "--version" in sys.argv:
    print("fixture-grok 1.0")
    raise SystemExit(0)
prompt = Path(sys.argv[sys.argv.index("--prompt-file") + 1]).read_text(encoding="utf-8")
marker = Path(re.search(r"^- Create or modify exactly this marker file: (.+)$", prompt, re.MULTILINE).group(1))
contract = json.loads(re.search(r"^  (\\{.*\\})$", prompt, re.MULTILINE).group(1))
if os.environ.get("FIXTURE_GROK_WRITE_MARKER", "1") == "1":
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps(contract) + "\\n", encoding="utf-8")
print(json.dumps({"status": "PASS", "marker": str(marker)}))
raise SystemExit(int(os.environ.get("FIXTURE_GROK_RC", "0")))
""",
        encoding="utf-8",
    )
    grok.chmod(0o755)
    return runtime


def make_bound_env(runtime, worktree, result, marker, receipt, instance="grok-1",
                   *, cli_rc=0, write_marker=True):
    env = os.environ.copy()
    env.update({
        "PATH": f"{runtime}:{env.get('PATH', '')}",
        "CORTEX_WORKTREE": str(worktree),
        "CORTEX_NATIVE_BOUND_RUN": "1",
        "CORTEX_INSTANCE_ID": instance,
        "CORTEX_SESSION_ID": f"session-{instance}",
        "CORTEX_THREAD_ID": f"thread-{instance}",
        "CORTEX_WORKTREE_ID": f"worktree-{instance}",
        "CORTEX_LEASE_ID": f"lease-{instance}",
        "CORTEX_RECEIPT_PATH": str(receipt),
        "CORTEX_RESULT_PATH": str(result),
        "CORTEX_MARKER_PATH": str(marker),
        "CORTEX_NODE24_BIN": str(runtime / "node"),
        "CORTEX_PNPM117_BIN": str(runtime / "pnpm"),
        "CORTEX_GROK_EXECUTION_PATH": "grok-build-cli",
        "CORTEX_GROK_MARKER_NONCE": "bound-marker-regression",
        "CORTEX_GROK_MARKER_REL": ".cortex/shared-default-marker.json",
        "FIXTURE_GROK_RC": str(cli_rc),
        "FIXTURE_GROK_WRITE_MARKER": "1" if write_marker else "0",
    })
    return env


def test_bound_marker_binding_and_blockers():
    with tempfile.TemporaryDirectory(prefix="cortex-grok-bound-regression-") as tmp:
        root = Path(tmp)
        runtime = write_fake_runtime(root)
        source, worktree = root / "source", root / "worktree"
        source.mkdir()
        run(["git", "init", "-q", str(source)], check=True)
        run(["git", "-C", str(source), "config", "user.email", "fixture@example.invalid"], check=True)
        run(["git", "-C", str(source), "config", "user.name", "Cortex Fixture"], check=True)
        (source / "README").write_text("fixture\n", encoding="utf-8")
        run(["git", "-C", str(source), "add", "README"], check=True)
        run(["git", "-C", str(source), "commit", "-q", "-m", "fixture"], check=True)
        run(["git", "-C", str(source), "worktree", "add", "-q", "--detach", str(worktree), "HEAD"], check=True)
        prompt = root / "prompt.txt"
        prompt.write_text("Perform the bounded marker smoke and report evidence.", encoding="utf-8")

        result = root / "receipts" / "result-grok-1.json"
        marker = worktree / ".cortex" / "bound-marker-grok-1.json"
        receipt = root / "receipts" / "success-grok-1.json"
        env = make_bound_env(runtime, worktree, result, marker, receipt)
        positive = run(["bash", str(ADAPTER), str(prompt), str(result)], cwd=worktree, env=env)
        assert positive.returncode == 0, (positive.stdout, positive.stderr, result.read_text())
        payload = json.loads(positive.stdout)
        assert payload["status"] == "PASS"
        assert payload["marker"] == str(marker.resolve())
        assert payload["marker_path"] == str(marker)
        assert json.loads(marker.read_text(encoding="utf-8"))["instance_id"] == "grok-1"
        assert not (worktree / ".cortex" / "shared-default-marker.json").exists()
        assert receipt.is_file()
        result_body = result.read_text(encoding="utf-8")
        assert "error=\n" in result_body
        assert "error=none\n" not in result_body
        assert "error=null\n" not in result_body
        assert json.loads(receipt.read_text(encoding="utf-8"))["error"] == "none"
        adapter_summary = runpy.run_path(str(BOUND_RUNNER))["_adapter_summary"]
        assert adapter_summary(result_body)["error"] is None, result_body

        for label, cli_rc, write_marker in (
            ("nonzero-cli", 7, True),
            ("missing-marker", 0, False),
        ):
            with tempfile.TemporaryDirectory(prefix="cortex-grok-%s-" % label) as case_tmp:
                case_root = Path(case_tmp)
                case_runtime = write_fake_runtime(case_root)
                case_source, case_worktree = case_root / "source", case_root / "worktree-grok-1"
                case_source.mkdir()
                run(["git", "init", "-q", str(case_source)], check=True)
                run(["git", "-C", str(case_source), "config", "user.email", "fixture@example.invalid"], check=True)
                run(["git", "-C", str(case_source), "config", "user.name", "Cortex Fixture"], check=True)
                (case_source / "README").write_text("fixture\n", encoding="utf-8")
                run(["git", "-C", str(case_source), "add", "README"], check=True)
                run(["git", "-C", str(case_source), "commit", "-q", "-m", "fixture"], check=True)
                run(["git", "-C", str(case_source), "worktree", "add", "-q", "--detach", str(case_worktree), "HEAD"], check=True)
                case_prompt = case_root / "prompt.txt"
                case_prompt.write_text("Perform the bounded marker smoke and report evidence.", encoding="utf-8")
                case_result = case_root / "receipts" / (label + "-result-grok-1.json")
                case_marker = case_worktree / ".cortex" / (label + "-marker-grok-1.json")
                case_receipt = case_root / "receipts" / (label + "-receipt-grok-1.json")
                case_env = make_bound_env(
                    case_runtime, case_worktree, case_result, case_marker, case_receipt,
                    cli_rc=cli_rc, write_marker=write_marker,
                )
                case_env["CORTEX_GROK_MARKER_REL"] = ".cortex/%s-marker-grok-1.json" % label
                blocked = run(["bash", str(ADAPTER), str(case_prompt), str(case_result)],
                              cwd=case_worktree, env=case_env)
                assert blocked.returncode == 3, (label, blocked.stdout, blocked.stderr)
                blocked_payload = json.loads(case_receipt.read_text(encoding="utf-8"))
                assert blocked_payload["verdict"] == "MACHINE_BLOCKER", blocked_payload
                assert blocked_payload["status"] != "PASS", blocked_payload

        missing_result_binding = dict(env)
        missing_result_binding.pop("CORTEX_RESULT_PATH")
        missing_result_fallback = root / "receipts" / "fallback-grok-1.json"
        blocked = run(
            ["bash", str(ADAPTER), str(prompt), str(missing_result_fallback)],
            cwd=worktree,
            env=missing_result_binding,
        )
        assert blocked.returncode == 3, (blocked.stdout, blocked.stderr)
        assert "bound-result-path-required" in blocked.stderr
        assert not missing_result_fallback.exists()

        missing = dict(env)
        missing.pop("CORTEX_MARKER_PATH")
        missing_result = root / "receipts" / "missing-grok-1.json"
        missing["CORTEX_RESULT_PATH"] = str(missing_result)
        missing["CORTEX_RECEIPT_PATH"] = str(root / "receipts" / "missing-receipt-grok-1.json")
        blocked = run(["bash", str(ADAPTER), str(prompt), str(missing_result)], cwd=worktree, env=missing)
        assert blocked.returncode == 3, (blocked.stdout, blocked.stderr)
        assert "error=bound-marker-path-required" in missing_result.read_text(encoding="utf-8")
        assert not (worktree / ".cortex" / "shared-default-marker.json").exists()

        shared = dict(env)
        shared_result = root / "receipts" / "shared-grok-1.json"
        shared["CORTEX_WORKTREE"] = str(source)
        shared["CORTEX_RESULT_PATH"] = str(shared_result)
        shared["CORTEX_RECEIPT_PATH"] = str(root / "receipts" / "shared-receipt-grok-1.json")
        shared["CORTEX_MARKER_PATH"] = str(source / ".cortex" / "bound-marker-grok-1.json")
        blocked = run(["bash", str(ADAPTER), str(prompt), str(shared_result)], cwd=source, env=shared)
        assert blocked.returncode == 3, (blocked.stdout, blocked.stderr)
        assert "error=shared-repository-refused" in shared_result.read_text(encoding="utf-8")
        assert not (source / ".cortex" / "bound-marker-grok-1.json").exists()

def test_dry_run_is_not_live():
    result = run(["bash", str(ADAPTER), "--dry-run"])
    assert result.returncode == 3, (result.stdout, result.stderr)
    payload = json.loads(result.stdout)
    assert payload["status"] == "DRY_RUN"
    assert payload["verdict"] == "NOT_LIVE"
    assert payload["evidence"]["execution_proof"] == "none"


def test_check_ready_initializes_grok_binary():
    with tempfile.TemporaryDirectory(prefix="cortex-grok-ready-") as tmp:
        root = Path(tmp)
        runtime = write_fake_runtime(root)
        client = root / "acp-policy-client.sh"
        client.write_text(
            "#!/bin/sh\nprintf '%s\\n' '{\"status\":\"dry-run\",\"tool\":\"fixture\",\"backend\":\"grok\"}'\n",
            encoding="utf-8",
        )
        client.chmod(0o755)
        env = os.environ.copy()
        env.update({
            "PATH": f"{runtime}:{env.get('PATH', '')}",
            "CORTEX_NODE24_BIN": str(runtime / "node"),
            "CORTEX_PNPM117_BIN": str(runtime / "pnpm"),
            "CORTEX_ACP_POLICY_CLIENT": str(client),
        })
        result = run(["bash", str(ADAPTER), "--check-ready"], env=env)
        assert result.returncode == 0, (result.stdout, result.stderr)
        payload = json.loads(result.stdout)
        assert payload["status"] == "READY"
        assert payload["provider"] == "grok"
        assert payload["model"] == "grok-4.6"
        assert payload["grok_binary"] == str(runtime / "grok")
        assert payload["live"] is False
        assert payload["execution_path"] == "none"


def live_smoke():
    receipt = Path(os.environ.get(
        "CORTEX_GROK_SMOKE_RECEIPT",
        str(Path(tempfile.gettempdir()) / "cortex-grok-native-smoke-receipt.json")))
    with tempfile.TemporaryDirectory(prefix="cortex-grok-native-source-") as tmp:
        source, worktree = Path(tmp) / "source", Path(tmp) / "worktree"
        source.mkdir()
        run(["git", "init", "-q", str(source)], check=True)
        run(["git", "-C", str(source), "config", "user.email", "cortex-fixture@example.invalid"], check=True)
        run(["git", "-C", str(source), "config", "user.name", "Cortex Fixture"], check=True)
        (source / "README").write_text("fixture\n", encoding="utf-8")
        run(["git", "-C", str(source), "add", "README"], check=True)
        run(["git", "-C", str(source), "commit", "-q", "-m", "fixture"], check=True)
        run(["git", "-C", str(source), "worktree", "add", "-q", "--detach", str(worktree), "HEAD"], check=True)
        prompt = Path(tmp) / "prompt.txt"
        prompt.write_text("Perform the bounded marker smoke and report evidence.", encoding="utf-8")
        result_file = Path(tmp) / "adapter.result"
        env = os.environ.copy()
        execution_path = os.environ.get("CORTEX_GROK_SMOKE_PATH", "grok-build-cli")
        env.update({
            "CORTEX_WORKTREE": str(worktree),
            "CORTEX_GROK_EXECUTION_PATH": execution_path,
            "CORTEX_GROK_RECEIPT_PATH": str(receipt),
            "CORTEX_GROK_MARKER_NONCE": "fixture-live-marker",
            "CORTEX_GROK_ALWAYS_APPROVE": "1",
        })
        result = run(["bash", str(ADAPTER), str(prompt), str(result_file)], cwd=worktree, env=env)
        assert result.returncode == 0, (result.stdout, result.stderr,
                                        result_file.read_text() if result_file.exists() else "")
        payload = json.loads(result.stdout)
        assert payload["status"] == "PASS"
        assert payload["execution_path"] == execution_path
        assert payload["provider"] == "grok" and payload["model"] == "grok-4.6"
        marker = worktree / ".cortex/grok-native-marker.json"
        assert json.loads(marker.read_text(encoding="utf-8")) == {
            "adapter": "acp-native-grok", "provider": "grok", "model": "grok-4.6",
            "nonce": "fixture-live-marker", "status": "written"}
        assert payload["verification"]["side_effect"] == "read-only-verifier"
        assert receipt.is_file()
        assert json.loads(receipt.read_text(encoding="utf-8"))["execution_path"] == execution_path
        print(json.dumps({"status":"PASS","execution_path":execution_path,
                          "receipt":str(receipt),"marker":str(marker),
                          "local_verifier":"PASS"}, sort_keys=True))

if __name__ == "__main__":
    test_contract()
    test_dry_run_is_not_live()
    test_check_ready_initializes_grok_binary()
    test_bound_marker_binding_and_blockers()
    if os.environ.get("CORTEX_GROK_NATIVE_LIVE") == "1":
        live_smoke()
    else:
        print("PASS focused Grok adapter contract; live smoke skipped (set CORTEX_GROK_NATIVE_LIVE=1)")
