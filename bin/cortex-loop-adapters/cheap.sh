#!/usr/bin/env bash
# cortex-loop:requires-env PATH
# cortex-loop adapter: cheap — GLM-backed coding agent (can really read, write, and execute)
# Contract: $1=prompt file  $2=result file
#
# Boundary: raw minimax.sh/glm.sh can only generate text; they cannot Read/Edit/Bash.
# Wiring them into auto-advance makes the ledger record a suggestion as if it were execution.
# This adapter therefore uses only the Claude Code CLI tool layer, but this adapter
# injects provider/model in the child env (ANTHROPIC_BASE_URL/AUTH_TOKEN/MODEL) and rotates
# matching accounts read from CC Switch SQLite (~/.cc-switch/cc-switch.db) (currently "Zhipu GLM",
# endpoint open.bigmodel.cn/api/anthropic, Coding Plan billing) --
# **no longer depends** on someone clicking Enable on ~/.claude/settings.json in the GUI.
#
# 2026-07-31 root cause: the old path worked only after a human toggled CC Switch GUI,
# and an unattended heartbeat has nobody to click it. settings.json pointed at Claude Official while the adapter
# sent a model name that endpoint does not know, so FAIL rc=1 was certain -- 0 adapter PASS all night.
# If the tool layer is unavailable, fail hard. Never fall back to a raw completion that can talk but not act.
#
# 2026-10-05 operator decision: all 4 MiniMax accounts are dead (API 400 [1211] "model does not exist",
# accounts stopped). The cheap chain moves entirely to "Zhipu GLM" glm-5.3-flash. The 2026-07-30
# "MiniMax before GLM" decision below is void. The old MiniMax accounts stay in CC Switch for reference.
#
# 2026-07-30 operator decision (void, see above): MiniMax before GLM (4 accounts had more quota).
# To make this adapter the real default cortex-loop executor, set
# `export CORTEX_DEFAULT_EXECUTOR=cheap` (read by cmd_run(), higher priority than node profile
# auto-discovery) -- node_profile()'s discovery table is outside this line and was not changed; see task report section G1.
set -uo pipefail
export PATH="$HOME/.local/bin:$HOME/.nvm/versions/node/v22.22.0/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
# shellcheck source=_openai_compat_lib.sh
source "$DIR/_openai_compat_lib.sh"
PROMPT="${1:-}"; RESULT="${2:-}"
OB1_ROOT="$(cd "$DIR/../.." && pwd)"
WORKDIR="${CORTEX_WORKTREE:-$OB1_ROOT}"
if [[ "${CORTEX_REQUIRE_WORKTREE:-0}" == "1" && -z "${CORTEX_WORKTREE:-}" ]]; then
  printf '[adapter] executor=cheap rc=2 reason=missing-CORTEX_WORKTREE\n' > "$RESULT"
  exit 2
fi
[[ -d "$WORKDIR" ]] || { printf '[adapter] executor=cheap rc=2 reason=invalid-worktree\n' > "$RESULT"; exit 2; }
if [[ "${CORTEX_REQUIRE_WORKTREE:-0}" == "1" && "$(cd "$WORKDIR" && pwd -P)" == "$(cd "$OB1_ROOT" && pwd -P)" ]]; then
  printf '[adapter] executor=cheap rc=2 reason=root-worktree-forbidden\n' > "$RESULT"
  exit 2
fi
FORCE_MODEL="${CORTEX_CHEAP_MODEL:-}"
CCSWITCH_STATE="${OC_CCSWITCH_STATE_FILE:-$HOME/.openclaw/state/cortex-loop-cheap-ccswitch-key-state.json}"
mkdir -p "$(dirname "$CCSWITCH_STATE")"
CCSWITCH_COOLDOWN="${CORTEX_CHEAP_COOLDOWN_SEC:-180}"
LOCK_ROOT="/tmp/spotlight/cortex-cheap-workers"
ACCOUNT_LOCK_ROOT="/tmp/spotlight/cortex-cheap-accounts"
WORKER_SLOTS="${CORTEX_CHEAP_WORKER_SLOTS:-3}"
LOCK_DIR=""
LOCK_PID=""
ACCOUNT_LOCK_DIR=""

if ! command -v claude >/dev/null 2>&1; then
  if [[ "${1:-}" == "--check-ready" ]]; then
    printf 'claude-code-cli-missing\n' >&2
    exit 127
  fi
  printf '[adapter] executor=cheap rc=127 reason=claude-code-cli-missing\n' > "$RESULT"
  exit 127
fi

ORDERED="$(oc_ordered_ccswitch_accounts "${CORTEX_CHEAP_ACCOUNT_PATTERN:-Zhipu GLM%}" "$CCSWITCH_STATE" "$CCSWITCH_COOLDOWN")"
if [[ -z "$ORDERED" ]]; then
  if [[ "${1:-}" == "--check-ready" ]]; then
    printf 'no-ccswitch-glm-account\n' >&2
    exit 89
  fi
  printf '[adapter] executor=cheap rc=89 reason=no-ccswitch-account hint: no GLM account in ~/.cc-switch/cc-switch.db (pattern=Zhipu GLM%%)\n' > "$RESULT"
  exit 89
fi
if [[ "${1:-}" == "--check-ready" ]]; then
  printf 'ready: claude-code + ccswitch-glm\n'
  exit 0
fi

cd "$WORKDIR" || exit 1
mkdir -p "$LOCK_ROOT" "$ACCOUNT_LOCK_ROOT"
for ((slot=0; slot<WORKER_SLOTS; slot++)); do
  candidate="$LOCK_ROOT/slot-$slot"
  if mkdir "$candidate" 2>/dev/null; then
    LOCK_DIR="$candidate"; LOCK_PID="$candidate/pid"; break
  fi
  owner="$(cat "$candidate/pid" 2>/dev/null || true)"
  if [[ "$owner" =~ ^[0-9]+$ ]] && ! kill -0 "$owner" 2>/dev/null; then
    stale="$candidate.stale.$(date +%s).$$"
    if mv "$candidate" "$stale" 2>/dev/null && mkdir "$candidate" 2>/dev/null; then
      rm -f "$stale/pid"
      rmdir "$stale" 2>/dev/null || true
      LOCK_DIR="$candidate"; LOCK_PID="$candidate/pid"; break
    fi
  fi
done
if [[ -z "$LOCK_DIR" ]]; then
  printf '[adapter] executor=cheap rc=75 reason=worker-slots-full slots=%s\n' "$WORKER_SLOTS" > "$RESULT"
  exit 75
fi
printf '%s\n' "$$" > "$LOCK_PID"
cleanup() {
  release_account_lock
  [[ -n "$LOCK_DIR" ]] || return 0
  current="$(cat "$LOCK_PID" 2>/dev/null || true)"
  if [[ "$current" == "$$" ]]; then
    rm -f "$LOCK_PID"
    rmdir "$LOCK_DIR" 2>/dev/null || true
  fi
}
release_account_lock() {
  [[ -n "$ACCOUNT_LOCK_DIR" ]] || return 0
  current="$(cat "$ACCOUNT_LOCK_DIR/pid" 2>/dev/null || true)"
  if [[ "$current" == "$$" ]]; then
    rm -f "$ACCOUNT_LOCK_DIR/pid"
    rmdir "$ACCOUNT_LOCK_DIR" 2>/dev/null || true
  fi
  ACCOUNT_LOCK_DIR=""
}
acquire_account_lock() {
  local hash="$1" candidate owner stale
  candidate="$ACCOUNT_LOCK_ROOT/$hash"
  if mkdir "$candidate" 2>/dev/null; then
    printf '%s\n' "$$" > "$candidate/pid"
    ACCOUNT_LOCK_DIR="$candidate"
    return 0
  fi
  owner="$(cat "$candidate/pid" 2>/dev/null || true)"
  if [[ "$owner" =~ ^[0-9]+$ ]] && ! kill -0 "$owner" 2>/dev/null; then
    stale="$candidate.stale.$(date +%s).$$"
    if mv "$candidate" "$stale" 2>/dev/null && mkdir "$candidate" 2>/dev/null; then
      rm -f "$stale/pid"
      rmdir "$stale" 2>/dev/null || true
      printf '%s\n' "$$" > "$candidate/pid"
      ACCOUNT_LOCK_DIR="$candidate"
      return 0
    fi
  fi
  return 1
}
terminate_worker() {
  [[ -n "${worker_pid:-}" ]] && kill -TERM "$worker_pid" 2>/dev/null || true
  wait "${worker_pid:-}" 2>/dev/null || true
  cleanup
  exit 143
}
trap cleanup EXIT
trap terminate_worker INT TERM

# ── usage must be written to disk (IMM-T45) ─────────────────────────────
# run-report scans result for "input_tokens"/"output_tokens" numbers; a missing field is UNKNOWN energy,
# not a silent 0. Every write to RESULT must include one [usage] JSON line (known or UNKNOWN; three states do not collapse).
cheap_write_result_with_usage() {
  # $1=raw attempt file  $2=final RESULT  $3=extra footer lines (optional, via stdin not used)
  local raw="$1" dest="$2"
  python3 - "$raw" "$dest" <<'PY'
import json, re, sys
from pathlib import Path
raw_path, dest_path = Path(sys.argv[1]), Path(sys.argv[2])
raw = raw_path.read_text(encoding="utf-8", errors="replace")
text = raw
usage = None
source = "absent"
reason = "no-json-usage"
# 1) whole-file JSON (--output-format json)
try:
    data = json.loads(raw)
    if isinstance(data, dict):
        if "result" in data and data["result"] is not None:
            text = data["result"] if isinstance(data["result"], str) else json.dumps(
                data["result"], ensure_ascii=False)
        u = data.get("usage")
        if isinstance(u, dict):
            usage = u
            source = "claude-json"
            reason = "ok"
except json.JSONDecodeError:
    # 2) a JSON object at the tail or inline that contains usage
    for m in re.finditer(r"\{[^{}]*\"usage\"\s*:\s*\{[^{}]+\}[^{}]*\}", raw, re.S):
        try:
            data = json.loads(m.group(0))
            u = data.get("usage")
            if isinstance(u, dict):
                usage = u
                source = "embedded-json"
                reason = "ok"
                break
        except json.JSONDecodeError:
            continue
    # 3) a bare "input_tokens": N
    if usage is None:
        mi = re.search(r'"input_tokens"\s*:\s*(\d+)', raw)
        mo = re.search(r'"output_tokens"\s*:\s*(\d+)', raw)
        if mi or mo:
            usage = {
                "input_tokens": int(mi.group(1)) if mi else None,
                "output_tokens": int(mo.group(1)) if mo else None,
            }
            source = "regex"
            reason = "partial" if not (mi and mo) else "ok"

def tok(u, *keys):
    if not isinstance(u, dict):
        return None
    for k in keys:
        v = u.get(k)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return int(v)
    return None

inp = tok(usage, "input_tokens", "prompt_tokens")
out = tok(usage, "output_tokens", "completion_tokens")
if inp is None and out is None:
    payload = {
        "input_tokens": "UNKNOWN",
        "output_tokens": "UNKNOWN",
        "status": "UNKNOWN",
        "source": source,
        "reason": reason,
    }
else:
    payload = {
        "input_tokens": inp if inp is not None else "UNKNOWN",
        "output_tokens": out if out is not None else "UNKNOWN",
        "status": "known" if (inp is not None and out is not None) else "partial",
        "source": source,
        "reason": reason,
    }
# Also write numeric keys as plain numbers so the old run-report regex hits (do not write numeric keys when UNKNOWN)
if isinstance(payload["input_tokens"], int):
    payload["prompt_tokens"] = payload["input_tokens"]
if isinstance(payload["output_tokens"], int):
    payload["completion_tokens"] = payload["output_tokens"]

body = text.rstrip() + "\n"
dest_path.write_text(body, encoding="utf-8")
with dest_path.open("a", encoding="utf-8") as fh:
    fh.write("\n[usage] " + json.dumps(payload, ensure_ascii=False) + "\n")
print(payload.get("status", "UNKNOWN"))
PY
}

attempts=0
success=0
summary=""
ATTEMPT_RESULT="$(mktemp /tmp/oc-cheap-attempt.XXXXXX)"
ATTEMPT_ERR="$(mktemp /tmp/oc-cheap-attempt-err.XXXXXX)"
while IFS=$'\t' read -r label base_url acct_model token hash; do
  [[ -z "$label" ]] && continue
  # One MiniMax account is given to only one Worker at a time. Anonymous concurrency slots only cap total throughput.
  # An account lease stops several Workers from all hitting the first-ranked account and 429 while other accounts sit idle.
  acquire_account_lock "$hash" || continue
  attempts=$((attempts + 1))
  model="${FORCE_MODEL:-$acct_model}"
  # stdout receives JSON alone; stderr must not pollute the parse (IMM-T45)
  ANTHROPIC_BASE_URL="$base_url" ANTHROPIC_AUTH_TOKEN="$token" ANTHROPIC_MODEL="$model" \
  ANTHROPIC_DEFAULT_SONNET_MODEL="$model" ANTHROPIC_DEFAULT_OPUS_MODEL="$model" \
  ANTHROPIC_DEFAULT_HAIKU_MODEL="$model" \
  timeout 1500 claude -p \
    --output-format json \
    --safe-mode \
    --disable-slash-commands \
    --strict-mcp-config \
    --mcp-config '{"mcpServers":{}}' \
    --model "$model" \
    --permission-mode acceptEdits \
    --allowedTools "Read,Edit,Write,Glob,Grep,Bash" \
    --disallowedTools "Bash(git *)" \
    --append-system-prompt "You are an execution worker inside an isolated CORTEX attempt worktree. Never run git add, commit, push, pull, merge, reset, restore, checkout, stash, rebase, cherry-pick, tag, or update-ref. Write only the declared artifact/bounds paths. After you return, cortex-loop will scope-check and commit this attempt index, then the integrator will lease-CAS it into canonical." \
    --no-session-persistence \
    < "$PROMPT" > "$ATTEMPT_RESULT" 2>"$ATTEMPT_ERR" &
  worker_pid=$!
  wait "$worker_pid"
  rc=$?
  if [[ $rc -eq 0 ]]; then
    oc_mark_success "$CCSWITCH_STATE" "$hash"
    # If JSON parse fails, still splice the raw text plus stderr into raw, then force usage
    if ! python3 -c "import json,sys; json.load(open(sys.argv[1]))" "$ATTEMPT_RESULT" 2>/dev/null; then
      { cat "$ATTEMPT_RESULT"; echo; echo "--- stderr ---"; cat "$ATTEMPT_ERR"; } > "${ATTEMPT_RESULT}.merged"
      mv "${ATTEMPT_RESULT}.merged" "$ATTEMPT_RESULT"
    fi
    cheap_write_result_with_usage "$ATTEMPT_RESULT" "$RESULT" >/dev/null
    printf '\n[adapter] executor=cheap provider=glm account=%s tool_layer=claude-code model=%s attempt=%s/? rc=0\n' \
      "$label" "$model" "$attempts" >> "$RESULT"
    # Second check: if [usage] is missing after the adapter line, append it (in case a later write dropped it)
    if ! grep -q '^\[usage\]' "$RESULT" 2>/dev/null; then
      printf '\n[usage] {"input_tokens":"UNKNOWN","output_tokens":"UNKNOWN","status":"UNKNOWN","source":"footer-guard","reason":"missing-after-adapter-line"}\n' >> "$RESULT"
    fi
    success=1
    release_account_lock
    break
  else
    oc_mark_failure "$CCSWITCH_STATE" "$hash" "$label"
    summary="${summary}[${label}:rc=${rc}] "
    { cat "$ATTEMPT_RESULT" 2>/dev/null; echo; echo "--- stderr ---"; cat "$ATTEMPT_ERR" 2>/dev/null; } > "${ATTEMPT_RESULT}.merged"
    cheap_write_result_with_usage "${ATTEMPT_RESULT}.merged" "$RESULT" >/dev/null || cp "${ATTEMPT_RESULT}.merged" "$RESULT"
    rm -f "${ATTEMPT_RESULT}.merged"
    release_account_lock
  fi
done <<< "$ORDERED"
rm -f "$ATTEMPT_RESULT" "$ATTEMPT_ERR"

if [[ $success -eq 1 ]]; then
  exit 0
fi
if [[ $attempts -eq 0 ]]; then
  printf '[adapter] executor=cheap rc=75 reason=all-glm-accounts-busy\n' > "$RESULT"
  printf '[usage] {"input_tokens":"UNKNOWN","output_tokens":"UNKNOWN","status":"UNKNOWN","source":"account-lease","reason":"all-accounts-busy"}\n' >> "$RESULT"
  exit 75
fi

printf '\n[adapter] executor=cheap provider=glm all %s accounts failed: %s\n' \
  "$attempts" "$summary" >> "$RESULT"
printf '[adapter] executor=cheap rc=98\n' >> "$RESULT"
# The failure path also forces usage (UNKNOWN is legal; collapsing to 0 is not)
if ! grep -q '^\[usage\]' "$RESULT" 2>/dev/null; then
  printf '\n[usage] {"input_tokens":"UNKNOWN","output_tokens":"UNKNOWN","status":"UNKNOWN","source":"all-accounts-failed","reason":"rc=98"}\n' >> "$RESULT"
fi
exit 98
