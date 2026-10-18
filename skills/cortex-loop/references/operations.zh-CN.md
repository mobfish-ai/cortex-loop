[English](operations.md) | 简体中文

# cortex-loop 运维手册（新增线 / 时钟部署 / 完整命令表 / 共栖索引）

> **何时该读**：要新开一条方向线、要装或核对三个时钟、要一份完整命令 cheatsheet、
> 或要找「这套东西还有哪些相关文档」。
> **上级**：[[cortex-loop/SKILL|SKILL.md]]

---

## 新增一条方向线（SOP）

1. `mkdir brain-network/directions/<line>/`
2. 写 `INTENT.md` —— frontmatter 必含 `line · status · created · updated · claim · success_criteria · out_of_scope · related`，正文七问段 `Why / Done / Proof / Anti / Bounds / Trade / Unknown`
3. 在 [[CLOCK]] 加一行：**`executor` 一律先写 `human`**（安全默认，先投递不执行）
4. `bin/cortex-loop decompose --line <line>` → 看 `TASKS.proposed.md` 对不对 → `--apply` 并入
5. `bin/cortex-loop reconcile` 确认 DRIFT=0
6. 跑几轮 human 看着对了，再把 `executor` 改成 `claude` / `codex` / `cheap`
7. **L2 headless（acp-lane）**：整线写 `CLOCK.executor=acp-lane`；或单任务 `requires_executor=acp-lane`（优先于线默认）。终端直跑：`bash bin/acp-policy-client.sh run --topic T --backend grok --cwd /tmp/xxx --prompt "…"`。禁止 cwd=vault 根。验收：`bash bin/verify-acp-l2-grok-mvp.sh`

字段硬规矩见 [[cortex-loop/references/contracts|contracts.md]]。

---

## 三个时钟（launchd · 职责正交）

| 时钟 | 周期 | 干什么 | plist |
|------|------|--------|-------|
| `com.cortex.loop` | **900s** | **推进**任务（做事） | `work-studio/devops/dotfiles/launchd/com.cortex.loop.plist` |
| `com.cortex.pulse` | **3600s** | **体检**健康趋势（P·U·L·S·E 五问） | `…/com.cortex.pulse.plist` |
| `com.cortex.ci` | **每天 09:30** | **约束**不跑偏（全套测试 + 目标锚定） | `…/com.cortex.ci.plist` |

**核对时钟实况**：`bash bin/cortex-trace.sh clocks` · `bin/cortex-loop reconcile`（声明 vs 实际，脱钩报 DRIFT）
选点与 LATCH 依据见 [[cortex-loop/references/architecture|architecture.md]] §五工具为什么正交。

---

## 完整命令 cheatsheet

```bash
# ── 心跳与账本 ──────────────────────────────
bin/cortex-loop tick                                     # 看什么到期（不推进）
bin/cortex-loop tick --auto                              # 真推进（launchd 每 900s 跑这个）
bin/cortex-loop next --line loop-ops --claim             # 拿提示词 + 占坑
bin/cortex-loop submit --line loop-ops --task T2 --result /tmp/r.txt
bin/cortex-loop try-complete --line loop-ops --task T2   # 唯一能写 done
bin/cortex-loop status
bin/cortex-loop idle                                     # 闲置率诚实口径（分母不含睡眠拍）

# ── 自检与对账 ──────────────────────────────
bin/cortex-loop health
bin/cortex-loop reconcile
bin/cortex-loop why                                      # 信任凭什么这么判
bin/cortex-loop value                                    # V1/V2/V3 + 杠杆率

# ── 蜂群 ────────────────────────────────────
bin/cortex-loop swarm                                    # 谁在线、哪条线没人管
bin/cortex-loop sync                                     # ref 层心跳（不碰工作区）
bin/cortex-loop caps                                     # 能力矩阵 + 单点能力告警
bin/cortex-loop lease --line loop-ops
bin/cortex-loop checkin        /  checkin --out          # 主线程接入 / 退出

# ── 去中心化分发 ────────────────────────────
bin/cortex-loop discover --publish
bin/cortex-loop plan  /  claim  /  run  /  result  /  gather --settle

# ── 信任与约束 ──────────────────────────────
bin/cortex-loop trust
bin/cortex-loop attest --executor claude
bin/cortex-loop fault  /  credit
bin/cortex-loop readjudicate                             # 判据改严后重判历史 rejected
bin/cortex-loop model

# ── 五工具（先查工具，别手搓）────────────────
bash bin/cortex-probe.sh list              # 10 个探针，三态 YES/NO/UNKNOWN
bash bin/cortex-trace.sh wiring            # 内部接线图：发现→排序→认领→准入→执行→完成门
bash bin/cortex-trace.sh task <id>         # 一个任务的完整生命周期
bash bin/cortex-trace.sh state / clocks / chain ci / history [天]
bash bin/cortex-dashboard.sh               # 一屏总览（--json 机读 / --watch 常驻 / --md 写 living md）
bash bin/cortex-pulse.sh                   # 周期体检（退出码 2 = 比上次退化）
bash bin/cortex-ci.sh                      # 每日约束（退出码 2 = 目标被改松）

# ── 测试 ────────────────────────────────────
bash bin/cortex-loop-tests/env-parity.sh
bash bin/cortex-loop-tests/suite.sh                      # 36 PASS / 0 FAIL / 1 SKIP（2026-07-29 实跑）
bash bin/cortex-loop-tests/autonomy-acceptance.sh        # A1-A6 自主闭环验收
bash bin/cortex-loop-tests/dimensional-collapse-scan.sh  # 维度坍缩扫描（T7 机械后盾）

# ── 长跑任务脱离终端（会话崩了不连坐 · E010）──
bin/cortex-loop-detach.sh <名字> "<命令>"
bin/cortex-loop-detach.sh --status <名字>   /  --wait  /  --list

# ── 合同门 ──────────────────────────────────
python3 bin/knowledge-contract-gate.py check-path brain-network/directions/CLOCK.md --strict
python3 bin/knowledge-contract-gate.py check-path skills/cortex-loop/SKILL.md
```

---

## 关联文档（共栖索引）

| 类型 | 路径 | 说明 |
|------|------|------|
| **总纲报告** | [[cortex-loop-intent]] | canonical reading entry：意图 / 三分 / SHIFT / 红→绿实测 7 项 |
| **蜂群总纲** | [[brain-network/directions/loop-ops/CHARTER-SWARM\|CHARTER-SWARM]] | 目标 G1–G6 / 范围 / out_of_scope；**ci 拿它核对目标没被改松** |
| **期待清单** | [[cortex-loop/EXPECTATIONS\|EXPECTATIONS.md]] | 要做但一直还没做到的（机读 `--json`） |
| 试点线产出 | [[cortex-loop-cron-error-triage]] | loop-ops T1：10 条 error job 五类根因 |
| 引擎 | `bin/cortex-loop` | python3，零 LLM（07-28 收盘 1093 行 → 07-29 4125 行） |
| 肌肉 | `bin/cortex-loop-adapters/{human,claude,codex,ollama,mock}.sh` | 唯一调 LLM 的通道 |
| 五工具 | `bin/cortex-{probe,trace,dashboard,pulse,ci}.sh` | 见 SKILL.md §工具箱 |
| 辅助 | `bin/cortex-loop-detach.sh` · `bin/cortex-loop-mcp.py` | tmux 脱离终端 · MCP 出口 |
| 三时钟 | `work-studio/devops/dotfiles/launchd/com.cortex.cortex-{loop,pulse,ci}.plist` | 900s / 3600s / 每天 09:30 |
| 测试 | `bin/cortex-loop-tests/suite.sh` + `fixtures/negtest-*.py` | 8 个负向测试，每个经破坏性验证「真的会红」 |
| 调度声明 | [[CLOCK]] | 改这张表 = 改调度 |
| 试点线 | [[brain-network/directions/loop-ops/INTENT\|loop-ops INTENT]] · [[brain-network/directions/loop-ops/INTENT-P2\|INTENT-P2]] · [[brain-network/directions/loop-ops/TASKS\|TASKS]] | 环修自己的地基 |
| 合同注册 | [[knowledge-contract-registry]] §4.12 / §4.12a | 见 [[cortex-loop/references/contracts\|contracts.md]] |
| 协作定律 | [[mobfish-six-laws]] | C1/C2/C3 三关 + V1/V2/V3 价值三律的真相源 |
| 错题本 | [[cortex-loop/ERRORS\|ERRORS.md]] | E001–E015，含「静默降级比报错更危险」 |
| 建设日记 | [[cortex-loop/JOURNAL\|JOURNAL.md]] | 07-28 从 0 到双端蜂群 · 07-29 从蜂群到自主闭环 |

---

## Nav

[[cortex-loop/SKILL|SKILL.md]] · [[cortex-loop/references/commands|commands]] · [[cortex-loop/references/architecture|architecture]] · [[cortex-loop/references/swarm|swarm]] · [[cortex-loop/references/contracts|contracts]]

---

<!-- cortex:map-backlink d-6907ff16c7030089e243be51 -->
关联地图：[[skills/cortex-loop/MAP|Cortex Loop 全景地图]]
