# cortex-loop 蜂群机制（多节点同写一个 git 账本）

> **何时该读**：多机协作出问题（谁该管这条线 / 两台机同时动 / 判某台机掉没掉线 / 该不该接管），
> 或要往蜂群里加一台新机器。
> **上级**：[[cortex-loop/SKILL|SKILL.md]] · **命令**：[[cortex-loop/references/commands|commands.md]] §蜂群协调 / §去中心化分发

---

**问题**：多节点同写一个 git 账本 = 冲突源。
**解法不是共识算法，是分片 + CAS 租约。**

---

## ① owner 分片（防日常打架）

`CLOCK.owner` 给每条线指定唯一负责节点 → **天然单写者**，git 不打架。
非 owner 节点 tick 时直接 `skip | X 归 Y 管`。

## ② git ref CAS 租约（防脑裂 · 零外部依赖）

> **核心洞见**：`git push` 更新远端 ref 本身就是**原子 compare-and-swap**。两个节点拿同一 parent 造 commit 同时推，服务器只让一个 fast-forward 成功，另一个必被 `[rejected] non-fast-forward`。**语义等价 Redis SETNX，零外部服务。**

- 命名空间：`refs/swarm/lease/<line>`（租约）· `refs/swarm/beat/<node>`（心跳）
- 每个节点只推自己的 beat ref → 结构上不可能撞
- 全程 git plumbing（`hash-object` / `mktree` / `commit-tree`），**不 checkout、不碰工作区**
- 为什么必须走 ref 层：worker 实况 267 文件未提交、auto-sync 已坏，任何 pull/rebase/checkout 都被脏树挡住 → 蜂群跟着瞎

> CAS 拒绝与网络故障**必须分开**，压成同一个返回值就是 [[cortex-loop/ERRORS|E009]]（[[dimensional-expansion-doctrine|DIMENSIONAL 律]] 母题）。

## ③ can_sleep 差异化静默阈值（防误判）

`loop_node` 画像自动探测：有电池=laptop 会睡；无电池或 `SleepDisabled=1` = always-on。

| 节点类型 | 静默正常阈值 | 可接管阈值（2 倍缓冲） |
|----------|-------------|----------------------|
| `can_sleep=yes`（笔记本） | 14h（合盖过夜属正常） | 28h |
| `can_sleep=no`（常开机） | 3h | 6h |

**接管须超阈值 2 倍**——宁可晚接管，不可抢了又还回去（**抖动比停摆更伤**）。
接管者 = 存活节点按名字排序第一个（无需选举，确定性）。
`last_seen` 取**整点精度** → 一小时内重复心跳文件无 diff → 蜂群不制造 commit 噪音。

> 「日志连续」不等于「一直在跑」——笔记本合盖 launchd 会停跳（[[cortex-loop/ERRORS|E007]]）。
> 所以 `idle` 的分母只含**真跑过的拍**，不是墙钟。

## ④ 会话死亡自动接管（HIVE R·Resume 机械化）

环**不认识会话是怎么死的**（API 断连 / 撞额度 / 机器睡了），只认「`running` 超 `stall_min`（默认 45min）没动静」→ 收回重推。
**接管的不是那个会话，是外部时钟。**

对应 [[hive-doctrine|HIVE 律]] 的 R·Resume —— 律说「重连第一件事是续传」，这里把它变成不依赖任何人记得的机械动作。

## ⑤ 多 Runtime 执行隔离（防共享 worktree 打架）

- ref 层负责 claim/lease/result；不得拿 Git 全局锁包住 Agent 生命周期。
- 每个 attempt 使用唯一稀疏 linked worktree，Git objects 共用一份但 index/worktree 不共用。
- Candidate 发布到 `refs/cortex/candidate/<attempt>/<oid>`，不可变、可跨节点消费。
- Integrator 是唯一逻辑 lander，但它不是长生命周期全局锁：每次只对 observed master tip 做一次 server-side CAS。
- CAS loser 返回 retryable，基于最新 tip 重放；路径/语义冲突才 blocked，不把正常竞争算执行失败。
- 结算成功立即回收 clean workspace；脏舱、foreign/live owner、身份不符全部 fail-closed。

---

## 主线程在蜂群里的身位

同一台机上「跑 tick 的」和「跟人对话的」是两个节点：

| 节点 | kind | 说明 |
|------|------|------|
| `<host>` | executor | launchd 拉起的自动执行体 |
| `orchestrator-<host>` | orchestrator | 人机接口，非执行体。用 `checkin` 接入 / `checkin --out` 退出 |

编排者也要被信任机制约束 → `fault`（自记违约）+ `credit`（记自主做成）双向计分。
真相源见 [[cortex-loop/references/architecture|architecture.md]] §六定律三关 · 律侧见 [[steer-doctrine|STEER]]。

---

## Nav

[[cortex-loop/SKILL|SKILL.md]] · [[cortex-loop/references/commands|commands]] · [[cortex-loop/references/architecture|architecture]] · [[cortex-loop/references/contracts|contracts]] · [[cortex-loop/references/operations|operations]] · [[cortex-loop/ERRORS|ERRORS]]

---

<!-- cortex:map-backlink d-66b637004ace09ce92612c5c -->
关联地图：[[skills/cortex-loop/MAP|Cortex Loop 全景地图]]
