#!/usr/bin/env python3
"""Focused protocol and fallback fixture for the OpenCode DeepSeek adapter."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path


REPO = Path(__file__).resolve().parents[3]
ADAPTER = REPO / "bin/cortex-loop-adapters/acp-native-opencode-deepseek.sh"


def git_repo(root: Path) -> None:
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.email", "fixture@example.invalid"], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.name", "fixture"], check=True)
    (root / "seed.txt").write_text("seed\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "seed.txt"], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-qm", "fixture seed"], check=True)


def fake_opencode(path: Path) -> None:
    path.write_text(
        """#!/usr/bin/env python3
import json, os, sys

def send(value):
    sys.stdout.write(json.dumps(value) + "\\n")
    sys.stdout.flush()

if len(sys.argv) > 1 and sys.argv[1] == "acp":
    for line in sys.stdin:
        request = json.loads(line)
        method = request.get("method")
        if method == "initialize":
            send({"jsonrpc": "2.0", "id": request["id"], "result": {"protocolVersion": 1}})
        elif method == "session/new":
            if os.environ.get("FAKE_ACP_FAIL"):
                send({"jsonrpc": "2.0", "id": request["id"], "error": {"code": -32602}})
                break
            assert request["params"]["mcpServers"] == []
            send({"jsonrpc": "2.0", "id": request["id"], "result": {"sessionId": "ses_fixture"}})
        elif method == "session/set_config_option":
            assert request["params"]["configId"] == "model"
            assert request["params"]["value"] == "opencode-go/deepseek-v4-flash"
            send({"jsonrpc": "2.0", "id": request["id"], "result": {}})
        elif method == "session/prompt":
            marker = os.environ["CORTEX_MARKER_PATH"]
            with open(marker, "w", encoding="utf-8") as handle:
                handle.write("native-capability-smoke:opencode:opencode-go/deepseek-v4-flash\\n")
            send({"jsonrpc": "2.0", "id": request["id"], "result": {"stopReason": "end_turn"}})
        elif method == "shutdown":
            send({"jsonrpc": "2.0", "id": request["id"], "result": {}})
            break
elif len(sys.argv) > 1 and sys.argv[1] == "run":
    marker = os.environ["CORTEX_MARKER_PATH"]
    with open(marker, "w", encoding="utf-8") as handle:
        handle.write("native-capability-smoke:opencode:opencode-go/deepseek-v4-flash\\n")
    print(json.dumps({"sessionID": "ses_cli_fixture"}))
else:
    print("1.18.13")
""",
        encoding="utf-8",
    )
    path.chmod(0o755)


def run_case(root: Path, fake: Path, fail_acp: bool) -> str:
    marker = root / "native-capability-marker-opencode-1.txt"
    prompt = root.parent / (root.name + "-prompt.txt")
    result = root / "result.txt"
    receipt = root / "receipt.json"
    prompt.write_text("create the marker\n", encoding="utf-8")
    env = os.environ.copy()
    env.update(
        {
            "OPENCODE_BIN": str(fake),
            "CORTEX_WORKTREE": str(root),
            "CORTEX_INSTANCE_ID": "opencode-1",
            "CORTEX_SESSION_ID": "session-opencode-1",
            "CORTEX_WORKTREE_ID": "wt-opencode-1",
            "CORTEX_LEASE_ID": "lease-opencode-1",
            "CORTEX_RECEIPT_PATH": str(receipt),
            "CORTEX_MARKER_PATH": str(marker),
            "CORTEX_OPENCODE_CLI_TIMEOUT": "10",
        }
    )
    if fail_acp:
        env["FAKE_ACP_FAIL"] = "1"
    else:
        env.pop("FAKE_ACP_FAIL", None)
    completed = subprocess.run([str(ADAPTER), str(prompt), str(result)], env=env, text=True, capture_output=True)
    if completed.returncode != 0:
        raise AssertionError(f"adapter failed: {completed.returncode} stderr={completed.stderr}")
    body = result.read_text(encoding="utf-8")
    required = [
        "backend=opencode-deepseek",
        "model=opencode-go/deepseek-v4-flash",
        "instance_id=opencode-1",
        "session_id=session-opencode-1",
        "worktree_id=wt-opencode-1",
        "lease_id=lease-opencode-1",
        "marker_path=" + str(marker.resolve()),
        "status=PASS",
    ]
    for item in required:
        assert item in body, (item, body)
    return body


with tempfile.TemporaryDirectory(prefix="opencode-adapter-fixture-") as temp:
    root = Path(temp)
    fake = root / "opencode"
    fake_opencode(fake)

    native = root / "native"
    native.mkdir()
    git_repo(native)
    native_body = run_case(native, fake, fail_acp=False)
    assert "execution_path=opencode-acp" in native_body
    assert "fallback_attempted=0" in native_body

    fallback = root / "fallback"
    fallback.mkdir()
    git_repo(fallback)
    fallback_body = run_case(fallback, fake, fail_acp=True)
    assert "execution_path=opencode-cli" in fallback_body
    assert "fallback_attempted=1" in fallback_body

print("PASS: OpenCode ACP session/new + model config + CLI fallback contract")
