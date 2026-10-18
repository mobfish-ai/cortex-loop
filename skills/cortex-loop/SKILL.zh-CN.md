---
name: cortex-loop
description: |
  CORTEX 心跳与蜂群：git 时钟推进任务（tick/try-complete/swarm/DRIFT）。AI 只有否决权，done 只能机械门写。
  Triggers: cortex-loop / 心跳 / 自动推进 / 方向线推进 / tick / 蜂群 / 租约 / HAAS /
  cortex-dashboard / cortex-probe / cortex-pulse / DRIFT.
  WHEN NOT: 一次性任务或战略拍板 → 直接做或 /hive; 写不出 short_test 先澄清完成标准.
type: skill
status: active
version: 2.1.0
host: loop-engineering-hub
mount_role: proactive-heartbeat-engine
related_skill: [loop-engineering-hub, hive, sub-agent-dispatch, cron, openclaw-master, evolve-ecosystem, model-fingerprint, epiplexity, cortex-architecture]
related_methods: [structure-as-contract, mobfish-six-laws, hive-doctrine, reap, triage-doctrine]
related_rules: [ground-first-doctrine, steer-doctrine, pulse-doctrine, dimensional-expansion-doctrine, atomize-tools-doctrine, glassbox-doctrine, latch-doctrine]
tags: [cortex-loop, proactive, heartbeat, swarm, contract, runtime-agnostic, trust, observability]
d_tier: D3
---
[English](SKILL.md) | 简体中文

# cortex-loop — CORTEX 心跳与蜂群

> **v2.1.0** · 建立 2026-07-28 · 蜂群化 2026-07-29 · 按四问重组 2026-07-29
> **真相源**：`bin/cortex-loop`（引擎）· `bin/cortex-loop-adapters/*.sh`（肌肉）· [[CLOCK]]（调度声明）
> **终局意图** [[cortex-loop/INTENT|INTENT.md]] · **错题本** [[cortex-loop/ERRORS|ERRORS.md]]（含 E031–E035 归一/快照门）· **日记** [[cortex-loop/JOURNAL|JOURNAL.md]] · **期待** [[cortex-loop/EXPECTATIONS|EXPECTATIONS.md]]
> **默认质量门**（2026-08-02）：主线程 = 编排/验证节点；执行 = HIVE/sub-agent/worker。代码/多文件/高风险任务必须先有 `success_criteria` + `short_test` + 本地门；生产库/钱/权限/账务、破坏性动作或目标歧义按 [[AGENT-CORE|AGENT-CORE §3.2]] 走人闸。普通可逆本地变更与 code PR 可自动推进，Guardian 通过后由 Merger 自动合并。小改、纯查询、低风险机械命令可主线程直做。L2 最小机械预检：`python3 bin/agent-dispatch-contract-gate.py <contract.md> --json`。声明了 `collaboration_pattern=distributed|long_proof` 时，同一门还拦 critic/falsifier 与 `failed_route_keep`。
> **编排内核5层**（2026-08-13 拍板）：本 `success_criteria`/`short_test` 合同即 dispatch-contract，是 5层编排内核里 Hatch 那一层；完整5层定位见 [[../loop-engineering-hub/SKILL#2-4-按合同分层-5层编排内核-2026-08-13-拍板-cortex-ob1-默认实施|loop-engineering-hub §2.4]]。协作模式字段见 [[../../aboutme/methods/structure-as-contract/dispatch-contract#03a-collaboration-pattern-spec-not-a-third-role-table|dispatch-contract §0.3a]]。

---

## 一 · 你是谁

> **cortex-loop = 把「事情往前走」的触发权，从人的记忆里搬到 git 里的时钟上。**
> 人提供**意图**；只有 §3.2 指定的生产、钱、权限、破坏性或目标歧义才需要拍板。拆解、推进、判完成、卡住来烦人——归环。

| 层 | 是什么 | 住在哪 | 会不会死 |
|----|--------|--------|---------|
| **账本** | 意图 + 任务 + 证据 | git：`CLOCK.md` / `INTENT.md` / `TASKS.md` / `JOURNAL.md` | 不会 |
| **心跳** | 到点叫醒账本，纯代码零 LLM | launchd `com.cortex.loop`（900s） | 重启自恢复；OpenClaw 挂了不受影响 |
| **肌肉** | 真正干活/判断的 AI | `bin/cortex-loop-adapters/{cheap,claude,codex,ollama,mock}.sh` | adapter 必须具备工作区工具能力；只返回文本不算执行 |

**边界**：不发明目标、不越过 §3.2 人闸；在已授权范围内自主拆解、推进和恢复。只做人做不好的两件事——**不忘**、**不停**。

## 二 · 从哪来

**病**：CORTEX 所有资产都是被动的（MEMORY / STATUS / Directions / 全部 skills），只在「有人来读」那一刻才存在。**时钟源是 operator 本人** —— 一件事只要他没想起来，就永久停在原地，跟没写过一样。

**逼出它的两个事实**（2026-07-28 亲验）：① 主动性议题已攒 **8 份报告、0 行能跑的代码**；② 上一代 `*-advance` 九条**全线蒸发 live=0**，死了几个月**没有任何文件、任何 commit、任何人发现** —— 因为它活在 OpenClaw 的库里、**不活在 git 里**。结论：**心跳不能寄生。**

| 阶段 | 转折 | 证据 |
|------|------|------|
| 07-28 | 从 0 到双端蜂群：引擎 + CLOCK 合同 + launchd 时钟 + git ref CAS 租约 | 8 commit，`93ae328c5`→`62b597a8b` |
| 07-29 上午 | 发现「能跑」≠「跑对」：传播门、PULSE 上时钟、fail-open 族总清算 | E011/E012/E013 |
| 07-29 下午 | 白盒三件套 + 补「我不受约束」漏洞（`orchestrator-*` 节点 + fault/credit） | `22d5ccb62` `ab69450ee` |
| 07-29 晚 | 信任是刷的还是干的：空转门 + 第四态 `moot` + 查验强度分档 | E014/E015 |
| 07-30 | 26 条真 lineage 被 naive 时间误判未来；来源可读 ≠ 解释正确 | E016 |

全文见 [[cortex-loop/JOURNAL|JOURNAL.md]]。**这天新增的 6 条 Layer 0 律全部诞生于本 Skill 的踩坑**，不是先有律再有实现（见 §关联 Layer 0 律）。

## 三 · 到哪去

**终局方向真相源** = [[cortex-loop/INTENT|INTENT]]；
[[brain-network/directions/loop-ops/CHARTER-SWARM|CHARTER-SWARM]] 定义 S0/S1 运行边界；
`brain-network/directions/loop-ops/METRICS.json` 定义 G1/G2 的 cohort、窗口、样本、baseline、
target 与审批证据。`bin/cortex-ci.sh` 验证合同完整性和门未漂移（退出码 2），不把口头数字写死。

| 阶段 | 当前判据 | 看哪里 |
|------|----------|--------|
| S0 可信底座 | run receipt 能追溯 source/claim/origin/world，缺一不结算 | `fixture-result-receipt.py` + origin result ref |
| S1 自运维 | eligible 已知任务无人值守完成 discovery→learning lineage | `cortex-metrics.py --json` + Dashboard |
| G1/G2 | 无完整 baseline、滚动窗、最小样本和批准证据时不激活目标 | `METRICS.json` |
| 辅助诊断 | 健康、信任、闲置、积压不能替代阶段证据 | `cortex-dashboard.sh` |
| G6 | 蜂群健康分 ≥85 | 92「健康」 | ✅（但权重待复核：过门率差 44pt 只扣 8 分） |

**「要做但一直还没做到」的完整清单 → [[cortex-loop/EXPECTATIONS|EXPECTATIONS.md]]**（含机读 `--json` 出口）。

## 四 · 来干什么

子命令归七族。任务查询/生成/重排均已原子化；`task-run` 与 AI 挂载点会烧额度，其余控制面为零 LLM 纯代码。
无人值守默认每条线每拍只推进 1 个任务；`max_advance_per_day` 是日上限，不得再误作单拍并发量。
确需提高吞吐时显式设置 `CORTEX_MAX_ADVANCE_PER_TICK`，仍受日上限约束。
退出码统一：`0`=正常 / `1`=红灯或失败 / `2`=用法错。

| 族 | 干什么 | 子命令 |
|----|--------|--------|
| 心跳与账本 | 到点推进、原子建卡/查询/重排/挂起/恢复/撤销假完成、判完成 | `tick` `task-add` `task-list` `task-show` `task-retry` `task-hold` `task-resume` `task-reopen` `task-run` `next` `submit` `try-complete` `status` `idle` |
| 自检与对账 | 地基健不健康、声明与实际有没有脱钩 | `health` `reconcile` `dashboard` `why` `value` |
| 蜂群协调 | 谁在线、哪条线归谁、锁怎么抢 | `swarm` `sync` `lease` `caps` `checkin` |
| 去中心化分发 | 一个计划怎么被多台机自主认领并汇总 | `discover` `plan` `claim` `run` `result` `gather` |
| 信任与约束 | 谁能干多大的事、凭什么这么判 | `trust` `attest` `fault` `credit` `readjudicate` `model` |
| **AI 挂载点（烧额度）** | 拆解意图、独立验收 | `decompose` `judge` |
| 对外与自愈 | 别的系统怎么调、执行器挂了怎么办、姊妹仓库 agent-runtime 怎么真实跑起来 | `api` `revive` `harness-run` |

**每个命令的参数与「什么时候用」→ [[cortex-loop/references/commands|references/commands.md]]**

---

## ⚡ 置顶铁律 T1–T11（动手前必读 · 违反即返工）

> 不是"最佳实践"，是从 15 条 ERRORS 里反复现形的**同几个根因**。靠人记必然复发，所以每条都配机械门。
> T1–T6 立于 2026-07-28（`c858a9ef9`）；T7–T9 立于 2026-07-29（三态判断 / 跨机传播 / 信任计分）。
> **每条被什么代价换来的（踩坑 + commit + ERRORS 编号）→ [[cortex-loop/references/tenets|references/tenets.md]]**

| # | 铁律 | 机械门 |
|---|------|--------|
| **T1** | **Runtime 无关**：引擎不认识任何具体 runtime，能力/需求由 adapter **自声明** | `env-parity.sh` 读 `# cortex-loop:requires-env` |
| **T2** | **跨环境一致性**：交互式 shell 能跑 ≠ 无人值守能跑 | `bash bin/cortex-loop-tests/env-parity.sh` |
| **T3** | **失败关闭，不是失败开放**：验证器自己没跑起来 ≠ 内容通过 | `ai_judge` 见 `[ADAPTER_FAILED]`/空输出直接 REJECT |
| **T4** | **判据要问「这一条具体的事变了没」**，不是「重跑会不会报错」 | `short_test` 用否定判据 `! (<扫描器> \| grep -qF <具体项>)` |
| **T5** | **静默降级比报错更危险**：任何"降级/退回/兜底"必须出声 | 退回快照必告警；push 失败打 stderr；非零退出加 `[ADAPTER_FAILED]` |
| **T6** | **占位符 `-` 是合法值不是路径** | `fit_score`/`covenant_check`/三道机械门均已加例外 |
| **T7** | **三态不是二态**：「查不到」独立于「没有」，**UNKNOWN 绝不倒向任何一边** | `dimensional-collapse-scan.sh`（已接入 suite）· 探针退出码 0/1/**2** |
| **T8** | **完成 = 传播到别人看得见的地方**：只躺本机磁盘的产出不算完成 | 传播门 v2：查 artifact **是否进了 origin 可达的历史** |
| **T9** | **信任只能由真实变化换来**：判据本就满足的重跑 = 空转，不加分不扣分 | 空转门在烧额度前拦 + 第四态 `moot` 独立命名空间 + 查验强度按信任分档 |
| **T10** | **“模型回了文字”不等于“任务被执行”**：自动 executor 必须有 Read/Edit/Write/Bash 工具层，且任务合同、状态、short_test 由引擎保护 | `cheap-tool-smoke.sh` 真 Write+Read · task/short_test guard · worker 单实例锁 |
| **T11** | **进程边界不能靠 PATH 与模式猜**：自动化禁用 `pkill`；查询显式 `/usr/bin/pgrep`；终止只认创建者记录并校验的确切 PID | suite H33/H34 · `verify-process-tool-safety.py` |

**一键自检**：`bash bin/cortex-loop-tests/env-parity.sh && bash bin/cortex-loop-tests/suite.sh`
（suite 内含 8 个负向测试 `fixtures/negtest-*.py`，每个都经破坏性验证「真的会红」）

---

## 🔧 工具箱：五件套 + 两个辅助（先查工具，别手搓）

> **搓错过一次的命令优先级最高，它已证明会再骗人一次**（[[atomize-tools-doctrine|ATOMIZE 律]]）。
> 五个工具**正交不重叠**，各答一个不同的问题。

| 工具 | 答什么问题 | 关键用法 |
|------|-----------|---------|
| `bin/cortex-probe.sh` | **单点：这一件事是 YES 还是 NO？**（被动，问了才答） | `list` 看 10 个探针；退出码 0=YES / 1=NO / **2=UNKNOWN** |
| `bin/system-load-alert.sh` | **CPU 过载主动告警**（跟磁盘不够会告警同思路，不用等人去问）| 复用 `cortex-probe.sh system-load-pressure`；launchd 每 5 分钟探测；**同一过载段企微只一次**，恢复要连续约 30 分钟才算、不发「已恢复」（防 5 分钟翻转刷屏，见 git-management ERRORS §4.5）；detect-only，不能变出更多 CPU |
| `bin/cortex-trace.sh` | **为什么：这个判断是怎么来的？** | `state` `clocks` `wiring` `chain ci` `task <id>` `history [天]` |
| `bin/cortex-dashboard.sh` | **此刻：一屏看完健康/任务/CI/目标** | 裸跑 · `--json` 机读 · `--watch` 常驻 · `--md <路径>` 写 living md |
| `bin/cortex-pulse.sh` | **趋势：比上次差了没？** | 退出码 0=健康 / 1=有红项 / **2=比上次退化** |
| `bin/cortex-ci.sh` | **还是不是原来那个东西？（防跑偏）** | 退出码 0=全绿 / 1=有失败 / **2=目标被改松**（比测试失败更严重） |

**pulse 与 ci 的区别不是频率，是问题**：pulse 问「今天健不健康」，ci 问「**还是不是原来那个东西**」——
系统完全可以**很健康地跑偏**（指标全绿，门被悄悄放宽）。
**辅助两件**：`bin/cortex-loop-detach.sh <名> "<命令>"`（长跑挂 tmux，会话崩溃不连坐 · E010）·
`bin/cortex-loop-mcp.py`（对外 MCP 出口，与 `cortex-loop api` 共用同一道六定律门）。

## ⏰ 三个时钟（launchd · 职责正交）

| 时钟 | 周期 | 干什么 |
|------|------|--------|
| `com.cortex.loop` | **900s** | **推进**任务（做事） |
| `com.cortex.pulse` | **3600s** | **体检**健康趋势（P·U·L·S·E 五问） |
| `com.cortex.ci` | **每天 09:30** | **约束**不跑偏（全套测试 + 目标锚定） |

plist 在 `work-studio/devops/dotfiles/launchd/`。**核对实况**：`bash bin/cortex-trace.sh clocks` · `bin/cortex-loop reconcile`（声明 vs 实际，脱钩报 DRIFT）。

---

## When to Use / When NOT to Use

| ✅ 该用 | 为什么 |
|---------|--------|
| 一件事「只要没人想起就永久停在原地」 | 这正是心跳要解的病 |
| 方向线要自动推进且**完成必须机械可验** | artifact + short_test + 传播门 三验，AI 说完成不算数 |
| 要查「声明部署了但实际没在跑」 | `reconcile` 把名实分裂从文档纪律升级为机器红灯 |
| 多机协作：判谁在线/谁接管、一个计划被多台机自主认领并汇总 | `swarm`/`sync`/`lease`/`caps` · `plan`→`claim`→`run`→`result`→`gather`（无 leader） |
| 会话被掐断后要有人接着做 | `stall_min` 收回重推 |
| 想知道系统健不健康 / 凭什么这么判 | dashboard + trace + `cortex-loop why` |
| 要判「有没有 / 成没成」而手边只有一条会骗人的命令 | `bin/cortex-probe.sh`（三态，UNKNOWN 不倒向 NO） |
| 代码实现 / 多文件改动 / 高风险任务要自动推进 | 先立 `success_criteria` + `short_test`，再派执行体；主线程只集成与验证——完整 4 条默认动作见 [[agent-code-gauntlet\|aboutme/methods/agent-code-gauntlet]]（2026-08-02 立） |

| ❌ 不该用 | 用什么替代 |
|-----------|-----------|
| 一次性任务、需要人拍板的战略决策 | 直接做 / `/hive`；环不发明目标，战略目标歧义只澄清一次 |
| 完成标准说不清、无法写 `short_test` | 先用一次澄清冻结标准；同时完成已授权诊断并继续独立 DAG 分支 |
| 想让主线程承担长流程执行 / 多文件实现 | 走 HIVE / sub-agent / worker；主线程默认不做执行体 |
| 想在 tick 里顺手做形态升级（脚本→Skill） | **禁止在 tick 内 `transform-emit`**，走 REAP / detect-* 事后路径 |
| 想靠调低 tick 频率省额度 | 错方向。防雪崩靠 `advance_window_min` + `max_advance_per_day` |
| 想手搓一条命令判「有没有」 | 先 `bin/cortex-probe.sh list` 看有没有现成探针 |
| 想改门/改目标让指标好看 | `CHARTER-SWARM.out_of_scope` 明写禁止；`cortex-ci.sh` 退出码 **2** 专抓这个 |

## 自主推进与收口绑定（复用 AGENT-CORE §3.2）

本 Skill 不另定义 autonomy、approval 或 completion 政策。命令映射为：
`task-run` 在授权范围内自动推进，`task-hold` 仅记录真实外部 blocker，
`task-retry`/`task-reopen` 携带 repair/replay next action，`try-complete`
是唯一写 `done` 的机械门。`task-add` 冻结 success criteria、short test、
owned scope 和 verifier；完成证据由非作者复跑（可由 Guardian 执行）与机器
证据共同提供，按任务类型判断新鲜度。失败只挂起受影响依赖，独立 DAG 继续；
失败 settlement 必须保留 `first_blocker` 与 `repair/replay_next_action`；Harness
映射保持 `M1 → M3 → M2`，失败走 `M1_REPLAY → M3 → M2`。

## 最常用命令

```bash
bin/cortex-loop tick [--auto]        # 看什么到期 / 真推进（launchd 每 900s 跑 --auto）
bin/cortex-loop task-list --line cortex-immune --json
bin/cortex-loop task-show --line cortex-immune --task T18
bin/cortex-loop task-add --line X --title ... --success-criteria ... --failure-modes ... --artifact-paths ... --short-test ...
bin/cortex-loop task-retry --line X --task T --reason "根因已修"
bin/cortex-loop task-hold --line X --task T --status waiting_external --reason "等待明确外部授权"
bin/cortex-loop task-resume --line X --task T --reason "授权已取得"
bin/cortex-loop task-reopen --line X --task T --reason "短测只验文档，实际功能未接"
bin/cortex-loop task-run --line X --task T       # 精确走 claim→工具执行→完成门
bin/cortex-loop health && bin/cortex-loop reconcile   # 地基自检 + 声明vs实际（脱钩报 DRIFT）
bin/cortex-loop try-complete --line loop-ops --task T2   # 唯一能写 done
bin/cortex-loop swarm / trust / why / idle            # 谁在线 / 信任 / 凭什么 / 闲置率
bin/cortex-loop harness-run --json                    # 真实驱动姊妹仓库 agent-runtime 跑一次（脚手架验证，非替代 tick）
bash bin/cortex-dashboard.sh         # 一屏总览（--json 机读）
bash bin/cortex-probe.sh list        # 10 个三态探针
bash bin/cortex-loop-tests/suite.sh  # 全套测试
```

完整 cheatsheet → [[cortex-loop/references/operations|references/operations.md]]

---

## 按需加载索引（细节全在这几份，SKILL.md 不重复）

| 文件 | 何时该读 |
|------|---------|
| [[cortex-loop/references/commands\|references/commands.md]] | 忘了某个子命令的参数 / 什么时候该用 |
| [[cortex-loop/references/tenets\|references/tenets.md]] | 想知道 T1–T9 每条被什么代价换来的 |
| [[cortex-loop/references/architecture\|references/architecture.md]] | 要改引擎行为 / 加门 / 调额度；问「为什么不直接让 AI 判完成」 |
| [[cortex-loop/references/swarm\|references/swarm.md]] | 多机出问题（谁管这条线 / 判掉线 / 该不该接管）或要加机器 |
| [[cortex-loop/references/contracts\|references/contracts.md]] | 要改 CLOCK / INTENT / TASKS / 节点画像字段；合同门报缺失 |
| [[cortex-loop/references/operations\|references/operations.md]] | 新开方向线 / 装时钟 / 完整命令表 / 找相关文档 |
| [[cortex-loop/EXPECTATIONS\|EXPECTATIONS.md]] | 问「还差什么 / 一直没做到什么 / 下一步攻哪」 |
| [[cortex-loop/ERRORS\|ERRORS.md]] | 撞到诡异行为，先查已知母题；归一清理优先看 E031–E035 |
| [[aboutme/methods/asset-evolve/red-flower-board\|红花榜]] | 人读正向激励。L4/L5 仍由本 Skill `credit`/`trust` 记分；榜不重记分 |

---

## 关联 Skills（双向索引）

**host（上游）** [[loop-engineering-hub/SKILL|loop-engineering-hub]] —— 选型「该用哪个 Loop」先到 hub。
**同源** [[hive/SKILL|hive]]（`stall_min` 收回重推 = R·Resume 机械化）· [[epiplexity/SKILL|epiplexity]]（公理 1 = 验收员必须独立）。
**配套** [[sub-agent-dispatch/SKILL|sub-agent-dispatch]]（复杂编排）· [[model-fingerprint/SKILL|model-fingerprint]](`attest` L-print 判据)。
**邻接** [[cron/SKILL|cron]]（被 `health` 观测的对象，非心跳本体）· [[openclaw-master/SKILL|openclaw-master]]（改 job 走它）。
**上游治理** [[evolve-ecosystem/SKILL|evolve-ecosystem]] —— 四合同 + 七 ref 命名空间注册在 Evolve 合同体系内。
**体系架构总入口** [[cortex-architecture/SKILL|cortex-architecture]] —— 多栈晶格路由；loop 在 **C 执行/强制区**（心跳），Evolve 在 **B 知识边**；CLI `bash bin/cortex-architecture-map.sh hang loop`。
**写代码任务默认标准** [[agent-code-gauntlet|aboutme/methods/agent-code-gauntlet]]（2026-08-02 立 · Uncle Bob Agent Code Gauntlet · 验收先于实现/本地门/高风险人闸/worktree 隔离；当前 L1 文档默认，L2 机械强制 backlog）。
**ACP headless / 本地 Builder** [[acp-headless/SKILL]] —— 补丁合同与模型档位；L2 DECIDE 车道仍走兄弟 Recipe，不并入心跳引擎。
**摸高薄路由** [[peak-compound-loop/SKILL|peak-compound-loop]] —— 「何时推进」判定通过后，ROUND_CLOSE 收口挂 PEAK + TaskOptimizer 摸高门，不替代本 Skill 的完成机械门。

## 关联 Layer 0 律（本 Skill 是它们的机械落地面）

> 2026-07-29 新增的六条律**全部诞生于本 Skill 的踩坑**，不是先有律再有实现。
> **六律成链**（真相源 `rules/on-demand/ground-first-doctrine-guide.md` §11）：
> [[ground-first-doctrine|GROUND]] 先查 → [[dimensional-expansion-doctrine|DIMENSIONAL]] 别压扁 → [[atomize-tools-doctrine|ATOMIZE]] 量具可靠 → [[glassbox-doctrine|GLASSBOX]] 人机双读 → [[steer-doctrine|STEER]] 循环推进 → [[pulse-doctrine|PULSE]] 定期自检

| 律 | 机械后盾（在本域） |
|----|------------------|
| [[ground-first-doctrine]] 先查现状再谈方向；查验强度随信任 | `cortex-loop fault --kind decision-dodge` · `inspection_mode()` |
| [[dimensional-expansion-doctrine]] 状态别压成布尔（= T7） | `bin/cortex-loop-tests/dimensional-collapse-scan.sh` |
| [[atomize-tools-doctrine]] 手搓第二次必须成工具，三态输出 | `bin/cortex-probe.sh`（10 探针） |
| [[glassbox-doctrine]] 人机同读一份真相 | `bin/cortex-dashboard.sh --json` · `bin/cortex-trace.sh` |
| [[steer-doctrine]] 主线程 = 决策者，每轮重新摸 | `orchestrator-*` 节点 + `checkin` / `credit` / `fault` |
| [[pulse-doctrine]] 交付前五问，每问必带证据 | `bin/cortex-pulse.sh` · `autonomy-acceptance.sh` |
| [[latch-doctrine]] 提醒对重复违规无效 → 建 Hook | pulse / ci 上时钟本身就是 LATCH 的产物 |
| [[hive-doctrine]] R·Resume | `stall_min` 收回重推 |

---

*v2.1.0（2026-07-29 按保安四问重组 + 细节下沉 references/）· 真相源 `bin/cortex-loop` · 总纲 [[cortex-loop-intent]]*

---

<!-- cortex:map-backlink d-94388841c8da3735ac51e296 -->
关联地图：[[skills/cortex-loop/MAP|Cortex Loop 全景地图]]
