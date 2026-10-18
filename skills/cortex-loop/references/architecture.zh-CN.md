[English](architecture.md) | 简体中文

# cortex-loop 设计原理（为什么这么造）

> **何时该读**：想改引擎行为、加一层门、调额度策略、或有人问「为什么不直接让 AI 判完成」时。
> 只想用命令 → [[cortex-loop/references/commands|commands.md]]；只想部署 → [[cortex-loop/references/operations|operations.md]]。
> **上级**：[[cortex-loop/SKILL|SKILL.md]]

---

## 病与药

**病**：CORTEX 所有资产都是被动的（MEMORY / STATUS / Directions / 全部 skills），只在「有人来读」的那一刻才存在。**时钟源是 operator 本人**——一件事只要他没想起来，就永久停在原地，跟没写过一样。

**为什么必须原生**：心跳不能寄生。上一代 `*-advance` 九条全线蒸发（2026-07-28 亲验 live=0），死因不是设计错，是**它活在 OpenClaw 的库里、不活在 git 里**——所以它死了几个月，没有任何文件、任何 commit、任何人发现。

**边界**：不替人决策、不发明目标、不替人拍板。只做人做不好的两件事——**不忘**、**不停**。

---

## 三分架构

| 层 | 是什么 | 住在哪 | 会不会死 |
|----|--------|--------|---------|
| **账本** | 意图 + 任务 + 证据 | git：`CLOCK.md` / `INTENT.md` / `TASKS.md` / `JOURNAL.md` | 不会 |
| **心跳** | 到点叫醒账本，纯代码零 LLM | launchd `com.cortex.loop`（900s） | 重启自恢复；OpenClaw 挂了不受影响 |
| **肌肉** | 真正干活/判断的 AI | `bin/cortex-loop-adapters/*.sh` | 死了就换，环不认识它是谁 |

## 分布式交付面：共享对象，不共享工作树

控制面继续使用 `refs/swarm/*` 的 CAS/lease；执行与交付拆成五段：

1. claim 固定 `run_id/base_oid/allowed_paths`；
2. `cortex-workspace.sh` 创建按 bounds 稀疏检出的 attempt 舱，独立 index、共享 objects；
3. Worker 只在舱内产出，`cortex-candidate.sh` 发布不可变 candidate ref；
4. `cortex-integrator.sh` 以 blobless + sparse 隔离仓复验范围、只读依赖、short_test，并用 master tip 的精确 lease-CAS 集成；
5. candidate 可达只叫 `integration_pending`；landed commit 成为 canonical master 祖先后才叫 done。

唯一允许全局串行的是 canonical ref 的一次原子更新。LLM、网络等待、文件生成、测试、部署均不持全局工作锁。
调度并行度由写集冲突、Worker/账号容量、磁盘预算共同决定；写集不重叠才并行，冲突等待不计失败。

**「与 Agent Runtime 无关」的精确含义**：不是不用 runtime，是**环不认识任何一个**。`CLOCK.md` 写 `executor: claude`，换成 `codex` 就换个肌肉，账本和心跳一个字不改。

### 可用肌肉（adapter 接口：`$1=提示词文件 $2=结果文件`）

| adapter | 行为 | 什么时候用 |
|---------|------|-----------|
| `human` | 提示词投递到 `/tmp/spotlight/cortex-loop-human-inbox.md`，**不烧 token 不产副作用** | **新线默认**。先让人看几轮对不对，再换自动 |
| `claude` | `timeout 1500 claude -p`（headless 无会话） | 线跑顺了、要真自动推进 |
| `codex` | 必走 `bin/codex-validate.sh` 封装（禁裸 `codex exec`） | 需要第二个模型独立视角时 |
| `ollama` | 本机模型，**零额度零网络** | 三级降级阶梯最底一级：云端全线撞额度/403 时仍能推进（`3436107a5`） |
| `mock` | 吐固定 3 行样本，零模型调用 | 自测「结构验收会不会正确丢弃坏行」 |

**执行器必须报真实模型与计费方式**（`9334868bb`）：`exec.claude` 是**假等价** ——
两台机器都写 `exec.claude`，一台是订阅一台是 API key，额度耗尽时的行为完全不同。
所以能力表要拆成 `exec.<name>` + `model.<vendor>.<id>` + `billing.<mode>` 三层，
且模型身份要能被 `attest` 验（见 [[cortex-loop/references/commands|commands.md]] §信任与约束）。

**T1 落地方式（接新 runtime 时照做）**：在 `bin/cortex-loop-adapters/<新runtime>.sh` 头部写一行
`# cortex-loop:requires-env PATH HTTP_PROXY ...`，`env-parity.sh` 会自动把它纳入校验，**引擎与门都不用改**。

---

## SHIFT 配比：哪里必须僵硬，哪里必须软

不是「代码太僵硬所以掺点 AI」，而是**判完成这件事有创造力就是灾难**。

| 必须僵硬（代码 · 零 LLM） | 必须软（AI · 走 adapter） |
|---|---|
| `tick` 算窗口 · `submit` 记账 | **拆解**：INTENT → 任务行（`decompose`） |
| `try-complete` 判 artifact / short_test | **诊断**：连败 ≥2 次才唤醒，问为什么卡住 |
| `reconcile` 对账 · `health` 自检 | **验收**：探索型任务的质量判断（`judge`） |
| 预算窗口 · 每日上限 · 租约 CAS | **升级文案**：卡住了怎么跟人说 |

### ⛔ 不对称铁律

> **AI 只有否决权，没有批准权。**

| AI 能 | AI 不能 |
|-------|--------|
| 提议任务（过结构验收才入账，字段不齐机械丢弃） | 写 `status=done` |
| 否决质量不合格的产出（`judge` REJECT） | 让一个没有 artifact 的任务变绿 |
| 判断该 blocked 还是重试 | 绕过 `short_test` |

**验收员必须是第二个 AI**（不是干活那个），且它的结论进 `evidence`，不进 `status`。
代码层保证：`cmd_try_complete` 里 AI 只在机械门**全过之后**被调用，且只有 `REJECT` 分支能改结果。
同源公理：[[epiplexity/SKILL|epiplexity]] 公理 1「同一观察者评自己的产出，盲区完全重合」。

### 额度护栏（4 层，从外到内）

1. `advance_window_min` —— 同一任务两轮推进的最小间隔（防雪崩靠窗口，**不靠调低 tick 频率**）
2. `max_advance_per_day` —— 单线每日推进上限
3. `health` 红 → `tick --auto` 直接拒跑（不在坏地基上烧钱）
4. AI 只在三个点被唤醒（拆解 / 连败 ≥2 / 验收），**不是每拍都问**

---

## 完成门的三道 + 一道空转门

| 门 | 问什么 | 失守表现 |
|----|--------|---------|
| **artifact** | 声明的产出文件存在且**非空** | `artifact=-` 占位符被当路径（T6） |
| **short_test** | 「**这一条具体的事**变了没」，不是「重跑会不会报错」（T4） | 复用扫描器退出码 → 任务永远通过（[[cortex-loop/ERRORS\|E011]]） |
| **传播门** | artifact **进了 origin 可达的历史**没有（T8） | 幽灵完成：本机判 done，蜂群里没人看得见 |

**再叠一层空转门**（T9）：判据**本来就满足**的任务不是活，是空转 —— 在烧额度之前拦掉，
落第四态 `moot`（既无功也无过，但**是终态**）。

> 第四态为什么必须有自己的命名空间：空转门 v1 识别出了它却只 `continue`，
> 没给它落脚点，于是它被折叠回 `pending` —— 计划因此永远闭不了，
> `tick` 的「先接旧活」分支被一个早已没活的计划锁住 **6 拍零产出**（[[cortex-loop/ERRORS\|E015]] / `34e8450f1`）。
> 塞进 `result` 也不行：会污染 HAAS 与过门率。

三道门是 [[dimensional-expansion-doctrine|DIMENSIONAL 律]] 的正面应用：
「完成」不是一个布尔，它至少有 **做没做 / 判据变没变 / 别人看不看得见** 三个正交维度。

---

## 账本原则：改判不删账

> 三处独立实现都坚持了同一条，此前散在代码里没成文（2026-07-29 归纳）。

| 场景 | 做法 | **没有**做的错法 |
|------|------|----------------|
| 判据改严/改准后重看历史 | `readjudicate` 用**当前判据重判**，原 rejected 记录留在账上 | 「特赦」—— 把旧的 rejected 抹掉重开 |
| 任务判据本来就满足（空转） | 落第四态 `moot` **独立命名空间**，是终态但不进功劳账 | 折叠回 `pending`（计划永远闭不了 · [[cortex-loop/ERRORS\|E015]]），或塞进 `result`（污染 HAAS） |
| 编排者自己做错/做对 | `fault` 与 `credit` **各自留痕、不相互抵消** | 净额记账（做错一件 + 做对一件 = 什么都没发生） |

**为什么是同一条**：这三处都在抵抗同一个诱惑 —— **让历史看起来更好看**。
账本的价值恰恰来自它**不能被回头改写**：`why` 之所以能回答「这个 L3 是刷的还是干的」，
靠的就是空转记录没被删掉。

**与 [[one-step-truth|ONE-STEP-TRUTH]] 的分工**（看似相反，实则正交）：
ONE-STEP-TRUTH 管**文档正文**——只留正确终态，历史归 git；
本原则管**账本**——终态可以变，但每一次判定都留痕。
一个是给人读的结论，一个是给机器算分的证据链，不是一回事。

**为什么不立成 Layer 0 律**：这三处是**重复做对**，不是重复违规；
[[latch-doctrine|LATCH]] 管的是「加提醒无效的违规模式」，够不上。判定过程见
[[cortex-loop/EXPECTATIONS|EXPECTATIONS.md]] §D 候选律。

---

## 六定律三关（Mobfish 协作定律的原子化植入）

> 真相源：[[mobfish-six-laws]] · 落点原则：**每条定律 = 一个字段 + 一道机械关，不加新基础设施**。
> 三关开在 `cmd_run` 里，**开在花钱之前**（`8c28d3775`）—— 花完了再拦等于没拦。

| 关 | 定律 | 机械判据 | 拦下什么 |
|----|------|---------|---------|
| **C1** | 意图为界 | 产出路径必须落在任务声明的 `bounds` 白名单内 | 未授权即越界。占位符 `-` 显式豁免（T6） |
| **C2** | 信任为尺 | 本节点 HAAS 分 ≥ 任务要求的 `need_trust` | 低信任节点接高风险任务 |
| **C3** | 安全为底 | 不可逆任务要求 ≥L4 **且**有人类 `approved_by` 签名 | 不可逆动作被自动执行 |

C2 的 HAAS 权重取自六定律原文：**意图对齐 30% / 操作准确 25% / 边界遵守 25% / 恢复能力 20%**，
全部从 ref 层实际记录统计 —— **节点无法自报**。
C3 违约走 `STOP → REPORT → WAIT → RECORD`，RECORD 落 `refs/swarm/<swarm>/incident`，**进 HAAS 分母**。

**主线程也是节点**（`22d5ccb62` / `ab69450ee`）：同一台机上「跑 tick 的」和「跟人对话的」必须分开计分，
所以有 `orchestrator-<host>` 这个独立节点身位（`kind=orchestrator`，人机接口非执行体）。
补的是「**我不受约束**」这个漏洞 —— 编排者也要被信任机制约束，
所以才有 `fault`（自记违约）与 `credit`（记自主做成）这对双向计分子命令。
与 [[steer-doctrine|STEER 律]] 同源：主线程是决策者，但决策者也在账本里。

**蜂群整体信任** = 各节点加权均值 **× 短板因子** —— 不是取平均了事，
因为一个 L1 节点能干的坏事不会因为旁边有个 L5 就变少。

---

## 五工具为什么正交（GLASSBOX 立场）

> 2026-07-29 单日四次手搓命令量具失灵（`grep -E` 下 `\|` 不是或运算 /
> 管道吞退出码 ×2 / `ls` 多路径退出码骗人），每次**都长得像结果而不像故障**。
> 这正是 [[atomize-tools-doctrine|ATOMIZE 律]] 的触发源：**搓错过一次的命令优先级最高，它已证明会再骗人一次。**

**pulse 与 ci 的区别不是频率，是问题**：pulse 问「今天健不健康」，ci 问「**还是不是原来那个东西**」——
一个系统完全可以**很健康地跑偏**：指标全绿，但门被悄悄放宽、目标被悄悄降低。
所以 ci 除了跑测试，还要**核对 [[brain-network/directions/loop-ops/CHARTER-SWARM\|CHARTER-SWARM]] 里的目标本身没被改松**。

**GLASSBOX 立场**（[[glassbox-doctrine]]）：dashboard 与 trace 是**人机同读的同一份真相**，
不做两套 —— 两套必然分叉。`--json` 与人读那面来自同一次采集，
所以 `e5e61a678`「`--json` 输出非法 JSON」才是**自愈链断在第一环**级别的缺陷，
而不是「格式小问题」—— 人读那面当时毫无异样。

**为什么 pulse 必须上时钟**（[[latch-doctrine|LATCH 律]]）：PULSE 立为规则时写的是「交付前必跑」，
但**依赖 AI 记得**的规则在 in-context 惯性下必然被绕过。operator 一句「不是定期做吗？」直接点破 ——
第 3 次出现就该建 Hook，而不是加第 3 条提醒文字。

09:30 这个 ci 时点是选的不是随手填的：operator 上午看得到，且**避开 00:00 日切与 02:00 各类 nightly cron**。

---

## Nav

[[cortex-loop/SKILL|SKILL.md]] · [[cortex-loop/references/commands|commands]] · [[cortex-loop/references/swarm|swarm]] · [[cortex-loop/references/contracts|contracts]] · [[cortex-loop/references/operations|operations]] · [[cortex-loop/ERRORS|ERRORS]] · [[cortex-loop/EXPECTATIONS|EXPECTATIONS]]

---

<!-- cortex:map-backlink d-a1444bf512a487ff1b89b25d -->
关联地图：[[skills/cortex-loop/MAP|Cortex Loop 全景地图]]
