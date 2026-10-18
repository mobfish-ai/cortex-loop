#!/usr/bin/env python3
"""C9 — 节点自我画像字段齐全，can_sleep 只能是 yes/no。

can_sleep 是蜂群唯一能区分「合盖睡觉」和「掉线」的字段：它一旦缺失或写歪，
笔记本过夜就会被判成故障并被抢走线（抖动比停摆更伤）。所以它必须是硬断言。

只读：node_profile() 不写任何文件（写盘的是 write_profile，本用例不碰）。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _engine import check, finish, load  # noqa: E402

m = load()
prof = m.node_profile()
print("    画像：%s" % prof)

REQUIRED = ("node", "kind", "can_sleep", "executors", "telegram_reach", "last_seen", "owns")
missing = [f for f in REQUIRED if f not in prof or prof[f] in ("", None)]
check("7 个字段齐全", not missing, "缺 %s" % missing)
check("can_sleep ∈ {yes,no}", prof.get("can_sleep") in ("yes", "no"),
      "实际 %r" % prof.get("can_sleep"))
check("kind ∈ {laptop,always-on}", prof.get("kind") in ("laptop", "always-on"),
      "实际 %r" % prof.get("kind"))
check("telegram_reach ∈ {yes,no}", prof.get("telegram_reach") in ("yes", "no"),
      "实际 %r" % prof.get("telegram_reach"))
check("last_seen 可解析且为整点精度", (m.parse_ts(prof.get("last_seen")) is not None
                                and prof.get("last_seen", "").endswith(":00")),
      "实际 %r" % prof.get("last_seen"))
check("executors 含 mock（零成本执行器必须在册）", "mock" in prof.get("executors", ""),
      "实际 %r" % prof.get("executors"))
check("node 是合法标识（无空格）", prof.get("node") and " " not in prof["node"],
      "实际 %r" % prof.get("node"))

# 一致性：quiet_limit 必须跟着 can_sleep 走，不能两台机器一把尺子
check("can_sleep=yes → 阈值 14h", m.quiet_limit({"can_sleep": "yes"}) == 14)
check("can_sleep=no → 阈值 3h", m.quiet_limit({"can_sleep": "no"}) == 3)

finish()
