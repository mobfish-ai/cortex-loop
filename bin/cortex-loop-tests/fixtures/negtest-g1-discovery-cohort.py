#!/usr/bin/env python3
"""Negative tests preventing G1 from borrowing the G2 result-rate numerator."""
import copy
import datetime as dt
import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("cortex_metrics", ROOT / "bin/cortex-metrics.py")
metrics = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules[spec.name] = metrics
spec.loader.exec_module(metrics)
contract = metrics.load_contract(ROOT / "brain-network/directions/loop-ops/METRICS.json")
g1 = copy.deepcopy(next(item for item in contract["metrics"] if item["legacy_name"] == "G1"))
now = dt.datetime(2026, 7, 30, 12, 0, tzinfo=dt.timezone.utc)

fails = 0


def check(name, ok, detail=""):
    global fails
    if ok:
        print("  PASS", name)
    else:
        fails += 1
        print("  FAIL", name, detail)


out = metrics.compute_g1(g1, None, [{"gate": "passed", "finished": "2026-07-30T11:00:00Z"}], "OK", now,
                         "UNKNOWN")
check("unreadable discovery source makes G1 UNKNOWN, never G2 rate", out.get("status") == "UNKNOWN", str(out))

out = metrics.compute_g1(g1, [], [], "OK", now, "OK")
check("readable empty discovery source is insufficient sample, not a fake zero/pass",
      out.get("status") == "INSUFFICIENT_SAMPLE"
      and out.get("actual") is None and out.get("denominator") == 0, str(out))

future = copy.deepcopy(g1)
future["window"]["duration_seconds"] = 3600
future["min_sample"]["value"] = 1
discoveries = [
    {"discovery_id": "d-passed", "discovered_at": "2026-07-30T11:10:00Z", "eligibility": "eligible",
     "source": "test", "authorization": "S1", "owner": "cortex-loop"},
    {"discovery_id": "d-scope", "discovered_at": "2026-07-30T11:20:00Z", "eligibility": "eligible",
     "source": "test", "authorization": "S1", "owner": "cortex-loop"},
    {"discovery_id": "d-outside", "discovered_at": "2026-07-30T08:00:00Z", "eligibility": "eligible",
     "source": "test", "authorization": "S1", "owner": "cortex-loop"},
    {"discovery_id": "d-ineligible", "discovered_at": "2026-07-30T11:30:00Z", "eligibility": "ineligible",
     "source": "test", "authorization": "S1", "owner": "cortex-loop"}
]
results = [
    {"discovery_id": "d-passed", "gate": "passed"},
    {"discovery_id": "d-scope", "gate": "scope-gap"},
    {"discovery_id": "d-outside", "gate": "passed"},
    {"discovery_id": "d-ineligible", "gate": "passed"}
]
out = metrics.compute_g1(future, discoveries, results, "OK", now, "OK")
check("frozen eligible discovery cohort excludes outside/ineligible events", out.get("denominator") == 2, str(out))
check("scope-gap remains visible and is not a passed G1 closure", out.get("classifications") == {
    "passed": 1, "scope-gap": 1, "rejected": 0
} and out.get("actual") == 0.5, str(out))

bad = copy.deepcopy(discoveries)
bad[0].pop("authorization")
out = metrics.compute_g1(future, bad, results, "OK", now, "OK")
check("discovery missing required field is UNKNOWN", out.get("status") == "UNKNOWN", str(out))

bad = copy.deepcopy(discoveries)
bad.append({**bad[0], "source": "conflicting-source"})
out = metrics.compute_g1(future, bad, results, "OK", now, "OK")
check("conflicting duplicate discovery_id is UNKNOWN", out.get("status") == "UNKNOWN", str(out))

duplicate = [discoveries[0], {**discoveries[0]}, *discoveries[1:]]
out = metrics.compute_g1(future, duplicate, results, "OK", now, "OK")
check("duplicate discovery_id is UNKNOWN rather than silently deduplicated", out.get("status") == "UNKNOWN", str(out))

retry_results = [
    {"discovery_id": "d-passed", "gate": "rejected", "finished": "2026-07-30T11:30:00Z"},
    {"discovery_id": "d-passed", "gate": "passed", "finished": "2026-07-30T11:40:00Z"},
    *results[1:],
]
out = metrics.compute_g1(future, discoveries, retry_results, "OK", now, "OK")
check("repair retry uses latest terminal attempt instead of poisoning G1",
      out.get("classifications", {}).get("passed") == 1
      and out.get("classifications", {}).get("rejected") == 0, str(out))

same_time = [
    {"discovery_id": "d-passed", "gate": "rejected", "finished": "2026-07-30T11:30:00Z"},
    {"discovery_id": "d-passed", "gate": "passed", "finished": "2026-07-30T11:30:00Z"},
    *results[1:],
]
out = metrics.compute_g1(future, discoveries, same_time, "OK", now, "OK")
check("same-time conflicting retry remains UNKNOWN",
      out.get("status") == "UNKNOWN", str(out))

print("negtest-g1-discovery-cohort:", "ALL PASS" if not fails else "%d FAIL" % fails)
sys.exit(1 if fails else 0)
