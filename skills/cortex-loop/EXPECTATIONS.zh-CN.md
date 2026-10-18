---
machine_reader: bin/cortex-loop-expectations.py
skill: cortex-loop
status: active
type: expectations
updated: "2026-07-30"
---
[English](EXPECTATIONS.md) | 简体中文

# cortex-loop 期待清单（能力缺口与结项证据）

> **这不是 TODO。** TODO 是「已经拆好、有人认领、有 `short_test`」的活 —— 那些住在
> [[brain-network/directions/loop-ops/TASKS|TASKS.md]]，由环自己推。
> **本文件装的是「知道该有的能力及其当前证据状态」**。`met` 保留结项证据，
> `gap/unknown` 只有同时具备 owner 与 `short_test` 才能进入自动执行候选；
> 否则只负责让缺口持续可见，不会被 `tick` 猜着推进。
>
> **为什么放在 `skills/cortex-loop/` 而不是 `directions/loop-ops/`**：
> 期待是「这套能力还差什么」，属 Skill 家族的第四个成员 ——
> [[cortex-loop/SKILL|SKILL]] 记已具备 · [[cortex-loop/ERRORS|ERRORS]] 记已犯的错 ·
> [[cortex-loop/JOURNAL|JOURNAL]] 记已发生的 · **本文件记还没具备的**。
> 放进 `directions/loop-ops/` 会撞两件事：① `TASKS.md` 是**机器消费**的账本，
> 混进没判据的条目会被当成待派任务；② `CHARTER-SWARM.md` 拥有 S1 G1–G6 的定义权，
> 本文件只**引用**阶段目标，不重复定义。终局方向归 [[cortex-loop/INTENT|INTENT]]。
>
> **机器怎么读**：`python3 bin/cortex-loop-expectations.py --json`
> 退出码 `0`=全部 met / `1`=有 gap / `2`=有 unknown（三态，UNKNOWN 不倒向任何一边）。

---

## A · 阶段证据状态

> 本节只追踪 [[brain-network/directions/loop-ops/CHARTER-SWARM|CHARTER-SWARM]] 的 S1 阶段指标；终局北极星见 [[cortex-loop/INTENT|INTENT]]。

| id | 期待 | 目标 | 现状 | 状态 | 缺口 / 前置 | owner | short_test |
|----|------|------|------|------|-------------|-------|------------|
| EX01 | G2 机械过门率 | 24 小时滚动窗、最小样本 15、目标 ≥90% | 已批准；全历史累计仅作战绩，不作目标 | **met** | origin 可读的滚动 cohort；`python3 bin/cortex-metrics.py --json` |
| EX02 | G1 自愈闭环率 | frozen eligible discovery 与 passed result 同 lineage | origin discovery/result/learning 三源已读通，真机 clock-auto lineage 已形成；当前数量由量具实时读取 | **met** | `BASELINE` 只表示滚动窗口尚未批准，不再误报“没有 cohort” | cortex-loop | `python3 bin/cortex-metrics.py --json` |
| EX03 | 蜂群整体信任 | ≥0.70（L3） | 0.195（L1）= 均值 0.435 × 短板因子 0.45 | gap | 短板因子被主线程拖累，见 EX04 | cortex-loop | `python3 bin/cortex-loop trust --no-fetch` |
| EX04 | 主线程信任 `orchestrator-laptop` | ≥0.70 | 0.195 —— **全群最低** | gap | 提分只有 `credit`（自主闭环）与过门率两条路；禁调阈值 | cortex-loop | `python3 bin/cortex-loop trust --no-fetch` |
| EX05 | 闲置率 | <30% | 根因已修（E015 · 19:40），当日 `idle --json` 报 `idle_pct 0.0` 但 `ran=8` 样本太小 | **unknown** | 需一个完整无人值守窗口复验。**样本不足不算达标**（fail-closed） |
| EX06 | 价值涌现层 V3 | >0 | V1 6 / V2 18 / **V3 0**（杠杆率 75%） | gap | 24 项产出零「产生新能力/新连接」。V3 判据本身是否可机械识别，待验 | cortex-loop | `python3 bin/cortex-loop value` |
| EX07 | L4 自主（人不在仍推进） | A1–A6 全过 | 2026-07-31 `autonomy-acceptance.sh` PASS 10·FAIL 0·UNKNOWN 0 判决达标；证据 `artifacts/t51-autonomy-acceptance.md`（IMM-T51） | **unknown** | A1–A6 证据已落盘；前置 EX03 蜂群信任仍 gap（≈0.47≪0.70）→ fail-closed 不升 met | cortex-loop | `bash bin/cortex-loop-tests/autonomy-acceptance.sh` |

## B · 保安四问的字段缺口（2026-07-29 本次实测发现）

> Skill 层四问已答完（SKILL.md 前 94 行）。**任务层与节点层各缺两问。**
> 查法：`bash bin/cortex-trace.sh task <id>` · `python3 bin/cortex-loop why --node <n>` · `brain-network/directions/_swarm/<node>.md`

| id | 层 | 缺哪一问 | 实测现状 | 状态 | owner | short_test |
|----|----|---------|---------|------|-------|------------|
| EX08 | 任务 | **从哪来** | S1 任务已用 immutable discovery receipt 绑定 `source/candidate`，result 再绑定 `candidate_source/discovery_id`，origin 真机 lineage 已成立 | met | cortex-loop | `python3 bin/cortex-metrics.py --json` |
| EX09 | 节点 | **从哪来** | `loop_node` 画像字段 = node / kind / can_sleep / executors / telegram_reach / last_seen / owns。**无入群时间、无累计样本数** —— 样本数只在 `trust` 运行时现算，不落盘，所以「这台机干过多少活」看画像看不出来 | **met** |
| EX10 | 节点 | **到哪去** | 画像无信任目标字段（这台机该爬到 L 几、还差什么）。G5 只有群体级目标，没有节点级 | **met** |

> **不在本次修**：补字段要动 `bin/cortex-loop`（另有 sub-agent 在改，会冲突）与合同 registry。
> 记在这里正是「知道该有但还没有」的一等公民。

## C · 已知技术债（每条指回原始诚实清单）

| id | 事项 | 状态 | 来源 | owner | short_test |
|----|------|------|------|-------|------------|
| EX11 | `read_ref` / `list_refs` 三态化 —— 把「读到空」当「没有」。**DIMENSIONAL 母题第 5 处、也是最底层**（被调 20 次，claim/plan/result/lease 全经过它） | **met** | `reports/2026-07-29/_standalone/cortex-loop-engine-fixes.md` §六 #6 |
| EX12 | G2 已拆为**累计战绩 + 24 小时滚动 cohort**，最小样本 15、目标 ≥90%，批准证据已落盘 | **met** | `METRICS.json` + `reports/2026-07-31/cortex-loop/metrics-ratification.md`；Dashboard 同时显示累计与滚动 |
| EX13 | `gate=scope-gap` 第三态**真机零实证**，只有 H06 桩测覆盖 | **unknown** | throughput-fix #4。需等真机自然产生一条才算闭环 |
| EX14 | 双节点下「一次失败让给别的节点」= 一件活最多被试 2 次，之后在所有计划里永久沉底 | **met** | throughput-fix #7。可能需要「冷却后重试」而非永久让位 |
| EX15 | 长任务跑满 >900s 时心跳无中间写入 → 外部看像掉线（实测 25min 单任务导致 pulse 判 `P ❌ 心跳=38分钟`）。**「在干重活」和「卡死了」又一处二态该展开三态** | **met** | throughput-fix §新发现的副作用 #8 |
| EX16 | worker git-sync 死锁（落后 302 / 领先 6 未推 / 70 脏 / 84 stash）→ **worker 判 done 的产出推不到 origin，传播门（T8）对它形同虚设** | gap | engine-fixes §六 #1。另一条工作线「先停再修」 |
| EX17 | `suite.sh` F15 幂等检查不抗并发：15 分钟真时钟会在跑测试时改 `TASKS.md` 造成假红（实测遇 1 次） | **met** | engine-fixes §六 #4 |
| EX18 | `bin/auto-mount.sh` 的 `OB1_ROOT` 硬编码 laptop 路径，worker 跑不了 | **met** | throughput-fix #6（不在该 lane 内，只记不代做） |
| EX19 | 预算编排未实施。已知不对称：laptop 订阅制**无 usage API**，只能用抑制状态 + 窗口计时代理 | gap | CHARTER-SWARM §Unknown · 设计见 `cortex-loop-handoff.md` §四 | cortex-loop | `test -s reports/2026-07-29/_standalone/cortex-loop-handoff.md && grep -qE '预算编排|usage API|窗口计时' reports/2026-07-29/_standalone/cortex-loop-handoff.md` |
| EX20 | `claim → run → write result` 的 run-v1 receipt、origin 可达性、learning 精确绑定与写失败不前进 | **met** | clock-auto 真机 canary 已形成完整 discovery/result/learning lineage；Dashboard 仍只称 canary，不冒充 production | cortex-loop | `python3 bin/cortex-metrics.py --json` |

---

## D · 候选律（走 [[latch-doctrine|LATCH]] 判据，够不上就不硬立）

> LATCH 门槛两条同时满足才建：**① 同一模式 ≥3 次 ② 已有文字提醒但无效**。
> 只满足 ① = 写进 guide/错题本，不占 Layer 0 的位置。

| 候选 | ① ≥3 次？ | ② 提醒无效？ | 判定 |
|------|----------|-------------|------|
| **每道新门首日必被自己的实测打脸** | ✅ 传播门 v1→v2（9:00 立 → 10:52 证伪）· PULSE（8:56 立 → 9:09 修首日两坑）· `991016f78` 负向测试逮到自己的修复是死的 | ❌ **从没被写成提醒过**，今天才第一次成文 | **不立律**。且它已有机械后盾（suite 每个负向测试必经破坏性验证）—— 机制在，缺的只是文字。已写入 [[cortex-loop/references/tenets\|references/tenets.md]] §元模式，等第 4 次或「机制在仍被绕过」的证据再升格 |
| **改判不删账** | ✅ `readjudicate`（用当前判据重判历史 rejected，非特赦）· `moot` 第四态独立命名空间不进功劳账 · `fault`/`credit` 双向计分不相互抵消 | ❌ 这三处**都是重复做对**，不是重复违规。LATCH 管的是违规模式 | **不立律**。它是 DIMENSIONAL 的推论（终态不能坍缩成「删掉」）+ 账本层设计原则。已写入 [[cortex-loop/references/architecture\|references/architecture.md]] §账本原则 |
| **分母虚高会让永远归不了零的债看起来像欠债** | ✅ 孤岛 56→0（分母含不该含的）· `idle` 墙钟当分母 → 59% 虚高 · 过门率全历史累计分母（EX12） | ✅ **`idle` 的帮助文字已明写「别用墙钟当分母」，而过门率照样在用全历史分母** —— 这就是「写了提醒、另一处照犯」 | **✅ 已达 LATCH 门槛，但本轮不由我立**。C·onstruct 要求先建 Hook 再写文字，而 Hook 规格见下 —— 它要碰 `cortex-pulse.sh` 的口径，正撞 EX12 的利益冲突（被这个数字考核的人不该改这个数字的口径）。**交 operator 指派执行方。** |

**候选 3 的 Hook 规格（已想清楚，可直接交付给执行方 · 不改任何数字）**：
一个**只读**扫描器，断言「任何被发布的比率，其分母口径必须显式声明」——
grep 出所有产出百分比的位置（`cortex-pulse.sh` / `cortex-dashboard.sh` / `cortex-loop idle|value|trust`），
逐个检查是否在同一文件里有对应的 `# denominator:` 声明行；缺声明即报红。
**它只查有没有说清楚，不判断口径对不对** —— 所以不构成利益冲突。

---

## Nav

[[cortex-loop/INTENT|INTENT.md]] · [[cortex-loop/SKILL|SKILL.md]] · [[cortex-loop/ERRORS|ERRORS.md]] · [[cortex-loop/JOURNAL|JOURNAL.md]] · [[brain-network/directions/loop-ops/CHARTER-SWARM\|CHARTER-SWARM]] · [[cortex-loop/references/tenets|references/tenets]]

*建立 2026-07-29 · 每条都指回 commit / 报告 / 命令回显，无一条凭印象*

---

<!-- cortex:map-backlink d-8ba45546f8116b1686496d6d -->
关联地图：[[skills/cortex-loop/MAP|Cortex Loop 全景地图]]
