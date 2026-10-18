#!/usr/bin/env python3
"""Regression for the authorized B/C backlink scanner and unattended executor choice."""
from __future__ import annotations

import importlib.machinery
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ENGINE = ROOT / "bin" / "cortex-loop"
loader = importlib.machinery.SourceFileLoader("cortex_loop_backlink_fixture", str(ENGINE))
spec = importlib.util.spec_from_loader(loader.name, loader)
module = importlib.util.module_from_spec(spec)
loader.exec_module(module)

fixture_rows = [
    {"state": "MISSING", "path": "rules/on-demand/ground-first-doctrine-guide.md"},
    {"state": "MISSING", "path": "reports/2026-07-29/_standalone/cortex-loop-handoff.md"},
    {"state": "MISSING", "path": "skills/cortex-loop/ERRORS.md"},
    {"state": "UNKNOWN", "path": None},
]
payload = {"files": {"skills/cortex-loop/MAP.md": fixture_rows}, "missing": 3}
original_run = module.run
module.run = lambda *_args, **_kwargs: (1, json.dumps(payload))
try:
    candidates = module.scan_map_backlink_gaps()
finally:
    module.run = original_run

assert len(candidates) == 3, candidates
assert {item["source"] for item in candidates} == {"map-backlink-gap"}
assert all(item["requires"] == "-" for item in candidates)
assert all(item["approved_by"] == "operator-2026-07-30" for item in candidates)
assert all("--check-target" in item["short_test"] for item in candidates)
assert {item["artifact"] for item in candidates} == {
    "rules/on-demand/ground-first-doctrine-guide.md",
    "reports/2026-07-29/_standalone/cortex-loop-handoff.md",
    "skills/cortex-loop/ERRORS.md",
}

# New discoveries must enter the controller ledger; legacy plan file runners are
# fail-closed and may never regain a root-worktree write bypass.
captured = []
saved_add, saved_pick = module.cmd_task_add, module.pick
module.pick = lambda _line, _task: None
module.cmd_task_add = lambda args: (captured.append(args) or 0)
try:
    routed = module.route_discovered_file_tasks(candidates, line="fixture-line")
finally:
    module.cmd_task_add, module.pick = saved_add, saved_pick
assert routed == [item["id"] for item in candidates]
assert len(captured) == 3
assert all(item.resource_class == "local-only" for item in captured)
assert all(item.artifact_paths in {c["artifact"] for c in candidates} for item in captured)
assert all(module.is_deterministic_backlink_task({
    "artifact_paths": item.artifact_paths, "short_test": item.short_test,
}) for item in captured)

engine_text = ENGINE.read_text(encoding="utf-8")
private_plist = ROOT / "work-studio/devops/dotfiles/launchd/com.cortex.loop.plist"
public_plist = ROOT / "examples/launchd/com.cortex.loop.plist"
plist_text = (private_plist if private_plist.is_file() else public_plist).read_text(encoding="utf-8")
assert 'os.environ.get("CORTEX_DEFAULT_EXECUTOR")' in engine_text
assert "<key>CORTEX_DEFAULT_EXECUTOR</key>" in plist_text
assert "<string>cheap</string>" in plist_text

print("fixture-map-backlink-scanner: ALL PASS")
