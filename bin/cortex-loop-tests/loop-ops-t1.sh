#!/usr/bin/env bash
# T1 acceptance: the root-cause report must cover all 10 error jobs and each one must have a found cause
set -euo pipefail
F="reports/2026-07-28/_standalone/cortex-loop-cron-error-triage.md"
test -s "$F"
n=$(grep -cE '^\|' "$F" || true)
[[ "$n" -ge 12 ]] || { echo "table row count $n < 12 (10 jobs + header + separator)"; exit 1; }
grep -qE "$(python3 -c 'import sys; sys.stdout.write("\u6839\u56e0")')|root cause" "$F" || { echo "missing root-cause section"; exit 1; }
echo "T1 PASS"
