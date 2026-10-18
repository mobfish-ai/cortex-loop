#!/usr/bin/env python3
"""负向测试：一拍的时间预算必须够跑完一个真任务，且不能长到把时钟卡死。

为什么必须常驻回归（2026-07-29 真机实证）：
  worker 的 `TimeoutStartSec=300` 被红灯挡了整整一天没人看见 ——
  旧代码 health 恒 RED，49 秒就退出，**永远碰不到 300s 这个上限**。
  等 health 修绿、节点第一次真的开始干活，300s 立刻变成新天花板：

      22:14:02  Starting CORTEX cortex-loop tick...
      22:14:08  sync worker | ... | beat=ok
      22:19:08  start operation timed out. Terminating.   ← 整整 300s，每拍如此

  心跳照跳（ExecStartPre 的 sync 只要 6 秒），干活的 `tick --auto` 每拍必被 SIGTERM。
  于是节点在蜂群眼里「活着且健康」，实际产出恒为零 —— 比死了更难发现。

这正是高维展开律说的坍缩：「服务失败」这一个状态里，
  `status=1/FAILURE`（判据不让跑）和 `status=15/TERM`（跑得好好的被掐死）
是两件完全相反的事 —— 前者要修判据，后者要给时间。压成一个「服务红了」就分不出来。

两侧都必须挡：
  下界 —— 太短 = 真任务永远跑不完（本次实测踩到的）
  上界 —— ≥ 时钟周期 = 一拍卡死就永久占住槽位，后面每一拍都进不来
"""
import os
import re
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..")
_PRIVATE_UNITS = os.path.join(ROOT, "work-studio", "devops", "dotfiles", "systemd")
_PUBLIC_UNITS = os.path.join(ROOT, "examples", "systemd")
UNIT_DIR = _PRIVATE_UNITS if os.path.isfile(os.path.join(_PRIVATE_UNITS, "cortex-loop.service")) else _PUBLIC_UNITS

# 一次真拍的实测下界（worker 2026-07-29）：
#   health 里 `openclaw cron list` 单条就 39s，加 git ls-remote + 扫描 ≈ 60-90s，
#   之后才轮到真正执行任务。给真任务留不到 3.5 分钟 = 基本必被杀。
FLOOR = 600          # 秒；低于此值 = 真任务没有合理完成机会

fails = 0


def judge(timeout, period):
    """三态而非二态：TOO_SHORT / TOO_LONG / OK。

    不写成 bool，因为「太短」和「太长」的修法完全相反 ——
    压成一个 False 会让读的人不知道该往哪边调。
    """
    if timeout is None or period is None:
        return "UNKNOWN"          # 读不到就如实说读不到，不冒充 OK
    if timeout < FLOOR:
        return "TOO_SHORT"
    if timeout >= period:
        return "TOO_LONG"
    return "OK"


# ── 1. 判据本身必须真的会拦（负向：喂坏值必须被判坏）───────────────────
SCENARIOS = [
    # (timeout, period, 期望, 说明)
    (300,  900, "TOO_SHORT", "本次真机踩到的原值：真任务跑不完，每拍 SIGTERM"),
    (599,  900, "TOO_SHORT", "刚好在下界之下"),
    (600,  900, "OK",        "下界本身应放行"),
    (840,  900, "OK",        "留 60s 余量，一拍卡死最多吃掉一拍"),
    (900,  900, "TOO_LONG",  "等于周期：卡死就永久占槽，后面每拍都进不来"),
    (3600, 900, "TOO_LONG",  "远超周期"),
    (None, 900, "UNKNOWN",   "读不到就报未知，绝不倒向 OK（fail-open 最危险）"),
]
for timeout, period, want, why in SCENARIOS:
    got = judge(timeout, period)
    if got != want:
        print("FAIL  judge(%s,%s) 期望 %s 实得 %s —— %s" % (timeout, period, want, got, why))
        fails += 1
if not fails:
    print("PASS  时间预算判据 %d 场景全绿（含 3 条必须被拦的坏值）" % len(SCENARIOS))

# ── 2. 判据必须真能分出「被判据拦下」vs「跑着被掐死」──────────────────
# 这两种 systemd 失败长得很像，但一个要修判据、一个要给时间，绝不能混。
JOURNAL_CASES = [
    ("Main process exited, code=exited, status=1/FAILURE", "GATED",
     "判据不让跑（旧 health RED 那一类）"),
    ("Main process exited, code=killed, status=15/TERM",   "KILLED",
     "跑得好好的被超时掐死（本次这一类）"),
]


def classify(line):
    if "status=15/TERM" in line or "timed out" in line:
        return "KILLED"
    if "status=1/FAILURE" in line:
        return "GATED"
    return "UNKNOWN"


for line, want, why in JOURNAL_CASES:
    got = classify(line)
    if got != want:
        print("FAIL  classify 期望 %s 实得 %s —— %s" % (want, got, why))
        fails += 1
if not fails:
    print("PASS  两类 systemd 失败可区分（判据拦下 vs 被掐死，修法相反）")

# ── 3. 真文件必须过（git 追踪的真相源，不是副本）──────────────────────
svc = os.path.join(UNIT_DIR, "cortex-loop.service")
tmr = os.path.join(UNIT_DIR, "cortex-loop.timer")
if not (os.path.isfile(svc) and os.path.isfile(tmr)):
    print("FAIL  找不到 systemd 真相源：%s" % UNIT_DIR)
    sys.exit(1)


def grab(path, key):
    m = re.search(r"^\s*%s=(\d+)" % key, open(path, encoding="utf-8").read(), re.M)
    return int(m.group(1)) if m else None


t_out = grab(svc, "TimeoutStartSec")
t_per = grab(tmr, "OnUnitActiveSec")
verdict = judge(t_out, t_per)
if verdict != "OK":
    print("FAIL  真文件 TimeoutStartSec=%s / OnUnitActiveSec=%s → %s" % (t_out, t_per, verdict))
    print("      下界 %ds（真任务要跑得完）· 上界 < 周期（卡死不许永久占槽）" % FLOOR)
    fails += 1
else:
    print("PASS  真文件时间预算合理：%ds 拍上限 < %ds 时钟周期，且 ≥ %ds 下界"
          % (t_out, t_per, FLOOR))

sys.exit(1 if fails else 0)
