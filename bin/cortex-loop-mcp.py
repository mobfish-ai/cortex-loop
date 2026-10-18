#!/usr/bin/env python3
"""cortex-loop MCP — expose swarm capabilities to an external AI through the same six-laws gate.

Design rules (think them through before changing this file):
  1. **This file contains no business logic.** It only translates MCP JSON-RPC into `cortex-loop api <verb>`.
     A second set of judgments here would open a bypass -- one standard inside, another outside, which is what this prevents.
  2. Auth is not done here. The caller identity is passed through to the api layer, which decides via covenant_check / VERB_POLICY.
  3. External callers and internal nodes share **the same HAAS trust**: first call = L1 = read only,
     and write permission comes from history or a human approved_by grant.

Usage (stdio MCP server):
    python3 bin/cortex-loop-mcp.py

Source of truth: bin/cortex-loop (api subcommand + VERB_POLICY) | aboutme/methods/mobfish-six-laws.md
"""

import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENGINE = os.path.join(ROOT, "bin", "cortex-loop")

# Expose read-only verbs only. Write verbs need L3+ trust and should run on the node itself --
# letting an external AI trigger execution hands quota and side effects to an L1 stranger.
EXPOSED = {
    "swarm": "swarm node liveness: who is online, what shape, which line they own, which capabilities they have",
    "caps": "capability matrix: union across the swarm, per-node spread, single-point capability alerts",
    "trust": "trust level: each node's computed HAAS score and L1-L5 grade (from history, not self-reported)",
    "value": "value mix: distribution and leverage of V1 linear / V2 leverage / V3 emergent",
    "gather": "plan rollup: completion progress of each distributed plan",
}


def call_engine(verb, caller):
    proc = subprocess.run(
        ["python3", ENGINE, "api", verb, "--caller", caller],
        capture_output=True, text=True, timeout=300, cwd=ROOT)
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"ok": False, "error": "engine output is not JSON",
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
        "description": "%s (caller must supply a caller identity; insufficient trust is blocked by six-laws C2)" % desc,
        "inputSchema": {
            "type": "object",
            "properties": {"caller": {
                "type": "string",
                "description": "Stable caller id. First call is trust L1 (read-only); "
                               "trust is computed from that caller's history and cannot be self-reported."}},
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
                respond(req_id, error={"code": -32601, "message": "verb not exposed: %s" % verb})
                continue
            if not caller:
                # Anonymous means no trust can accumulate and nobody can be held accountable. The six laws have no anonymous tier.
                respond(req_id, error={"code": -32602,
                                       "message": "caller identity is required: an anonymous call cannot accumulate trust "
                                                  "and cannot be held accountable; the six laws have no anonymous tier"})
                continue
            out = call_engine(verb, caller)
            respond(req_id, {"content": [{"type": "text",
                                          "text": json.dumps(out, ensure_ascii=False, indent=2)}],
                             "isError": not out.get("ok", False)})
        elif method and method.startswith("notifications/"):
            continue
        elif req_id is not None:
            respond(req_id, error={"code": -32601, "message": "not implemented: %s" % method})


if __name__ == "__main__":
    main()
