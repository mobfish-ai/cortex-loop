# cortex-loop — 建设日记

> **作用域**: 引擎 / 合同 / 蜂群的关键事件与决策转折
> **主文档**: [[cortex-loop/SKILL|SKILL.md]] · **错题本**: [[cortex-loop/ERRORS|ERRORS.md]]
> **总纲报告**: [[cortex-loop-intent]]
> **规矩**: 只记「转折」与「实测证据」，过程流水账不进（ONE-STEP-TRUTH）

---

## 2026-07-30 · S0/S1 真实闭环 + S2 合链接门户影子试点

- **S0/S1**：两批 `map-backlink-gap` 经 launchd `clock-auto` 跑完 26 条严格 discovery→result→world verify→learning；MAP `48/48 OK`
- **S2**：合链接门户仅做只读 shadow，91 个 comparable cases；结论相对库存基线 `SUPPORTED`，权限保持 `FORBIDDEN` 自动晋级
- **Dashboard**：首屏四问；manual/auto、canary/production、UNKNOWN/0、累计/滚动分开；真实显示 S0/S1 passed、guardrails UNKNOWN
- **反身修复**：v3.34 定位 stash owner 丢失后，最终升 Git 提交事务 V4，彻底移除后台 stash/reset/bulk add/merge；无时区 receipt 不再被误判未来；origin 三命名空间由逐 ref fetch 改为批量读取
- **验证**：suite `49 PASS / 0 FAIL / 1 SKIP`；H03 是人工性价比候选，不伪装成绿

---

## 2026-07-28 · 从「8 份报告 0 行代码」到双端蜂群实测通过

### 起点：8 份报告，一行能跑的代码都没有

在此之前，主动性/自主推进这个议题已经攒了 **8 份报告**（[[cortex-loop-intent]] §7 列全）：

`proactive-intent-master-brief` · `proactive-intent-loop-cortex-deliberation` ·
`nova-proactive-listen-spec` · `direction-cron-proactive-archaeology` ·
`proactive-intent-loop-codex-review` · `nova-60s-proactive-cortex-fusion` ·
`recap-35e58e01-agent-proactivity-extract` · `external-nova-agent-import-analysis`

四层模型、状态机、矩阵、Codex 对敲评审全都有了——**没有任何东西在跑**。
同日亲验的另一个事实把这件事钉死：上一代 `*-advance` 九条**全线蒸发，live=0**，死了几个月，**没有任何文件、任何 commit、任何人发现**。死因不是设计错，是它活在 OpenClaw 的库里、不活在 git 里。

结论：**心跳不能寄生。**

### 当日 8 个 commit（`git log --oneline` 真查）

| # | sha | 时间 | 转折 |
|---|-----|------|------|
| 1 | `93ae328c5` | 23:06 | **心跳引擎 + 可换肌肉 adapter** — 引擎零 LLM；AI 三挂载点全部走 adapter；确立不对称铁律 |
| 2 | `8d49d74b2` | — | **调度声明 CLOCK + 试点线 loop-ops 三合同** — 试点线选「环修自己的地基」而非市调线 |
| 3 | `ea254e217` | — | **launchd 主时钟 + 总入口报告** — 时钟不寄生；8 份旧报告降为卫星 |
| 4 | `f63bd4430` | 23:12 | **health 区分「干活失败」vs「报信失败」** + 试点线 T1 交付（见 ERRORS [[cortex-loop/ERRORS\|E005]]） |
| 5 | `e007fc7ec` | 23:20 | **睡眠感知** + T2 凭据链修复后转 pending 待自然验证（E006 / E007） |
| 6 | `f227f2868` | 23:32 | **蜂群** — 自我感知 + 群体感知 + owner 分片 + 掉线接管 |
| 7 | `51d317f9a` | 23:42 | **蜂群总线改走 git ref 层** — 零外部依赖的分布式 CAS 租约锁（E004 在此被拦下） |
| 8 | `62b597a8b` | 23:44 | **fix**：`list_refs` 格式串转义 → 静默退回文件快照（E003） |

---

## 关键决策转折（4 个）

### ① 试点线不推业务，先推环自己

试点线本可以选市调之类「看起来有价值」的线。选的是 **`loop-ops`：环修自己的调度底座**。

理由（[[brain-network/directions/loop-ops/INTENT|INTENT]] 原话）：心跳目前挂在一个**自己就有 31% 报错率**的底座上，在这种地基上跑自动推进，产出的是**自动化的假进展**。
且这是最强的自证——**如果环连自己的运维都推不动，它更推不动市调**。

### ② 完成判定必须先能报红，才配报绿

T3 是**反测哨兵**：它的产出文件（`cortex-loop-never-exists.md`）永远不该存在。
它一旦变绿，说明有人把完成门放宽了。

红→绿反证 7 项（[[cortex-loop-intent]] §5 全表），其中最关键的三条：
- `try-complete --task T3` → `FAIL T3: artifact 缺失` exit=1（门能报红）
- `try-complete --task T0` → `PASS T0 → done` exit=0（门能转绿）
- `reconcile`（装 launchd 前）→ `查无此驱动 → 脱钩 DRIFT` DRIFT=1；装载后 → `在跑 → OK` DRIFT=0

### ③ operator 拍板「不用 Redis，纯 git 天然完美解决」

蜂群总线原本要引外部依赖做分布式锁。operator 直接否掉。

答案是：**`git push` 更新远端 ref 本身就是原子 compare-and-swap**。两个节点拿同一 parent 造 commit 同时推，服务器只让一个 fast-forward 成功，另一个必被 `[rejected] non-fast-forward`——语义等价 Redis SETNX，**零外部服务**。

实测（真并发，非模拟，见 `51d317f9a` commit message）：
```
共同 parent b568f07f4 → nodeA 1f3579ca8 push 成功 / nodeB 824a2e238 [rejected] non-fast-forward
最终 holder=nodeA，确定性
```

配套决定：**全程走 git plumbing，不碰工作区**。因为 worker 实况 267 文件未提交、auto-sync 已坏，任何 pull/rebase/checkout 都会被脏树挡住 → 蜂群跟着瞎。ref 层完全绕开工作区。

### ④ 「修好了」的验收必须是自然运行，不是人为触发

T2（修 `mercury-daily-ops-report`）根因查到并处置后，**没有**在 23:20 强跑一次日报来让它变绿。
改为：任务转 `pending`，等 0729-0800 自然运行，环在 09:00 窗口自己核对。

这是 INTENT `Anti` 段「删 job 冒充修好 / 改 short_test 让它变绿」的同一条原则的延伸——**为了变绿而触发的一次成功，不是修好了**。

---

## 双端蜂群实测（当日收尾证据）

`/tmp/spotlight/cortex-loop.log` 亲读：

```
23:38 | sync nodes=1 beat=True     ← E003 未修：ref 层读空，静默退回本地文件快照，只看得见自己
23:43 | sync nodes=2 beat=True     ← 62b597a8b 修复后
23:44 | sync nodes=2 beat=True
```

`git for-each-ref refs/swarm` 实有两条：`refs/swarm/beat/laptop` · `refs/swarm/beat/worker`。

**从 8 份报告 0 行代码 → 引擎 12 子命令 + 四合同过 gate + launchd 装载 + 红→绿实测 7 项 + 双端蜂群 nodes=2，同日完成。**

---

## 当日留下的账（未完成，不美化）

| 项 | 状态 | 说明 |
|----|------|------|
| `loop-ops` T2 | `pending` fails=1 | GLM 摘链 + primary 改 MiniMax 已做，等 0729-0800 自然运行验证 |
| `loop-ops` T3 | `pending` fails=1 | 反测哨兵，**本来就该永远红**，不是待办 |
| `CLOCK.loop-ops.executor` | `human` | 安全默认。跑顺了才改 `claude` |
| 试点线数量 | 1 条 | 只有 loop-ops，业务线尚未接入 |

---

## 2026-07-29 · 从「能跑」到「不看着也能跑对」

> 这天引擎从 **1093 行长到 4125 行**（近 4 倍），子命令 12 → 31，工具 0 → 5，Layer 0 律 +5 条。
> 但真正的转折不是加了多少功能，是**发现「能跑」和「跑对」是两件事**——
> 07-28 收盘时环已经会自己推进了，07-29 一整天在回答的问题是：
> **它推进的那些，有几件是真的？**

---

### 00:00–01:00 · 上线即挨打：三个引擎级缺陷

`2eda7fa95` 一个 commit 修三个：心跳被 health 掐死 / `reconcile` 把「没能力检测」报成「坏了」/ 内部口径不自洽。

第二个尤其典型 —— 它是 **E013 维度坍缩的第一次现形**，只是当时还没起名字：
「**检测不出来**」和「**检测出来是坏的**」被压成同一个返回值，于是一台没装 systemd 的机器被报成「驱动坏了」。

同时段建了两件后来一直在用的东西：
- `9422cca9b` **24 用例套件 + 变异测试**——不只测「过没过」，还**故意改坏代码验证测试真的会红**。
  这条规矩后面救了命：10:36 的负向测试直接逮到「**我自己写的修复是死的**」（`991016f78`）。
- `6e5944883` **对外 API + MCP**——对内对外**同一道六定律门**。不做两个入口两套规则。

### 01:00–02:30 · 从「被派活」到「自己找活」

`6192092af` `discover` 自主找活。紧接着 `8f0b45897` **把找活策略从「挑最有价值的」改成「补低洼」**。

改的理由不是效率，是**目标函数选错了**：求最大值会让环反复扑同一个热点，
而蜂群要的是**降方差**——让最弱的那条腿别一直瘸着。这跟后来「蜂群整体信任 = 加权均值 **× 短板因子**」是同一个思路。

`b1189b725` `tick --auto` 真正闭环（发现 → 自动发布 → 自动认领执行）。**闭环当天就出事**：

| 时间 | commit | 真机逮到什么 |
|------|--------|-------------|
| 02:25 | `bac0c69b7` | `artifact='-'` 占位符被 C1 和机械门当成**真实路径** |
| 02:52 | `314d641ef` | **假完成**：`short_test` 复用扫描器退出码 + 验证器失败开放，两层同时失守（E011 → T3/T4） |

> **全自动闭环首跑的价值不在于它跑通了，在于它立刻暴露了假完成。**
> 手动跑一万次都不会发现——因为手动跑的人会顺手把 `-` 当占位符看懂。

### 03:00–08:00 · 4 小时无人值守窗口：最贵也最值的一段

这段没人看着。醒来发现：

1. `2ebcf66d2` **`revive` 从不自动触发** —— 写了自愈但没接上，环在无脑重试同一个坏执行器。
2. `724117356` **4 小时全线 403 的真因是 launchd 缺代理变量，不是锁屏**。
   先前的假设（「锁屏导致」）是错的，commit message 里明确写了「**更正错误假设**」。
   → 直接催生 **T2 跨环境一致性铁律**（`c858a9ef9` 同时立了 6 条置顶铁律 + E012）。

**为什么这 4 小时值**：交互式 shell 里一切正常，是**无人值守**才暴露的差异。
环境不一致这类缺陷，**只有在没人能顺手补救的时候才现形**。

同期并行的一大批 `fix(frontmatter)` / `fix(data-recovery)` / `fix(conflict-markers)` 不是本域的活，
是环**自己扫出来的缺口**（633 个 mossriver YAML 崩坏、假合并丢失的 50+ 个 AI 产出）——
这是「自主找活」第一次真的产出了人不知道的东西。

### 08:00–09:10 · PULSE 上时钟 + 传播门

`bb07bba02` **PULSE 从「靠 AI 记得跑」变成「机器自己跑」**。

触发是 operator 一句「**不是定期做吗？**」。
这是 [[latch-doctrine|LATCH 律]] 的教科书场景：规则写的是「交付前必跑」，但**依赖 AI 记得的规则在 in-context 惯性下必然被绕过**。
第 3 次出现就该建 Hook，而不是加第 3 条提醒文字。

`54b1dd836` **补传播门** —— 抓到幽灵完成 `real1/R2`：worker 判了 done，**产出从没进过 git 历史**。
本机磁盘上有文件 ≠ 完成。蜂群是靠 git 看见彼此的活的。

> 一小时后 `28f7d5d41` 打脸：**传播门 v1 是假门**。
> v1 只查 `git log -1 -- <artifact>` 非空 —— 但「文件历史上进过 git」和「**这次的改动进了 git**」是两回事。
> 真机当场证明 v1 放行了「有历史但改了没提交」。→ v2 改查 origin 可达性。**这条后来升为 T8。**

### 10:30–11:30 · fail-open 族总清算 + E013 起名

`22b23217c` **三处 fail-open 静默失明**，commit message 原话：「**越瞎越能干活的荒谬全部堵掉**」。

这是当天最关键的一次抽象跃迁 —— 之前每次都当成孤立 bug 修，这次终于看出**是同一个母题**：
> 判断不出来的时候，代码倾向于**倒向「通过」**，因为倒向通过不会报错。
> 于是**观测能力越差的节点，通过率越高**。

`9415010f2` 把它立成 **[[dimensional-expansion-doctrine|高维展开铁律]]**，并做了两件超出「修 bug」的事：
- **扩大化**：grep 全域找同类，逐处三态化（`02c3edacb` 是第 5 处）
- **机械沉淀**：`dimensional-collapse-scan.sh` 扫描器接进 suite —— 靠人记必然复发

**判据不是「能不能穷举」，是「这两态合并，会不会有人因此做错下一步动作」。**
会 → 展开；不会 → 合并。不是无限穷举。

### 12:00–14:00 · 三条律成型 + 蜂群总纲

| 时间 | commit | 立了什么 | 触发它的坑 |
|------|--------|---------|-----------|
| 12:52 | `a923e1072` | [[steer-doctrine\|STEER 律]] | 单会话内 **6 次结论腐烂**——站在上一轮结论上继续推，全推错 |
| 13:39 | `f32f0b96f` | [[atomize-tools-doctrine\|ATOMIZE 律]] + `cortex-probe.sh` | 单日**四次手搓命令量具失灵**，每次都长得像结果而不像故障 |
| 13:28 | `02d53a821` | [[brain-network/directions/loop-ops/CHARTER-SWARM\|CHARTER-SWARM]] | 目标散落各处 → ci 无从核对「有没有被改松」 |

ATOMIZE 那四次失灵值得单记，因为**它们全都不报错**：
`grep -E` 里 `\|` 不是或运算（静默匹配不到）· 管道吞掉退出码 ×2 · `ls` 多路径退出码骗人。
所以判据不是「麻烦不麻烦」，是「**这条命令搓错过吗**」—— **搓错过的优先级最高，它已证明会再骗人一次**。

`d747af8da` + `742ba002c` 六定律**负向测试**补齐 C1/C2/C3 + V1/V2/V3。
写负向测试的动机是回答一个具体的质疑：「**是不是真机械化，还是只是文档里说机械化**」。

### 14:00–15:30 · 白盒三件套 + 一个必须记下的错误

`6d16a350c` `cortex-trace.sh`（透明机箱）→ `e78d6fdd3` `cortex-dashboard.sh`（一屏总览）→ `e002c7438` `cortex-ci.sh`（每日约束）。

三者与 probe/pulse 凑成五工具，**正交不重叠**。ci 与 pulse 的分工是这天想清楚的：
> **一个系统完全可以很健康地跑偏**——指标全绿，但门被悄悄放宽、目标被悄悄降低。
> 所以 pulse 问「今天健不健康」，ci 问「**还是不是原来那个东西**」，且 ci 退出码 **2 = 目标被改松**，比测试失败更严重。

`e5e61a678` **dashboard `--json` 输出非法 JSON**。
这个 bug 单独记，因为它不是格式问题：**人读那面毫无异样，机读那面直接断**——
自愈链的第一环就断在这里，而没有任何人会察觉。这正是 [[glassbox-doctrine|GLASSBOX 律]]「人机同读**同一份**真相」的反面：
只要两面来源不同，**分叉是必然的，且总是机器那面先烂**。

同段还有两条自我纠错，如实记：
- `e78d6fdd3` commit message 里写明「**撤回我一个基于错误前提的修复**」
- `7f3f05678` 复核发现 13:34 那次实测**跑的是修复前的代码**（用打印字符串为证）——
  结论对不对先不论，**前提本身是假的**，整条推论作废

### 15:00–16:00 · 补上「我不受约束」这个漏洞

`22d5ccb62` → `ab69450ee` **主线程升为完整对等节点**。

起因是一个很不舒服的自问：环给每个自动节点算信任、扣违约分，
**但发号施令的那个（我）不在任何账本里**。这等于「谁定规则谁豁免」。

解法是把主线程做成 `orchestrator-<host>` 独立节点（`kind=orchestrator`，人机接口非执行体），
配 `checkin` / `credit` / `fault` 三个子命令——**有扣分必须有加分，否则没人敢自主**。
`c739cc3a1` 紧接着修「违约扣到了错误的节点」，且**误记豁免不删账**——错记也是记录，删了就没法复盘。

**蜂群整体信任 = 加权均值 × 短板因子**，不是取平均了事：
一个 L1 节点能干的坏事，不会因为旁边站着一个 L5 就变少。

`216a194d0` `readjudicate` 冤判复核，过门率 **20% → 75%**。
关键在于它是「**用当前判据重判**」，不是特赦 —— 判据改准之后，之前被烂判据误杀的要还回来，
但**判据本身不能为了好看而放松**（那是 ci 退出码 2 要抓的事）。

### 16:00–20:00 · 信任是刷的还是干的

`0f167ca4d` **E014 空转刷分**：判据**本来就满足**的任务，重跑一遍仍计 passed。
一次放行 17 条，事后查出 **7 条是空转**。

根因不是判据写错，是**用错了严格度**：
> 在信任 **L1** 的阶段用了**抽检**的严格度。

`d121dc721` 补上分档（服装厂验货逻辑）：新供应商全检，老供应商抽检。

| 信任 | 强度 | 查什么 |
|------|------|--------|
| 低 | **全检** | 不只验「判据现在过」，还验「**这次做完世界有没有变化**」 |
| 中 | 抽检 | 仍过 AI 验收，但不逐件查时间戳 |
| L4/L5 | 免检 | 机械门过了就认，省下验收调用（验收本身要烧模型调用） |

`34e8450f1` + `6a3bd6d3c` **E015 闲置率 59% 的根因链**，这是当天最长的一条因果链：

```
空转门识别出第四态 → 但只 continue、没给它落脚点
  → moot 被折叠回 pending → 计划永远闭不了
  → tick「先接旧活」分支被一个早已没活的计划锁住
  → 6 拍零产出
  ＋ 认领与执行互相把对方算成负载 → 节点显示满载，实则零产出
```

修法是给第四态**自己的命名空间** `refs/swarm/<swarm>/moot`。
为什么不塞进 `result`：**空转既不该加分也不该扣分**，塞进去会污染 HAAS 与过门率。
—— 这条后来升为 **T9**。

`bin/cortex-loop idle` 同时诞生，因为讨论闲置率时发现**分母就是错的**：
墙钟应跑 96 拍，但笔记本合盖那些拍机器**根本没跑**。用墙钟当分母，闲置率是虚构的。
四态口径：有产出 / 记终态 / 真闲置 / **认不出**（独立第三态，不倒向任何一边）。

---

## 三个反复出现的元模式（当天最该记住的）

### ① 每一道新门，首日必被自己的实测打脸

传播门 v1（9:00 立 → 10:52 被证伪）· PULSE（8:56 立 → 9:09 修自己首日暴露的两个缺陷）·
`991016f78`「负向测试逮到我自己的修复是死的」。

**推论**：门立完不算完成，**门被自己的测试红过一次才算**。
所以 suite 里每个负向测试都要经破坏性验证——不验证「真的会红」的测试，本身就是一道假门。

### ② 判据的严格度必须随信任变化，固定严格度两头不讨好

固定严格 = 高信任节点白烧验收调用；固定宽松 = 低信任节点空转刷分（E014 实测 7/17）。
这跟「AI 只有否决权没有批准权」是同一原则的两个层：**不对称**是本质，对称是偷懒。

### ③ 「我不在账本里」是最容易忽略的漏洞

给别人立规矩很自然，把自己放进同一套规矩里要专门想一下。
`orchestrator-*` 节点 + `fault` / `credit` 是这天补的，但它暴露的是更普遍的盲区：
**元治理层默认豁免自己**。—— 与 [[epiplexity]] 公理 1 同源：同一观察者评自己的产出，盲区完全重合。

---

## 当日留下的账（未完成，不美化）

| 项 | 状态 | 说明 |
|----|------|------|
| suite H03 维度坍缩扫描 | **SKIP** | 1 处候选待人工核对「性价比是否值得展开」，非红非绿 |
| `loop-ops` T2 | 未证实修好 | 第 4 轮确认是 **openclaw CLI 结构性阻塞**，非 mercury 本身问题（`f176a2594`） |
| 过门率 | 20% → 75%（readjudicate 后） | 仅作累计战绩；target 未批准，不作为完成门 |
| 闲置率 | 59% → 根因已修，**效果待下一个完整无人值守窗口验证** | 修在 19:40，当天没有足够长的窗口复验 |
| 自造损伤 | 已如实记（`e8efd0a34`） | `ANTHROPIC_API_KEY` 污染 adapter + 我自己造成的孤儿认领 |

---

## 2026-07-30 · S0/S1/S2 闭环后的独立审计

- 两批 `clock-auto` 计划形成 26 条完整 discovery/result/learning lineage，MAP 48/48
- S2 合链接门户只读影子回放完成，仍禁止自动晋级
- 第一轮 Dashboard 虽能显示 lineage，却把“窗口未批准”误写成“无 cohort”，并把回执字段绑定夸成 VERIFIED
- 独立审计后拆成：`BASELINE` / `UNMEASURED`、legacy `unclassified` debt、
  `receipt_binding` / `origin_reachability` / `verification_replay`
- 第二位独立复验又用“可达 commit + 不存在的 artifact 路径”打穿一次，最终收紧为
  **origin head 可达 commit × 安全仓库相对路径 × blob 存在**三项同时成立
- Dashboard 本地 origin 路径建立 `<15s` 预算，当前 fixture 实测通过；JSON invalid reasons 只保留 5 条摘要

机械门：`python3 bin/cortex-loop-tests/fixtures/negtest-dashboard-json.py`

---

## 2026-07-31 · 执行引擎从“会回话”升级为“真干活”

### 15:28 · Repair Controller、MiniMax 与指标合同最终闭环

- 日累计预算升级为 Git ref CAS；named-task 增加 clean/commit/origin 三验。
- 失败上下文从 `/tmp` 迁到有界、脱敏、原子持久账本，重启后仍可进入 repair。
- raw MiniMax/GLM 从 `exec.*` 降为 `text.*`；`cheap` 以 Claude Code + CC Switch
  MiniMax 作为唯一廉价 workspace executor。
- Mercury 真跑 MiniMax 成功；T2、T18 完成，三条信任 ref 已到 origin。
- HIVE 任一 PENDING 即 fail-closed；live WeCom 内联 webhook 改共享 resolver。
- G1 retry duplicate 与 G2 `_settled` 污染修复；批准 G1 7 天、G2 24 小时两个 90%。
  当前 G1 69.2% 如实红，G2 100% 绿。
- fresh suite `49/0/1`；live autonomy `10 PASS / 0 FAIL / 0 UNKNOWN`。

### 13:57 · mercury 旧模型覆盖揭晓

`openclaw cron get` 证明 `mercury-daily-ops-report` 仍有独立 per-job 覆盖：
Gemini timeout 后回退失效 GLM 401，累计 13 次错误。defaults 与 Cortex adapter
切到 MiniMax 并不会穿透 cron 覆盖。已用官方 CLI 改为
`minimax/MiniMax-M2.7` 并清空 fallback；真实运行会把运营日报发到 Telegram，
需明确外发批准后再验收，未运行前不判 done。

- 真机确认 `cheap` 原先只是 raw MiniMax/GLM 文本补全，任务从未获得工作区工具。
- 改成 MiniMax-backed Claude Code 工具层，并以 `/tmp` Write+Read 证明真实执行。
- T21、T15、T19、T22 已通过各自 short_test 与完成门；launchd 首拍真实 claim T18。
- 补单实例 tick、worker PID 锁、失败短退避、孤儿回执恢复、任务合同/short_test 防篡改。
- Dashboard 实时解析两份 TASKS，显示逐线 running、fails、launchd runs/last-exit/heartbeat。
- 新增 task-add/list/show/retry/run 原子命令；任务生命周期不再靠手搓 Markdown。
- 生产权限全套 suite：49 PASS / 0 FAIL / 1 SKIP（H03 人工成本收益候选）。

根因与证据：`reports/2026-07-31/cortex-loop/cortex-loop-execution-engine-closure.md`。

## 2026-08-01 · 锁域从全局串行改为最小资源互斥

- 删除全生命周期 tick lock；异任务并发、同任务 task flock 排重。
- TASKS 多字段原子写 + status CAS；task-add 私有候选先过 gate 后发布。
- cheap 改为 3 Worker 槽 + MiniMax account lease；冷却状态加 flock/fsync/replace。
- Git transaction 增加活 owner/stale/index/merge 判定，candidate scan 与 deploy 移出锁；
  pre-commit 禁止裸提交自建锁。
- H23 与 Git V4 专项全绿；Dashboard H09 no-origin fixture 去除真仓泄漏。

### 23:13–23:45 · 执行面升级为低磁盘分布式交付

- 复盘证明只缩 Git transaction 不够：控制 ref 已分布式，Worker 仍共写根 worktree/index。
- 实测稀疏 linked worktree 仅新增 6.4M，而共享对象库约 3.4G；据此否决“完整 worktree 每任务复制”的方案。
- 新增 workspace broker、candidate publisher、blobless integrator 与 delivery-plane inspector；崩溃、残锁、磁盘不足、越界、只读依赖、short_test 红、双写 CAS 全有负测。
- 完成语义拆成 candidate-visible 与 master-landed；前者只进 `integration_pending`，后者才允许 done。
- Dashboard 新增交付流水线，分别显示隔离舱、Candidate、集成回执、landed、retryable 与异常。
- EXPECTATIONS reader 修掉 `**met**` 误判及短行静默丢弃：真实总数从错误的 8 恢复为 20（met 12 / gap 4 / unknown 4）。

## 2026-08-02 · Dashboard Ctrl-C 批量误杀根治

- 两次 GUI 级联不是内存泄漏：系统日志明确记录由旧 `pkill` 分别终止 63、42 个进程。
- PATH 被 `/usr/local/bin` 的 `proctools/0.4pre1` 影子工具劫持；它在 macOS 26.3 忽略 `-P`。
- Dashboard watch 删除后台 collector、1Hz 全量重绘与父 PID 追杀，改为单前台同步快照；备用屏只承担原位显示，并在退出时恢复原终端状态。
- 影子 pgrep/pkill 已移入可恢复隔离目录；运行脚本统一显式 `/usr/bin/pgrep`。
- H33 验证 SIGINT 退出 130 且无残留进程组；H34 阻止影子二进制与裸进程查询调用回归。

### 06:54–07:11 · squash/replay 结算语义闭环

- 集成器会把多个源提交重放成一个 canonical commit；旧完成门只认源提交成为 master 祖先，导致内容已上线仍永久 settling。
- 新增统一结算检查：本地路径必须存在、非空、tracked、clean 且绑定源提交，再比较源提交与 canonical tip 的精确 blob OID。
- source OID 不可达但所有 artifact/check 路径 blob 完全一致时，以 `content-equivalent` 证明落地；任一路径不同仍拒绝完成。
- `task-show --settlement` 与完成门共用同一 helper；T64–T67 逐条经原子完成门从 settling 进入 done。
- H35 覆盖 squash/replay 正例、canonical 内容不一致、本地脏改、check 未落地与只读查询零副作用；全套 62 PASS / 0 FAIL。
- integrator 首次复验正确拒绝分叉内容冲突；随后补齐 `candidate compose` 原子入口，以临时 index 把精确写集投影到最新 canonical，避免手搓与共享仓 merge。

## 2026-08-02 · sparse attempt 失败回滚与旧舱收口

- 旧 T66 三个 attempt 在 V4 hook 失败后各从 1 个脏文件膨胀为约 2.9 万删除，定位到 tree 回滚丢 `skip-worktree` 元数据。
- V4 改为原始 index 文件快照；新增 skip-worktree 回归并通过完整专项。
- 三份不同 artifact 以原 SHA-256 归档，重应用 sparse 规则后均为 clean，再由 workspace broker 安全释放；分支和内容均保留。

---

## 2026-08-16 · 逻辑会话隔离不得退化为完整 worktree

- 为 ROSACE/ROSEUM 做知识交接时，错误地沿用了项目默认的完整 worktree 入口；该错误与磁盘余量无关，根因是把 Session/Agent/Topic 的逻辑隔离误当成文件系统隔离。
- 已将 E029 写入 `ERRORS.md`，并把硬规则同步到 Layer0 与长版 HIVE 指南：共享 OB1 的 Codex 会话必须 `environment=local`；需要隔离且写集已知时使用稀疏 broker；完整 worktree 只留给确有并发代码冲突或高风险探索的例外。
- 知识交接、只读审计、品牌规划、数据读取和跨 Runtime 迁移，永远不能因为“磁盘够”而复制整仓。错题、规则、报告和记忆落在主 OB1 真相源。

---

## Nav

| 文档 | 关系 |
|------|------|
| [[cortex-loop/SKILL\|SKILL.md]] | 主文档：9 条置顶铁律 / 五工具 / 三时钟 / 31 子命令 / 合同体系 |
| [[cortex-loop/ERRORS\|ERRORS.md]] | E001–E029 + 压轴教训「静默降级比报错更危险」 |
| [[cortex-loop-intent]] | 心跳总纲（canonical reading entry） |
| [[brain-network/directions/loop-ops/CHARTER-SWARM\|CHARTER-SWARM]] | 蜂群总纲：目标 G1–G6 / 范围 |
| [[cortex-loop-cron-error-triage]] | 试点线 T1 产出：10 条 error job 五类根因 |
| [[CLOCK]] | 调度声明 |
| [[knowledge-contract-registry]] | §4.12 四文件合同 · §4.12a ref 层协议 |
| [[steer-doctrine]] · [[pulse-doctrine]] · [[dimensional-expansion-doctrine]] · [[atomize-tools-doctrine]] · [[glassbox-doctrine]] | 当天诞生于本域踩坑的五条 Layer 0 律 |

---

*建立: 2026-07-28 · 续: 2026-07-29*

---

<!-- cortex:map-backlink d-112009e679396742854f3a6a -->
关联地图：[[skills/cortex-loop/MAP|Cortex Loop 全景地图]]

## 2026-08-27 · CORTEX Harness 归一清理：先身份，再处置

- 本轮把 5 条交叉审计视角改成了 5 个互斥处理批次；每个批次只拥有自己的路径集合，最终处置仍由统一清单收拢。
- 实际快照会随并行 worker 变化，因此 135/140/142 只能作为带时间的快照，不能当固定分母。最终清单必须冻结 `origin/main`、worktree registry、common-dir、remote、dirty/lock/进程和唯一 disposition。
- `${CORTEX_WORKSPACE_ROOT}/` 是混合路径：按 Git common-dir 区分 Cortex Harness 与 OB1，不能按目录名删除。OB1 总仓及其镜像保持不动。
- 7 个候选在 canonical `origin/main` 上发生 `modify/delete` 或依赖缺失，已保留源证据并拒绝强行整合；10 个明确无注册、无锁、无进程的临时目录已可恢复地移入 Trash。
- 继续清理时发现一条跨仓库登记：目标目录的 `.git` 指向独立临时 common-dir，canonical `git worktree remove` 因归属不一致而拒绝。复核其 clean、无进程、6.4 MB 后移入可恢复 Trash，再 prune canonical 失效登记；同步删除 4 个确认重复的本地分支，远端分支保留。当前 canonical registry 为 127，18 dirty、1 locked/initializing，未把剩余 clean 树自动当垃圾。

## 2026-08-27 · 第二轮审计工具化

- 第一轮的有效经验被转成原子合同：即时快照、Git identity、状态分轴、价值复核、可恢复引用和漂移失效；第二轮不再直接复用旧数字或旧清单。
- 工具边界固定为 read-only manifest：它可以生成唯一 disposition 和 `STALE_SNAPSHOT`，但不执行迁移、删除、prune 或授权。后续轮次只消费该 manifest，再由独立执行门决定动作。
- 经验同步写入 dispatch/cortex-loop 错题本与 MEMORY；canonical Cortex Harness 已有 legacy repository audit 工具，后续只做最小增量，不重复造同义工具。
## 2026-08-20 · 固定编组先于并发：Codex 子席越界

本轮暴露出“有并发槽位”不能推出“可以增加 Codex 子席”。CORTEX 的编组合同必须先于调度：4+3+2 固定为 Grok×2、Claude×2、MiniMax×3、Codex Luna×1、DeepSeek×1。已加入 Eval 负例和 Layer-0 禁令。
