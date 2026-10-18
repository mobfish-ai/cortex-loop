#!/usr/bin/env python3
"""DeepSeek native ACP adapter bridge check; no live provider or credential use."""
import json
import os
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


with tempfile.TemporaryDirectory(prefix="cortex-acp-native-deepseek-") as tmp:
    base = Path(tmp)
    repo = base / "repo"
    adapters = repo / "bin/cortex-loop-adapters"
    adapters.mkdir(parents=True)
    for name in ("acp-native-mmx-a.sh", "acp-native-deepseek.sh"):
        target = adapters / name
        target.write_text((ROOT / "bin/cortex-loop-adapters" / name).read_text(encoding="utf-8"), encoding="utf-8")
        target.chmod(0o755)

    fake_agent = repo / "bin/cortex-acp-agent"
    fake_agent.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, sys\n"
        "if sys.argv[1:] == ['doctor', '--backend', 'deepseek']:\n"
        "    print('deepseek YES fixture')\n"
        "    raise SystemExit(0)\n"
        "if sys.argv[1:4] != ['serve', '--backend', 'deepseek']:\n"
        "    raise SystemExit(9)\n"
        "for raw in sys.stdin:\n"
        "    message = json.loads(raw)\n"
        "    if message.get('method') == 'initialize':\n"
        "        print(json.dumps({'jsonrpc':'2.0','id':message['id'],'result':{'protocolVersion':1}}), flush=True)\n"
        "    elif message.get('method') == 'session/new':\n"
        "        print(json.dumps({'jsonrpc':'2.0','id':message['id'],'result':{'sessionId':'fixture-deepseek-session'}}), flush=True)\n"
        "    elif message.get('method') == 'session/prompt':\n"
        "        sid = message['params']['sessionId']\n"
        "        final = os.environ.get('FAKE_ACP_FINAL', 'fixture DeepSeek result')\n"
        "        print(json.dumps({'jsonrpc':'2.0','method':'session/update','params':{'update':{'sessionUpdate':'tool_result','content':{'tool_name':'bash','ok':True}}}}), flush=True)\n"
        "        print(json.dumps({'jsonrpc':'2.0','method':'session/update','params':{'sessionId':sid,'update':{'sessionUpdate':'agent_message_chunk','content':{'type':'text','text':final}}}}), flush=True)\n"
        "        print(json.dumps({'jsonrpc':'2.0','id':message['id'],'result':{'stopReason':'end_turn'}}), flush=True)\n"
        "    elif message.get('method') == 'shutdown':\n"
        "        print(json.dumps({'jsonrpc':'2.0','id':message['id'],'result':{}}), flush=True)\n"
        "        break\n",
        encoding="utf-8",
    )
    fake_agent.chmod(0o755)
    adapter = adapters / "acp-native-deepseek.sh"
    env = os.environ.copy()
    env.update({
        "OB1_ROOT": str(repo),
        "CORTEX_WORKTREE": str(base / "worktree"),
        "CORTEX_INSTANCE_ID": "deepseek-1",
        "CORTEX_SESSION_ID": "session-deepseek-1",
        "CORTEX_WORKTREE_ID": "wt-deepseek-1",
        "CORTEX_LEASE_ID": "lease-deepseek-1",
        "CORTEX_RECEIPT_PATH": str(base / "receipt-deepseek-1.json"),
        "CORTEX_MARKER_PATH": str(base / "marker-deepseek-1.txt"),
        "CORTEX_ACP_TIMEOUT": "300",
        "CORTEX_ACP_MODEL_TIMEOUT": "240",
        "CORTEX_ACP_MAX_TOOL_ROUNDS": "48",
    })

    ready = subprocess.run(["bash", str(adapter), "--check-ready"], cwd=repo, env=env, text=True, capture_output=True, check=False)
    assert ready.returncode == 0, (ready.stdout, ready.stderr)
    assert "deepseek YES fixture" in ready.stdout

    prompt = base / "prompt.txt"
    result = base / "result.txt"
    prompt.write_text("Perform the bounded fixture task.", encoding="utf-8")
    bridged = subprocess.run(["bash", str(adapter), str(prompt), str(result)], cwd=repo, env=env, text=True, capture_output=True, check=False)
    assert bridged.returncode == 0, (bridged.stdout, bridged.stderr)
    body = result.read_text(encoding="utf-8")
    for expected in (
        "[adapter] executor=acp-native:deepseek rc=0",
        "tool_layer=acp-native",
        "backend=deepseek",
        "model=deepseek-v4-pro",
        "native_session_id=fixture-deepseek-session",
        "instance_id=deepseek-1",
        "session_id=session-deepseek-1",
        "worktree_id=wt-deepseek-1",
        "lease_id=lease-deepseek-1",
        "execution_path=acp-native-deepseek",
        "receipt_path=" + str(base / "receipt-deepseek-1.json"),
        "result_path=" + str(result),
        "marker_path=" + str(base / "marker-deepseek-1.txt"),
        "max_tool_rounds=48",
        "timeout_reason=none",
        "error_category=none",
    ):
        assert expected in body, body

    failed = base / "network-error.txt"
    transport_env = env.copy()
    transport_env["FAKE_ACP_FINAL"] = "(backend error: network_error)"
    networked = subprocess.run(["bash", str(adapter), str(prompt), str(failed)], cwd=repo, env=transport_env, text=True, capture_output=True, check=False)
    assert networked.returncode != 0
    transport_body = failed.read_text(encoding="utf-8")
    assert "timeout_reason=network_error" in transport_body
    assert "error_category=network_error" in transport_body

print("PASS acp-native:deepseek: doctor + bounded bridge + network_error footer")
