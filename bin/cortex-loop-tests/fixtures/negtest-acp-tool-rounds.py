#!/usr/bin/env python3
"""Protocol-free regression for configurable ACP tool rounds and cap evidence."""
import os
from importlib.machinery import SourceFileLoader
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[3]
acp = SourceFileLoader("cortex_acp", str(ROOT / "bin/_cortex_acp.py")).load_module()
saved_chat = acp.chat
saved_run_tool = acp.run_tool


def run_case(cap: int, finish_on: int):
    calls = {"count": 0}

    def fake_chat(_resolved, _messages, timeout=0):
        calls["count"] += 1
        if calls["count"] < finish_on:
            return {
                "content": "",
                "tool_calls": [{
                    "id": "fixture-%d" % calls["count"],
                    "function": {
                        "name": "bash",
                        "arguments": '{"command":"true"}',
                    },
                }],
            }
        return {"content": "done", "tool_calls": []}

    acp.chat = fake_chat
    acp.run_tool = lambda _cwd, _name, _args: "ok"
    os.environ["CORTEX_ACP_MAX_TOOL_ROUNDS"] = str(cap)
    server = acp.HttpAcpServer({"id": "fixture", "name": "fixture", "title": "fixture"})
    server.notify = lambda *_args, **_kwargs: None
    with TemporaryDirectory(prefix="cortex-acp-rounds-") as tmp:
        result = server.loop("fixture-session", {"cwd": Path(tmp), "messages": []}, timeout=30)
    return result, calls["count"]


try:
    low, low_calls = run_case(1, 3)
    assert low == "(tool round cap)", (low, low_calls)
    assert low_calls == 1, low_calls

    high, high_calls = run_case(3, 3)
    assert high == "done", (high, high_calls)
    assert high_calls == 3, high_calls

    os.environ["CORTEX_ACP_MAX_TOOL_ROUNDS"] = "0"
    try:
        run_case(0, 1)
    except ValueError as exc:
        assert "between 1 and 1000" in str(exc)
    else:
        raise AssertionError("invalid round cap must fail closed")
finally:
    acp.chat = saved_chat
    acp.run_tool = saved_run_tool
    os.environ.pop("CORTEX_ACP_MAX_TOOL_ROUNDS", None)

print("PASS ACP tool round cap: low cap fails closed, high cap continues, invalid cap rejected")
