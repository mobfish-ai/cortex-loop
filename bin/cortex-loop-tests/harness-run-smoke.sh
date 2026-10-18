#!/usr/bin/env bash
# 验证 cortex-loop harness-run 子命令真实驱动姊妹仓库 cortex-harness/packages/agent-runtime。
# 2026-08-21 HANDOFF Q2 done_when："从 Skill 发起一次运行 … 且有测试断言"。
#
# 三态而非二态：cortex-harness 是姊妹仓库（不在 ob1 版本控制内），机器上没有它
# 或没有满足 engines(>=24.0.0 <25) 的 node 都不是本仓代码缺陷 —— 判 SKIP 而不是 FAIL。
# 只有「环境齐全但接线跑不通」才判 FAIL（真回归）。
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
CORTEX_LOOP="$ROOT/bin/cortex-loop"

HARNESS_DIR="${CORTEX_HARNESS_DIR:-$HOME/cortex-harness}"
if [[ ! -d "$HARNESS_DIR" ]]; then
  echo "SKIP harness-run-smoke：本机无 ${HARNESS_DIR}（姊妹仓库未检出，非代码缺陷）"
  exit 0
fi

OUT="$(python3 "$CORTEX_LOOP" harness-run --json --timeout 60 "harness-run-smoke test" 2>&1)"
rc=$?

if grep -q '"reason": "node_v24_missing"' <<<"$OUT"; then
  echo "SKIP harness-run-smoke：本机无满足 cortex-harness engines(>=24.0.0 <25) 的 node（非代码缺陷）"
  exit 0
fi

if [[ $rc -ne 0 ]]; then
  echo "FAIL harness-run-smoke：退出码 $rc"
  echo "$OUT"
  exit 1
fi

if ! grep -q '"ok": true' <<<"$OUT"; then
  echo "FAIL harness-run-smoke：ok≠true"
  echo "$OUT"
  exit 1
fi

if ! grep -q '"status": "succeeded"' <<<"$OUT"; then
  echo "FAIL harness-run-smoke：agent-runtime 返回的 result.status ≠ succeeded"
  echo "$OUT"
  exit 1
fi

echo "PASS harness-run-smoke：ob1 → cortex-harness/agent-runtime 接线可达"
