#!/usr/bin/env bash
# T0 验收：时钟真装上了 —— 声明(CLOCK.md) 与 实际(launchctl) 必须对上
set -euo pipefail
bin/cortex-loop reconcile | grep -q 'DRIFT: 0' || { echo "仍有 DRIFT"; exit 1; }
launchctl print "gui/$(id -u)/${CORTEX_LAUNCHD_LABEL:-com.cortex.loop}" >/dev/null 2>&1 \
  || { echo "launchd 未装载"; exit 1; }
echo "T0 PASS"
