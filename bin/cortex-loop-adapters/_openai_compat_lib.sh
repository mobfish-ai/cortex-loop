#!/usr/bin/env bash
# bin/cortex-loop-adapters/_openai_compat_lib.sh
#
# Shared library -- not an adapter. No $1/$2 top-level entry; it can only be sourced.
# Shared by minimax.sh / glm.sh: both providers declare in openclaw.json
# api="openai-completions", i.e. standard OpenAI-compatible /chat/completions.
# Body construction / HTTP call / status classification / response parsing are byte-for-byte the same --
# the second hand-roll should become a tool (ATOMIZE), so one copy is shared by both provider adapters.
#
# Functions provided (usable after source; none print a raw key):
#   oc_key_hash <key>                                          → stdout: 12-char sha256 prefix
#   oc_ordered_keys <providers_csv> <extra_env_name> <state_file> <cooldown_sec>
#                                                               → stdout: label\tbase_url\tkey\thash (one row each; ready keys first, cooling keys last)
#   oc_call <base_url> <api_key> <model> <prompt_file> <result_file> <timeout_sec>
#                                                               → rc=0 success (result written to result_file); non-zero: see OC_ERROR_KIND
#   oc_mark_success <state_file> <hash>                        → clear this key's failure record
#   oc_mark_failure <state_file> <hash> <label>                → record this key's failure time
#
# Safety: no function writes the raw api_key into result_file / state_file / stdout /
# stderr -- state_file stores only the sha256 prefix (hash) + label (e.g. "minimax#1", not the key itself).

oc_key_hash() {
    printf '%s' "$1" | shasum -a 256 2>/dev/null | cut -c1-12
}

# oc_ordered_keys <providers_csv> <extra_env_name> <state_file> <cooldown_sec>
# providers_csv: entry names under openclaw.json models.providers, comma-separated (e.g. "minimax,minimax-cn")
# extra_env_name: env var for extra keys (e.g. "MINIMAX_API_KEYS", comma-separated, using the first provider's base_url)
# Read order: each provider's apiKey (single, backward compatible) + apiKeys[] (array, new convention, for multiple accounts)
oc_ordered_keys() {
    local providers_csv="$1" extra_env_name="$2" state_file="$3" cooldown="$4"
    local extra_val="${!extra_env_name:-}"
    OC_PROVIDERS_CSV="$providers_csv" OC_EXTRA_KEYS="$extra_val" \
    OC_OPENCLAW_JSON="${OPENCLAW_JSON_PATH:-$HOME/.openclaw/openclaw.json}" \
    OC_STATE_FILE="$state_file" OC_COOLDOWN="$cooldown" \
    python3 - <<'PYEOF'
import json, os, hashlib, time

def key_hash(k):
    return hashlib.sha256(k.encode("utf-8")).hexdigest()[:12]

providers_csv = os.environ["OC_PROVIDERS_CSV"]
extra_keys = os.environ.get("OC_EXTRA_KEYS", "")
oj_path = os.environ["OC_OPENCLAW_JSON"]
state_path = os.environ["OC_STATE_FILE"]
cooldown = int(os.environ.get("OC_COOLDOWN", "180") or "180")

try:
    with open(oj_path, "r", encoding="utf-8") as f:
        oj = json.load(f)
except Exception:
    oj = {}
providers = oj.get("models", {}).get("providers", {})

rows = []
first_base_url = None
for pname in [p.strip() for p in providers_csv.split(",") if p.strip()]:
    p = providers.get(pname)
    if not isinstance(p, dict):
        continue
    base_url = p.get("baseUrl", "")
    if not base_url:
        continue
    if first_base_url is None:
        first_base_url = base_url
    keys = []
    ak = p.get("apiKey")
    if isinstance(ak, str) and ak:
        keys.append(ak)
    extra_arr = p.get("apiKeys")
    if isinstance(extra_arr, list):
        for k in extra_arr:
            if isinstance(k, str) and k:
                keys.append(k)
    for i, k in enumerate(keys, start=1):
        rows.append((f"{pname}#{i}", base_url, k))

# Extra keys from the env (temporary / quick fill-in; real multi-account keys belong in openclaw.json apiKeys[])
if extra_keys.strip() and first_base_url:
    for i, k in enumerate([x.strip() for x in extra_keys.split(",") if x.strip()], start=1):
        rows.append((f"env#{i}", first_base_url, k))

try:
    with open(state_path, "r", encoding="utf-8") as f:
        state = json.load(f)
except Exception:
    state = {}

now = int(time.time())
ready, cooling = [], []
for label, base_url, key in rows:
    h = key_hash(key)
    last_fail = state.get(h, {}).get("last_fail_epoch", 0)
    row_out = f"{label}\t{base_url}\t{key}\t{h}"
    if now - last_fail < cooldown:
        cooling.append(row_out)
    else:
        ready.append(row_out)

# Ready keys first; if every key is cooling, still return all of them (better to retry through cooldown than to have no key)
for r in ready + cooling:
    print(r)
PYEOF
}

# oc_call <base_url> <api_key> <model> <prompt_file> <result_file> <timeout_sec>
oc_call() {
    local base_url="$1" api_key="$2" model="$3" prompt_file="$4" result_file="$5" timeout="${6:-120}"
    local body_file resp_file http_code curl_rc err_file
    body_file="$(mktemp /tmp/oc-body.XXXXXX)"
    resp_file="$(mktemp /tmp/oc-resp.XXXXXX)"
    err_file="$(mktemp /tmp/oc-err.XXXXXX)"

    OC_PROMPT_FILE="$prompt_file" OC_MODEL="$model" python3 - "$body_file" <<'PYEOF'
import json, os, sys
body_file = sys.argv[1]
prompt_file = os.environ["OC_PROMPT_FILE"]
model = os.environ["OC_MODEL"]
with open(prompt_file, "r", encoding="utf-8", errors="replace") as f:
    prompt = f.read()
payload = {
    "model": model,
    "messages": [{"role": "user", "content": prompt}],
    "temperature": 0.3,
}
with open(body_file, "w", encoding="utf-8") as f:
    json.dump(payload, f, ensure_ascii=False)
PYEOF
    if [[ ! -s "$body_file" ]]; then
        OC_ERROR_KIND="build_body"
        echo "[oc_call] failed to build request body (prompt file unreadable?)" > "$result_file"
        rm -f "$body_file" "$resp_file" "$err_file"
        return 90
    fi

    http_code=$(timeout "$((timeout + 30))" curl -sS -o "$resp_file" -w '%{http_code}' \
        --max-time "$timeout" \
        "${base_url%/}/chat/completions" \
        -H "Authorization: Bearer ${api_key}" \
        -H "Content-Type: application/json" \
        --data-binary @"$body_file" 2>"$err_file")
    curl_rc=$?
    rm -f "$body_file"

    if [[ $curl_rc -ne 0 ]]; then
        OC_ERROR_KIND="network"
        { echo "[oc_call] curl network failure curl_rc=$curl_rc"; cat "$err_file" 2>/dev/null; } > "$result_file"
        rm -f "$resp_file" "$err_file"
        return 91
    fi
    rm -f "$err_file"

    case "$http_code" in
        200)
            if OC_RESP_FILE="$resp_file" OC_RESULT_FILE="$result_file" python3 - <<'PYEOF'
import json, os, sys
resp_path = os.environ["OC_RESP_FILE"]
result_path = os.environ["OC_RESULT_FILE"]
try:
    with open(resp_path, "r", encoding="utf-8", errors="replace") as f:
        data = json.load(f)
    content = data["choices"][0]["message"]["content"]
except Exception:
    sys.exit(1)
if not content or not content.strip():
    sys.exit(1)
with open(result_path, "w", encoding="utf-8") as f:
    f.write(content)
PYEOF
            then
                rm -f "$resp_file"
                return 0
            else
                OC_ERROR_KIND="empty"
                { echo "[oc_call] HTTP 200 but response parse failed or content is empty (first 500 bytes):"; head -c 500 "$resp_file"; } > "$result_file"
                rm -f "$resp_file"
                return 92
            fi
            ;;
        401|403)
            OC_ERROR_KIND="auth"
            { echo "[oc_call] HTTP $http_code auth failure (key invalid or quota exhausted) (first 500 bytes):"; head -c 500 "$resp_file"; } > "$result_file"
            rm -f "$resp_file"
            return 93
            ;;
        429)
            OC_ERROR_KIND="rate_limit"
            { echo "[oc_call] HTTP 429 rate limit or quota exhausted (first 500 bytes):"; head -c 500 "$resp_file"; } > "$result_file"
            rm -f "$resp_file"
            return 94
            ;;
        5*)
            OC_ERROR_KIND="server"
            { echo "[oc_call] HTTP $http_code server error (first 500 bytes):"; head -c 500 "$resp_file"; } > "$result_file"
            rm -f "$resp_file"
            return 95
            ;;
        *)
            OC_ERROR_KIND="other"
            { echo "[oc_call] HTTP $http_code unclassified error (first 500 bytes):"; head -c 500 "$resp_file"; } > "$result_file"
            rm -f "$resp_file"
            return 96
            ;;
    esac
}

# oc_ordered_ccswitch_accounts <name_like_pattern> <state_file> <cooldown_sec>
# Read Anthropic-compatible endpoint accounts straight from the CC Switch desktop tool's
# local SQLite (~/.cc-switch/cc-switch.db): the base_url/model/token triple. The provider
# that the claude CLI uses is this schema, not openclaw.json's OpenAI-compatible schema.
#
# Why not ~/.claude/settings.json: that file is written only after a human clicks
# Enable in the CC Switch GUI -- the unattended heartbeat runs every 2 minutes, and nobody clicks for it.
# Observed 2026-07-31: settings.json pointed at "Claude Official" while cheap.sh sent
# a model name the real official endpoint does not know, so adapter FAIL rc=1 was certain, not a flake.
# Reading SQLite directly (read-only query; do not touch GUI state / is_current) removes that human dependency.
oc_ordered_ccswitch_accounts() {
    local name_pattern="$1" state_file="$2" cooldown="$3"
    local db="$HOME/.cc-switch/cc-switch.db"
    OC_DB="$db" OC_PATTERN="$name_pattern" OC_STATE_FILE="$state_file" OC_COOLDOWN="$cooldown" \
    python3 - <<'PYEOF'
import sqlite3, json, os, hashlib, time

def key_hash(k):
    return hashlib.sha256(k.encode("utf-8")).hexdigest()[:12]

db_path = os.environ["OC_DB"]
pattern = os.environ["OC_PATTERN"]
state_path = os.environ["OC_STATE_FILE"]
cooldown = int(os.environ.get("OC_COOLDOWN", "180") or "180")

rows = []
try:
    conn = sqlite3.connect(db_path)
    cur = conn.execute(
        "SELECT name, settings_config FROM providers "
        "WHERE app_type='claude' AND name LIKE ? ORDER BY name",
        (pattern,),
    )
    for name, cfg_json in cur.fetchall():
        try:
            cfg = json.loads(cfg_json)
        except Exception:
            continue
        env = cfg.get("env", {})
        base_url = env.get("ANTHROPIC_BASE_URL", "")
        token = env.get("ANTHROPIC_AUTH_TOKEN", "")
        model = env.get("ANTHROPIC_MODEL", "")
        if base_url and token and model:
            rows.append((name, base_url, model, token))
    conn.close()
except Exception:
    pass

try:
    with open(state_path, "r", encoding="utf-8") as f:
        state = json.load(f)
except Exception:
    state = {}

now = int(time.time())
ready, cooling = [], []
for name, base_url, model, token in rows:
    h = key_hash(token)
    last_fail = state.get(h, {}).get("last_fail_epoch", 0)
    row_out = f"{name}\t{base_url}\t{model}\t{token}\t{h}"
    if now - last_fail < cooldown:
        cooling.append(row_out)
    else:
        ready.append(row_out)

for r in ready + cooling:
    print(r)
PYEOF
}

oc_mark_success() {
    local state_file="$1" hash="$2"
    OC_STATE_FILE="$state_file" OC_HASH="$hash" python3 - <<'PYEOF'
import fcntl, json, os, tempfile
path = os.environ["OC_STATE_FILE"]
h = os.environ["OC_HASH"]
state_dir = os.path.dirname(path) or "."
os.makedirs(state_dir, exist_ok=True)
with open(path + ".lock", "a+") as lock:
    fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
    try:
        with open(path) as f:
            data = json.load(f)
    except Exception:
        data = {}
    data.pop(h, None)
    fd, tmp = tempfile.mkstemp(prefix=os.path.basename(path) + ".", dir=state_dir)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f)
            f.flush(); os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)
PYEOF
}

oc_mark_failure() {
    local state_file="$1" hash="$2" label="$3"
    OC_STATE_FILE="$state_file" OC_HASH="$hash" OC_LABEL="$label" python3 - <<'PYEOF'
import fcntl, json, os, tempfile, time
path = os.environ["OC_STATE_FILE"]
h = os.environ["OC_HASH"]
label = os.environ["OC_LABEL"]
state_dir = os.path.dirname(path) or "."
os.makedirs(state_dir, exist_ok=True)
with open(path + ".lock", "a+") as lock:
    fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
    try:
        with open(path) as f:
            data = json.load(f)
    except Exception:
        data = {}
    entry = data.get(h, {"fail_count": 0})
    entry["last_fail_epoch"] = int(time.time())
    entry["fail_count"] = entry.get("fail_count", 0) + 1
    entry["label_hint"] = label
    data[h] = entry
    fd, tmp = tempfile.mkstemp(prefix=os.path.basename(path) + ".", dir=state_dir)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f)
            f.flush(); os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)
PYEOF
}
