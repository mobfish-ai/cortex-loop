#!/usr/bin/env python3
"""Protocol-only adapter bridge test; no provider call or credential read."""
import json
import os
import subprocess
import sys
import tempfile
from importlib.machinery import SourceFileLoader
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


with tempfile.TemporaryDirectory(prefix="cortex-acp-native-adapter-") as tmp:
    base = Path(tmp)
    repo = base / "repo"
    (repo / "bin/cortex-loop-adapters").mkdir(parents=True)
    adapter = repo / "bin/cortex-loop-adapters/acp-native-mmx-a.sh"
    adapter.write_text(
        (ROOT / "bin/cortex-loop-adapters/acp-native-mmx-a.sh").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    adapter.chmod(0o755)
    for backend in ("mmx-b", "mmx-d"):
        sibling = repo / ("bin/cortex-loop-adapters/acp-native-%s.sh" % backend)
        sibling.write_text(
            (ROOT / ("bin/cortex-loop-adapters/acp-native-%s.sh" % backend)).read_text(
                encoding="utf-8"
            ),
            encoding="utf-8",
        )
        sibling.chmod(0o755)
    fake_agent = repo / "bin/cortex-acp-agent"
    fake_agent.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, sys, time\n"
        "for raw in sys.stdin:\n"
        "    m = json.loads(raw)\n"
        "    if m.get('method') == 'initialize':\n"
        "        print(json.dumps({'jsonrpc':'2.0','id':m['id'],'result':{'protocolVersion':1}}), flush=True)\n"
        "    elif m.get('method') == 'session/new':\n"
        "        print(json.dumps({'jsonrpc':'2.0','id':m['id'],'result':{'sessionId':'fake-mmxa-session'}}), flush=True)\n"
        "    elif m.get('method') == 'session/prompt':\n"
        "        capture = os.environ.get('FAKE_ACP_CAPTURE')\n"
        "        if capture:\n"
        "            open(capture, 'w', encoding='utf-8').write(json.dumps(m))\n"
        "        delay = float(os.environ.get('FAKE_ACP_DELAY', '0'))\n"
        "        if delay:\n"
        "            time.sleep(delay)\n"
        "        sid = m['params']['sessionId']\n"
        "        print(json.dumps({'jsonrpc':'2.0','method':'session/update','params':{'update':{'sessionUpdate':'tool_result','content':{'tool_name':'bash','ok':True}}}}), flush=True)\n"
        "        final = os.environ.get('FAKE_ACP_FINAL', 'fake native result')\n"
        "        print(json.dumps({'jsonrpc':'2.0','method':'session/update','params':{'sessionId':sid,'update':{'sessionUpdate':'agent_message_chunk','content':{'type':'text','text':final}}}}), flush=True)\n"
        "        print(json.dumps({'jsonrpc':'2.0','id':m['id'],'result':{'stopReason':'end_turn'}}), flush=True)\n"
        "    elif m.get('method') == 'shutdown':\n"
        "        print(json.dumps({'jsonrpc':'2.0','id':m['id'],'result':{}}), flush=True)\n"
        "        break\n",
        encoding="utf-8",
    )
    fake_agent.chmod(0o755)
    prompt = base / "prompt.txt"
    result = base / "result.txt"
    prompt.write_text("Do the bounded fixture task.", encoding="utf-8")
    env = os.environ.copy()
    prompt_capture = base / "prompt.json"
    env.update(
        {
            "OB1_ROOT": str(repo),
            "CORTEX_WORKTREE": str(base / "worktree"),
            "CORTEX_ACP_TIMEOUT": "3",
            "CORTEX_ACP_MODEL_TIMEOUT": "2",
            "FAKE_ACP_CAPTURE": str(prompt_capture),
        }
    )
    proc = subprocess.run(
        ["bash", str(adapter), str(prompt), str(result)],
        cwd=repo,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 0, (proc.stdout, proc.stderr)
    body = result.read_text(encoding="utf-8")
    assert "[adapter] executor=acp-native:mmx-a rc=0" in body
    assert "tool_layer=acp-native" in body
    assert "native_session_id=fake-mmxa-session" in body
    assert "native_tool_events=1" in body
    assert "native_tool_names=bash" in body
    assert "session_timeout_seconds=3.000" in body
    assert "max_tool_rounds=12" in body
    assert "timeout_reason=none" in body
    assert "budget_result=completed" in body
    for backend in ("mmx-b", "mmx-d"):
        sibling_result = base / (backend + "-result.txt")
        sibling = repo / ("bin/cortex-loop-adapters/acp-native-%s.sh" % backend)
        sibling_proc = subprocess.run(
            ["bash", str(sibling), str(prompt), str(sibling_result)],
            cwd=repo,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        assert sibling_proc.returncode == 0, (sibling_proc.stdout, sibling_proc.stderr)
        sibling_body = sibling_result.read_text(encoding="utf-8")
        assert "[adapter] executor=acp-native:%s rc=0" % backend in sibling_body
        assert "executor=acp-native:%s" % backend in sibling_body
        assert "backend=%s" % backend in sibling_body
        assert "budget_result=completed" in sibling_body
    prompt_params = json.loads(prompt_capture.read_text(encoding="utf-8"))["params"]
    assert 0 < prompt_params["timeout"] <= 2
    assert prompt_params["model_timeout"] == prompt_params["timeout"]

    timeout_result = base / "timeout-result.txt"
    timeout_env = env.copy()
    timeout_env.update(
        {
            "CORTEX_ACP_TIMEOUT": "2",
            "CORTEX_ACP_MODEL_TIMEOUT": "0.1",
            "FAKE_ACP_DELAY": "3",
        }
    )
    timed = subprocess.run(
        ["bash", str(adapter), str(prompt), str(timeout_result)],
        cwd=repo,
        env=timeout_env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert timed.returncode != 0
    timeout_body = timeout_result.read_text(encoding="utf-8")
    assert "[adapter] executor=acp-native:mmx-a rc=1" in timeout_body
    assert "tool_layer=acp-native" in timeout_body
    assert "native_session_id=fake-mmxa-session" in timeout_body
    assert "native_tool_events=0" in timeout_body
    assert "session_timeout_seconds=2.000" in timeout_body
    assert "model_timeout_seconds=0.100" in timeout_body
    assert "timeout_stage=prompt_wait" in timeout_body
    assert "max_tool_rounds=12" in timeout_body
    assert "timeout_reason=session_timeout" in timeout_body
    assert "error=TimeoutError" in timeout_body

    round_result = base / "round-result.txt"
    round_env = env.copy()
    round_env.update(
        {
            "CORTEX_ACP_MAX_TOOL_ROUNDS": "1",
            "FAKE_ACP_FINAL": "(tool round cap)",
        }
    )
    rounded = subprocess.run(
        ["bash", str(adapter), str(prompt), str(round_result)],
        cwd=repo,
        env=round_env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert rounded.returncode != 0
    round_body = round_result.read_text(encoding="utf-8")
    assert "max_tool_rounds=1" in round_body
    assert "timeout_reason=tool_round_cap" in round_body
    assert "error=TimeoutError" in round_body

    network_result = base / "network-timeout-result.txt"
    network_env = env.copy()
    network_env["FAKE_ACP_FINAL"] = "(backend error: network_timeout)"
    networked = subprocess.run(
        ["bash", str(adapter), str(prompt), str(network_result)],
        cwd=repo,
        env=network_env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert networked.returncode != 0
    network_body = network_result.read_text(encoding="utf-8")
    assert "timeout_reason=network_timeout" in network_body
    assert "error_category=network_timeout" in network_body
    assert "error=TimeoutError" in network_body

    transport_result = base / "network-error-result.txt"
    transport_env = env.copy()
    transport_env["FAKE_ACP_FINAL"] = "(backend error: network_error)"
    transported = subprocess.run(
        ["bash", str(adapter), str(prompt), str(transport_result)],
        cwd=repo,
        env=transport_env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert transported.returncode != 0
    transport_body = transport_result.read_text(encoding="utf-8")
    assert "timeout_reason=network_error" in transport_body
    assert "error_category=network_error" in transport_body
    assert "error=RuntimeError" in transport_body

acp = SourceFileLoader("cortex_acp_timeout_observability", str(ROOT / "bin/_cortex_acp.py")).load_module()
original_urlopen = acp.urllib.request.urlopen


def force_url_error(*_args, **_kwargs):
    raise acp.urllib.error.URLError("fixture transport failure")


acp.urllib.request.urlopen = force_url_error
try:
    try:
        acp.chat(
            {"id": "fixture", "model": "fixture", "base_url": "https://invalid", "api_key": "fixture"},
            [{"role": "user", "content": "fixture"}],
            timeout=1,
        )
    except acp.NetworkTransportError as exc:
        assert str(exc) == "network error"
    else:
        raise AssertionError("non-timeout URLError must become NetworkTransportError")
finally:
    acp.urllib.request.urlopen = original_urlopen

server = acp.HttpAcpServer({"id": "fixture", "model": "fixture", "base_url": "https://invalid"})
emitted = []
server.send = emitted.append

def force_network_timeout(_sid, _sess, *, timeout):
    assert timeout > 0
    raise acp.NetworkTimeoutError("network timeout")

server.loop = force_network_timeout
server.on_prompt(9, {"sessionId": "fixture-session", "prompt": "fixture", "model_timeout": 1})
timeout_updates = [
    message for message in emitted
    if message.get("method") == "session/update"
]
assert timeout_updates[-1]["params"]["update"]["errorCategory"] == "network_timeout"
assert timeout_updates[-1]["params"]["update"]["content"]["text"] == "(backend error: network_timeout)"

emitted.clear()


def force_network_error(_sid, _sess, *, timeout):
    assert timeout > 0
    raise acp.NetworkTransportError("network error")


server.loop = force_network_error
server.on_prompt(10, {"sessionId": "fixture-session", "prompt": "fixture", "model_timeout": 1})
transport_updates = [
    message for message in emitted
    if message.get("method") == "session/update"
]
assert transport_updates[-1]["params"]["update"]["errorCategory"] == "network_error"
assert transport_updates[-1]["params"]["update"]["content"]["text"] == "(backend error: network_error)"

module = SourceFileLoader("cortex_loop", str(ROOT / "bin/cortex-loop")).load_module()
assert module.executor_adapter_name("acp-native:mmx-a") == "acp-native-mmx-a"
assert module.executor_adapter_path("acp-native:mmx-a").endswith(
    "/bin/cortex-loop-adapters/acp-native-mmx-a.sh"
)
assert Path(module.executor_adapter_path("acp-native:mmx-a")).is_file()
for backend in ("mmx-b", "mmx-d"):
    executor = "acp-native:%s" % backend
    assert module.executor_adapter_name(executor) == "acp-native-%s" % backend
    assert module.executor_adapter_path(executor).endswith(
        "/bin/cortex-loop-adapters/acp-native-%s.sh" % backend
    )
    assert Path(module.executor_adapter_path(executor)).is_file()

with tempfile.TemporaryDirectory(prefix="cortex-acp-missing-catalog-") as missing:
    missing_env = os.environ.copy()
    missing_env["CORTEX_ACP_BACKENDS"] = str(Path(missing) / "absent.json")
    missing_ready = subprocess.run(
        ["bash", str(ROOT / "bin/cortex-loop-adapters/acp-native-mmx-a.sh"), "--check-ready"],
        env=missing_env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert missing_ready.returncode != 0

print("PASS acp-native:mmx-a adapter: safe alias + ACP bridge tool evidence")
