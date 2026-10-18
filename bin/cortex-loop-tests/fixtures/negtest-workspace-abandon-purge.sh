#!/usr/bin/env bash
# Contract tests for cortex-workspace.sh abandon --purge safety net.
# (a) tracked uncommitted edit must land in patch
# (b) brand-new untracked file must land in patch (sparse + add -N --sparse)

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
BROKER="$ROOT/bin/cortex-workspace.sh"
TMP="$(mktemp -d /tmp/cortex-abandon-purge-test.XXXXXX)"
trap 'rm -rf "$TMP"' EXIT

repo="$TMP/repo"
remote="$TMP/remote.git"
workspaces="$TMP/workspaces"
patches="$TMP/patches"
git init --bare --quiet "$remote"
git init --quiet -b master "$repo"
git -C "$repo" config user.name fixture
git -C "$repo" config user.email fixture@example.invalid
git -C "$repo" config core.fsmonitor false
printf 'alpha\n' > "$repo/a.txt"
printf 'beta\n' > "$repo/b.txt"
# §6.2 gate（attempt 必须物化 versioned hooks dir，否则 create fail-closed）落地晚于本
# fixture → 夹具此前长期跑不起来（2026-10-11 实测 HEAD 版本同样 fail）。种子化修复。
mkdir -p "$repo/work-studio/devops/dotfiles/git-hooks"
printf '#!/bin/sh\nexit 0\n' > "$repo/work-studio/devops/dotfiles/git-hooks/pre-commit"
chmod +x "$repo/work-studio/devops/dotfiles/git-hooks/pre-commit"
git -C "$repo" add a.txt b.txt work-studio/devops/dotfiles/git-hooks/pre-commit
git -C "$repo" commit --quiet -m seed
git -C "$repo" remote add origin "$remote"
git -C "$repo" push --quiet -u origin master
base="$(git -C "$repo" rev-parse HEAD)"

export CORTEX_WORKSPACE_REPO_ROOT="$repo"
export CORTEX_WORKSPACE_ROOT="$workspaces"
export CORTEX_WORKSPACE_MIN_FREE_KB=1
export CORTEX_WORKSPACE_ABANDON_PATCH_DIR="$patches"

pass=0
fail=0
assert_ok() {
  local label="$1"; shift
  if "$@"; then echo "PASS $label"; pass=$((pass+1))
  else echo "FAIL $label" >&2; fail=$((fail+1)); fi
}
assert_fail() {  # 断言目标命令必须失败（负例：ref 应已不存在等）
  local label="$1"; shift
  if "$@"; then echo "FAIL $label" >&2; fail=$((fail+1))
  else echo "PASS $label"; pass=$((pass+1)); fi
}

# --- (a) tracked uncommitted edit ---
"$BROKER" create --attempt purge-tracked --base "$base" --allow a.txt --allow b.txt >/dev/null
wa="$workspaces/purge-tracked"
printf 'tracked-edit-marker-AAA\n' >> "$wa/a.txt"
out_a="$("$BROKER" abandon --attempt purge-tracked --reason test-a --purge --discard-unique)"
assert_ok "tracked purge removes worktree" test ! -e "$wa"
assert_ok "tracked purge archives manifest" test -f "$workspaces/.state/abandoned/purge-tracked.json"
assert_ok "tracked patch exists" test -s "$patches/purge-tracked.patch"
assert_ok "tracked patch contains edit marker" grep -qF 'tracked-edit-marker-AAA' "$patches/purge-tracked.patch"
assert_ok "tracked out mentions purged=1" grep -q 'purged=1' <<<"$out_a"
# Same attempt id can be recreated after purge archive
"$BROKER" create --attempt purge-tracked --base "$base" --allow a.txt >/dev/null
assert_ok "recreate after purge-tracked works" test -d "$workspaces/purge-tracked"
"$BROKER" abandon --attempt purge-tracked --reason cleanup --purge --discard-unique >/dev/null

# --- (b) brand-new untracked file under sparse allow ---
"$BROKER" create --attempt purge-untracked --base "$base" --allow a.txt --allow b.txt >/dev/null
wb="$workspaces/purge-untracked"
printf 'untracked-secret-BBB-line\n' > "$wb/new-untracked.txt"
# Without --sparse this would silently omit the file from intent-to-add on sparse wt.
out_b="$("$BROKER" abandon --attempt purge-untracked --reason test-b --purge --discard-unique)"
assert_ok "untracked purge removes worktree" test ! -e "$wb"
assert_ok "untracked patch exists" test -s "$patches/purge-untracked.patch"
assert_ok "untracked patch names file" grep -qF 'new-untracked.txt' "$patches/purge-untracked.patch"
assert_ok "untracked patch contains file body" grep -qF 'untracked-secret-BBB-line' "$patches/purge-untracked.patch"
assert_ok "untracked out mentions purged=1" grep -q 'purged=1' <<<"$out_b"

# --- without --purge: disk remains ---
"$BROKER" create --attempt no-purge --base "$base" --allow a.txt >/dev/null
wc="$workspaces/no-purge"
"$BROKER" abandon --attempt no-purge --reason keep-disk >/dev/null
assert_ok "no-purge keeps worktree on disk" test -d "$wc"
assert_ok "no-purge marks abandoned" test "$(jq -r .state "$workspaces/.state/no-purge.json")" = abandoned

# --- (c) 2026-10-11: abandoned 态可被 --purge 补完（此前无任何入口，只能人工 rm） ---
printf 'resume-marker-CCC\n' >> "$wc/a.txt"
set +e
err_z="$("$BROKER" abandon --attempt no-purge --reason again 2>&1)"
rc_z=$?
set -e
assert_ok "abandoned re-abandon without --purge still refused" test "$rc_z" -ne 0
assert_ok "abandoned refusal points at --purge" grep -qi 'already abandoned' <<<"$err_z"
assert_ok "abandoned worktree untouched after refusal" test -d "$wc"
out_z="$("$BROKER" abandon --attempt no-purge --reason complete --purge --discard-unique)"
assert_ok "abandoned --purge completes worktree removal" test ! -e "$wc"
assert_ok "abandoned --purge archives manifest" test -f "$workspaces/.state/abandoned/no-purge.json"
assert_ok "abandoned --purge safety patch captures edit" grep -qF 'resume-marker-CCC' "$patches/no-purge.patch"
assert_fail "abandoned --purge deletes branch" \
  git -C "$repo" show-ref --verify --quiet refs/heads/cortex/attempt/no-purge
assert_ok "abandoned --purge output purged=1" grep -q 'purged=1' <<<"$out_z"

# --- (d) 2026-10-11 独立审计 P0：含 NUL 的二进制未跟踪内容必须**真的**进补丁 ---
# 旧门靠 `awk 'NF{print;exit}'` 取样本，遇 NUL 截断成前缀（本例截成 "nul"），该前缀命中
# diff 头部的 /dev/null → 门误判通过、worktree 被删、内容不可恢复（审计实测 rc=0 丢内容）。
# 新门 = `git diff --binary` + 重放证明：内容必须能从补丁逐字节还原。
"$BROKER" create --attempt purge-binary --base "$base" --allow a.txt >/dev/null
wbin="$workspaces/purge-binary"
printf 'nul\0body-tail-UNIQUE\n' > "$wbin/f.bin"
cp "$wbin/f.bin" "$TMP/f.bin.orig"
out_bin="$("$BROKER" abandon --attempt purge-binary --reason test-binary --purge --discard-unique 2>&1)"
assert_ok "binary purge removes worktree" test ! -e "$wbin"
assert_ok "binary patch carries git binary payload" grep -q 'GIT binary patch' "$patches/purge-binary.patch"
# 独立还原（不经本工具的门）：直接用 git apply 把补丁打到 base 检出再逐字节比对
scratch="$TMP/apply-check"
git -C "$repo" worktree add --quiet --detach "$scratch" "$base"
git -C "$scratch" apply --binary "$patches/purge-binary.patch" 2>/dev/null || true
assert_ok "binary content recoverable byte-exact from patch" cmp -s "$TMP/f.bin.orig" "$scratch/f.bin"

# --- (e) 审计 P2：worktree 带外消失后仍能补完；分支是否删仍由同一判据决定 ---
mk_absent() {  # $1=attempt  $2=marker：造"已提交(唯一内容) + worktree 带外删除"的形态
  "$BROKER" create --attempt "$1" --base "$base" --allow a.txt >/dev/null
  local w="$workspaces/$1"
  printf '%s\n' "$2" >> "$w/a.txt"
  git -C "$w" commit --quiet -am "$2"
  git -C "$repo" worktree remove --force "$w"
}
mk_absent purge-absent keep-branch-marker
assert_ok "absent-worktree precondition (dir gone)" test ! -e "$workspaces/purge-absent"
out_abs="$("$BROKER" abandon --attempt purge-absent --reason audit-p2 --purge 2>&1)"
assert_ok "absent-worktree purge reports purged" grep -q 'purged=1' <<<"$out_abs"
assert_ok "absent-worktree manifest archived" test -f "$workspaces/.state/abandoned/purge-absent.json"
assert_ok "absent-worktree branch KEPT (has unique commits, no --discard-unique)" \
  git -C "$repo" show-ref --verify --quiet refs/heads/cortex/attempt/purge-absent

mk_absent purge-absent-drop drop-marker
out_abs2="$("$BROKER" abandon --attempt purge-absent-drop --reason audit-p2-drop --purge --discard-unique 2>&1)"
assert_ok "absent-worktree + --discard-unique reports purged" grep -q 'purged=1' <<<"$out_abs2"
assert_fail "absent-worktree + --discard-unique removes branch" \
  git -C "$repo" show-ref --verify --quiet refs/heads/cortex/attempt/purge-absent-drop

# --- (f) 2026-10-12 工具层根治：全 D 型（worktree 文件整体丢失）→ 落指针清单，不抄全量 ---
# 现状：一个 4.0G 补丁其实就是「仓库自身内容」的副本（53,268 个纯删除块），
# 压缩/上传都不可行。指针清单（路径 + pre-image blob + size）几十 KB 即可等价保住，
# 且**可还原**——本用例的还原断言就是"安全网没漏"的证明。
"$BROKER" create --attempt purge-alld --base "$base" --allow a.txt --allow b.txt >/dev/null
wl="$workspaces/purge-alld"
rm -f "$wl/a.txt" "$wl/b.txt"          # 模拟烂尾检出：已跟踪文件从磁盘消失
assert_ok "all-D precondition (tracked files missing)" test ! -f "$wl/a.txt"
out_alld="$("$BROKER" abandon --attempt purge-alld --reason test-alld --purge 2>&1)"
assert_ok "all-D purge completes" grep -q 'purged=1' <<<"$out_alld"
assert_ok "pointer manifest written" test -s "$patches/purge-alld.patch.pointers"
assert_fail "no full-size patch left behind" test -s "$patches/purge-alld.patch"
assert_ok "manifest records entry count" grep -q 'entries=2' "$patches/purge-alld.patch.pointers"
dest_alld="$TMP/restore-alld"
"$BROKER" patch-pointer-restore --patch "$patches/purge-alld.patch.pointers" --dest "$dest_alld" >/dev/null
assert_ok "restore reproduces a.txt byte-exact" cmp -s <(git -C "$repo" show "$base:a.txt") "$dest_alld/a.txt"
assert_ok "restore reproduces b.txt byte-exact" cmp -s <(git -C "$repo" show "$base:b.txt") "$dest_alld/b.txt"

# 反例：含新增内容的补丁绝不能指针化（否则真会丢字节）
ww="$TMP/nonpointer"
"$BROKER" create --attempt purge-mixed --base "$base" --allow a.txt >/dev/null
wm="$workspaces/purge-mixed"
printf 'brand-new-unique-payload-XYZ\n' > "$wm/new.txt"
out_mix="$("$BROKER" abandon --attempt purge-mixed --reason test-mixed --purge 2>&1)"
assert_ok "mixed patch purge still completes via replay proof" grep -q 'purged=1' <<<"$out_mix"
assert_ok "mixed patch kept as full patch (not pointer-ized)" test -s "$patches/purge-mixed.patch"
assert_fail "mixed patch produced no pointer manifest" test -f "$patches/purge-mixed.patch.pointers"
assert_ok "mixed full patch preserves the unique payload" grep -qF 'brand-new-unique-payload-XYZ' "$patches/purge-mixed.patch"

# --- P0-4: domain-named attempt refused without override ---
"$BROKER" create --attempt cortex-domain-faketest --base "$base" --allow a.txt >/dev/null
wd="$workspaces/cortex-domain-faketest"
set +e
err_d="$("$BROKER" abandon --attempt cortex-domain-faketest --reason domain-gate --purge --discard-unique 2>&1)"
rc_d=$?
set -e
assert_ok "domain-named purge refused (nonzero)" test "$rc_d" -ne 0
assert_ok "domain-named purge error mentions domain" grep -qi 'persistent domain\|cortex-domain\|i-know-this-is-a-domain' <<<"$err_d"
assert_ok "domain-named worktree still on disk after refuse" test -d "$wd"
assert_ok "domain-named branch still exists after refuse" \
  git -C "$repo" show-ref --verify --quiet refs/heads/cortex/attempt/cortex-domain-faketest

# Override still works (explicit)
out_ov="$("$BROKER" abandon --attempt cortex-domain-faketest --reason domain-override --purge --discard-unique --i-know-this-is-a-domain 2>&1)"
assert_ok "domain override removes worktree" test ! -e "$wd"
assert_ok "domain override output purged=1" grep -q 'purged=1' <<<"$out_ov"

# Normal temporary attempt still cleans without override (regression)
"$BROKER" create --attempt temp-ok --base "$base" --allow a.txt >/dev/null
assert_ok "temp attempt purge still works" \
  "$BROKER" abandon --attempt temp-ok --reason temp --purge --discard-unique >/dev/null
assert_ok "temp attempt disk gone" test ! -e "$workspaces/temp-ok"

# --- P0-5: release also refuses domain-named attempt without override ---
"$BROKER" create --attempt cortex-domain-reltest --base "$base" --allow a.txt >/dev/null
wr="$workspaces/cortex-domain-reltest"
set +e
err_r="$("$BROKER" release --attempt cortex-domain-reltest 2>&1)"
rc_r=$?
set -e
assert_ok "domain-named release refused (nonzero)" test "$rc_r" -ne 0
assert_ok "domain-named release error mentions domain/override" \
  grep -qi 'persistent domain\|cortex-domain\|i-know-this-is-a-domain\|release refused' <<<"$err_r"
assert_ok "domain-named still on disk after refused release" test -d "$wr"
# Override allows release
oid_r="$("$BROKER" release --attempt cortex-domain-reltest --i-know-this-is-a-domain 2>/dev/null)"
assert_ok "domain release override returns oid" test -n "$oid_r"
assert_ok "domain release override removes worktree" test ! -e "$wr"
# Ordinary attempt release unaffected
"$BROKER" create --attempt temp-rel --base "$base" --allow a.txt >/dev/null
oid_t="$("$BROKER" release --attempt temp-rel)"
assert_ok "temp release still works" test -n "$oid_t"
assert_ok "temp release removes worktree" test ! -e "$workspaces/temp-rel"

echo "----"
echo "pass=$pass fail=$fail tmp=$TMP"
[[ "$fail" -eq 0 ]]
