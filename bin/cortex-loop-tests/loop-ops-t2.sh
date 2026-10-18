#!/usr/bin/env bash
# T2 验收：机械可验 —— 该 job 在 live 里必须是 ok
# openclaw cron list 默认带 ANSI 色码（status=ok 渲染成 \e[32mok），
# 裸 grep ' ok ' 会假红。先剥色再判状态。
set -euo pipefail
line="$(openclaw cron list 2>/dev/null | grep 'mercury-daily-ops-report' || true)"
[[ -n "$line" ]] || { echo "mercury-daily-ops-report 不在 cron list"; exit 1; }
plain="$(printf '%s' "$line" | sed $'s/\x1b\\[[0-9;]*m//g')"
# 列格式：… last … status … — status 字段独立成词
printf '%s\n' "$plain" | grep -Eq '(^|[[:space:]])ok([[:space:]]|$)' \
  || { echo "mercury-daily-ops-report 仍非 ok"; echo "raw: $plain"; exit 1; }
echo "T2 PASS"
