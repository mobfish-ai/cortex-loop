#!/usr/bin/env bash
# Contract tests for cortex-attempt-reconcile.sh 落地判据扩展（2026-10-11）。
# 背景：ancestry 判据漏掉"内容已落地但 SHA 不同"的 attempt（isolate 重放 /
# landed twin 附带额外内容）→ 永久跳过。新增内容级证明：manifest.allowed_paths
# 的 blob 与 master 逐一相等 ⇒ 不可能含唯一内容。
#
# 红绿门（反向验证）：把 cortex-attempt-reconcile.sh 换回 HEAD 版本，
# 本夹具必须变红（CONTENT_LANDED 用例判 unlanded）。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
SWEEPER="$ROOT/bin/cortex-attempt-reconcile.sh"
TMP="$(mktemp -d /tmp/cortex-reconcile-content-test.XXXXXX)"
trap 'rm -rf "$TMP"' EXIT

repo="$TMP/repo"
wts="$TMP/worktrees/cortex"     # 必须以 /cortex 结尾：sweeper 只碰 */cortex/iso* worktree
git init --quiet -b master "$repo"
git -C "$repo" config user.name fixture
git -C "$repo" config user.email fixture@example.invalid
git -C "$repo" config core.fsmonitor false
printf 'alpha\n' > "$repo/a.txt"
# 模拟真实仓布局：sweeper 的 A/B 清理路径都通过 `$REPO/bin/cortex-workspace.sh` 调用；
# 夹具仓若缺这个文件，两条路径都会失败 → 用例变成"假通过"（2026-10-11 自查发现）。
mkdir -p "$repo/bin"
cp "$ROOT/bin/cortex-workspace.sh" "$repo/bin/cortex-workspace.sh"
git -C "$repo" add a.txt bin/cortex-workspace.sh
git -C "$repo" commit --quiet -m seed
base="$(git -C "$repo" rev-parse HEAD)"

# master 前进：a.txt 变 v2（这是"落地 twin"，与分支提交 SHA 不同）
printf 'v2\n' > "$repo/a.txt"
git -C "$repo" commit --quiet -am landed-v2
printf 'beta\n' > "$repo/b.txt"
git -C "$repo" add b.txt
git -C "$repo" commit --quiet -m add-b

mkdir -p "$wts"

# 分支 1：内容已落地 —— 从 base 起，内容与 master 的 a.txt 相同，但历史不同
git -C "$repo" branch cortex/attempt/isoCL "$base"
git -C "$repo" worktree add --quiet "$wts/isoCL" cortex/attempt/isoCL
( cd "$wts/isoCL" && printf 'v2\n' > a.txt && git commit --quiet -am same-content-diff-sha )

# 分支 2：对照 —— a.txt=v3 在 master 上不存在（真唯一内容）
git -C "$repo" branch cortex/attempt/isoUL "$base"
git -C "$repo" worktree add --quiet "$wts/isoUL" cortex/attempt/isoUL
( cd "$wts/isoUL" && printf 'v3\n' > a.txt && git commit --quiet -am unique-v3 )

# manifest（真实形态：<worktree root>/.state/<attempt>.json）
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
assert_ok() {  # 断言命令成功（存在性等正向断言）
  local label="$1"; shift
  if "$@"; then echo "PASS $label"; pass=$((pass+1))
  else echo "FAIL $label" >&2; fail=$((fail+1)); fi
}

run_json() { ( cd "$repo" && bash "$SWEEPER" --json 2>/dev/null ); }
jget() { printf '%s' "$1" | jq -r ".$2"; }

# 前置：确认两条分支都是 master 的"非祖先"（否则夹具没测到目标场景）
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

# 负例：拿掉 manifest（无 allowed_paths 可证）→ 内容级证明必须失效，不得凭猜测放行
rm -f "$wts/.state/isoCL.json"
j2="$(run_json)"
assert_eq "without manifest, content proof is withdrawn" "0" "$(jget "$j2" worktree_cleanup_targets)"
assert_eq "without manifest, both worktrees kept" "2" "$(jget "$j2" unlanded_skip)"

# 负例：manifest 存在但 allowed_paths 指向 master 上不存在的路径 → 保守判未落地
jq -n '{state:"active",attempt:"isoCL",allowed_paths:["nope.txt"]}' > "$wts/.state/isoCL.json"
j3="$(run_json)"
assert_eq "unresolvable allowed_path is conservative" "0" "$(jget "$j3" worktree_cleanup_targets)"

# --- (d) 加固反例（反例驱动）：allowed_paths 与 master 逐一相等，但 allowed_paths
#     之外另有唯一内容。第 1 步（blob 相等）会通过 → 必须由第 2 步（改动集合
#     ⊆ allowed_paths）判未落地。缺第 2 步时本用例变红 = 唯一内容会被误拆。
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

# --- (e) P1（2026-10-11 独立审计）：A 路径被域身份闸拒绝后，B 路径不得无门拆除 ---
# 带 .cortex-domain-lease 的 iso worktree：A 的 `abandon --purge` 会被域闸拒绝，
# 旧版随即回退进**没有域闸**的 B 路径把 worktree+branch 删掉（审计实测 `✅ B isoLease`）。
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
