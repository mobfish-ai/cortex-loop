#!/usr/bin/env python3
"""负向测试：验收员的**标签本身**要机械核验，不能照单全收。

2026-07-29 真机根因（21/25 result 倒在这里）：
  ai_judge 的 prompt 已明写「执行器被硬性禁止改 bounds 之外的文件，
  所以『它没去改 bounds 外的 X』永远不构成 REJECT 理由」，并提供 SCOPE 第三态。
  验收员**仍然**回 REJECT，理由是「只加了 host: 一行，没跑 generate-taxonomy.py、
  没登记进 SKILLS-TAXONOMY.md」—— 点名的两个路径全在 bounds 外。

  上一版只对 SCOPE 分支做反向核验（点名路径若在界内 → 改判 REJECT），
  REJECT 分支照单全收 → **换个标签说同一件事就绕过了整道防线**。

教训：不能靠 prompt 让 LLM 自觉选对标签；**它选的标签本身也要机械验**。
这不是放宽门 —— 界内没干好仍然 REJECT，只是把「界外的事」正确改判为 SCOPE。

本测试直接调 _judge_verdict_from_text（纯函数，不调模型、不烧额度）。
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

BOUNDS = "skills/impeccable/"

# (标签, 验收员原始输出, 期望判定)
CASES = [
    # ── 红线：不许替验收员改标签（一次被推翻的修复，本条防它复活）────
    # 我曾让「REJECT 理由全在界外」自动改判 SCOPE，依据是 13:34 实测仍被 REJECT。
    # 但那一拍跑的是**修复前的代码**（日志里的旧字符串在当前代码中 0 处命中）。
    # 前提不成立，且替 AI 改标签是放宽门的隐蔽形式 —— 它把「验收员说不行」
    # 变成「系统说其实行」。真实证据相反：判据换成 short_test 后，
    # 同一产出同一验收员 11:09 REJECT → 13:41 ACCEPT。
    # 本条锁死：**验收员说 REJECT 就是 REJECT，系统不替它翻案。**
    ("验收员 REJECT 理由全在界外 → 仍然 REJECT（不许系统替它翻案）",
     "REJECT: 只加了 SKILL.md 里的 host: html-master 一行 frontmatter，"
     "但没跑 bin/generate-taxonomy.py 重新生成树、"
     "也没把 impeccable 登记进 skills/SKILLS-TAXONOMY.md",
     "REJECT"),

    # ── 界内没干好 → 必须仍然 REJECT（不许放宽）─────────────────
    ("界内空泛套话 → 保持 REJECT",
     "REJECT: 内容全是教科书模板，没有针对本机实况的任何具体信息",
     "REJECT"),
    ("点名的路径在界内 → 保持 REJECT",
     "REJECT: skills/impeccable/SKILL.md 里 host 字段写错了，指向不存在的 host",
     "REJECT"),
    ("界内界外混合点名 → 保持 REJECT（不是全部界外）",
     "REJECT: skills/impeccable/SKILL.md 没写完整，"
     "而且没登记进 skills/SKILLS-TAXONOMY.md",
     "REJECT"),
    ("没点名任何路径的 REJECT → 保持 REJECT",
     "REJECT: 产出过于简略",
     "REJECT"),

    # ── 正常通过与显式 SCOPE 不受影响 ───────────────────────────
    ("ACCEPT 原样放行",
     "ACCEPT", "ACCEPT"),
    ("显式 SCOPE 且路径在界外 → SCOPE",
     "SCOPE: skills/SKILLS-TAXONOMY.md bin/generate-taxonomy.py | 任务定义太窄",
     "SCOPE"),
    ("显式 SCOPE 但路径在界内 → 改判 REJECT（原有防线不许退化）",
     "SCOPE: skills/impeccable/SKILL.md | 说是超范围",
     "REJECT"),
]

fails = 0
for label, raw, want in CASES:
    got, why = cl._judge_verdict_from_text(raw, BOUNDS)
    ok = (got == want)
    fails += 0 if ok else 1
    print("%s  %-44s 判定=%-7s 期望=%s"
          % ("PASS" if ok else "FAIL", label, got, want))
    if not ok:
        print("       ↳ 引擎理由：%s" % why[:140])

print()
print("验收员标签机械核验：%s（%d 个断言失败）"
      % ("全绿" if fails == 0 else "有失败", fails))
sys.exit(1 if fails else 0)
