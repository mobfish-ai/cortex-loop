"""Load bin/cortex-loop (the extensionless python3 engine) as a module so tests can call internals directly.

Use SourceFileLoader instead of import: the filename has a hyphen and no .py, so a normal import cannot load it.
Name the module "cortexloop" rather than "__main__" so the main() guard at the end of the engine does not run.
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


# -- minimal assertions for tests (a failure exits non-zero and prints the reason to stdout) --

FAILURES = []


def check(label, condition, detail=""):
    if condition:
        print("    ok   %s" % label)
    else:
        FAILURES.append("%s%s" % (label, (" — %s" % detail) if detail else ""))
        print("    BAD  %s%s" % (label, (" — %s" % detail) if detail else ""))


def finish():
    if FAILURES:
        print("assertion failed %d: %s" % (len(FAILURES), " / ".join(FAILURES)))
        raise SystemExit(1)
    raise SystemExit(0)
