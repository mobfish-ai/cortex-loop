#!/usr/bin/env python3
"""EX11 / T34 —— read_ref 与 list_refs 三态返回契约回归。

DIMENSIONAL 母题第 5 处：「空」与「查不到」必须可区分，否则下游会拿
"git 出错"假装"确认无数据"做 health/scanner/done 决策，说谎且不自愈。

本 fixture 不引诱 git 异常（环境依赖过重且不可重现），改用两条**确定可触**
的路径断言三态契约：

  1. 已知有 payload 的 ref → status="ok"，payload 非空
  2. 已知无 ref 的 namespace → status="empty"，refs 列表为空
  3. 错误态用 mock-monkey-patch `git()` 直接返回非 0 → status="error"，
     payload 为空。这样回归不需要外部故障注入器，git 调用本身也仍在走。

同时覆盖向后兼容：
  - parse_kv(read_ref(ref)) 仍按字符串切割（ReadRefResult IS str）
  - [r for r in list_refs(NS)] 仍按列表迭代（ListRefsResult IS list）
"""

import os
import random
import string
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
# bin/cortex-loop-tests/fixtures/negtest-read-ref-tristate.py
#   HERE   = .../bin/cortex-loop-tests/fixtures
#   PARENT = .../bin/cortex-loop-tests
#   GRAND  = .../bin
#   ROOT   = <repo-root>
PARENT = os.path.dirname(HERE)
GRAND = os.path.dirname(PARENT)
ROOT = os.path.dirname(GRAND)
sys.path.insert(0, PARENT)
import importlib.machinery
import importlib.util

loader = importlib.machinery.SourceFileLoader(
    "cortexloop",
    os.path.join(GRAND, "cortex-loop"),
)
spec = importlib.util.spec_from_loader(loader.name, loader)
m = importlib.util.module_from_spec(spec)
loader.exec_module(m)

FAILURES = []


def check(label, condition, detail=""):
    if condition:
        print("    ok   %s" % label)
    else:
        FAILURES.append("%s%s" % (label, (" — %s" % detail) if detail else ""))
        print("    BAD  %s%s" % (label, (" — %s" % detail) if detail else ""))


# 1. 类存在并支持三态枚举
check(
    "ReadRefResult 是 str 子类（向后兼容旧 parse_kv 调用）",
    issubclass(m.ReadRefResult, str),
    "类型不对，调用方 .split() 会坏",
)
check(
    "ListRefsResult 是 list 子类（向后兼容 [r for r in list_refs(NS)]）",
    issubclass(m.ListRefsResult, list),
    "类型不对，调用方迭代/索引会坏",
)

# 2. 构造路径覆盖三个 status 枚举
ok_inst = m.ReadRefResult("ok", "hello=world")
empty_inst = m.ReadRefResult("empty", "", "no payload")
err_inst = m.ReadRefResult("error", "", "git cat-file exit 128")
check("ReadRefResult status 字段分别可读 ok/empty/error",
      (ok_inst.status, empty_inst.status, err_inst.status) == ("ok", "empty", "error"),
      "实际 %r" % ((ok_inst.status, empty_inst.status, err_inst.status),))
check("ReadRefResult is_ok/is_empty/is_error 谓词各自独立",
      (ok_inst.is_ok, empty_inst.is_empty, err_inst.is_error) == (True, True, True),
      "实际 %r" % ((ok_inst.is_ok, empty_inst.is_empty, err_inst.is_error),))
check("ReadRefResult str() == payload（parse_kv 兼容）",
      str(ok_inst) == "hello=world" and str(empty_inst) == "" and str(err_inst) == "",
      "实际 %r/%r/%r" % (str(ok_inst), str(empty_inst), str(err_inst)))
check("ReadRefResult 是 str 实例，parse_kv 仍按行切",
      m.parse_kv(ok_inst) == {"hello": "world"},
      "实际 %r" % m.parse_kv(ok_inst))

list_ok = m.ListRefsResult("ok", ["refs/x/a", "refs/x/b"])
list_empty = m.ListRefsResult("empty", [])
list_err = m.ListRefsResult("error", [], "for-each-ref timeout")
check("ListRefsResult 是 list 实例，len/iter 兼容",
      len(list_ok) == 2 and list(list_empty) == [] and list(list_err) == [],
      "len/list 行为不对")
check("ListRefsResult status 三态独立",
      (list_ok.status, list_empty.status, list_err.status) == ("ok", "empty", "error"),
      "实际 %r" % ((list_ok.status, list_empty.status, list_err.status),))
check("ListRefsResult set() / sorted() / [r for r in] 旧用法兼容",
      sorted(list_ok) == ["refs/x/a", "refs/x/b"]
      and set(list_ok) == {"refs/x/a", "refs/x/b"}
      and [r for r in list_ok] == ["refs/x/a", "refs/x/b"],
      "迭代语义不对")

# 3. 真 git 路径 —— 已确认存在 / 已确认不存在的两条 ref
sfx = "".join(random.choice(string.ascii_lowercase + string.digits) for _ in range(8))
NS = "refs/swarm/tristate-test-%s" % sfx
REF = "%s/fakenode" % NS
PAYLOAD = "\n".join([
    "node=fakenode",
    "kind=always-on",
    "last_seen=%s" % m.fmt(m.now()),
])


def build_local_ref():
    code, blob = m.git("hash-object -w --stdin <<'CORTEXEOF'\n%s\nCORTEXEOF" % PAYLOAD)
    if code != 0:
        return False
    blob = blob.strip().split("\n")[-1]
    code, tree = m.git("mktree <<'CORTEXEOF'\n100644 blob %s\tpayload\nCORTEXEOF" % blob)
    if code != 0:
        return False
    tree = tree.strip().split("\n")[-1]
    code, commit = m.git("commit-tree %s -m tristate-suite" % tree)
    if code != 0:
        return False
    commit = commit.strip().split("\n")[-1]
    return m.git("update-ref %s %s" % (REF, commit))[0] == 0


try:
    check("本地测试 ref 造得出来", build_local_ref(), "plumbing 失败")

    r_ok = m.read_ref(REF)
    check("read_ref 已知存在 → status='ok'", getattr(r_ok, "status", None) == "ok",
          "status=%r" % getattr(r_ok, "status", None))
    check("read_ref 已知存在 → payload 含 'node=fakenode'",
          "node=fakenode" in r_ok, "读到 %r" % str(r_ok)[:80])

    r_empty = m.read_ref("%s/never-written" % NS)
    check("read_ref 已知不存在 → status='empty'（**不是** 'error'）",
          getattr(r_empty, "status", None) == "empty",
          "status=%r reason=%r" % (getattr(r_empty, "status", None),
                                    getattr(r_empty, "reason", None)))
    check("read_ref 已知不存在 → payload 仍为空串（parse_kv 兼容）",
          str(r_empty) == "", "实际 %r" % str(r_empty))

    lr_ok = m.list_refs(NS)
    check("list_refs 已知 ns → status='ok'", getattr(lr_ok, "status", None) == "ok",
          "status=%r" % getattr(lr_ok, "status", None))
    check("list_refs 已知 ns → refs 列表含 [REF]",
          list(lr_ok) == [REF], "实际 %r" % list(lr_ok))

    lr_empty = m.list_refs("refs/swarm/tristate-empty-%s" % sfx)
    check("list_refs 已知空 ns → status='empty'（**不是** 'error'）",
          getattr(lr_empty, "status", None) == "empty",
          "status=%r" % getattr(lr_empty, "status", None))
    check("list_refs 已知空 ns → refs 列表为 []（迭代兼容）",
          list(lr_empty) == [], "实际 %r" % list(lr_empty))

    # 4. 错误态 —— 只让 cat-file / for-each-ref 命令失败，
    #    rev-parse 仍要返回真 sha（不然 read_ref 在 rev_ref 处就 short-circuit 走 empty，
    #    测不到 cat-file 失败这条真正的错误路径）。
    orig_git = m.git

    def git_fail(cmd, *a, **kw):
        if "cat-file" in cmd or "for-each-ref" in cmd:
            return (128, "fatal: simulated failure")
        return orig_git(cmd, *a, **kw)

    m.git = git_fail
    try:
        r_err = m.read_ref(REF)
        check("read_ref cat-file 出错 → status='error'（**不**坍缩为 empty）",
              getattr(r_err, "status", None) == "error",
              "status=%r reason=%r" % (getattr(r_err, "status", None),
                                        getattr(r_err, "reason", None)))
        check("read_ref cat-file 出错 → payload 仍为空串（parse_kv 不崩）",
              str(r_err) == "", "实际 %r" % str(r_err))

        # list_refs 错误态
        lr_err = m.list_refs(NS)
        check("list_refs for-each-ref 出错 → status='error'（**不**坍缩为 empty）",
              getattr(lr_err, "status", None) == "error",
              "status=%r reason=%r" % (getattr(lr_err, "status", None),
                                        getattr(lr_err, "reason", None)))
        check("list_refs for-each-ref 出错 → refs 为 []（迭代兼容）",
              list(lr_err) == [], "实际 %r" % list(lr_err))

        # 三态互不重合（关键防回归点：别让 error 又被合并回 empty）
        s_err = getattr(r_err, "status", None)
        s_empty = "empty"
        check("错误态 status ≠ 'empty'（DIMENSIONAL 律第三态不可坍缩）",
              s_err != s_empty, "status=%r" % s_err)
    finally:
        m.git = orig_git

finally:
    m.git("update-ref -d %s" % REF)
    left = m.git("for-each-ref --format='%(refname)' " + NS)[1].strip()
    print("    清理：%s → %s" % (NS, "已清空" if not left else "残留 %s" % left))

if FAILURES:
    print("断言失败 %d 条：%s" % (len(FAILURES), " / ".join(FAILURES)))
    raise SystemExit(1)
print("T34 三态回归：全绿")
raise SystemExit(0)
