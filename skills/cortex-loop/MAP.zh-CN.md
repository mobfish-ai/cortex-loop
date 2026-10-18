---
name: cortex-loop-map
title: cortex-loop 全景地图 — 资产清单 + 观点索引
type: reference
status: active
created: 2026-07-29
updated: 2026-07-29
host: cortex-loop
related:
  - "[[cortex-loop/SKILL]]"
  - "[[cortex-loop/ERRORS]]"
  - "[[cortex-loop/EXPECTATIONS]]"
  - "[[cortex-loop/JOURNAL]]"
  - "[[CHARTER-SWARM]]"
tags: [cortex-loop, map, panorama, index]
---
[English](MAP.md) | 简体中文

# cortex-loop 全景地图

> **这份文件回答一个问题**：cortex-loop 这套东西**一共由哪些部件构成、它们怎么咬合、
> 以及我们在建它的过程中想明白了什么**。
> 文件体积为 2026-07-29 23:22 实测；§6 蜂群指标为 22:55 实测清点。均非估算。
> **它不重复定义任何东西** —— 每格都指向真相源，本文件只负责「让你一眼看见全部」。
>
> **给 Codex / 外部 agent**：先读 [[cortex-loop/MAP#12-资产总表机读友好|§12 资产总表]]（扁平一行一资产，
> 含角色与双向对端），再按需下钻。**不要**从 §0 结构图开始推敲 —— 图是给人看的，表才是给你看的。

---

## 0 · 一屏结构

```
                    ┌─────────────── 意图层（人定方向）───────────────┐
                    │  cortex-loop/INTENT.md       终局方向（唯一 SSOT）  │
                    │  CHARTER-SWARM.md            S1 运行目标与阈值      │
                    │  METRICS.json               S1 机器指标合同      │
                    └──────────────────────┬───────────────────────────┘
                                           │ 约束
   ┌───────────────────────────────────────┼───────────────────────────────────┐
   │                            引擎层（机器执行）                              │
   │   bin/cortex-loop  216KB / 31 子命令  ← 唯一能写 done 的地方               │
   │   └ adapters/  claude · codex · ollama · human · mock （肌肉，可换 runtime）│
   └───────────────────────────────────────┬───────────────────────────────────┘
                     ┌─────────────────────┼─────────────────────┐
                     │                     │                     │
              ┌──────┴──────┐      ┌───────┴───────┐     ┌───────┴────────┐
              │  账本层      │      │   心跳层       │     │  观测层        │
              │ git refs ×7  │      │ 3 个时钟       │     │ 五件套 + 2 辅助 │
              │ 177 条记录   │      │ 零 LLM         │     │ 人机同读       │
              └──────┬───────┘      └───────┬───────┘     └───────┬────────┘
                     └──────────────────────┴─────────────────────┘
                                           │ 产生经验
   ┌───────────────────────────────────────┴───────────────────────────────────┐
   │                       沉淀层（下次不再犯）                                  │
   │  ERRORS.md E001–E015 · Layer 0 六律 · suite 回归 · EXPECTATIONS 机读缺口   │
   └───────────────────────────────────────────────────────────────────────────┘
```

**读法**：意图层是**人**说了算，引擎层是**机器**说了算，中间靠**账本**对账。
观测层的存在理由是让这两层**看同一份真相**（[[glassbox-doctrine|GLASSBOX 律]]）。

---

## 1 · 引擎与工具（`bin/`）

| 文件 | 体积 | 干什么 | 什么时候用它 |
|------|------|--------|-------------|
| `cortex-loop` | 216 KB | **引擎**。31 个子命令，唯一能写 `done` 的地方 | 一切推进 / 认领 / 判定 |
| `cortex-dashboard.sh` | 29 KB | 白盒总览 + `--json` 机读 + `--watch` | 「现在什么情况」 |
| `cortex-pulse.sh` | 9.7 KB | P·U·L·S·E 五问，每小时时钟 | 定期自检，退出码 0/1/2 |
| `cortex-probe.sh` | 9.5 KB | **10 个三态探针**（YES/NO/**UNKNOWN**） | 要判「有/无」「成/败」 |
| `cortex-trace.sh` | 8.9 KB | 白盒下钻 state/clocks/wiring/chain/task | 「为什么这么判」 |
| `cortex-ci.sh` | 5.6 KB | 每日 CI：回归 + **目标锚定**（退出 2 = 跑偏） | 防 regression 与偏航 |
| `cortex-loop-expectations.py` | 5.0 KB | EXPECTATIONS 机读器 | 「还差什么没做到」 |
| `cortex-capability-bundle.py` | 4.8 KB | 节点能力打包 | 按能力派活 |
| `cortex-loop-mcp.py` | 4.9 KB | MCP 接口 | 外部 agent 接入 |
| `cortex-loop-detach.sh` | 2.7 KB | 长命令脱离终端 | 防 E010 会话崩全灭 |

**肌肉（adapter，可换 runtime）**：`claude.sh` · `codex.sh` · `ollama.sh` · `human.sh` · `mock.sh`

> **设计要点**：工具全部**三态输出**，`UNKNOWN` 绝不倒向 `NO` ——
> 倒向健康是 fail-open，倒向故障是过度保守。见 [[dimensional-expansion-doctrine]]。

---

## 2 · 账本层（git refs · 实测 177 条）

| 命名空间 | 条数 | 含义 |
|---------|------|------|
| `refs/swarm/cortex/claim/` | 61 | 认领（git ref CAS 当分布式锁） |
| `refs/swarm/cortex/result/` | 52 | 产出结果 |
| `refs/swarm/cortex/plan/` | 36 | 计划 |
| `refs/swarm/cortex/moot/` | 16 | 空转（判据已满足，不烧额度不计分） |
| `refs/swarm/cortex/incident/` | 8 | 事故 |
| `refs/swarm/cortex/beat/` | 3 | 心跳 |
| `refs/swarm/cortex/lease/` | 1 | 租约 |

**为什么用 git ref 不用数据库**：`git push <sha>:<ref>` 的 non-fast-forward 拒绝
天然就是 CAS（比较并交换）—— 多机抢锁不需要额外中间件，账本自带审计历史。

**文本账本**：`CLOCK.md`（调度声明）· `loop-ops/TASKS.md`（待办）——
suite 的 F15 用例逐字节校验它们没被测试污染。

---

## 3 · 心跳层（3 个时钟 · 零 LLM）

| 时钟 | 周期 | 职责 | 本机状态 |
|------|------|------|---------|
| `com.cortex.loop` | 15 min | 主推进（tick） | EXIT=0 ✅ |
| `com.cortex.pulse` | 1 h | 健康五问 | EXIT=1（有未达标项，符合预期） |
| `com.cortex.ci` | 每日 | 回归 + 目标锚定 | EXIT=0 ✅ |

**职责正交**：推进的不管健康，健康的不管跑偏，各自失败不互相掩盖。
**时间预算硬约束**：单拍上限必须 `≥600s`（够跑完真任务）且 `<900s`（小于时钟周期，
否则一拍卡死永久占槽）。常驻判据 = suite `H10`。

---

## 4 · Skill 家族（`skills/cortex-loop/`）

| 文件 | 体积 | 回答什么 |
|------|------|---------|
| **INTENT.md** | 5.5 KB | **终局：为何存在、到哪去、人机契约、晋级边界** |
| **SKILL.md** | 17.3 KB | **保安四问**（你是谁 / 从哪来 / 到哪去 / 来干什么）+ T1–T9 铁律 |
| **ERRORS.md** | 32.7 KB | 已经犯过的错（E001–E015） |
| **JOURNAL.md** | 19.9 KB | 建设日记（怎么一步步长成这样） |
| **EXPECTATIONS.md** | 10.0 KB | **还没做到的**（20 条，`--json` 可机读） |
| **MAP.md** | 本文件 | 全景：一共有哪些部件 + 想明白了什么 |

**下沉的细节**（`references/`，按需读，不默认装载）：

| 文件 | 体积 | 何时该读 |
|------|------|---------|
| [[cortex-loop/references/architecture\|architecture.md]] | 12.0 KB | 要改引擎/理解三分架构 |
| [[cortex-loop/references/commands\|commands.md]] | 8.9 KB | 查 31 个子命令的具体用法 |
| [[cortex-loop/references/operations\|operations.md]] | 8.2 KB | 部署/运维/新增方向线 |
| [[cortex-loop/references/tenets\|tenets.md]] | 5.5 KB | 想知道 T1–T9 各自的真实代价 |
| [[cortex-loop/references/contracts\|contracts.md]] | 4.4 KB | 写/改合同字段 |
| [[cortex-loop/references/swarm\|swarm.md]] | 4.2 KB | 多节点、分片、租约、信任 |

---

## 5 · 沉淀层

### 5.1 错题本 E001–E015（15 条）

| # | 一句话 | 母题 |
|---|--------|------|
| E001 | 把「列含义」说明表当数据表 | 口径 |
| E002 | 传错主键 → 静默读到 0 行 | **静默失败** |
| E003 | for-each-ref 格式串转义 → 静默退回文件快照 | **量具** |
| E004 | 本地无 ref 时 rev-parse 返回空 → push 变成删除远端 | **致命 · 静默失败** |
| E005 | health 把「投递失败」当「执行失败」 | **维度坍缩** |
| E006 | 死凭据挂在 fallback 链末尾，长期无人察觉 | 静默降级 |
| E007 | 合盖 → launchd 停跳；「日志连续」被误读成「一直在跑」 | 量具 |
| E008 | 表头被后续表冲空 → 唯一写入口崩溃 | 数据 |
| E009 | CAS 拒绝与网络故障压成同一个返回值 | **维度坍缩** |
| E010 | 长跑进程绑在终端上 → 会话一崩全灭 | 运行时 |
| E011 | 假完成：short_test 复用扫描器退出码 + 验证器失败开放 | **假绿灯** |
| E012 | 跨环境不一致：交互式能跑 ≠ 无人值守能跑 | 环境 |
| E013 | 维度坍缩：压成一个判断，丢掉的是「为什么」 | **维度坍缩** |
| E014 | 空转刷分：判据已满足的任务重跑仍计 passed | **假绿灯** |
| E015 | 认领与执行互相把对方算成负载 → 满载零产出 | 死锁 |

**四个母题反复出现**：静默失败 · 量具不可靠 · 维度坍缩 · 假绿灯。
这四个正是下面六律要挡的东西。

### 5.2 Layer 0 六律（本 Skill 是它们的机械落地面）

```
GROUND 先查（起点）→ DIMENSIONAL 别压扁（建模）→ ATOMIZE 量具可靠（采集）
→ GLASSBOX 人机双读（呈现）→ STEER 循环推进（运转）→ PULSE 定期自检（守恒）
```

| 律 | 短触发器 | 机械后盾 |
|----|---------|---------|
| [[ground-first-doctrine\|GROUND]] | 2414 B | `fault --kind decision-dodge` · `inspection_mode()` |
| [[dimensional-expansion-doctrine\|DIMENSIONAL]] | 2076 B | `dimensional-collapse-scan.sh` |
| [[atomize-tools-doctrine\|ATOMIZE]] | 2068 B | `cortex-probe.sh`（10 探针） |
| [[glassbox-doctrine\|GLASSBOX]] | 2028 B | `cortex-dashboard.sh` · `cortex-trace.sh` |
| [[steer-doctrine\|STEER]] | 2033 B | `orchestrator-*` 节点 + `checkin`/`credit`/`fault` |
| [[pulse-doctrine\|PULSE]] | 2168 B | `cortex-pulse.sh`（每小时） |

六条全部配套 `rules/on-demand/*-guide.md` 全文，且**已双向互链**。

### 5.3 测试套件（`bin/cortex-loop-tests/` · 以现场退出码为准）

分组 A–F + H 专项。关键的负向测试（**每条都破坏性验证过会红**）：

| 用例 | 挡什么 |
|------|--------|
| `H08` | 验收员标签机械核验（界外改判 SCOPE，界内一条不放宽） |
| `H10` | 一拍时间预算（太短真任务跑不完，太长卡死时钟槽） |
| `H11` | 负载率分子分母同窗（跨天不 fail-open） |
| `F15` | 真账本 `CLOCK.md` / `TASKS.md` 逐字节未变（测试不许污染生产） |
| `T3` 哨兵 | **必须一直 blocked** —— 变绿 = 完成门被放宽 |

---

## 6 · 蜂群现状（实测 2026-07-29 22:55 · 过门率 46 与孤岛 0 于 23:22 复测一致）

| 节点 | HAAS | 等级 | 自主度 | 样本 | 违约 |
|------|------|------|--------|------|------|
| worker | 0.762 | L3 | ✅ 可逆自动 | 16 | 0 |
| laptop | 0.590 | L2 | ❌ 建议为主 | 18 | 1 |
| **orchestrator-laptop**（主线程） | **0.195** | L1 | ❌ 每步确认 | 3 | **5** |

**蜂群整体 0.195** = 均值 0.435 × 短板因子 0.45。
**可信度取决于最弱那个，不是平均那个** —— 所以主线程是当前瓶颈。

| 指标 | 现状 | 目标 | 差 |
|------|------|------|-----|
| G1/G2 | 累计战绩与滚动 cohort 已分离 | 已批准：G1 7 天 / G2 24 小时，目标均 ≥90% | `python3 bin/cortex-metrics.py --json` |
| 闲置率 | 66% | <30% | 36 pt |
| 真孤岛 | 0 | 0 | ✅ |
| suite | 现场运行 | 0 FAIL | `bash bin/cortex-loop-tests/suite.sh` |

---

## 7 · 观点层 —— 建这套东西的过程里想明白的

> 这是本地图**最有价值的一节**。上面的清单会过时，下面这些不会。
> 分两类：**operator 立的**（方向与判据）和 **工程实证得来的**（踩出来的）。

### 7.1 operator 立的（方向与判据）

| # | 观点 | 落在哪 |
|---|------|--------|
| 1 | **不知道方向也能开始** —— 先把真实情况翻箱倒柜查清楚，问题自己会浮出来 | [[ground-first-doctrine\|GROUND]] G |
| 2 | 低垂果优先；**都清了才谈「更好的提升」**，那是下一层决策 | GROUND R/O |
| 3 | **查验强度随信任**（新供应商全检、老供应商抽检）—— 服装厂验货 | GROUND U · `inspection_mode()` |
| 4 | **该我判的我判，不推给人** —— 人的注意力是最稀缺资源 | GROUND N · `fault decision-dodge` |
| 5 | **主线程 = 决策者不是执行者**，且它自己也是一个对等节点，一样要打怪升级 | [[steer-doctrine\|STEER]] · `orchestrator-*` |
| 6 | **每轮的「摸」必须重新摸**，不能站在上轮结论上推（结论半衰期以小时计） | STEER S |
| 7 | **人机同读一份真相 = 人机交互界面**；越白、越可追溯，越能建立信任 | [[glassbox-doctrine\|GLASSBOX]] |
| 8 | 状态**别压成布尔**，压掉的恰好是「为什么」，而「为什么」决定下一步 | [[dimensional-expansion-doctrine\|DIMENSIONAL]] |
| 9 | **手搓一次可以，第二次必须成工具**；搓错过的优先级最高 | [[atomize-tools-doctrine\|ATOMIZE]] |
| 10 | 交付前**自问五问，每问带证据**；答不出证据的那问就是真缺口 | [[pulse-doctrine\|PULSE]] |
| 11 | **保安四问是最底层的验收** —— 你是谁 / 从哪来 / 到哪去 / 来干什么 | SKILL.md §一–§四 |
| 12 | 闲置率降 → 满载率升 → 经济效益升，**三级递进不能跳** | dashboard 负载率 |
| 13 | **改判可以，抹账不行** —— 禁止删 ref 来「清理」数字 | `readjudicate` |
| 14 | 不能出现「**发现了却修不稳**」 | CHARTER-SWARM G1 |
| 15 | **诚实的 UNKNOWN > 好看的假数字** | CHARTER-SWARM Trade 段 |
| 16 | 整机重启后要能**断点续传**，不从头再来 | HIVE R·Resume 机械化 |

### 7.2 工程实证得来的（踩出来的）

| # | 观点 | 实证 |
|---|------|------|
| 17 | **空转（noop）比失败更坏** —— 判据已满足的任务重跑仍计 passed，会把信任刷高 | E014 · `moot` 第四态 16 条 |
| 18 | **产出必须到达 origin 可见的 git 历史**，只落本机磁盘不算完成 | 传播门 v2 |
| 19 | **修好一层，下一层才看得见** —— 300s 超时被 health 恒红遮了整整一天 | H10 |
| 20 | **代码修好了传不过去 = 等于没修** —— worker 落后 532 commit，拿旧尺子把自己锁在门外 | 今日空转真因 |
| 21 | **分母虚高会把不存在的债变成永远归不了零的债** | 孤岛「56」→ 实际 0 |
| 22 | **量纲不同窗 = 跨天 fail-open**，且越久没产出历史存量越厚、数字越好看（自我掩盖） | H11 · 闲置率 |
| 23 | **量具本身会骗人**，至今 6 次：`grep -cE` 转义 · `tail` 吞退出码 · `ls` 多路径 · CJK 变量名 · `--json` 换行 · `for-each-ref` 的 `*` 不跨 `/` | ATOMIZE 立律基础 |
| 24 | **每道新门首日必被自己的实测打脸**（传播门 v1→v2、PULSE 首日两坑、SCANNER-DOWN 焊死）—— 所以负向测试必须破坏性验证 | tenets.md |
| 25 | **没有 baseline、窗口、最小样本和批准证据的数字目标，不是门** | `METRICS.json` 合同 |
| 26 | **「查不到」必须独立成第三态** —— 倒向健康是 fail-open，倒向故障是过度保守 | 10 探针 UNKNOWN |
| 27 | **心跳照跳、产出恒零，比死了更难发现** —— 活着且健康的假象最贵 | worker 300s |
| 28 | **蜂群可信度 = 最弱节点，不是平均节点** | 短板因子 0.45 |
| 29 | **两类失败修法相反必须可区分**：`status=1/FAILURE`（判据不让跑，修判据）vs `15/TERM`（跑着被掐死，给时间） | H10 断言 |
| 30 | **拆分的组织原则是四问，不是「常用/不常用」** —— 体积小了但读者仍不知道这是什么，等于没拆 | SKILL.md 40.7→17.1 KB |

---

## 8 · 意图与目标（人定，机器不许自己改）

| 文件 | 体积 | 管什么 |
|------|------|--------|
| [[cortex-loop/INTENT]] | 5.5 KB | **终局方向唯一 SSOT：自主兑现内核 + 人机 Covenant + S0–S4** |
| [[CHARTER-SWARM]] | 运行 Charter | **S0/S1 边界与晋级证据** |
| `METRICS.json` | JSON | **G1/G2 cohort、窗口、baseline、target 与审批** |
| `INTENT-P2.md` | 历史 | 已 superseded，不参与当前阶段判定 |
| `GOAL-throughput.md` | 历史 | 已 superseded，不参与当前指标判定 |
| `INTENT.md` | 3.2 KB | 方向线原始意图 |
| `TASKS.md` | 3.6 KB | 待办账本（机器消费） |
| `PROGRESS.md` | 19.4 KB | 断点续传进度 |
| `JOURNAL.md` | 11.7 KB | 方向线日记 |

---

## 9 · 关联 Skills

| Skill | 关系 |
|-------|------|
| [[loop-engineering-hub/SKILL]] | **上游主控台**（本 Skill 挂在它下面） |
| [[hive/SKILL]] | R·Resume 的机械化落地就是本引擎的「running 停滞收回重推」 |
| [[sub-agent-dispatch/SKILL]] | 派活的另一条路径（人在场时） |
| `skills/cron`（**vault 外软链** → `~/.aionui/builtin-skills/`）· [[openclaw-master/SKILL]] | 时钟与外部编排层 |
| [[evolve-ecosystem/SKILL]] · [[model-fingerprint/SKILL]] · [[epiplexity/SKILL]] | 生态/模型侧 |
| [[cortex-architecture/SKILL]] | **全体系多栈晶格总入口**；本引擎 = 晶格 **C 区（执行/强制/心跳）** |

### 9.1 多栈晶格挂联（2026-08-02 · 与 Evolve 分工）

> 全文：[[reports/2026-08-02/architecture/cortex-multi-stack-coherence-map|coherence map]] · CLI：`bash bin/cortex-architecture-map.sh hang all`

| 区 | 谁 | cortex-loop 怎么用 |
|----|-----|-------------------|
| **B 知识网** | Evolve（边）+ insight/memory/skill-ecosystem（点） | **消费**已 harden 的 Skill/Method/Rule；完成后 REAP 可触发 detect-*，**禁止 tick 内 transform-emit** |
| **C 执行/强制** | **本引擎** + Runtime-L2 + L-git | 时钟推进、认领、机械完成门、蜂群 |
| **A 交付剖面** | Ankole HTML 01–05 | 对人讲「loop 在编排层」；不替代本 MAP |
| **数据竖切** | D-Tier / 数据治理 | 业务任务的 short_test 常钉在 D0–D2 真源；loop 不替代数据栈 |
| **坐标** | 5D Gravity | 实体可填 C2/ETCLOVG；HAAS 信任与 loop trust 同源 mobfish 六定律 |

**飞轮**：loop 执行 → 证据 → REAP → Evolve 升维（若命中）→ 下轮 loop 更省 token = CIE。

---

## 10 · 今日相关报告（`reports/2026-07-29/_standalone/`）

`cortex-loop-throughput-fix` 22 KB · `cortex-loop-modernization` 19 KB ·
`cortex-loop-engine-fixes` 15 KB · `cortex-loop-consolidation` 15 KB ·
`island-skills-cleanup` 9.5 KB · `layer0-compression` 8.1 KB ·
`cortex-loop-handoff` 7.6 KB · `idle-rate-fix` 6.8 KB ·
`cortex-loop-next-round-design` 5.4 KB · `dashboard-async` 4.5 KB

---

## 11 · 怎么用这张地图

| 你想干什么 | 从哪进 |
|-----------|--------|
| 第一次接触，想知道这是什么 | [[cortex-loop/SKILL]] §一–§四（保安四问，前 94 行） |
| 现在什么情况 | `bash bin/cortex-dashboard.sh` |
| 任务为什么卡在 Git 交付 | `python3 bin/cortex-workspace-inspect.py` · Dashboard「交付流水线」 |
| 哪些 Agent worktree 真在用、哪些可回收 | `python3 bin/git-worktree-doctor.py --json` · Dashboard「开发工作区」 |
| 为什么这么判 | `bash bin/cortex-trace.sh` · `python3 bin/cortex-loop why <id>` |
| 还差什么没做到 | [[cortex-loop/EXPECTATIONS]] · `python3 bin/cortex-loop-expectations.py --json` |
| 别再犯同样的错 | [[cortex-loop/ERRORS]] |
| 改引擎前 | `references/architecture.md` + `references/tenets.md` |
| 终局要去哪、人机边界是什么 | [[cortex-loop/INTENT]]（**只读**） |
| 当前 S1 怎么跑、指标有没有生效 | [[CHARTER-SWARM]] + `METRICS.json`（**只读**） |

---

## 12 · 资产总表（机读友好）

> **一行一资产**。给 Codex / 外部 agent 做完整推敲与规划用。
> `↔` 列 = **双向对端**（谁指向它 / 它指向谁）。`—` = 非 markdown，不参与 wikilink 网络。
> 体积为 2026-07-29 23:22 实测字节数。

### 12.1 意图层（人定，机器不许自改）

| 资产 | 类型 | 体积 | 角色 | ↔ 双向对端 |
|------|------|------|------|-----------|
| [[cortex-loop/INTENT]] | md | 5.5 K | **终局方向唯一 SSOT** | [[cortex-loop/SKILL]] · [[CHARTER-SWARM]] · [[cortex-loop/MAP]] |
| [[CHARTER-SWARM]] | md | 运行 Charter | **S0/S1 边界与证据** | [[cortex-loop/INTENT]] · [[cortex-loop/SKILL]] · [[cortex-loop/MAP]] |
| `METRICS.json` | json | 指标合同 | **G1/G2 唯一机器真相源** | Dashboard · PULSE · CI |
| [[GOAL-throughput]] | md | 历史 | superseded | `METRICS.json` |
| [[loop-ops/INTENT-P2\|INTENT-P2]] | md | 历史 | superseded | [[cortex-loop/INTENT]] |
| [[loop-ops/INTENT\|INTENT]] | md | 3.2 K | 方向线原始意图 | [[cortex-loop/MAP]] |
| [[loop-ops/TASKS\|TASKS]] | md | 3.6 K | 待办账本（**机器消费**） | 引擎 `tick` 读 · [[cortex-loop/MAP]] |
| [[loop-ops/PROGRESS\|PROGRESS]] | md | 19.4 K | 断点续传进度 | HIVE R·Resume · [[cortex-loop/MAP]] |
| [[loop-ops/JOURNAL\|loop-ops/JOURNAL]] | md | 11.7 K | 方向线日记 | [[cortex-loop/MAP]] |

### 12.2 引擎与工具（`bin/` · 非 md）

| 资产 | 体积 | 角色 | 三态 | ↔ 文档对端 |
|------|------|------|------|-----------|
| `bin/cortex-loop` | 216 K | **引擎 · 31 子命令 · 唯一写 done** | — | `references/commands.md` · `architecture.md` |
| `bin/cortex-dashboard.sh` | 29 K | 白盒总览 + `--json` + `--watch` | ✅ | [[glassbox-doctrine]] |
| `bin/cortex-pulse.sh` | 9.7 K | 五问自检（每小时） | ✅ 0/1/2 | [[pulse-doctrine]] |
| `bin/cortex-probe.sh` | 9.5 K | **10 探针** YES/NO/UNKNOWN | ✅ | [[atomize-tools-doctrine]] |
| `bin/cortex-trace.sh` | 8.9 K | 白盒下钻 | ✅ | [[glassbox-doctrine]] |
| `bin/cortex-ci.sh` | 5.6 K | 每日回归 + **目标锚定**（退 2=跑偏） | ✅ | [[CHARTER-SWARM]] |
| `bin/cortex-loop-expectations.py` | 5.0 K | EXPECTATIONS 机读器 | ✅ 0/1/2 | [[cortex-loop/EXPECTATIONS]] |
| `bin/cortex-workspace.sh` | 动态 | 稀疏 attempt 舱：独立 index / 崩溃恢复 / 磁盘门 | ✅ | `references/architecture.md` · `references/commands.md` |
| `bin/cortex-candidate.sh` | 动态 | Candidate 范围验证 / 不可变发布 / 查询 | ✅ 0/2/75 | `references/swarm.md` · `references/commands.md` |
| `bin/cortex-integrator.sh` | 动态 | Blobless 集成 + canonical lease-CAS | ✅ 0/1/2/75 | `references/architecture.md` · `references/commands.md` |
| `bin/cortex-workspace-inspect.py` | 动态 | 交付面 workspace/candidate/landed/残锁统计 | ✅ 0/1 | `cortex-dashboard.sh` · `references/commands.md` |
| `bin/git-worktree-doctor.py` | 动态 | worktree 认领 / 活进程 / 脏改 / 可恢复回收 | ✅ 0/1/2/3 | `cortex-dashboard.sh` · `references/commands.md` |
| `bin/cortex-capability-bundle.py` | 4.8 K | 节点能力打包 | — | `references/swarm.md` |
| `bin/cortex-loop-mcp.py` | 4.9 K | MCP 接口（外部 agent 接入） | — | — |
| `bin/cortex-loop-detach.sh` | 2.7 K | 长命令脱离终端 | — | [[cortex-loop/ERRORS]] E010 |
| `bin/cortex-loop-adapters/*.sh` | ×5 | 肌肉：claude/codex/ollama/human/mock | — | `references/architecture.md` |

### 12.3 Skill 家族（`skills/cortex-loop/`）

| 资产 | 体积 | 回答什么 | ↔ 双向对端 |
|------|------|---------|-----------|
| [[cortex-loop/INTENT]] | 5.5 K | **终局 + 人机 Covenant + 晋级边界** | [[cortex-loop/SKILL]] · [[CHARTER-SWARM]] · [[cortex-loop/MAP]] |
| [[cortex-loop/SKILL]] | 17.3 K | **保安四问** + T1–T9 | 全家族 · 六律 · [[cortex-loop/INTENT]] · [[CHARTER-SWARM]] |
| [[cortex-loop/ERRORS]] | 32.7 K | 已犯过的错 E001–E015 | 六律（错题→律映射表） · [[cortex-loop/MAP]] |
| [[cortex-loop/JOURNAL]] | 19.9 K | 建设日记 | [[cortex-loop/SKILL]] · [[cortex-loop/MAP]] |
| [[cortex-loop/EXPECTATIONS]] | 10.0 K | **还没做到的 20 条**（`--json`） | [[CHARTER-SWARM]] · [[cortex-loop/MAP]] |
| [[cortex-loop/MAP]] | 本文件 | 全景 + 观点索引 | **全部** |
| [[cortex-loop/references/architecture\|references/architecture]] | 12.0 K | 三分架构（改引擎前必读） | [[cortex-loop/SKILL]] · [[cortex-loop/MAP]] |
| [[cortex-loop/references/commands\|references/commands]] | 8.9 K | 31 子命令详表 | [[cortex-loop/SKILL]] · [[cortex-loop/MAP]] |
| [[cortex-loop/references/operations\|references/operations]] | 8.2 K | 部署/运维/新增方向线 | [[cortex-loop/SKILL]] · [[cortex-loop/MAP]] |
| [[cortex-loop/references/tenets\|references/tenets]] | 5.5 K | T1–T9 各自真实代价 | [[cortex-loop/SKILL]] · [[cortex-loop/MAP]] |
| [[cortex-loop/references/contracts\|references/contracts]] | 4.4 K | 合同字段 | [[knowledge-contract-registry]] · [[cortex-loop/MAP]] |
| [[cortex-loop/references/swarm\|references/swarm]] | 4.2 K | 多节点/分片/租约/信任 | [[CHARTER-SWARM]] · [[cortex-loop/MAP]] |

### 12.4 沉淀层 · Layer 0 六律（本 Skill = 它们的机械落地面）

| 律 | 短触发器 | 全文 guide | 机械后盾 |
|----|---------|-----------|---------|
| [[ground-first-doctrine\|GROUND]] | 2414 B | [[ground-first-doctrine-guide]] | `fault decision-dodge` · `inspection_mode()` |
| [[dimensional-expansion-doctrine\|DIMENSIONAL]] | 2076 B | [[dimensional-expansion-doctrine-guide]] | `dimensional-collapse-scan.sh` |
| [[atomize-tools-doctrine\|ATOMIZE]] | 2068 B | [[atomize-tools-doctrine-guide]] | `cortex-probe.sh` |
| [[glassbox-doctrine\|GLASSBOX]] | 2028 B | [[glassbox-doctrine-guide]] | `cortex-dashboard.sh` · `cortex-trace.sh` |
| [[steer-doctrine\|STEER]] | 2033 B | [[steer-doctrine-guide]] | `orchestrator-*` · `checkin`/`credit`/`fault` |
| [[pulse-doctrine\|PULSE]] | 2168 B | [[pulse-doctrine-guide]] | `cortex-pulse.sh` |

### 12.5 账本与心跳（运行时 · 非文件）

| 资产 | 实测 | 角色 |
|------|------|------|
| `refs/swarm/cortex/{claim,result,plan,moot,incident,beat,lease}` | 177 条 | git ref CAS 当分布式锁 |
| `com.cortex.loop`（launchd） | 15 min · EXIT=0 | 主推进 |
| `com.cortex.pulse` | 1 h · EXIT=1 | 健康五问 |
| `com.cortex.ci` | 每日 · EXIT=0 | 回归 + 目标锚定 |
| `work-studio/devops/dotfiles/systemd/cortex-loop.service` | 840 s | worker 侧单拍预算 |

### 12.6 测试套件（`bin/cortex-loop-tests/` · 现场运行）

| 用例 | 挡什么 | 破坏性验证 |
|------|--------|-----------|
| `H08` | 验收员标签核验（界外 SCOPE，界内不放宽） | ✅ |
| `H10` | 一拍时间预算（下界 600s / 上界 <900s） | ✅ |
| `H11` | 负载率分子分母同窗（跨天不 fail-open） | ✅ |
| `F15` | 真账本逐字节未变（测试不许污染生产） | ✅ |
| `T3` 哨兵 | **必须一直 blocked**，变绿 = 门被放宽 | ✅ |
| `dimensional-collapse-scan.sh` | 布尔坍缩扫描 | — |
| `autonomy-acceptance.sh` | 自主度验收 | — |
| `env-parity.sh` | 交互式 ≠ 无人值守（E012） | — |

### 12.7 报告（`reports/2026-07-29/_standalone/`）

| 报告 | 体积 | 内容 |
|------|------|------|
| [[cortex-loop-throughput-fix]] | 22 K | 吞吐攻坚：worker 空转真因 + 300s 掐死 |
| [[cortex-loop-modernization]] | 19 K | SKILL 按保安四问重组 + 双向边补齐 |
| [[cortex-loop-engine-fixes]] | 15 K | 引擎缺陷修复（E014 空转门 / E015 死锁） |
| [[cortex-loop-consolidation]] | 15 K | 体系合并与治理 |
| [[island-skills-cleanup]] | 9.5 K | 孤岛 56 → 实际 0（分母虚高实证） |
| [[layer0-compression]] | 8.1 K | Layer 0 短触发器压缩 |
| [[cortex-loop-handoff]] | 7.6 K | 交接说明 |
| [[idle-rate-fix]] | 6.8 K | 闲置率死锁破解 |
| [[cortex-loop-next-round-design]] | 5.4 K | 下一轮设计 |
| [[dashboard-async]] | 4.5 K | Dashboard 异步采集 |

---

## 13 · 给 Codex 的推敲入口

> 不是让你复述，是让你**找出我们没看见的**。以下每条都附了我方当前立场，
> **请优先攻击立场，而不是补充同意**。

| # | 待推敲 | 我方当前立场 | 攻击面 |
|---|--------|-------------|--------|
| 1 | G1/G2 的 target 如何维护 | 已有 baseline、滚动窗、最小样本与人类批准证据；变更仍须新批准记录 | 样本独立性与窗口长度是否仍足以支撑决策？ |
| 2 | 蜂群整体信任 = 均值 × **短板因子 0.45** | 可信度取决于最弱节点 | 短板因子是否过度惩罚？主线程 L1 是否该独立计？ |
| 3 | 主线程既是**决策者**又是**被计分节点** | 对等才有约束力 | 自评自罚的裁判问题怎么破？ |
| 4 | 六律成链 GROUND→DIMENSIONAL→ATOMIZE→GLASSBOX→STEER→PULSE | 顺序即依赖 | 链条是真依赖还是事后叙事？有无循环？ |
| 5 | 「空转」立为第四态 `moot` | 不烧额度不计分 | 会不会被滥用成逃避执行的借口？ |
| 6 | 观点 #24「每道新门首日必被自己打脸」未立律（LATCH 判据不足） | 只写进 `tenets.md` | 是否已达 ≥3 次门槛该立？ |
| 7 | EXPECTATIONS 是否被消费 | Dashboard 已接入 total/eligible/non-eligible | 如何把具备 owner+short_test 的条目安全晋升为 S1 任务？ |
| 8 | worker git-sync cron 仍关闭（269 文件分歧待决） | **最大存量风险** | 恢复策略？分歧怎么裁？ |

---

*体积清点 2026-07-29 23:22 · 蜂群指标 22:55 · 数字会过时，§7 观点与 §13 推敲入口不会 ·
数字变了重跑本文件 §1–§6 的清点命令 · 双向边由 `bin/verify-wikilinks.py` 守*
