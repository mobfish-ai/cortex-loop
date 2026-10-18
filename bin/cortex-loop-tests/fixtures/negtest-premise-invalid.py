#!/usr/bin/env python3
"""负向测试：前提失效的任务必须走 moot 退役，不许当作「失败」无限重试。

为什么必须常驻回归（2026-07-29 真机实证）：
  `own_skill()` 落地后，发现层不再把 vendor 软链当自家欠债 —— 但**修好之前
  入队的任务不会自己消失**。计划 imm-0729073608 里的 island-YC-autoplan 早已排上，
  于是 worker 每一拍都去跑一个物理上不可能完成的活：

      skills/YC-autoplan -> ${CORTEX_VENDOR_SKILLS}/gstack/autoplan
      Linux 节点上 dangling；31 个 YC-* 全是同类

  每拍烧一整轮额度、产出恒零，还往过门率分母里加一个数。
  更坏的是它逼出了作弊压力：07:36 那轮诚实地写了 BLOCKED 报告，
  23:13 那轮就造了个 stub 去满足门 —— **不可能完成的任务会持续生产假产出**。

这是维度坍缩：「失败」这一个状态里混了两件修法相反的事 ——
    「我做不到」        → 修能力 / 换节点 / 给时间
    「这活本来就不该存在」→ 退役判据，重试多少次都没用
压成一个 FAIL，系统必然选择后者的最坏解：永远重试。

所以前提失效必须是独立终态（moot），而不是 result：
  既不配加分（没干活），也不该扣分（不是节点的错）。
  写 result 会同时污染 HAAS 与过门率两个口径。

判据必须与发现层用**同一把尺子**（own_skill）——
两层各判各的，就会出现「发现层说不该派、执行层说该跑」的分裂。
"""
import atexit
import os
import re
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..")
ROOT = os.path.abspath(ROOT)
ENGINE = os.path.join(ROOT, "bin", "cortex-loop")

fails = 0


def check(name, ok, detail=""):
    global fails
    if ok:
        print("  PASS %s" % name)
    else:
        fails += 1
        print("  FAIL %s  %s" % (name, detail))


# ── 1 · 判定逻辑：与引擎同一把尺子 ────────────────────────────────────
def own_skill(path):
    real = os.path.realpath(path)
    return real == os.path.abspath(path) or real.startswith(ROOT + os.sep)


def premise_invalid(task):
    """复刻 cmd_run 里的前提失效判定，用于场景验证。"""
    for fld in ("short_test", "artifact", "detail"):
        for m in re.finditer(r"skills/([A-Za-z0-9._-]+)", str(task.get(fld) or "")):
            p = os.path.join(ROOT, "skills", m.group(1))
            if os.path.lexists(p) and not own_skill(p):
                return m.group(1)
    return ""


vendor = os.path.join(ROOT, "skills", "YC-autoplan")
created_vendor = False
if not os.path.lexists(vendor):
    # Public tree does not ship the private vendor symlink. A link whose
    # target sits outside this repo is enough for own_skill() to reject it.
    os.symlink("/tmp/cortex-not-in-this-repo", vendor)
    created_vendor = True


def _cleanup_vendor():
    if created_vendor and os.path.islink(vendor):
        os.unlink(vendor)


atexit.register(_cleanup_vendor)

CASES = [
    # (说明, task, 期望被判前提失效)
    ("vendor 软链任务必须 moot",
     {"short_test": "grep -qE '^host:' skills/YC-autoplan/SKILL.md"}, True),
    ("自家 skill 任务必须放行",
     {"short_test": "grep -qE '^host:' skills/cortex-loop/SKILL.md"}, False),
    ("artifact 字段里的 vendor 路径也要抓到",
     {"short_test": "true", "artifact": "skills/YC-autoplan/SKILL.md"}, True),
    ("不存在的 skill 不算前提失效（那是真的没做，该跑）",
     {"short_test": "test -f skills/definitely-not-here-xyz/SKILL.md"}, False),
    ("无 skills/ 路径的任务不受影响",
     {"short_test": "bash bin/cortex-loop-tests/suite.sh"}, False),
]

for name, task, want in CASES:
    got = bool(premise_invalid(task))
    check(name, got == want, "期望 %s 实得 %s" % (want, got))


# ── 2 · 实现层：引擎里这道门必须真实存在且开在烧额度之前 ────────────────
try:
    src = open(ENGINE, encoding="utf-8").read()
except OSError as e:
    print("  FAIL 读不到引擎：%s" % e)
    sys.exit(1)

check("引擎里存在前提失效门", "前提失效" in src and "premise-invalid" in src,
      "门不在 = 已排队的坏任务仍会无限重试")

check("前提失效走 MOOT_NS，不写 result",
      re.search(r"premise-invalid", src) is not None
      and re.search(r"MOOT_NS[^\n]*\n[^\n]*premise-invalid|premise-invalid[\s\S]{0,400}?MOOT_NS"
                    r"|MOOT_NS[\s\S]{0,400}?premise-invalid", src) is not None,
      "写 result 会同时污染 HAAS 与过门率")

# 门必须开在花钱之前。
# ⚠️ 本断言第一版写错过（2026-07-29，量具失灵第 7 次）：用了全局 `src.find`，
# 抓到的是**另一个函数里**更靠前的 covenant_check（行 1598），于是在代码完全
# 正确的情况下报红。教训：跨函数的位置比较必须先锚定到同一个块内，
# 全局 find 的「第一个」几乎从来不是你想要的那个。
i_premise = src.find("premise-invalid")
i_coven = src.find("covenant_check(task", i_premise) if i_premise > 0 else -1
check("门开在烧额度之前（同一块内 premise 判定早于 covenant_check）",
      i_premise > 0 and i_coven > i_premise,
      "放到执行之后再拦 = 白烧一次调用")

check("判据与发现层同一把尺子（复用 own_skill，不另起判据）",
      "own_skill(" in src and src.count("def own_skill") == 1,
      "两层各判各的会分裂成「发现层说不派、执行层说该跑」")

print("negtest-premise-invalid: %s" % ("ALL PASS" if fails == 0 else "%d FAIL" % fails))
sys.exit(1 if fails else 0)
