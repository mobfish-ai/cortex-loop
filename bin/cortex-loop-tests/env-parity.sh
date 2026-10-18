#!/usr/bin/env bash
# env-parity — 跨环境一致性机械门（ERRORS E012 硬化执行器）· runtime 无关版
#
# 为什么存在：2026-07-29 一晚同一根因咬了三次，全是「交互式 shell 能跑、
# 无人值守环境跑不了」，因为调度器不继承登录 shell 的环境变量：
#   ① ollama pull 断在 79%    → 缺 HTTPS_PROXY
#   ② worker systemd 全失败  → 缺 ANTHROPIC_*
#   ③ Mac launchd 7 次 403    → 缺 HTTP(S)_PROXY
# 第一次撞到时只在当次命令里补了代理，没横向推广到调度器配置，于是换个马甲又咬两次。
#
# ⚠️ runtime 无关设计（operator 2026-07-29 要求）：
#   本门**不硬编码任何 runtime 名**（不写死 claude/ANTHROPIC_*），而是：
#     1. 扫 bin/cortex-loop-adapters/*.sh 里的 `# cortex-loop:requires-env A B C` 自声明
#     2. 取并集 = 本节点无人值守跑通所需的全部变量
#     3. 与本机实际调度器配置（launchd plist / systemd unit，按存在性自动识别）比对
#   加任何新 runtime（Codex/Gemini/自研）只需在它的 adapter 头部写一行自声明，
#   **本文件一个字都不用改**。
#   只比对变量名是否声明，绝不读取或打印任何值（密钥安全）。
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ADAPTERS="$ROOT/bin/cortex-loop-adapters"
FAIL=0

# ── 1. 从 adapter 自声明收集需求（runtime 无关的真相源）────────────────
declare -a NEEDED=()
for f in "$ADAPTERS"/*.sh; do
  [[ -f "$f" ]] || continue
  line=$(grep -m1 '^# cortex-loop:requires-env' "$f" 2>/dev/null) || continue
  for v in ${line#\# cortex-loop:requires-env }; do
    [[ " ${NEEDED[*]:-} " == *" $v "* ]] || NEEDED+=("$v")
  done
done

if [[ ${#NEEDED[@]} -eq 0 ]]; then
  echo "SKIP  没有任何 adapter 声明 requires-env —— 无从校验"
  echo "      新 runtime 接入时请在 adapter 头部加：# cortex-loop:requires-env VAR1 VAR2"
  exit 0
fi
echo "需求并集（来自 adapter 自声明，非硬编码）：${NEEDED[*]}"
echo

# ── 2. 自动识别本机调度器类型，比对其配置 ──────────────────────────────
if [[ -n "${CORTEX_LAUNCHD_PLIST:-}" ]]; then
  PLIST="$CORTEX_LAUNCHD_PLIST"
elif [[ -f "$ROOT/work-studio/devops/dotfiles/launchd/com.cortex.loop.plist" ]]; then
  PLIST="$ROOT/work-studio/devops/dotfiles/launchd/com.cortex.loop.plist"
else
  PLIST="$ROOT/examples/launchd/com.cortex.loop.plist"
fi
if [[ -n "${CORTEX_SYSTEMD_UNIT:-}" ]]; then
  UNIT="$CORTEX_SYSTEMD_UNIT"
elif [[ -f "$ROOT/work-studio/devops/dotfiles/systemd/cortex-loop.service" ]]; then
  UNIT="$ROOT/work-studio/devops/dotfiles/systemd/cortex-loop.service"
else
  UNIT="$ROOT/examples/systemd/cortex-loop.service"
fi
CHECKED=0

if [[ -f "$PLIST" ]] && command -v launchctl >/dev/null 2>&1; then
  CHECKED=1
  echo "[launchd] $PLIST"
  for var in "${NEEDED[@]}"; do
    if grep -q "<key>${var}</key>" "$PLIST"; then
      echo "  PASS  声明了 $var"
    else
      echo "  FAIL  缺 $var —— 无人值守调用会失败（E012 同款）"
      FAIL=$((FAIL+1))
    fi
  done
fi

if [[ -f "$UNIT" ]]; then
  CHECKED=1
  echo "[systemd] $UNIT"
  # systemd 侧允许两种合法形态：显式 Environment= 或 source 外部环境脚本
  if grep -qE '^\s*(ExecStart|ExecStartPre)=.*(source|\.)\s+\S+\.sh' "$UNIT"; then
    echo "  PASS  通过 source 外部脚本注入环境（变量有来源，不在本文件硬编码）"
  else
    for var in "${NEEDED[@]}"; do
      if grep -qE "^Environment=${var}=" "$UNIT"; then
        echo "  PASS  声明了 $var"
      else
        echo "  FAIL  缺 $var 且未 source 环境脚本（E012 同款）"
        FAIL=$((FAIL+1))
      fi
    done
  fi
fi

[[ $CHECKED -eq 0 ]] && { echo "SKIP  本机未找到可校验的调度器配置"; exit 0; }

echo
if [[ $FAIL -eq 0 ]]; then
  echo "env-parity PASS —— 调度器环境声明覆盖全部 adapter 需求"
  exit 0
fi
echo "env-parity FAIL=$FAIL —— 修法见 skills/cortex-loop/ERRORS.md E012"
exit 1
