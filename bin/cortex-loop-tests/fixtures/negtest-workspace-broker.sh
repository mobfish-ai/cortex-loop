#!/usr/bin/env bash
# Negative/contract test for linked sparse Cortex attempt workspaces.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
BROKER="$ROOT/bin/cortex-workspace.sh"
TMP="$(mktemp -d /tmp/cortex-workspace-test.XXXXXX)"
trap 'rm -rf "$TMP"' EXIT

repo="$TMP/repo"
remote="$TMP/remote.git"
workspaces="$TMP/workspaces"
git init --bare --quiet "$remote"
git init --quiet -b master "$repo"
git -C "$repo" config user.name fixture
git -C "$repo" config user.email fixture@example.invalid
git -C "$repo" config core.fsmonitor false
printf 'alpha\n' > "$repo/a.txt"
printf 'beta\n' > "$repo/b.txt"
dd if=/dev/urandom of="$repo/large.bin" bs=1048576 count=4 2>/dev/null
git -C "$repo" add a.txt b.txt large.bin
git -C "$repo" commit --quiet -m seed
git -C "$repo" remote add origin "$remote"
git -C "$repo" push --quiet -u origin master
base="$(git -C "$repo" rev-parse HEAD)"

export CORTEX_WORKSPACE_REPO_ROOT="$repo"
export CORTEX_WORKSPACE_ROOT="$workspaces"
export CORTEX_WORKSPACE_MIN_FREE_KB=1

# SIGKILL after lock publication leaves a fully owned lock; next same-host process
# recovers the dead PID without touching any other attempt.
CORTEX_WORKSPACE_FAULT_POINT=after_lock CORTEX_WORKSPACE_FAULT_SLEEP_SEC=60 \
  "$BROKER" create --attempt killed-lock --base "$base" --allow a.txt \
  >"$TMP/killed.out" 2>"$TMP/killed.err" &
killed_pid=$!
for _ in $(seq 1 100); do
  [[ -s "$workspaces/.locks/killed-lock.lock/pid" ]] && break
  sleep 0.02
done
[[ -s "$workspaces/.locks/killed-lock.lock/pid" ]]
# A live owner is fail-closed and its token is not replaced.
live_token="$(cat "$workspaces/.locks/killed-lock.lock/token")"
if "$BROKER" create --attempt killed-lock --base "$base" --allow a.txt >/dev/null 2>&1; then
  echo 'expected live attempt lock refusal' >&2
  exit 1
fi
[[ "$(cat "$workspaces/.locks/killed-lock.lock/token")" == "$live_token" ]]
kill -9 "$killed_pid"
wait "$killed_pid" 2>/dev/null || true
"$BROKER" create --attempt killed-lock --base "$base" --allow a.txt >/dev/null
[[ -f "$workspaces/killed-lock/a.txt" ]]
recovered_locks=("$workspaces"/.locks/.recovered.killed-lock.*/recovered_at)
[[ "${#recovered_locks[@]}" -eq 1 && -f "${recovered_locks[0]}" ]]
"$BROKER" release --attempt killed-lock >/dev/null
[[ ! -e "$workspaces/.locks/killed-lock.lock" ]]

# Foreign-host owners are never recovered from this machine.
mkdir "$workspaces/.locks/foreign-lock.lock"
printf '999999\n' > "$workspaces/.locks/foreign-lock.lock/pid"
printf 'some-other-host\n' > "$workspaces/.locks/foreign-lock.lock/hostname"
printf '1\n' > "$workspaces/.locks/foreign-lock.lock/started_at"
printf 'foreign-owner-token\n' > "$workspaces/.locks/foreign-lock.lock/token"
if "$BROKER" create --attempt foreign-lock --base "$base" --allow a.txt >/dev/null 2>&1; then
  echo 'expected foreign attempt lock refusal' >&2
  exit 1
fi
[[ "$(cat "$workspaces/.locks/foreign-lock.lock/token")" == foreign-owner-token ]]

# Every failure after worktree add rolls back only that attempt's worktree, branch,
# and partial manifest. Main tree and unrelated attempts remain untouched.
if CORTEX_WORKSPACE_FAULT_POINT=after_worktree_add \
  "$BROKER" create --attempt rollback-add --base "$base" --allow a.txt \
  >/dev/null 2>&1; then
  echo 'expected after_worktree_add injection failure' >&2
  exit 1
fi
[[ ! -e "$workspaces/rollback-add" && ! -e "$workspaces/.state/rollback-add.json" ]]
if git -C "$repo" show-ref --verify --quiet refs/heads/cortex/attempt/rollback-add; then
  echo 'rollback-add branch survived rollback' >&2
  exit 1
fi

if CORTEX_WORKSPACE_FAULT_POINT=before_manifest \
  "$BROKER" create --attempt rollback-manifest --base "$base" --allow a.txt \
  >/dev/null 2>&1; then
  echo 'expected before_manifest injection failure' >&2
  exit 1
fi
[[ ! -e "$workspaces/rollback-manifest" \
  && ! -e "$workspaces/.state/rollback-manifest.json" ]]
if git -C "$repo" show-ref --verify --quiet refs/heads/cortex/attempt/rollback-manifest; then
  echo 'rollback-manifest branch survived rollback' >&2
  exit 1
fi

# SIGKILL after worktree creation is recovered on the next create: only the exact
# reserved attempt worktree/branch is rolled back, then the same attempt is recreated.
CORTEX_WORKSPACE_FAULT_POINT=after_worktree_add CORTEX_WORKSPACE_FAULT_MODE=sleep \
  CORTEX_WORKSPACE_FAULT_SLEEP_SEC=60 \
  "$BROKER" create --attempt killed-partial --base "$base" --allow a.txt \
  >"$TMP/killed-partial.out" 2>"$TMP/killed-partial.err" &
killed_partial_pid=$!
for _ in $(seq 1 150); do
  [[ -d "$workspaces/killed-partial" \
    && -s "$workspaces/.locks/killed-partial.lock/pid" ]] && break
  sleep 0.02
done
[[ -d "$workspaces/killed-partial" ]]
kill -9 "$killed_partial_pid"
wait "$killed_partial_pid" 2>/dev/null || true
"$BROKER" create --attempt killed-partial --base "$base" --allow a.txt >/dev/null
[[ -f "$workspaces/killed-partial/a.txt" ]]
"$BROKER" release --attempt killed-partial >/dev/null

"$BROKER" create --attempt attempt-a --base "$base" --allow a.txt >/dev/null
"$BROKER" create --attempt attempt-b --base "$base" --allow b.txt >/dev/null
wa="$workspaces/attempt-a"
wb="$workspaces/attempt-b"

[[ -f "$wa/a.txt" && ! -e "$wa/b.txt" && ! -e "$wa/large.bin" ]]
[[ -f "$wb/b.txt" && ! -e "$wb/a.txt" && ! -e "$wb/large.bin" ]]

main_objects="$(git -C "$repo" rev-parse --path-format=absolute --git-path objects)"
objects_a="$(git -C "$wa" rev-parse --path-format=absolute --git-path objects)"
objects_b="$(git -C "$wb" rev-parse --path-format=absolute --git-path objects)"
[[ "$main_objects" == "$objects_a" && "$main_objects" == "$objects_b" ]]

main_index="$(git -C "$repo" rev-parse --path-format=absolute --git-path index)"
index_a="$(git -C "$wa" rev-parse --git-path index)"
index_b="$(git -C "$wb" rev-parse --git-path index)"
[[ "$main_index" != "$index_a" && "$main_index" != "$index_b" && "$index_a" != "$index_b" ]]
main_index_before="$(git hash-object "$main_index")"
main_a_before="$(git -C "$repo" hash-object a.txt)"
main_b_before="$(git -C "$repo" hash-object b.txt)"

(
  printf 'attempt-a\n' >> "$wa/a.txt"
  git -C "$wa" add a.txt
  git -C "$wa" -c user.name=fixture -c user.email=fixture@example.invalid commit --quiet -m attempt-a
) &
pid_a=$!
(
  printf 'attempt-b\n' >> "$wb/b.txt"
  git -C "$wb" add b.txt
  git -C "$wb" -c user.name=fixture -c user.email=fixture@example.invalid commit --quiet -m attempt-b
) &
pid_b=$!
wait "$pid_a"
wait "$pid_b"

[[ "$main_index_before" == "$(git hash-object "$main_index")" ]]
[[ "$main_a_before" == "$(git -C "$repo" hash-object a.txt)" ]]
[[ "$main_b_before" == "$(git -C "$repo" hash-object b.txt)" ]]
[[ -z "$(git -C "$repo" status --porcelain=v1)" ]]
[[ -z "$(git -C "$wa" status --porcelain=v1)" ]]
[[ -z "$(git -C "$wb" status --porcelain=v1)" ]]
[[ "$(git -C "$wa" rev-parse HEAD)" != "$base" ]]
[[ "$(git -C "$wb" rev-parse HEAD)" != "$base" ]]

objects_kb="$(du -sk "$repo/.git/objects" | awk '{print $1}')"
wa_kb="$(du -sk "$wa" | awk '{print $1}')"
wb_kb="$(du -sk "$wb" | awk '{print $1}')"
((wa_kb * 4 < objects_kb))
((wb_kb * 4 < objects_kb))

# Dirty workspaces cannot be released; the explicit release call is the only remover.
printf 'dirty\n' >> "$wa/a.txt"
if "$BROKER" release --attempt attempt-a >/dev/null 2>&1; then
  echo 'expected dirty release refusal' >&2
  exit 1
fi
[[ -d "$wa" ]]
git -C "$wa" restore -- a.txt

candidate_a="$("$BROKER" release --attempt attempt-a)"
candidate_b="$("$BROKER" release --attempt attempt-b)"
[[ ! -e "$wa" && ! -e "$wb" ]]
[[ "$(jq -r .state "$workspaces/.state/attempt-a.json")" == released ]]
[[ "$(jq -r .candidate_oid "$workspaces/.state/attempt-a.json")" == "$candidate_a" ]]
[[ "$(jq -r .candidate_oid "$workspaces/.state/attempt-b.json")" == "$candidate_b" ]]
git -C "$repo" cat-file -e "$candidate_a^{commit}"
git -C "$repo" cat-file -e "$candidate_b^{commit}"

# Disk gate runs before worktree creation.
export CORTEX_WORKSPACE_MIN_FREE_KB=999999999999
if "$BROKER" create --attempt disk-gated --base "$base" --allow a.txt >/dev/null 2>&1; then
  echo 'expected disk gate refusal' >&2
  exit 1
fi
[[ ! -e "$workspaces/disk-gated" ]]
export CORTEX_WORKSPACE_MIN_FREE_KB=1

# Concurrent creators for one attempt: exactly one wins the atomic reservation.
set +e
"$BROKER" create --attempt attempt-race --base "$base" --allow a.txt \
  >"$TMP/race-a.out" 2>"$TMP/race-a.err" &
race_a=$!
"$BROKER" create --attempt attempt-race --base "$base" --allow a.txt \
  >"$TMP/race-b.out" 2>"$TMP/race-b.err" &
race_b=$!
wait "$race_a"; rc_a=$?
wait "$race_b"; rc_b=$?
set -e
(( (rc_a == 0 && rc_b != 0) || (rc_a != 0 && rc_b == 0) ))
[[ "$(jq -r .state "$workspaces/.state/attempt-race.json")" == active ]]
"$BROKER" release --attempt attempt-race >/dev/null
[[ ! -e "$workspaces/.locks/attempt-race.lock" ]]
if compgen -G "$workspaces/.locks/attempt-race.lock/.owner.*" >/dev/null; then
  echo 'concurrent loser polluted live attempt lock' >&2
  exit 1
fi

# Same attempt is atomically reserved and cannot be recreated after release.
if "$BROKER" create --attempt attempt-a --base "$base" --allow a.txt >/dev/null 2>&1; then
  echo 'expected duplicate attempt refusal' >&2
  exit 1
fi
[[ "$(jq -r .state "$workspaces/.state/attempt-a.json")" == released ]]

printf 'PASS workspace broker: sparse linked objects, isolated indexes, concurrent commits, guarded release\n'
