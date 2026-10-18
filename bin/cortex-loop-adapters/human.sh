#!/usr/bin/env bash
# cortex-loop adapter: human — safe default (spends no tokens, causes no side effects)
# Contract: $1=prompt file  $2=result file; exit code 0=delivered to the executor
set -euo pipefail
PROMPT="$1"; RESULT="$2"
INBOX="/tmp/spotlight/cortex-loop-human-inbox.md"

{
  echo "## $(date '+%Y-%m-%d %H:%M') awaiting human execution"
  echo
  cat "$PROMPT"
  echo
  echo "---"
} >> "$INBOX"

cat > "$RESULT" <<EOF
executor=human
This round did not run automatically: this line's executor=human in CLOCK.md (safe default).
Prompt delivered to ${INBOX}; waiting for a human to run it.
To automate, change this line's executor to claude / codex / openclaw.
EOF
echo "human adapter: delivered $INBOX"
