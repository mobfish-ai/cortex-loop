#!/usr/bin/env bash
# cortex-loop adapter: human — 安全默认值（不烧 token、不产生副作用）
# 约定接口：$1=提示词文件  $2=结果文件；退出码 0=已交付给执行者
set -euo pipefail
PROMPT="$1"; RESULT="$2"
INBOX="/tmp/spotlight/cortex-loop-human-inbox.md"

{
  echo "## $(date '+%Y-%m-%d %H:%M') 待人工执行"
  echo
  cat "$PROMPT"
  echo
  echo "---"
} >> "$INBOX"

cat > "$RESULT" <<EOF
executor=human
本轮未自动执行：CLOCK.md 里该线 executor=human（安全默认）。
提示词已投递到 ${INBOX}，等人工执行。
改成自动请把该线 executor 改为 claude / codex / openclaw。
EOF
echo "human adapter: 已投递 $INBOX"
