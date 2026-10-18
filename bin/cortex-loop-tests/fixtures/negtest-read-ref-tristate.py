#!/usr/bin/env python3
"""EX11 / T34 -- regression for the three-state return contract of read_ref and list_refs.

DIMENSIONAL theme, site 5: "empty" and "could not look it up" must stay distinguishable,
or a downstream health/scanner/done decision will treat "git failed" as "confirmed no data",
which lies and does not heal itself.

This fixture does not induce a git fault (too environment-dependent to reproduce). It asserts
the three-state contract on two paths that are deterministically reachable:

  1. a ref known to have a payload -> status="ok", payload non-empty
  2. a namespace known to have no ref -> status="empty", refs list empty
  3. the error state monkey-patches `git()` to return non-zero -> status="error",
     payload empty. The regression needs no external fault injector, and git is still called.

Also covers backward compatibility:
  - parse_kv(read_ref(ref)) still splits a string (ReadRefResult IS str)
  - [r for r in list_refs(NS)] still iterates a list (ListRefsResult IS list)
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


# 1. The classes exist and support the three-state enum
check(
    "ReadRefResult is a str subclass (old parse_kv callers stay compatible)",
    issubclass(m.ReadRefResult, str),
    "wrong type; caller .split() would break",
)
check(
    "ListRefsResult is a list subclass (old [r for r in list_refs(NS)] stays compatible)",
    issubclass(m.ListRefsResult, list),
    "wrong type; caller iteration/indexing would break",
)

# 2. Construction covers the three status values
ok_inst = m.ReadRefResult("ok", "hello=world")
empty_inst = m.ReadRefResult("empty", "", "no payload")
err_inst = m.ReadRefResult("error", "", "git cat-file exit 128")
check("ReadRefResult status field reads ok/empty/error",
      (ok_inst.status, empty_inst.status, err_inst.status) == ("ok", "empty", "error"),
      "actual %r" % ((ok_inst.status, empty_inst.status, err_inst.status),))
check("ReadRefResult is_ok/is_empty/is_error predicates are independent",
      (ok_inst.is_ok, empty_inst.is_empty, err_inst.is_error) == (True, True, True),
      "actual %r" % ((ok_inst.is_ok, empty_inst.is_empty, err_inst.is_error),))
check("ReadRefResult str() == payload (parse_kv compatible)",
      str(ok_inst) == "hello=world" and str(empty_inst) == "" and str(err_inst) == "",
      "actual %r/%r/%r" % (str(ok_inst), str(empty_inst), str(err_inst)))
check("ReadRefResult is a str instance, and parse_kv still splits lines",
      m.parse_kv(ok_inst) == {"hello": "world"},
      "actual %r" % m.parse_kv(ok_inst))

list_ok = m.ListRefsResult("ok", ["refs/x/a", "refs/x/b"])
list_empty = m.ListRefsResult("empty", [])
list_err = m.ListRefsResult("error", [], "for-each-ref timeout")
check("ListRefsResult is a list instance; len/iter compatible",
      len(list_ok) == 2 and list(list_empty) == [] and list(list_err) == [],
      "len/list behavior is wrong")
check("ListRefsResult status values are independent",
      (list_ok.status, list_empty.status, list_err.status) == ("ok", "empty", "error"),
      "actual %r" % ((list_ok.status, list_empty.status, list_err.status),))
check("ListRefsResult set() / sorted() / [r for r in] old usage stays compatible",
      sorted(list_ok) == ["refs/x/a", "refs/x/b"]
      and set(list_ok) == {"refs/x/a", "refs/x/b"}
      and [r for r in list_ok] == ["refs/x/a", "refs/x/b"],
      "iteration semantics are wrong")

# 3. Real git path -- one ref known to exist, one known not to exist
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
    check("local test ref can be built", build_local_ref(), "plumbing failed")

    r_ok = m.read_ref(REF)
    check("read_ref known to exist -> status='ok'", getattr(r_ok, "status", None) == "ok",
          "status=%r" % getattr(r_ok, "status", None))
    check("read_ref known to exist -> payload contains 'node=fakenode'",
          "node=fakenode" in r_ok, "read %r" % str(r_ok)[:80])

    r_empty = m.read_ref("%s/never-written" % NS)
    check("read_ref known to be missing -> status='empty' (**not** 'error')",
          getattr(r_empty, "status", None) == "empty",
          "status=%r reason=%r" % (getattr(r_empty, "status", None),
                                    getattr(r_empty, "reason", None)))
    check("read_ref known to be missing -> payload is still the empty string (parse_kv compatible)",
          str(r_empty) == "", "actual %r" % str(r_empty))

    lr_ok = m.list_refs(NS)
    check("list_refs known ns -> status='ok'", getattr(lr_ok, "status", None) == "ok",
          "status=%r" % getattr(lr_ok, "status", None))
    check("list_refs known ns -> refs list is [REF]",
          list(lr_ok) == [REF], "actual %r" % list(lr_ok))

    lr_empty = m.list_refs("refs/swarm/tristate-empty-%s" % sfx)
    check("list_refs known-empty ns -> status='empty' (**not** 'error')",
          getattr(lr_empty, "status", None) == "empty",
          "status=%r" % getattr(lr_empty, "status", None))
    check("list_refs known-empty ns -> refs list is [] (iteration compatible)",
          list(lr_empty) == [], "actual %r" % list(lr_empty))

    # 4. Error state -- fail only cat-file / for-each-ref.
    #    rev-parse must still return a real sha (otherwise read_ref short-circuits to empty
    #    at rev_ref, and the real cat-file failure path is never tested).
    orig_git = m.git

    def git_fail(cmd, *a, **kw):
        if "cat-file" in cmd or "for-each-ref" in cmd:
            return (128, "fatal: simulated failure")
        return orig_git(cmd, *a, **kw)

    m.git = git_fail
    try:
        r_err = m.read_ref(REF)
        check("read_ref cat-file error -> status='error' (**not** collapsed to empty)",
              getattr(r_err, "status", None) == "error",
              "status=%r reason=%r" % (getattr(r_err, "status", None),
                                        getattr(r_err, "reason", None)))
        check("read_ref cat-file error -> payload is still the empty string (parse_kv does not crash)",
              str(r_err) == "", "actual %r" % str(r_err))

        # list_refs error state
        lr_err = m.list_refs(NS)
        check("list_refs for-each-ref error -> status='error' (**not** collapsed to empty)",
              getattr(lr_err, "status", None) == "error",
              "status=%r reason=%r" % (getattr(lr_err, "status", None),
                                        getattr(lr_err, "reason", None)))
        check("list_refs for-each-ref error -> refs is [] (iteration compatible)",
              list(lr_err) == [], "actual %r" % list(lr_err))

        # The three states do not overlap (regression point: do not merge error back into empty)
        s_err = getattr(r_err, "status", None)
        s_empty = "empty"
        check("error status != 'empty' (DIMENSIONAL third state must not collapse)",
              s_err != s_empty, "status=%r" % s_err)
    finally:
        m.git = orig_git

finally:
    m.git("update-ref -d %s" % REF)
    left = m.git("for-each-ref --format='%(refname)' " + NS)[1].strip()
    print("    cleanup: %s -> %s" % (NS, "cleared" if not left else "left %s" % left))

if FAILURES:
    print("%d assertions failed: %s" % (len(FAILURES), " / ".join(FAILURES)))
    raise SystemExit(1)
print("T34 three-state regression: ALL PASS")
raise SystemExit(0)
