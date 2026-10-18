#!/usr/bin/env python3
"""B8 — list_refs / read_ref / read_swarm 必须真走 ref 层，不得静默退回文件快照。

回归的真实风险：ref 层读不到任何东西时 read_swarm 会退回本地 _swarm/*.md 文件快照，
那份快照可能是几天前的 —— 蜂群会拿着过期画像判活，等于假装自己看得见别的节点。

本用例用**独立测试命名空间**造一个本地 ref（不 push，不碰 refs/swarm/beat），
断言 ref 层真的被读到；跑完 update-ref -d 清理干净。
"""

import os
import random
import string
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _engine import check, finish, load  # noqa: E402

m = load()
sfx = "".join(random.choice(string.ascii_lowercase + string.digits) for _ in range(8))
NS = "refs/swarm/test-%s" % sfx
REF = "%s/fakenode" % NS
PAYLOAD = "\n".join([
    "node=fakenode",
    "kind=always-on",
    "can_sleep=no",
    "executors=mock",
    "telegram_reach=no",
    "last_seen=%s" % m.fmt(m.now()),
    "owns=testline",
])


def build_local_ref():
    """纯 plumbing 造对象 + update-ref，全程本地，不 push。"""
    code, blob = m.git("hash-object -w --stdin <<'CORTEXEOF'\n%s\nCORTEXEOF" % PAYLOAD)
    if code != 0:
        return False
    blob = blob.strip().split("\n")[-1]
    code, tree = m.git("mktree <<'CORTEXEOF'\n100644 blob %s\tpayload\nCORTEXEOF" % blob)
    if code != 0:
        return False
    tree = tree.strip().split("\n")[-1]
    code, commit = m.git("commit-tree %s -m suite-test" % tree)
    if code != 0:
        return False
    commit = commit.strip().split("\n")[-1]
    return m.git("update-ref %s %s" % (REF, commit))[0] == 0


try:
    check("本地测试 ref 造得出来", build_local_ref(), "plumbing 失败")

    refs = m.list_refs(NS)
    check("list_refs 真返回 ref 列表", refs == [REF], "实际 %r" % refs)

    check("read_ref 取得回 payload", "node=fakenode" in m.read_ref(REF),
          "读到 %r" % m.read_ref(REF)[:80])

    # read_swarm 优先读 ref；把命名空间指到测试 ns，断言它不走文件快照那条路
    m.BEAT_NS = NS
    m.SWARM = "/nonexistent-swarm-dir-%s" % sfx      # 文件快照路径故意打死
    nodes = m.read_swarm()
    check("read_swarm 从 ref 层拿到节点", list(nodes) == ["fakenode"], "实际 %r" % list(nodes))
    check("ref 层节点字段完整", nodes.get("fakenode", {}).get("owns") == "testline",
          "实际 %r" % nodes.get("fakenode"))

    # 反向：ref 层空 + 文件快照也空 → 必须返回空，不能编出节点来
    m.BEAT_NS = "refs/swarm/test-empty-%s" % sfx
    check("ref 与快照皆空时返回空字典", m.read_swarm() == {})
finally:
    m.git("update-ref -d %s" % REF)
    left = m.git("for-each-ref --format='%(refname)' " + NS)[1].strip()
    print("    清理：%s → %s" % (NS, "已清空" if not left else "残留 %s" % left))

finish()
