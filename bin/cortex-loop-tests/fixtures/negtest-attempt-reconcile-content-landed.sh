#!/usr/bin/env bash
# Contract tests for the cortex-attempt-reconcile.sh landing-criterion extension (2026-10-11).
# Background: the ancestry criterion missed attempts whose content had landed under a different SHA
# (isolate replay / a landed twin that carries extra content) -> they were skipped forever.
# New content-level proof: every blob in manifest.allowed_paths equals master -> no unique content.
#
# Red/green gate (reverse check): put cortex-attempt-reconcile.sh back to the HEAD version
# and this fixture must go red (the CONTENT_LANDED case is judged unlanded).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
SWEEPER="$ROOT/bin/cortex-attempt-reconcile.sh"
TMP="$(mktemp -d /tmp/cortex-reconcile-content-test.XXXXXX)"
trap 'rm -rf "$TMP"' EXIT

repo="$TMP/repo"
wts="$TMP/worktrees/cortex"     # must end in /cortex: the sweeper only touches */cortex/iso* worktrees
git init --quiet -b master "$repo"
git -C "$repo" config user.name fixture
git -C "$repo" config user.email fixture@example.invalid
git -C "$repo" config core.fsmonitor false
printf 'alpha\n' > "$repo/a.txt"
# Mirror a real repo layout: both sweeper cleanup paths A and B call `$REPO/bin/cortex-workspace.sh`.
# If the fixture repo lacks that file, both paths fail and the case becomes a false pass (found 2026-10-11).
mkdir -p "$repo/bin"
cp "$ROOT/bin/cortex-workspace.sh" "$repo/bin/cortex-workspace.sh"
git -C "$repo" add a.txt bin/cortex-workspace.sh
git -C "$repo" commit --quiet -m seed
base="$(git -C "$repo" rev-parse HEAD)"

# master moves forward: a.txt becomes v2 (the landed twin; its commit SHA differs from the branch)
printf 'v2\n' > "$repo/a.txt"
git -C "$repo" commit --quiet -am landed-v2
printf 'beta\n' > "$repo/b.txt"
git -C "$repo" add b.txt
git -C "$repo" commit --quiet -m add-b

mkdir -p "$wts"

# Branch 1: content has landed -- from base, a.txt matches master, but the history differs
git -C "$repo" branch cortex/attempt/isoCL "$base"
git -C "$repo" worktree add --quiet "$wts/isoCL" cortex/attempt/isoCL
( cd "$wts/isoCL" && printf 'v2\n' > a.txt && git commit --quiet -am same-content-diff-sha )

# Branch 2: control -- a.txt=v3 does not exist on master (truly unique content)
git -C "$repo" branch cortex/attempt/isoUL "$base"
git -C "$repo" worktree add --quiet "$wts/isoUL" cortex/attempt/isoUL
( cd "$wts/isoUL" && printf 'v3\n' > a.txt && git commit --quiet -am unique-v3 )

# manifest (real shape: <worktree root>/.state/<attempt>.json)
mkdir -p "$wts/.state"
jq -n '{state:"active",attempt:"isoCL",allowed_paths:["a.txt"]}' > "$wts/.state/isoCL.json"
jq -n '{state:"active",attempt:"isoUL",allowed_paths:["a.txt"]}' > "$wts/.state/isoUL.json"

export CORTEX_WORKSPACE_ROOT="$wts"

pass=0
fail=0
assert_eq() {
  local label="$1" want="$2" got="$3"
  if [ "$want" = "$got" ]; then echo "PASS $label ($got)"; pass=$((pass+1))
  else echo "FAIL $label (want=$want got=$got)" >&2; fail=$((fail+1)); fi
}
assert_ok() {  # assert the command succeeds (positive checks such as existence)
  local label="$1"; shift
  if "$@"; then echo "PASS $label"; pass=$((pass+1))
  else echo "FAIL $label" >&2; fail=$((fail+1)); fi
}

run_json() { ( cd "$repo" && bash "$SWEEPER" --json 2>/dev/null ); }
jget() { printf '%s' "$1" | jq -r ".$2"; }

# Precondition: both branches are non-ancestors of master (otherwise the fixture misses the target case)
assert_eq "isoCL is non-ancestor" "no" \
  "$(git -C "$repo" merge-base --is-ancestor cortex/attempt/isoCL master && echo yes || echo no)"
assert_eq "isoCL blob equals master" "$(git -C "$repo" rev-parse master:a.txt)" \
  "$(git -C "$repo" rev-parse cortex/attempt/isoCL:a.txt)"
assert_eq "isoUL blob differs from master" "no" \
  "$([ "$(git -C "$repo" rev-parse master:a.txt)" = "$(git -C "$repo" rev-parse cortex/attempt/isoUL:a.txt)" ] && echo yes || echo no)"

j="$(run_json)"
assert_eq "content-landed worktree is a cleanup target" "1" "$(jget "$j" worktree_cleanup_targets)"
assert_eq "unique-content worktree is kept (unlanded)" "1" "$(jget "$j" unlanded_skip)"
assert_eq "manifest resolved at real state path (A-path reachable)" "1" "$(jget "$j" active_manifest_targets)"
assert_eq "no branch-only deletable (isoCL has worktree, isoUL unlanded)" "0" "$(jget "$j" branch_only_deletable)"

# Negative: remove the manifest (no allowed_paths to prove) -> content-level proof must fail; do not guess a pass
rm -f "$wts/.state/isoCL.json"
j2="$(run_json)"
assert_eq "without manifest, content proof is withdrawn" "0" "$(jget "$j2" worktree_cleanup_targets)"
assert_eq "without manifest, both worktrees kept" "2" "$(jget "$j2" unlanded_skip)"

# Negative: manifest exists but allowed_paths points at a path missing on master -> conservatively unlanded
jq -n '{state:"active",attempt:"isoCL",allowed_paths:["nope.txt"]}' > "$wts/.state/isoCL.json"
j3="$(run_json)"
assert_eq "unresolvable allowed_path is conservative" "0" "$(jget "$j3" worktree_cleanup_targets)"

# --- (d) Hardening counterexample (counterexample-driven): allowed_paths blobs each equal master,
#     but unique content exists outside allowed_paths. Step 1 (blob equality) passes -> step 2
#     (the change set is a subset of allowed_paths) must judge it unlanded. Without step 2 this
#     case goes red = unique content would be torn down by mistake.
repo2="$TMP/repo2"
wts2="$TMP/worktrees2/cortex"
git init --quiet -b master "$repo2"
git -C "$repo2" config user.name fixture
git -C "$repo2" config user.email fixture@example.invalid
git -C "$repo2" config core.fsmonitor false
printf 'alpha\n' > "$repo2/a.txt"
mkdir -p "$repo2/bin"
cp "$ROOT/bin/cortex-workspace.sh" "$repo2/bin/cortex-workspace.sh"
git -C "$repo2" add a.txt bin/cortex-workspace.sh
git -C "$repo2" commit --quiet -m seed
base2="$(git -C "$repo2" rev-parse HEAD)"
printf 'v2\n' > "$repo2/a.txt"
git -C "$repo2" commit --quiet -am landed-v2
git -C "$repo2" branch cortex/attempt/isoScope "$base2"
mkdir -p "$wts2"
git -C "$repo2" worktree add --quiet "$wts2/isoScope" cortex/attempt/isoScope
( cd "$wts2/isoScope" && printf 'v2\n' > a.txt && printf 'unique-extra\n' > extra.txt \
  && git add extra.txt && git commit --quiet -am scope-violation )
mkdir -p "$wts2/.state"
jq -n '{state:"active",attempt:"isoScope",allowed_paths:["a.txt"]}' > "$wts2/.state/isoScope.json"

assert_eq "scope-violation precondition: allowed path equals master" "yes" \
  "$([ "$(git -C "$repo2" rev-parse cortex/attempt/isoScope:a.txt)" = "$(git -C "$repo2" rev-parse master:a.txt)" ] && echo yes || echo no)"
assert_eq "scope-violation precondition: extra file is unique" "no" \
  "$(git -C "$repo2" cat-file -e master:extra.txt 2>/dev/null && echo yes || echo no)"
j4="$( cd "$repo2" && CORTEX_WORKSPACE_ROOT="$wts2" bash "$SWEEPER" --json 2>/dev/null )"
assert_eq "out-of-scope unique content blocks cleanup" "0" "$(jget "$j4" worktree_cleanup_targets)"
assert_eq "out-of-scope attempt kept as unlanded" "1" "$(jget "$j4" unlanded_skip)"

# --- (e) P1 (independent audit, 2026-10-11): after path A is refused by the domain-identity gate, path B must not tear down without a gate ---
# An iso worktree with .cortex-domain-lease: A's `abandon --purge` is refused by the domain gate.
# The old code then fell back into path B, which has no domain gate, and deleted the worktree and branch (audit observed `B isoLease`).
git -C "$repo" branch cortex/attempt/isoLease "$base"
git -C "$repo" worktree add --quiet "$wts/isoLease" cortex/attempt/isoLease
( cd "$wts/isoLease" && printf 'v2\n' > a.txt && git commit --quiet -am lease-landed )
printf 'lease\n' > "$wts/isoLease/.cortex-domain-lease"
jq -n '{state:"active",attempt:"isoLease",allowed_paths:["a.txt"]}' > "$wts/.state/isoLease.json"
( cd "$repo" && CORTEX_WORKSPACE_ROOT="$wts" CORTEX_WORKSPACE_ABANDON_PATCH_DIR="$TMP/patches" \
  bash "$SWEEPER" --apply >/dev/null 2>&1 ) || true
assert_ok "lease-marked worktree survives --apply (domain gate not bypassed)" test -d "$wts/isoLease"
assert_ok "lease-marked branch survives --apply" \
  git -C "$repo" show-ref --verify --quiet refs/heads/cortex/attempt/isoLease

echo "----"
echo "pass=$pass fail=$fail tmp=$TMP"
[[ "$fail" -eq 0 ]]
