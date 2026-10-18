#!/usr/bin/env bash
# cortex-loop adapter: acp-native:mmx-b
#
# mmx-b reuses the bounded native ACP bridge. Backend selection stays explicit
# here so the task-facing executor and result footer remain mmx-b.
set -uo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export CORTEX_ACP_BACKEND="mmx-b"
exec bash "$DIR/acp-native-mmx-a.sh" "$@"
