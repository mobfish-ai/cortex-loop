#!/usr/bin/env python3
"""Dashboard v2 contract regression.

Covers the failures that are easiest to hide behind a visually healthy screen:
- a real empty result window must not produce ``0\n0`` or arithmetic failure;
- G1/G2 values use ratio floats, while deprecated flat fields are percent;
- rolling and cumulative records stay separate; scope-gap/rejected never enter passed;
- strict discovery/result/learning canaries remain independent of the health score;
- deletion, mutation, bad time order, or bad ref OID can never produce canary green;
- guardrails remain UNKNOWN even when both lineage canaries pass;
- S2 is NOT_RUN until an explicit S2 contract exists;
- EXPECTATIONS without owner+short_test remain non-eligible;
- the human first screen answers four concrete questions without fake green.
"""
from __future__ import annotations

import datetime as dt
import copy
import hashlib
import importlib.util
import re
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import uuid


ROOT = Path(__file__).resolve().parents[3]
DASH = ROOT / "bin" / "cortex-dashboard.sh"
CONTRACT = ROOT / "brain-network" / "directions" / "loop-ops" / "METRICS.json"
METRICS = ROOT / "bin" / "cortex-metrics.py"
METRICS_SPEC = importlib.util.spec_from_file_location("cortex_metrics_dashboard_test", METRICS)
METRICS_MODULE = importlib.util.module_from_spec(METRICS_SPEC)
assert METRICS_SPEC and METRICS_SPEC.loader
sys.modules[METRICS_SPEC.name] = METRICS_MODULE
METRICS_SPEC.loader.exec_module(METRICS_MODULE)
fails = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global fails
    if ok:
        print("PASS  " + name)
    else:
        fails += 1
        print("FAIL  %s%s" % (name, " — " + detail if detail else ""))


def run_dashboard(env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(DASH), *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )


TEST_RUNTIME = tempfile.TemporaryDirectory(prefix="cortex-dashboard-shared-fixture-")
TEST_RUNTIME_PATH = Path(TEST_RUNTIME.name)
TEST_TRUST_TABLE = TEST_RUNTIME_PATH / "trust-table.txt"
TEST_TRUST_EVENTS = TEST_RUNTIME_PATH / "trust-events.json"
TEST_AI_LOCAL = TEST_RUNTIME_PATH / "ai-local.json"
TEST_AI_QUOTA = TEST_RUNTIME_PATH / "ai-quota.json"
TEST_WORKTREE_FLEET = TEST_RUNTIME_PATH / "worktree-fleet.json"
TEST_TRUST_TABLE.write_text(
    "| node | HAAS | level | auto-run | basis |\n"
    "|------|------|------|----------|------|\n"
    "| orchestrator-fixture | 0.650 | L2 | suggest-only | fixture |\n"
    "| worker-fixture | 0.470 | L1 | confirm each step | fixture |\n",
    encoding="utf-8",
)
TEST_TRUST_EVENTS.write_text(json.dumps({
    "state": "OK",
    "events": [{
        "node": "orchestrator-fixture", "kind": "mechanism-adopted",
        "label": "L5 adopted", "corrected_target": "worker-loop",
        "evidence": "reports/fixture-mechanism.md",
        "finished": "2026-08-01T12:00:00Z",
    }],
    "by_node": {},
}), encoding="utf-8")
TEST_AI_LOCAL.write_text("{}\n", encoding="utf-8")
TEST_AI_QUOTA.write_text("{}\n", encoding="utf-8")
TEST_WORKTREE_FLEET.write_text(json.dumps({
    "schema_version": "git-worktree-doctor/v1", "state": "OK",
    "summary": {"external_registered": 2, "claimed": 1, "in_use": 1,
                "managed_reclaimable": 0, "classifications": {"claimed_keep": 1}},
}), encoding="utf-8")


def dashboard_fixture_env(base: dict[str, str] | None = None) -> dict[str, str]:
    env = (base or os.environ).copy()
    workspace_fixture = TEST_RUNTIME_PATH / "workspace-observability"
    workspace_fixture.mkdir(exist_ok=True)
    env.update({
        "CORTEX_DASH_TEST_MODE": "1",
        "CORTEX_DASH_TRUST_TABLE_FILE": str(TEST_TRUST_TABLE),
        "CORTEX_DASH_TRUST_EVENTS_FILE": str(TEST_TRUST_EVENTS),
        "CORTEX_DASH_AI_LOCAL_FILE": str(TEST_AI_LOCAL),
        "CORTEX_DASH_AI_QUOTA_FILE": str(TEST_AI_QUOTA),
        "CORTEX_DASH_WORKTREE_JSON_FILE": str(TEST_WORKTREE_FLEET),
        "CORTEX_WORKSPACE_ROOT": str(workspace_fixture),
        "CORTEX_INTEGRATION_RECEIPT_ROOT": str(workspace_fixture / ".integration"),
        "CORTEX_WORKTREE_PARENT": str(TEST_RUNTIME_PATH / "managed-worktrees"),
        "CORTEX_WORKTREE_CLAIM_DIR": str(TEST_RUNTIME_PATH / "worktree-claims"),
        # Do not read or modify the real production guardrail ledger; this fixture tests "missing source = UNKNOWN".
        "CORTEX_OPENCLAW_STATE": str(TEST_RUNTIME_PATH / "missing-guardrail-state"),
    })
    return env


def lineage_events(now: dt.datetime) -> dict:
    discovered = now - dt.timedelta(minutes=10)
    claimed = now - dt.timedelta(minutes=8)
    world = now - dt.timedelta(minutes=2)
    finished = now - dt.timedelta(minutes=1)
    discovery_id = "d-" + hashlib.sha256(
        b"fixture-scanner\0c-canary"
    ).hexdigest()[:24]
    result_ref = "refs/swarm/cortex/result/p-canary/c-canary"
    return {
        "source_status": "OK",
        "learning_source_status": "OK",
        "discoveries": [{
            "oid": "a" * 40,
            "ref": "refs/swarm/cortex/discovery/" + discovery_id,
            "discovery_id": discovery_id,
            "discovered_at": discovered.isoformat(),
            "source": "fixture-scanner",
            "eligibility": "eligible",
            "authorization": "approved_by=fixture;reversible=true",
            "owner": "fixture-owner",
            "plan": "p-canary",
            "candidate": "c-canary",
        }],
        "results": [{
            "oid": "b" * 40,
            "ref": result_ref,
            "receipt": "run-v1",
            "plan": "p-canary",
            "candidate": "c-canary",
            "candidate_source": "fixture-scanner",
            "discovery_id": discovery_id,
            "claim_holder": "fixture-node",
            "claim_since": claimed.isoformat(),
            "executor": "fixture-executor",
            "status": "done",
            "artifact": "-",
            "finished": finished.isoformat(),
            "gate": "passed",
            "verification_command": "python3 -m compileall fixture",
            "world_verified_at": world.isoformat(),
            "trigger_kind": "clock-auto",
        }],
        "learnings": [{
            "oid": "c" * 40,
            "ref": "refs/swarm/cortex/learning/" + discovery_id,
            "discovery": discovery_id,
            "discovery_ref": "refs/swarm/cortex/discovery/" + discovery_id,
            "discovery_oid": "a" * 40,
            "result": result_ref,
            "result_oid": "b" * 40,
            "artifact": "-",
            "origin": "-",
            "verification": "python3 -m compileall fixture",
            "world_verified_at": world.isoformat(),
            "created_by": "fixture-node",
            "created_at": now.isoformat(),
            "trigger_kind": "clock-auto",
        }],
    }


def verify_bulk_origin_reader() -> None:
    with tempfile.TemporaryDirectory(prefix="cortex-metrics-bulk-") as tmp:
        fixture = Path(tmp)
        remote = fixture / "origin.git"
        work = fixture / "work"
        subprocess.run(["git", "init", "--bare", "-q", str(remote)], check=True)
        subprocess.run(["git", "init", "-q", str(work)], check=True)
        subprocess.run(["git", "-C", str(work), "config", "user.name", "metrics-test"], check=True)
        subprocess.run(
            ["git", "-C", str(work), "config", "user.email", "metrics-test@example.invalid"],
            check=True,
        )
        subprocess.run(["git", "-C", str(work), "remote", "add", "origin", str(remote)], check=True)
        for namespace in ("result", "discovery", "learning"):
            payload = work / "payload"
            payload.write_text("fixture=%s\n" % namespace, encoding="utf-8")
            subprocess.run(["git", "-C", str(work), "add", "payload"], check=True)
            subprocess.run(
                ["git", "-C", str(work), "commit", "-qm", "fixture " + namespace],
                check=True,
            )
            subprocess.run(
                [
                    "git", "-C", str(work), "push", "-q", "origin",
                    "HEAD:refs/swarm/bulk/%s/fixture" % namespace,
                ],
                check=True,
            )
        head_oid = subprocess.check_output(
            ["git", "-C", str(work), "rev-parse", "HEAD"], text=True
        ).strip()
        subprocess.run(
            ["git", "-C", str(work), "push", "-q", "origin", "HEAD:refs/heads/fixture-artifact"],
            check=True,
        )
        artifact_pairs = METRICS_MODULE.reachable_artifacts(
            work,
            [{"artifact": "payload", "origin_commit": head_oid}],
            [head_oid],
        )
        check("origin reachability binds commit x artifact blob",
              artifact_pairs == {(head_oid, "payload")}, str(artifact_pairs))
        missing_pairs = METRICS_MODULE.reachable_artifacts(
            work,
            [{"artifact": "missing.md", "origin_commit": head_oid}],
            [head_oid],
        )
        check("an artifact missing from a reachable commit still must not pass", missing_pairs == set())
        check("artifact path traversal and absolute paths are rejected",
              not METRICS_MODULE.artifact_path_is_safe("../payload")
              and not METRICS_MODULE.artifact_path_is_safe("/payload")
              and METRICS_MODULE.artifact_path_is_safe("payload"))
        started = time.monotonic()
        proc = subprocess.run(
            [
                sys.executable, str(METRICS), "--repo", str(work),
                "--swarm", "bulk", "--json",
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        elapsed = time.monotonic() - started
        payload = json.loads(proc.stdout)
        states = payload.get("lineage_evidence", {}).get("source_states", {})
        check("origin three namespaces are read in one batch", proc.returncode == 0 and set(states.values()) == {"OK"})
        check("local origin fixture reads do not fetch once per ref", elapsed < 5, "%.2fs" % elapsed)

        dash_env = dashboard_fixture_env()
        dash_env.update({
            "CORTEX_METRICS_REPO": str(work),
            "CORTEX_SWARM": "bulk",
            "CORTEX_S2_RESULT": str(fixture / "missing-s2.json"),
        })
        started = time.monotonic()
        dash = run_dashboard(dash_env, "--json")
        dash_elapsed = time.monotonic() - started
        check("Dashboard local origin real path emits valid JSON",
              dash.returncode == 0 and isinstance(json.loads(dash.stdout), dict))
        check("Dashboard JSON total time stays in budget (<15s)", dash_elapsed < 15, "%.2fs" % dash_elapsed)


base_env = dashboard_fixture_env()
base_env["CORTEX_METRICS_REPO"] = str(TEST_RUNTIME_PATH / "no-origin-repo")
(TEST_RUNTIME_PATH / "no-origin-repo").mkdir()
base_env["CORTEX_SWARM"] = "negtest-empty-%s" % uuid.uuid4().hex
base_env["CORTEX_S2_RESULT"] = "/private/tmp/cortex-s2-missing-%s.json" % uuid.uuid4().hex
verify_bulk_origin_reader()

# 1) Production path with a genuinely empty local result namespace.
r = run_dashboard(base_env, "--json")
check("empty-window dashboard exits cleanly", r.returncode == 0, r.stderr.strip()[:300])
try:
    empty = json.loads(r.stdout)
    check("empty-window output is valid JSON", True)
except Exception as exc:
    print("FAIL  JSON invalid: %s\nraw: %s" % (exc, r.stdout[:300]))
    sys.exit(1)

required = {
    "schema_version", "ts", "summary", "metric_contract", "g1", "g2",
    "lineage_evidence", "guardrails", "evidence_state", "stages", "expectations",
    "health_diagnostic", "runtime", "rate", "goal_rate", "deprecated_fields",
}
check("canonical top-level fields are complete", required <= set(empty), str(required - set(empty)))
check("schema_version is fixed at cortex-dashboard/v2",
      empty.get("schema_version") == "cortex-dashboard/v2")

runtime = empty.get("runtime", {})
check("a real empty result window has ticks_prod=0", runtime.get("ticks_prod") == 0)
check("a real empty window does not fake green: load=0/idle=100",
      runtime.get("load_pct") == 0 and runtime.get("idle_pct") == 100)

valid_states = {
    "UNMEASURED", "BASELINE", "INSUFFICIENT_SAMPLE", "UNKNOWN", "PASS", "FAIL"
}
for name in ("g1", "g2"):
    metric = empty.get(name, {})
    needed = {
        "metric_id", "unit", "sample_state", "value", "numerator", "denominator",
        "threshold", "threshold_state", "source_state", "rolling_window",
        "cumulative_record", "reason",
    }
    check("%s canonical metric fields are complete" % name, needed <= set(metric), str(needed - set(metric)))
    check("%s unit=ratio" % name, metric.get("unit") == "ratio")
    check("%s sample_state is legal" % name, metric.get("sample_state") in valid_states)
    if metric.get("sample_state") in {"UNMEASURED", "UNKNOWN"}:
        check("%s value=null when evidence is missing" % name, metric.get("value") is None)
check("G1 stays UNKNOWN/null when origin is unreadable",
      empty.get("g1", {}).get("sample_state") in {"UNKNOWN", "UNMEASURED"}
      and empty.get("g1", {}).get("value") is None)

guards = empty.get("guardrails", {})
items = guards.get("items", [])
check("guardrails aggregate to UNKNOWN", guards.get("state") == "UNKNOWN")
check("every unwired event-source guardrail is UNKNOWN/null",
      bool(items) and all(g.get("state") == "UNKNOWN" and g.get("observed_events") is None
                          for g in items))

evidence = empty.get("evidence_state", {})
check("evidence_state is independent and does not drift green with health",
      evidence.get("state") != "COMPLETE"
      and evidence.get("production_complete") is False
      and evidence.get("independent_of_health_score") is True)
empty_lineage = empty.get("lineage_evidence", {})
check("empty lineage has no fake-green canary",
      empty_lineage.get("valid_receipts") == 0
      and empty_lineage.get("full_lineages") == 0
      and empty_lineage.get("s0_canary") != "S0_CANARY_PASSED"
      and empty_lineage.get("s1_canary") != "S1_CANARY_PASSED")
check("health is explicitly not stage evidence",
      empty.get("health_diagnostic", {}).get("is_stage_evidence") is False)
check("S2 is NOT_RUN before it is authorized",
      empty.get("stages", {}).get("s2", {}).get("state") == "NOT_RUN"
      and empty.get("stages", {}).get("s2", {}).get("authority") == "NOT_GRANTED")

expect = empty.get("expectations", {})
check("EXPECTATIONS total/eligible/non_eligible are all present",
      all(k in expect for k in ("total", "eligible", "non_eligible")))
if expect.get("state") == "OK":
    check("EXPECTATIONS keeps old short rows intact",
          expect.get("total") == 20)
    check("EXPECTATIONS partitions conserve the total",
          expect.get("eligible", 0) + expect.get("non_eligible", 0) == expect.get("total"))
    check("only expectations that are not closed may enter the execution queue",
          expect.get("eligible", 0) <= expect.get("gap", 0) + expect.get("unknown", 0))
    check("EXPECTATIONS has absorbed live S1 evidence",
          expect.get("met", 0) >= 3)

# 2) Offline active-contract fixture proves that ratios remain floats and the
# three terminal classifications cannot collapse into one pass bucket.
with tempfile.TemporaryDirectory(prefix="cortex-dash-contract-") as tmp:
    tmp_path = Path(tmp)
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    g2_spec = next(m for m in contract["metrics"] if m["legacy_name"] == "G2")
    g2_spec["window"]["duration_seconds"] = 86400
    g2_spec["min_sample"]["value"] = 1
    g2_spec["baseline"] = {"status": "COMPLETE", "evidence_ref": "fixture"}
    g2_spec["target"] = {
        "status": "ACTIVE", "operator": ">=", "value": 0.5,
        "approved_by": "fixture-human", "approval_ref": "fixture",
        "effective_at": "2026-07-29T00:00:00Z",
    }
    contract_path = tmp_path / "contract.json"
    contract_path.write_text(json.dumps(contract), encoding="utf-8")

    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    events = {
        "source_status": "OK",
        "results": [
            {"finished": now.isoformat(), "gate": "passed"},
            {"finished": now.isoformat(), "gate": "scope-gap"},
            {"finished": now.isoformat(), "gate": "rejected"},
        ],
        "discoveries": [],
    }
    events_path = tmp_path / "events.json"
    events_path.write_text(json.dumps(events), encoding="utf-8")
    s2_path = tmp_path / "s2-result.json"
    s2_path.write_text(json.dumps({
        "stage_judgement": "S2_PILOT_EVIDENCE_ONLY",
        "verdict_vs_inventory_baseline": "SUPPORTED",
        "evaluated_cases": 91,
        "heuristic": {"hit_at_5": 0.120879},
        "baseline": {"hit_at_5": 0.0},
    }), encoding="utf-8")

    fixture_env = base_env.copy()
    fixture_env.update({
        "CORTEX_DASH_TEST_MODE": "1",
        "CORTEX_METRICS_CONTRACT": str(contract_path),
        "CORTEX_METRICS_EVENTS": str(events_path),
        "CORTEX_S2_RESULT": str(s2_path),
    })
    positive_r = run_dashboard(fixture_env, "--json")
    check("ratio fixture dashboard exits cleanly", positive_r.returncode == 0,
          positive_r.stderr.strip()[:300])
    positive = json.loads(positive_r.stdout)
    check("ACTIVE G1 empty cohort is explicitly an insufficient sample",
          positive.get("g1", {}).get("sample_state") == "INSUFFICIENT_SAMPLE"
          and positive.get("g1", {}).get("value") is None)
    g2 = positive["g2"]
    check("G2 canonical value stays a ratio float=1/3",
          isinstance(g2.get("value"), float) and abs(g2["value"] - (1 / 3)) < 1e-9)
    check("G2 threshold stays ratio=0.5", g2.get("threshold") == 0.5)
    rolling = g2.get("rolling_window", {})
    check("rolling window keeps passed/scope-gap/rejected apart",
          rolling == {
              "passed": 1, "scope-gap": 1, "rejected": 1,
              "denominator": 3, "unclassified": 0,
          })
    check("scope-gap/rejected did not enter the passed numerator",
          g2.get("numerator") == 1 and g2.get("denominator") == 3)
    cumulative = g2.get("cumulative_record", {})
    check("cumulative ledger stays separate from the rolling window and cannot feed the target",
          cumulative.get("passed") == 1
          and cumulative.get("scope-gap") == 1
          and cumulative.get("rejected") == 1
          and cumulative.get("ledger_only") is True
          and cumulative.get("target_eligible") is False)

    legacy_window_events = copy.deepcopy(events)
    legacy_window_events["results"].append({
        "finished": (now - dt.timedelta(days=2)).isoformat(),
        "gate": "noop",
    })
    events_path.write_text(json.dumps(legacy_window_events), encoding="utf-8")
    legacy_proc = subprocess.run(
        [
            sys.executable, str(METRICS), "--json", "--contract", str(contract_path),
            "--events", str(events_path), "--now", now.isoformat(),
        ],
        cwd=ROOT, capture_output=True, text=True, timeout=60,
    )
    legacy_g2 = json.loads(legacy_proc.stdout).get("g2", {})
    check("legacy noop outside the rolling window is only data debt and does not poison current G2",
          legacy_g2.get("sample_state") == "FAIL"
          and legacy_g2.get("denominator") == 3
          and legacy_g2.get("cumulative_record", {}).get("unclassified") == 1)

    current_noop_events = copy.deepcopy(events)
    current_noop_events["results"].append({"finished": now.isoformat(), "gate": "noop"})
    events_path.write_text(json.dumps(current_noop_events), encoding="utf-8")
    current_noop_proc = subprocess.run(
        [
            sys.executable, str(METRICS), "--json", "--contract", str(contract_path),
            "--events", str(events_path), "--now", now.isoformat(),
        ],
        cwd=ROOT, capture_output=True, text=True, timeout=60,
    )
    current_noop_g2 = json.loads(current_noop_proc.stdout).get("g2", {})
    check("an unknown gate inside the rolling window still fails closed as UNKNOWN",
          current_noop_g2.get("sample_state") == "UNKNOWN"
          and current_noop_g2.get("unclassified") == 1)

    events_path.write_text(json.dumps(events), encoding="utf-8")
    check("compat flat rate is a percent and explicitly deprecated",
          abs(positive.get("rate") - (100 / 3)) < 1e-9
          and positive["deprecated_fields"]["rate"] ==
              {"deprecated": True, "unit": "percent", "maps_to": "g2.value"})
    check("the S2 read-only pilot is consumed by the same Dashboard source and promotion is forbidden",
          positive.get("stages", {}).get("s2", {}).get("state") == "S2_PILOT_EVIDENCE_ONLY"
          and positive.get("s2_pilot", {}).get("authority") == "AUTHORIZED_SHADOW"
          and positive.get("s2_pilot", {}).get("promotion") == "FORBIDDEN"
          and positive.get("s2_pilot", {}).get("evaluated_cases") == 91)

    # 3) A complete immutable lineage proves only S0/S1 canaries.  It never
    # promotes the overall evidence state while guardrail sources are UNKNOWN.
    full_events = lineage_events(now)
    events_path.write_text(json.dumps(full_events), encoding="utf-8")
    canary_r = run_dashboard(fixture_env, "--json")
    check("complete lineage dashboard exits cleanly", canary_r.returncode == 0,
          canary_r.stderr.strip()[:300])
    canary = json.loads(canary_r.stdout)
    lineage = canary.get("lineage_evidence", {})
    check("a complete run-v1 receipt lets only the S0 canary pass",
          lineage.get("valid_receipts") == 1
          and lineage.get("receipt_bound") == 1
          and lineage.get("origin_reachable") == 1
          and lineage.get("s0_canary") == "S0_CANARY_PASSED")
    check("an exact learning binding lets the S1 canary pass",
          lineage.get("learning_linked") == 1
          and lineage.get("full_lineages") == 1
          and lineage.get("s1_canary") == "S1_CANARY_PASSED")
    check("G1 correctly reads the result/discovery dual source fields",
          canary.get("g1", {}).get("source_state") == "OK")
    check("ACTIVE G1 small cohort is explicitly an insufficient sample and must not claim the target",
          canary.get("g1", {}).get("sample_state") == "INSUFFICIENT_SAMPLE"
          and canary.get("g1", {}).get("denominator") == 1
          and canary.get("g1", {}).get("value") == 1.0)
    evidence_contract = canary.get("evidence_state", {})
    check("Dashboard does not name an unreplayed verification VERIFIED",
          evidence_contract.get("receipt_binding") == "BOUND"
          and evidence_contract.get("origin_reachability") == "REACHABLE"
          and evidence_contract.get("verification_replay") == "NOT_REPLAYED"
          and "world_verification" not in evidence_contract)
    check("Dashboard lineage keeps a single bounded summary",
          "lineage_evidence" not in evidence_contract
          and evidence_contract.get("lineage_ref") == "$.lineage_evidence"
          and len(lineage.get("invalid_samples", [])) <= 5)
    check("when guardrails are UNKNOWN the overall state is only CANARY_ONLY",
          canary.get("guardrails", {}).get("state") == "UNKNOWN"
          and canary.get("evidence_state", {}).get("state") == "CANARY_ONLY"
          and canary.get("evidence_state", {}).get("production_complete") is False)
    check("after S1 passes, the first-screen max blocker moves to unwired guardrails",
          "three event classes" in canary.get("summary", {}).get("max_blocker", "")
          and "three safety event sources" in canary.get("summary", {}).get("next_action", ""))

    # Metrics-level killer mutations are deterministic and cheap.  Each one
    # removes or tampers with one piece of the only positive lineage.
    def project(events: dict) -> dict:
        events_path.write_text(json.dumps(events), encoding="utf-8")
        proc = subprocess.run(
            [
                sys.executable, str(METRICS), "--json", "--contract", str(contract_path),
                "--events", str(events_path), "--now", now.isoformat(),
            ],
            cwd=ROOT, capture_output=True, text=True, timeout=60,
        )
        check("tamper-case metrics exit cleanly", proc.returncode == 0, proc.stderr[:200])
        return json.loads(proc.stdout).get("lineage_evidence", {})

    legacy_naive = copy.deepcopy(full_events)
    local_tz = now.astimezone().tzinfo
    for section, fields in (
        ("discoveries", ("discovered_at",)),
        ("results", ("claim_since", "world_verified_at", "finished")),
        ("learnings", ("world_verified_at", "created_at")),
    ):
        for record in legacy_naive[section]:
            for field in fields:
                parsed = dt.datetime.fromisoformat(record[field])
                record[field] = parsed.astimezone(local_tz).replace(tzinfo=None).isoformat(timespec="minutes")
    legacy_lineage = project(legacy_naive)
    check("an old local receipt with no offset is not misread as a future time",
          legacy_lineage.get("s1_canary") == "S1_CANARY_PASSED")

    deleted_learning = copy.deepcopy(full_events)
    deleted_learning["learnings"] = []
    deleted = project(deleted_learning)
    check("deleting learning: S0 stays, S1 must not go falsely green",
          deleted.get("s0_canary") == "S0_CANARY_PASSED"
          and deleted.get("s1_canary") != "S1_CANARY_PASSED"
          and deleted.get("full_lineages") == 0)

    deleted_result = copy.deepcopy(full_events)
    deleted_result["results"] = []
    no_result = project(deleted_result)
    check("deleting result: neither S0 nor S1 may go falsely green",
          no_result.get("s0_canary") != "S0_CANARY_PASSED"
          and no_result.get("s1_canary") != "S1_CANARY_PASSED"
          and no_result.get("valid_receipts") == 0
          and no_result.get("full_lineages") == 0)

    mutations = []
    for label, section, field, value in (
        ("tamper result receipt", "results", "receipt", "legacy"),
        ("tamper result status", "results", "status", "failed"),
        ("tamper result gate", "results", "gate", "scope-gap"),
        ("tamper result source", "results", "candidate_source", "other-scanner"),
        ("tamper world timestamp", "results", "world_verified_at",
         (now - dt.timedelta(minutes=20)).isoformat()),
        ("tamper finished order", "results", "finished",
         (now - dt.timedelta(minutes=9)).isoformat()),
        ("tamper result OID", "results", "oid", "bad-oid"),
        ("tamper result trigger", "results", "trigger_kind", "invalid-trigger"),
        ("tamper learning result ref", "learnings", "result",
         "refs/swarm/cortex/result/p-canary/other"),
        ("tamper learning discovery OID", "learnings", "discovery_oid", "d" * 40),
        ("tamper learning result OID", "learnings", "result_oid", "e" * 40),
        ("tamper learning trigger", "learnings", "trigger_kind", "manual"),
        ("tamper learning verification", "learnings", "verification", "true"),
        ("tamper learning world", "learnings", "world_verified_at",
         (now - dt.timedelta(minutes=3)).isoformat()),
        ("tamper learning OID", "learnings", "oid", "bad-oid"),
    ):
        mutated = copy.deepcopy(full_events)
        mutated[section][0][field] = value
        mutations.append((label, mutated))

    bad_discovery_oid = copy.deepcopy(full_events)
    bad_discovery_oid["discoveries"][0]["oid"] = "bad-oid"
    mutations.append(("tamper discovery OID", bad_discovery_oid))

    unstable_discovery = copy.deepcopy(full_events)
    unstable_discovery["discoveries"][0]["candidate"] = "other-candidate"
    mutations.append(("tamper stable discovery_id input", unstable_discovery))

    artifact_without_origin = copy.deepcopy(full_events)
    artifact_without_origin["results"][0]["artifact"] = "fixture.txt"
    artifact_without_origin["learnings"][0]["artifact"] = "fixture.txt"
    mutations.append(("artifact lacks a legal origin_commit", artifact_without_origin))

    unreachable_origin = copy.deepcopy(full_events)
    unreachable_origin["results"][0]["artifact"] = "fixture.txt"
    unreachable_origin["results"][0]["origin_commit"] = "d" * 40
    unreachable_origin["learnings"][0]["artifact"] = "fixture.txt"
    unreachable_origin["learnings"][0]["origin"] = "d" * 40
    unreachable = project(unreachable_origin)
    check("a legal 40-hex oid that origin cannot reach must not fake-green S1",
          unreachable.get("s1_canary") != "S1_CANARY_PASSED"
          and unreachable.get("full_lineages") == 0
          and "absent at origin_commit" in str(unreachable.get("invalid_reasons", [])))

    reachable_origin = copy.deepcopy(unreachable_origin)
    reachable_origin["reachable_origin_artifacts"] = [{
        "commit": "d" * 40,
        "artifact": "fixture.txt",
    }]
    reachable = project(reachable_origin)
    check("artifact lineage passes only for a commit reachable from an origin branch",
          reachable.get("s1_canary") == "S1_CANARY_PASSED"
          and reachable.get("origin_reachable") == 1)

    conflicting_learning = copy.deepcopy(full_events)
    conflict = copy.deepcopy(conflicting_learning["learnings"][0])
    conflict["verification"] = "different-command"
    conflict["oid"] = "d" * 40
    conflicting_learning["learnings"].append(conflict)
    mutations.append(("same-discovery learning conflict", conflicting_learning))

    conflicting_result = copy.deepcopy(full_events)
    result_conflict = copy.deepcopy(conflicting_result["results"][0])
    result_conflict["verification_command"] = "different-command"
    result_conflict["oid"] = "e" * 40
    conflicting_result["results"].append(result_conflict)
    mutations.append(("same-discovery result conflict", conflicting_result))

    for label, mutated in mutations:
        projected = project(mutated)
        check(label + " must not fake-green S1",
              projected.get("s1_canary") != "S1_CANARY_PASSED"
              and projected.get("full_lineages") == 0
              and projected.get("invalid_count", 0) > 0,
              str(projected))

    manual_lineage = copy.deepcopy(full_events)
    manual_lineage["results"][0]["trigger_kind"] = "manual"
    manual_lineage["learnings"][0]["trigger_kind"] = "manual"
    manual = project(manual_lineage)
    check("a human plan can prove S0, but must never impersonate unattended S1",
          manual.get("s0_canary") == "S0_CANARY_PASSED"
          and manual.get("s1_canary") != "S1_CANARY_PASSED"
          and manual.get("full_lineages") == 0)

    legacy_plus_valid = copy.deepcopy(full_events)
    legacy = copy.deepcopy(legacy_plus_valid["results"][0])
    legacy["discovery_id"] = "legacy-result"
    legacy["receipt"] = "legacy"
    legacy["oid"] = "f" * 40
    legacy_plus_valid["results"].append(legacy)
    coexistence = project(legacy_plus_valid)
    check("historical old debt keeps its warning, but must not permanently veto an independent real canary",
          coexistence.get("invalid_count", 0) > 0
          and coexistence.get("s0_canary") == "S0_CANARY_PASSED"
          and coexistence.get("s1_canary") == "S1_CANARY_PASSED")

    # Even a cosmetically healthy dashboard must preserve a tampered lineage as
    # UNKNOWN rather than borrowing the unrelated health score.
    events_path.write_text(json.dumps(mutations[0][1]), encoding="utf-8")
    tampered_r = run_dashboard(fixture_env, "--json")
    tampered = json.loads(tampered_r.stdout)
    check("health must not fake-green a tampered lineage stage",
          tampered.get("health_diagnostic", {}).get("is_stage_evidence") is False
          and tampered.get("stages", {}).get("s0", {}).get("state") != "S0_CANARY_PASSED"
          and tampered.get("stages", {}).get("s1", {}).get("state") != "S1_CANARY_PASSED")

    # Restore the ratio fixture for its human-render assertions below.
    events_path.write_text(json.dumps(events), encoding="utf-8")

    human_r = run_dashboard(fixture_env)
    human = human_r.stdout
    check("human output exits cleanly", human_r.returncode == 0, human_r.stderr.strip()[:300])
    for token in (
        "━━ task overview", "recently completed", "━━ execution and delivery", "task scratch",
        "dev workspaces", "claimed", "reclaimable", "━━ node scores",
        "━━ mechanism board", "L5 adopted", "worker-loop",
        "━━ quality and next step", "max blocker:", "TASKS.md",
    ):
        check("human first screen contains `%s`" % token, token in human)
    check("human first screen states the running condition",
          "no task is running" in human or "▶ running" in human)
    check("human first screen states the real-failure condition",
          "no real failures" in human or re.search(r"real failures\s+\d+", human) is not None)
    check("a historical settling rejection does not impersonate a current real failure",
          'status not in ("done", "settling")' in DASH.read_text(encoding="utf-8"))
    check("human first screen does not repeat a ledger block", "[ ledger ]" not in human)
    check("the max-blocker line contains a next-step arrow (the merged line still shows what to do next)",
          re.search(r"max blocker:.*→", human) is not None)
    check("human first screen has no evidence fake-green",
          "evidence state COMPLETE" not in human and "guardrails=OK" not in human)
    check("an unknown metric is not rendered as a minus percent", "-%" not in human)

    full_r = run_dashboard(fixture_env, "--full")
    full = full_r.stdout
    check("full diagnostic view exits cleanly", full_r.returncode == 0, full_r.stderr.strip()[:300])
    for token in (
        "1 is the system actually running?", "2 which stage are we at?", "🔴 problems first",
        "S2 shadow AUTHORIZED_SHADOW", "automatic promotion forbidden", "guardrails=UNKNOWN",
        "rolling window", "cumulative ledger", "scope-gap=1", "only passed is the numerator",
        "health score is not stage proof",
    ):
        check("full diagnostic contains `%s`" % token, token in full)

    snapshot_path = Path(tmp) / "dashboard-snapshot.md"
    snapshot_r = run_dashboard(fixture_env, "--md", str(snapshot_path))
    snapshot = snapshot_path.read_text(encoding="utf-8") if snapshot_path.exists() else ""
    check("dashboard --md writes a snapshot", snapshot_r.returncode == 0 and bool(snapshot))
    for token in (
        "status: snapshot",
        "generated_at:",
        "source_view: worktree",
        "base_commit:",
        "dirty:",
        "producer: bin/cortex-dashboard.sh",
        "freshness: on_demand_snapshot",
        "truth_consistency: OK",
    ):
        check("snapshot provenance contains `%s`" % token, token in snapshot)
    check("a living promise with no producer has been removed", "status: living" not in snapshot)

    provenance = json.loads(run_dashboard(fixture_env, "--json").stdout).get("provenance", {})
    check("machine JSON also exposes freshness/truth",
          provenance.get("freshness") == "on_demand_snapshot"
          and provenance.get("truth_consistency") == "OK"
          and provenance.get("producer") == "bin/cortex-dashboard.sh"
          and provenance.get("source_view") == "worktree"
          and isinstance(provenance.get("dirty"), bool)
          and bool(provenance.get("base_commit")))
    delivery = json.loads(run_dashboard(fixture_env, "--json").stdout).get("runtime", {}).get("delivery_plane", {})
    check("machine JSON also exposes the workspace/candidate/integration delivery plane",
          delivery.get("schema_version") == "cortex-workspace-observability/v1"
          and isinstance(delivery.get("summary"), dict))
    fleet = json.loads(run_dashboard(fixture_env, "--json").stdout).get("runtime", {}).get("worktree_fleet", {})
    check("machine JSON also exposes Agent worktree claim/use/reclaim",
          fleet.get("schema_version") == "git-worktree-doctor/v1"
          and isinstance(fleet.get("summary"), dict))

print()
print("dashboard v2 contract: %s (%d assertions failed)" %
      ("ALL PASS" if not fails else "FAILED", fails))
sys.exit(1 if fails else 0)
