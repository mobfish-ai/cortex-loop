#!/usr/bin/env bash
# 维度坍缩扫描器 —— E013 的机械化沉淀（skills/cortex-loop/ERRORS.md）。
#
# 母题（operator 2026-07-29 拍板命名）：真实世界的状态天然是高维的
# （「无数据」≠「读取异常」、「故障」≠「够不着」、「跑着」≠「刚做完」），
# 把这些压成一个低维布尔/状态码，丢的信息恰好是「为什么」。
# 今天在完全不相关的 5 处代码里现形，全部同一个模子。
#
# 本脚本不自动修 —— 判据本身需要人读上下文才能确认是不是真坍缩，
# 硬编码"自动修"反而会制造新的假阳性。只做**候选发现**，报出来交人判断。
#
# 用法：bash bin/cortex-loop-tests/dimensional-collapse-scan.sh [文件...]
#   不给参数默认扫 bin/cortex-loop
# 退出码：0=无候选  1=有候选（不代表真的是 bug，代表"值得看一眼"）

set -uo pipefail
cd "$(dirname "$0")/../.." || exit 2
TARGETS=("$@")
[[ ${#TARGETS[@]} -eq 0 ]] && TARGETS=(bin/cortex-loop)

FOUND=0

echo "维度坍缩候选扫描 · E013 特征模式"
echo "════════════════════════════════════════════════════"

for f in "${TARGETS[@]}"; do
  [[ -f "$f" ]] || continue

  # 特征①：`X if code == 0 else <falsy>` —— "成功但为空" 与 "失败" 是否共用同一 falsy
  # 这不必然是 bug（很多场景两者确实等价），但值得人核对一遍。
  hits1=$(grep -nE 'if code == 0 else (""|\[\]|None|False)' "$f" || true)
  if [[ -n "$hits1" ]]; then
    echo
    echo "── $f · 特征①「成功空结果」与「失败」共用同一 falsy 值 ──"
    echo "$hits1" | sed 's/^/  /'
    FOUND=1
  fi

  # 特征②：同一个函数体内出现 ≥2 次 `return False, ""`（或等价的空 falsy）
  # —— 大概率是把多种不同性质的失败原因压成了同一个返回值。
  hits2=$(awk '
    /^def / { fn=$0; cnt=0; buf="" }
    /return False, ""/ { cnt++; buf = buf sprintf("    L%d: %s\n", NR, $0) }
    /^def / && prevfn!="" && prevcnt>=2 { print prevfn"\n"prevbuf }
    { prevfn=fn; prevcnt=cnt; prevbuf=buf }
    END { if (cnt>=2) print fn"\n"buf }
  ' "$f" | grep -B1 "L[0-9]*:.*return False" | grep "^def " || true)
  if [[ -n "$hits2" ]]; then
    echo
    echo "── $f · 特征②函数内 ≥2 处 return False,\"\" （同一 falsy 表达多种失败原因）──"
    echo "$hits2" | sed 's/^/  /'
    FOUND=1
  fi

  # 特征③：`if X: ... GREEN/OK else: ... RED/FAIL` 里 else 分支合并了多个不同来源
  # 的判断（用「and」或多个条件合并成一次判断）——粗筛，命中不代表就是 bug。
  hits3=$(grep -nE '(RED|FAIL|GREEN|OK)["\x27].*\bif\b.*\band\b' "$f" || true)
  if [[ -n "$hits3" ]]; then
    echo
    echo "── $f · 特征③状态判定里用 and 合并了多个条件（核对是否该分开报）──"
    echo "$hits3" | sed 's/^/  /'
    FOUND=1
  fi
done

echo
echo "════════════════════════════════════════════════════"
if [[ $FOUND -eq 1 ]]; then
  echo "有候选 —— 不代表都是 bug，代表值得人核对「这里是否该展开成三态」。"
  echo "判据：真实世界这里有几种性质不同的状态？如果 ≥2 种被压成 1 种，就是本条。"
  exit 1
else
  echo "无候选。"
  exit 0
fi
