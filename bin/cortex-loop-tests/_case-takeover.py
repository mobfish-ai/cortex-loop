#!/usr/bin/env python3
"""C10 — liveness buffer vs scheduler eligibility.

takeover_ready stays conservative: a node is takeover-ready only after twice
its quiet limit. owns_line is no longer that lock. CLOCK.owner is an affinity
hint. A node with a fresh heartbeat may compete for the short scheduler lease;
git CAS stops two nodes from scheduling the same pass. A process with no swarm
profile still cannot schedule.

In-memory profiles only. No files, refs, or _swarm/ writes.
"""

import os
import sys
from datetime import timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _engine import check, finish, load  # noqa: E402

m = load()
os.environ["CORTEX_NODE"] = "aa-tester"          # 排序第一，保证「该我接管」


def prof(node, can_sleep, hours_ago):
    return {"node": node, "kind": "laptop" if can_sleep == "yes" else "always-on",
            "can_sleep": can_sleep, "owns": "testline",
            "last_seen": m.fmt(m.now() - timedelta(hours=hours_ago))}


ME = prof("aa-tester", "no", 0)
ENTRY = {"line": "testline", "owner": "sleepy-laptop", "enabled": "yes"}

# ① 笔记本静默 6h：阈值 14h 内 → 还活着，更不该接管
nodes = {"aa-tester": ME, "sleepy-laptop": prof("sleepy-laptop", "yes", 6)}
alive, why = m.node_alive(nodes["sleepy-laptop"])
check("笔记本静默 6h 判活", alive, why)
check("静默 6h 本节点仍可竞争短租约", m.owns_line(ENTRY, nodes) is True)

# ② 笔记本静默 20h：超 14h 阈值但没到 28h 缓冲 → 判死，但仍不接管
nodes["sleepy-laptop"] = prof("sleepy-laptop", "yes", 20)
alive, why = m.node_alive(nodes["sleepy-laptop"])
check("笔记本静默 20h 判死", alive is False, why)
check("静默 20h 仍在缓冲期内不接管", m.takeover_ready(nodes["sleepy-laptop"]) is False)
check("静默 20h 本节点仍可竞争短租约", m.owns_line(ENTRY, nodes) is True)

# ③ 笔记本静默 40h：超 2 倍缓冲 → 接管
nodes["sleepy-laptop"] = prof("sleepy-laptop", "yes", 40)
check("静默 40h 超缓冲", m.takeover_ready(nodes["sleepy-laptop"]) is True)
check("静默 40h 由存活节点接管", m.owns_line(ENTRY, nodes) is True)

# ④ 常开机静默 4h：3h 阈值 → 判死；但 8h 缓冲未过 → 仍不接管（同一把尺子两段语义）
srv = {"aa-tester": ME, "srv": prof("srv", "no", 4)}
check("常开机静默 4h 判死", m.node_alive(srv["srv"])[0] is False)
check("常开机静默 4h 未超缓冲，本节点仍可竞争",
      m.takeover_ready(srv["srv"]) is False
      and m.owns_line({"line": "testline", "owner": "srv"}, srv) is True)
srv["srv"] = prof("srv", "no", 9)
check("常开机静默 9h 超 2 倍缓冲 → 接管",
      m.owns_line({"line": "testline", "owner": "srv"}, srv) is True)

# ⑤ owner 是自己 / 空 / '-' → 永远归自己，跟画像无关
for owner in ("aa-tester", "", "-"):
    check("owner=%r 直接归本节点" % owner,
          m.owns_line({"line": "testline", "owner": owner}, {}) is True)

# ⑥ owner 不在名册里不再锁死整条线；本节点有新鲜心跳就可以竞争。
check("owner 未知时本节点有心跳仍可竞争",
      m.owns_line({"line": "testline", "owner": "ghost"}, srv) is True)
# ⑦ 本节点没有画像 → 保守拒绝，避免未登记进程自动调度。
check("本节点无画像则不可调度",
      m.owns_line(ENTRY, {"sleepy-laptop": prof("sleepy-laptop", "yes", 40)}) is False)

print("    本用例零落盘：未写 _swarm/、未建 ref、未改账本")
finish()
