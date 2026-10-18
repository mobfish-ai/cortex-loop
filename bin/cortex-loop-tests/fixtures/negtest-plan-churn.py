#!/usr/bin/env python3
"""负向测试：_oldest_open_plan 真的能识别「还有活可干的旧计划」。

为什么必须有（2026-07-29 真机根因）：
  24 个免疫计划里 7 个从头到尾**零认领**。cmd_tick 的自主找活路径每拍无条件
  写一个新 plan id，且只跑自己刚发的那个，从不回头看已有未完成计划。
  同一批候选被反复派成新 plan，而过门率的分母是 result ref 数 =（plan,task）
  对数 —— 每重发一次同一件活就在分母里多占一格：分子不动、分母暴涨。

这道门一旦写错方向，症状是**静默的**：
  · 判太松（永远返回某个 plan）→ 新缺口再也发不出去，蜂群假装很忙实则空转
  · 判太紧（永远返回 None）  → 退化回原样，堆积照旧，而且没人会发现
所以必须有断言把两个方向都钉住。

判据是三态不是两态（高维展开律）：
  已 done / 本节点上次 failed（让给别人）/ 其余可干
—— 少展开任何一态都会错：把「别的节点 failed」当成「不用干了」，
一次失败就等于任务死刑，蜂群容错全废（这正是 cmd_claim 修过的同一个病）。

不碰真账本、不联网：打桩 list_refs / plan_tasks / read_ref。
"""
import importlib.machinery
import importlib.util
import os
import sys

ENGINE = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "cortex-loop")
loader = importlib.machinery.SourceFileLoader("cl", ENGINE)
cl = importlib.util.module_from_spec(importlib.util.spec_from_loader("cl", loader))
loader.exec_module(cl)

ME = "testnode"


def stub(plans, results):
    """plans: {pid: [task_id|task_dict,...]} results: {'pid/task': receipt}"""
    cl.node_id = lambda: ME
    cl.list_refs = lambda ns: ["%s/%s" % (cl.PLAN_NS, p) for p in plans]
    cl.plan_tasks = lambda pid: [
        {"id": t} if isinstance(t, str) else t for t in plans.get(pid, [])
    ]
    cl.read_ref = lambda ref: results.get(ref.split("/result/", 1)[-1], "")


# 不存在 ref 是正常空态，不能依赖英文错误串识别（本机 Git locale 可能输出中文）。
_real_rev_ref, _real_git = cl.rev_ref, cl.git
_git_calls = []
cl.rev_ref = lambda ref: None
cl.git = lambda *args, **kwargs: (_git_calls.append(args) or (1, "不该执行"))
_missing_ref_value = cl.read_ref("refs/swarm/cortex/result/missing")
cl.rev_ref, cl.git = _real_rev_ref, _real_git
if _missing_ref_value != "" or _git_calls:
    print("  BAD  missing ref 应在 rev-parse 后直接返回空，不应调用 cat-file")
    sys.exit(1)
print("  ok   missing ref 不依赖 Git locale 错误文本")


# (标签, plans, results, 期望返回)
CASES = [
    ("全部 done → 没有旧活，该去发新计划",
     {"imm-1": ["a", "b"]},
     {"imm-1/a": "status=done\nnode=other", "imm-1/b": "status=done\nnode=%s" % ME},
     None),

    ("零 result 的旧计划 → 就是它（这就是真机那 7 个零认领）",
     {"imm-1": ["a"]}, {}, "imm-1"),

    ("本节点上次 failed → 让给别的节点，不算本节点的活",
     {"imm-1": ["a"]}, {"imm-1/a": "status=failed\nnode=%s" % ME}, None),

    ("**别的节点** failed → 本节点该接手（一次失败≠任务死刑）",
     {"imm-1": ["a"]}, {"imm-1/a": "status=failed\nnode=other"}, "imm-1"),

    ("scope-gap 也算已完成不了？——不，status=done 才跳过，gate 不参与判定",
     {"imm-1": ["a"]}, {"imm-1/a": "status=done\ngate=scope-gap\nnode=other"}, None),

    ("挑**最早**的那个，不是随便一个（一拍接一件，防雪崩）",
     {"imm-0729130809": ["a"], "imm-0729053637": ["a"], "imm-0729100933": ["a"]},
     {}, "imm-0729053637"),

    ("冻结 discovery 的 S1 cohort 优先于更老的 legacy 半成品",
     {"imm-legacy": [{"id": "a", "discovery_id": "-"}],
      "imm-s1": [{"id": "b", "discovery_id": "d-b"}]},
     {}, "imm-s1"),

    ("确定性 S1 优先于更老的模型型 frozen discovery",
     {"imm-old-model": [{"id": "a", "discovery_id": "d-a", "source": "frontmatter-gap"}],
      "imm-s1": [{"id": "b", "discovery_id": "d-b", "source": "map-backlink-gap"}]},
     {}, "imm-s1"),

    ("旧计划部分完成 → 只要还有一条能干就返回它",
     {"imm-1": ["a", "b"]},
     {"imm-1/a": "status=done\nnode=other"}, "imm-1"),

    ("空计划（tasks 解析不出来）→ 跳过，不当成有活",
     {"imm-1": []}, {}, None),

    ("非 imm- 前缀的计划（人发的 real1）不在自主找活范围内",
     {"real1": ["R1"]}, {}, None),
]

fails = []
for label, plans, results, want in CASES:
    stub(plans, results)
    got = cl._oldest_open_plan()
    if got != want:
        fails.append("%s — 期望 %r 实得 %r" % (label, want, got))
        print("  BAD  %s — 期望 %r 实得 %r" % (label, want, got))
    else:
        print("  ok   %s → %r" % (label, got))

if fails:
    print("\n断言失败 %d 条：%s" % (len(fails), " / ".join(fails)))
    sys.exit(1)


# 自动 run 后必须无条件 gather(settle=True)：即使本拍只完成部分任务，也要先发布
# 已通过任务的 learning；最后一批收齐时同一路径会自动结算。
_calls = []
cl.cmd_run = lambda ns: (_calls.append(("run", ns.plan)) or 0)
cl.cmd_gather = lambda ns: (_calls.append(("gather", ns.plan, ns.settle)) or 1)
_run_args = type("RunArgs", (), {"plan": "imm-s1"})()
cl._run_and_gather("imm-s1", _run_args)
if _calls != [("run", "imm-s1"), ("gather", "imm-s1", True)]:
    print("  BAD  自动执行没有形成 run→gather(settle=True) 闭环：%r" % (_calls,))
    sys.exit(1)
print("  ok   自动执行强制 run→gather(settle=True)")
if _run_args.trigger_kind != "clock-auto":
    print("  BAD  自动执行 receipt 未标 trigger_kind=clock-auto")
    sys.exit(1)
print("  ok   自动执行 receipt 标记 clock-auto，手工 run 不冒充 S1")

print("\n计划复用与自动结算判据 %d 场景全绿" % len(CASES))
