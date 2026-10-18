#!/usr/bin/env python3
"""Negative tests for rolling-window math and source failure handling."""
import copy
import datetime as dt
import importlib.util
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
# 本 fixture 专测“缺源=UNKNOWN”，不得继承真实生产 guardrail 账本。
os.environ["CORTEX_OPENCLAW_STATE"] = "/tmp/cortex-metric-window-missing-%d" % os.getpid()
spec = importlib.util.spec_from_file_location("cortex_metrics", ROOT / "bin/cortex-metrics.py")
metrics = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules[spec.name] = metrics
spec.loader.exec_module(metrics)
contract = metrics.load_contract(ROOT / "brain-network/directions/loop-ops/METRICS.json")
g2 = copy.deepcopy(next(item for item in contract["metrics"] if item["legacy_name"] == "G2"))
# Keep baseline/window mechanics independent from the production contract's
# current ratification state.  The ACTIVE case is constructed explicitly below.
g2["window"]["duration_seconds"] = None
g2["min_sample"]["value"] = None
g2["target"] = {
    "status": "NOT_SET", "operator": None, "value": None,
    "approved_by": None, "approval_ref": None, "effective_at": None,
}
now = dt.datetime(2026, 7, 30, 12, 0, tzinfo=dt.timezone.utc)

fails = 0


def check(name, ok, detail=""):
    global fails
    if ok:
        print("  PASS", name)
    else:
        fails += 1
        print("  FAIL", name, detail)


records = [
    {"finished": "2026-07-30T11:30:00Z", "gate": "passed"},
    {"finished": "2026-07-30T11:40:00Z", "gate": "scope-gap"},
    {"finished": "2026-07-30T09:00:00Z", "gate": "rejected"},
]
baseline = metrics.compute_g2(g2, records, "OK", now)
check("baseline exposes all-history record without treating it as a target cohort",
      baseline.get("status") == "BASELINE" and baseline.get("actual") == (1 / 3)
      and baseline.get("cumulative_record") == {
          "passed": 1, "scope-gap": 1, "rejected": 1, "denominator": 3,
          "unclassified": 0, "total_records": 3,
      }, str(baseline))

snapshot = metrics.build_snapshot(contract, results=records, source_status="OK", now=now)
check("dashboard-compatible G1/G2 snapshots declare ratio units",
      snapshot.get("g1", {}).get("unit") == "ratio" and snapshot.get("g2", {}).get("unit") == "ratio",
      str({key: snapshot.get(key) for key in ("g1", "g2")}))
check("missing guardrail sources are UNKNOWN, never reassuring zero", all(
    item.get("state") == "UNKNOWN" and item.get("observed_events") is None
    and bool(item.get("reason"))
    for item in snapshot.get("guardrails", [])
), str(snapshot.get("guardrails")))

g2["window"]["duration_seconds"] = 3600
g2["min_sample"]["value"] = 3
out = metrics.compute_g2(g2, records, "OK", now)
check("window excludes result outside the declared interval", out.get("denominator") == 2, str(out))
check("passed and scope-gap stay separate", out.get("classifications") == {
    "passed": 1, "scope-gap": 1, "rejected": 0
}, str(out))
check("small cohort cannot report target status", out.get("status") == "BASELINE",
      "no active target should be evaluated during baseline")

active = copy.deepcopy(g2)
active["baseline"]["status"] = "COMPLETE"
active["target"] = {
    "status": "ACTIVE", "operator": ">=", "value": 0.5,
    "approved_by": "test", "approval_ref": "test-evidence", "effective_at": "2026-07-30T00:00:00Z"
}
out = metrics.compute_g2(active, records, "OK", now)
check("active target with insufficient cohort reports INSUFFICIENT_SAMPLE", out.get("status") == "INSUFFICIENT_SAMPLE", str(out))

out = metrics.compute_g2(g2, None, "UNKNOWN", now)
check("unreadable origin is UNKNOWN, not zero", out.get("status") == "UNKNOWN", str(out))

out = metrics.compute_g2(g2, [{"gate": "passed"}], "OK", now)
check("malformed result timestamp is UNKNOWN, not excluded", out.get("status") == "UNKNOWN", str(out))

print("negtest-metric-window:", "ALL PASS" if not fails else "%d FAIL" % fails)
sys.exit(1 if fails else 0)
