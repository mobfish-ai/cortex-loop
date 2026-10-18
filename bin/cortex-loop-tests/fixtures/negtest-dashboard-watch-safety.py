#!/usr/bin/env python3
"""Fail if dashboard watch can redraw/kill outside its foreground process group."""

from __future__ import annotations

import os
from pathlib import Path
import pty
import signal
import subprocess
import tempfile
import termios
import time


ROOT = Path(__file__).resolve().parents[3]
DASH = ROOT / "bin" / "cortex-dashboard.sh"
source = DASH.read_text(encoding="utf-8")
watch = source.split("# ═══ --watch：安全的单前台刷新", 1)[1].split(
    "# ── 采集（全部真探）", 1
)[0]

for forbidden in ("pkill ", "pkill\t", "COLLECTOR", "kill -0", ") &"):
    if forbidden in watch:
        raise AssertionError(f"unsafe watch primitive returned: {forbidden}")

for required in ("\\033[?1049h", "\\033[?1049l", "\\033[?25l", "\\033[?25h"):
    if required not in source:
        raise AssertionError(f"watch screen lifecycle missing: {required}")

if '· 跑%s · 待%s · 结%s · 败%s · 下次%2ss · Ctrl-C' not in watch:
    raise AssertionError("watch pulse regressed from the bounded focus summary")
if '"${_watch_tasks:-任务读取中}"' in watch:
    raise AssertionError("watch pulse repeats the full task summary and can wrap narrow terminals")
if "sed -n '1p' \"$SNAP_TXT\"" not in watch:
    raise AssertionError("watch pulse no longer reads heartbeat from compact snapshot header")

with tempfile.TemporaryDirectory(prefix="cortex-dashboard-watch-") as tmp:
    home = Path(tmp)
    state = home / ".openclaw" / "state"
    state.mkdir(parents=True)
    (state / "cortex-dash-snapshot.txt").write_text("fixture snapshot\n", encoding="utf-8")
    env = os.environ.copy()
    env.update({"HOME": str(home), "CORTEX_DASH_INTERVAL": "60", "CORTEX_DASH_TEST_MODE": "1"})
    proc = subprocess.Popen(
        ["bash", str(DASH), "--watch"],
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )
    time.sleep(1)
    os.killpg(proc.pid, signal.SIGINT)
    output, _ = proc.communicate(timeout=15)
    if proc.returncode != 130:
        raise AssertionError(f"SIGINT exit={proc.returncode}; output={output[-500:]}")
    if "没有后台采集进程需要追杀" not in output:
        raise AssertionError("watch did not report safe foreground-only shutdown")
    if "\x1b" in output:
        raise AssertionError("non-TTY watch emitted terminal control sequences")
    # A foreground descendant can remain as a kernel zombie for a few scheduler
    # ticks after the shell has returned 130. Give init a bounded reap window;
    # never send another signal (the old accident was caused by cleanup killing).
    deadline = time.monotonic() + 2
    while True:
        try:
            os.killpg(proc.pid, 0)
        except ProcessLookupError:
            break
        if time.monotonic() >= deadline:
            raise AssertionError("dashboard process group survived SIGINT reap window")
        time.sleep(0.02)

print("PASS dashboard watch: foreground-only, non-TTY plain output, SIGINT leaves no process group")

# A pipe cannot exercise terminal line discipline. Use a real pseudo-terminal to
# prove that watch disables ordinary key echo while it owns the foreground and
# restores the caller's exact ECHO bit after Ctrl-C.
with tempfile.TemporaryDirectory(prefix="cortex-dashboard-watch-tty-") as tmp:
    home = Path(tmp)
    state = home / ".openclaw" / "state"
    state.mkdir(parents=True)
    (state / "cortex-dash-snapshot.txt").write_text("fixture snapshot\n", encoding="utf-8")
    env = os.environ.copy()
    env.update({"HOME": str(home), "CORTEX_DASH_INTERVAL": "60", "CORTEX_DASH_TEST_MODE": "1"})
    master_fd, slave_fd = pty.openpty()
    before = termios.tcgetattr(master_fd)
    proc = subprocess.Popen(
        ["bash", str(DASH), "--watch"],
        cwd=ROOT,
        env=env,
        stdin=slave_fd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )
    try:
        deadline = time.monotonic() + 5
        while termios.tcgetattr(master_fd)[3] & termios.ECHO:
            if proc.poll() is not None:
                raise AssertionError(f"TTY watch exited before disabling echo: {proc.returncode}")
            if time.monotonic() >= deadline:
                raise AssertionError("watch did not disable TTY echo")
            time.sleep(0.02)
        os.killpg(proc.pid, signal.SIGINT)
        output, _ = proc.communicate(timeout=15)
        if proc.returncode != 130:
            raise AssertionError(f"TTY SIGINT exit={proc.returncode}; output={output[-500:]}")
        after = termios.tcgetattr(master_fd)
        if bool(after[3] & termios.ECHO) != bool(before[3] & termios.ECHO):
            raise AssertionError("watch did not restore the caller's TTY echo state")
    finally:
        if proc.poll() is None:
            os.killpg(proc.pid, signal.SIGINT)
            proc.wait(timeout=15)
        os.close(master_fd)
        os.close(slave_fd)

print("PASS dashboard watch TTY: ordinary input hidden, Ctrl-C restores terminal state")

# Screen lifecycle is orthogonal to input line discipline. Force only the screen
# capability under explicit test mode so the exact enter/clear/restore bytes can
# be asserted through a pipe without fabricating a controlling-terminal session.
with tempfile.TemporaryDirectory(prefix="cortex-dashboard-watch-screen-") as tmp:
    home = Path(tmp)
    state = home / ".openclaw" / "state"
    state.mkdir(parents=True)
    (state / "cortex-dash-snapshot.txt").write_text("fixture snapshot\n", encoding="utf-8")
    env = os.environ.copy()
    env.update({
        "HOME": str(home),
        "CORTEX_DASH_INTERVAL": "60",
        "CORTEX_DASH_TEST_MODE": "1",
        "CORTEX_DASH_TEST_FORCE_SCREEN": "1",
    })
    proc = subprocess.Popen(
        ["bash", str(DASH), "--watch"], cwd=ROOT, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        start_new_session=True,
    )
    time.sleep(1)
    os.killpg(proc.pid, signal.SIGINT)
    output, _ = proc.communicate(timeout=15)
    if proc.returncode != 130:
        raise AssertionError(f"screen SIGINT exit={proc.returncode}; output={output[-500:]}")
    for required in ("\x1b[?1049h", "\x1b[?1049l", "\x1b[?25l", "\x1b[?25h"):
        if required not in output:
            raise AssertionError(f"screen lifecycle output missing: {required!r}")

print("PASS dashboard watch screen: alternate screen and cursor state restored")

with tempfile.TemporaryDirectory(prefix="cortex-dashboard-watch-compact-") as tmp:
    env = os.environ.copy()
    env.update({
        "HOME": tmp,
        "CORTEX_DASH_TEST_MODE": "1",
        "DASH_WATCH_COMPACT": "1",
    })
    compact = subprocess.run(
        ["bash", str(DASH)], cwd=ROOT, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        timeout=30, check=True,
    ).stdout
    lines = compact.splitlines()
    if len(lines) > 34:
        raise AssertionError(f"watch compact view exceeds one-screen budget: {len(lines)} lines")
    for heading in ("━━ 当前任务", "━━ 执行与交付", "━━ 节点分数", "━━ 机制红榜", "━━ 质量"):
        if heading not in compact:
            raise AssertionError(f"watch compact view missing focus block: {heading}")
    for verbose in ("✓ 最近完成", "开发工作区  登记"):
        if verbose in compact:
            raise AssertionError(f"watch compact view regressed verbose block: {verbose}")

print(f"PASS dashboard watch compact: {len(lines)} lines fit one screen")
