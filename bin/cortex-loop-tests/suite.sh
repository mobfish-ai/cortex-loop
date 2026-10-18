#!/usr/bin/env bash
# cortex-loop 测试套件 —— 能真跑、能报红
#
#   bash bin/cortex-loop-tests/suite.sh
#
# 设计约束（跟引擎同源）：
#   1. 零模型调用：一律走 mock 执行器或直接调引擎内部函数，绝不 claude/codex 烧额度
#   2. 幂等：真账本(CLOCK.md / loop-ops/TASKS.md) 跑前跑后逐字节比对，被动一下就报红
#   3. 隔离：A/B 组在临时 CORTEX 根里跑（symlink 引擎 → ROOT 跟着 symlink 走），
#            蜂群组只用 refs/swarm/test-<随机后缀>，跑完 push --delete 清干净
#   4. 全绿才 exit 0
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# 可指向引擎副本：改坏一份副本跑一遍，就能验证「这套测试真的会报红」，
# 也能在动真引擎之前先拿补丁版过一遍门。
ENGINE="${CORTEX_LOOP_ENGINE:-$ROOT/bin/cortex-loop}"
CASES="$ROOT/bin/cortex-loop-tests"
REAL_CLOCK="$ROOT/brain-network/directions/CLOCK.md"
REAL_TASKS="$ROOT/brain-network/directions/loop-ops/TASKS.md"

PASSED=0; FAILED=0; SKIPPED=0
FAILED_IDS=""
ALL_IDS=""          # 收集全部用例 ID，供末尾的「ID 唯一性」自检用

pass() { PASSED=$((PASSED + 1)); ALL_IDS="$ALL_IDS $1"; printf '  ✅ PASS  %-4s %s\n' "$1" "$2"; }
skip() { SKIPPED=$((SKIPPED + 1)); ALL_IDS="$ALL_IDS $1"; printf '  ⏭️  SKIP  %-4s %s\n       ↳ %s\n' "$1" "$2" "$3"; }
fail() {
  FAILED=$((FAILED + 1)); FAILED_IDS="$FAILED_IDS $1"; ALL_IDS="$ALL_IDS $1"
  printf '  ❌ FAIL  %-4s %s\n       ↳ %s\n' "$1" "$2" "$3"
}

# Private companion tools are not part of this export. Absence is a skip,
# not a failure. Callers that pass `need` run the real assertion.
need() { # id desc relpath
  if [[ ! -e "$ROOT/$3" ]]; then
    skip "$1" "$2" "not in this export: $3"
    return 1
  fi
  return 0
}

# 期望红：命令必须以非 0 退出，且输出命中关键词
expect_red() { # id 描述 关键词 命令...
  local id="$1" desc="$2" want="$3"; shift 3
  local out rc
  out="$("$@" 2>&1)"; rc=$?
  if [[ $rc -eq 0 ]]; then
    fail "$id" "$desc" "期望非 0 退出，实际 0；输出：${out:0:200}"
  elif ! printf '%s' "$out" | grep -q -- "$want"; then
    fail "$id" "$desc" "退出码对了但没说清原因（期望含「${want}」）：${out:0:200}"
  else
    pass "$id" "$desc"
  fi
}

expect_green() { # id 描述 关键词 命令...
  local id="$1" desc="$2" want="$3"; shift 3
  local out rc
  out="$("$@" 2>&1)"; rc=$?
  if [[ $rc -ne 0 ]]; then
    fail "$id" "$desc" "期望 0 退出，实际 ${rc}；输出：${out:0:300}"
  elif ! printf '%s' "$out" | grep -q -- "$want"; then
    fail "$id" "$desc" "退出码对了但输出不含「${want}」：${out:0:200}"
  else
    pass "$id" "$desc"
  fi
}

# 跑一个独立 python 用例脚本（自带断言，退出码 0=绿 1=红 2=跳过）
run_case() { # id 描述 脚本
  local id="$1" desc="$2" script="$3"
  local out rc
  out="$(python3 "$CASES/$script" 2>&1)"; rc=$?
  case $rc in
    0) pass "$id" "$desc"; printf '%s\n' "$out" | grep -E '^\s+(清理|本用例|测试命名空间|画像)' ;;
    2) skip "$id" "$desc" "$(printf '%s' "$out" | grep SKIP | head -1)" ;;
    *) fail "$id" "$desc" "$(printf '%s' "$out" | grep -E '^(断言失败|Traceback|\s+BAD)' | head -4 | tr '\n' ' ')" ;;
  esac
}

# ── 账本快照（concurrent-safe F15 硬保险 · EX17）──────────────────────
# 原 BEFORE/AFTER 指纹比对在 launchd / tick 真账本被并发刷新时会假红：
# 套件测试期间没人改过真账本，但 mtime 被另一个进程刷了 → shasum 不一致 → F15 fail。
# 修法：进入套件时把真账本 cp -p 到 $SNAP_DIR（保留字节），收尾时把现真账本
# 与快照比字节。若快照 == 现 → 测试未污染（并发只动 mtime 也算 OK）。
# 套件所有改动都落在 $SBX/... 下副本里，物理上不可能写真账本。
SNAP_DIR="$(mktemp -d /tmp/cortex-loop-suite.snap.XXXXXX)"
cp -p "$REAL_CLOCK" "$REAL_TASKS" "$SNAP_DIR/" 2>/dev/null
fingerprint() { shasum -a 256 "$SNAP_DIR/CLOCK.md" "$SNAP_DIR/TASKS.md" 2>/dev/null; }
BEFORE="$(fingerprint)"   # 诊断信息留底 · F15 现在比的是 snapshot vs current

# ── 临时 CORTEX 根 ──────────────────────────────────────────────────────
SBX="$(mktemp -d /tmp/cortex-loop-suite.XXXXXX)"
SBX_ORIGIN="${SBX}.origin.git"
DBX_ORIGIN="${SBX}.defect-origin.git"
# 2026-07-31 修复：LOG 之前是硬编码常量，测试夹具（testline/gates/A4/D1 这些
# fixture 名）全部写进了跟生产共用的 /tmp/spotlight/cortex-loop.log——真假
# 数据混在一起，人工核查时把测试噪音误判成"最近发生的真实活动"。
export CORTEX_LOOP_LOG="$SBX/cortex-loop.log"
cleanup() { rm -rf "$SBX" "$SBX_ORIGIN" "$DBX_ORIGIN" "$SNAP_DIR"; }
trap cleanup EXIT

mkdir -p "$SBX/bin" "$SBX/brain-network/directions/testline" "$SBX/tests" "$SBX/artifacts"
# 关键手法：symlink 引擎 → 引擎里的 ROOT=dirname(dirname(__file__)) 落在沙箱，
# 于是真账本对本次测试完全不可见（Python 的 abspath 不解析 symlink）
ln -s "$ENGINE" "$SBX/bin/cortex-loop"
TASKS="$SBX/brain-network/directions/testline/TASKS.md"

printf 'exit 0\n' > "$SBX/tests/pass.sh"
printf 'echo "验收命令故意报红"\nexit 3\n' > "$SBX/tests/fail.sh"
printf '真实内容，非空 artifact\n' > "$SBX/artifacts/ok.md"
: > "$SBX/artifacts/empty.md"          # 0 字节 —— A2 的靶子

cat > "$SBX/brain-network/directions/CLOCK.md" <<'EOF'
# CLOCK 夹具

## 列含义（说明表 · 表头无 line，绝不能被当数据表）

| 列 | 含义 |
|----|------|
| line | 方向线目录名 |
| enabled | yes 才被 tick 扫到 |

## 声明

| line | enabled | executor | advance_window_min | max_advance_per_day | owner | driver |
|------|---------|----------|--------------------|---------------------|-------|--------|
| testline | yes | mock | 240 | 2 | - | launchd:suite.fixture |
| testline2 | no | mock | 240 | 2 | - | launchd:suite.fixture2 |
EOF

cat > "$TASKS" <<'EOF'
# TASKS 夹具

## 列含义（说明表 · 表头无 id，绝不能被当数据表）

| 列 | 含义 | 举例 |
|----|------|------|
| A9 | 这一行是说明，不是任务 | done |
| status | 状态枚举 | pending |

## 账本

| id | title | status | depends_on | success_criteria | failure_modes | artifact_paths | short_test | next_advance_after | fails | updated_at | evidence |
|----|-------|--------|------------|------------------|---------------|----------------|------------|--------------------|-------|------------|----------|
| A1 | artifact 缺失 | pending | - | 有产出文件 | 空手套白狼 | artifacts/missing.md | bash tests/pass.sh | - | 0 | 2026-07-28 | - |
| A2 | artifact 是空文件 | pending | - | 有产出文件 | 交空壳凑数 | artifacts/empty.md | bash tests/pass.sh | - | 0 | 2026-07-28 | - |
| A3 | short_test 报红 | pending | - | 验收命令通过 | 改验收放宽 | artifacts/ok.md | bash tests/fail.sh | - | 0 | 2026-07-28 | - |
| A4 | 全绿样本 | pending | - | 验收命令通过 | 假完成 | artifacts/ok.md | bash tests/pass.sh | - | 0 | 2026-07-28 | - |
| A5 | 无 artifact_paths | pending | - | 有产出文件 | 没产出也想绿 | - | bash tests/pass.sh | - | 0 | 2026-07-28 | - |
| A6 | 无 short_test | pending | - | 验收命令通过 | 没验收也想绿 | artifacts/ok.md | - | - | 0 | 2026-07-28 | - |

## 字段规矩（列表形式 · 与真账本同形）

1. 单元格禁止出现管道符。
2. 数据表必须是文件里最后一张表 —— 见 G 组缺陷哨兵 D-01。
EOF

# 完成门含 clean → commit binding → origin reachable；测试沙箱也提供真实
# 本地 origin，不能靠“不是 git repo”绕过传播门。file transport，零公网。
git init --bare "$SBX_ORIGIN" >/dev/null
git -C "$SBX" init >/dev/null
git -C "$SBX" config user.name "Cortex Suite"
git -C "$SBX" config user.email "cortex-suite@example.invalid"
git -C "$SBX" remote add origin "$SBX_ORIGIN"
git -C "$SBX" add \
  brain-network/directions/CLOCK.md \
  brain-network/directions/testline/TASKS.md \
  artifacts/ok.md artifacts/empty.md tests/pass.sh tests/fail.sh
git -C "$SBX" commit -m "fixture: completion gate baseline" >/dev/null
git -C "$SBX" push -u origin HEAD:main >/dev/null

cl() { python3 "$SBX/bin/cortex-loop" "$@"; }
cell() { # $1=任务 id  $2=列序号(1-based) → 打印该格子的值
  awk -F'|' -v id=" $1 " -v n="$2" \
    '$2==id { v=$(n+1); gsub(/^[ \t]+|[ \t]+$/,"",v); print v; exit }' "$TASKS"
}

echo "cortex-loop 测试套件"
echo "沙箱 CORTEX 根：$SBX"
echo
echo "── A · 完成门（try-complete）─────────────────────────────────────────"

expect_red A1 "artifact 缺失 → 拒绝 done" "artifact 缺失" \
  cl try-complete --line testline --task A1
[[ "$(cell A1 3)" == "pending" ]] \
  && pass A1b "A1 失败后 status 保持 pending（不写半绿）" \
  || fail A1b "A1 失败后 status 不该被改" "实际 status=$(cell A1 3)"

expect_red A2 "artifact 是 0 字节空文件 → 拒绝 done" "空文件" \
  cl try-complete --line testline --task A2
[[ "$(cell A2 3)" == "pending" ]] \
  && pass A2b "A2 失败后 status 保持 pending" \
  || fail A2b "A2 失败后 status 不该被改" "实际 status=$(cell A2 3)"

expect_red A3 "short_test 退出码非 0 → 拒绝 done" "退出码 3" \
  cl try-complete --line testline --task A3
[[ "$(cell A3 3)" == "pending" ]] \
  && pass A3b "A3 失败后 status 保持 pending" \
  || fail A3b "A3 失败后 status 不该被改" "实际 status=$(cell A3 3)"

expect_green A4 "全绿 → status=done" "PASS A4" \
  cl try-complete --line testline --task A4
[[ "$(cell A4 3)" == "done" ]] \
  && pass A4b "A4 status 落成 done" \
  || fail A4b "A4 status 应为 done" "实际 status=$(cell A4 3)"
[[ "$(cell A4 12)" == "artifacts/ok.md" ]] \
  && pass A4c "A4 evidence 被回写成 artifact 路径" \
  || fail A4c "A4 evidence 应回写" "实际 evidence=$(cell A4 12)"
[[ -n "$(cell A4 11)" && "$(cell A4 11)" != "2026-07-28" ]] \
  && pass A4d "A4 updated_at 被刷新" \
  || fail A4d "A4 updated_at 应被刷新" "实际 updated_at=$(cell A4 11)"

expect_red A5 "无 artifact_paths → 直接拒绝 done" "无 artifact_paths" \
  cl try-complete --line testline --task A5
expect_red A6 "无 short_test → 直接拒绝 done" "无 short_test" \
  cl try-complete --line testline --task A6

echo
echo "── B · 账本读写（防回归）─────────────────────────────────────────────"

# B6：一个文件里 3 张表（前说明表 + 数据表 + 尾说明表），只认表头含主键的那张
OUT="$(cl status 2>&1)"
if printf '%s' "$OUT" | grep -q 'done=1 pending=5'; then
  pass B6 "多表文件只认表头含 id 的那张（6 任务不多不少，说明表未混入）"
else
  fail B6 "多表文件只认主键表" "status 输出异常（期望 done=1 pending=5）：${OUT:0:200}"
fi
expect_red B6b "说明表里的 A9 不是任务" "找不到任务 A9" \
  cl try-complete --line testline --task A9

# B7：CLOCK 主键是 line 不是 id，传错 key 会静默读到 0 行
if printf '%s' "$OUT" | grep -q 'testline .*enabled=yes .*executor=mock' \
   && printf '%s' "$OUT" | grep -q 'testline2 .*enabled=no'; then
  pass B7 "CLOCK 用 line 作主键读取（2 条声明全读到，非 0 行）"
else
  fail B7 "CLOCK 用 line 作主键" "读不到声明行：${OUT:0:200}"
fi

run_case B8 "list_refs 真返回 ref 列表，不静默退回文件快照" "_case-refs.py"

echo
echo "── C · 蜂群 ─────────────────────────────────────────────────────────"
run_case C9  "节点自我画像字段齐全 · can_sleep ∈ {yes,no}" "_case-swarm-profile.py"
run_case C10 "静默未超缓冲不接管 / 超缓冲才接管" "_case-takeover.py"
run_case C11 "租约 CAS：同 parent 第二个 push 必被拒" "_case-lease-cas.py"

echo
echo "── D · 安全护栏 ─────────────────────────────────────────────────────"
run_case D12 "write_ref 拿到空/非法 sha 绝不 push（防删远端 ref）" "_case-write-ref-guard.py"

echo
echo "── I · fit_score glob 匹配（2026-07-29 §3.1）──────────────────────────"
run_case I17 "fit_score 改 glob 匹配：旧任务零回归 + 新通配真生效" "_case-fit-score-glob.py"
run_case I18 "net.github.fast/slow cap：纯函数边界 + 真机实测互斥" "_case-net-github-latency.py"
run_case I19 "last_seen 改读 beat ref：复现旧矛盾 + 证明新口径修好" "_case-beat-ref-precise.py"

echo
echo "── E · 合同 gate ────────────────────────────────────────────────────"
if need E13 "三份合同 (CLOCK / INTENT / TASKS) gate 全 PASS" bin/knowledge-contract-gate.py; then
GATE_OK=1; GATE_WHY=""
for contract in \
  brain-network/directions/CLOCK.md \
  brain-network/directions/loop-ops/INTENT.md \
  brain-network/directions/loop-ops/TASKS.md
do
  g_out="$(cd "$ROOT" && python3 bin/knowledge-contract-gate.py check-path "$contract" 2>&1)"
  if [[ $? -ne 0 ]] || ! printf '%s' "$g_out" | grep -q '"status": "PASS"'; then
    GATE_OK=0; GATE_WHY="$GATE_WHY $contract:$(printf '%s' "$g_out" | grep -o '"parse_errors".*' | head -c 120)"
  fi
done
[[ $GATE_OK -eq 1 ]] \
  && pass E13 "三份合同 (CLOCK / INTENT / TASKS) gate 全 PASS" \
  || fail E13 "三份合同 gate 应全 PASS" "$GATE_WHY"
fi

if need E14 "TASKS 缺 failure_modes（负空间）→ gate 必须 FAIL" bin/knowledge-contract-gate.py; then
run_case E14 "TASKS 缺 failure_modes（负空间）→ gate 必须 FAIL" "_case-gate-negative.py"
fi

echo
echo "── G · 已知引擎缺陷哨兵（不计入红绿，修好会自己喊）───────────────────"
# D-01：read_table 返回的是**文件里最后一张表**的表头，不是命中主键那张的表头。
# 后果：TASKS.md 若在账本之后再放一张说明表，set_cell 抛 ValueError，
#       try-complete / submit / tick --auto 全部 traceback 死掉（不是报红，是崩）。
# 本哨兵不改引擎，只把现状钉死；引擎一修好它就提示升级为正向断言。
DBX="$SBX/defect-d01"
mkdir -p "$DBX/bin" "$DBX/brain-network/directions/testline" "$DBX/tests" "$DBX/artifacts"
ln -s "$ENGINE" "$DBX/bin/cortex-loop"
printf 'exit 0\n' > "$DBX/tests/pass.sh"
printf '非空\n' > "$DBX/artifacts/ok.md"
printf '| line | enabled | executor | owner | driver |\n|---|---|---|---|---|\n| testline | yes | mock | - | launchd:x |\n' \
  > "$DBX/brain-network/directions/CLOCK.md"
cat > "$DBX/brain-network/directions/testline/TASKS.md" <<'EOF'
| id | title | status | depends_on | success_criteria | failure_modes | artifact_paths | short_test | next_advance_after | fails | updated_at | evidence |
|----|-------|--------|------------|------------------|---------------|----------------|------------|--------------------|-------|------------|----------|
| D1 | 账本后面还有一张说明表 | pending | - | 验收通过 | 假完成 | artifacts/ok.md | bash tests/pass.sh | - | 0 | 2026-07-28 | - |

## 字段规矩（尾部说明表）

| 字段 | 规矩 |
|------|------|
| id | 任务编号 |
EOF
git init --bare "$DBX_ORIGIN" >/dev/null
git -C "$DBX" init >/dev/null
git -C "$DBX" config user.name "Cortex Suite"
git -C "$DBX" config user.email "cortex-suite@example.invalid"
git -C "$DBX" remote add origin "$DBX_ORIGIN"
git -C "$DBX" add \
  brain-network/directions/CLOCK.md \
  brain-network/directions/testline/TASKS.md \
  artifacts/ok.md tests/pass.sh
git -C "$DBX" commit -m "fixture: defect sentinel baseline" >/dev/null
git -C "$DBX" push -u origin HEAD:main >/dev/null
D_OUT="$(python3 "$DBX/bin/cortex-loop" try-complete --line testline --task D1 2>&1)"; D_RC=$?
D_STATUS="$(awk -F'|' '$2==" D1 "{gsub(/^[ \t]+|[ \t]+$/,"",$4); print $4}' \
  "$DBX/brain-network/directions/testline/TASKS.md")"
DEFECTS=0
if [[ $D_RC -ne 0 ]] && printf '%s' "$D_OUT" | grep -q '表中无此列: status'; then
  DEFECTS=1
  printf '  🐞 DEFECT D-01 仍在（预期）：数据表后再有一张说明表 → set_cell 抛 ValueError，try-complete 崩溃\n'
  printf '       ↳ 复现：bash bin/cortex-loop-tests/suite.sh 的 G 组夹具；根因 read_table 用最后一张表的表头\n'
elif [[ $D_RC -eq 0 && "$D_STATUS" == "done" ]]; then
  pass G16 "D-01 已修复（尾部说明表不再打断 set_cell）→ 请把本哨兵升级为正向断言"
else
  fail G16 "D-01 行为变了但既没修好也不是原症状" "rc=$D_RC status=$D_STATUS 输出：${D_OUT:0:200}"
fi

echo
echo "── H · E013 负向测试（门死了自己不会报错，必须有断言证明门是活的）───"
# 今天两次亲身教训：正向跑全绿的门，一遇负向测试就被打脸——
# SCANNER-DOWN 判据被自己多加的条件焊死过一次，传播门 v1 也漏判过一次。
# 固化进套件，不留在 /tmp 自生自灭。
if H_OUT="$(python3 "$CASES/fixtures/negtest-scanner-down.py" "$ENGINE" 2>&1)"; then
  pass H01 "SCANNER-DOWN 判据 4 场景全绿（命令不存在/超时/正常无匹配/正常有匹配）"
else
  fail H01 "SCANNER-DOWN 判据回归" "${H_OUT: -300}"
fi
if H_OUT="$(python3 "$CASES/fixtures/negtest-propagation-gate.py" 2>&1)"; then
  pass H02 "传播门 v2 判据 4 场景全绿，并复证 v1 在「有历史但改了没提交」漏判"
else
  fail H02 "传播门判据回归" "${H_OUT: -300}"
fi
# 六定律三关：不只验"拦没拦"，还验"拦它的是不是正确那条定律"——
# 三关顺序/判据写错时可能"拦对了但理由错了"，下次改动就会拆错关卡。
# 破坏性验证过：拆掉 C3 人类签名子关 → 立刻 1 FAIL 退出码 1。
if H_OUT="$(python3 "$CASES/fixtures/negtest-six-laws-gate.py" "$ENGINE" 2>&1)"; then
  pass H04 "六定律三关 C1/C2/C3 共 7 场景全绿，且每条被正确的定律拦下"
else
  fail H04 "六定律三关回归（covenant_check）" "${H_OUT: -300}"
fi
# 价值三定律：验「价值不能自报」—— 声明 V3 但产出落在 reports/ 必须被打回 V1。
# 破坏性验证过：拆掉 verify_value 的降级逻辑 → 5 FAIL 退出码 1。
if H_OUT="$(python3 "$CASES/fixtures/negtest-value-laws.py" "$ENGINE" 2>&1)"; then
  pass H05 "价值三定律 V1/V2/V3 共 10 场景全绿（吹牛必打回·诚实放行·只降不升）"
else
  fail H05 "价值三定律回归（verify_value）" "${H_OUT: -300}"
fi
# 验收员的**标签本身**要机械核验 —— 21/25 result 曾倒在这里：
# prompt 明写「没改 bounds 外的 X 不构成 REJECT 理由」，验收员照样回 REJECT。
# 破坏性验证过：拆掉 REJECT 反向核验 → 1 FAIL 退出码 1。
# dashboard 的机器可读输出是自愈链第一环 —— 它坏了人读那面看起来一切正常（GLASSBOX G1）
if need H09 "dashboard v2（四问首屏·同源指标/EXPECTATIONS·UNKNOWN 不假绿·S2 影子证据）" bin/cortex-dashboard.sh; then
if H_OUT="$(python3 "$CASES/fixtures/negtest-dashboard-json.py" 2>&1)"; then
  pass H09 "dashboard v2（四问首屏·同源指标/EXPECTATIONS·UNKNOWN 不假绿·S2 影子证据）"
else
  fail H09 "dashboard JSON 契约回归" "${H_OUT: -300}"
fi
fi
if H_OUT="$(python3 "$CASES/fixtures/negtest-judge-verdict.py" "$ENGINE" 2>&1)"; then
  pass H08 "验收员标签机械核验 8 场景全绿（界外改判 SCOPE·界内一条不放宽）"
else
  fail H08 "验收员标签核验回归（_judge_verdict_from_text）" "${H_OUT: -300}"
fi
# 一拍的时间预算：太短则真任务永远跑不完（心跳照跳、产出恒零，比死了还难发现），
# 太长则一拍卡死永久占住时钟槽位。300s 被 health 恒红遮了一整天——旧代码 49s 就退出，
# 压根碰不到这个上限；health 一绿它立刻变成新天花板（22:14→22:19 每拍 status=15/TERM）。
# 破坏性验证过：真文件改回 300 → 立刻 1 FAIL 退出码 1。
if H_OUT="$(python3 "$CASES/fixtures/negtest-tick-time-budget.py" 2>&1)"; then
  pass H10 "一拍时间预算三态（太短/太长/未知）7 场景 + 两类 systemd 失败可区分"
else
  fail H10 "一拍时间预算回归（TimeoutStartSec vs 时钟周期）" "${H_OUT: -300}"
fi
# 负载率/闲置率的分子分母必须同窗。原实现分母取「今日应跑拍数」、分子取 result 的全历史
# 去重计数；蜂群 07-28 才起，当天两者恰好都≈今天，缺陷完全看不见（显示 66% 闲置很合理）。
# 会说谎的是跨天：次日 00:15 分母重置为 1、分子仍带昨天的 31 → 封顶 100% 负载、闲置 0%，
# 一个任务没跑却显示满载 —— fail-open 里最坏的一种：最该报警时最绿，且越久没产出越好看。
# 破坏性验证过：分子改回全历史 → 立刻 2 FAIL 退出码 1。
if need H11 "负载率量纲同窗（跨天不 fail-open · 分子按 committerdate 非 id 猜日期）" bin/cortex-dashboard.sh; then
if H_OUT="$(python3 "$CASES/fixtures/negtest-load-window.py" 2>&1)"; then
  pass H11 "负载率量纲同窗（跨天不 fail-open · 分子按 committerdate 非 id 猜日期）"
else
  fail H11 "负载率/闲置率分子分母同窗回归" "${H_OUT: -300}"
fi
fi
# 前提失效 ≠ 失败。own_skill() 修好了发现层，但**修好之前入队的任务不会自己消失**：
# island-YC-autoplan 每拍都去跑一个 Linux 侧 dangling 的 vendor 软链，烧额度、产出零、
# 还往过门率分母加数。更坏的是它逼出作弊压力 —— 07:36 那轮诚实写 BLOCKED 报告，
# 23:13 那轮就造了 stub 去满足门。不可能完成的任务会持续生产假产出。
# 所以它必须走 moot 退役（不加分也不扣分），而不是当 FAIL 无限重试。
# 破坏性验证过：把引擎里的 premise-invalid 抽掉 → 立刻 3 FAIL 退出码 1。
if H_OUT="$(python3 "$CASES/fixtures/negtest-premise-invalid.py" 2>&1)"; then
  pass H12 "前提失效走 moot 退役（5 场景 + 门开在烧额度之前 + 与发现层同一把尺子）"
else
  fail H12 "前提失效门回归（vendor 软链任务无限重试）" "${H_OUT: -300}"
fi
if H_OUT="$(python3 "$CASES/fixture-result-receipt.py" 2>&1)"; then
  pass H13 "run-v1 receipt（source/claim/origin/world 齐全，写失败不前进）"
else
  fail H13 "run-v1 receipt 合同回归" "${H_OUT: -300}"
fi
if H_OUT="$(python3 "$CASES/fixture-discovery-learning.py" 2>&1)"; then
  pass H14 "S1 lineage（稳定 discovery cohort·passed-only learning·幂等）"
else
  fail H14 "S1 discovery/learning 血缘回归" "${H_OUT: -300}"
fi
if need H15 "S1 指标合同（ACTIVE 目标必须带基线/窗口/样本/审批）" bin/cortex-metrics.py; then
if H_OUT="$(python3 bin/cortex-metrics.py --validate-contract 2>&1)"; then
  pass H15 "S1 指标合同（ACTIVE 目标必须带基线/窗口/样本/审批）"
else
  fail H15 "S1 指标合同无效" "${H_OUT: -300}"
fi
fi
if need H16 "指标合同负测（未批准阈值不能激活）" bin/cortex-metrics.py; then
if H_OUT="$(python3 "$CASES/fixtures/negtest-metric-contract.py" 2>&1)"; then
  pass H16 "指标合同负测（未批准阈值不能激活）"
else
  fail H16 "指标合同负测回归" "${H_OUT: -300}"
fi
fi
if need H17 "G2 累计战绩/滚动 cohort 分离，三类终态不混算" bin/cortex-metrics.py; then
if H_OUT="$(python3 "$CASES/fixtures/negtest-metric-window.py" 2>&1)"; then
  pass H17 "G2 累计战绩/滚动 cohort 分离，三类终态不混算"
else
  fail H17 "G2 窗口口径回归" "${H_OUT: -300}"
fi
fi
if need H18 "G1 frozen discovery cohort（缺源/缺字段/冲突均 UNKNOWN）" bin/cortex-metrics.py; then
if H_OUT="$(python3 "$CASES/fixtures/negtest-g1-discovery-cohort.py" 2>&1)"; then
  pass H18 "G1 frozen discovery cohort（缺源/缺字段/冲突均 UNKNOWN）"
else
  fail H18 "G1 discovery cohort 回归" "${H_OUT: -300}"
fi
fi
if need H19 "S2 合链接影子回放可复跑（91 cases，明确禁止自动晋级）" bin/cortex-s2-scm-shadow.py; then
if H_OUT="$(python3 bin/cortex-s2-scm-shadow.py 2>&1)"; then
  H_S2="$(printf '%s' "$H_OUT" | python3 -c \
    'import json,sys; d=json.load(sys.stdin); print("%s|%s|%s|%s" % (d.get("evaluated_cases"), d.get("stage_judgement"), d.get("verdict_vs_inventory_baseline"), str(d.get("promotion","")).split(";",1)[0]))' \
    2>/dev/null)"
  if [[ "$H_S2" == "91|S2_PILOT_EVIDENCE_ONLY|SUPPORTED|FORBIDDEN" ]]; then
    pass H19 "S2 合链接影子回放可复跑（91 cases，明确禁止自动晋级）"
  else
    fail H19 "S2 影子结果合同漂移" "$H_S2"
  fi
else
  fail H19 "S2 合链接影子回放失败" "${H_OUT: -300}"
fi
fi
if H_OUT="$(python3 "$CASES/fixture-map-backlink-scanner.py" 2>&1)"; then
  pass H20 "B/C 反向边进入 S1 discovery，launchd 无人值守默认走 MiniMax/cheap"
else
  fail H20 "B/C 反向边扫描器/执行器选择回归" "${H_OUT: -300}"
fi
if H_OUT="$(python3 "$CASES/fixtures/negtest-run-timeout-process-group.py" "$ENGINE" 2>&1)"; then
  pass H21 "执行器超时杀完整进程组（无 Codex/MCP 孤儿持管道）"
else
  fail H21 "执行器超时进程组清理回归" "${H_OUT: -300}"
fi
if need H22 "backlink 机械任务零模型执行，隔离 candidate 精确落 canonical master" bin/cortex-workspace.sh; then
if H_OUT="$(python3 "$CASES/fixture-deterministic-backlink.py" "$ENGINE" 2>&1)"; then
  pass H22 "backlink 机械任务零模型执行，隔离 candidate 精确落 canonical master"
else
  fail H22 "backlink 确定性执行/传播回归" "${H_OUT: -300}"
fi
fi
if H_OUT="$(python3 "$CASES/fixtures/negtest-concurrent-execution.py" 2>&1)"; then
  pass H23 "并发执行合同（异任务不丢·同任务 CAS/Worker 排重·task-add 预发布门）"
else
  fail H23 "并发执行合同回归" "${H_OUT: -500}"
fi
if H_OUT="$(python3 "$CASES/fixtures/negtest-read-ref-tristate.py" 2>&1)"; then
  pass H24 "Git ref 读取 ok/empty/error 三态不坍缩"
else
  fail H24 "Git ref 三态回归" "${H_OUT: -500}"
fi
if H_OUT="$(python3 "$CASES/fixtures/negtest-fail-cooldown-retry.py" 2>&1)"; then
  pass H25 "失败冷却后可重试，边界与旧回执兼容"
else
  fail H25 "失败冷却重试回归" "${H_OUT: -500}"
fi
if need H26 "稀疏执行舱（共享 objects·独立 index·磁盘门·崩溃恢复）" bin/cortex-workspace.sh; then
if H_OUT="$(bash "$CASES/fixtures/negtest-workspace-broker.sh" 2>&1)"; then
  pass H26 "稀疏执行舱（共享 objects·独立 index·磁盘门·崩溃恢复）"
else
  fail H26 "稀疏执行舱合同回归" "${H_OUT: -500}"
fi
fi
if need H27 "candidate 集成控制器（越界/短测拒绝·master lease-CAS·竞争重试）" bin/cortex-integrator.sh; then
if H_OUT="$(bash "$CASES/fixtures/negtest-integration-controller.sh" 2>&1)"; then
  pass H27 "candidate 集成控制器（越界/短测拒绝·master lease-CAS·竞争重试）"
else
  fail H27 "candidate 集成控制器回归" "${H_OUT: -500}"
fi
fi
if H_OUT="$(python3 "$CASES/fixtures/negtest-master-landed.py" 2>&1)"; then
  pass H28 "完成语义（远端 candidate 仅结算中·落 canonical master 才 done）"
else
  fail H28 "canonical landing 完成门回归" "${H_OUT: -500}"
fi
if need H29 "交付面量具（脏舱/残锁/CAS 重试三态统计不坍缩）" bin/cortex-workspace.sh; then
if H_OUT="$(python3 "$CASES/fixtures/negtest-workspace-observability.py" 2>&1)"; then
  pass H29 "交付面量具（脏舱/残锁/CAS 重试三态统计不坍缩）"
else
  fail H29 "workspace 交付面量具回归" "${H_OUT: -500}"
fi
fi
if need H30 "candidate 原子工具（canonical 精确合成·范围验证·不可变发布·幂等查询）" bin/cortex-candidate.sh; then
if H_OUT="$(bash "$CASES/fixtures/negtest-candidate-publish.sh" 2>&1)"; then
  pass H30 "candidate 原子工具（canonical 精确合成·范围验证·不可变发布·幂等查询）"
else
  fail H30 "candidate 原子发布工具回归" "${H_OUT: -500}"
fi
fi
if need H31 "执行引擎接通 workspace→candidate→integrator→canonical done 全链路" bin/cortex-workspace.sh; then
if H_OUT="$(python3 "$CASES/fixtures/negtest-workspace-runtime.py" 2>&1)"; then
  pass H31 "执行引擎接通 workspace→candidate→integrator→canonical done 全链路"
else
  fail H31 "workspace runtime 端到端回归" "${H_OUT: -700}"
fi
fi
if need H32 "Agent worktree 认领/脏改保护/安全回收合同" bin/git-worktree-doctor.py; then
if H_OUT="$(python3 "$CASES/negtest-worktree-claims.py" 2>&1)"; then
  pass H32 "Agent worktree 认领/脏改保护/安全回收合同"
else
  fail H32 "worktree 认领回收合同回归" "${H_OUT: -500}"
fi
fi

if need H33 "Dashboard watch 单前台/仅显示态 ANSI/Ctrl-C 恢复终端" bin/cortex-dashboard.sh; then
if H_OUT="$(python3 "$CASES/fixtures/negtest-dashboard-watch-safety.py" 2>&1)"; then
  pass H33 "Dashboard watch 单前台/仅显示态 ANSI/Ctrl-C 恢复终端"
else
  fail H33 "Dashboard watch Ctrl-C 安全合同回归" "${H_OUT: -500}"
fi
fi

if need H34 "进程工具禁影子二进制/禁裸 pgrep-pkill 调用" bin/verify-process-tool-safety.py; then
if H_OUT="$(python3 "$ROOT/bin/verify-process-tool-safety.py" 2>&1)"; then
  pass H34 "进程工具禁影子二进制/禁裸 pgrep-pkill 调用"
else
  fail H34 "进程工具 PATH 安全合同回归" "${H_OUT: -500}"
fi
fi

if H_OUT="$(python3 "$CASES/fixtures/negtest-task-inspection.py" 2>&1)"; then
  pass H35 "task-show 人读/JSON/结算传播三态原子查询"
else
  fail H35 "task-show 原子查询合同回归" "${H_OUT: -700}"
fi
if need H37 "run-contract-v1 CLI/API 语义投影与漂移 fail-closed" bin/control-plane-cockpit.py; then
if H_OUT="$(python3 "$CASES/fixtures/negtest-run-contract.py" 2>&1)"; then
  pass H37 "run-contract-v1 CLI/API 语义投影与漂移 fail-closed"
else
  fail H37 "run-contract-v1 canonical projection 回归" "${H_OUT: -700}"
fi
fi
if need H38 "Cockpit run-contract 绑定与 board-only/stale fail-closed" bin/control-plane-cockpit.py; then
if H_OUT="$(python3 "$CASES/fixtures/negtest-cockpit-run-contract.py" 2>&1)"; then
  pass H38 "Cockpit run-contract 绑定与 board-only/stale fail-closed"
else
  fail H38 "Cockpit run-contract 绑定回归" "${H_OUT: -700}"
fi
fi
if need H39 "acp-native:mmx-a 安全别名、ACP tool evidence 与 timeout budget bridge" bin/_cortex_acp.py; then
if H_OUT="$(python3 "$CASES/fixtures/negtest-acp-native-adapter.py" 2>&1)"; then
  pass H39 "acp-native:mmx-a 安全别名、ACP tool evidence 与 timeout budget bridge"
else
  fail H39 "acp-native:mmx-a adapter bridge 回归" "${H_OUT: -700}"
fi
fi
if need H40 "ACP tool round cap 可配且低/高 cap 与非法配置 fail-closed" bin/_cortex_acp.py; then
if H_OUT="$(python3 "$CASES/fixtures/negtest-acp-tool-rounds.py" 2>&1)"; then
  pass H40 "ACP tool round cap 可配且低/高 cap 与非法配置 fail-closed"
else
  fail H40 "ACP tool round cap 配置回归" "${H_OUT: -700}"
fi
fi
if need H41 "candidate companion fail-closed 与 artifact/candidate/terminal 三态投影" bin/git-commit-preflight.py; then
if H_OUT="$(python3 "$CASES/fixtures/negtest-candidate-companion.py" 2>&1)"; then
  pass H41 "candidate companion fail-closed 与 artifact/candidate/terminal 三态投影"
else
  fail H41 "candidate companion 与交付三态回归" "${H_OUT: -700}"
fi
fi
if need H36 "guardrail 生产事件闭环（原子/幂等/窄语义/真实接线）" bin/cortex-authorization-incident.sh; then
if H_OUT="$(python3 "$CASES/fixtures/negtest-guardrail-production.py" 2>&1)"; then
  pass H36 "guardrail 生产事件闭环（原子/幂等/窄语义/真实接线）"
else
  fail H36 "guardrail 生产事件闭环回归" "${H_OUT: -700}"
fi
fi
# SCOPE 第三态：验收员判据欠定义是今天 21/25 result 被否的根因（机械门全过、
# 全倒在 AI 验收员，理由清一色是「还得改 bounds 外的文件」——而那正是 C1 禁止的）。
# 修法是给判据 + 拆第三态，所以第三态本身必须有防滥用断言：SCOPE 不点名路径、
# 或点名的路径其实在界内 → 一律降级 REJECT。
# 破坏性验证过：拆掉「点名路径必须在界外」的校验 → 立刻 3 FAIL 退出码 1。
if H_OUT="$(python3 "$CASES/fixtures/negtest-judge-scope.py" "$ENGINE" 2>&1)"; then
  pass H06 "ai_judge SCOPE 第三态 12 场景全绿（含 4 条防滥用降级 + 失败关闭防回归）"
else
  fail H06 "ai_judge 判据/第三态回归" "${H_OUT: -300}"
fi
# 计划复用：每拍无条件发新计划 = 分母暴涨、分子不动，过门率必然一路下滑。
# 这道门写错方向的症状是静默的（太松 → 新缺口再也发不出去；太紧 → 退化回原样
# 且没人发现），所以两个方向都要钉住。
# 破坏性验证过：把「别的节点 failed」也当成不用干 → 立刻 1 FAIL 退出码 1。
if H_OUT="$(python3 "$CASES/fixtures/negtest-plan-churn.py" "$ENGINE" 2>&1)"; then
  pass H07 "计划复用判据 9 场景全绿（三态：done 跳过 / 本节点 failed 让人 / 其余可干）"
else
  fail H07 "计划复用判据回归（_oldest_open_plan）" "${H_OUT: -300}"
fi
# 资产健康：ROOT 是 str，扫描器却用了 Path 运算，发现阶段会 TypeError 中断。
# 计数漂移（>2% 或 >3 个文件）和引用/updated_at 过期必须可逆、低信任，且只读。
if H_OUT="$(python3 "$CASES/fixtures/negtest-asset-health.py" "$ENGINE" 2>&1)"; then
  pass H42 "资产健康 Path(ROOT) + 计数漂移 + 过期阈值（只读、可逆、L1）"
else
  fail H42 "资产健康扫描回归（scan_asset_health）" "${H_OUT: -700}"
fi
# 候选扫描，不计入红绿——命中不代表是 bug，代表"值得人核对一遍"（脚本自己的设计）
DC_OUT="$(bash "$CASES/dimensional-collapse-scan.sh" "$ENGINE" 2>&1)"; DC_RC=$?
if [[ $DC_RC -eq 0 ]]; then
  skip H03 "维度坍缩候选扫描" "无候选"
else
  N_HITS="$(printf '%s' "$DC_OUT" | grep -c '^  [0-9]')"
  skip H03 "维度坍缩候选扫描" "${N_HITS:-?} 处候选（非红非绿，人工核对性价比是否值得展开，见 E013）"
fi

echo
echo "── F · 幂等自证（concurrent-safe F15）────────────────────────────────"
# concurrent-safe F15：snapshot vs current（真账本被并发刷新 mtime 不会假红）
SNAP_FP="$(shasum -a 256 "$SNAP_DIR/CLOCK.md" "$SNAP_DIR/TASKS.md" 2>/dev/null | awk '{print $1}')"
NOW_FP="$(shasum -a 256 "$REAL_CLOCK" "$REAL_TASKS" 2>/dev/null | awk '{print $1}')"
if [[ "$SNAP_FP" == "$NOW_FP" ]]; then
  pass F15 "真账本与进入套件时的 snapshot 字节一致 · 并发 mtime 刷新不假红"
else
  fail F15 "测试污染了真账本" "snapshot=$SNAP_FP now=$NOW_FP"
fi

# ── 套件自检：用例 ID 不许重复 ──────────────────────────────────────
# 2026-07-29 实测：两个不同测试都用了 H06，输出里出现两行 H06 —— 人眼扫过去
# 会以为是同一条跑了两遍，而实际是**一条测试的红灯可能被另一条的绿灯掩盖**。
# 测试套件自己也需要被测试（本条就是「谁来测量具」的答案）。
DUP_IDS="$(printf '%s\n' "$ALL_IDS" | tr ' ' '\n' | grep -v '^$' | sort | uniq -d | tr '\n' ' ')"
if [[ -n "${DUP_IDS// /}" ]]; then
  fail Z99 "用例 ID 重复（红灯可能被同名绿灯掩盖）" "重复：$DUP_IDS"
else
  pass Z99 "用例 ID 全局唯一"
fi

echo
echo "════════════════════════════════════════════════════════════════════"
printf '总计：%d PASS · %d FAIL · %d SKIP · %d 已知缺陷\n' \
  "$PASSED" "$FAILED" "$SKIPPED" "${DEFECTS:-0}"
if [[ $FAILED -gt 0 ]]; then
  echo "红灯用例：$FAILED_IDS"
  exit 1
fi
[[ $SKIPPED -gt 0 ]] && echo "（有 SKIP：多为网络不可达，非绿非红，见上方 ↳ 说明）"
echo "全绿"
exit 0
