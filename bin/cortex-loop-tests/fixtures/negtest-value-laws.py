#!/usr/bin/env python3
"""负向测试：价值三定律 V1/V2/V3 真的机械核验，不是自报。

为什么必须有：2026-07-29 AFR (b) 我自己诚实标出的缺口 ——
六定律里 C1/C2/C3 已有负向测试（negtest-six-laws-gate.py），
但 V1/V2/V3 当时只验了"权重表存在"，没验"降级逻辑真的会触发"。
「权重表存在」≠「声明 V3 会被打回 V1」，跟 C 组当初的缺口同型。

被测函数 verify_value(task, artifact)：
  设计意图是「价值不能自报，要机械核验」—— 看产出**落在哪一层目录**，
  声明高于实际就打回实际。注意它是**单向**的：只降级不升级
  （声明 V1 但产出在 skills/ 仍按 V1 计，不主动抬高）。

判据来自 VALUE_LAYERS（引擎 :1686）：
  V3 = skills/_shared/ · bin/cortex-loop-adapters/ · brain-network/directions/_swarm/
  V2 = skills/ · bin/ · aboutme/methods/ · execution-recipes/ · work-studio/ · rules/ · brain-network/directions/
  V1 = reports/ · memory/ · /tmp/
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

# (标签, 声明的 value, 产出路径, 期望核验后的层级, 期望是否被打回)
CASES = [
    # ── 核心：吹牛必须被打回 ────────────────────────────────────────
    ("声明 V3 但产出在 reports/ → 打回 V1",
     "V3", "reports/2026-07-29/x.md", "V1", True),
    ("声明 V2 但产出在 memory/ → 打回 V1",
     "V2", "memory/2026-07-29.md", "V1", True),
    ("声明 V3 但产出在 skills/ → 打回 V2",
     "V3", "skills/foo/SKILL.md", "V2", True),
    ("声明 V3 但产出在 /tmp/ → 打回 V1（临时产出不算资产）",
     "V3", "/tmp/scratch.md", "V1", True),

    # ── 诚实声明必须原样放行 ────────────────────────────────────────
    ("V3 产出真在 skills/_shared/ → 保持 V3",
     "V3", "skills/_shared/normalizers.py", "V3", False),
    ("V3 产出真在 adapters → 保持 V3（新增执行器=给蜂群加能力）",
     "V3", "bin/cortex-loop-adapters/newruntime.sh", "V3", False),
    ("V2 产出真在 bin/ → 保持 V2",
     "V2", "bin/some-tool.sh", "V2", False),
    ("V1 产出在 reports/ → 保持 V1",
     "V1", "reports/2026-07-29/y.md", "V1", False),

    # ── 单向性：只降级不升级（保守设计，不替人吹牛）──────────────────
    ("声明 V1 但产出在 skills/_shared/ → 仍按 V1，不主动抬高",
     "V1", "skills/_shared/x.py", "V1", False),

    # ── 边界：未知路径兜底 V1，不能兜底成高价值 ─────────────────────
    ("产出在判据覆盖不到的路径 → 兜底 V1 不是兜底 V3",
     "V3", "some/unknown/path.md", "V1", True),
]

fails = 0
for label, claimed, artifact, want_level, want_demoted in CASES:
    level, note = cl.verify_value({"value": claimed}, artifact)
    demoted = bool(note)
    good = (level == want_level) and (demoted == want_demoted)
    fails += 0 if good else 1
    print("%s  %-46s 判定=%-3s 期望=%-3s  打回=%-5s 期望=%s"
          % ("PASS" if good else "FAIL", label, level, want_level,
             demoted, want_demoted))
    if not good and note:
        print("       ↳ 引擎说：%s" % note)

print()
print("价值三定律负向测试：%s（%d 个断言失败）"
      % ("全绿" if fails == 0 else "有失败", fails))
sys.exit(1 if fails else 0)
