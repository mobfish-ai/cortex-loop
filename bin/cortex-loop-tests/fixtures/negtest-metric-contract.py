#!/usr/bin/env python3
"""Negative tests for the S1 structured metric contract.

The test intentionally checks approval mechanics, not a preferred target number.
"""
import copy
import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = ROOT / "bin/cortex-metrics.py"
CONTRACT_PATH = ROOT / "brain-network/directions/loop-ops/METRICS.json"
spec = importlib.util.spec_from_file_location("cortex_metrics", MODULE_PATH)
metrics = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules[spec.name] = metrics
spec.loader.exec_module(metrics)

fails = 0


def check(name, ok, detail=""):
    global fails
    if ok:
        print("  PASS", name)
    else:
        fails += 1
        print("  FAIL", name, detail)


contract = metrics.load_contract(CONTRACT_PATH)
errors = metrics.validate_contract(contract)
check("real S1 contract validates", not errors, "; ".join(errors))
check("ratified operating targets are active and evidence-bound", all(
    item["target"]["status"] == "ACTIVE"
    and item["target"]["value"] == 0.9
    and item["target"].get("approval_ref")
    and item["baseline"]["status"] == "COMPLETE"
    for item in contract["metrics"]
), "an ACTIVE target must retain its approval evidence and completed baseline")
check("G1 and G2 preserve passed/scope-gap/rejected separately", all(
    set(metrics.GATES).issubset(item["classifications"])
    for item in contract["metrics"]
), "a missing category silently collapses a terminal state")
g1 = next(item for item in contract["metrics"] if item["legacy_name"] == "G1")
check("G1 discovery source is enabled only with its event namespace", g1["source"].get("available") is True
      and g1["source"].get("discovery_events") == "refs/swarm/cortex/discovery/*", str(g1["source"]))

bad = copy.deepcopy(contract)
g2 = next(item for item in bad["metrics"] if item["legacy_name"] == "G2")
g2["target"].pop("approval_ref")
errors = metrics.validate_contract(bad)
check("active target without approval evidence is rejected", any("approval_ref" in error for error in errors), str(errors))

bad = copy.deepcopy(contract)
g2 = next(item for item in bad["metrics"] if item["legacy_name"] == "G2")
g2["baseline"]["status"] = "COLLECTING"
errors = metrics.validate_contract(bad)
check("active target without complete baseline is rejected", any("COMPLETE baseline" in error for error in errors), str(errors))

bad = copy.deepcopy(contract)
g2 = next(item for item in bad["metrics"] if item["legacy_name"] == "G2")
g2["window"]["duration_seconds"] = None
g2["min_sample"]["value"] = None
errors = metrics.validate_contract(bad)
check("active target without declared window/sample is rejected", any("rolling window" in error for error in errors)
      and any("min_sample" in error for error in errors), str(errors))

bad = copy.deepcopy(contract)
g2 = next(item for item in bad["metrics"] if item["legacy_name"] == "G2")
g2["classifications"].pop("scope-gap")
errors = metrics.validate_contract(bad)
check("removing scope-gap classification is rejected", any("scope-gap" in error for error in errors), str(errors))

print("negtest-metric-contract:", "ALL PASS" if not fails else "%d FAIL" % fails)
sys.exit(1 if fails else 0)
