#!/usr/bin/env python3
"""超时必须杀掉整个执行进程组，不能留下持管道的孤儿。"""
import importlib.machinery
import importlib.util
import os
import sys
import tempfile
import time


ENGINE = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "cortex-loop")
loader = importlib.machinery.SourceFileLoader("cl_timeout", ENGINE)
cl = importlib.util.module_from_spec(importlib.util.spec_from_loader("cl_timeout", loader))
loader.exec_module(cl)


with tempfile.TemporaryDirectory(prefix="cortex-timeout-") as tmp:
    pid_path = os.path.join(tmp, "grandchild.pid")
    command = "sh -c 'sleep 60 & echo $! > %s; wait'" % pid_path
    started = time.monotonic()
    code, output = cl.run(command, timeout=0.2)
    elapsed = time.monotonic() - started

    if code != 124 or "TimeoutExpired" not in output:
        print("FAIL  超时没有返回 124：code=%r output=%r" % (code, output[-200:]))
        sys.exit(1)
    if elapsed > 6:
        print("FAIL  超时后仍被遗留管道拖住：elapsed=%.2fs" % elapsed)
        sys.exit(1)
    try:
        child_pid = int(open(pid_path, encoding="utf-8").read().strip())
    except (OSError, ValueError) as exc:
        print("FAIL  未形成可核对的孙进程 PID：%s" % exc)
        sys.exit(1)

    alive = True
    for _ in range(20):
        try:
            os.kill(child_pid, 0)
        except ProcessLookupError:
            alive = False
            break
        time.sleep(0.05)
    if alive:
        print("FAIL  孙进程 %d 在 timeout 后仍存活（孤儿泄漏）" % child_pid)
        sys.exit(1)

print("PASS  timeout=124 且整组进程终止，无孤儿持管道")
