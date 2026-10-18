#!/usr/bin/env python3
"""I19 — last_seen 改读 beat ref 真实时间（2026-07-29 §3.3）。

背景（今天实测过的具体矛盾）：node_profile() 的 last_seen 字段特意抹平成
整点精度（"一小时内 tick 不制造 git diff"），但 beat_publish() 每次 sync
都会真推一个新 commit —— 于是 commit 的真实时间(精确到秒)和 payload 里
last_seen 字段的文本(整点精度,可能比真实时间早了近一小时)是**两个不同的
"什么时候"**，被压成同一份数据里的一个字段去读，就会出现
"worker 刚推过心跳，dashboard 却显示静默 0.9h" 这种矛盾。

本用例先**复现旧口径确实会算出假的大静默**，再证明新口径
(beat_ref_precise_seen 读 commit 的真实时间)修好了它——不只是加个函数，
要证明这个函数真的接进 node_alive()/takeover_ready() 的判断链路里。

只碰本地 ref，从不 push：refs/swarm/<swarm>/beat/test-beatprecise-<rand>，
用完 git update-ref -d 删除，不留痕、不碰远端。
"""

import os
import random
import re
import sys
from datetime import timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _engine import check, finish, load  # noqa: E402

m = load()

NODE = "test-beatprecise-%06d" % random.randint(0, 999999)
REF = "%s/%s" % (m.BEAT_NS, NODE)


def make_local_commit(payload):
    """在真实本地 git 里造一个 commit（不 push），返回 sha。"""
    code, blob = m.git("hash-object -w --stdin <<'CORTEXEOF'\n%s\nCORTEXEOF" % payload)
    assert code == 0, "hash-object 失败：%s" % blob
    blob = blob.strip().split("\n")[-1]
    code, tree = m.git("mktree <<'CORTEXEOF'\n100644 blob %s\tpayload\nCORTEXEOF" % blob)
    assert code == 0, "mktree 失败：%s" % tree
    tree = tree.strip().split("\n")[-1]
    code, commit = m.git("commit-tree %s -m swarm" % tree)
    assert code == 0, "commit-tree 失败：%s" % commit
    return commit.strip().split("\n")[-1]


try:
    # 造出"矛盾"本身：commit 的真实提交时刻就是现在，但 payload 里的
    # last_seen 字段模拟整点抹平后偏早约 50 分钟(与 node_profile() 的
    # "%Y-%m-%dT%H:00" 抹平逻辑同源)。
    now = m.now()
    stale_last_seen = (now - timedelta(minutes=50)).strftime("%Y-%m-%dT%H:00")
    payload = "node=%s\nlast_seen=%s\ncan_sleep=no\nowns=-\n" % (NODE, stale_last_seen)
    commit = make_local_commit(payload)
    code, _ = m.git("update-ref %s %s" % (REF, commit))
    assert code == 0, "update-ref 失败"

    prof = {"node": NODE, "can_sleep": "no", "last_seen": stale_last_seen}

    # ── 复现旧矛盾：只读 profile 字段，quiet 会显示约 0.8h（不是秒级）───────
    old_quiet = (m.now() - m.parse_ts(prof["last_seen"])).total_seconds() / 3600
    check("旧口径(只读 profile last_seen)确实算出约 0.8h 静默 —— 这正是要修的矛盾",
          old_quiet > 0.5, "实际 %.2fh" % old_quiet)

    # ── 新函数：beat ref 精确时间必须接近真实推送时刻(秒级)──────────────
    precise = m.beat_ref_precise_seen(prof)
    check("beat_ref_precise_seen 读到精确时间（非 None）", precise is not None)
    if precise is not None:
        drift = abs((m.now() - precise).total_seconds())
        check("beat ref 精确时间与真实推送时刻相差 <10s（不是被抹平的整点）",
              drift < 10, "实际相差 %.1fs" % drift)

    # ── 接入链路：node_alive() 必须用精确时间，不再显示旧矛盾的 ~0.8h ──────
    alive, why = m.node_alive(prof)
    check("接入 node_alive() 后判活（本该活，旧口径也判活，但理由应变了）", alive, why)
    check("node_alive() 理由标注用的是 beat ref 精确时间，不是 profile 整点精度",
          "beat ref 精确时间" in why, "实际: %r" % why)
    quiet_match = re.search(r"静默 ([\d.]+)h", why)
    check("node_alive() quiet 数字是秒级精确(<0.05h)，不再是旧口径的 ~0.8h",
          quiet_match is not None and float(quiet_match.group(1)) < 0.05,
          "实际理由: %r" % why)

    # ── takeover_ready() 同一把尺子：用同一个精确来源，不产生第二种口径 ────
    ready = m.takeover_ready(prof)
    check("takeover_ready() 用精确时间判断——刚推过心跳，远未到接管缓冲",
          ready is False, "ready=%r" % ready)

    # ── 没有 beat ref 的节点：必须优雅退回 profile 字段，不能报错/不能判死 ──
    ghost_prof = {"node": "test-beatprecise-no-such-node-ever", "can_sleep": "no",
                  "last_seen": stale_last_seen}
    ghost_precise = m.beat_ref_precise_seen(ghost_prof)
    check("从没发过心跳的节点：beat_ref_precise_seen 返回 None（不是抛异常/不是编造时间）",
          ghost_precise is None, "实际 %r" % ghost_precise)
    ghost_alive, ghost_why = m.node_alive(ghost_prof)
    check("没有 beat ref 时优雅退回 profile 整点精度（旧行为不变，零回归）",
          "profile 整点精度" in ghost_why, "实际: %r" % ghost_why)

finally:
    m.git("update-ref -d %s" % REF)

finish()
