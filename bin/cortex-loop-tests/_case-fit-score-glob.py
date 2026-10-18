#!/usr/bin/env python3
"""I17 — fit_score 改 glob 匹配后：现有任务判定结果逐条不变 + 通配确实生效。

背景：`bin/cortex-loop` fit_score 原来对 requires 做字面差集 `need - have`，
新任务写不出模式串（如 "model.anthropic.*"），只能退化成 "exec.claude" 这种
最粗写法。改成 fnmatch 后，精确串（旧任务全部这么写）行为与 `==` 完全一致，
新任务才能用通配符——这条用例既要证明"零回归"，也要证明"通配真的生效"。

只读：不写任何文件、不碰真账本、不动网络。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _engine import check, finish, load  # noqa: E402

m = load()

HAVE = {"exec.claude", "exec.codex", "model.anthropic.claude-opus-5",
        "model.openai.openai-codex", "host.laptop", "net.github",
        "net.github.fast"}


def score(requires_str, have=HAVE, load_=0, max_load=3):
    task = {"requires": requires_str}
    return m.fit_score(task, {"caps": " ".join(have)}, load_, max_load)


# ── 零回归：现有任务精确串写法，改前改后判定必须一致 ─────────────────────
ok, why = score("-")
check("旧写法 requires=- → 无要求，可认领", ok is not None, why)

ok, why = score("exec.claude")
check("旧写法 requires=exec.claude（有）→ 可认领", ok is not None, why)

ok, why = score("exec.human")
check("旧写法 requires=exec.human（没有）→ 缺能力拒绝", ok is None, why)
check("拒绝理由原样报出缺的能力名（非 glob 污染）",
      why == "缺能力 exec.human", "实际: %r" % why)

# ── 新能力：通配符真的生效（不是形同虚设）───────────────────────────────
ok, why = score("model.anthropic.*")
check("新写法 model.anthropic.* 通配命中 model.anthropic.claude-opus-5",
      ok is not None, why)

ok, why = score("model.google.*")
check("通配不该无差别放行——没有的 provider 仍应拒绝", ok is None, why)

ok, why = score("net.github.fast")
check("精确串 net.github.fast（有）→ 可认领", ok is not None, why)

ok, why = score("net.github.slow")
check("精确串 net.github.slow（没有，节点是 fast）→ 拒绝", ok is None, why)

# ── 混合：一个 requires 里既有精确串也有通配串，必须同时满足 ────────────
ok, why = score("exec.claude model.anthropic.*")
check("混合 requires（精确+通配）全满足 → 可认领", ok is not None, why)

ok, why = score("exec.claude model.openai.gpt-*")
check("混合 requires 里通配那半没命中 → 整体拒绝", ok is None, why)

finish()
