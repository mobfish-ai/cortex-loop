#!/usr/bin/env bash
# cortex-loop-doctor — 一键跑 pipeline 健康探针（只读，默认不清理）
#
# 2026-07-31 从「日额度满 / 僵尸 tick / artifact 不过门 / 15min 空等」检修路径沉淀。
# 退出码：0=关键探针全 YES  1=有 NO  2=有 UNKNOWN 无 NO（探不清）
#
# 用法：
#   bin/cortex-loop-doctor.sh
#   bin/cortex-loop-doctor.sh --json
#   bin/cortex-loop-doctor.sh --fix   # 先跑 cleanup（非 force）
#   bin/cortex-loop-doctor.sh --line cortex-immune
#   bin/cortex-loop-doctor.sh --promote          # NO 缺陷类探针 → task-add（IMM-T46）
#   bin/cortex-loop-doctor.sh --promote --dry-run
#
# 跑批效率报告（另工具）：
#   bin/cortex-loop-run-report.sh --line cortex-immune --id-min 34 --id-max 44
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT" || exit 2

JSON=0
FIX=0
PROMOTE=0
PROMOTE_DRY=0
LINE=cortex-immune
while [ $# -gt 0 ]; do
  case "$1" in
    --json) JSON=1; shift ;;
    --fix) FIX=1; shift ;;
    --promote) PROMOTE=1; shift ;;
    --dry-run) PROMOTE_DRY=1; shift ;;
    --line) LINE="${2:?}"; shift 2 ;;
    -h|--help) sed -n '2,16p' "$0"; exit 0 ;;
    *) echo "unknown $1" >&2; exit 2 ;;
  esac
done

PROBE=bin/cortex-probe.sh
[ -x "$PROBE" ] || { echo "UNK missing $PROBE"; exit 2; }

if [ "$FIX" -eq 1 ]; then
  bash bin/cortex-loop-cleanup-stuck-tick.sh 2>&1 || true
fi

# 每项：probe名 + 可选参数数组用 shell 词拆
run_one() {
  local name="$1"; shift
  local out rc st
  out="$(bash "$PROBE" "$name" "$@" 2>&1)"; rc=$?
  case $rc in
    0) st=YES; yes=$((yes+1)) ;;
    1) st=NO;  no=$((no+1)) ;;
    *) st=UNK; unk=$((unk+1)) ;;
  esac
  one="$(printf '%s' "$out" | tr '\n' ' ' | head -c 200)"
  rows+=("$name|$st|$one")
  printf '%-22s %-4s %s\n' "$name" "$st" "$one"
}

yes=0; no=0; unk=0
rows=()
run_one tick-lock-free
run_one tick-not-zombie 90
run_one daily-budget-ok "$LINE"
run_one launchd-interval-ok 60
run_one health-green
run_one land-artifacts-wired
run_one cheap-no-git
run_one auto-queue-clear "$LINE"
run_one idle-with-ex-gap "$LINE"
run_one beat-fresh "" 3
run_one channel-intake-phase

echo "---"
echo "summary YES=$yes NO=$no UNKNOWN=$unk line=$LINE"

if [ "$JSON" -eq 1 ]; then
  python3 - "$yes" "$no" "$unk" "$LINE" "${rows[@]}" <<'PY'
import json,sys
yes,no,unk,line=int(sys.argv[1]),int(sys.argv[2]),int(sys.argv[3]),sys.argv[4]
items=[]
for row in sys.argv[5:]:
    name,st,detail=row.split('|',2)
    items.append({"probe":name,"state":st,"detail":detail})
print(json.dumps({"yes":yes,"no":no,"unknown":unk,"line":line,"probes":items}, ensure_ascii=False, indent=2))
PY
fi

# IMM-T46：有 NO 时可选自动 promote（缺陷类探针 + short_test，不假绿）
if [ "$PROMOTE" -eq 1 ] && [ "$no" -gt 0 ]; then
  promo_args=(--line "$LINE")
  [ "$PROMOTE_DRY" -eq 1 ] && promo_args+=(--dry-run)
  [ "$JSON" -eq 1 ] && promo_args+=(--json)
  echo "--- promote ---"
  bash bin/cortex-loop-doctor-promote.sh "${promo_args[@]}" || true
fi

if [ "$no" -gt 0 ]; then exit 1; fi
if [ "$unk" -gt 0 ]; then exit 2; fi
exit 0
