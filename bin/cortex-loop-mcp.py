#!/usr/bin/env python3
"""cortex-loop MCP — 把蜂群能力暴露给外部 AI，走的是同一道六定律门。

设计铁律（改之前先想清楚再改）：
  1. **本文件不含任何业务逻辑**。它只把 MCP 的 JSON-RPC 转译成 `cortex-loop api <verb>`。
     一旦这里出现第二套判断，就等于开了旁路 —— 对内一套标准、对外另一套，正是要防的。
  2. 鉴权不在这里做。caller 身份原样透传给 api 层，由 covenant_check / VERB_POLICY 裁决。
  3. 外部调用者与内部节点**同一套 HAAS 信任**：首次调用 = L1 = 只能读，
     写权限靠历史积累或人类 approved_by 签发。

用法（stdio MCP server）：
    python3 bin/cortex-loop-mcp.py

真相源：bin/cortex-loop（api 子命令 + VERB_POLICY）· aboutme/methods/mobfish-six-laws.md
"""

import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENGINE = os.path.join(ROOT, "bin", "cortex-loop")

# 只暴露只读 verb。写类 verb 需要 L3+ 信任，且应经由节点自身执行 ——
# 让外部 AI 直接触发执行，等于把额度与副作用交给一个 L1 陌生人。
EXPOSED = {
    "swarm": "蜂群节点存活表：谁在线、什么形态、负责哪条线、具备哪些能力",
    "caps": "能力矩阵：全群能力并集、逐节点分布、单点能力告警",
    "trust": "信任等级：各节点 HAAS 实算分数与 L1-L5 等级（历史算出，非自报）",
    "value": "价值构成：V1 线性 / V2 杠杆 / V3 涌现 的分布与杠杆率",
    "gather": "计划汇总：各分布式计划的完成进度",
}


def call_engine(verb, caller):
    proc = subprocess.run(
        ["python3", ENGINE, "api", verb, "--caller", caller],
        capture_output=True, text=True, timeout=300, cwd=ROOT)
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"ok": False, "error": "引擎输出非 JSON",
                "stdout": proc.stdout[-500:], "stderr": proc.stderr[-500:]}


def respond(req_id, result=None, error=None):
    msg = {"jsonrpc": "2.0", "id": req_id}
    if error is not None:
        msg["error"] = error
    else:
        msg["result"] = result
    sys.stdout.write(json.dumps(msg, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def tool_list():
    return {"tools": [{
        "name": "cortex_loop_%s" % verb,
        "description": "%s（调用方需自报 caller 身份；信任不足会被六定律 C2 拦下）" % desc,
        "inputSchema": {
            "type": "object",
            "properties": {"caller": {
                "type": "string",
                "description": "调用方稳定标识。首次调用信任为 L1（只读）；"
                               "信任按该 caller 的历史记录实算，无法自报。"}},
            "required": ["caller"],
        },
    } for verb, desc in sorted(EXPOSED.items())]}


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        method, req_id = req.get("method"), req.get("id")
        if method == "initialize":
            respond(req_id, {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "cortex-loop", "version": "0.1.0"}})
        elif method == "tools/list":
            respond(req_id, tool_list())
        elif method == "tools/call":
            params = req.get("params", {})
            name = params.get("name", "")
            caller = (params.get("arguments") or {}).get("caller", "").strip()
            verb = name.replace("cortex_loop_", "")
            if verb not in EXPOSED:
                respond(req_id, error={"code": -32601, "message": "未暴露的 verb: %s" % verb})
                continue
            if not caller:
                # 匿名 = 无法积累信任 = 无法问责。六定律里没有匿名这一档。
                respond(req_id, error={"code": -32602,
                                       "message": "必须提供 caller 身份：匿名调用无法积累信任，"
                                                  "也无法问责，六定律里没有匿名这一档"})
                continue
            out = call_engine(verb, caller)
            respond(req_id, {"content": [{"type": "text",
                                          "text": json.dumps(out, ensure_ascii=False, indent=2)}],
                             "isError": not out.get("ok", False)})
        elif method and method.startswith("notifications/"):
            continue
        elif req_id is not None:
            respond(req_id, error={"code": -32601, "message": "未实现: %s" % method})


if __name__ == "__main__":
    main()
