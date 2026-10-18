#!/usr/bin/env bash
# T2 acceptance: mechanically checkable -- that job must be ok in the live list
# openclaw cron list emits ANSI color by default (status=ok renders as \e[32mok),
# so a raw grep for ' ok ' false-fails. Strip color before judging status.
set -euo pipefail
line="$(openclaw cron list 2>/dev/null | grep 'mercury-daily-ops-report' || true)"
[[ -n "$line" ]] || { echo "mercury-daily-ops-report is not in the cron list"; exit 1; }
plain="$(printf '%s' "$line" | sed $'s/\x1b\\[[0-9;]*m//g')"
# Column layout: ... last ... status ... -- the status field is its own word
printf '%s\n' "$plain" | grep -Eq '(^|[[:space:]])ok([[:space:]]|$)' \
  || { echo "mercury-daily-ops-report is still not ok"; echo "raw: $plain"; exit 1; }
echo "T2 PASS"
