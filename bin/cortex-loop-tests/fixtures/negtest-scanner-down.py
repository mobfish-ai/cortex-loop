#!/usr/bin/env python3
"""负向测试：故意弄坏扫描器，验证 discover 会报出来而不是静默算 0 条。

不碰真文件 —— 用 SourceFileLoader 把引擎加载成模块后替换 SCANNERS。
用 `exit 124` 直接模拟超时码，不真 sleep 300（省 5 分钟）。
"""
import importlib.machinery
import importlib.util
import os
import sys

ENGINE_PATH = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "cortex-loop")

loader = importlib.machinery.SourceFileLoader("cl", ENGINE_PATH)
cl = importlib.util.module_from_spec(importlib.util.spec_from_loader("cl", loader))
loader.exec_module(cl)

# 只留被测扫描器，其它一律不跑（本测试只验退出码分诊这一件事）
cl.scan_self_defects = lambda: []
cl.scan_contract_debt = lambda: []
cl.scan_network_evenness = lambda: []
cl.scan_data_integrity = lambda: []
cl.scan_frontmatter_readable = lambda: []

CASES = [
    ("A 命令不存在", "this-command-does-not-exist-xyz", True),
    ("B 超时 exit 124", "exit 124", True),
    ("C 正常无匹配 exit 1 有输出", "echo '一切正常' && exit 1", False),
    ("D 正常有匹配 exit 0", "echo '未注册：foo-skill'", False),
]

fails = 0
for label, cmd, should_be_down in CASES:
    cl.SCANNERS = [("probe", cmd, r"未注册：(\S+)", "修 %s", "L1", "V2", "skills/")]
    found = cl.discover_candidates()
    down = cl.discover_candidates.last_broken
    is_down = bool(down)
    ok = (is_down == should_be_down)
    fails += 0 if ok else 1
    print("%s  %-28s  SCANNER-DOWN=%-5s 期望=%-5s 候选数=%d"
          % ("PASS" if ok else "FAIL", label, is_down, should_be_down, len(found)))

print()
print("负向测试：%s（%d 个断言失败）" % ("全绿" if fails == 0 else "有失败", fails))
sys.exit(1 if fails else 0)
