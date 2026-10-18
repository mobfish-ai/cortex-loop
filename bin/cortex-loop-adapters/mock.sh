#!/usr/bin/env bash
# cortex-loop adapter: mock — only checks structural acceptance; calls no model
cat > "$2" <<'OUT'
| M1 | valid sample: write a checklist | pending | - | checklist covers every item | padding with missing items | reports/2026-07-28/_standalone/mock.md | bash bin/cortex-loop-tests/mock.sh | - | 0 | 2026-07-28 | - |
| M2 | sample missing negative space | pending | - | has a completion standard | - | reports/x.md | bash t.sh | - | 0 | 2026-07-28 | - |
| M3 | sample with an illegal status | done | - | standard | cheating | reports/y.md | bash t.sh | - | 0 | 2026-07-28 | - |
OUT
echo mock ok
