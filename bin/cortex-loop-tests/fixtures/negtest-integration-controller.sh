#!/usr/bin/env bash
set -euo pipefail
export GIT_CONFIG_COUNT=3
export GIT_CONFIG_KEY_0=core.fsmonitor GIT_CONFIG_VALUE_0=false
export GIT_CONFIG_KEY_1=maintenance.auto GIT_CONFIG_VALUE_1=false
export GIT_CONFIG_KEY_2=gc.auto GIT_CONFIG_VALUE_2=0

ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
INTEGRATOR="$ROOT/bin/cortex-integrator.sh"
TMP="$(mktemp -d /tmp/cortex-integrator-test.XXXXXX)"
cleanup() { rm -rf "$TMP"; }
trap cleanup EXIT
SRC="$TMP/source"; ORIGIN="$TMP/origin.git"

git init --bare --quiet "$ORIGIN"
git --git-dir="$ORIGIN" config uploadpack.allowFilter true
git --git-dir="$ORIGIN" config uploadpack.allowAnySHA1InWant true
git init --quiet "$SRC"
git -C "$SRC" config user.name Fixture
git -C "$SRC" config user.email fixture@example.invalid
git -C "$SRC" remote add origin "$ORIGIN"
printf 'a0\n' > "$SRC/a.txt"
printf 'b0\n' > "$SRC/b.txt"
mkdir -p "$SRC/checks"
printf '#!/usr/bin/env bash\ntest -s a.txt && test -s b.txt\n' > "$SRC/checks/verify.sh"
# shellcheck disable=SC2016
printf '#!/usr/bin/env bash\ntest "$(cat a.txt)" = a1 && test "$(cat b.txt)" = b1\n' > "$SRC/checks/final.sh"
dd if=/dev/urandom of="$SRC/big-unrelated.bin" bs=1048576 count=32 2>/dev/null
git -C "$SRC" add a.txt b.txt checks/verify.sh checks/final.sh big-unrelated.bin
git -C "$SRC" commit --quiet -m base
BASE="$(git -C "$SRC" rev-parse HEAD)"
git -C "$SRC" push --quiet origin "HEAD:refs/heads/main"
git -C "$SRC" push --quiet origin "HEAD:refs/heads/directory-test"

printf 'a1\n' > "$SRC/a.txt"
git -C "$SRC" add a.txt
git -C "$SRC" commit --quiet -m candidate-a
CANDIDATE_A="$(git -C "$SRC" rev-parse HEAD)"

git -C "$SRC" checkout --quiet --detach "$BASE"
printf 'b1\n' > "$SRC/b.txt"
git -C "$SRC" add b.txt
git -C "$SRC" commit --quiet -m candidate-b
CANDIDATE_B="$(git -C "$SRC" rev-parse HEAD)"

git -C "$SRC" checkout --quiet --detach "$BASE"
printf 'forbidden\n' > "$SRC/evil.txt"
git -C "$SRC" add evil.txt
git -C "$SRC" commit --quiet -m candidate-evil
CANDIDATE_EVIL="$(git -C "$SRC" rev-parse HEAD)"

git -C "$SRC" checkout --quiet --detach "$BASE"
printf '<<<<<<< ours\na1\n=======\na2\n>>>>>>> theirs\n' > "$SRC/a.txt"
git -C "$SRC" add a.txt
git -C "$SRC" commit --quiet -m candidate-conflict-marker
CANDIDATE_MARKER="$(git -C "$SRC" rev-parse HEAD)"

git -C "$SRC" checkout --quiet --detach "$BASE"
printf '#!/usr/bin/env bash\nexit 99\n' > "$SRC/checks/verify.sh"
git -C "$SRC" add checks/verify.sh
git -C "$SRC" commit --quiet -m candidate-readonly-mutation
CANDIDATE_READ_MUT="$(git -C "$SRC" rev-parse HEAD)"

git -C "$SRC" checkout --quiet --detach "$BASE"
printf 'TOKEN=do-not-land\n' > "$SRC/.env"
git -C "$SRC" add .env
git -C "$SRC" commit --quiet -m candidate-protected-path
CANDIDATE_PROTECTED="$(git -C "$SRC" rev-parse HEAD)"

git -C "$SRC" checkout --quiet --detach "$BASE"
# Build the forbidden shape only inside the ephemeral fixture repository. Keeping
# the key and JSON syntax on separate tracked lines lets the production range
# gate scan this test file without mistaking the test vector for a real secret.
SECRET_KEY='appSecret'
SECRET_VALUE='secret-shaped-value'
printf '{"%s":"%s"}\n' "$SECRET_KEY" "$SECRET_VALUE" > "$SRC/secret-shaped.json"
git -C "$SRC" add secret-shaped.json
git -C "$SRC" commit --quiet -m candidate-secret-shaped
CANDIDATE_SECRET="$(git -C "$SRC" rev-parse HEAD)"

git -C "$SRC" checkout --quiet --detach "$BASE"
mkdir -p "$SRC/allowed-dir"
printf 'directory allow without slash\n' > "$SRC/allowed-dir/ok.txt"
git -C "$SRC" add allowed-dir/ok.txt
git -C "$SRC" commit --quiet -m candidate-directory-allow
CANDIDATE_DIRECTORY="$(git -C "$SRC" rev-parse HEAD)"

git -C "$SRC" checkout --quiet --detach "$BASE"
mkdir -p "$SRC/allowed-dir-sibling"
printf 'must not prefix-match\n' > "$SRC/allowed-dir-sibling/evil.txt"
git -C "$SRC" add allowed-dir-sibling/evil.txt
git -C "$SRC" commit --quiet -m candidate-directory-prefix-escape
CANDIDATE_DIRECTORY_ESCAPE="$(git -C "$SRC" rev-parse HEAD)"

# A living companion receipt is already present on the canonical tip while the
# candidate also refreshes that same path. The business artifact must still
# replay and land; only the conflicting companion is retained from canonical.
git -C "$SRC" checkout --quiet --detach "$BASE"
mkdir -p "$SRC/reports"
printf 'canonical living receipt\n' > "$SRC/reports/live-receipt.md"
git -C "$SRC" add reports/live-receipt.md
git -C "$SRC" commit --quiet -m canonical-living-receipt
COMPANION_CANONICAL="$(git -C "$SRC" rev-parse HEAD)"
git -C "$SRC" push --quiet origin "HEAD:refs/heads/companion-canonical"
git -C "$SRC" checkout --quiet --detach "$BASE"
mkdir -p "$SRC/reports"
printf 'business artifact\n' > "$SRC/business-artifact.txt"
printf 'candidate refreshed receipt\n' > "$SRC/reports/live-receipt.md"
git -C "$SRC" add business-artifact.txt reports/live-receipt.md
git -C "$SRC" commit --quiet -m candidate-with-living-receipt
COMPANION_CANDIDATE="$(git -C "$SRC" rev-parse HEAD)"

(cd "$SRC" && "$INTEGRATOR" --candidate "$COMPANION_CANDIDATE" --base "$BASE" \
  --allow business-artifact.txt --allow reports/live-receipt.md \
  --companion reports/live-receipt.md --remote origin \
  --ref refs/heads/companion-canonical \
  --short-test 'test "$(cat business-artifact.txt)" = "business artifact"') > "$TMP/companion.json"
python3 - "$TMP/companion.json" <<'PY'
import json, sys
d = json.load(open(sys.argv[1], encoding="utf-8"))
assert d["status"] == "landed", d
assert d["companion_status"] == "skipped_content_conflict", d
assert d["companion_policy"] == "skip-conflicting-companion", d
assert d["companion_paths"] == ["reports/live-receipt.md"], d
PY
COMPANION_VERIFY="$TMP/verify-companion"
git clone --quiet --branch companion-canonical "$ORIGIN" "$COMPANION_VERIFY"
[[ "$(cat "$COMPANION_VERIFY/business-artifact.txt")" == "business artifact" ]]
[[ "$(cat "$COMPANION_VERIFY/reports/live-receipt.md")" == "canonical living receipt" ]]

set +e
(cd "$SRC" && CORTEX_INTEGRATOR_MIN_FREE_KB=999999999999 "$INTEGRATOR" \
  --candidate "$CANDIDATE_A" --base "$BASE" --allow a.txt --read b.txt \
  --read checks/verify.sh --remote origin --ref refs/heads/main \
  --short-test 'bash checks/verify.sh') > "$TMP/disk.json"
DISK_RC=$?
(cd "$SRC" && "$INTEGRATOR" --candidate "$CANDIDATE_EVIL" --base "$BASE" \
  --allow a.txt --allow b.txt --read checks/verify.sh --remote origin --ref refs/heads/main \
  --short-test 'bash checks/verify.sh') > "$TMP/evil.json"
EVIL_RC=$?
set -e
[[ $DISK_RC -eq 75 && $EVIL_RC -eq 2 ]]
python3 - "$TMP/disk.json" "$TMP/evil.json" <<'PY'
import json, sys
disk=json.load(open(sys.argv[1])); evil=json.load(open(sys.argv[2]))
assert disk["status"] == "retryable_disk_budget", disk
assert evil["status"] == "rejected_scope", evil
PY
[[ "$(git --git-dir="$ORIGIN" rev-parse refs/heads/main)" == "$BASE" ]]

# Directory declarations match descendants with or without a trailing slash,
# but never a sibling that merely shares the textual prefix.
(cd "$SRC" && "$INTEGRATOR" --candidate "$CANDIDATE_DIRECTORY" --base "$BASE" \
  --allow allowed-dir --remote origin --ref refs/heads/directory-test \
  --short-test 'test -s allowed-dir/ok.txt && test ! -e big-unrelated.bin') > "$TMP/directory.json"
set +e
(cd "$SRC" && "$INTEGRATOR" --candidate "$CANDIDATE_DIRECTORY_ESCAPE" --base "$BASE" \
  --allow allowed-dir --remote origin --ref refs/heads/directory-test \
  --short-test 'exit 0') > "$TMP/directory-escape.json"
DIRECTORY_ESCAPE_RC=$?
set -e
[[ $DIRECTORY_ESCAPE_RC -eq 2 ]]
python3 - "$TMP/directory.json" "$TMP/directory-escape.json" <<'PY'
import json, sys
ok=json.load(open(sys.argv[1])); escape=json.load(open(sys.argv[2]))
assert ok["status"] == "landed", ok
assert escape["status"] == "rejected_scope", escape
PY

set +e
(cd "$SRC" && "$INTEGRATOR" --candidate "$CANDIDATE_MARKER" --base "$BASE" \
  --allow a.txt --read b.txt --read checks/verify.sh --remote origin --ref refs/heads/main \
  --short-test 'bash checks/verify.sh') > "$TMP/marker.json"
MARKER_RC=$?
(cd "$SRC" && "$INTEGRATOR" --candidate "$CANDIDATE_A" --base "$BASE" \
  --allow a.txt --read b.txt --read checks/verify.sh --remote origin --ref refs/heads/main \
  --short-test 'exit 9') > "$TMP/short-test.json"
SHORT_RC=$?
(cd "$SRC" && "$INTEGRATOR" --candidate "$CANDIDATE_A" --base "$BASE" \
  --allow a.txt --read b.txt --read checks/verify.sh --remote origin --ref refs/heads/main \
  --short-test 'printf "test mutation\\n" >> a.txt; exit 0') > "$TMP/short-test-side-effect.json"
SHORT_SIDE_EFFECT_RC=$?
(cd "$SRC" && "$INTEGRATOR" --candidate "$CANDIDATE_READ_MUT" --base "$BASE" \
  --allow checks/verify.sh --read checks/verify.sh --remote origin --ref refs/heads/main \
  --short-test 'bash checks/verify.sh') > "$TMP/readonly.json"
READONLY_RC=$?
(cd "$SRC" && "$INTEGRATOR" --candidate "$CANDIDATE_PROTECTED" --base "$BASE" \
  --allow .env --read a.txt --read b.txt --read checks/verify.sh \
  --remote origin --ref refs/heads/main --short-test 'bash checks/verify.sh') > "$TMP/protected.json"
PROTECTED_RC=$?
(cd "$SRC" && "$INTEGRATOR" --candidate "$CANDIDATE_SECRET" --base "$BASE" \
  --allow secret-shaped.json --read a.txt --read b.txt --read checks/verify.sh \
  --remote origin --ref refs/heads/main --short-test 'bash checks/verify.sh') > "$TMP/secret.json"
SECRET_RC=$?
set -e
[[ $MARKER_RC -eq 2 && $SHORT_RC -eq 1 && $SHORT_SIDE_EFFECT_RC -eq 1 && $READONLY_RC -eq 2 \
   && $PROTECTED_RC -eq 2 && $SECRET_RC -eq 2 ]]
python3 - "$TMP/marker.json" "$TMP/short-test.json" "$TMP/short-test-side-effect.json" "$TMP/readonly.json" \
  "$TMP/protected.json" "$TMP/secret.json" <<'PY'
import json, sys
marker=json.load(open(sys.argv[1])); short=json.load(open(sys.argv[2]))
side_effect=json.load(open(sys.argv[3])); readonly=json.load(open(sys.argv[4]))
protected=json.load(open(sys.argv[5])); secret=json.load(open(sys.argv[6]))
assert marker["status"] == "rejected_conflict_marker", marker
assert short["status"] == "rejected_short_test", short
assert side_effect["status"] == "rejected_short_test_side_effect", side_effect
assert readonly["status"] == "rejected_readonly_change", readonly
assert protected["status"] == "rejected_v4_secret_gate", protected
assert secret["status"] == "rejected_v4_secret_gate", secret
assert protected["safety_gates"]["v4_secret_gate"] == "rejected", protected
assert secret["safety_gates"]["v4_secret_gate"] == "rejected", secret
PY
[[ "$(git --git-dir="$ORIGIN" rev-parse refs/heads/main)" == "$BASE" ]]

# Force both integrators to observe BASE before either push. Exactly one lease-CAS
# may win; the loser must return retryable 75 and leave the winner untouched.
BARRIER="$TMP/barrier"; mkdir -p "$BARRIER"
(cd "$SRC" && CORTEX_INTEGRATOR_TEST_BARRIER_DIR="$BARRIER" "$INTEGRATOR" \
  --candidate "$CANDIDATE_A" --base "$BASE" --allow a.txt --read b.txt \
  --read checks/verify.sh --remote origin --ref refs/heads/main \
  --short-test 'bash checks/verify.sh') > "$TMP/a.json" &
PID_A=$!
(cd "$SRC" && CORTEX_INTEGRATOR_TEST_BARRIER_DIR="$BARRIER" "$INTEGRATOR" \
  --candidate "$CANDIDATE_B" --base "$BASE" --allow b.txt --read a.txt \
  --read checks/verify.sh --remote origin --ref refs/heads/main \
  --short-test 'bash checks/verify.sh') > "$TMP/b.json" &
PID_B=$!

deadline=$(( $(date +%s) + 15 ))
while [[ "$(find "$BARRIER" -name 'ready.*' -type f | wc -l | tr -d ' ')" -lt 2 ]]; do
  [[ $(date +%s) -lt $deadline ]]
  sleep 0.05
done
: > "$BARRIER/release"
set +e
wait "$PID_A"; RC_A=$?
wait "$PID_B"; RC_B=$?
set -e
if [[ $RC_A -eq 0 && $RC_B -eq 75 ]]; then
  LOSER_CANDIDATE="$CANDIDATE_B"; LOSER_ALLOW="b.txt"; LOSER_READ="a.txt"
elif [[ $RC_B -eq 0 && $RC_A -eq 75 ]]; then
  LOSER_CANDIDATE="$CANDIDATE_A"; LOSER_ALLOW="a.txt"; LOSER_READ="b.txt"
else
  printf 'expected one landed and one CAS retry, got a=%s b=%s\n' "$RC_A" "$RC_B" >&2
  exit 1
fi
python3 - "$TMP/a.json" "$TMP/b.json" <<'PY'
import json, sys
states=[json.load(open(p))["status"] for p in sys.argv[1:]]
assert sorted(states) == ["landed", "retryable_cas_conflict"], states
PY

# Same old-base candidate is safe to retry: controller replays its delta onto the
# new canonical tip and leases that exact new tip.
# shellcheck disable=SC2016
(cd "$SRC" && "$INTEGRATOR" --candidate "$LOSER_CANDIDATE" --base "$BASE" \
  --allow "$LOSER_ALLOW" --read "$LOSER_READ" --read checks/final.sh \
  --remote origin --ref refs/heads/main \
  --short-test 'test ! -e big-unrelated.bin && bash checks/final.sh' \
  --receipt "$TMP/retry.receipt.json") > "$TMP/retry.json"
SOURCE_OBJECT_KB="$(du -sk "$SRC/.git/objects" | awk '{print $1}')"
python3 - "$TMP/retry.json" "$SOURCE_OBJECT_KB" <<'PY'
import json, sys
d=json.load(open(sys.argv[1])); assert d["status"] == "landed" and d["landed_commit"]
iso=d["isolation"]
assert iso["candidate_objects"] == "local-alternates"
assert iso["canonical_fetch"].endswith("filter=blob:none")
assert iso["materialization"] == "sparse allow+read"
assert int(sys.argv[2]) > 30000, sys.argv[2]
assert iso["temp_repo_kb"] < 4096, (iso, sys.argv[2])
PY
cmp "$TMP/retry.json" "$TMP/retry.receipt.json"

VERIFY="$TMP/verify"
git clone --quiet --branch main "$ORIGIN" "$VERIFY"
[[ "$(cat "$VERIFY/a.txt")" == "a1" ]]
[[ "$(cat "$VERIFY/b.txt")" == "b1" ]]
[[ ! -e "$VERIFY/evil.txt" ]]
[[ "$(git --git-dir="$ORIGIN" rev-list --count refs/heads/main)" -eq 3 ]]

# Cross-node handoff: candidate exists only behind a remote custom ref. The
# consumer has no candidate/base alternates and the producer is removed before
# integration; blobless candidate-ref fetch must still land it sparsely.
PRODUCER="$TMP/producer"
git clone --quiet --branch main "$ORIGIN" "$PRODUCER"
git -C "$PRODUCER" config user.name RemoteProducer
git -C "$PRODUCER" config user.email remote-producer@example.invalid
REMOTE_BASE="$(git -C "$PRODUCER" rev-parse HEAD)"
printf 'remote candidate\n' > "$PRODUCER/remote-only.txt"
git -C "$PRODUCER" add remote-only.txt
git -C "$PRODUCER" commit --quiet -m remote-only-candidate
REMOTE_CANDIDATE="$(git -C "$PRODUCER" rev-parse HEAD)"
REMOTE_CANDIDATE_REF="refs/cortex/candidate/fixture-remote-only"
git -C "$PRODUCER" push --quiet origin "HEAD:$REMOTE_CANDIDATE_REF"
rm -rf "$PRODUCER"

CONSUMER="$TMP/consumer"
git init --quiet "$CONSUMER"
git -C "$CONSUMER" remote add origin "$ORIGIN"
if git -C "$CONSUMER" cat-file -e "$REMOTE_CANDIDATE^{commit}" 2>/dev/null; then
  printf 'consumer unexpectedly has remote-only candidate before integration\n' >&2
  exit 1
fi
set +e
(cd "$CONSUMER" && "$INTEGRATOR" --candidate "$REMOTE_BASE" \
  --candidate-ref "$REMOTE_CANDIDATE_REF" --base "$REMOTE_BASE" \
  --allow remote-only.txt --read a.txt --read b.txt --read checks/final.sh \
  --remote origin --ref refs/heads/main \
  --short-test 'test -s remote-only.txt && bash checks/final.sh') > "$TMP/remote-mismatch.json"
MISMATCH_RC=$?
set -e
[[ $MISMATCH_RC -eq 2 ]]
python3 - "$TMP/remote-mismatch.json" <<'PY'
import json, sys
d=json.load(open(sys.argv[1])); assert d["status"] == "rejected_candidate_ref_mismatch", d
PY
(cd "$CONSUMER" && "$INTEGRATOR" --candidate "$REMOTE_CANDIDATE" \
  --candidate-ref "$REMOTE_CANDIDATE_REF" --base "$REMOTE_BASE" \
  --allow remote-only.txt --read a.txt --read b.txt --read checks/final.sh \
  --remote origin --ref refs/heads/main \
  --short-test 'test -s remote-only.txt && test ! -e big-unrelated.bin && bash checks/final.sh') > "$TMP/remote-candidate.json"
ORIGIN_OBJECT_KB="$(du -sk "$ORIGIN/objects" | awk '{print $1}')"
python3 - "$TMP/remote-candidate.json" "$REMOTE_CANDIDATE_REF" "$ORIGIN_OBJECT_KB" <<'PY'
import json, sys
d=json.load(open(sys.argv[1]))
assert d["status"] == "landed", d
assert d["candidate_ref"] == sys.argv[2], d
assert d["isolation"]["candidate_objects"] == "remote-ref-blobless", d
assert d["isolation"]["materialization"] == "sparse allow+read", d
assert int(sys.argv[3]) > 30000, sys.argv[3]
assert d["isolation"]["temp_repo_kb"] < 4096, (d["isolation"], sys.argv[3])
PY
VERIFY_REMOTE="$TMP/verify-remote"
git clone --quiet --branch main "$ORIGIN" "$VERIFY_REMOTE"
[[ "$(cat "$VERIFY_REMOTE/remote-only.txt")" == "remote candidate" ]]
[[ "$(cat "$VERIFY_REMOTE/a.txt")" == "a1" && "$(cat "$VERIFY_REMOTE/b.txt")" == "b1" ]]
[[ "$(git --git-dir="$ORIGIN" rev-parse "$REMOTE_CANDIDATE_REF")" == "$REMOTE_CANDIDATE" ]]
[[ "$(git --git-dir="$ORIGIN" rev-list --count refs/heads/main)" -eq 4 ]]

# Diverged local base: one local-only commit precedes the desired candidate.
# Only base..candidate may land; the unrelated local commit must not leak into main.
git -C "$SRC" fetch --quiet origin refs/heads/main:refs/remotes/origin/main
DIVERGED_SHARED="$(git -C "$SRC" rev-parse refs/remotes/origin/main)"
git -C "$SRC" checkout --quiet --detach "$DIVERGED_SHARED"
printf 'must stay local\n' > "$SRC/local-only-before-base.txt"
git -C "$SRC" add local-only-before-base.txt
git -C "$SRC" commit --quiet -m unrelated-local-prelude
DIVERGED_BASE="$(git -C "$SRC" rev-parse HEAD)"
printf 'safe replay delta\n' > "$SRC/diverged-delta.txt"
git -C "$SRC" add diverged-delta.txt
git -C "$SRC" commit --quiet -m diverged-candidate-delta
DIVERGED_CANDIDATE="$(git -C "$SRC" rev-parse HEAD)"
(cd "$SRC" && "$INTEGRATOR" --candidate "$DIVERGED_CANDIDATE" --base "$DIVERGED_BASE" \
  --allow diverged-delta.txt --read a.txt --read b.txt --read checks/final.sh \
  --remote origin --ref refs/heads/main \
  --short-test 'test -s diverged-delta.txt && bash checks/final.sh') > "$TMP/diverged.json"
python3 - "$TMP/diverged.json" <<'PY'
import json, sys
d=json.load(open(sys.argv[1]))
assert d["status"] == "landed" and d["base_relation"] == "diverged", d
assert d["safety_gates"]["v4_secret_gate"] == "passed", d
PY
VERIFY_DIVERGED="$TMP/verify-diverged"
git clone --quiet --branch main "$ORIGIN" "$VERIFY_DIVERGED"
[[ "$(cat "$VERIFY_DIVERGED/diverged-delta.txt")" == "safe replay delta" ]]
[[ ! -e "$VERIFY_DIVERGED/local-only-before-base.txt" ]]

# Truly unrelated object graph is not a parallel branch and must fail closed.
UNRELATED="$TMP/unrelated"
git init --quiet "$UNRELATED"
git -C "$UNRELATED" config user.name Unrelated
git -C "$UNRELATED" config user.email unrelated@example.invalid
git -C "$UNRELATED" remote add origin "$ORIGIN"
printf 'other root\n' > "$UNRELATED/root.txt"
git -C "$UNRELATED" add root.txt
git -C "$UNRELATED" commit --quiet -m unrelated-root
UNRELATED_BASE="$(git -C "$UNRELATED" rev-parse HEAD)"
printf 'must reject\n' > "$UNRELATED/unrelated-delta.txt"
git -C "$UNRELATED" add unrelated-delta.txt
git -C "$UNRELATED" commit --quiet -m unrelated-delta
UNRELATED_CANDIDATE="$(git -C "$UNRELATED" rev-parse HEAD)"
set +e
(cd "$UNRELATED" && "$INTEGRATOR" --candidate "$UNRELATED_CANDIDATE" \
  --base "$UNRELATED_BASE" --allow unrelated-delta.txt --remote origin \
  --ref refs/heads/main --short-test 'test -s unrelated-delta.txt') > "$TMP/unrelated.json"
UNRELATED_RC=$?
set -e
[[ $UNRELATED_RC -eq 2 ]]
python3 - "$TMP/unrelated.json" <<'PY'
import json, sys
d=json.load(open(sys.argv[1])); assert d["status"] == "rejected_unrelated_history", d
PY
FINAL_COUNT="$(git --git-dir="$ORIGIN" rev-list --count refs/heads/main)"
[[ "$FINAL_COUNT" -eq 5 ]]
printf 'PASS integration controller: ancestor/diverged replay + unrelated reject + V4 secret gate + remote candidate\n'
