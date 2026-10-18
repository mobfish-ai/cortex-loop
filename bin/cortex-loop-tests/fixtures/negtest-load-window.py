#!/usr/bin/env python3
"""负向测试：负载率/闲置率的分子与分母必须取同一个时间窗。

为什么必须常驻回归（2026-07-29 实测）：
  `cortex-dashboard.sh` 的分母是「今天 00:00 至今应跑多少拍」，
  分子却是 `refs/swarm/<shard>/result/` 的**全历史**去重计数。

      TICKS_DUE  = (now - 今天00:00) / 900        ← 今天
      TICKS_PROD = 全部 result ref 去重 = 31       ← 开天辟地至今

  蜂群 2026-07-28 才起，当天两者恰好都≈今天，**缺陷被完全掩盖**（显示 66% 闲置，看着挺合理）。
  真正会说谎的是跨天那一刻：

      次日 00:15 → TICKS_DUE = 1，TICKS_PROD 仍带着昨天的 31
                 → LOAD = min(100, 3100) = 100%  →  闲置 0%

  新的一天一个任务都还没跑，仪表盘显示**满载**。
  这是 fail-open 里最坏的一种：**最该报警的时刻恰好最绿**。
  而且它自我掩盖 —— 越是长期没产出，分子里的历史存量越厚，数字越好看。

与「一拍时间预算」是同一个母题的两个面：
  那个是量具坏了（300s 把活掐死），这个是量纲错了（分子分母不同窗）。
  两者都不会让系统崩，只会让**看仪表盘的人以为一切正常**。

修法不是调数字（那是粉饰），是让分子跟着分母走同一个窗口。
判据方向也要对：修完数字应该变**难看**或不变，绝不该变好看 ——
若某次改动让这个指标凭空变好，第一嫌疑就是又把窗口放宽了。
"""
import os
import re
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..")
DASH = os.path.join(ROOT, "bin", "cortex-dashboard.sh")

fails = 0


def check(name, ok, detail=""):
    global fails
    if ok:
        print("  PASS %s" % name)
    else:
        fails += 1
        print("  FAIL %s  %s" % (name, detail))


# ── 1 · 算术层：证明「不同窗」在跨天时刻必然 fail-open ──────────────────
def load_pct(prod, due):
    due = max(due, 1)
    return min(100, prod * 100 // due)


# 场景取真值：2026-07-29 当天分子 31、分母 90
check(
    "同日两者≈同窗时缺陷不可见（这正是它藏了一整天的原因）",
    load_pct(31, 90) == 34,
    "实测当天应为 34% 负载 / 66% 闲置",
)

# 跨天：分母重置、分子不重置 → 满载
check(
    "跨天 00:15 用全历史分子 → 必然虚假满载（这是要挡的行为）",
    load_pct(31, 1) == 100,
    "旧口径在次日开局显示 100% 负载 = fail-open",
)

# 跨天：分子同窗（新的一天还没产出 → 0） → 正确显示零负载
check(
    "跨天 00:15 用同窗分子 → 正确显示 0% 负载 / 100% 闲置",
    load_pct(0, 1) == 0,
    "同窗后新的一天没产出就该显示闲置，而不是满载",
)


# ── 2 · 实现层：真文件里分子必须带窗口过滤 ────────────────────────────
try:
    src = open(DASH, encoding="utf-8").read()
except OSError as e:
    print("  FAIL 读不到 cortex-dashboard.sh：%s" % e)
    sys.exit(1)

m = re.search(r"TICKS_PROD=\"\$\((.*?)\)\"", src, re.S)
check("cortex-dashboard.sh 里找得到 TICKS_PROD 计算", m is not None,
      "取不到就无从判断口径 —— 按三态这是 UNKNOWN，不倒向 PASS")

if m:
    body = m.group(1)
    # 分子必须引用分母用的同一个起点变量，且真的拿它做了过滤
    check(
        "分子引用了分母的窗口起点 _day_start",
        "_day_start" in body,
        "分子没引用 _day_start = 两端不同窗，跨天必假绿",
    )
    check(
        "分子按 ref 提交时间过滤（不是靠 id 里编的日期字符串猜）",
        "committerdate" in body,
        "靠 plan id 里的 MMDD 猜日期会被非常规 id（orchestrator / real1 等夹具）绕过",
    )
    check(
        "零 ref 时计数只产生一个 0（不会形成 0\\n0 算术崩溃）",
        "count_nonempty" in body and "grep -c" not in body,
        "`grep -c . || echo 0` 在零匹配时会打印两个 0",
    )

check(
    "dashboard 已清除所有 `grep -c ... || echo 0` 双零模式",
    not any(
        re.search(r"grep\s+-c\S*.*\|\|\s*echo\s+0", line)
        for line in src.splitlines()
        if not line.lstrip().startswith("#")
    ),
    "任何一个残留点都可能在午夜/空文件时变成多行整数",
)

# 分母口径本身也要显式，防止有人反向把分母改成全历史来"对齐"
m2 = re.search(r"TICKS_DUE=\$\(\(.*?\)\)", src, re.S)
check(
    "分母仍是「今日应跑拍数」，没有被反向改成全历史",
    m2 is not None and "_day_start" in m2.group(0) and "900" in m2.group(0),
    "对齐量纲的正解是收紧分子，不是放宽分母",
)

print("negtest-load-window: %s" % ("ALL PASS" if fails == 0 else "%d FAIL" % fails))
sys.exit(1 if fails else 0)
