#!/usr/bin/env python3
"""资产健康扫描：Path(ROOT) 回归、计数漂移、过期阈值。只读，不联网。"""
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
    check(cand is not None and set(cand) == SHAPE, "%s 候选字段齐全" % msg)
    if not cand:
        return
    check(cand["source"] == "asset-health", "%s source" % msg)
    check(cand["min_trust"] == "L1", "%s 低信任 L1" % msg)
    check(cand["reversible"] == "yes", "%s 可逆" % msg)
    check(cand["requires"] == "exec.claude", "%s requires" % msg)
    check(cand["approved_by"] == "-", "%s approved_by" % msg)
    check(SENTINEL not in json.dumps(cand, ensure_ascii=False), "%s 不含文件正文" % msg)


def run_short(cmd):
    proc = subprocess.run(
        cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=60)
    return proc.returncode, (proc.stdout + proc.stderr)[-400:]


def balanced_tree(root):
    """与 fixtures/asset-health/registry.json 的 source 语法对齐的小树。"""
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
          "全局 ROOT 仍是 str 赋值")
    check("ROOT = Path(" not in text, "没有把全局 ROOT 改成 Path")
    check(isinstance(cl.ROOT, str), "装载后的 ROOT 是 str")


def test_predicate_boundaries():
    # 恰好 2% 或恰好 3 个文件不报；大于任一才报。
    check(not cl._asset_count_drifted(100, 102), "差 2 / 100 = 2% 不报")
    check(cl._asset_count_drifted(100, 103), "差 3 / 100 > 2% 要报")
    check(not cl._asset_count_drifted(200, 203), "差 3 且相对约 1.5% 不报")
    check(cl._asset_count_drifted(200, 204), "差 4 虽不足 2% 也要报")
    check(cl._asset_count_drifted(50, 52), "差 2 但相对 4% 要报（或，不是与）")
    check(not cl._asset_count_drifted(0, 0), "登记 0 实扫 0 不报")
    check(cl._asset_count_drifted(0, 1), "登记 0 实扫 1 相对越线要报")
    check(cl.ASSET_HEALTH_STALE_DAYS == 30, "默认过期阈值 30 天")
    check(abs(cl.ASSET_HEALTH_COUNT_REL - 0.02) < 1e-12, "相对阈值 2%")
    check(cl.ASSET_HEALTH_COUNT_ABS == 3, "绝对阈值 3 个文件")


def test_glob_syntax():
    check(cl._asset_source_globs("bin/*.sh|py") == ["bin/*.sh", "bin/*.py"],
          "扩展名竖线展开")
    check(cl._asset_source_globs("skills/*/ERRORS.md（错题本，按域分布）")
          == ["skills/*/ERRORS.md"], "中文括注剥掉")
    check(cl._asset_source_globs("**/discovery-trees.jsonl + dt-*.md（发现树）")
          == ["**/discovery-trees.jsonl", "**/dt-*.md"], "无斜杠的文件名通配按任意深度")
    check(cl._asset_source_globs("cortex-harness 席 AAR-014 同批") == [],
          "纯说明不是 glob")
    check(cl._asset_source_globs("skills/SKILLS-TAXONOMY.md")
          == ["skills/SKILLS-TAXONOMY.md"], "具体文件也是可数 source")


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
        cl.ROOT = str(root)  # 生产里 ROOT 就是 str；这里复现原来的 TypeError 路径
        try:
            cands = cl.scan_asset_health(now=NOW)
        finally:
            cl.ROOT = saved
            socket.socket = orig_socket
        check(blocked["calls"] == 0, "扫描不建 socket")
        check(snapshot(root) == before, "扫描不改文件字节")
        check(isinstance(cl.ROOT, str) and cl.ROOT == saved, "扫描不改全局 ROOT")
        check("asset-health-count-tools" not in ids(cands), "对齐的 tools 计数不报")
        check("asset-health-count-errors" not in ids(cands), "对齐的 errors 计数不报")
        check("asset-health-count-ledgers" not in ids(cands), "跳过依赖目录后 ledgers 对齐")
        check("asset-health-count-skills" not in ids(cands), "skills 具体文件计数对齐")
        check("asset-health-count-discovery_trees" not in ids(cands), "发现树两条 glob 对齐")
        check("asset-health-count-references" not in ids(cands), "references 目录下文件对齐")
        check("asset-health-count-recipes" not in ids(cands), "recipes 目录加根文件去重对齐")
        check("asset-health-count-agent_skins" not in ids(cands), "说明文字 source 不比计数")
        check("asset-health-count-directions" not in ids(cands), "没有 source 的 count 不比")
        check("asset-health-nodes" not in ids(cands), "引用文件存在则不报缺失")
        check("asset-health-stale-registry" not in ids(cands), "未来的 updated_at 不算过期")
        blob = json.dumps(cands, ensure_ascii=False)
        check(SENTINEL not in blob, "候选不含文件正文")
        # 把 tools 登记改大，同一棵树应报漂移，且短测能被文件数修好。
        reg = json.loads(reg_path.read_text(encoding="utf-8"))
        reg["segments"]["tools"]["count"] = 10
        write_json(reg_path, reg)
        cands = cl.scan_asset_health(root=root, now=NOW)
        cand = one(cands, "asset-health-count-tools")
        assert_shape(cand, "tools 漂移")
        if cand:
            check("登记 10，实扫 2" in cand["title"], "漂移标题带登记数和实扫数")
            code, err = run_short(cand["short_test"])
            check(code == 1, "漂移未修时短测失败 code=%s %s" % (code, err))
            (root / "bin" / "e.sh").write_text("echo e\n", encoding="utf-8")
            # 原有 2 个 + 这 8 个 = 登记的 10。相对阈值 2% 在 10 这个分母上只允许差 0。
            for i in range(7):
                (root / "bin" / ("extra-%d.sh" % i)).write_text("echo\n", encoding="utf-8")
            code, err = run_short(cand["short_test"])
            check(code == 0, "补齐文件后同一条短测通过 code=%s %s" % (code, err))


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

        check("asset-health-count-batch" not in scan(200), "200=200 不报")
        check("asset-health-count-batch" not in scan(203), "差 3 且相对不足 2% 不报")
        check("asset-health-count-batch" in scan(204), "差 4 个文件要报")
        check("asset-health-count-batch" in scan(190), "相对差大于 2% 要报")


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
        # 注册表文件本身很旧，但 updated_at 字段是新的：只看字段，不看 mtime。
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
        check("asset-health-stale-nodes" not in ids(cands), "恰好 30 天不算过期")
        cand = one(cands, "asset-health-stale-skills")
        assert_shape(cand, "skills 引用过期")
        if cand:
            check(cand["value"] == "V1", "过期候选价值 V1")
            check("skills/SKILLS-TAXONOMY.md" in cand["title"], "过期标题点名引用文件")
            code, err = run_short(cand["short_test"])
            check(code == 1, "过期未修时短测失败 code=%s %s" % (code, err))
            touch(taxonomy, datetime.now().astimezone())
            code, err = run_short(cand["short_test"])
            check(code == 0, "刷新 mtime 后短测通过 code=%s %s" % (code, err))
        check("asset-health-stale-registry" not in ids(cands), "updated_at 新鲜时不因文件 mtime 报注册表过期")
        check("asset-health-escape" not in ids(cands), "拒绝跳出根目录的引用")
        check("asset-health-absolute" not in ids(cands), "拒绝绝对路径引用")
        blob = json.dumps(cands, ensure_ascii=False)
        check("/etc/passwd" not in blob and "passwd" not in blob, "候选不带越界路径")
        # 注册表字段过期，文件 mtime 不动。
        reg = json.loads(reg_path.read_text(encoding="utf-8"))
        reg["_meta"]["updated_at"] = "2026-09-14T12:00:00+00:00"
        write_json(reg_path, reg)
        touch(reg_path, NOW)  # 文件是新的，字段是旧的
        cands = cl.scan_asset_health(root=root, now=NOW)
        meta = one(cands, "asset-health-stale-registry")
        assert_shape(meta, "注册表 updated_at 过期")
        if meta:
            check(meta["value"] == "V1", "注册表过期价值 V1")
            code, err = run_short(meta["short_test"])
            check(code == 1, "updated_at 过期时短测失败 code=%s %s" % (code, err))
            reg["_meta"]["updated_at"] = datetime.now().astimezone().strftime("%Y-%m-%dT%H:%M:%S%z")
            write_json(reg_path, reg)
            code, err = run_short(meta["short_test"])
            check(code == 0, "改 updated_at 后短测通过 code=%s %s" % (code, err))
        # 垃圾时间戳是未知，不当成过期。
        reg["_meta"]["updated_at"] = "not-a-date"
        write_json(reg_path, reg)
        cands = cl.scan_asset_health(root=root, now=NOW)
        check("asset-health-stale-registry" not in ids(cands)
              and "asset-health-stale-registry-updated-at" not in ids(cands),
              "解析不了的 updated_at 不报过期")
        # 阈值可配置：15 天的文件，默认 30 不报，10 天要报；显式参数压过环境变量。
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
        # via_bad 仍在 env=10 的 try 里。15 天 > 10。
        check("asset-health-stale-nodes" in ids(via_env), "环境变量把阈值改成 10 天后要报")
        check("asset-health-stale-nodes" not in ids(via_arg), "显式 stale_days 压过环境变量")
        os.environ["CORTEX_ASSET_HEALTH_STALE_DAYS"] = "nope"
        try:
            via_bad_env = cl.scan_asset_health(root=root, now=NOW)
        finally:
            os.environ.pop("CORTEX_ASSET_HEALTH_STALE_DAYS", None)
            if old is not None:
                os.environ["CORTEX_ASSET_HEALTH_STALE_DAYS"] = old
        check("asset-health-stale-nodes" not in ids(via_bad_env), "非法环境变量回落 30 天")


def test_missing_index_and_discover():
    with tempfile.TemporaryDirectory(prefix="asset-health-disc-") as tmp:
        root = Path(tmp)
        check(cl.scan_asset_health(root=root, now=NOW) == [], "没有注册表就没有候选")
        reg_path = root / "work-studio/devops/infrastructure/data/cortex-asset-registry.json"
        reg_path.parent.mkdir(parents=True, exist_ok=True)
        reg_path.write_text("{", encoding="utf-8")
        check(cl.scan_asset_health(root=root, now=NOW) == [], "坏 JSON 不抛、不报")
        write_json(reg_path, {
            "_meta": {"updated_at": "2099-01-01T00:00:00Z"},
            "segments": {
                "nodes": {"file": "work-studio/devops/infrastructure/data/nodes-registry.json"},
                "weird": "not-a-dict",
            },
        })
        cands = cl.scan_asset_health(root=root, now=NOW)
        cand = one(cands, "asset-health-nodes")
        assert_shape(cand, "缺失引用")
        if cand:
            check(cand["value"] == "V2", "缺失引用价值 V2")
            check(cand["bounds"] == "work-studio/devops/infrastructure/data/nodes-registry.json",
                  "缺失引用 bounds 是相对路径")
            code, _err = run_short(cand["short_test"])
            check(code != 0, "文件还缺着时短测失败")
            target = root / cand["bounds"]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("{}\n", encoding="utf-8")
            code, _err = run_short(cand["short_test"])
            check(code == 0, "补上文件后短测通过")
        index = root / "work-studio/devops/infrastructure/data/verb-task-index.md"
        index.write_text("index\n", encoding="utf-8")
        touch(index, NOW - timedelta(hours=169))
        cands = cl.scan_asset_health(root=root, now=NOW)
        index_cand = one(cands, "asset-health-index-stale")
        assert_shape(index_cand, "索引过期")
        touch(index, NOW - timedelta(hours=167))
        cands = cl.scan_asset_health(root=root, now=NOW)
        check("asset-health-index-stale" not in ids(cands), "索引不足 7 天不报")
        # discover_candidates 会把这条扫描接进去。其它扫描器全部关掉。
        # 上面为了短测把引用文件补上了，这里拿掉，缺失候选才会重新出现。
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
        check("asset-health-nodes" in ids(found), "discover_candidates 带上缺失引用")
        check(cl.ROOT == saved_root and isinstance(cl.ROOT, str), "discover 之后全局 ROOT 仍是原来的 str")


def test_directory_source_is_not_a_full_tree():
    with tempfile.TemporaryDirectory(prefix="asset-health-dir-") as tmp:
        root = Path(tmp)
        reg_path = root / "reg.json"
        # 具体目录：直接子项 2 个（a.txt + sub），嵌套文件和隐藏文件不算。
        (root / "pack").mkdir()
        (root / "pack/a.txt").write_text("a\n", encoding="utf-8")
        (root / "pack/.hidden.txt").write_text(SENTINEL + "\n", encoding="utf-8")
        (root / "pack/sub").mkdir()
        (root / "pack/sub/c.txt").write_text("c\n", encoding="utf-8")
        (root / "pack/sub/d.txt").write_text("d\n", encoding="utf-8")
        # 带通配符的目录：数目录本身。两个 references 里一共 3 个文件，登记 2 仍对齐。
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
        check("asset-health-count-directions" not in ids(cands), "具体目录只数直接子项")
        check("asset-health-count-references" not in ids(cands), "通配目录数目录，不数里面的文件")
        check("asset-health-count-discovery_trees" not in ids(cands), "dt-*.md 匹配子目录里的文件")
        check(SENTINEL not in json.dumps(cands, ensure_ascii=False), "隐藏文件正文不进候选")
        reg = json.loads(reg_path.read_text(encoding="utf-8"))
        reg["segments"]["directions"]["count"] = 9
        write_json(reg_path, reg)
        cands = cl.scan_asset_health(root=root, registry_path=reg_path, now=NOW)
        check("asset-health-count-directions" in ids(cands), "直接子项对不上才报漂移")


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
              ".claude 计入、node_modules 不计入")


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
