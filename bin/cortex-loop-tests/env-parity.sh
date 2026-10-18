#!/usr/bin/env bash
# env-parity -- mechanical gate for cross-environment consistency (ERRORS E012 hardened executor), runtime-agnostic
#
# Why it exists: on 2026-07-29 one root cause bit three times, all "the interactive shell can run it,
# the unattended environment cannot", because the scheduler does not inherit the login shell's environment:
#   (1) ollama pull stalled at 79%    -> missing HTTPS_PROXY
#   (2) worker systemd failed entirely -> missing ANTHROPIC_*
#   (3) Mac launchd returned 403 seven times -> missing HTTP(S)_PROXY
# The first hit only patched the proxy into that one command and did not spread it to the scheduler config, so the same bug bit twice more in another costume.
#
# Runtime-agnostic design (required 2026-07-29):
#   This gate **hard-codes no runtime name** (it does not freeze claude/ANTHROPIC_*), it:
#     1. Scans `# cortex-loop:requires-env A B C` self-declarations in bin/cortex-loop-adapters/*.sh
#     2. The union is every variable this node needs to run unattended
#     3. Compare that with this machine's real scheduler config (launchd plist / systemd unit, detected by what exists)
#   Adding any new runtime (Codex/Gemini/in-house) only needs one self-declaration line at the top of its adapter.
#   **This file does not need a single character changed**.
#   Compare only whether the variable name is declared. Never read or print a value (secret safety).
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ADAPTERS="$ROOT/bin/cortex-loop-adapters"
FAIL=0

# -- 1. Collect requirements from adapter self-declarations (the runtime-agnostic source of truth) --
declare -a NEEDED=()
for f in "$ADAPTERS"/*.sh; do
  [[ -f "$f" ]] || continue
  line=$(grep -m1 '^# cortex-loop:requires-env' "$f" 2>/dev/null) || continue
  for v in ${line#\# cortex-loop:requires-env }; do
    [[ " ${NEEDED[*]:-} " == *" $v "* ]] || NEEDED+=("$v")
  done
done

if [[ ${#NEEDED[@]} -eq 0 ]]; then
  echo "SKIP  no adapter declares requires-env -- nothing to check"
  echo "      when adding a runtime, put this at the top of the adapter: # cortex-loop:requires-env VAR1 VAR2"
  exit 0
fi
echo "required union (from adapter self-declarations, not hard-coded): ${NEEDED[*]}"
echo

# -- 2. Detect this machine's scheduler and compare its config --
if [[ -n "${CORTEX_LAUNCHD_PLIST:-}" ]]; then
  PLIST="$CORTEX_LAUNCHD_PLIST"
elif [[ -f "$ROOT/work-studio/devops/dotfiles/launchd/com.cortex.loop.plist" ]]; then
  PLIST="$ROOT/work-studio/devops/dotfiles/launchd/com.cortex.loop.plist"
else
  PLIST="$ROOT/examples/launchd/com.cortex.loop.plist"
fi
if [[ -n "${CORTEX_SYSTEMD_UNIT:-}" ]]; then
  UNIT="$CORTEX_SYSTEMD_UNIT"
elif [[ -f "$ROOT/work-studio/devops/dotfiles/systemd/cortex-loop.service" ]]; then
  UNIT="$ROOT/work-studio/devops/dotfiles/systemd/cortex-loop.service"
else
  UNIT="$ROOT/examples/systemd/cortex-loop.service"
fi
CHECKED=0

if [[ -f "$PLIST" ]] && command -v launchctl >/dev/null 2>&1; then
  CHECKED=1
  echo "[launchd] $PLIST"
  for var in "${NEEDED[@]}"; do
    if grep -q "<key>${var}</key>" "$PLIST"; then
      echo "  PASS  declared $var"
    else
      echo "  FAIL  missing $var -- an unattended call will fail (same shape as E012)"
      FAIL=$((FAIL+1))
    fi
  done
fi

if [[ -f "$UNIT" ]]; then
  CHECKED=1
  echo "[systemd] $UNIT"
  # systemd may legally inject env two ways: an explicit Environment= or by sourcing an external script
  if grep -qE '^\s*(ExecStart|ExecStartPre)=.*(source|\.)\s+\S+\.sh' "$UNIT"; then
    echo "  PASS  environment is injected by sourcing an external script (the variables have a source, and are not hard-coded in this file)"
  else
    for var in "${NEEDED[@]}"; do
      if grep -qE "^Environment=${var}=" "$UNIT"; then
        echo "  PASS  declared $var"
      else
        echo "  FAIL  missing $var and no environment script is sourced (same shape as E012)"
        FAIL=$((FAIL+1))
      fi
    done
  fi
fi

[[ $CHECKED -eq 0 ]] && { echo "SKIP  no scheduler config on this machine that can be checked"; exit 0; }

echo
if [[ $FAIL -eq 0 ]]; then
  echo "env-parity PASS -- scheduler environment declarations cover every adapter requirement"
  exit 0
fi
echo "env-parity FAIL=$FAIL -- see skills/cortex-loop/ERRORS.md E012 for the fix"
exit 1
