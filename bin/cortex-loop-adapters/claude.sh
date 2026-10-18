#!/usr/bin/env bash
# cortex-loop adapter: claude — headless Claude CLI execution in an isolated worktree
# Contract: $1=prompt file, $2=result file; --check-ready is read-only.
set -uo pipefail

MACHINE_BLOCKER_RC=75
DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
OB1_ROOT="$(cd "$DIR/../.." && pwd)"
PROMPT="${1:-}"
RESULT="${2:-}"
WORKDIR=""
NODE24_BIN=""
PNPM_BIN=""
CLAUDE_BIN=""
NODE_VERSION=""
PNPM_VERSION=""
CLAUDE_VERSION=""
INSTANCE_ID=""
AUTH_SOURCE="unknown"

write_blocker() {
  local reason="$1"
  local message="MACHINE_BLOCKER reason=${reason}"
  if [[ -n "${RESULT:-}" ]]; then
    mkdir -p "$(dirname "$RESULT")" 2>/dev/null || true
    printf '[adapter] claude rc=%s\n%s\n' "$MACHINE_BLOCKER_RC" "$message" >"$RESULT" 2>/dev/null || true
  fi
  printf '%s\n' "$message" >&2
}

blocker() {
  write_blocker "$1"
  exit "$MACHINE_BLOCKER_RC"
}

resolve_node24() {
  local candidate=""
  local nvm_dir="${NVM_DIR:-$HOME/.nvm}"
  local preferred="$nvm_dir/versions/node/v24.19.0/bin/node"
  local path_node=""
  local path_version=""

  if [[ -n "${CORTEX_NODE24_BIN:-}" ]]; then
    candidate="$CORTEX_NODE24_BIN"
  elif [[ -n "${CORTEX_NODE24_PREFIX:-}" ]]; then
    candidate="${CORTEX_NODE24_PREFIX%/}/bin/node"
  elif [[ -x "$preferred" ]]; then
    candidate="$preferred"
  else
    for candidate in "$nvm_dir"/versions/node/v24.*/bin/node; do
      [[ -x "$candidate" ]] && break
      candidate=""
    done
  fi

  if [[ -z "$candidate" || ! -x "$candidate" ]]; then
    path_node="$(command -v node 2>/dev/null || true)"
    if [[ -n "$path_node" && -x "$path_node" ]]; then
      path_version="$($path_node --version 2>/dev/null || true)"
      [[ "$path_version" == v22.* ]] && blocker node22-forbidden
      candidate="$path_node"
    fi
  fi

  [[ -n "$candidate" && -x "$candidate" ]] || blocker node24-runtime-unavailable

  NODE24_BIN="$candidate"
  NODE_VERSION="$($NODE24_BIN --version 2>/dev/null || true)"
  [[ "$NODE_VERSION" == v24.* ]] || {
    [[ "$NODE_VERSION" == v22.* ]] && blocker node22-forbidden
    blocker "node-version-not-24:${NODE_VERSION:-unknown}"
  }

  # Put the verified runtime first so #!/usr/bin/env node shims cannot silently
  # execute under Node22/Node26. The original PATH is retained only after it.
  export PATH="$(dirname "$NODE24_BIN"):$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:${PATH:-}"
}

resolve_pnpm() {
  if [[ -n "${CORTEX_PNPM_BIN:-}" ]]; then
    PNPM_BIN="$CORTEX_PNPM_BIN"
  else
    PNPM_BIN="$(command -v pnpm 2>/dev/null || true)"
  fi
  [[ -n "$PNPM_BIN" && -x "$PNPM_BIN" ]] || blocker pnpm11.7-unavailable

  PNPM_VERSION="$($PNPM_BIN --version 2>/dev/null || true)"
  [[ "$PNPM_VERSION" =~ ^11\.7\.[0-9]+$ ]] || {
    blocker "pnpm-version-not-11.7:${PNPM_VERSION:-unknown}"
  }
}

resolve_claude() {
  if [[ -n "${CORTEX_CLAUDE_BIN:-}" ]]; then
    CLAUDE_BIN="$CORTEX_CLAUDE_BIN"
  else
    CLAUDE_BIN="$(command -v claude 2>/dev/null || true)"
  fi
  [[ -n "$CLAUDE_BIN" && -x "$CLAUDE_BIN" ]] || blocker claude-cli-unavailable

  CLAUDE_VERSION="$($CLAUDE_BIN --version 2>&1 || true)"
  [[ -n "$CLAUDE_VERSION" ]] || blocker claude-cli-not-invokable
  CLAUDE_VERSION="${CLAUDE_VERSION//$'\n'/ }"
}

keychain_oauth_present() {
  # Do not print Keychain contents. 0 = access or refresh present.
  local raw=""
  command -v security >/dev/null 2>&1 || return 1
  command -v python3 >/dev/null 2>&1 || return 1
  raw="$(security find-generic-password -s "Claude Code-credentials" -w 2>/dev/null || true)"
  [[ -n "$raw" ]] || return 1
  python3 -c '
import json, sys
try:
    data = json.loads(sys.argv[1])
except Exception:
    raise SystemExit(1)
oauth = data.get("claudeAiOauth") or {}
access = (oauth.get("accessToken") or "").strip()
refresh = (oauth.get("refreshToken") or "").strip()
raise SystemExit(0 if (access or refresh) else 1)
' "$raw" 2>/dev/null
}

inject_oauth_if_needed() {
  # Same DNA as work-studio/devops/dotfiles/aionui/bin/claude-aion-wrapper.sh:
  # Keychain OAuth empty after restart → inject ~/.claude/.long-lived-token.
  # Never echo the token. Interactive `claude auth login` is what looks "stuck".
  local token_file="${CLAUDE_AION_TOKEN_FILE:-$HOME/.claude/.long-lived-token}"
  if [[ -n "${CLAUDE_CODE_OAUTH_TOKEN:-}" ]]; then
    AUTH_SOURCE="env"
    return 0
  fi
  if keychain_oauth_present; then
    AUTH_SOURCE="keychain"
    return 0
  fi
  if [[ -f "$token_file" && -s "$token_file" ]]; then
    CLAUDE_CODE_OAUTH_TOKEN="$(tr -d '\n\r' < "$token_file")"
    export CLAUDE_CODE_OAUTH_TOKEN
    AUTH_SOURCE="long-lived"
    return 0
  fi
  AUTH_SOURCE="missing"
  return 1
}

validate_worktree() {
  local root_real=""
  local worktree_real=""
  local git_top=""

  [[ -n "${CORTEX_WORKTREE:-}" ]] || blocker missing-worktree
  [[ -d "$CORTEX_WORKTREE" ]] || blocker invalid-worktree
  worktree_real="$(cd "$CORTEX_WORKTREE" 2>/dev/null && pwd -P)" || blocker invalid-worktree
  root_real="$(cd "$OB1_ROOT" && pwd -P)"
  [[ "$worktree_real" != "$root_real" ]] || blocker root-worktree-forbidden
  git_top="$(git -C "$worktree_real" rev-parse --show-toplevel 2>/dev/null || true)"
  [[ "$git_top" == "$worktree_real" ]] || blocker invalid-worktree
  WORKDIR="$worktree_real"
}

validate_instance_binding() {
  INSTANCE_ID="${CORTEX_INSTANCE_ID:-}"
  [[ "$INSTANCE_ID" =~ ^claude-[12]$ ]] || blocker instance-id-not-registered
  [[ -n "${CORTEX_WORKTREE_ID:-}" ]] || blocker instance-binding-mismatch
  for value in "${CORTEX_SESSION_ID:-}" "${CORTEX_THREAD_ID:-}" \
    "${CORTEX_LEASE_ID:-}" \
    "${CORTEX_RECEIPT_PATH:-}" "${CORTEX_RESULT_PATH:-}" "${CORTEX_MARKER_PATH:-}"; do
    [[ "$value" == *"$INSTANCE_ID"* ]] || blocker instance-binding-mismatch
  done
  [[ "${CORTEX_MODEL:-sonnet}" == sonnet ]] || blocker claude-model-mismatch
}

preflight() {
  resolve_node24
  resolve_pnpm
  resolve_claude
  inject_oauth_if_needed || true
}

if [[ "$PROMPT" == "--check-ready" ]]; then
  preflight
  if [[ -n "${CORTEX_WORKTREE:-}" ]]; then
    validate_worktree
  fi
  printf 'READY executor=claude backend=cli node=%s pnpm=%s claude=%s auth=%s\n' \
    "$NODE_VERSION" "$PNPM_VERSION" "$CLAUDE_VERSION" "$AUTH_SOURCE"
  exit 0
fi

[[ -n "$PROMPT" && -f "$PROMPT" && -r "$PROMPT" ]] || blocker missing-prompt
[[ -n "$RESULT" ]] || blocker missing-result
validate_worktree
preflight
validate_instance_binding
[[ "$AUTH_SOURCE" != "missing" ]] || blocker claude-oauth-empty

cd "$WORKDIR" || blocker worktree-not-enterable
PROMPT_TEXT="$(<"$PROMPT")"
TIMEOUT_BIN="${CORTEX_TIMEOUT_BIN:-$(command -v timeout 2>/dev/null || command -v gtimeout 2>/dev/null || true)}"
[[ -n "$TIMEOUT_BIN" && -x "$TIMEOUT_BIN" ]] || blocker timeout-unavailable

MODEL="${CORTEX_MODEL:-sonnet}"
CLI_ARGS=(-p "$PROMPT_TEXT" --model "$MODEL" --permission-mode acceptEdits)
if [[ -n "${CORTEX_CLAUDE_ALLOWED_TOOLS:-}" ]]; then
  read -r -a ALLOWED_TOOLS <<<"$CORTEX_CLAUDE_ALLOWED_TOOLS"
  CLI_ARGS+=(--allowedTools "${ALLOWED_TOOLS[@]}")
fi

mkdir -p "$(dirname "$RESULT")" 2>/dev/null || blocker result-parent-unavailable
CLI_OUTPUT="$(mktemp -t cortex-claude-result.XXXXXX)" || blocker temp-output-unavailable
trap 'rm -f "$CLI_OUTPUT"' EXIT

set +e
"$TIMEOUT_BIN" "${CORTEX_CLAUDE_TIMEOUT_SECONDS:-1500}" "$CLAUDE_BIN" "${CLI_ARGS[@]}" >"$CLI_OUTPUT" 2>&1
RC=$?
set -e

{
  printf '[adapter] executor=claude rc=%s\n' "$RC"
  printf 'executor=claude\ntool_layer=claude-cli\nbackend=cli\nmodel=%s\ninstance_id=%s\nsession_id=%s\nworktree_id=%s\nlease_id=%s\nexecution_path=claude-cli\nworktree=%s\nnode=%s\npnpm=%s\nclaude=%s\nreceipt_path=%s\nresult_path=%s\nmarker_path=%s\n' \
    "$MODEL" "$INSTANCE_ID" "${CORTEX_SESSION_ID}" "${CORTEX_WORKTREE_ID}" "${CORTEX_LEASE_ID}" \
    "$WORKDIR" "$NODE_VERSION" "$PNPM_VERSION" "$CLAUDE_VERSION" \
    "${CORTEX_RECEIPT_PATH}" "${CORTEX_RESULT_PATH}" "${CORTEX_MARKER_PATH}"
  printf '%s\n' "$(<"$CLI_OUTPUT")"
  if [[ $RC -ne 0 ]]; then
    printf '[adapter] claude exited rc=%s (124=timeout)\n' "$RC"
  fi
} >"$RESULT"
exit "$RC"
