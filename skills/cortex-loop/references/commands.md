# cortex-loop 子命令全表（按族详解）

> **何时该读**：要用某个子命令但忘了它干什么 / 有什么参数 / 什么时候该用；
> 或想知道「这一族里还有什么工具我没用过」。
> **上级**：[[cortex-loop/SKILL|SKILL.md]] §子命令六族（那里只有族级总表）
> **真相源**：`bin/cortex-loop`（引擎）

退出码统一：`0`=正常 / `1`=红灯或失败 / `2`=用法错。
**只有「AI 挂载点」那族会烧额度**，其余全是零 LLM 的纯代码。

---

## 心跳与账本（零 LLM）

| 子命令 | 干什么 | 什么时候用 |
|--------|--------|-----------|
| `tick [--auto]` | 扫所有 enabled 线，算出到窗口的任务；`--auto` 才真推进一轮 | launchd 每 900s 自动敲。人手跑不加 `--auto` = 只看有什么到期 |
| `next --line X [--task T] [--claim]` | 渲染下一步**自足提示词**到 stdout；`--claim` 同时占坑为 `running` | 想手工执行一轮，或看看环会怎么派活 |
| `submit --line X --task T [--result F] [--window-min N]` | 收执行结果 → 写 JOURNAL + 推窗口；**永远不写 done** | 手工跑完一轮后回填 |
| `try-complete --line X --task T [--judge]` | **独立完成门**：artifact + `short_test` 过 → 再 land/origin；传播暂不可用时写 **`settling`**（执行已绿），不把已验绿工作打回「没干」；origin 可达才 **`done`** | 唯一能写 `done` 的命令。`settling` 由下一拍 tick 只做 land 结算。`--judge` 叠加 AI 否决 |
| `status` | 人读概览：每条线 enabled / executor / 各状态计数 | 想一眼看全局 |
| `idle [--date D] [--json]` | **拍口径四态普查**：有产出 / 记终态 / 真闲置 / **认不出**，分母只含真跑过的拍 | 问「闲置率多少」时。**别用墙钟当分母** —— 笔记本合盖那些拍机器根本没跑 |
| `task-list --line X [--status S] [--json]` | 原子查询一条线的任务，不再 grep/awk 手搓表格 | Dashboard/Agent 要列队列或按状态过滤 |
| `task-show --line X --task T [--json] [--settlement]` | 精确取一条任务；默认人读，`--json` 输出 `cortex-loop/task-show-v1`；`--settlement` 只读解释 artifact→commit→origin→canonical exact-blob 绑定，缺证据明确 `UNKNOWN`；integrator squash/replay 后以 `content-equivalent` 证明落地，不误绑提交祖先关系 | 排障、审计、派发前读合同，或查任务为什么停在 settling；禁止再手搓 `git log/ref` 拼判断 |
| `task-add --line X ...` | 按账本真实表头生成任务行；缺正/负判据拒绝，合同门失败自动回滚 | 新增任务，禁止手拼 Markdown 列 |
| `task-retry --line X --task T --reason R [--reset-fails]` | 原子把失败任务重排到当前窗口；done/blocked/human-gate 不暗中重开 | 根因修复后立即重试 |
| `task-hold --line X --task T --status blocked\|waiting_external --reason R` | 原子挂起并停止自动重试 | 等外部授权或已确认技术阻塞 |
| `task-resume --line X --task T --reason R` | 原子解除 blocked/waiting_external，保留失败史并恢复 pending | 阻塞条件已解决 |
| `task-reopen --line X --task T --reason R` | 撤销一次假完成，清 evidence、增加 fails、原子退回 pending | 短测失真或完成声明被新证据推翻 |
| `task-run --line X --task T` | 精确执行一条任务，仍走 claim→工具型 adapter→submit→完成门 | 端到端冒烟或只跑指定任务；会烧模型额度 |

## 自检与对账（零 LLM）

| 子命令 | 干什么 | 什么时候用 |
|--------|--------|-----------|
| `health` | 驱动自检：cron 真实执行失败率 >15% → RED（退出码 1） | 每次 `tick --auto` 前自动跑；怀疑地基坏了也手跑 |
| `reconcile` | CLOCK **声明** vs launchd/cron **实际** → 输出 DRIFT | 「说部署了但真在跑吗」；改完 CLOCK 必跑 |
| `dashboard` | 引擎内建的账本总览（与 `bin/cortex-dashboard.sh` 一屏总览互补） | 只想看账本层，不需要全系统 |
| `why [--node N]` | **信任为什么涨/跌**：逐条追溯每一次加减分 + 识别空转刷分 | 有人问「凭什么这个节点是 L3」；怀疑分数是刷的 |
| `value` | V1/V2/V3 价值三律机械核验 + 杠杆率（六定律价值侧） | 问「这套东西到底产出了什么价值」 |

## 蜂群协调（多节点 · 零 LLM）

| 子命令 | 干什么 | 什么时候用 |
|--------|--------|-----------|
| `swarm` | 刷新本节点画像 + 打印群体存活表（含无人认领的线） | 想知道哪台机在线、哪条线没人管 |
| `sync` | ref 层收发心跳（`refs/swarm/<swarm>/beat/<node>`），**不碰工作区** | 每台机定期跑；脏树/坏 auto-sync 都拦不住它 |
| `lease --line X [--ttl-min N]` | 抢线的 scheduler 租约（git ref CAS 原子锁） | 手工验证锁；`tick --auto` 内部以短租约竞争；worker 生命周期不由此锁住 |
| `caps` | 全群能力矩阵 + **单点能力告警**（只有一台机有的能力 = 单点故障） | 想知道「这台机掉了会瘸哪条腿」 |
| `checkin [--out]` | **主线程接入/退出蜂群** —— 与自动节点对等的心跳 | 开始一段有产出的会话时接入；结束时 `--out` |

## 去中心化分发（plan-claim-result · 零 LLM）

> **无 leader、无选举、无 quorum。** git 服务器只提供存储 + ref 的原子 CAS。
> CLOCK.owner 只提供亲和性提示；短 scheduler lease + 任务级 claim 解决「谁此刻调度」，本族解决「一个计划怎么拆开、被多台机器自主认领并汇总」。

| 子命令 | 干什么 | 什么时候用 |
|--------|--------|-----------|
| `discover [--publish]` | **自主找活**：扫机械可查的缺口 → 候选任务；`--publish` 才真发 | 环没活干时自己找活。策略是**补低洼**（目标函数降方差，不是求最大值） |
| `plan` | 发布不可变计划 —— **任何节点都能发** = 去中心化编排入口 | 手工投放一批任务 |
| `claim` | 自评能力/形态/负载 → CAS 抢任务 | 手工验证认领；`tick --auto` 内部自动跑 |
| `run` | 认领 → 执行 → 回写一条龙（分发层执行入口） | 想跑完整一轮而不是分三步 |
| `result` | 认领者回写结果 | `run` 的第三段单独跑 |
| `gather [--settle]` | 任一节点汇总；**收不齐拒绝宣称完成**。`--settle` 带 CAS 防重复结算 | 计划跑完要结算 |

### 分布式 Git 交付原子工具

| 工具 | 原子动作 | 关键边界 |
|------|----------|----------|
| `bin/cortex-workspace.sh create/status/release` | 按 attempt 创建稀疏执行舱、查状态、clean 后回收 | 共享 objects、独立 index；磁盘不足/活 owner/foreign owner/脏舱 fail-closed |
| `bin/cortex-candidate.sh compose/validate/publish/inspect` | 从任意 source commit 向最新 canonical base 覆盖精确文件，再校验写集并发布不可变 candidate ref | `compose` 不 checkout、不碰共享 index；拒绝目录/缺路径；同 OID 幂等，不同 OID 不可覆写 |
| `bin/cortex-integrator.sh` | blobless 稀疏复验并 lease-CAS 更新 canonical master | `--allow` 可写、`--read` 只读；CAS loser 返回 75 重试 |
| `bin/cortex-workspace-inspect.py [--json]` | 汇总 workspace/candidate/integration/残锁/磁盘 | 只读；Dashboard `runtime.delivery_plane` 与它同源 |
| `bin/git-worktree-doctor.py --json [--skip-disk]` | 盘点注册 Agent 舱、认领、活进程、脏改、可回收数 | Dashboard `runtime.worktree_fleet` 与它同源；进程不可读即 UNKNOWN |
| `bin/git-worktree-doctor.py --claim PATH --owner ID --task ID [--ttl-hours 24]` | 使用者认领/续租 worktree | 中央 claim 含 owner/task/host/pid/heartbeat/expiry；他人活 claim 不可覆盖 |
| `bin/git-worktree-doctor.py --release-claim PATH --owner ID` | 主动释放认领 | owner 不匹配 fail-closed |
| `bin/git-worktree-doctor.py --reclaim PATH` | 回收受管目录内的旧 worktree | 仅 clean + 无 claim + 无活进程；保留 branch，detached 未合并 tip 先建 archive ref |

调试顺序：先 `workspace status` 看执行舱，再 `candidate inspect` 看跨节点可见性，最后看
integrator receipt 的 `landed/retryable_*/rejected_*`。candidate 远端可见但未落 master 时，任务必须保持 settling。

## 信任与约束（六定律落地 · 零 LLM）

| 子命令 | 干什么 | 什么时候用 |
|--------|--------|-----------|
| `trust` | **HAAS 实算 L1–L5**（六定律 C2）：全部从 ref 层实际记录统计，节点**无法自报** | 想知道谁能干多大的事 |
| `attest [--executor X]` | 验证执行器背后**真的是**声明的模型，三层强度 L-env / L-say / **L-print** | 新节点加入；怀疑自报模型不实 |
| `fault` | **主线程自记违约** —— 编排者也要被信任机制约束 | 我自己做错了。有扣分机制才叫约束 |
| `credit` | **主线程记一次自主做成** —— 有扣分必须有加分 | 我自主闭环了一件事 |
| `readjudicate` | 用**当前判据**重判历史 rejected（冤判复核，**非特赦**） | 判据改严/改准之后。实测过门率 20%→75%（`216a194d0`） |
| `model` | 各档模型可用性 + 当前选档（额度紧张自动降档） | 撞额度时想知道还剩什么可用 |

**L-print 为什么是最硬的一层**：自报和环境变量都是「**声明**」，声明可以撒谎；
行为分布是「**表现**」，装不了。`attest` 最强一档走 [[model-fingerprint/SKILL|model-fingerprint]]（Bruckner PAMELA）——
单 token 输出分布 = 模型身份，算 Jensen-Shannon 散度比对。
该 skill 2026-07-21 实证：cosplay「claude 贴 gemini」被 JSD=0.0 当场抓出。

**透明度封顶**（operator 2026-07-29 拍板）：结构化信息越透明、越可验证，信任才越高；
信息缺失或无法验证 → **信任被封顶**。所以**伪装没有收益** —— 装得再漂亮也换不来自主权。

| 透明度状态 | 上限 |
|-----------|------|
| 字段齐全 + attest 通过 | 不封顶（可到 L5） |
| 缺字段 / 未公开 `model.*` `billing.*` / 未做 attest | 封顶 **0.70**（最高 L3，只能干可逆的事） |
| attest **失败**（自报 ≠ 实测） | 记违约 + 封顶 **0.49**（打回 L1，只能读） |

## AI 挂载点（唯一会烧额度的两个）

| 子命令 | 干什么 | 什么时候用 |
|--------|--------|-----------|
| `decompose --line X [--apply]` | AI 把 INTENT 拆成任务行 → **结构验收后**写 `TASKS.proposed.md`；`--apply` 才并入账本 | 新线只有意图、还没有任务表时 |
| `judge --line X --task T` | AI 独立验收员看产出，只回 `REJECT:` 或 `ACCEPT`（第三态 `SCOPE` 单列，不压成 REJECT） | 探索型任务，机械门过了但怀疑内容空泛 |

> `decompose` 的结构验收是**机械的**：11 列不齐 / `status≠pending` / `success_criteria` 或 `failure_modes` 为 `-` / id 重复 → 整行丢弃并打印原因。mock 实测：3 行提议丢 2 行（M2 缺 `failure_modes`、M3 `status` 非法），通过 1 行。
> **Agent Code Gauntlet 默认门**（2026-08-02）：`decompose` 生成代码实现 / 多文件改动 / 高风险执行任务时，必须把验收写在实现前：`success_criteria` + 可跑 `short_test` + `out_of_scope`。主线程默认只编排/验证，执行交给 HIVE/sub-agent/worker；生产库/钱/权限/账务即使门绿也停等 operator 点闸；并行代码任务走独立 worktree/隔离 cwd。小改、纯查询、低风险机械命令可直做。

## 对外与自愈

| 子命令 | 干什么 | 什么时候用 |
|--------|--------|-----------|
| `api` | **对外统一入口**：同一道六定律门，JSON 出参 | 别的系统要调环。`bin/cortex-loop-mcp.py` 走同一道门 |
| `revive` | 自愈：诊断执行器 → 能修则修 → **修不了就摘能力让蜂群绕过** → 恢复后自动上线 | 执行器挂了 |
| `harness-run [title...] [--timeout N] [--json]` | 真实驱动**姊妹仓库** `cortex-harness/packages/agent-runtime` 跑一次 local-MVP（`scripts/cortex-local-mvp.mjs` → `executeCliEntry()`），把手敲 `pnpm --filter @cortex/agent-runtime` 收口成一个入口 | 要验 agent-runtime 接线是否还活着；**不是** tick 的替代品 |

> **最有效的复活不是修好挂掉的那个模型，是切到还活着的那个。**
> 额度耗尽是单点问题，蜂群有多节点多模型 —— 该做的是路由绕过，不是死等它恢复。
> 「宣告能力下线」这一步最关键：**不用修好，环也能继续跑**。
> `diagnose_executor` 先纯代码分类根因（missing / path / auth / quota / network / proxy / config / ok），
> **别一上来就叫模型** —— 根因类决定能不能自动修，`quota` 类**不该修，该绕过**。

> **`harness-run` 诚实边界**（2026-08-21 HANDOFF Q2 接线）：`agent-runtime` 目前只有一个验证
> 运行时脚手架（session/goal/lease/durable-autonomy loop）的**合成 2 步 executor**，不调用任何
> LLM、不做真实业务任务。跑通只证明「ob1 → cortex-harness 的接线可达」，不代表 agent-runtime
> 已具备真实执行能力。路径可用 `CORTEX_HARNESS_DIR` 覆盖（默认 `~/cortex-harness`）；
> node 版本按该仓 `engines`（`>=24.0.0 <25`）自动挑 `~/.nvm/versions/node/v24.*` 里最高 patch，
> 找不到则显式报 `node_v24_missing`，不会静默降级到不满足声明的版本（T5）。

---

## Nav

[[cortex-loop/SKILL|SKILL.md]] · [[cortex-loop/references/architecture|architecture]] · [[cortex-loop/references/swarm|swarm]] · [[cortex-loop/references/contracts|contracts]] · [[cortex-loop/references/operations|operations]] · [[cortex-loop/ERRORS|ERRORS]]

---

<!-- cortex:map-backlink d-299b7f1d69b17515abad28ce -->
关联地图：[[skills/cortex-loop/MAP|Cortex Loop 全景地图]]
