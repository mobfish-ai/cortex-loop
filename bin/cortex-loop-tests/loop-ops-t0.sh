#!/usr/bin/env bash
# T0 acceptance: the clock is really installed -- the declaration (CLOCK.md) and launchctl must agree
set -euo pipefail
bin/cortex-loop reconcile | grep -q 'DRIFT: 0' || { echo "DRIFT remains"; exit 1; }
launchctl print "gui/$(id -u)/${CORTEX_LAUNCHD_LABEL:-com.cortex.loop}" >/dev/null 2>&1 \
  || { echo "launchd is not loaded"; exit 1; }
echo "T0 PASS"
