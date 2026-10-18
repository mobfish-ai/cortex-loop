#!/usr/bin/env python3
"""B2 杀手负测：discovery 必须冻结且可追溯；learning 只能来自有效 passed 世界证据。"""
import contextlib
import importlib.machinery
import importlib.util
import io
import os
from types import SimpleNamespace


ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
ENGINE = os.path.join(ROOT, "bin", "cortex-loop")
loader = importlib.machinery.SourceFileLoader("cortex_loop_discovery_fixture", ENGINE)
spec = importlib.util.spec_from_loader(loader.name, loader)
cl = importlib.util.module_from_spec(spec)
loader.exec_module(cl)


def check(label, ok, detail=""):
    if not ok:
        raise AssertionError("%s: %s" % (label, detail))
    print("  PASS %s" % label)


def candidate():
    return {
        "id": "scanner-1", "source": "scanner", "title": "fixture",
        "requires": "exec.mock", "bounds": "skills/", "min_trust": "L1",
        "reversible": "yes", "value": "V1", "weight": "1", "artifact": "-",
        "short_test": "true", "approved_by": "-",
    }


def frozen_discovery_is_stable_and_source_reaches_receipt():
    names = ("rev_ref", "read_ref", "write_ref", "node_id")
    saved = {name: getattr(cl, name) for name in names}
    refs, writes = {}, []
    try:
        cl.rev_ref = lambda ref: "sha" if ref in refs else ""
        cl.read_ref = lambda ref: refs.get(ref, "")
        def write_ref(ref, payload, **_kwargs):
            if ref in refs:
                return False, "exists"
            refs[ref] = payload
            writes.append((ref, payload))
            return True, "sha"
        cl.write_ref = write_ref
        cl.node_id = lambda: "node-a"
        first, second = candidate(), candidate()
        first_id = cl.freeze_discovery(first, "auto-first")
        second_id = cl.freeze_discovery(second, "auto-rerun")
        discovery = cl.parse_kv(refs["%s/%s" % (cl.DISCOVERY_NS, first_id)])
        line = cl.plan_task_line(first)
        cl.read_ref = lambda _ref: line
        task = cl.plan_tasks("auto-first")[0]
        receipt = cl.parse_kv(cl.run_receipt_payload(
            "auto-first", task, {"holder": "node-a", "since": "2026-07-30T00:00"},
            "mock", "done", "passed", world_verified_at="2026-07-30T00:01"))
        check("stable source+candidate creates one immutable discovery cohort",
              first_id == second_id and len(writes) == 1 and discovery.get("plan") == "auto-first"
              and discovery.get("source") == "scanner" and discovery.get("candidate") == "scanner-1",
              repr(discovery))
        check("frozen source lineage reaches task and result receipt",
              task.get("source") == "scanner" and task.get("discovery_id") == first_id
              and receipt.get("candidate_source") == "scanner"
              and receipt.get("discovery_id") == first_id,
              repr(receipt))
    finally:
        for name, value in saved.items():
            setattr(cl, name, value)


def receipt(plan, task, discovery_id, gate="passed"):
    return {
        "receipt": "run-v1", "plan": plan, "candidate": task,
        "candidate_source": "scanner", "discovery_id": discovery_id,
        "claim_holder": "node-a", "claim_since": "2026-07-30T00:00", "executor": "mock",
        "gate": gate, "status": "done", "artifact": "-", "verification_command": "true",
        "world_verified_at": "2026-07-30T00:01", "node": "node-a",
        "trigger_kind": "clock-auto",
    }


def gather_only_learns_from_frozen_passed_receipts():
    names = ("fetch_refs", "plan_tasks", "read_ref", "rev_ref", "write_ref", "node_id")
    saved = {name: getattr(cl, name) for name in names}
    refs, writes = {}, []
    did = cl.stable_discovery_id("scanner", "T-pass")
    try:
        cl.fetch_refs = lambda: True
        cl.node_id = lambda: "node-gather"
        cl.plan_tasks = lambda plan: [{"id": {"p-pass": "T-pass", "p-scope": "T-scope",
                                               "p-manual": "T-manual"}[plan]}]
        refs["%s/%s" % (cl.DISCOVERY_NS, did)] = (
            "discovery_id=%s\nsource=scanner\ncandidate=T-pass\nplan=p-pass" % did)
        def read_ref(ref):
            if ref in refs:
                return refs[ref]
            if "/result/" in ref:
                plan, task = ref.rsplit("/", 2)[-2:]
                data = {
                    ("p-pass", "T-pass"): receipt("p-pass", "T-pass", did),
                    ("p-scope", "T-scope"): receipt("p-scope", "T-scope", did, "scope-gap"),
                    ("p-manual", "T-manual"): receipt("p-manual", "T-manual", "-"),
                }[(plan, task)]
                return "\n".join("%s=%s" % item for item in data.items())
            return "holder=node-a"
        cl.read_ref = read_ref
        cl.rev_ref = lambda ref: ("a" * 40) if ref in refs or "/result/" in ref else ""
        def write_ref(ref, payload, **_kwargs):
            if ref in refs:
                return False, "exists"
            refs[ref] = payload
            writes.append((ref, payload))
            return True, "sha"
        cl.write_ref = write_ref
        with contextlib.redirect_stdout(io.StringIO()):
            pass_rc = cl.cmd_gather(SimpleNamespace(plan="p-pass", settle=False))
            second_rc = cl.cmd_gather(SimpleNamespace(plan="p-pass", settle=False))
            scope_rc = cl.cmd_gather(SimpleNamespace(plan="p-scope", settle=False))
            manual_rc = cl.cmd_gather(SimpleNamespace(plan="p-manual", settle=False))
        learning_ref = "%s/%s" % (cl.LEARNING_NS, did)
        learning = cl.parse_kv(refs.get(learning_ref, ""))
        check("only frozen passed receipt publishes one idempotent learning candidate",
              pass_rc == second_rc == 0 and len(writes) == 1 and learning.get("discovery") == did
              and learning.get("result", "").endswith("/p-pass/T-pass")
              and learning.get("verification") == "true"
              and learning.get("discovery_oid") == "a" * 40
              and learning.get("result_oid") == "a" * 40
              and learning.get("trigger_kind") == "clock-auto"
              and learning.get("created_by") == "node-gather",
              repr(learning))
        check("scope-gap and missing frozen discovery do not count as learning",
              scope_rc == manual_rc == 0 and "%s/%s" % (cl.LEARNING_NS,
              cl.stable_discovery_id("scanner", "T-scope")) not in refs
              and len(writes) == 1,
              repr(refs))
    finally:
        for name, value in saved.items():
            setattr(cl, name, value)


frozen_discovery_is_stable_and_source_reaches_receipt()
gather_only_learns_from_frozen_passed_receipts()
print("fixture-discovery-learning: ALL PASS")
