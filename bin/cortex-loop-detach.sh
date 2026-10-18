#!/usr/bin/env bash
# cortex-loop-detach — 让长跑任务脱离终端存活
#
# 为什么需要：2026-07-29 实测，终端/会话崩溃会连带杀掉
#   · 正在下载的 ollama pull（死在 79%）
#   · 三个正在跑的 sub-agent
# launchd/systemd 的定时心跳不受影响（它们本就脱离终端），但**会话里手动起的长跑**会陪葬。
# tmux 把进程挂到独立 server 上，终端死了进程还活着。
#
# 用法：
#   bin/cortex-loop-detach.sh <会话名> <命令...>     启动（同名已存在则不重复起）
#   bin/cortex-loop-detach.sh --status <会话名>      看状态与最后 20 行输出
#   bin/cortex-loop-detach.sh --list                 列出所有 cortex 会话
#   bin/cortex-loop-detach.sh --wait <会话名> [超时秒] 等它结束（默认 3600）
#
# 约定：所有会话名加 cx- 前缀，日志落 /tmp/spotlight/detach-<name>.log
set -uo pipefail
export PATH="$HOME/.local/bin:$HOME/.nvm/versions/node/v22.22.0/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
LOGDIR=/tmp/spotlight
mkdir -p "$LOGDIR"

command -v tmux >/dev/null || { echo "本机未装 tmux —— 无法脱离终端存活" >&2; exit 127; }

case "${1:-}" in
  --list)
    tmux ls 2>/dev/null | grep '^cx-' || echo "（无 cortex 会话）"
    exit 0 ;;
  --status)
    name="cx-${2:?缺会话名}"
    if tmux has-session -t "$name" 2>/dev/null; then
      echo "▶ $name 运行中"
    else
      echo "■ $name 已结束"
    fi
    echo "--- 最后 20 行 ---"
    tail -20 "$LOGDIR/detach-${2}.log" 2>/dev/null || echo "（无日志）"
    exit 0 ;;
  --wait)
    name="cx-${2:?缺会话名}"; limit="${3:-3600}"; waited=0
    while tmux has-session -t "$name" 2>/dev/null; do
      sleep 5; waited=$((waited+5))
      [[ $waited -ge $limit ]] && { echo "等待超时 ${limit}s，进程仍在跑（不杀它）"; exit 3; }
    done
    echo "$name 已结束（等待 ${waited}s）"
    tail -5 "$LOGDIR/detach-${2}.log" 2>/dev/null
    exit 0 ;;
esac

raw="${1:?用法: cortex-loop-detach.sh <会话名> <命令...>}"; shift
name="cx-${raw}"
log="$LOGDIR/detach-${raw}.log"

if tmux has-session -t "$name" 2>/dev/null; then
  echo "▶ $name 已在跑，不重复启动（幂等）"
  echo "看进度：bin/cortex-loop-detach.sh --status $raw"
  exit 0
fi

# 用 tee 落盘：tmux 缓冲区会滚掉，日志文件不会
tmux new-session -d -s "$name" "{ $*; } 2>&1 | tee '$log'"
echo "▶ 已在 tmux 会话 $name 中启动，终端挂掉也不影响"
echo "  看进度：bin/cortex-loop-detach.sh --status $raw"
echo "  等结束：bin/cortex-loop-detach.sh --wait $raw"
echo "  日志：  $log"
