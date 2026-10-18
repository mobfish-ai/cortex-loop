#!/usr/bin/env bash
# Fixed Grok lane: provider=grok, model=grok-4.6.
# ACP is the existing policy facade; it is not provider-native. Dry-run is
# readiness evidence only. The default live path is Grok Build CLI, where
# --model makes the model binding observable.
set -uo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OB1_ROOT="$(cd "$DIR/../.." && pwd)"
CLIENT="${CORTEX_ACP_POLICY_CLIENT:-$OB1_ROOT/bin/acp-policy-client.sh}"
EXECUTOR="acp-native:grok"
PROVIDER="grok"
MODEL="grok-4.6"
NODE_BIN="${CORTEX_NODE24_BIN:-${CORTEX_NODE24_BIN:-node}}"
PNPM_BIN="${CORTEX_PNPM117_BIN:-${CORTEX_PNPM117_BIN:-pnpm}}"
TIMEOUT="${CORTEX_GROK_TIMEOUT_SECONDS:-600}"
TOPIC="${CORTEX_GROK_TOPIC:-native-grok-smoke}"
PATH_MODE="${CORTEX_GROK_EXECUTION_PATH:-auto}"
GROK_BIN="$(command -v grok 2>/dev/null || true)"

runtime_preflight_json() {
  PATH="$(dirname "$NODE_BIN"):$PATH" python3 - "$NODE_BIN" "$PNPM_BIN" <<'PY'
import json, os, re, subprocess, sys
node, pnpm = sys.argv[1:]
errors = []
def version(path, pattern):
    if not os.path.isfile(path) or not os.access(path, os.X_OK):
        return "unknown", "missing-or-not-executable:" + path
    try:
        p = subprocess.run([path, "--version"], text=True,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           timeout=10, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return "unknown", path + ":" + type(exc).__name__
    value = (p.stdout or "").splitlines()[0].strip() or "unknown"
    if p.returncode != 0:
        return value, path + ":exit=" + str(p.returncode)
    if not re.fullmatch(pattern, value):
        return value, "unexpected-version:" + path + ":" + value
    return value, None
node_version, node_error = version(node, r"v24\.\d+\.\d+")
pnpm_version, pnpm_error = version(pnpm, r"11\.7\.\d+")
for error in (node_error, pnpm_error):
    if error:
        errors.append(error)
print(json.dumps({
    "status": "PASS" if not errors else "MACHINE_BLOCKER",
    "runtime_id": "node24-pnpm11.7",
    "node": {"path": node, "version": node_version},
    "pnpm": {"path": pnpm, "version": pnpm_version},
    "errors": errors,
}, sort_keys=True))
PY
}

client_dry_run_json() {
  if [[ ! -f "$CLIENT" ]]; then
    printf '%s\n' '{"status":"MACHINE_BLOCKER","reason":"missing-acp-policy-client"}'
    return
  fi
  local out
  out="$(bash "$CLIENT" dry-run --topic "$TOPIC" --backend grok \
    --prompt "adapter readiness probe; this is not live execution" 2>/dev/null || true)"
  python3 - "$out" <<'PY'
import json, sys
try:
    value = json.loads(sys.argv[1])
except (IndexError, json.JSONDecodeError):
    value = {"status": "MACHINE_BLOCKER", "reason": "invalid-acp-dry-run-json"}
print(json.dumps({
    "status": value.get("status", "UNKNOWN"),
    "verdict": "NOT_LIVE" if value.get("status") == "dry-run" else "MACHINE_BLOCKER",
    "tool": value.get("tool", "acp-policy-client"),
    "backend": value.get("backend", "grok"),
    "reason": value.get("reason", ""),
}, sort_keys=True))
PY
}

if [[ "${1:-}" == "--check-ready" ]]; then
  runtime="$(runtime_preflight_json)"
  probe="$(client_dry_run_json)"
  grok_version=""
  if [[ -n "$GROK_BIN" ]]; then
    grok_version="$("$GROK_BIN" --version 2>&1 | head -1 || true)"
  fi
  reason=""
  [[ -n "$GROK_BIN" ]] || reason="grok-cli-not-found"
  [[ "$(python3 -c 'import json,sys; print(json.load(sys.stdin).get("status"))' <<<"$runtime")" == "PASS" ]] || reason="${reason:-node24-pnpm11.7-preflight-failed}"
  [[ "$(python3 -c 'import json,sys; print(json.load(sys.stdin).get("status"))' <<<"$probe")" == "dry-run" ]] || reason="${reason:-acp-policy-client-dry-run-unavailable}"
  python3 - "$runtime" "$probe" "$grok_version" "$reason" "$CLIENT" "$GROK_BIN" <<'PY'
import json, sys
runtime = json.loads(sys.argv[1])
probe = json.loads(sys.argv[2])
reason = sys.argv[4]
print(json.dumps({
    "schema_version": "cortex.native-grok-adapter/v1",
    "status": "READY" if not reason and runtime.get("status") == "PASS" and sys.argv[3] else "MACHINE_BLOCKER",
    "verdict": "READINESS_ONLY", "live": False,
    "provider": "grok", "model": "grok-4.6", "executor": "acp-native:grok",
    "execution_path": "none", "provider_native": False,
    "boundary": "Grok Build CLI or ACP policy facade; not provider-native",
    "runtime_preflight": runtime, "acp_dry_run": probe,
    "grok_version": sys.argv[3] or "unknown",
    "client": sys.argv[5], "grok_binary": sys.argv[6] or "missing",
    "error": reason or "none",
    "evidence": {"dry_run_is_not_live": True, "execution_proof": "none"},
}, ensure_ascii=False, sort_keys=True))
PY
  [[ -z "$reason" ]] && exit 0 || exit 3
fi

if [[ "${1:-}" == "--dry-run" ]]; then
  probe="$(client_dry_run_json)"
  python3 - "$probe" "$CLIENT" <<'PY'
import json, sys
print(json.dumps({
    "schema_version": "cortex.native-grok-adapter/v1",
    "status": "DRY_RUN", "verdict": "NOT_LIVE",
    "provider": "grok", "model": "grok-4.6", "executor": "acp-native:grok",
    "execution_path": "none", "provider_native": False,
    "acp_dry_run": json.loads(sys.argv[1]),
    "error": "dry-run-never-proves-live",
    "evidence": {"execution_proof": "none", "client": sys.argv[2]},
}, sort_keys=True))
PY
  exit 3
fi

PROMPT_FILE="${1:-}"
RESULT_FILE="${2:-}"
if [[ -z "$PROMPT_FILE" || ! -f "$PROMPT_FILE" || -z "$RESULT_FILE" ]]; then
  printf '%s\n' '{"status":"ERROR","error":"missing-prompt-or-result"}' >&2
  exit 1
fi

fail_without_receipt() {
  local error="$1"
  local target="${RESULT_FILE:-}"
  if [[ -n "$target" && "$target" = /* && ( -z "$BOUND_RUN" || "$target" == "$BOUND_RESULT_PATH" ) ]]; then
    mkdir -p "$(dirname "$target")" 2>/dev/null || true
    printf 'status=MACHINE_BLOCKER\nerror=%s\nprovider=%s\nmodel=%s\nexecutor=%s\nexecution_path=none\nprovider_native=false\ninstance_id=%s\nsession_id=%s\nworktree_id=%s\nlease_id=%s\n' \
      "$error" "$PROVIDER" "$MODEL" "$EXECUTOR" "${CORTEX_INSTANCE_ID:-}" "${CORTEX_SESSION_ID:-}" \
      "${CORTEX_WORKTREE_ID:-}" "${CORTEX_LEASE_ID:-}" >"$target"
  fi
  printf 'MACHINE_BLOCKER error=%s\n' "$error" >&2
  exit 3
}

BOUND_RUN="${CORTEX_NATIVE_BOUND_RUN:-}"
BOUND_RESULT_PATH="${CORTEX_RESULT_PATH:-}"
BOUND_MARKER_PATH="${CORTEX_MARKER_PATH:-}"
BOUND_RECEIPT_PATH="${CORTEX_RECEIPT_PATH:-}"
BOUND_INSTANCE_ID="${CORTEX_INSTANCE_ID:-}"
BOUND_WORKTREE="${CORTEX_WORKTREE:-}"
BOUND_WORKTREE_REAL=""
BOUND_MARKER_REAL=""
BOUND_MARKER_REL=""

if [[ -n "$BOUND_RUN" ]]; then
  [[ -n "$BOUND_RESULT_PATH" && "$BOUND_RESULT_PATH" = /* ]] || fail_without_receipt "bound-result-path-required"
  [[ "$RESULT_FILE" == "$BOUND_RESULT_PATH" ]] || fail_without_receipt "bound-result-path-mismatch"
  [[ ! -L "$BOUND_RESULT_PATH" ]] || fail_without_receipt "bound-result-path-must-not-be-symlink"
  [[ -n "$BOUND_MARKER_PATH" && "$BOUND_MARKER_PATH" = /* ]] || fail_without_receipt "bound-marker-path-required"
  [[ ! -L "$BOUND_MARKER_PATH" ]] || fail_without_receipt "bound-marker-path-must-not-be-symlink"
  [[ -n "$BOUND_RECEIPT_PATH" && "$BOUND_RECEIPT_PATH" = /* ]] || fail_without_receipt "bound-receipt-path-required"
  [[ ! -L "$BOUND_RECEIPT_PATH" ]] || fail_without_receipt "bound-receipt-path-must-not-be-symlink"
  [[ "$BOUND_INSTANCE_ID" =~ ^grok-[12]$ ]] || fail_without_receipt "instance-id-not-registered"
  for value in "${CORTEX_SESSION_ID:-}" "${CORTEX_THREAD_ID:-}" "${CORTEX_LEASE_ID:-}" \
    "$BOUND_RECEIPT_PATH" "$BOUND_RESULT_PATH" "$BOUND_MARKER_PATH"; do
    [[ "$value" == *"$BOUND_INSTANCE_ID"* ]] || fail_without_receipt "instance-binding-mismatch"
  done
  [[ -n "${CORTEX_WORKTREE_ID:-}" ]] || fail_without_receipt "instance-binding-mismatch"
  [[ -n "$BOUND_WORKTREE" && "$BOUND_WORKTREE" = /* ]] || fail_without_receipt "CORTEX_WORKTREE-must-be-absolute"
  BOUND_WORKTREE_REAL="$(cd "$BOUND_WORKTREE" 2>/dev/null && pwd -P)" || fail_without_receipt "worktree-not-found"
  BOUND_MARKER_REAL="$(python3 - "$BOUND_MARKER_PATH" <<'PY'
from pathlib import Path
import sys
print(Path(sys.argv[1]).resolve(strict=False))
PY
)" || fail_without_receipt "bound-marker-path-invalid"
  [[ "$BOUND_MARKER_REAL" == "$BOUND_WORKTREE_REAL"/* ]] || fail_without_receipt "marker-outside-worktree"
  BOUND_MARKER_REL="${BOUND_MARKER_REAL#"$BOUND_WORKTREE_REAL/"}"
  [[ -n "$BOUND_MARKER_REL" && "$BOUND_MARKER_REL" != /* && "$BOUND_MARKER_REL" != *".."* ]] || \
    fail_without_receipt "marker-path-must-be-relative-without-parent"
fi

if [[ -n "$BOUND_RUN" ]]; then
  WORKTREE="$BOUND_WORKTREE_REAL"
  INSTANCE_ID="$BOUND_INSTANCE_ID"
  MARKER_REL="$BOUND_MARKER_REL"
  RECEIPT="$BOUND_RECEIPT_PATH"
else
  WORKTREE="${CORTEX_WORKTREE:-}"
  INSTANCE_ID="${CORTEX_INSTANCE_ID:-}"
  MARKER_REL="${CORTEX_GROK_MARKER_REL:-.cortex/grok-native-marker.json}"
  RECEIPT="${CORTEX_RECEIPT_PATH:-${CORTEX_GROK_RECEIPT_PATH:-${RESULT_FILE}.receipt.json}}"
fi
[[ -n "$WORKTREE" && "$WORKTREE" = /* ]] || fail_without_receipt "CORTEX_WORKTREE-must-be-absolute"
WORKTREE="$(cd "$WORKTREE" 2>/dev/null && pwd -P)" || fail_without_receipt "worktree-not-found"
[[ -d "$WORKTREE" ]] || fail_without_receipt "worktree-not-found"
[[ -f "$CLIENT" ]] || fail_without_receipt "missing-acp-policy-client"
[[ "$PATH_MODE" == "auto" || "$PATH_MODE" == "acp" || "$PATH_MODE" == "grok-build-cli" ]] || fail_without_receipt "invalid-execution-path"
repo_root="$(git -C "$WORKTREE" rev-parse --show-toplevel 2>/dev/null || true)"
[[ "$repo_root" == "$WORKTREE" ]] || fail_without_receipt "worktree-is-not-git-root"
[[ -f "$WORKTREE/.git" ]] || fail_without_receipt "shared-repository-refused"
[[ "$WORKTREE" != "$OB1_ROOT" ]] || fail_without_receipt "ob1-root-refused"
git -C "$WORKTREE" status --porcelain=v1 2>/dev/null | grep -q . && fail_without_receipt "worktree-must-start-clean"
if [[ "$MARKER_REL" = /* || "$MARKER_REL" == *..* ]]; then
  fail_without_receipt "marker-path-must-be-relative-without-parent"
fi
MARKER="$WORKTREE/$MARKER_REL"
mkdir -p "$(dirname "$RESULT_FILE")" 2>/dev/null || true
[[ "$RECEIPT" = /* ]] || fail_without_receipt "receipt-path-must-be-absolute"
[[ ! -L "$RECEIPT" ]] || fail_without_receipt "receipt-path-must-not-be-symlink"
runtime="$(runtime_preflight_json)"
runtime_status="$(python3 -c 'import json,sys; print(json.load(sys.stdin).get("status"))' <<<"$runtime")"
[[ "$runtime_status" == "PASS" ]] || fail_without_receipt "node24-pnpm11.7-preflight-failed"
[[ -n "$GROK_BIN" ]] || fail_without_receipt "grok-cli-not-found"

nonce="${CORTEX_GROK_MARKER_NONCE:-grok-native-$(date -u +%Y%m%dT%H%M%SZ)-$$}"
AUGMENTED="$(mktemp -t cortex-grok-native-prompt.XXXXXX)"
ACP_OUT="$(mktemp -t cortex-grok-native-acp.XXXXXX)"
ACP_ERR="$(mktemp -t cortex-grok-native-acp-err.XXXXXX)"
CLI_OUT="$(mktemp -t cortex-grok-native-cli.XXXXXX)"
CLI_ERR="$(mktemp -t cortex-grok-native-cli-err.XXXXXX)"
trap 'rm -f "$AUGMENTED" "$ACP_OUT" "$ACP_ERR" "$CLI_OUT" "$CLI_ERR"' EXIT

python3 - "$PROMPT_FILE" "$AUGMENTED" "$MARKER_REL" "$nonce" "$INSTANCE_ID" <<'PY'
import sys
from pathlib import Path
source, target = Path(sys.argv[1]), Path(sys.argv[2])
marker, nonce, instance_id = sys.argv[3], sys.argv[4], sys.argv[5]
body = source.read_text(encoding="utf-8", errors="replace")
identity = f',"instance_id":"{instance_id}"' if instance_id else ""
body += f"""

Bounded live smoke contract (current cwd only):
- Create or modify exactly this marker file: {marker}
- It must be valid JSON with exactly:
  {{"adapter":"acp-native-grok","provider":"grok","model":"grok-4.6"{identity},"nonce":"{nonce}","status":"written"}}
- Create parent directories if needed. Do not edit another file, run git, use network,
  delete files, or spawn subagents. Report the marker path after writing it.
"""
target.write_text(body, encoding="utf-8")
PY

run_acp() {
  ( cd "$WORKTREE" && bash "$CLIENT" run --topic "$TOPIC" --backend grok --cwd "$WORKTREE" \
      --prompt-file "$AUGMENTED" --permission-mode auto --timeout "$TIMEOUT" \
      --deny "Bash(rm*)" --deny "Bash(git*)" --deny "Bash(curl*)" --deny "Bash(wget*)" )
}
run_grok_build_cli() {
  local -a command=( "$GROK_BIN" --cwd "$WORKTREE" --model "$MODEL"
    --permission-mode acceptEdits --no-plan --prompt-file "$AUGMENTED"
    --output-format json --disable-web-search --no-subagents
    --deny "Bash(rm*)" --deny "Bash(git*)" --deny "Bash(curl*)"
    --deny "Bash(wget*)" --deny "Bash(nc*)" )
  if [[ "${CORTEX_GROK_ALWAYS_APPROVE:-0}" == "1" ]]; then
    command+=(--always-approve)
  fi
  ( cd "$WORKTREE" && "${command[@]}" )
}
verify_marker() {
  python3 - "$MARKER" "$nonce" "$INSTANCE_ID" <<'PY'
import hashlib, json, sys
from pathlib import Path
path, nonce, instance_id = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
if not path.is_file() or path.is_symlink():
    print(json.dumps({"status":"MACHINE_BLOCKER","error":"marker-missing-or-symlink"})); raise SystemExit(1)
try:
    value = json.loads(path.read_text(encoding="utf-8"))
except (OSError, json.JSONDecodeError) as exc:
    print(json.dumps({"status":"MACHINE_BLOCKER","error":"marker-invalid:"+type(exc).__name__})); raise SystemExit(1)
expected = {"adapter":"acp-native-grok","provider":"grok","model":"grok-4.6","nonce":nonce,"status":"written"}
if instance_id:
    expected["instance_id"] = instance_id
if value != expected:
    print(json.dumps({"status":"MACHINE_BLOCKER","error":"marker-content-mismatch","observed":value})); raise SystemExit(1)
print(json.dumps({"status":"PASS","path":str(path),"sha256":hashlib.sha256(path.read_bytes()).hexdigest(),"side_effect":"read-only-verifier"}))
PY
}
classify_failure() {
  if printf '%s' "$1" | grep -Eiq 'auth|login|unauthor|forbidden|credential|401|403|network|timeout|timed out|connect|rate limit|quota|sign in'; then
    printf '%s' "MACHINE_BLOCKER"
  else
    printf '%s' "ERROR"
  fi
}
write_receipt() {
  local status="$1" error="$2" acp_status="$3" cli_rc="$4" verify="$5" execution_path="$6"
  python3 - "$RESULT_FILE" "$RECEIPT" "$status" "$error" "$acp_status" "$cli_rc" "$verify" "$execution_path" "$runtime" "$PROMPT_FILE" "$WORKTREE" "$MARKER" "$nonce" "$CLIENT" "$GROK_BIN" <<'PY'
import hashlib, json, os, sys
from datetime import datetime, timezone
from pathlib import Path
(result, receipt, status, error, acp_status, cli_rc, verify, execution_path,
 runtime, prompt, worktree, marker, nonce, client, grok) = sys.argv[1:]
try:
    verification = json.loads(verify)
except json.JSONDecodeError:
    verification = {"status":"MACHINE_BLOCKER","error":"verifier-output-invalid"}
normalized_error = str(error or "").strip()
if normalized_error.lower() in {"", "none", "null"}:
    normalized_error = ""
prompt_hash = hashlib.sha256(Path(prompt).read_bytes()).hexdigest()
payload = {
    "schema_version":"cortex.native-grok-adapter/v1",
    "status":status, "verdict":"PASS_SCOPE" if status == "PASS" else "MACHINE_BLOCKER",
    "error":normalized_error or "none", "provider":"grok", "model":"grok-4.6",
    "executor":"acp-native:grok", "execution_path":execution_path,
    "instance_id":os.environ.get("CORTEX_INSTANCE_ID", ""),
    "session_id":os.environ.get("CORTEX_SESSION_ID", ""),
    "thread_id":os.environ.get("CORTEX_THREAD_ID", ""),
    "worktree_id":os.environ.get("CORTEX_WORKTREE_ID", ""),
    "lease_id":os.environ.get("CORTEX_LEASE_ID", ""),
    "result_path":result, "receipt_path":receipt,
    "marker_path":os.environ.get("CORTEX_MARKER_PATH", marker),
    "provider_native":False,
    "boundary":"Grok Build CLI with explicit model; ACP is an existing policy facade, not provider-native",
    "runtime_preflight":json.loads(runtime), "worktree":worktree, "cwd":worktree,
    "marker":marker, "nonce":nonce, "verification":verification,
    "acp":{"status":acp_status,"dry_run_is_not_live":True,"client":client},
    "grok_build_cli":{"returncode":int(cli_rc),"binary":grok},
    "prompt_sha256":prompt_hash,
    "evidence":{"marker":marker,"marker_verifier":"read-only local Python verifier",
                "receipt":receipt,"execution_proof":"marker-and-verifier" if status == "PASS" else "none"},
    "rerun":{"adapter":"bin/cortex-loop-adapters/acp-native-grok.sh",
             "execution_path":execution_path,"worktree_required":True,"prompt_sha256":prompt_hash},
    "finished_at":datetime.now(timezone.utc).isoformat().replace("+00:00","Z"),
}
receipt_path = Path(receipt)
receipt_path.parent.mkdir(parents=True, exist_ok=True)
tmp = receipt_path.with_name("." + receipt_path.name + "." + str(os.getpid()) + ".tmp")
tmp.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
os.replace(tmp, receipt_path)
Path(result).write_text("\n".join([
    # The bound runner treats a non-empty error summary as a real provider
    # error. Keep the machine-readable no-error states empty there while the
    # JSON receipt retains its stable "none" representation.
    "status="+status, "error="+normalized_error, "provider=grok", "model=grok-4.6",
    "executor=acp-native:grok", "execution_path="+execution_path, "provider_native=false",
    "instance_id="+os.environ.get("CORTEX_INSTANCE_ID", ""),
    "session_id="+os.environ.get("CORTEX_SESSION_ID", ""),
    "worktree_id="+os.environ.get("CORTEX_WORKTREE_ID", ""),
    "lease_id="+os.environ.get("CORTEX_LEASE_ID", ""),
    "evidence="+receipt, "marker="+marker, "verifier_status="+verification.get("status","UNKNOWN"),
    "acp_status="+acp_status, "cli_rc="+cli_rc, "receipt="+receipt,
]) + "\n", encoding="utf-8")
print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
PY
}

ACP_STATUS="not-run"
CLI_RC=125
if [[ "$PATH_MODE" == "auto" || "$PATH_MODE" == "grok-build-cli" ]]; then
  EXECUTION_PATH="grok-build-cli"
  set +e; run_grok_build_cli >"$CLI_OUT" 2>"$CLI_ERR"; CLI_RC=$?; set -e
else
  EXECUTION_PATH="acp"
  set +e; run_acp >"$ACP_OUT" 2>"$ACP_ERR"; ACP_RC=$?; set -e
  ACP_STATUS="$(python3 - "$ACP_OUT" "$ACP_RC" <<'PY'
import json, sys
try:
    value = json.loads(open(sys.argv[1], encoding="utf-8").read().splitlines()[-1])
    print(value.get("status","UNKNOWN"))
except (OSError, IndexError, json.JSONDecodeError):
    print("exit="+sys.argv[2])
PY
)"
  CLI_RC=0
fi

VERIFY_JSON="$(verify_marker 2>/dev/null || true)"
[[ -n "$VERIFY_JSON" ]] || VERIFY_JSON='{"status":"MACHINE_BLOCKER","error":"verifier-did-not-return"}'
VERIFY_STATUS="$(python3 -c 'import json,sys; print(json.loads(sys.stdin.read()).get("status","UNKNOWN"))' <<<"$VERIFY_JSON" 2>/dev/null || printf 'UNKNOWN')"
if [[ "$EXECUTION_PATH" == "acp" ]]; then
  if [[ "$ACP_RC" -eq 0 && "$VERIFY_STATUS" == "PASS" ]]; then
    write_receipt "PASS" "" "$ACP_STATUS" "$CLI_RC" "$VERIFY_JSON" "acp"; exit 0
  fi
  error="$(classify_failure "$(cat "$ACP_OUT" "$ACP_ERR" 2>/dev/null || true) $VERIFY_JSON")"
  write_receipt "$error" "acp-live-failed-or-marker-not-verified" "$ACP_STATUS" "$CLI_RC" "$VERIFY_JSON" "acp"
  exit 3
fi
if [[ "$CLI_RC" -eq 0 && "$VERIFY_STATUS" == "PASS" ]]; then
  write_receipt "PASS" "" "$ACP_STATUS" "$CLI_RC" "$VERIFY_JSON" "grok-build-cli"; exit 0
fi
error="$(classify_failure "$(cat "$CLI_OUT" "$CLI_ERR" 2>/dev/null || true) $VERIFY_JSON")"
write_receipt "$error" "grok-build-cli-live-failed-or-marker-not-verified" "$ACP_STATUS" "$CLI_RC" "$VERIFY_JSON" "grok-build-cli"
exit 3
