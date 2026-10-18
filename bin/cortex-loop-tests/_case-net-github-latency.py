#!/usr/bin/env python3
"""I18 — net.github.fast/slow cap（2026-07-29 §3.2）。

两层验证：
  1. 纯函数 _github_latency_caps() 的分类边界（不碰真网络，覆盖 4 个象限）
  2. 真机实测：本机跑 node_capabilities()，caps 必须同时含 net.github 和
     恰好一个 fast/slow 标记（不可能两个都有，也不可能一个都没有——已连通）

第 2 层是本条用例存在的意义：证明真探测确实把标签接上了，不是只有纯函数
逻辑对但从没被真调用点使用（这正是今天 SCANNER-DOWN 门 v1 踩过的坑——
门建了但没验证真的会触发）。

只读：node_capabilities() 只读探测，不写任何文件。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _engine import check, finish, load  # noqa: E402

m = load()

# ── 第 1 层：纯函数边界（4 象限）──────────────────────────────────────
THRESH = m.NET_GITHUB_FAST_THRESHOLD_S

check("不通 → 空标签（不该报 fast/slow 里任何一个）",
      m._github_latency_caps(False, 0.1) == [])
check("不通 → 即使延迟很小也不报 net.github",
      "net.github" not in m._github_latency_caps(False, 0.1))

caps_fast = m._github_latency_caps(True, THRESH - 0.5)
check("通 + 延迟 < 阈值 → net.github + net.github.fast",
      set(caps_fast) == {"net.github", "net.github.fast"}, "实际 %r" % caps_fast)

caps_slow = m._github_latency_caps(True, THRESH + 0.5)
check("通 + 延迟 >= 阈值 → net.github + net.github.slow",
      set(caps_slow) == {"net.github", "net.github.slow"}, "实际 %r" % caps_slow)

caps_edge = m._github_latency_caps(True, THRESH)
check("边界值(恰好=阈值) 归入 slow（< 是 fast 的唯一判据，不是 <=）",
      set(caps_edge) == {"net.github", "net.github.slow"}, "实际 %r" % caps_edge)

# ── 第 2 层：真机实测（本机是 laptop，历史锚点=慢，但不写死断言机器身份，
#    只断言"标签自洽"——避免这条用例本身变成又一处硬编码猜测）────────────
real_caps = set(m.node_capabilities())
has_fast = "net.github.fast" in real_caps
has_slow = "net.github.slow" in real_caps
check("真探测：net.github 在场（本机确实连得通 github，前置条件）",
      "net.github" in real_caps, "实际 caps 子集: %s" %
      sorted(c for c in real_caps if c.startswith("net.")))
check("真探测：fast 与 slow 恰好命中一个，不多不少（互斥）",
      has_fast != has_slow, "fast=%s slow=%s" % (has_fast, has_slow))

finish()
