#!/usr/bin/env python3
"""Asset-health scan: Path(ROOT) regression, count drift, stale threshold. Read-only, no network."""
from __future__ import annotations

import hashlib
import importlib.machinery
import importlib.util
import json
import os
import socket
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ENGINE = sys.argv[1] if len(sys.argv) > 1 else str(
    Path(__file__).resolve().parents[2] / "cortex-loop")
FIXTURE = Path(__file__).resolve().parent / "asset-health" / "registry.json"
SENTINEL = "SECRET_SENTINEL_do-not-leak"
NOW = datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)
SHAPE = {
    "id", "source", "title", "requires", "bounds", "min_trust",
    "reversible", "value", "weight", "artifact", "short_test", "approved_by",
}

loader = importlib.machinery.SourceFileLoader("cortex_loop_asset_health_test", ENGINE)
spec = importlib.util.spec_from_loader(loader.name, loader)
cl = importlib.util.module_from_spec(spec)
loader.exec_module(cl)

failures = []


def check(cond, msg):
    if cond:
        print("  PASS  %s" % msg)
    else:
        failures.append(msg)
        print("  FAIL  %s" % msg)


def write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def touch(path, when):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text("x\n", encoding="utf-8")
    epoch = when.timestamp() if isinstance(when, datetime) else float(when)
    os.utime(path, (epoch, epoch))


def snapshot(root):
    found = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [name for name in dirnames if name != "__pycache__"]
        for name in filenames:
            path = Path(dirpath) / name
            found[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return found


def ids(cands):
    return {item["id"] for item in cands}


def one(cands, cid):
    hits = [item for item in cands if item["id"] == cid]
    return hits[0] if len(hits) == 1 else None


def assert_shape(cand, msg):
    check(cand is not None and set(cand) == SHAPE, "%s candidate fields are complete" % msg)
    if not cand:
        return
    check(cand["source"] == "asset-health", "%s source" % msg)
    check(cand["min_trust"] == "L1", "%s low trust L1" % msg)
    check(cand["reversible"] == "yes", "%s reversible" % msg)
    check(cand["requires"] == "exec.claude", "%s requires" % msg)
    check(cand["approved_by"] == "-", "%s approved_by" % msg)
    check(SENTINEL not in json.dumps(cand, ensure_ascii=False), "%s does not contain file body text" % msg)


def run_short(cmd):
    proc = subprocess.run(
        cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=60)
    return proc.returncode, (proc.stdout + proc.stderr)[-400:]


def balanced_tree(root):
    """A small tree aligned with the source syntax in fixtures/asset-health/registry.json."""
    files = {
        "skills/SKILLS-TAXONOMY.md": "taxonomy\n",
        "skills/alpha/ERRORS.md": SENTINEL + "\nalpha\n",
        "skills/beta/ERRORS.md": "beta\n",
        "skills/alpha/nested/ERRORS.md": "nested-should-not-count\n",
        "skills/alpha/references/a.md": "ref-a\n",
        "skills/beta/references/sub/b.md": "ref-b\n",
        "bin/a.sh": "echo a\n",
        "bin/b.py": "print('b')\n",
        "bin/c.txt": "not a tool\n",
        "bin/nested/d.sh": "echo nested\n",
        "topics/evidence/EXPERIENCE-LEDGER.md": "ledger\n",
        "node_modules/hidden/EXPERIENCE-LEDGER.md": SENTINEL + "\n",
        "venv/lib/EXPERIENCE-LEDGER.md": SENTINEL + "\n",
        ".git/objects/EXPERIENCE-LEDGER.md": SENTINEL + "\n",
        "evidence/discovery-trees.jsonl": "{}\n",
        "dt-root.md": "tree\n",
        "skills/loop-engineering-hub/execution-recipes/one.md": "r1\n",
        "skills/loop-engineering-hub/execution-recipes/two.md": "r2\n",
        "RECIPE-REGISTRY.md": "registry\n",
        "work-studio/devops/infrastructure/data/nodes-registry.json": "{}\n",
    }
    for rel, body in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    reg = json.loads(FIXTURE.read_text(encoding="utf-8"))
    reg_path = root / "work-studio/devops/infrastructure/data/cortex-asset-registry.json"
    write_json(reg_path, reg)
    return reg_path


def test_root_stays_str():
    text = Path(ENGINE).read_text(encoding="utf-8")
    check(bool(__import__("re").search(r"^ROOT = os\.path\.dirname", text, __import__("re").M)),
          "global ROOT is still a str assignment")
    check("ROOT = Path(" not in text, "global ROOT was not changed to Path")
    check(isinstance(cl.ROOT, str), "loaded ROOT is a str")


def test_predicate_boundaries():
    # Exactly 2% or exactly 3 files does not report; report only when either bound is exceeded.
    check(not cl._asset_count_drifted(100, 102), "delta 2 / 100 = 2% does not report")
    check(cl._asset_count_drifted(100, 103), "delta 3 / 100 > 2% reports")
    check(not cl._asset_count_drifted(200, 203), "delta 3 and about 1.5% relative does not report")
    check(cl._asset_count_drifted(200, 204), "delta 4 reports even though it is under 2%")
    check(cl._asset_count_drifted(50, 52), "delta 2 but 4% relative reports (or, not and)")
    check(not cl._asset_count_drifted(0, 0), "registered 0 scanned 0 does not report")
    check(cl._asset_count_drifted(0, 1), "registered 0 scanned 1 reports because the relative bound is crossed")
    check(cl.ASSET_HEALTH_STALE_DAYS == 30, "default stale threshold is 30 days")
    check(abs(cl.ASSET_HEALTH_COUNT_REL - 0.02) < 1e-12, "relative threshold 2%")
    check(cl.ASSET_HEALTH_COUNT_ABS == 3, "absolute threshold is 3 files")


def test_glob_syntax():
    check(cl._asset_source_globs("bin/*.sh|py") == ["bin/*.sh", "bin/*.py"],
          "extension bar expands")
    # deliberate CJK fixture
    check(cl._asset_source_globs("skills/*/ERRORS.md（错题本，按域分布）")
          == ["skills/*/ERRORS.md"], "Chinese parenthetical is stripped")
    # deliberate CJK fixture
    check(cl._asset_source_globs("**/discovery-trees.jsonl + dt-*.md（发现树）")
          == ["**/discovery-trees.jsonl", "**/dt-*.md"], "a filename wildcard with no slash matches any depth")
    # deliberate CJK fixture
    check(cl._asset_source_globs("cortex-harness 席 AAR-014 同批") == [],
          "prose is not a glob")
    check(cl._asset_source_globs("skills/SKILLS-TAXONOMY.md")
          == ["skills/SKILLS-TAXONOMY.md"], "a concrete file is also a countable source")


def test_balanced_and_path_root():
    with tempfile.TemporaryDirectory(prefix="asset-health-") as tmp:
        root = Path(tmp)
        reg_path = balanced_tree(root)
        before = snapshot(root)
        saved = cl.ROOT
        blocked = {"calls": 0}

        class Guard:
            def __init__(self, *args, **kwargs):
                blocked["calls"] += 1
                raise AssertionError("scan opened a socket")

        orig_socket = socket.socket
        socket.socket = Guard
        cl.ROOT = str(root)  # production ROOT is a str; this recreates the old TypeError path
        try:
            cands = cl.scan_asset_health(now=NOW)
        finally:
            cl.ROOT = saved
            socket.socket = orig_socket
        check(blocked["calls"] == 0, "the scan opens no socket")
        check(snapshot(root) == before, "the scan does not change file bytes")
        check(isinstance(cl.ROOT, str) and cl.ROOT == saved, "the scan does not change global ROOT")
        check("asset-health-count-tools" not in ids(cands), "an aligned tools count does not report")
        check("asset-health-count-errors" not in ids(cands), "an aligned errors count does not report")
        check("asset-health-count-ledgers" not in ids(cands), "ledgers align after dependency directories are skipped")
        check("asset-health-count-skills" not in ids(cands), "the concrete skills file count aligns")
        check("asset-health-count-discovery_trees" not in ids(cands), "the two discovery-tree globs align")
        check("asset-health-count-references" not in ids(cands), "files under references align")
        check("asset-health-count-recipes" not in ids(cands), "recipes directory plus root file dedupe and align")
        check("asset-health-count-agent_skins" not in ids(cands), "a prose source is not compared as a count")
        check("asset-health-count-directions" not in ids(cands), "a count with no source is not compared")
        check("asset-health-nodes" not in ids(cands), "an existing referenced file is not reported missing")
        check("asset-health-stale-registry" not in ids(cands), "a future updated_at is not stale")
        blob = json.dumps(cands, ensure_ascii=False)
        check(SENTINEL not in blob, "candidates do not contain file body text")
        # Raise the tools registration. The same tree must report drift, and the short test can be repaired by file count.
        reg = json.loads(reg_path.read_text(encoding="utf-8"))
        reg["segments"]["tools"]["count"] = 10
        write_json(reg_path, reg)
        cands = cl.scan_asset_health(root=root, now=NOW)
        cand = one(cands, "asset-health-count-tools")
        assert_shape(cand, "tools drift")
        if cand:
            check("declared 10, scanned 2" in cand["title"], "the drift title carries the declared count and the scanned count")
            code, err = run_short(cand["short_test"])
            check(code == 1, "short test fails while drift is unfixed code=%s %s" % (code, err))
            (root / "bin" / "e.sh").write_text("echo e\n", encoding="utf-8")
            # The original 2 plus these 8 = the registered 10. A 2% relative threshold on a denominator of 10 allows a delta of 0.
            for i in range(7):
                (root / "bin" / ("extra-%d.sh" % i)).write_text("echo\n", encoding="utf-8")
            code, err = run_short(cand["short_test"])
            check(code == 0, "the same short test passes after the files are filled in code=%s %s" % (code, err))


def test_or_on_filesystem():
    with tempfile.TemporaryDirectory(prefix="asset-health-or-") as tmp:
        root = Path(tmp)
        batch = root / "batch"
        batch.mkdir()
        for i in range(200):
            (batch / ("%03d.txt" % i)).write_text("x\n", encoding="utf-8")
        reg_path = root / "reg.json"

        def scan(declared):
            write_json(reg_path, {
                "_meta": {"updated_at": "2099-01-01T00:00:00Z"},
                "segments": {"batch": {"count": declared, "source": "batch/*.txt"}},
            })
            return ids(cl.scan_asset_health(root=root, registry_path=reg_path, now=NOW))

        check("asset-health-count-batch" not in scan(200), "200=200 does not report")
        check("asset-health-count-batch" not in scan(203), "delta 3 and under 2% relative does not report")
        check("asset-health-count-batch" in scan(204), "a delta of 4 files reports")
        check("asset-health-count-batch" in scan(190), "a relative delta above 2% reports")


def test_staleness_and_config():
    with tempfile.TemporaryDirectory(prefix="asset-health-stale-") as tmp:
        root = Path(tmp)
        reg_path = root / "work-studio/devops/infrastructure/data/cortex-asset-registry.json"
        nodes = root / "work-studio/devops/infrastructure/data/nodes-registry.json"
        nodes.parent.mkdir(parents=True, exist_ok=True)
        nodes.write_text("{}\n", encoding="utf-8")
        taxonomy = root / "skills/SKILLS-TAXONOMY.md"
        taxonomy.parent.mkdir(parents=True, exist_ok=True)
        taxonomy.write_text("tax\n", encoding="utf-8")
        touch(nodes, NOW - timedelta(days=30))
        touch(taxonomy, NOW - timedelta(days=31))
        # The registry file itself is old, but the updated_at field is new: look at the field, not the mtime.
        write_json(reg_path, {
            "_meta": {"updated_at": "2026-10-15T12:00:00Z"},
            "segments": {
                "nodes": {"file": "work-studio/devops/infrastructure/data/nodes-registry.json", "count": 1},
                "skills": {"count": 1, "source": "skills/SKILLS-TAXONOMY.md"},
                "escape": {"file": "../../etc/passwd"},
                "absolute": {"file": "/etc/passwd"},
            },
        })
        touch(reg_path, NOW - timedelta(days=100))
        old = os.environ.get("CORTEX_ASSET_HEALTH_STALE_DAYS")
        os.environ.pop("CORTEX_ASSET_HEALTH_STALE_DAYS", None)
        try:
            cands = cl.scan_asset_health(root=root, now=NOW)
        finally:
            if old is None:
                os.environ.pop("CORTEX_ASSET_HEALTH_STALE_DAYS", None)
            else:
                os.environ["CORTEX_ASSET_HEALTH_STALE_DAYS"] = old
        check("asset-health-stale-nodes" not in ids(cands), "exactly 30 days is not stale")
        cand = one(cands, "asset-health-stale-skills")
        assert_shape(cand, "skills reference stale")
        if cand:
            check(cand["value"] == "V1", "stale candidate value V1")
            check("skills/SKILLS-TAXONOMY.md" in cand["title"], "the stale title names the referenced file")
            code, err = run_short(cand["short_test"])
            check(code == 1, "short test fails while stale is unfixed code=%s %s" % (code, err))
            touch(taxonomy, datetime.now().astimezone())
            code, err = run_short(cand["short_test"])
            check(code == 0, "short test passes after mtime is refreshed code=%s %s" % (code, err))
        check("asset-health-stale-registry" not in ids(cands), "a fresh updated_at does not report the registry stale because of file mtime")
        check("asset-health-escape" not in ids(cands), "a reference that escapes the root is rejected")
        check("asset-health-absolute" not in ids(cands), "an absolute-path reference is rejected")
        blob = json.dumps(cands, ensure_ascii=False)
        check("/etc/passwd" not in blob and "passwd" not in blob, "candidates do not carry an out-of-root path")
        # The registry field is stale; the file mtime is left alone.
        reg = json.loads(reg_path.read_text(encoding="utf-8"))
        reg["_meta"]["updated_at"] = "2026-09-14T12:00:00+00:00"
        write_json(reg_path, reg)
        touch(reg_path, NOW)  # the file is new, the field is old
        cands = cl.scan_asset_health(root=root, now=NOW)
        meta = one(cands, "asset-health-stale-registry")
        assert_shape(meta, "registry updated_at stale")
        if meta:
            check(meta["value"] == "V1", "stale registry value V1")
            code, err = run_short(meta["short_test"])
            check(code == 1, "short test fails when updated_at is stale code=%s %s" % (code, err))
            reg["_meta"]["updated_at"] = datetime.now().astimezone().strftime("%Y-%m-%dT%H:%M:%S%z")
            write_json(reg_path, reg)
            code, err = run_short(meta["short_test"])
            check(code == 0, "short test passes after updated_at is edited code=%s %s" % (code, err))
        # An unparseable timestamp is unknown, not stale.
        reg["_meta"]["updated_at"] = "not-a-date"
        write_json(reg_path, reg)
        cands = cl.scan_asset_health(root=root, now=NOW)
        check("asset-health-stale-registry" not in ids(cands)
              and "asset-health-stale-registry-updated-at" not in ids(cands),
              "an updated_at that cannot be parsed does not report stale")
        # The threshold is configurable: a 15-day file is quiet at the default 30 and reports at 10; an explicit argument beats the environment variable.
        touch(nodes, NOW - timedelta(days=15))
        os.environ["CORTEX_ASSET_HEALTH_STALE_DAYS"] = "10"
        try:
            via_env = cl.scan_asset_health(root=root, now=NOW)
            via_arg = cl.scan_asset_health(root=root, stale_days=30, now=NOW)
        finally:
            if old is None:
                os.environ.pop("CORTEX_ASSET_HEALTH_STALE_DAYS", None)
            else:
                os.environ["CORTEX_ASSET_HEALTH_STALE_DAYS"] = old
        # via_bad is still inside the env=10 try. 15 days > 10.
        check("asset-health-stale-nodes" in ids(via_env), "after the environment variable sets the threshold to 10 days it reports")
        check("asset-health-stale-nodes" not in ids(via_arg), "an explicit stale_days beats the environment variable")
        os.environ["CORTEX_ASSET_HEALTH_STALE_DAYS"] = "nope"
        try:
            via_bad_env = cl.scan_asset_health(root=root, now=NOW)
        finally:
            os.environ.pop("CORTEX_ASSET_HEALTH_STALE_DAYS", None)
            if old is not None:
                os.environ["CORTEX_ASSET_HEALTH_STALE_DAYS"] = old
        check("asset-health-stale-nodes" not in ids(via_bad_env), "an illegal environment variable falls back to 30 days")


def test_missing_index_and_discover():
    with tempfile.TemporaryDirectory(prefix="asset-health-disc-") as tmp:
        root = Path(tmp)
        check(cl.scan_asset_health(root=root, now=NOW) == [], "no registry means no candidates")
        reg_path = root / "work-studio/devops/infrastructure/data/cortex-asset-registry.json"
        reg_path.parent.mkdir(parents=True, exist_ok=True)
        reg_path.write_text("{", encoding="utf-8")
        check(cl.scan_asset_health(root=root, now=NOW) == [], "bad JSON does not raise and does not report")
        write_json(reg_path, {
            "_meta": {"updated_at": "2099-01-01T00:00:00Z"},
            "segments": {
                "nodes": {"file": "work-studio/devops/infrastructure/data/nodes-registry.json"},
                "weird": "not-a-dict",
            },
        })
        cands = cl.scan_asset_health(root=root, now=NOW)
        cand = one(cands, "asset-health-nodes")
        assert_shape(cand, "missing reference")
        if cand:
            check(cand["value"] == "V2", "missing-reference value V2")
            check(cand["bounds"] == "work-studio/devops/infrastructure/data/nodes-registry.json",
                  "missing-reference bounds is a relative path")
            code, _err = run_short(cand["short_test"])
            check(code != 0, "the short test fails while the file is still missing")
            target = root / cand["bounds"]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("{}\n", encoding="utf-8")
            code, _err = run_short(cand["short_test"])
            check(code == 0, "the short test passes after the file is added")
        index = root / "work-studio/devops/infrastructure/data/verb-task-index.md"
        index.write_text("index\n", encoding="utf-8")
        touch(index, NOW - timedelta(hours=169))
        cands = cl.scan_asset_health(root=root, now=NOW)
        index_cand = one(cands, "asset-health-index-stale")
        assert_shape(index_cand, "index stale")
        touch(index, NOW - timedelta(hours=167))
        cands = cl.scan_asset_health(root=root, now=NOW)
        check("asset-health-index-stale" not in ids(cands), "an index younger than 7 days does not report")
        # discover_candidates wires this scan in. Every other scanner is turned off.
        # The short test above put the referenced file back; remove it here so the missing candidate appears again.
        target = root / "work-studio/devops/infrastructure/data/nodes-registry.json"
        if target.exists():
            target.unlink()
        saved_root = cl.ROOT
        saved_scanners = cl.SCANNERS
        stubs = [
            "scan_self_defects", "scan_contract_debt", "scan_network_evenness",
            "scan_data_integrity", "scan_frontmatter_readable", "scan_map_backlink_gaps",
        ]
        saved = {name: getattr(cl, name) for name in stubs}
        cl.ROOT = str(root)
        cl.SCANNERS = []
        for name in stubs:
            setattr(cl, name, lambda: [])
        try:
            found = cl.discover_candidates()
        finally:
            cl.ROOT = saved_root
            cl.SCANNERS = saved_scanners
            for name, fn in saved.items():
                setattr(cl, name, fn)
        check("asset-health-nodes" in ids(found), "discover_candidates includes the missing reference")
        check(cl.ROOT == saved_root and isinstance(cl.ROOT, str), "after discover, global ROOT is still the original str")


def test_directory_source_is_not_a_full_tree():
    with tempfile.TemporaryDirectory(prefix="asset-health-dir-") as tmp:
        root = Path(tmp)
        reg_path = root / "reg.json"
        # A concrete directory: 2 direct children (a.txt + sub). Nested files and hidden files do not count.
        (root / "pack").mkdir()
        (root / "pack/a.txt").write_text("a\n", encoding="utf-8")
        (root / "pack/.hidden.txt").write_text(SENTINEL + "\n", encoding="utf-8")
        (root / "pack/sub").mkdir()
        (root / "pack/sub/c.txt").write_text("c\n", encoding="utf-8")
        (root / "pack/sub/d.txt").write_text("d\n", encoding="utf-8")
        # A wildcard directory: count the directory itself. Two references hold 3 files in total; registering 2 still aligns.
        for name, body in (
            ("skills/alpha/references/a.md", "a\n"),
            ("skills/beta/references/b.md", "b\n"),
            ("skills/beta/references/nested/c.md", "c\n"),
            ("deep/dt-one.md", "tree\n"),
        ):
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body, encoding="utf-8")
        write_json(reg_path, {
            "_meta": {"updated_at": "2099-01-01T00:00:00Z"},
            "segments": {
                "directions": {"count": 2, "source": "pack/"},
                "references": {"count": 2, "source": "skills/*/references/"},
                "discovery_trees": {"count": 1, "source": "dt-*.md"},
            },
        })
        cands = cl.scan_asset_health(root=root, registry_path=reg_path, now=NOW)
        check("asset-health-count-directions" not in ids(cands), "a concrete directory counts only direct children")
        check("asset-health-count-references" not in ids(cands), "a wildcard directory counts directories, not the files inside")
        check("asset-health-count-discovery_trees" not in ids(cands), "dt-*.md matches files in subdirectories")
        check(SENTINEL not in json.dumps(cands, ensure_ascii=False), "hidden-file body text does not enter candidates")
        reg = json.loads(reg_path.read_text(encoding="utf-8"))
        reg["segments"]["directions"]["count"] = 9
        write_json(reg_path, reg)
        cands = cl.scan_asset_health(root=root, registry_path=reg_path, now=NOW)
        check("asset-health-count-directions" in ids(cands), "drift is reported only when direct children do not match")


def test_dot_claude_is_counted():
    with tempfile.TemporaryDirectory(prefix="asset-health-dot-") as tmp:
        root = Path(tmp)
        reg_path = root / "reg.json"
        ledger = root / ".claude/EXPERIENCE-LEDGER.md"
        ledger.parent.mkdir(parents=True)
        ledger.write_text("kept\n", encoding="utf-8")
        skipped = root / "node_modules/pkg/EXPERIENCE-LEDGER.md"
        skipped.parent.mkdir(parents=True)
        skipped.write_text(SENTINEL + "\n", encoding="utf-8")
        write_json(reg_path, {
            "_meta": {"updated_at": "2099-01-01T00:00:00Z"},
            "segments": {"ledgers": {"count": 1, "source": "**/EXPERIENCE-LEDGER.md"}},
        })
        cands = cl.scan_asset_health(root=root, registry_path=reg_path, now=NOW)
        check("asset-health-count-ledgers" not in ids(cands),
              ".claude counts, node_modules does not")


def main():
    test_root_stays_str()
    test_predicate_boundaries()
    test_glob_syntax()
    test_balanced_and_path_root()
    test_or_on_filesystem()
    test_staleness_and_config()
    test_missing_index_and_discover()
    test_directory_source_is_not_a_full_tree()
    test_dot_claude_is_counted()
    print()
    if failures:
        print("FAIL %d" % len(failures))
        for msg in failures:
            print("  - %s" % msg)
        return 1
    print("negtest-asset-health: ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
