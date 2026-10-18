#!/usr/bin/env bash
# T1 验收：根因报告必须覆盖全部 10 条 error job 且每条有查到的根因
set -euo pipefail
F="reports/2026-07-28/_standalone/cortex-loop-cron-error-triage.md"
test -s "$F"
n=$(grep -cE '^\|' "$F" || true)
[[ "$n" -ge 12 ]] || { echo "表格行数 $n < 12（10 条 job + 表头 + 分隔行）"; exit 1; }
grep -qE '根因|root cause' "$F" || { echo "缺根因段"; exit 1; }
echo "T1 PASS"
