#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
TOOL="$ROOT/bin/cortex-candidate.sh"
TMP="$(mktemp -d /tmp/cortex-candidate-test.XXXXXX)"
trap 'rm -rf "$TMP"' EXIT
REPO="$TMP/repo"; REMOTE="$TMP/remote.git"
git init --quiet -b master "$REPO"
git init --quiet --bare "$REMOTE"
git -C "$REPO" config user.name fixture
git -C "$REPO" config user.email fixture@example.invalid
git -C "$REPO" config core.fsmonitor false
git -C "$REPO" config maintenance.auto false
git -C "$REPO" remote add origin "$REMOTE"
printf 'a0\n' > "$REPO/a.txt"; printf 'b0\n' > "$REPO/b.txt"
git -C "$REPO" add a.txt b.txt; git -C "$REPO" commit --quiet -m base
BASE="$(git -C "$REPO" rev-parse HEAD)"
printf 'a1\n' > "$REPO/a.txt"; git -C "$REPO" add a.txt; git -C "$REPO" commit --quiet -m candidate
CANDIDATE="$(git -C "$REPO" rev-parse HEAD)"

# Diverged source can be projected onto the latest canonical base without
# checkout, shared-index mutation, or carrying unrelated source history.
git -C "$REPO" checkout --quiet --detach "$BASE"
printf 'b-canonical\n' > "$REPO/b.txt"; git -C "$REPO" add b.txt
git -C "$REPO" commit --quiet -m canonical-newer
CANONICAL="$(git -C "$REPO" rev-parse HEAD)"
git -C "$REPO" checkout --quiet --detach "$CANDIDATE"
HEAD_BEFORE="$(git -C "$REPO" rev-parse HEAD)"
INDEX_BEFORE="$(git -C "$REPO" ls-files -s | shasum -a 256 | awk '{print $1}')"
(cd "$REPO" && "$TOOL" compose --source "$CANDIDATE" --base "$CANONICAL" \
  --allow a.txt --receipt "$TMP/compose.receipt.json") > "$TMP/compose.json"
cmp "$TMP/compose.json" "$TMP/compose.receipt.json"
COMPOSED="$(jq -r '.candidate_oid' "$TMP/compose.json")"
jq -e --arg base "$CANONICAL" '.status == "composed" and .base_oid == $base' "$TMP/compose.json" >/dev/null
[[ "$(git -C "$REPO" rev-parse "$COMPOSED^")" == "$CANONICAL" ]]
[[ "$(git -C "$REPO" show "$COMPOSED:a.txt")" == "a1" ]]
[[ "$(git -C "$REPO" show "$COMPOSED:b.txt")" == "b-canonical" ]]
[[ "$(git -C "$REPO" rev-parse HEAD)" == "$HEAD_BEFORE" ]]
[[ "$(git -C "$REPO" ls-files -s | shasum -a 256 | awk '{print $1}')" == "$INDEX_BEFORE" ]]
set +e
(cd "$REPO" && "$TOOL" compose --source "$CANDIDATE" --base "$CANONICAL" \
  --allow missing.txt) > "$TMP/compose-missing.json"
COMPOSE_MISSING_RC=$?
set -e
[[ $COMPOSE_MISSING_RC -eq 2 ]]
jq -e '.status == "rejected_scope"' "$TMP/compose-missing.json" >/dev/null

(cd "$REPO" && "$TOOL" validate --candidate "$CANDIDATE" --base "$BASE" --allow .) > "$TMP/invalid-root.json" 2>/dev/null || true
jq -e '.status == "rejected_scope"' "$TMP/invalid-root.json" >/dev/null
(cd "$REPO" && "$TOOL" validate --candidate "$CANDIDATE" --base "$BASE" --allow a.txt) > "$TMP/validate.json"
jq -e '.status == "validated"' "$TMP/validate.json" >/dev/null
(cd "$REPO" && "$TOOL" publish --attempt t1 --candidate "$CANDIDATE" --base "$BASE" \
  --allow a.txt --remote origin --receipt "$TMP/publish.receipt.json") > "$TMP/publish.json"
cmp "$TMP/publish.json" "$TMP/publish.receipt.json"
REF="refs/cortex/candidate/t1/$CANDIDATE"
[[ "$(git --git-dir="$REMOTE" rev-parse "$REF")" == "$CANDIDATE" ]]
# Idempotent republish is success and never rewrites the immutable ref.
(cd "$REPO" && "$TOOL" publish --attempt t1 --candidate "$CANDIDATE" --base "$BASE" --allow a.txt --remote origin) >/dev/null
(cd "$REPO" && "$TOOL" inspect --ref "$REF" --remote origin) > "$TMP/inspect.json"
jq -e --arg oid "$CANDIDATE" '.status == "found" and .remote_oid == $oid' "$TMP/inspect.json" >/dev/null

git -C "$REPO" checkout --quiet --detach "$BASE"
printf 'evil\n' > "$REPO/b.txt"; git -C "$REPO" add b.txt; git -C "$REPO" commit --quiet -m out-of-scope
EVIL="$(git -C "$REPO" rev-parse HEAD)"
set +e
(cd "$REPO" && "$TOOL" publish --attempt evil --candidate "$EVIL" --base "$BASE" --allow a.txt --remote origin) > "$TMP/evil.json"
RC=$?
set -e
[[ $RC -eq 2 ]]
jq -e '.status == "rejected_scope"' "$TMP/evil.json" >/dev/null
! git --git-dir="$REMOTE" show-ref --verify --quiet "refs/cortex/candidate/evil/$EVIL"

# Directory allow works without a trailing slash.
git -C "$REPO" checkout --quiet --detach "$BASE"
mkdir -p "$REPO/docs"; printf 'nested\n' > "$REPO/docs/nested.md"
git -C "$REPO" add docs/nested.md; git -C "$REPO" commit --quiet -m nested
NESTED="$(git -C "$REPO" rev-parse HEAD)"
(cd "$REPO" && "$TOOL" validate --candidate "$NESTED" --base "$BASE" --allow docs) >/dev/null

# Preoccupied immutable ref with a different OID is a hard collision, never overwritten.
COLLISION_REF="refs/cortex/candidate/collision/$CANDIDATE"
git --git-dir="$REMOTE" update-ref "$COLLISION_REF" "$BASE"
set +e
(cd "$REPO" && "$TOOL" publish --attempt collision --candidate "$CANDIDATE" --base "$BASE" --allow a.txt --remote origin) > "$TMP/collision.json"
COLLISION_RC=$?
(cd "$REPO" && "$TOOL" inspect --ref refs/cortex/candidate/missing --remote does-not-exist) > "$TMP/unknown.json"
UNKNOWN_RC=$?
set -e
[[ $COLLISION_RC -eq 2 && $UNKNOWN_RC -eq 2 ]]
jq -e '.status == "rejected_ref_collision"' "$TMP/collision.json" >/dev/null
jq -e '.status == "unknown"' "$TMP/unknown.json" >/dev/null
[[ "$(git --git-dir="$REMOTE" rev-parse "$COLLISION_REF")" == "$BASE" ]]
printf 'PASS candidate tool: exact compose, validate, immutable publish, idempotent inspect, scope rejection\n'
