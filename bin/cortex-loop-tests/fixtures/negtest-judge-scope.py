#!/usr/bin/env python3
"""负向测试：ai_judge 的 SCOPE 第三态**不是免死金牌**。

为什么必须有（2026-07-29 真机根因）：
  25 条 result 里 21 条 `gate=rejected`，机械门**全过**，全部倒在 AI 验收员。
  根因是调用方把 `success_criteria` 填成 `task["title"]`（一句愿景式描述），
  且 prompt 从未传 `short_test` / `bounds` —— 验收员手里没有客观判据，只能
  自行发明最大化解释，于是连续要求执行器去改 `skills/SKILLS-TAXONOMY.md`
  等**bounds 之外**的文件。而 C1 意图为界明令禁止执行器碰 bounds 外的路径：
  照办记违约、不照办被 REJECT，两条路都是死的。

修法是**给判据**，不是**放宽门**。为此展开了第三态 SCOPE
（界内做完了但任务定义本身太窄）。第三态天然有被滥用的风险：
验收员只要回一句 SCOPE 就能让任何东西过门。所以代码侧加了硬校验：
  · SCOPE 必须点名 bounds 外的具体路径；一个都没点名 → 降级 REJECT
  · 点名的路径必须**确实**在 bounds 之外；有一条在界内 → 降级 REJECT

本测试直接打桩 run_adapter 喂各种验收员回话，断言解析与降级逻辑正确。
破坏性验证：把 `if inside:` 那段删掉 → 用例「点名的路径其实在界内」立刻 FAIL。

不碰真账本、不联网、不烧模型额度：run_adapter 被替换成纯函数桩。
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

TASK = {
    "id": "island-x", "title": "把孤岛 skill x 挂进 host 树（网络连通）",
    "success_criteria": "以机械判据为准：grep -qE '^host:' skills/x/SKILL.md",
    "short_test": "grep -qE '^host:' skills/x/SKILL.md",
    "bounds": "skills/x/",
    "failure_modes": "泛化套话",
    "artifact_paths": "skills/x/SKILL.md",
}

# (标签, 验收员回话, 期望 verdict, 理由里必须出现的关键字)
CASES = [
    ("干净 ACCEPT", "ACCEPT", "ACCEPT", ""),

    ("界内没干好 → REJECT",
     "REJECT: 只有标题没有实质内容", "REJECT", "标题"),

    # 这一条就是真机上连续发生 6 次的那种否决 —— 修好后必须是 SCOPE 不是 REJECT
    ("只差 bounds 外的路径 → SCOPE（不再冤判 failed）",
     "SCOPE: skills/SKILLS-TAXONOMY.md skills/html-master/SKILL.md | 还需注册进总表",
     "SCOPE", "SKILLS-TAXONOMY"),

    # ↓↓↓ 以下三条是「第三态不许被滥用」的硬保险 ↓↓↓
    ("SCOPE 但一个路径都没点名 → 降级 REJECT",
     "SCOPE: 我觉得还差点意思", "REJECT", "没点名"),

    ("SCOPE 但点名的路径其实在 bounds 内 → 降级 REJECT",
     "SCOPE: skills/x/ERRORS.md | 还缺错题本", "REJECT", "bounds 内"),

    ("SCOPE 里混进一条界内路径 → 整条降级 REJECT",
     "SCOPE: skills/SKILLS-TAXONOMY.md skills/x/ERRORS.md | 两处都缺",
     "REJECT", "bounds 内"),

    # 失败关闭：验证器自己没跑起来 ≠ 内容没问题（原有行为，防回归）
    ("adapter 挂了 → REJECT（失败关闭不是失败开放）",
     "[ADAPTER_FAILED rc=1]\nAPI Error: 502", "REJECT", "验证器未能正常运行"),

    ("空输出 → REJECT", "", "REJECT", "验证器未能正常运行"),

    # bounds 未限定时无法判「界外」，SCOPE 无从校验 → 只能按不合格计，不能放行
    ("bounds 为空 → SCOPE 无法校验，降级 REJECT",
     "SCOPE: skills/anything.md | 缺东西", "REJECT", "bounds 内"),
]

fails = []
for label, reply, want_verdict, want_kw in CASES:
    cl.run_adapter = (lambda r: (lambda *a, **k: r))(reply)
    task = dict(TASK)
    if label.startswith("bounds 为空"):
        task["bounds"] = ""
    got_verdict, got_reason = cl.ai_judge("testline", "stub", task)
    if got_verdict != want_verdict:
        fails.append("%s — 期望 %s，实得 %s（理由：%s）"
                     % (label, want_verdict, got_verdict, got_reason[:120]))
        print("  BAD  %s — 期望 %s 实得 %s" % (label, want_verdict, got_verdict))
        continue
    if want_kw and want_kw not in got_reason:
        fails.append("%s — verdict 对但理由里没有 %r：%s" % (label, want_kw, got_reason[:120]))
        print("  BAD  %s — 理由缺关键字 %r" % (label, want_kw))
        continue
    print("  ok   %s → %s" % (label, got_verdict))

# 纯函数 _paths_outside_bounds 的边界（SCOPE 校验的地基）
for label, paths, bounds, want in [
    ("多 bounds 命中任一即算界内", ["skills/x/a.md"], "bin/ skills/x/", []),
    ("确实界外", ["skills/SKILLS-TAXONOMY.md"], "skills/x/", ["skills/SKILLS-TAXONOMY.md"]),
    ("bounds 空 = 无边界 = 都算界内", ["anything"], "", []),
]:
    got = cl._paths_outside_bounds(paths, bounds)
    if got != want:
        fails.append("_paths_outside_bounds %s — 期望 %s 实得 %s" % (label, want, got))
        print("  BAD  _paths_outside_bounds %s" % label)
    else:
        print("  ok   _paths_outside_bounds %s" % label)

if fails:
    print("\n断言失败 %d 条：%s" % (len(fails), " / ".join(fails)))
    sys.exit(1)
print("\nSCOPE 第三态 %d 场景全绿（含 4 条防滥用降级）" % (len(CASES) + 3))
