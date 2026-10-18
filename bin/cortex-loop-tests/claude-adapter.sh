#!/usr/bin/env bash
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$DIR/../.." && pwd)"
ADAPTER="$ROOT/bin/cortex-loop-adapters/claude.sh"
FIXTURE_CLI="$DIR/fixtures/claude-cli-fixture.sh"
FIXTURE_VERIFIER="$DIR/fixtures/claude-marker-verifier.mjs"

die() {
  printf 'FAIL: %s\n' "$1" >&2
  exit 1
}

find_node24() {
  if [[ -n "${CORTEX_NODE24_BIN:-}" && -x "$CORTEX_NODE24_BIN" ]]; then
    printf '%s\n' "$CORTEX_NODE24_BIN"
    return
  fi
  local nvm_dir="${NVM_DIR:-$HOME/.nvm}"
  for node in "$nvm_dir"/versions/node/v24.*/bin/node; do
    [[ -x "$node" ]] && { printf '%s\n' "$node"; return; }
  done
  die "Node24 is required for this focused test"
}

NODE24_BIN="$(find_node24)"
PNPM_BIN="${CORTEX_PNPM_BIN:-${NODE24_BIN%/node}/pnpm}"
[[ -x "$PNPM_BIN" ]] || die "pnpm binary missing beside Node24: $PNPM_BIN"
[[ "$($NODE24_BIN --version)" == v24.* ]] || die "test selected a non-Node24 runtime"
[[ "$($PNPM_BIN --version)" =~ ^11\.7(\.[0-9]+)?$ ]] || die "test selected a non-pnpm11.7 runtime"

new_git_worktree() {
  local base="$1"
  local worktree="$2"
  mkdir -p "$base"
  git -C "$base" init -q
  git -C "$base" config user.email cortex-test@example.invalid
  git -C "$base" config user.name cortex-test
  printf 'fixture\n' >"$base/seed.txt"
  git -C "$base" add seed.txt
  git -C "$base" commit -q -m fixture
  git -C "$base" worktree add --detach -q "$worktree" HEAD
}

run_adapter() {
  env CORTEX_NODE24_BIN="$NODE24_BIN" CORTEX_PNPM_BIN="$PNPM_BIN" "$@"
}

run_contract_tests() {
  local tmp="$(mktemp -d -t cortex-claude-adapter-test.XXXXXX)"
  local base="$tmp/repo"
  local worktree="$tmp/worktree"
  local prompt="$tmp/prompt.txt"
  local result="$tmp/result.txt"
  local output="$tmp/output.txt"
  local node22="$tmp/node22"
  local missing_cli="$tmp/missing-claude"
  local instance_id="claude-1"
  local session_id="session-claude-1"
  local thread_id="thread-claude-1"
  local worktree_id="wt-claude-1-fixture"
  local lease_id="lease-claude-1"
  local receipt_path="$tmp/receipt-claude-1.json"
  local result_path="$tmp/result-claude-1.txt"
  local marker_path="$worktree/.marker-claude-1"
  local rc

  new_git_worktree "$base" "$worktree"
  printf 'write the marker\n' >"$prompt"

  set +e
  run_adapter env -u CORTEX_WORKTREE "$ADAPTER" "$prompt" "$result" >"$output" 2>&1
  rc=$?
  set -e
  [[ $rc -eq 75 ]] || die "missing worktree rc=$rc"
  rg -q 'MACHINE_BLOCKER reason=missing-worktree' "$output" || die "missing worktree blocker absent"

  printf '#!/usr/bin/env bash\nprintf "v22.22.0\\n"\n' >"$node22"
  chmod +x "$node22"
  set +e
  CORTEX_NODE24_BIN="$node22" CORTEX_PNPM_BIN="$PNPM_BIN" "$ADAPTER" --check-ready >"$output" 2>&1
  rc=$?
  set -e
  [[ $rc -eq 75 ]] || die "Node22 rc=$rc"
  rg -q 'MACHINE_BLOCKER reason=node22-forbidden' "$output" || die "Node22 blocker absent"

  set +e
  run_adapter env CORTEX_WORKTREE="$worktree" CORTEX_CLAUDE_BIN="$missing_cli" \
    CORTEX_INSTANCE_ID="$instance_id" CORTEX_SESSION_ID="$session_id" CORTEX_THREAD_ID="$thread_id" \
    CORTEX_WORKTREE_ID="$worktree_id" CORTEX_LEASE_ID="$lease_id" CORTEX_RECEIPT_PATH="$receipt_path" \
    CORTEX_RESULT_PATH="$result_path" CORTEX_MARKER_PATH="$marker_path" \
    "$ADAPTER" "$prompt" "$result" >"$output" 2>&1
  rc=$?
  set -e
  [[ $rc -eq 75 ]] || die "missing CLI rc=$rc"
  rg -q 'MACHINE_BLOCKER reason=claude-cli-unavailable' "$output" || die "missing CLI blocker absent"

  run_adapter env CORTEX_WORKTREE="$worktree" CORTEX_CLAUDE_BIN="$FIXTURE_CLI" \
    CORTEX_INSTANCE_ID="$instance_id" CORTEX_SESSION_ID="$session_id" CORTEX_THREAD_ID="$thread_id" \
    CORTEX_WORKTREE_ID="$worktree_id" CORTEX_LEASE_ID="$lease_id" CORTEX_RECEIPT_PATH="$receipt_path" \
    CORTEX_RESULT_PATH="$result_path" CORTEX_MARKER_PATH="$marker_path" \
    "$ADAPTER" "$prompt" "$result"
  [[ "$(<"$worktree/fixture-claude-marker.txt")" == 'fixture-claude-wrote-marker' ]] || die "fixture CLI did not change worktree state"
  rg -q '^tool_layer=claude-cli$' "$result" || die "result did not identify Claude CLI"
  rg -q '^node=v24\.' "$result" || die "result did not record Node24"
  rg -q '^pnpm=11\.7' "$result" || die "result did not record pnpm11.7"
  rg -q '^instance_id=claude-1$' "$result" || die "result did not record instance_id"
  rg -q '^execution_path=claude-cli$' "$result" || die "result did not record execution_path"

  run_adapter env CORTEX_WORKTREE="$worktree" CORTEX_CLAUDE_BIN="$FIXTURE_CLI" \
    "$ADAPTER" --check-ready >"$output"
  rg -q '^READY executor=claude backend=cli node=v24\.[^ ]+ pnpm=11\.7' "$output" || die "check-ready output invalid"
  printf 'contract_tests=PASS\nworktree=%s\n' "$worktree"
}

write_receipt() {
  local receipt="$1"
  local status="$2"
  local smoke_rc="$3"
  local worktree="$4"
  local marker="$5"
  local verifier_output="$6"
  local claude_result="$7"
  local marker_sha="$8"
  local claude_version="$9"
  local result_text="${10}"
  mkdir -p "$(dirname "$receipt")"
  RECEIPT="$receipt" STATUS="$status" SMOKE_RC="$smoke_rc" WORKTREE="$worktree" \
    MARKER="$marker" VERIFIER_OUTPUT="$verifier_output" CLAUDE_RESULT="$claude_result" \
    MARKER_SHA="$marker_sha" NODE24_BIN="$NODE24_BIN" NODE_VERSION="$($NODE24_BIN --version)" \
    PNPM_VERSION="$($PNPM_BIN --version)" CLAUDE_VERSION="$claude_version" \
    ADAPTER="$ADAPTER" TEST_SCRIPT="$DIR/claude-adapter.sh" RESULT_TEXT="$result_text" \
    "$NODE24_BIN" - <<'NODE'
import { writeFileSync } from "node:fs";
const record = {
  schema: "cortex.claude-cli-smoke/v1",
  status: process.env.STATUS,
  smoke_rc: Number(process.env.SMOKE_RC),
  executor: "claude-cli",
  execution_path: "claude-cli",
  backend: "cli",
  adapter: process.env.ADAPTER,
  worktree: process.env.WORKTREE,
  worktree_isolated: true,
  marker: process.env.MARKER,
  marker_sha256: process.env.MARKER_SHA || null,
  verifier_command: `cd ${process.env.WORKTREE} && ${process.env.NODE24_BIN} smoke/verify-marker.mjs`,
  verifier_output: process.env.VERIFIER_OUTPUT,
  adapter_result: process.env.CLAUDE_RESULT,
  adapter_result_text: process.env.RESULT_TEXT,
  node: process.env.NODE_VERSION,
  pnpm: process.env.PNPM_VERSION,
  claude_cli: process.env.CLAUDE_VERSION,
  acp: {
    status: "MACHINE_BLOCKER",
    reason: "No Claude ACP backend is registered; this receipt is CLI-only and does not claim ACP."
  },
  rerun: `bash ${process.env.TEST_SCRIPT} --real-smoke --receipt ${process.env.RECEIPT}`
};
writeFileSync(process.env.RECEIPT, JSON.stringify(record, null, 2) + "\n");
NODE
}

run_real_smoke() {
  local receipt="${1:-/tmp/cortex-claude-cli-smoke-receipt.json}"
  local tmp="$(mktemp -d -t cortex-claude-cli-smoke.XXXXXX)"
  local base="$tmp/repo"
  local worktree="$tmp/worktree"
  local prompt="$tmp/prompt.txt"
  local result="$tmp/adapter-result.txt"
  local marker="$worktree/claude-native-smoke-marker.txt"
  local verifier_output=""
  local marker_sha=""
  local claude_version="$(claude --version 2>&1 | tr '\n' ' ')"
  local smoke_rc=0
  local status=PASS
  local verifier_rc=1

  new_git_worktree "$base" "$worktree"
  mkdir -p "$worktree/smoke"
  cp "$FIXTURE_VERIFIER" "$worktree/smoke/verify-marker.mjs"
  printf '%s\n' \
    'Use your file and shell tools; do not merely describe the work.' \
    'In this isolated worktree, create exactly claude-native-smoke-marker.txt with exactly one line: claude-cli-native-smoke-v1' \
    'Then run exactly: node smoke/verify-marker.mjs' \
    'Do not modify any other file. Report the verifier output after it succeeds.' >"$prompt"

  set +e
  env CORTEX_NODE24_BIN="$NODE24_BIN" CORTEX_PNPM_BIN="$PNPM_BIN" \
    CORTEX_WORKTREE="$worktree" CORTEX_CLAUDE_BIN="$(command -v claude)" \
    CORTEX_CLAUDE_ALLOWED_TOOLS='Bash(*) Read Write Edit' CORTEX_CLAUDE_TIMEOUT_SECONDS=300 \
    "$ADAPTER" "$prompt" "$result"
  smoke_rc=$?
  set -e

  if [[ -f "$marker" ]]; then
    marker_sha="$(shasum -a 256 "$marker" | awk '{print $1}')"
    set +e
    verifier_output="$(cd "$worktree" && "$NODE24_BIN" smoke/verify-marker.mjs 2>&1)"
    verifier_rc=$?
    set -e
  fi
  [[ $verifier_rc -eq 0 ]] || status=MACHINE_BLOCKER
  [[ $smoke_rc -eq 0 ]] || status=MACHINE_BLOCKER
  local result_text="$(<"$result")"
  write_receipt "$receipt" "$status" "$smoke_rc" "$worktree" "$marker" \
    "$verifier_output" "$result" "$marker_sha" "$claude_version" "$result_text"
  printf 'real_smoke_status=%s\nreceipt=%s\nworktree=%s\n' "$status" "$receipt" "$worktree"
  if [[ "$status" != PASS ]]; then
    printf 'MACHINE_BLOCKER reason=claude-cli-smoke-failed\n' >&2
    return 75
  fi
}

if [[ "${1:-}" == "--real-smoke" ]]; then
  if [[ "${2:-}" == "--receipt" ]]; then
    run_real_smoke "${3:-/tmp/cortex-claude-cli-smoke-receipt.json}"
  else
    run_real_smoke "${2:-/tmp/cortex-claude-cli-smoke-receipt.json}"
  fi
else
  run_contract_tests
fi
