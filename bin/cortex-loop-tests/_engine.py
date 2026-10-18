"""把 bin/cortex-loop（无扩展名的 python3 引擎）当模块加载，供测试直接调内部函数。

用 SourceFileLoader 而不是 import：文件名带连字符且无 .py，普通 import 语法进不来。
模块名给 "cortexloop" 而非 "__main__" → 引擎末尾的 main() 守卫不会触发。
"""

import importlib.machinery
import importlib.util
import os

ENGINE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cortex-loop")


def load():
    loader = importlib.machinery.SourceFileLoader("cortexloop", ENGINE)
    spec = importlib.util.spec_from_loader("cortexloop", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


# ── 测试自用的极简断言（失败即非 0 退出，理由打到 stdout）────────────────

FAILURES = []


def check(label, condition, detail=""):
    if condition:
        print("    ok   %s" % label)
    else:
        FAILURES.append("%s%s" % (label, (" — %s" % detail) if detail else ""))
        print("    BAD  %s%s" % (label, (" — %s" % detail) if detail else ""))


def finish():
    if FAILURES:
        print("断言失败 %d 条：%s" % (len(FAILURES), " / ".join(FAILURES)))
        raise SystemExit(1)
    raise SystemExit(0)
