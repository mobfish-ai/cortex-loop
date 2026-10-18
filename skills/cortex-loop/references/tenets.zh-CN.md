[English](tenets.md) | 简体中文

# cortex-loop 置顶铁律 T1–T9（全文 · 含真实代价）

> **何时该读**：SKILL.md 的 T1–T9 速查表只给「铁律 + 机械门」；
> 想知道**每条是被什么代价换来的**（哪次踩坑、哪个 commit、对应哪条 ERRORS）时读本文。
> **上级**：[[cortex-loop/SKILL|SKILL.md]] §置顶铁律 · **错题本**：[[cortex-loop/ERRORS|ERRORS.md]]

---

这 9 条不是"最佳实践"，是从 15 条 ERRORS 里反复现形的**同几个根因**提炼出来的。
每条都配了机械门 —— 靠人记必然复发，同一根因两天内咬过三次就是证据。
T1–T6 立于 2026-07-28（`c858a9ef9`）；**T7–T9 立于 2026-07-29**，因为这天多出了 07-28 还不存在的三个层：
三态判断（[[cortex-loop/ERRORS|E013]]）、跨机传播（传播门）、信任计分（[[cortex-loop/ERRORS|E014]]）。

| # | 铁律 | 为什么（真实代价） | 机械门 |
|---|------|-------------------|--------|
| **T1** | **Runtime 无关**：引擎不认识任何具体 runtime，能力/需求由 adapter **自声明**，加新 runtime 只改 adapter 不改引擎 | 硬编码 `claude`/`ANTHROPIC_*` 会让接 Codex/Gemini/自研时改到引擎核心 | `env-parity.sh` 从 `# cortex-loop:requires-env` 自声明取需求，零硬编码 |
| **T2** | **跨环境一致性**：交互式 shell 能跑 ≠ 无人值守能跑。调度器不继承登录 shell 环境 | 一晚三次：ollama 断 79%、worker 全线 `Not logged in`、Mac 7 次 403 | `bash bin/cortex-loop-tests/env-parity.sh` |
| **T3** | **失败关闭，不是失败开放**：验证器自己没跑起来 ≠ 内容通过；看不清就判拒绝 | E011：验证器遇 502 报错，旧逻辑「没看到 REJECT 就当 ACCEPT」放行了假完成 | `ai_judge` 见 `[ADAPTER_FAILED]`/空输出直接 REJECT |
| **T4** | **判据要问「这一条具体的事变了没」**，不能问「重跑会不会报错」 | E011：扫描器 WARN 不影响退出码 → 任务永远"通过"，不管有没有真修 | `short_test` 用否定判据 `! (<扫描器> \| grep -qF <具体项>)` |
| **T5** | **静默降级比报错更危险**：任何"降级/退回/兜底"必须出声 | 本项目 DNA 第 1-9 次现形（E001/E002/E003/E005/E008/E009/E011…）全是"退出码 0、日志正常、功能已坏" | 退回快照必告警；push 失败打 stderr；`run_adapter` 非零退出加 `[ADAPTER_FAILED]` 前缀 |
| **T6** | **占位符 `-` 是合法值不是路径**：凡读 `-` 约定的地方都要显式排除 | 同类 bug 两次现形：`requires="-"` 被当能力名、`artifact="-"` 被当文件路径 | `fit_score`/`covenant_check`/机械门三处均已加例外 |
| **T7** | **三态不是二态**：「查不到」必须独立于「没有」，**UNKNOWN 绝不倒向任何一边** | E013 单日**五处**现形：`read_ref`/`list_refs` 读空当没有、gate 把 scope-gap 压成 FAIL、`ai_judge` 把 SCOPE 压成 REJECT、health 分类器跨版本失效当健康 | `bash bin/cortex-loop-tests/dimensional-collapse-scan.sh`（已接入 suite）· 全部探针退出码 0/1/**2** |
| **T8** | **完成 = 传播到别人看得见的地方**：只躺在本机磁盘上的产出不算完成 | 幽灵完成 real1/R2 —— worker 判 done，产出从没进过 git 历史，蜂群里没人看得见（`54b1dd836`）；v1 只查 `git log -1 -- <path>` 非空，被真机当场打脸（`28f7d5d41`） | 传播门 v2：查 artifact **是否进了 origin 可达的历史**，不是本地有文件就算 |
| **T9** | **信任只能由真实变化换来**：判据本来就满足的重跑 = 空转，既不加分也不扣分 | E014：17 条一次放行，事后查出 7 条是空转刷分 —— **在信任 L1 的阶段用了抽检的严格度**（`0f167ca4d` / `d121dc721`） | 空转门在烧额度前拦掉 + 第四态 `moot` 独立命名空间（不进功劳账）+ 查验强度按信任分档（全检/抽检/免检） |

---

## T1 落地方式（接新 runtime 时照做）

在 `bin/cortex-loop-adapters/<新runtime>.sh` 头部写一行：

```bash
# cortex-loop:requires-env PATH HTTP_PROXY ...
```

`env-parity.sh` 会自动把它纳入校验，**引擎与门都不用改**。

---

## 元模式：每一道新门，首日必被自己的实测打脸

传播门 v1（9:00 立 → 10:52 被证伪）· PULSE（8:56 立 → 9:09 修自己首日暴露的两个缺陷）·
`991016f78`「负向测试逮到我自己的修复是死的」。

**推论**：门立完不算完成，**门被自己的测试红过一次才算**。
所以 suite 里每个负向测试都要经破坏性验证 —— 不验证「真的会红」的测试，本身就是一道假门。
（这条已在 [[cortex-loop/JOURNAL|JOURNAL.md]] §三个反复出现的元模式 立档；是否升格为律见 [[cortex-loop/EXPECTATIONS|EXPECTATIONS.md]] §候选律。）

---

## Nav

[[cortex-loop/SKILL|SKILL.md]] · [[cortex-loop/references/commands|commands]] · [[cortex-loop/references/architecture|architecture]] · [[cortex-loop/references/swarm|swarm]] · [[cortex-loop/references/contracts|contracts]] · [[cortex-loop/references/operations|operations]]

---

<!-- cortex:map-backlink d-8c94cb5cf6b251f5ea1f210b -->
关联地图：[[skills/cortex-loop/MAP|Cortex Loop 全景地图]]
