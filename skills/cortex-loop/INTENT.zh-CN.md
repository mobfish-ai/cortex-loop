---
claim: 在预授权边界内把真实缺口持续转成可验证、可传播、可回滚、可复用的现实变化
created: "2026-07-30"
host: cortex-loop
name: cortex-loop-intent
status: ratified
title: cortex-loop 终局意图 — CORTEX 自主兑现内核
type: loop_intent
updated: "2026-10-15"
---
[English](INTENT.md) | 简体中文

# cortex-loop 终局意图 — CORTEX 自主兑现内核

> **终局规范 SSOT。** 本文件定义最终方向；[[brain-network/directions/loop-ops/CHARTER-SWARM|CHARTER-SWARM]] 只定义 S1 当前运行目标。运行时和 CI 尚未迁移，不能拿 S1 指标冒充终局。

## 已确认

- cortex-loop 是整个 CORTEX 的**通用自主兑现内核**。
- `loop-ops` 是 S1 自运维试验线，不等于蜂群；`swarm` 是可选多节点拓扑，单机与多机验收同标。
- 机器只在预授权内自主推进；目标、价值、扩权和不可逆决定归 operator。
- 当前授权只到 S1；无新 Intent Pack，不得执行真实业务动作。

## Why / End State

CORTEX 的根病不是缺 Agent，而是意图依赖 operator 想起才继续；行动、世界结果和 Knowledge 写回没有稳定闭环。

> **CORTEX 在已授权的意图、预算和风险边界内持续运行（operator 在线、离线、异步均可），把真实缺口持续转成可验证、可传播、可回滚、可复用的现实变化；operator 在场时其当场指令优先于自主环路，系统只把价值取舍、UNKNOWN、扩权和不可逆决策升级给他。**

> **业务北极星（2026-10-15 operator 指定）**：① 全平台统一盘货（MOSSRIVER+Lulukaka+Treely 等全部品牌 × 独立站/Amazon/TikTok Shop/TEMU/SHEIN 等全部渠道）月销量 10,000 单 / 全年 GMV 1 亿 RMB；② CORTEX Harness GitHub 开源 + Blocks 商业化 + 1,000 付费用户；③ CORTEX 体系整体多快好省自主推进效率最大化。实现方法和增长路径由 RSI 闭环 hill-climbing 自主探索——operator 给方向和目标（随时补充信息），系统只报结果和阻塞，不报过程。
> 真相源：`work-studio/devops/infrastructure/data/cortex-asset-registry.json` `_meta.business_north_stars`
> 日期：2026-10-15

> 在场优先级 / 异步等待规则：operator 在场发出的当场指令优先于自主环路的当前调度（不接管既有授权边界）；自主环路已启动的原子步骤不被当场指令打断，完成该步骤后按当场指令重排后续队列；operator 异步回复（消息/批注）视同当场指令入队，不视为「等待授权」。依据 [[business/governance/AAR/2026-10-15-014-intent-continuous-mode-and-fourth-scarcity|AAR-2026-10-15-014]]。

## 四平面

1. **意图与授权**：目标、价值、范围、预算、风险、止损；缺失/冲突就停止升级。
2. **世界状态与价值**：现实、基线、效果；缺数保持 UNKNOWN。
3. **执行与拓扑**：账本、心跳、adapter；swarm 只管分片、租约、接管。
4. **证据与学习**：独立验收、传播、因果复核、Knowledge 写回；无世界效果就不完成。

沿用 [[dimensional-expansion-doctrine]]：**合并后会让下一步动作错误才展开；动作相同就合并。** 真实性收益必须大于认知、实现和运维成本。

世界结果不得被 artifact 替代。每个结果必须携带：
`metric_id / source / observed_at / baseline / comparison_or_counterfactual / owner / confidence / missing_policy`。

## 人机 Covenant：知情拍板，不是盲从

- operator 永久保留：目标与价值取舍、预算/风险、资金/法律/品牌/人员/客户承诺、不可逆动作、暂停/撤权/修订。
- 内核可自主：授权内发现、排序、执行可逆动作、恢复、验收、传播和学习。
- **异议是 Agent 的义务**：先审可达性、证据、机会成本、Goodhart 和副作用；不合理必须反对并给替代方案，不能把 operator 第一句话焊进 CI。
- operator 在看过异议后可显式 override；必须记录“原建议→反对证据→最终拍板→风险承担”。安全、法律、权限和不可逆红线不能被对话 override。
- 忠于意图，不盲从手段；见 [[founder-playbook/SKILL#模块一structured-dissent结构化唱反调|Structured Dissent]]。

按 [[mobfish-six-laws]] + [[business/mobfish/mobseed/2026-01-03-covenant-protocol-design|MobSeed Covenant]] 分层：

`终局 INTENT（理念）→ 阶段 Charter（授权等级）→ Intent Pack（方向线配置）→ Run Contract（单次动作）`。

下层可收窄、不可扩权；变更须版本化、可追溯、可撤权。**Authority / Trust / Safety / Observability 四维分开**；HAAS 总分只作证据之一。C1–C3 是授权护栏，V1–V3 是价值阶梯，价值高不自动获得权限。

业务接入必须签 Intent Pack：
`id/version / goal / value_metric / bounds / allowed_actions / authority / trust / safety / observability / budget / validity / approver / proof / stop_loss / kill_switch / rollback / downgrade / escalation / learning_sink`。缺项不得自动执行/续期；违约走 `STOP→REPORT→WAIT→RECORD`。

## 北极星与护栏

**无人值守意图兑现率** =
`观察窗内按时完成世界结果验证+origin 传播+学习写回且无人临时介入的 intent ÷ 窗口开始时已授权、到期、可机械验收且预算可用的 eligible intent`。

`UNKNOWN / escalated / moot / budget-rejected / expired` 必须分态显示，不得静默移出 cohort。基线前状态=`UNMEASURED`；阈值只能在真实基线后由 operator 拍板。累计历史只作战绩，不作当前门。

领先指标：发现覆盖、`claim→run`、`run→world-verified`、闭环 P50/P95、恢复率。硬护栏：越权、假完成、预算突破、目标漂移、丢证据均为 0；任一发生立即降级。信任决定授权，健康分只诊断，都不是价值。

## S0–S4 晋级

| 阶段 | 能做什么 | Exit 杀手级反验 |
|------|----------|-----------------|
| S0 可信底座 | 人或上层给定任务后，可靠执行、记账、恢复；任何失败不得假绿 | 断网/重启/adapter 失败/节点冲突不假绿且可恢复；`done` 只能由可信 run receipt 写入 |
| S1 自运维 | 在预授权的系统维护域内，**已知 eligible 任务无人值守自动执行**；新故障可发现、排序、修复、独立复验、传播和形成 learning candidate | 注入可回滚故障后，同一 lineage 完成 `discover→plan→claim→run→origin receipt→world verify→learning candidate`；缺证据、越界或失败必须降级而非卡死/假完成 |
| S2 业务影子 | 接入真实业务状态与反馈，但只给建议、不执行真实业务动作 | 前瞻盲测稳定不劣于人工基线，且 UNKNOWN、反例和机会成本完整呈现 |
| S3 受限执行 | 在显式 Intent Pack 内执行小预算、低风险、可逆的真实业务动作 | 有对照归因和止损；动作产生净效果，越界、不可归因或回滚失败立即退回 S2 |
| S4 方向闭环 | 在授权方向内持续感知、执行、复核和复用学习，人只处理价值取舍与扩权 | 连续两个业务周期优于基线、干预下降、学习被真实复用、零违规 |

`eligible` 不是“机器觉得值得做”：必须同时满足**已授权、到期、前提仍成立、预算可用、可机械验收、动作可逆**。不满足者分态进入
`escalated / moot / budget-rejected / expired / UNKNOWN`，不得静默移出 cohort，也不得为了提高自动执行率强行运行。

假绿停自动；失准重建基线；越界、不可归因或回滚失败退 S2；护栏破坏撤权。每级需机械证据、独立 Witness、operator 扩权签名，禁止自动晋级。

## Trade / Anti / Unknown / Proof

- 顺序：**真实价值 > 安全与授权 > 可复用学习 > 吞吐 > 利用率**。
- 禁止用命令数、节点数、过门率、闲置率或健康分替代阶段证明；禁止删账、改门、压平 UNKNOWN。
- 未决：首个业务沙盒、阶段阈值、业务 SSOT、归因方法、Intent Pack 机械合同。未知进入验证，不靠猜。
- 完成只看杀手级反验真实回显；执行者不得兼任最终验收者。

## Nav

[[cortex-loop/SKILL|SKILL]] · [[cortex-loop/MAP|MAP]] · [[cortex-loop/EXPECTATIONS|EXPECTATIONS]] · [[brain-network/directions/loop-ops/CHARTER-SWARM|S1 CHARTER]] · [[business/governance/AAR/2026-07-30-006-cortex-loop-terminal-intent|AAR-006]]

## AUTH-PACK-20261015（operator 14:31 批 · S1→业务执行级）

**范围**：MossRiver G2 增长线 + Cortex Fleet 内部工程。

**允许自动执行（无需逐次问 operator）**：
- Shopify API 可逆改动：文章/集合/商品正文、SEO 标题与描述、metafield、URL 跳转；每批 ≤50、公网抽 3、可回滚；面料/尺码口径按 operator 已定规则。
- 舰队内部：脚本/skill/例程/总线改动、PR 合并（Alfred 决定）、自愈重启。

**硬闸（永远升级 operator）**：花钱、不可逆删除、改价、对客户发信、扩权/新账号/ACL 变更、价值取舍。

**止损**：同类 REJECT 一天 ≥3 次或公网抽查失败即 STOP 报 Alfred。

**有效期**：长期，operator 一句话即撤。

**Nav**: [[cortex-fleet/SKILL|cortex-fleet]]（执行通道）· [[dsh-g2-seat-ops/SKILL|G2 席位运维]]
