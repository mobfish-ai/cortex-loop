#!/usr/bin/env bash
# cortex-loop 自主闭环验收门 —— 回答「达标了吗」用数字，不用形容词。
#
# 为什么要这个：operator 连问两次「这个到底验证得怎么样」。
# 用散文回答等于让我自己给自己打分 —— 同一个观察者评自己的产出，
# 盲区完全重合（epiplexity 公理 1）。所以判据必须机械、可重跑、不经我口。
#
# 判据全部读**执行真相**（git ref + 任务账本 + 进程/调度器实况），
# 不读任何「自报完成」的文字。
#
# 用法：bash bin/cortex-loop-tests/autonomy-acceptance.sh [--verbose]
# 退出码：0=全过  1=有未达标项  2=环境不具备（无法判定，**不算通过**）

set -uo pipefail
cd "$(dirname "$0")/../.." || exit 2
VERBOSE=0; [[ "${1:-}" == "--verbose" ]] && VERBOSE=1

SWARM="${CORTEX_SWARM:-cortex}"
PASS=0; FAIL=0; UNKNOWN=0

ok()   { echo "  ✅ $1"; PASS=$((PASS+1)); }
bad()  { echo "  ❌ $1"; FAIL=$((FAIL+1)); }
huh()  { echo "  ⚠️  $1"; UNKNOWN=$((UNKNOWN+1)); }
note() { [[ $VERBOSE -eq 1 ]] && echo "       $1"; return 0; }

echo "cortex-loop 自主闭环验收 · 蜂群 $SWARM"
echo "════════════════════════════════════════════════════════"

# ── A1 自主找活 ──────────────────────────────────────────────
# 判据：discover 实扫出候选，且**含治理/低洼类**（不只是硬编码的固定清单）
echo
echo "A1 · 自主找活（不靠人喂任务清单）"
DISC=$(timeout 600 python3 bin/cortex-loop discover 2>&1)
N_CAND=$(echo "$DISC" | grep -cE '^\| [0-9]+\.[0-9]+ \|')
if [[ $N_CAND -ge 1 ]]; then
  ok "扫出 $N_CAND 条候选"
else
  bad "扫不出候选（自主找活失效）"
fi
# 治理类来源：合同欠账 / 低洼 / 坏数据 / frontmatter —— 有任一即算接上 EVO 治理
if echo "$DISC" | grep -qE 'debt-|lowland-|island-|marker-|fm-'; then
  ok "候选含 EVO 治理类（合同欠账/低洼/坏数据/元数据）"
else
  bad "候选里没有治理类 —— 只会做固定清单，不算自主治理"
fi

# ── A2 自主派发 ──────────────────────────────────────────────
echo
echo "A2 · 自主派发（跨节点，不靠人分配）"
PLANS=$(git ls-remote origin "refs/swarm/$SWARM/plan/*" 2>/dev/null | wc -l | tr -d ' ')
if [[ "${PLANS:-0}" -ge 2 ]]; then
  ok "累计派发 $PLANS 轮计划"
else
  huh "只有 ${PLANS:-0} 轮计划（样本不足，无法判定）"
fi
NODES=$(git ls-remote origin "refs/swarm/$SWARM/beat/*" 2>/dev/null \
        | sed 's|.*/beat/||' | sort -u | wc -l | tr -d ' ')
if [[ "${NODES:-0}" -ge 2 ]]; then
  ok "蜂群 $NODES 个节点在心跳"
else
  bad "只有 ${NODES:-0} 个节点 —— 单节点不构成蜂群"
fi

# ── A3 自主完成 ──────────────────────────────────────────────
# 这是最硬的一项：同源指标合同 + 可追溯 receipt，不在验收脚本里另造阈值。
echo
echo "A3 · 自主完成（过机械门，不是自报完成）"
METRICS=$(timeout 180 python3 bin/cortex-metrics.py --json 2>/dev/null)
if [[ $? -ne 0 || -z "$METRICS" ]]; then
  huh "指标合同来源不可读（无法判定自主完成）"
else
  G2_STATE=$(python3 -c 'import json,sys; print(json.load(sys.stdin)["g2"]["sample_state"])' <<<"$METRICS" 2>/dev/null)
  G2_TARGET=$(python3 -c 'import json,sys; print(json.load(sys.stdin)["g2"]["threshold_state"])' <<<"$METRICS" 2>/dev/null)
  if [[ "$G2_STATE" == "PASS" && "$G2_TARGET" == "RATIFIED" ]]; then
    ok "G2 滚动窗目标已批准且达标"
  else
    huh "G2=${G2_STATE}、target=${G2_TARGET}；无批准阈值或证据不足不算通过"
  fi
fi

# ── A4 自愈 ──────────────────────────────────────────────────
echo
echo "A4 · 自愈（失败后自己爬起来，不等人）"
# ①执行器抑制能自动到期  ②失败任务会被重试（fails 计数在涨说明有重投）
SUPP=$(timeout 120 python3 bin/cortex-loop model 2>&1)
if echo "$SUPP" | grep -q '抑制中'; then
  if echo "$SUPP" | grep -qE '还剩 [0-9]+ 分钟'; then
    ok "执行器抑制带自动到期（额度窗口免疫）"
  else
    bad "执行器被抑制但无到期时间 —— 会永久卡死"
  fi
else
  ok "当前无执行器被抑制"
fi
LEDGERS=$(find brain-network/directions -name TASKS.md 2>/dev/null)
RETRIED=0
for L in $LEDGERS; do
  n=$(awk -F'|' '/^\| [A-Za-z0-9_-]+ \|/ && $11+0 > 0 {c++} END{print c+0}' "$L")
  RETRIED=$((RETRIED + n))
done
if [[ $RETRIED -ge 1 ]]; then
  ok "有 $RETRIED 个任务经历过失败重投（fails>0 仍在账本里）"
else
  huh "没有任务重投记录 —— 要么没失败过，要么失败即弃"
fi

# ── A5 门没被放宽（最重要的反向判据）────────────────────────
echo
echo "A5 · 完成门未被放宽（反测哨兵必须仍是红的）"
# T3 是故意埋的「永远缺 artifact」任务。它一旦变绿 = 有人把门放松了。
SENT=$(grep -E '^\| T3 \|' brain-network/directions/loop-ops/TASKS.md 2>/dev/null \
       | awk -F'|' '{gsub(/ /,"",$4); print $4}')
case "${SENT:-missing}" in
  # 注意 ${SENT} 必须带花括号：紧跟中文全角括号时 bash 会把它并进变量名
  blocked|pending|failed) ok "反测哨兵 T3 = ${SENT}（门没被放宽）" ;;
  done)                   bad "反测哨兵 T3 = done —— **门被放宽了**，系统失去可信度" ;;
  *)                      huh "找不到反测哨兵 T3（判据本身丢了）" ;;
esac

# ── A6 无人值守 ──────────────────────────────────────────────
echo
echo "A6 · 无人值守（人不在也在推进）"
if launchctl print "gui/$(id -u)/${CORTEX_LAUNCHD_LABEL:-com.cortex.loop}" >/dev/null 2>&1; then
  ok "主时钟已装载（launchd）"
else
  bad "主时钟没装载 —— 只能靠人开会话才推进"
fi
BEAT="$HOME/.openclaw/state/cortex-loop.launchd.log"
if [[ -f "$BEAT" ]]; then
  AGE=$(( ($(date +%s) - $(stat -f %m "$BEAT")) / 60 ))
  # 阈值 30 分钟 = 15 分钟间隔的两倍，留一次容错
  if [[ $AGE -le 30 ]]; then ok "上次心跳 ${AGE} 分钟前"
  else                       bad "上次心跳 ${AGE} 分钟前 —— 心跳停了"
  fi
else
  huh "找不到心跳日志（无法判定活性）"
fi

# ── 判决 ─────────────────────────────────────────────────────
echo
echo "════════════════════════════════════════════════════════"
echo "PASS $PASS · FAIL $FAIL · 无法判定 $UNKNOWN"
if [[ $FAIL -gt 0 ]]; then
  echo "判决：**未达标** —— 上面每个 ❌ 都是没做到的具体项"
  exit 1
fi
if [[ $UNKNOWN -gt 0 ]]; then
  # 判不出来不等于通过 —— fail-closed 不是 fail-open
  echo "判决：**未达标** —— 有 $UNKNOWN 项判不出来，样本不足不算过"
  exit 1
fi
echo "判决：达标"
exit 0
