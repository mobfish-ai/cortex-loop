#!/usr/bin/env bash
# cortex-loop:requires-env PATH HTTP_PROXY HTTPS_PROXY
# 说明：codex CLI 同样需要出网代理
# cortex-loop adapter: codex — 必须走 bin/codex-validate.sh 封装（禁裸 codex exec）
# 约定接口：$1=提示词文件  $2=结果文件
set -uo pipefail
PROMPT="$1"; RESULT="$2"
OB1_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
WORKDIR="${CORTEX_WORKTREE:-$OB1_ROOT}"
if [[ "${CORTEX_REQUIRE_WORKTREE:-0}" == "1" && -z "${CORTEX_WORKTREE:-}" ]]; then
  printf '[adapter] codex rc=2 reason=missing-CORTEX_WORKTREE\n' > "$RESULT"
  exit 2
fi
[[ -d "$WORKDIR" ]] || { printf '[adapter] codex rc=2 reason=invalid-worktree\n' > "$RESULT"; exit 2; }
if [[ "${CORTEX_REQUIRE_WORKTREE:-0}" == "1" && "$(cd "$WORKDIR" && pwd -P)" == "$(cd "$OB1_ROOT" && pwd -P)" ]]; then
  printf '[adapter] codex rc=2 reason=root-worktree-forbidden\n' > "$RESULT"
  exit 2
fi
TOPIC="cortex-loop-$(basename "$PROMPT" .prompt)"

cd "$WORKDIR" || exit 1
bash "$OB1_ROOT/bin/codex-validate.sh" --stakes cross-file "$TOPIC" "$PROMPT" 25 > /dev/null 2>&1
rc=$?
OUT="/tmp/panel-$TOPIC/codex.out"
if [[ -s "$OUT" ]]; then
  cp "$OUT" "$RESULT"
else
  echo "[adapter] codex 无输出（退出码 ${rc}）" > "$RESULT"
fi
exit $rc
