#!/usr/bin/env python3
"""负向测试：六定律三关（covenant_check）真的会拦，且拦对定律。

为什么必须有（operator 2026-07-29 追问）：「写进规则」≠「机械化」。
STEER 律文档里声称 C1/C2/C3 各自约束哪一步，但文档声称不等于代码会拦。
本测试构造三种**必须被拦**的任务，断言：
  ① 确实被拦（不是放行）
  ② 拦它的是**正确的那条定律**（不是碰巧被别的关卡挡住）
第 ② 点尤其重要：如果三关顺序或判据写错，可能"拦对了但理由错了"，
下次改动时就会拆错关卡。

不碰真账本：直接调引擎内部函数，传构造的 dict。
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

PROF = {"node": "testnode"}

# (标签, task, trust, score, 期望放行?, 期望拦它的定律)
CASES = [
    # ── C1 意图为界：产出落在授权白名单外 ───────────────────────────
    ("C1 产出越界",
     {"bounds": "skills/", "artifact": "bin/somewhere-else.sh",
      "min_trust": "L1", "reversible": "yes"},
     "L5", 0.99, False, "C1 意图为界"),

    # C1 的合法例外：artifact="-" 是「无单一固定产出」占位符，不算越界。
    # 真机实测抓到过误拦（治理类扫描任务全被 C1 挡死），必须常驻回归。
    ("C1 占位符 - 不算越界",
     {"bounds": "skills/", "artifact": "-",
      "min_trust": "L1", "reversible": "yes"},
     "L5", 0.99, True, ""),

    # ── C2 信任为尺：节点信任低于任务要求 ───────────────────────────
    ("C2 信任不足",
     {"bounds": "", "artifact": "skills/x.md",
      "min_trust": "L4", "reversible": "yes"},
     "L1", 0.16, False, "C2 信任为尺"),

    # ── C3 安全为底：不可逆任务的两道子关 ───────────────────────────
    ("C3 不可逆 + 信任 < L4",
     {"bounds": "", "artifact": "skills/x.md",
      "min_trust": "L1", "reversible": "no", "approved_by": "operator"},
     "L3", 0.80, False, "C3 安全为底"),

    ("C3 不可逆 + 信任够但缺人类签名",
     {"bounds": "", "artifact": "skills/x.md",
      "min_trust": "L1", "reversible": "no", "approved_by": "-"},
     "L4", 0.90, False, "C3 安全为底"),

    ("C3 不可逆 + 信任够 + 有签名 → 放行",
     {"bounds": "", "artifact": "skills/x.md",
      "min_trust": "L1", "reversible": "no", "approved_by": "operator"},
     "L4", 0.90, True, ""),

    # ── 全绿对照组：三关都不该拦 ────────────────────────────────────
    ("全合规任务放行",
     {"bounds": "skills/", "artifact": "skills/x.md",
      "min_trust": "L1", "reversible": "yes"},
     "L3", 0.80, True, ""),
]

fails = 0
for label, task, trust, score, want_ok, want_law in CASES:
    ok, law, why = cl.covenant_check(task, PROF, trust, score)
    good = (ok == want_ok) and (want_ok or law == want_law)
    fails += 0 if good else 1
    print("%s  %-32s 放行=%-5s 期望=%-5s  拦它的=%-12s 期望=%s"
          % ("PASS" if good else "FAIL", label, ok, want_ok,
             law or "-", want_law or "-"))
    if not good:
        print("       ↳ 理由：%s" % why)

print()
print("六定律三关负向测试：%s（%d 个断言失败）"
      % ("全绿" if fails == 0 else "有失败", fails))
sys.exit(1 if fails else 0)
