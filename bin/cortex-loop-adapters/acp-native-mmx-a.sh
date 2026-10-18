#!/usr/bin/env bash
# cortex-loop adapter: acp-native:mmx-a
#
# Safe filename for the task-facing executor alias `acp-native:mmx-a`.
# The ACP server/HTTP facade and backend credentials remain owned by
# bin/_cortex_acp.py + governance/acp-backends.json; this file only bridges
# cortex-loop's prompt/result contract to one ACP session.
# `cortex-acp-agent serve` is a long-lived stdio loop with no wall-clock budget;
# this adapter owns the session budget and passes the remaining model slice in
# both `timeout` and `model_timeout` on session/prompt.
set -uo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OB1_ROOT="$(cd "$DIR/../.." && pwd)"
BACKEND="${CORTEX_ACP_BACKEND:-mmx-a}"
EXECUTOR="acp-native:${BACKEND}"
PROMPT_FILE="${1:-}"
RESULT_FILE="${2:-}"

if [[ "$BACKEND" == "opencode-deepseek" ]]; then
  exec bash "$DIR/acp-native-opencode-deepseek.sh" "$@"
fi

if [[ "${1:-}" == "--check-ready" ]]; then
  exec python3 "$OB1_ROOT/bin/cortex-acp-agent" doctor --backend "$BACKEND"
fi

if [[ -z "$PROMPT_FILE" || ! -f "$PROMPT_FILE" ]]; then
  echo "acp-native-mmx-a: missing prompt file" >&2
  exit 1
fi
if [[ -z "$RESULT_FILE" ]]; then
  echo "acp-native-mmx-a: missing result path" >&2
  exit 1
fi

export OB1_ROOT BACKEND EXECUTOR
python3 - "$PROMPT_FILE" "$RESULT_FILE" <<'PY'
import json
import math
import os
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path


prompt_path = Path(sys.argv[1])
result_path = Path(sys.argv[2])
root = Path(os.environ["OB1_ROOT"])
backend = os.environ["BACKEND"]
executor = os.environ["EXECUTOR"]
prompt = prompt_path.read_text(encoding="utf-8", errors="replace")
cwd = Path(os.environ.get("CORTEX_WORKTREE") or os.getcwd()).expanduser().resolve()
cwd.mkdir(parents=True, exist_ok=True)
session_timeout = 1740.0
configured_model_timeout = session_timeout
max_tool_rounds = 12
model_timeout = 0.0
timeout_stage = "config"
timeout_reason = "none"
error_category = "none"
session_id = ""
text_chunks: list[str] = []
tool_names: list[str] = []
final_output = ""
messages: queue.Queue[str | None] = queue.Queue()
command = [sys.executable, str(root / "bin" / "cortex-acp-agent"), "serve", "--backend", backend]


def read_timeout(name: str, default: float) -> float:
    value = float(os.environ.get(name, str(default)))
    if not math.isfinite(value) or value <= 0:
        raise ValueError("%s must be a finite positive number" % name)
    return value


def read_round_cap(name: str, default: int) -> int:
    raw = os.environ.get(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError("%s must be an integer" % name) from exc
    if value < 1 or value > 1000:
        raise ValueError("%s must be between 1 and 1000" % name)
    return value


def write_result(rc: int, lines: list[str]) -> None:
    result_path.parent.mkdir(parents=True, exist_ok=True)
    body = [
        "[adapter] executor=%s rc=%d" % (executor, rc),
        "tool_layer=acp-native",
        "executor=%s" % executor,
        "backend=%s" % backend,
        "model=%s" % os.environ.get("MMX_ACP_MODEL", "MiniMax-M3"),
        "instance_id=%s" % os.environ.get("CORTEX_INSTANCE_ID", "unknown"),
        "session_id=%s" % os.environ.get("CORTEX_SESSION_ID", "unknown"),
        "worktree_id=%s" % os.environ.get("CORTEX_WORKTREE_ID", "unknown"),
        "lease_id=%s" % os.environ.get("CORTEX_LEASE_ID", "unknown"),
        "execution_path=acp-native-mmx-%s.sh" % backend.removeprefix("mmx-"),
        "cwd=%s" % cwd,
        "native_session_id=%s" % (session_id or "unknown"),
        "native_tool_events=%d" % len(tool_names),
        "native_tool_names=%s" % ",".join(tool_names or ["none"]),
        "session_timeout_seconds=%.3f" % session_timeout,
        "model_timeout_seconds=%.3f" % model_timeout,
        "max_tool_rounds=%d" % max_tool_rounds,
        "timeout_stage=%s" % timeout_stage,
        "timeout_reason=%s" % timeout_reason,
        "error_category=%s" % error_category,
    ]
    if final_output:
        body.append("final_output=%s" % final_output[:12000])
    body.extend(lines)
    body.append("exit=%d" % rc)
    result_path.write_text("\n".join(body) + "\n", encoding="utf-8")


def harvest_pending_evidence() -> None:
    """Capture protocol evidence already emitted when the wall clock expires."""
    global error_category, session_id, timeout_stage
    end = time.monotonic() + 0.1
    while time.monotonic() < end:
        try:
            raw = messages.get(timeout=min(0.02, max(0.001, end - time.monotonic())))
        except queue.Empty:
            continue
        if raw is None:
            return
        try:
            message = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if message.get("id") == 2:
            candidate = str((message.get("result") or {}).get("sessionId") or "")
            if candidate:
                session_id = candidate
                timeout_stage = "prompt_wait"
        if message.get("method") != "session/update":
            continue
        update = ((message.get("params") or {}).get("update") or {})
        category = str(update.get("errorCategory") or "").strip()
        if category:
            error_category = category
        kind = update.get("sessionUpdate")
        content = update.get("content") or {}
        if kind == "agent_message_chunk" and isinstance(content, dict):
            text = content.get("text")
            if text:
                text_chunks.append(str(text))
        elif kind == "tool_result" and isinstance(content, dict):
            name = content.get("tool_name")
            if name:
                tool_names.append(str(name))


def send(proc, message: dict) -> None:
    proc.stdin.write(json.dumps(message, ensure_ascii=False) + "\n")
    proc.stdin.flush()


proc = None
try:
    session_timeout = read_timeout("CORTEX_ACP_TIMEOUT", 1740.0)
    configured_model_timeout = read_timeout(
        "CORTEX_ACP_MODEL_TIMEOUT", session_timeout
    )
    max_tool_rounds = read_round_cap("CORTEX_ACP_MAX_TOOL_ROUNDS", 12)
    deadline = time.monotonic() + session_timeout
    timeout_stage = "spawn"
    proc = subprocess.Popen(
        command,
        cwd=str(root),
        env=os.environ.copy(),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        bufsize=1,
    )
    timeout_stage = "initialize"
    send(proc, {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {"protocolVersion": 1, "clientInfo": {"name": "cortex-loop", "version": "1"}},
    })
    send(proc, {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "session/new",
        "params": {"cwd": str(cwd)},
    })
    send_prompt = False
    prompt_done = False
    def read_output() -> None:
        for line in proc.stdout:
            messages.put(line)
        messages.put(None)

    threading.Thread(target=read_output, daemon=True).start()
    while time.monotonic() < deadline and not prompt_done:
        try:
            raw = messages.get(timeout=min(1.0, max(0.1, deadline - time.monotonic())))
        except queue.Empty:
            continue
        if raw is None:
            break
        try:
            message = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if message.get("id") == 2:
            timeout_stage = "prompt_wait"
            session_id = str((message.get("result") or {}).get("sessionId") or "")
            if not session_id:
                raise RuntimeError("ACP session/new returned no sessionId")
            remaining = deadline - time.monotonic()
            if remaining <= 0.1:
                raise TimeoutError("ACP session timed out before model prompt")
            model_timeout = min(configured_model_timeout, remaining)
            send(proc, {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "session/prompt",
                "params": {
                    "sessionId": session_id,
                    "prompt": prompt,
                    "timeout": model_timeout,
                    "model_timeout": model_timeout,
                },
            })
            send_prompt = True
            continue
        if message.get("method") == "session/update":
            update = ((message.get("params") or {}).get("update") or {})
            category = str(update.get("errorCategory") or "").strip()
            if category:
                error_category = category
            kind = update.get("sessionUpdate")
            content = update.get("content") or {}
            if kind == "agent_message_chunk" and isinstance(content, dict):
                text = content.get("text")
                if text:
                    text_chunks.append(str(text))
            elif kind == "tool_result" and isinstance(content, dict):
                name = content.get("tool_name")
                if name:
                    tool_names.append(str(name))
            continue
        if send_prompt and message.get("id") == 3:
            if "error" in message:
                raise RuntimeError(str(message["error"]))
            prompt_done = True
    if not prompt_done:
        raise TimeoutError("ACP session timed out")
    if not send_prompt:
        raise RuntimeError("ACP session/new did not complete")
    final_output = "".join(text_chunks).strip().replace("\x00", "")
    if final_output.startswith("(backend error: network_timeout)") or error_category == "network_timeout":
        timeout_reason = "network_timeout"
        error_category = "network_timeout"
        raise TimeoutError("ACP network request timed out")
    if final_output.startswith("(backend error: network_error)") or error_category == "network_error":
        timeout_reason = "network_error"
        error_category = "network_error"
        raise RuntimeError("ACP network transport error")
    if final_output.startswith("(backend error:"):
        timeout_reason = "backend_error"
        raise RuntimeError("ACP backend error: %s" % final_output[:200])
    if final_output == "(model timeout)":
        timeout_reason = "model_timeout"
        raise TimeoutError("ACP model session timed out: %s" % final_output)
    if final_output == "(tool round cap)":
        timeout_reason = "tool_round_cap"
        raise TimeoutError("ACP tool round cap reached: %d" % max_tool_rounds)
    try:
        send(proc, {"jsonrpc": "2.0", "id": 4, "method": "shutdown", "params": {}})
    except (BrokenPipeError, OSError):
        pass
    try:
        shutdown_remaining = deadline - time.monotonic()
        if shutdown_remaining > 0:
            proc.wait(timeout=min(5.0, shutdown_remaining))
        else:
            proc.kill()
            proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)
    write_result(0, [
        "budget_result=completed",
    ])
except Exception as exc:  # noqa: BLE001
    harvest_pending_evidence()
    if proc is not None:
        try:
            proc.kill()
            proc.wait(timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            pass
    final_output = "".join(text_chunks).strip().replace("\x00", "")
    if timeout_reason == "none":
        if isinstance(exc, TimeoutError):
            timeout_reason = "session_timeout"
        else:
            timeout_reason = "backend_error"
    write_result(1, ["error=%s" % type(exc).__name__, "detail=%s" % str(exc)[:500]])
    raise SystemExit(1)
PY
