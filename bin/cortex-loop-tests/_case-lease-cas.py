#!/usr/bin/env python3
"""C11 — 租约 CAS：同 parent 两个 commit 推同一 ref，第二个必须被拒。

这是整个蜂群的防脑裂根基：网络分区时两个节点都会认为自己该接管，
git 服务器的 fast-forward 检查是唯一裁决者（语义等价 Redis SETNX，但零外部依赖）。
它一旦失效（比如有人给 push 加了 --force），两个节点会同时推进同一条线。

隔离：只用 refs/swarm/test-<随机后缀>，绝不碰 refs/swarm/lease/*；
跑完 push --delete 清远端 + update-ref -d 清本地。

抗抖：write_ref 的返回值把「被 CAS 拒」和「网络挂了」压成同一个 False（见报告 O-01），
所以每次判「被拒」之前都用 ls-remote 反证网络是通的，网络问题则重试/SKIP，
绝不把一次 SSL 抖动记成 CAS 生效。
"""

import os
import random
import string
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _engine import check, finish, load  # noqa: E402

m = load()
sfx = "".join(random.choice(string.ascii_lowercase + string.digits) for _ in range(8))
REF = "refs/swarm/test-cas-%s" % sfx
LEASE_REF = "refs/swarm/test-lease-%s/testline" % sfx
print("    测试命名空间：%s（绝不碰 refs/swarm/lease/*）" % REF)


def remote_sha(ref, tries=3):
    """远端该 ref 指向哪。返回 None = 网络不通（跟「ref 不存在」返回空串区分开）。

    连着 3 次够不着才认输：GitHub 走 Tailscale exit node 出境(2026-09-21 起，原 Privoxy 已退役)，单次 SSL_ERROR_SYSCALL 很常见，
    一次抖动就判「网络挂了」会让 CAS 断言变成掷骰子。
    """
    for _ in range(tries):
        code, out = m.git("ls-remote origin %s" % ref, timeout=120)
        if code == 0:
            rows = [r for r in out.split("\n") if r.strip() and "\t" in r]
            return rows[0].split()[0] if rows else ""
        time.sleep(2)
    return None


def net_down():
    return remote_sha("HEAD") is None


def push_expect_ok(payload, parent, tries=3):
    """期望成功的 push：只对网络失败重试，CAS 拒绝不重试。"""
    for attempt in range(tries):
        ok, sha = m.write_ref(REF, payload, parent=parent)
        if ok:
            return True, sha
        if net_down():
            print("    网络抖动，第 %d 次重试" % (attempt + 1))
            time.sleep(3)
            continue
        return False, sha
    return False, ""


try:
    if net_down():
        print("    SKIP：origin 不可达，CAS 用例无法真跑")
        raise SystemExit(2)

    ok0, sha0 = push_expect_ok("holder=setup", None)
    if not ok0:
        print("    SKIP：测试 ref 建不起来（凭据或权限问题），CAS 用例无法真跑")
        raise SystemExit(2)

    # 节点 A 与 节点 B 同时拿 sha0 当 parent —— 「同时抢」的精确复现
    okA, shaA = push_expect_ok("holder=nodeA", sha0)
    check("先到的节点 A 推成功", okA is True, "A 都推不上，后面无从谈起")

    okB, shaB = m.write_ref(REF, "holder=nodeB", parent=sha0)
    if not shaB:                      # 连 commit 都没造出来 = 本地 git 抖了，不是 CAS 拒绝
        okB, shaB = m.write_ref(REF, "holder=nodeB", parent=sha0)
    live = remote_sha(REF)
    check("判 B 被拒时网络是通的（排除假阳性）", live is not None, "ls-remote 拿不到 → 网络挂了")
    check("同 parent 的节点 B 被拒", okB is False, "B 也成功了 = CAS 失效，两节点会同时动同一条线")
    check("远端停在赢家 A 上", live == shaA, "远端 %r 期望 %r" % (live, shaA))
    check("A/B 是两个不同 commit（确实各造各的）", shaA != shaB)

    # 拿最新 parent 重试必须成功 —— 否则这不是锁，是死结
    okB2, shaB2 = push_expect_ok("holder=nodeB", shaA)
    check("B 拿最新 parent 重试成功", okB2 is True, "重试也失败 = 锁变死结")
    check("重试后远端换成 B", remote_sha(REF) == shaB2)

    # acquire_lease 层：租约有效期内别的节点抢不到
    m.LEASE_NS = "refs/swarm/test-lease-%s" % sfx

    def lease_expect_ok(node, tries=3):
        """期望抢到的场景。抢不到的原因可能是上一次 fetch 抖掉了（本地 ref 过期 →
        parent 陈旧 → 被拒），重试一次就好；所以这里只对「期望成功」的调用重试。"""
        os.environ["CORTEX_NODE"] = node
        got, why = False, ""
        for _ in range(tries):
            got, why = m.acquire_lease("testline", ttl_min=60)
            if got:
                break
            time.sleep(3)
        return got, why

    got1, why1 = lease_expect_ok("node-first")
    check("首个节点拿到租约", got1 is True, why1)

    os.environ["CORTEX_NODE"] = "node-second"
    got2, why2 = m.acquire_lease("testline", ttl_min=60)
    check("判第二个节点抢不到时网络是通的", remote_sha(LEASE_REF) is not None, "网络挂了")
    check("租约未到期时第二个节点拿不到", got2 is False, why2)
    check("拒绝理由点名持有者", "node-first" in why2, "实际 %r" % why2)

    # 过期租约必须能被接手，否则一个节点挂掉就把线永久锁死
    expired = "holder=node-first\nexpires=%s\nsince=%s" % (
        m.fmt(m.now() - m.timedelta(minutes=5)), m.fmt(m.now() - m.timedelta(minutes=65)))
    okE, _ = m.write_ref(LEASE_REF, expired, parent=remote_sha(LEASE_REF) or None)
    check("能造出一个已过期的租约", okE is True, "写不进测试 ref")
    if okE:
        got3, why3 = lease_expect_ok("node-second")
        check("租约过期后可被别的节点接手", got3 is True, why3)
finally:
    for ref in (REF, LEASE_REF):
        m.git("push origin --delete %s 2>&1" % ref, timeout=180)
        m.git("update-ref -d %s 2>&1" % ref)
    left = m.git("ls-remote origin 'refs/swarm/test-*'", timeout=120)[1].strip()
    local = m.git("for-each-ref --format='%(refname)' refs/swarm/")[1]
    local_test = [r for r in local.split("\n") if "test-" in r]
    print("    清理：远端 %s ｜ 本地 %s"
          % ("已删净" if sfx not in left else "⚠️ 残留 %s" % left,
             "已删净" if not local_test else "⚠️ 残留 %s" % local_test))

finish()
