#!/usr/bin/env bash
# 清理僵尸 tick / 死锁文件 — 2026-07-31 血泪：旧 tick 占锁 1h+，task-add 全 BUSY。
#
# 三态退出：0=已清理或本来干净  1=需要 --force 但未给  2=探不清
# 默认只清「死 pid 锁」；活进程超龄需 --force（会 SIGTERM tick 组）
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT" || exit 2
LOCK="${CORTEX_TICK_LOCK:-/tmp/spotlight/cortex-loop.tick.lock}"
FORCE=0
MAX_MIN=90
while [ $# -gt 0 ]; do
  case "$1" in
    --force) FORCE=1; shift ;;
    --max-min) MAX_MIN="${2:?}"; shift 2 ;;
    -h|--help)
      echo "usage: $0 [--force] [--max-min N]"
      echo "  默认：清死 pid 锁；--force：杀超龄 tick 进程"
      exit 0 ;;
    *) echo "unknown: $1" >&2; exit 2 ;;
  esac
done

echo "=== cortex-loop-cleanup-stuck-tick ==="
bash bin/cortex-probe.sh tick-lock-free; rc_lock=$?
bash bin/cortex-probe.sh tick-not-zombie "$MAX_MIN"; rc_zom=$?

cleaned=0
if [ $rc_lock -eq 0 ]; then
  # YES lock free — 若文件在但死 pid，probe 也 YES
  if [ -f "$LOCK" ]; then
    pid="$(tr -cd '0-9' <"$LOCK" 2>/dev/null | head -c 12)"
    if [ -n "$pid" ] && ! kill -0 "$pid" 2>/dev/null; then
      rm -f "$LOCK"
      echo "removed dead-pid lock (was pid=$pid)"
      cleaned=1
    elif [ -z "$pid" ]; then
      # flock free 残留空文件
      if python3 - "$LOCK" <<'PY' 2>/dev/null
import fcntl,sys
h=open(sys.argv[1],"a+")
try:
  fcntl.flock(h.fileno(), fcntl.LOCK_EX|fcntl.LOCK_NB)
except BlockingIOError:
  sys.exit(1)
fcntl.flock(h.fileno(), fcntl.LOCK_UN)
sys.exit(0)
PY
      then
        rm -f "$LOCK"
        echo "removed orphan lock file"
        cleaned=1
      fi
    fi
  fi
  echo "RESULT: lock ok cleaned=$cleaned"
  exit 0
fi

if [ $rc_zom -eq 1 ] || [ $rc_lock -eq 1 ]; then
  if [ "$FORCE" -ne 1 ]; then
    echo "RESULT: stuck process present — re-run with --force to SIGTERM"
    echo "  probe tick-not-zombie → exit $rc_zom"
    exit 1
  fi
  # force: kill cortex-loop tick --auto
  pids="$(/usr/bin/pgrep -f 'cortex-loop tick' 2>/dev/null || true)"
  if [ -n "$pids" ]; then
    echo "SIGTERM pids: $pids"
    # shellcheck disable=SC2086
    kill -TERM $pids 2>/dev/null || true
    sleep 2
    # shellcheck disable=SC2086
    kill -KILL $pids 2>/dev/null || true
  fi
  rm -f "$LOCK"
  echo "RESULT: force-cleaned"
  exit 0
fi

echo "RESULT: UNKNOWN probe state lock=$rc_lock zombie=$rc_zom"
exit 2
