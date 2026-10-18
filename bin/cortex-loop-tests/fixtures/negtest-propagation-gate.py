#!/usr/bin/env python3
"""负向测试：传播门 v2 与 node_load 释放。

传播门用一个**临时 git 仓库**跑真实场景，不碰真库：
  A 文件有历史且已提交（干净）        → 应放行
  B 文件有历史但被改了没提交          → 应拦（这正是 v1 漏掉的那类）
  C 文件只 git add 没 commit（real1/R2 的原状） → 应拦
  D 文件根本没进过 git（untracked）    → 应拦
"""
import os
import subprocess
import sys
import tempfile

def sh(cwd, cmd):
    return subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True)

def gate(root, artifact):
    """复刻引擎里传播门 v2 的判据。"""
    dirty = sh(root, "git status --porcelain -- %s" % artifact).stdout
    seen = sh(root, "git log -1 --oneline -- %s" % artifact).stdout
    return not (dirty.strip() or not seen.strip())

def gate_v1(root, artifact):
    """v1 的判据，用来证明 v1 确实漏 B。"""
    seen = sh(root, "git log -1 --oneline -- %s" % artifact).stdout
    return bool(seen.strip())

tmp = tempfile.mkdtemp(prefix="gate-test-")
sh(tmp, "git init -q && git config user.email t@t && git config user.name t")

# A: 有历史且干净
open(os.path.join(tmp, "a.md"), "w").write("host: x\n")
sh(tmp, "git add a.md && git commit -q -m init")

# B: 有历史但改了没提交（v1 的漏洞）
open(os.path.join(tmp, "b.md"), "w").write("no host\n")
sh(tmp, "git add b.md && git commit -q -m init-b")
open(os.path.join(tmp, "b.md"), "w").write("host: x\n")      # 改了，不提交

# C: 只 add 没 commit
open(os.path.join(tmp, "c.md"), "w").write("host: x\n")
sh(tmp, "git add c.md")

# D: untracked
open(os.path.join(tmp, "d.md"), "w").write("host: x\n")

CASES = [("A 已提交且干净", "a.md", True),
         ("B 有历史但改了没提交", "b.md", False),
         ("C 只 add 没 commit", "c.md", False),
         ("D 完全没进 git", "d.md", False)]

fails = 0
print("传播门 v2 vs v1")
for label, f, expect in CASES:
    v2 = gate(tmp, f)
    v1 = gate_v1(tmp, f)
    ok = (v2 == expect)
    fails += 0 if ok else 1
    print("  %s  %-22s v2=%-5s 期望=%-5s   （v1=%s%s）"
          % ("PASS" if ok else "FAIL", label, v2, expect, v1,
             "  ← v1 在这里漏了" if v1 != expect else ""))

print()
print("传播门负向测试：%s（%d 个断言失败）" % ("全绿" if fails == 0 else "有失败", fails))
sys.exit(1 if fails else 0)
