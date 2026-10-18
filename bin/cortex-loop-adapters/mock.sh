#!/usr/bin/env bash
# cortex-loop adapter: mock — 只用于验证结构验收逻辑，不调任何模型
cat > "$2" <<'OUT'
| M1 | 合格样本：写一份清单 | pending | - | 清单覆盖全部条目 | 漏项凑数 | reports/2026-07-28/_standalone/mock.md | bash bin/cortex-loop-tests/mock.sh | - | 0 | 2026-07-28 | - |
| M2 | 缺负空间的样本 | pending | - | 有完成标准 | - | reports/x.md | bash t.sh | - | 0 | 2026-07-28 | - |
| M3 | 非法状态的样本 | done | - | 标准 | 作弊 | reports/y.md | bash t.sh | - | 0 | 2026-07-28 | - |
OUT
echo mock ok
