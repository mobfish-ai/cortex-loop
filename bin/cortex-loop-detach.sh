#!/usr/bin/env bash
# cortex-loop-detach — keep a long run alive after the terminal dies
#
# Why: on 2026-07-29 a terminal/session crash also killed
#   - an ollama pull still downloading (died at 79%)
#   - three sub-agents that were running
# launchd/systemd heartbeats are unaffected (they are already detached), but a **long run started by hand in the session** dies with it.
# tmux hangs the process on its own server, so the process lives after the terminal dies.
#
# Usage:
#   bin/cortex-loop-detach.sh <session-name> <command...>     start (do not start again if that name exists)
#   bin/cortex-loop-detach.sh --status <session-name>      show status and the last 20 lines
#   bin/cortex-loop-detach.sh --list                 list every cortex session
#   bin/cortex-loop-detach.sh --wait <session-name> [timeout-seconds] wait until it ends (default 3600)
#
# Convention: every session name gets a cx- prefix; logs go to /tmp/spotlight/detach-<name>.log
set -uo pipefail
export PATH="$HOME/.local/bin:$HOME/.nvm/versions/node/v22.22.0/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
LOGDIR=/tmp/spotlight
mkdir -p "$LOGDIR"

command -v tmux >/dev/null || { echo "tmux is not installed; cannot keep the process alive after the terminal exits" >&2; exit 127; }

case "${1:-}" in
  --list)
    tmux ls 2>/dev/null | grep '^cx-' || echo "(no cortex sessions)"
    exit 0 ;;
  --status)
    name="cx-${2:?missing session name}"
    if tmux has-session -t "$name" 2>/dev/null; then
      echo "▶ $name running"
    else
      echo "■ $name finished"
    fi
    echo "--- last 20 lines ---"
    tail -20 "$LOGDIR/detach-${2}.log" 2>/dev/null || echo "(no log)"
    exit 0 ;;
  --wait)
    name="cx-${2:?missing session name}"; limit="${3:-3600}"; waited=0
    while tmux has-session -t "$name" 2>/dev/null; do
      sleep 5; waited=$((waited+5))
      [[ $waited -ge $limit ]] && { echo "wait timed out after ${limit}s; process is still running (not killing it)"; exit 3; }
    done
    echo "$name finished (waited ${waited}s)"
    tail -5 "$LOGDIR/detach-${2}.log" 2>/dev/null
    exit 0 ;;
esac

raw="${1:?usage: cortex-loop-detach.sh <session-name> <command...>}"; shift
name="cx-${raw}"
log="$LOGDIR/detach-${raw}.log"

if tmux has-session -t "$name" 2>/dev/null; then
  echo "▶ $name is already running; not starting again (idempotent)"
  echo "status: bin/cortex-loop-detach.sh --status $raw"
  exit 0
fi

# tee writes the log: the tmux buffer scrolls away, the log file does not
tmux new-session -d -s "$name" "{ $*; } 2>&1 | tee '$log'"
echo "▶ started in tmux session $name; a dead terminal will not stop it"
echo "  status: bin/cortex-loop-detach.sh --status $raw"
echo "  wait:   bin/cortex-loop-detach.sh --wait $raw"
echo "  log:    $log"
