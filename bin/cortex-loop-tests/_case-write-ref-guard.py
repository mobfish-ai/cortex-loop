#!/usr/bin/env python3
"""D12 — write_ref 拿到空/非法 sha 时绝不 push。

这是致命 footgun 的护栏：`git push origin :<ref>` 的语义是**删掉远端 ref**。
如果 commit-tree 因任何原因返回空串，字符串拼出来就是 `push origin :refs/swarm/...`
—— 一次心跳失败就能把整个蜂群的 ref 抹掉。所以「空 sha 不 push」必须有测试守着。

做法：把模块里的 git() 换成假的记录器，让它按剧本返回坏 sha，
断言 push 那一步**根本没被调用过**。全程不碰真 git，不产生任何副作用。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _engine import check, finish, load  # noqa: E402

m = load()
GOOD = "a" * 40


def make_fake(commit_out):
    calls = []

    def fake_git(cmd, timeout=120):
        calls.append(cmd)
        if cmd.startswith("hash-object"):
            return 0, GOOD
        if cmd.startswith("mktree"):
            return 0, "b" * 40
        if cmd.startswith("commit-tree"):
            return 0, commit_out
        return 0, ""

    return fake_git, calls


for label, commit_out in (("空 sha", ""),
                          ("短 sha", "abc123"),
                          ("非 hex", "z" * 40),
                          ("带引号噪音", "'%s'" % GOOD)):
    m.git, calls = make_fake(commit_out)
    ok, sha = m.write_ref("refs/swarm/test-guard-never-pushed", "holder=x")
    pushed = [c for c in calls if c.startswith("push")]
    check("%s → 不 push" % label, not pushed, "竟然执行了 %r" % pushed)
    check("%s → 返回 (False, '')" % label, (ok, sha) == (False, ""), "实际 %r" % ((ok, sha),))

# 反向对照：正常 sha 必须真的走到 push（否则这个护栏是把功能整个关死了）
m.git, calls = make_fake(GOOD)
ok, sha = m.write_ref("refs/swarm/test-guard-happy", "holder=x")
pushed = [c for c in calls if c.startswith("push")]
check("合法 sha → 确实发起 push", len(pushed) == 1, "实际 %r" % calls)
check("origin push 成功后立即更新同名本地 ref",
      "update-ref refs/swarm/test-guard-happy %s" % GOOD in calls,
      "实际 %r" % calls)
check("push 目标带完整 sha 不是裸冒号",
      pushed and (":refs/" not in pushed[0].split()[2].split(":")[0] + ":")
      and pushed[0].split()[2].startswith(GOOD),
      "实际 %r" % (pushed[0] if pushed else None))
check("合法 sha → 返回 (True, sha)", (ok, sha) == (True, GOOD), "实际 %r" % ((ok, sha),))

# rev_ref 的同源护栏：读不到必须给 None，绝不给空串（空串会拼出删 ref 的命令）
m.git = load().git                                   # 换回真 git
check("rev_ref 读不存在的 ref 返回 None",
      m.rev_ref("refs/swarm/test-definitely-not-exist-zzz") is None)

finish()
