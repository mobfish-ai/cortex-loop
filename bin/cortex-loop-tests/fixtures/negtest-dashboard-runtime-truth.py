#!/usr/bin/env python3
"""Dashboard runtime truth regression.

The dashboard must read task state from both live TASKS.md ledgers and driver
state from ``launchctl print``.  A pulse snapshot is deliberately absent: if
the test still passes, the displayed task/launchd facts cannot be inherited
from a stale pulse cache.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[3]
DASH = ROOT / "bin" / "cortex-dashboard.sh"
fails = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global fails
    if condition:
        print("PASS  " + name)
    else:
        fails += 1
        print("FAIL  %s%s" % (name, " — " + detail if detail else ""))


def write_tasks(path: Path, rows: list[tuple[str, str, str, int]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = [
        "| id | title | status | fails |",
        "|----|-------|--------|-------|",
    ]
    body.extend(
        "| %s | %s | %s | %d |" % row
        for row in rows
    )
    path.write_text("\n".join(body) + "\n", encoding="utf-8")


with tempfile.TemporaryDirectory(prefix="cortex-dashboard-runtime-") as tmp:
    fixture = Path(tmp)
    directions = fixture / "directions"
    write_tasks(
        directions / "loop-ops" / "TASKS.md",
        [
            ("OPS-T1", "done task", "done", 0),
            ("OPS-T2", "blocked task", "blocked", 3),
        ],
    )
    write_tasks(
        directions / "cortex-immune" / "TASKS.md",
        [
            ("IMM-T1", "running task", "running", 2),
            ("IMM-T2", "queued task", "pending", 0),
            ("IMM-T3", "external task", "waiting_external", 1),
        ],
    )

    launchctl_print = fixture / "launchctl-print.txt"
    launchctl_print.write_text(
        """gui/502/com.cortex.loop = {
    state = not running
    runs = 42
    last exit code = 7
}
""",
        encoding="utf-8",
    )
    loop_log = fixture / "cortex-loop.launchd.log"
    loop_log.write_text("fixture heartbeat\n", encoding="utf-8")
    ai_local = fixture / "ai-local.json"
    ai_quota = fixture / "ai-quota.json"
    trust_events = fixture / "trust-events.json"
    trust_table = fixture / "trust-table.txt"
    ai_local.write_text("{}\n", encoding="utf-8")
    ai_quota.write_text("{}\n", encoding="utf-8")
    trust_events.write_text(json.dumps({
        "state": "OK",
        "events": [{
            "node": "orchestrator-laptop", "kind": "mechanism-adopted",
            "label": "L5 adopted", "corrected_target": "worker-loop",
            "evidence": "reports/fixture-mechanism.md",
            "finished": "2026-08-01T12:00:00Z",
        }],
        "by_node": {},
    }) + "\n", encoding="utf-8")
    trust_table.write_text(
        "| node | HAAS | level | auto-run | basis |\n"
        "|------|------|------|----------|------|\n"
        "| orchestrator-laptop | 0.650 | L2 | suggest-only | fixture |\n"
        "| laptop | 0.470 | L1 | confirm each step | fixture |\n",
        encoding="utf-8",
    )

    repo = fixture / "metrics-repo"
    subprocess.run(["git", "init", "-q", str(repo)], check=True)

    env = os.environ.copy()
    env.update(
        {
            "CORTEX_DASH_TEST_MODE": "1",
            "CORTEX_DASH_DIRECTIONS_ROOT": str(directions),
            "CORTEX_DASH_LAUNCHCTL_PRINT_FILE": str(launchctl_print),
            "CORTEX_DASH_LOOP_LOG": str(loop_log),
            "CORTEX_DASH_AI_LOCAL_FILE": str(ai_local),
            "CORTEX_DASH_AI_QUOTA_FILE": str(ai_quota),
            "CORTEX_DASH_TRUST_EVENTS_FILE": str(trust_events),
            "CORTEX_DASH_TRUST_TABLE_FILE": str(trust_table),
            "CORTEX_METRICS_REPO": str(repo),
            "CORTEX_SWARM": "runtime-truth-fixture",
            "CORTEX_S2_RESULT": str(fixture / "missing-s2.json"),
            "CORTEX_DASH_TRUST_TIMEOUT": "1",
        }
    )

    result = subprocess.run(
        ["bash", str(DASH), "--json"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    check("dashboard --json exits zero", result.returncode == 0, result.stderr[:300])
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        check("dashboard --json is valid JSON", False, str(exc))
        payload = {}

    runtime = payload.get("runtime", {})
    tasks = runtime.get("tasks", {})
    totals = tasks.get("totals", {})
    lines = {line.get("line"): line for line in tasks.get("lines", [])}
    launchd = runtime.get("launchd", {})

    check(
        "two TASKS.md ledgers are the task source",
        tasks.get("source") == "TASKS.md"
        and tasks.get("source_state") == "OK"
        and set(lines) == {"loop-ops", "cortex-immune"},
        str(tasks),
    )
    check(
        "realtime totals separate historical fails from actionable open fails",
        totals
        == {
            "total": 5,
            "done": 1,
            "pending": 1,
            "running": 1,
            "settling": 0,
            "blocked": 1,
            "waiting_external": 1,
            "unknown": 0,
            "fails": 6,
            "tasks_with_fails": 3,
            # Every non-terminal row with fails>0 counts as open (including blocked/waiting, not only pending/running)
            "open_fails": 6,
            "open_tasks_with_fails": 3,
            "sentinel": 0,
        },
        str(totals),
    )
    check(
        "each line keeps its own counts",
        lines.get("loop-ops", {}).get("fails") == 3
        and lines.get("cortex-immune", {}).get("status", {}).get("running") == 1,
        str(lines),
    )
    check(
        "launchctl print exposes loaded/state/runs/last-exit",
        launchd.get("loaded") is True
        and launchd.get("state") == "not running"
        and launchd.get("runs") == 42
        and launchd.get("last_exit_code") == 7,
        str(launchd),
    )
    check(
        "runtime compatibility fields use the same truth",
        runtime.get("running") == 1
        and runtime.get("live") is False
        and runtime.get("drifted") == 0,
        str(runtime),
    )
    check(
        "machine view exposes node scores and mechanism upgrades",
        runtime.get("node_scores", {}).get("nodes", [{}])[0].get("score") == 0.65
        and runtime.get("mechanism_upgrades", {}).get("items", [{}])[0].get("kind")
        == "mechanism-adopted",
        str(runtime),
    )

    human = subprocess.run(
        ["bash", str(DASH)],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    check("human dashboard exits zero", human.returncode == 0, human.stderr[:300])
    check(
        "human view focuses running/fails and removes duplicate ledger block",
        (
            "TASKS.md" in human.stdout
            and "running 1" in human.stdout
            and "cortex-immune/IMM-T1" in human.stdout
            and "cumulative rejections 6" in human.stdout
            and "━━ current tasks" in human.stdout
            and "[ ledger ]" not in human.stdout
        ),
        human.stdout[-1200:],
    )
    check(
        "human view shows launchd runs and last exit",
        "ran 42 ticks" in human.stdout and "previous tick error 7" in human.stdout,
        human.stdout[-1200:],
    )
    check(
        "human view shows node scores and mechanism upgrade board",
        "0.650 L2" in human.stdout
        and "0.470 L1" in human.stdout
        and "━━ mechanism board" in human.stdout
        and "L5 adopted" in human.stdout
        and "worker-loop" in human.stdout,
        human.stdout[-1200:],
    )

    source = DASH.read_text(encoding="utf-8")
    check(
        "watch only redraws full body on a published snapshot",
        '"$c_state" == "idle"' in source
        and "sleep 0.25" not in source
        and "sleep 1" in source
        and "\\033[H\\033[2K%s" in source,
        "watch must not rewrite the whole CJK body at 4Hz or mix txt/json generations",
    )

print("dashboard runtime truth: %s" % ("PASS" if fails == 0 else f"FAIL ({fails})"))
raise SystemExit(1 if fails else 0)
