#!/usr/bin/env bash
# Bounded OpenCode DeepSeek adapter.
#
# OpenCode's ACP transport is NDJSON and requires mcpServers on session/new.
# The adapter tries that native path first, then uses the explicitly allowed
# OpenCode CLI fallback when ACP cannot establish or complete a session.
set -uo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$DIR/../.." && pwd)"
PROMPT_FILE="${1:-}"
RESULT_FILE="${2:-}"

if [[ "${1:-}" == "--check-ready" ]]; then
  command -v opencode >/dev/null 2>&1 || exit 3
  opencode --version
  exit 0
fi

if [[ -z "$PROMPT_FILE" || ! -f "$PROMPT_FILE" || -z "$RESULT_FILE" ]]; then
  printf 'status=MACHINE_BLOCKER\nerror=missing-prompt-or-result\n' >&2
  exit 1
fi

export OB1_ROOT="$ROOT"
exec python3 - "$PROMPT_FILE" "$RESULT_FILE" <<'PY'
from __future__ import annotations

import json
import os
import re
import select
import shutil
import subprocess
import sys
import time
from pathlib import Path


prompt_path = Path(sys.argv[1])
result_path = Path(sys.argv[2])
worktree = Path(os.environ.get("CORTEX_WORKTREE", os.getcwd())).expanduser().resolve()
model = os.environ.get("CORTEX_OPENCODE_MODEL", "opencode-go/deepseek-v4-flash")
provider = "opencode-deepseek"
executor = "acp-native:opencode-deepseek"
instance_id = os.environ.get("CORTEX_INSTANCE_ID", "")
session_id = os.environ.get("CORTEX_SESSION_ID", "")
worktree_id = os.environ.get("CORTEX_WORKTREE_ID", "")
lease_id = os.environ.get("CORTEX_LEASE_ID", "")
receipt_path = os.environ.get("CORTEX_RECEIPT_PATH", "")
marker_path = Path(os.environ.get("CORTEX_MARKER_PATH", "")).expanduser().resolve()
expected_marker = os.environ.get("CORTEX_OPENCODE_MARKER_EXPECTED", "").strip()
prompt = prompt_path.read_text(encoding="utf-8", errors="replace")
native_session_id = "unknown"
tool_events: list[str] = []
tool_call_labels: list[str] = []
permission_requests = 0


def safe(value: object) -> str:
    return re.sub(r"[^A-Za-z0-9._:/+,-]", "_", str(value))[:240] or "none"


def changed_files() -> list[str]:
    try:
        output = subprocess.check_output(
            ["git", "-C", str(worktree), "status", "--porcelain=v1", "--untracked-files=all"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.CalledProcessError):
        return ["unknown"]
    paths: list[str] = []
    for line in output.splitlines():
        if len(line) >= 4:
            path = line[3:]
            if " -> " in path:
                path = path.split(" -> ", 1)[1]
            paths.append(path)
    return sorted(paths)


def marker_ok() -> bool:
    try:
        if not marker_path.is_file() or marker_path.is_symlink():
            return False
        relative = os.path.relpath(marker_path, worktree)
        if relative not in changed_files():
            return False
        content = marker_path.read_text(encoding="utf-8").strip()
        if expected_marker:
            return content == expected_marker
        if os.environ.get("CORTEX_NATIVE_BOUND_RUN") == "1":
            # Bound prompts own the marker content.  Require evidence of both
            # requested actions while avoiding the historical smoke string,
            # which incorrectly rejected valid per-seat markers.
            return content.startswith("provider-write=") and "node-exec=" in content
        return content == "native-capability-smoke:opencode:opencode-go/deepseek-v4-flash"
    except OSError:
        return False


def send(proc: subprocess.Popen[str], message: dict) -> None:
    if proc.stdin is None:
        raise RuntimeError("opencode-stdin-closed")
    proc.stdin.write(json.dumps(message, ensure_ascii=False) + "\n")
    proc.stdin.flush()


def read_messages(proc: subprocess.Popen[str], expected_id: int, deadline: float) -> dict:
    global native_session_id, permission_requests
    while time.monotonic() < deadline:
        if proc.stdout is None:
            raise RuntimeError("opencode-stdout-closed")
        ready, _, _ = select.select([proc.stdout], [], [], min(1.0, max(0.05, deadline - time.monotonic())))
        if not ready:
            continue
        line = proc.stdout.readline()
        if not line:
            raise RuntimeError("opencode-acp-closed")
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            continue
        if message.get("method") == "session/request_permission":
            permission_requests += 1
            params = message.get("params") or {}
            options = params.get("options") if isinstance(params, dict) else None
            option_id = "allow_once"
            if isinstance(options, list):
                for option in options:
                    if isinstance(option, dict) and option.get("optionId"):
                        option_id = str(option["optionId"])
                        break
            send(proc, {
                "jsonrpc": "2.0",
                "id": message.get("id"),
                "result": {"outcome": {"outcome": "selected", "optionId": option_id}},
            })
            continue
        if message.get("method") == "session/update":
            update = ((message.get("params") or {}).get("update") or {})
            kind = update.get("sessionUpdate")
            if kind:
                tool_events.append(str(kind))
            nested_tool = update.get("toolCall") if isinstance(update, dict) else None
            label = (
                update.get("toolName")
                or update.get("tool_name")
                or update.get("name")
                or update.get("title")
                or (nested_tool.get("name") if isinstance(nested_tool, dict) else None)
            )
            if label:
                tool_call_labels.append(str(label))
            continue
        if message.get("id") != expected_id:
            continue
        if "error" in message:
            error = message.get("error") or {}
            raise RuntimeError("rpc-%s" % safe(error.get("code", "error")))
        return message.get("result") or {}
    raise TimeoutError("opencode-acp-timeout")


def run_acp() -> tuple[bool, str]:
    global native_session_id
    opencode = os.environ.get("OPENCODE_BIN") or shutil.which("opencode")
    if not opencode:
        return False, "opencode-not-found"
    proc: subprocess.Popen[str] | None = None
    overall_budget = min(float(os.environ.get("CORTEX_ACP_TIMEOUT", "600")), 600.0)
    acp_budget = min(float(os.environ.get("CORTEX_OPENCODE_ACP_TIMEOUT", "90")), max(10.0, overall_budget * 0.4))
    deadline = time.monotonic() + acp_budget
    try:
        proc = subprocess.Popen(
            [opencode, "acp"],
            cwd=str(worktree),
            env=os.environ.copy(),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
        )
        send(proc, {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": 1,
                "clientInfo": {"name": "cortex-native-opencode", "version": "1"},
            },
        })
        read_messages(proc, 1, deadline)
        send(proc, {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "session/new",
            "params": {"cwd": str(worktree), "mcpServers": []},
        })
        session = read_messages(proc, 2, deadline)
        native_session_id = str(session.get("sessionId") or "")
        if not native_session_id:
            raise RuntimeError("opencode-session-id-missing")
        send(proc, {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "session/set_config_option",
            "params": {"sessionId": native_session_id, "configId": "model", "value": model},
        })
        read_messages(proc, 3, deadline)
        send(proc, {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "session/prompt",
            "params": {
                "sessionId": native_session_id,
                "prompt": [{"type": "text", "text": prompt}],
            },
        })
        read_messages(proc, 4, deadline)
        return marker_ok(), "none" if marker_ok() else "opencode-acp-marker-missing"
    except (OSError, RuntimeError, TimeoutError) as exc:
        return False, type(exc).__name__ + ":" + safe(exc)
    finally:
        if proc is not None:
            try:
                send(proc, {"jsonrpc": "2.0", "id": 5, "method": "shutdown", "params": {}})
            except (BrokenPipeError, OSError, RuntimeError):
                pass
            try:
                proc.terminate()
                proc.wait(timeout=3)
            except (OSError, subprocess.TimeoutExpired):
                try:
                    proc.kill()
                except OSError:
                    pass


def run_cli() -> tuple[bool, str]:
    opencode = os.environ.get("OPENCODE_BIN") or shutil.which("opencode")
    if not opencode:
        return False, "opencode-not-found"
    overall_budget = min(float(os.environ.get("CORTEX_ACP_TIMEOUT", "600")), 600.0)
    timeout = min(float(os.environ.get("CORTEX_OPENCODE_CLI_TIMEOUT", "120")), max(10.0, overall_budget * 0.5))
    cli_prompt = prompt + "\n\nExecution path fallback: use the OpenCode CLI in the current working directory."
    try:
        proc = subprocess.run(
            [opencode, "run", "--model", model, "--format", "json", "--auto", cli_prompt],
            cwd=str(worktree),
            env=os.environ.copy(),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, type(exc).__name__
    for line in proc.stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        candidate = event.get("sessionID") or event.get("sessionId") or event.get("session_id")
        if candidate:
            global native_session_id
            native_session_id = str(candidate)
    if proc.returncode != 0:
        return False, "opencode-cli-exit-%d" % proc.returncode
    return marker_ok(), "none" if marker_ok() else "opencode-cli-marker-missing"


acp_ok, acp_error = run_acp()
execution_path = "opencode-acp" if acp_ok else "none"
fallback_error = "none"
success = acp_ok
if not success and changed_files() in ([], [marker_path.name]):
    cli_ok, fallback_error = run_cli()
    success = cli_ok
    if cli_ok:
        execution_path = "opencode-cli"

files = changed_files()
unique_tool_events = list(dict.fromkeys(tool_events))
unique_tool_calls = list(dict.fromkeys(tool_call_labels))
error = "none" if success else "acp-%s-cli-%s" % (safe(acp_error), safe(fallback_error))
lines = [
    "[adapter] executor=%s rc=%d" % (executor, 0 if success else 1),
    "tool_layer=opencode-native",
    "executor=" + executor,
    "backend=" + provider,
    "model=" + model,
    "instance_id=" + instance_id,
    "session_id=" + session_id,
    "worktree_id=" + worktree_id,
    "lease_id=" + lease_id,
    "native_session_id=" + (native_session_id or "unknown"),
    "execution_path=" + execution_path,
    "receipt_path=" + receipt_path,
    "result_path=" + str(result_path),
    "marker_path=" + str(marker_path),
    "changed_files=" + (",".join(files) if files else "none"),
    "permission_requests=%d" % permission_requests,
    "native_tool_events=%d" % len(tool_events),
    "native_tool_names=" + ",".join(unique_tool_calls or unique_tool_events or ["none"]),
    "native_tool_calls=" + ",".join(unique_tool_calls or ["none"]),
    "native_tool_event_log=" + ",".join(tool_events or ["none"]),
    "fallback_attempted=" + ("1" if not acp_ok else "0"),
    "fallback_error=" + safe(fallback_error),
]
if not success:
    lines.append("error=" + error)
lines.extend(["status=" + ("PASS" if success else "MACHINE_BLOCKER"), "adapter_rc=" + ("0" if success else "1")])
result_path.parent.mkdir(parents=True, exist_ok=True)
result_path.write_text(
    "\n".join(lines) + "\n",
    encoding="utf-8",
)
raise SystemExit(0 if success else 1)
PY
