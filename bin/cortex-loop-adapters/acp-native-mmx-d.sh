#!/usr/bin/env bash
# cortex-loop adapter: acp-native:mmx-d
#
# mmx-d reuses the bounded native ACP bridge. Backend selection stays explicit
# here so the task-facing executor and result footer remain mmx-d.
set -uo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export CORTEX_ACP_BACKEND="mmx-d"
exec bash "$DIR/acp-native-mmx-a.sh" "$@"
