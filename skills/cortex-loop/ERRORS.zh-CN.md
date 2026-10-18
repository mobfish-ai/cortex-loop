[English](ERRORS.md) | 简体中文

# cortex-loop — 错题本

> **建立**: 2026-07-28
> **作用域**: `bin/cortex-loop` 引擎 + adapter + 四合同 + 蜂群总线
> **字段合同**: [[recipe-and-errors-contract]] §ERRORS — `id · symptom · root_cause · fix · never_again · related_skill`
> **铁律**: 任何踩坑先入此处，再改代码。修复必须带 commit sha。
> **主文档**: [[cortex-loop/SKILL|SKILL.md]]

---

---

## E021 · 执行与结算焊死：git 事务锁/push 失败 → short_test 已绿仍显示「没在跑」

| 字段 | 内容 |
|------|------|
| **id** | E021 |
| **date** | 2026-08-01 |
| **status** | closed |
| **related_skill** | cortex-loop |

**symptom**：IMM-T54–T57 四条 `pending` 在账本里挂着；`short_test` 本地已 PASS；`try-complete` 却 `FAIL artifact 落地失败 rc=75`（另一提交事务）或 push behind/SSL。人看到「没有 running、代跑不动」，以为任务没执行。

**root_cause**：完成门把三件事压成一条同步链：
1. 磁盘真值 + short_test（**执行面**）
2. pathspec commit + push + origin 可达（**结算/传播面**）
3. 全仓 `ob1-transaction.lock.d` 互斥（防 index 互踩）

2/3 失败时返回硬 FAIL 且 status 仍 `pending` → 「已验绿」与「还没干」同态（DIMENSIONAL 坍缩）。传播门本身有道理（防 worker 幽灵完成），错的是**把结算失败等价成执行失败**。

**fix**：
- 新状态 **`settling`**：short_test 已过、只等 git 传播；不是终态、不可 claim LLM
- `try-complete`：land 可重试失败 → `SETTLING`（exit 0），不记 attempt-fail
- `tick --auto` 每线先 `settle_line_tasks`（只 land→done），再 claim pending
- `commit_own_profile`：事务锁忙则 skip，**不阻塞 claim**
- `advance_once` settle-first/收尾识别 settling，不烧模型、不洗失败退避
- contract / task-add / probe 认 `settling`

**never_again**：
- **执行面不得等 git 锁**；**结算面可以排队**；二者状态必须可区分
- 「蜂群看不见 = 不算 done」仍成立，但不得反推「可以不 claim / 可以当没干」
- 任何 `FAIL` 出口问：是世界没变，还是传播通道忙？后者禁止打回 pending 失败语义

---

## E001 · read_table 把「列含义」说明表当数据表

| 字段 | 内容 |
|------|------|
| **id** | E001 |
| **date** | 2026-07-28 |
| **status** | closed |
| **related_skill** | cortex-loop |

**symptom**：首次冒烟，引擎读 markdown 账本读出一堆莫名其妙的行（内容是「列 / 含义」这种说明文字），不是任务。

**root_cause**：一个 markdown 文件里可以有**多张表**——顶部通常有一张「列含义」说明表，下面才是数据表。原 `read_table` 遇到第一个 `|` 开头的块就当数据表开吃，把说明表整张读了进来。

**fix**：`93ae328c5` `read_table(path, key=...)` 只认**表头含 `key` 列**的那张表；表头不含 key → `header=[]`，整张表跳过。

**never_again**：
- markdown 当结构化存储时，**表识别必须靠表头字段名**，不能靠「第一张表」「第 N 张表」这种位置约定
- 位置约定会在任何人往文档顶部加一段说明表时静默崩塌

---

## E002 · 传错主键 → 静默读到 0 行

| 字段 | 内容 |
|------|------|
| **id** | E002 |
| **date** | 2026-07-28 |
| **status** | closed |
| **related_skill** | cortex-loop |

**symptom**：`tick` 跑通、退出码 0、没有任何报错，但**一条线都扫不到**，行为等同「没有任何线启用」。

**root_cause**：`read_table` 默认 `key="id"`，而 `CLOCK.md` 的主键列是 **`line`** 不是 `id`。传错 key → 表头不匹配 → 整张表被当说明表跳过 → 返回 0 行。**E001 的修复本身制造了 E002 的失败模式**：跳过说明表是对的，但跳过时不吭声。

**fix**：`93ae328c5` `clock_lines()` 显式 `read_table(CLOCK, key="line")`，并在函数上方留死警告注释：
```python
# CLOCK 的主键列是 line（不是 id）；传错 key 会静默读到 0 行
```

**never_again**：
- 「读到 0 行」和「表里本来就 0 行」是**两件事**，代码必须能区分
- 每张合同表的主键列名写进合同注册表（registry §4.12 已列全 7 字段），调用方不许凭记忆传

---

## E003 · for-each-ref 格式串转义 → 静默退回文件快照

| 字段 | 内容 |
|------|------|
| **id** | E003 |
| **date** | 2026-07-28 |
| **status** | closed |
| **related_skill** | cortex-loop |

**symptom**：`sync` 报 `beat=True` 一切正常，但 `swarm` 只看得见 laptop 一个节点，**看不见 worker**——而 worker 的 ref 明明已经推上去了。

**root_cause**：
```python
git("for-each-ref --format='%%(refname)' " + namespace)   # ❌
```
`%%` 是 **`%` 格式化**语境下的转义写法。这里是**字符串拼接**（`+`），不走 `%` 格式化 → git 收到的是字面量 `%%(refname)` → 输出字面量 `%(refname)` → 过滤 `startswith(namespace)` 恒为空 → `read_swarm()` 拿到 0 个节点 → **静默退回本地文件快照**，于是只看得见本机自己写的那份 `.md`。

**fix**：`62b597a8b` 
1. `--format='%(refname)'`（去掉多余转义）
2. **退回快照必须显式告警**：`print("⚠️ ref 层读不到任何节点，退回本地文件快照…", file=sys.stderr)`

**never_again**：
- 拼接构造 shell 命令时，`%` 不需要转义；只有 `"..." % args` 才需要 `%%`。改代码从 `%` 格式化换成拼接（或反过来）时，**必须全串重扫一遍 `%`**
- **任何 fallback 分支都必须出声**。静默 fallback = 把 bug 伪装成正常运行

---

## E004 · 【致命】本地无 ref 时 rev-parse 返回空 → push 变成删除远端 ref

| 字段 | 内容 |
|------|------|
| **id** | E004 |
| **date** | 2026-07-28 |
| **status** | closed |
| **severity** | 🔴 致命（不可逆的远端数据删除） |
| **related_skill** | cortex-loop |

**symptom**：潜伏期缺陷，在造成损失前被拦下 `git push origin <sha>:<ref>` 中的 `<sha>` 若为空串，命令退化成 `git push origin :<ref>` —— 这是 git 的**删除远端 ref** 语法。

**root_cause**：`rev_ref()` 在本地没有该 ref 时，`git rev-parse --verify --quiet` 返回**空串**（不是报错、不是 None）。空串被当成正常的 parent/commit sha 拼进 push 命令，冒号左边空 → 远端 ref 被删。
本地没有 ref 是**最常见的正常情况**（新节点第一次 sync、fetch 失败、ref 未推送），不是异常路径。

**fix**：`51d317f9a` 
1. `rev_ref()` 严格返回 `None` 而非空串：`return sha if re.fullmatch(r"[0-9a-f]{40}", sha or "") else None`
2. `write_ref()` push 前硬校验：sha 必须匹配 40 位十六进制，否则**直接返回 False 不 push**
3. `acquire_lease()` 先 `fetch_refs()` 再判持有人——本地缺 ref 会被误判成「无人持有」
4. 全程**不加 `--force`**：非 fast-forward 必须被拒，被拒正是锁生效的信号

**never_again**：
- 任何拼进 git push 冒号左边的值，**必须先正则校验是 40 位 sha**。空值不是「没有」，是「删除」
- 「拿不到」的返回值用 `None`，绝不用空串——空串会被静默拼进命令字符串
- 破坏性语义靠**语法糖**触发（`:ref` = 删除）的命令，必须在调用点写死防线，不能指望调用方记得

---

## E005 · health 把「投递失败」当「执行失败」→ 环被通知渠道抖动瘫痪

| 字段 | 内容 |
|------|------|
| **id** | E005 |
| **date** | 2026-07-28 |
| **status** | closed |
| **related_skill** | cortex-loop · openclaw-master · cron |

**symptom**：`openclaw cron list` 32 条 job 里 10 条 `error`（31%）。`health` 原口径「error 比例 > 15% 即 RED」→ 判 RED → `tick --auto` 拒绝推进 → **整个自愈系统全面停摆**。

**root_cause**：逐条亲读 `openclaw cron get <id>` 的 `lastError`，见 [[cortex-loop-cron-error-triage]] 
10 条 error 里 **7 条根本不是任务失败**——

| 类 | 条数 | 是否真失败 |
|----|------|-----------|
| A 投递失败（`OutboundDeliveryError: sendMessage failed`，本机 Privoxy/Clash 掐 Telegram） | 6 | **否**，任务跑完了只是通知没送到 |
| D 投递目标歧义（`Refusing implicit isolated cron delivery`） | 1 | **否**，拒绝执行 |
| B 模型全挂 / C 执行超时 / E 工具调用失败 | 各 1 | 是 |

**真正的任务失败只有 3 条（9%）**，另外 7 条是投递侧问题。把报信失败当干活失败 → **一个通知渠道抖动就能让整个自愈系统停摆**。

**fix**：`f63bd4430` `cmd_health` 逐条读 `lastError` 并按正则分流：
```python
delivery_re = re.compile(r"OutboundDeliveryError|Refusing implicit.*delivery", re.I)
```
- 命中 → `WARN | 投递降级`，**不阻断推进**
- 其余 → 计入 RED 比例

实测：真实执行失败 3/32 (9%) → `HEALTH: GREEN`。

**never_again**：
- **健康检查必须区分「干活失败」与「报信失败」**。自愈系统的判红口径要是把观测通道的故障算进被观测对象，它就会在自己的传感器抖动时自杀
- 任何「比例超阈值即红」的口径，落地前必须**逐条读原始错误**确认同质，不能只数条数

**2026-08-03 补：A 类"投递失败"根因找到 + 真修了，不再是长期接受的已知缺陷**——

之前只是把 `OutboundDeliveryError` 分流成不阻断的 WARN，没查为什么会失败。这次查
`~/.openclaw/openclaw.json` `channels` 段，发现 **`discord` 渠道配了
`"proxy": "http://127.0.0.1:10794"`，`telegram` 渠道完全没配代理**——curl 直连
`api.telegram.org` 能通（GET/POST 都测过），但 OpenClaw 内部的 Node/undici 客户端
不知道要走代理，直连被墙，所以只有 telegram 渠道反复报 `sendMessage` 失败，discord
没这个问题。

**fix**：`openclaw config set channels.telegram.proxy "http://127.0.0.1:10794"`
（CLI 入口，不手改 json）。热重载生效，不需要手动 `launchctl kickstart`。**真实验证**：
`openclaw message send --channel telegram --target 7803302841 --message "..."` →
`✅ Sent via telegram. Message ID: 4685`，走的是真实投递通道，不是绕过测试。

之前那 6 条"投递失败"、以及本会话开头 PULSE 检查时看到的 8 条"投递降级"，大概率
都是这一个根因——**不再是要长期忍受的已知缺陷，是真的修掉了**。后续如果 telegram
投递还失败，先确认这条 proxy 配置有没有被某次 `openclaw setup`/`configure` 跑丢。

---

## E006 · 死凭据挂在 fallback 链末尾，长期无人察觉

| 字段 | 内容 |
|------|------|
| **id** | E006 |
| **date** | 2026-07-28 |
| **status** | waiting_external |
| **related_skill** | cortex-loop · openclaw-master |

**symptom**：`mercury-daily-ops-report` 连错 13 次，`lastError` = `FallbackSummaryError: All models failed (2): gemini timeout | zhipu/glm-4-flash: 401 身份验证失败`。

**root_cause**：GLM key 已失效（401），且该 cron 有独立的 per-job model/fallback
覆盖：`gemini/gemini-2.5-flash → zhipu/glm-4-flash`。只修改 agent defaults
和 Cortex adapter 不会穿透这个覆盖，因此系统层已经切到 MiniMax，mercury 仍继续跑
旧链。fallback 链末尾的死凭据平时不会被调用，只有 Gemini 同时超时才暴露。

**fix**：
1. agent defaults 与 Cortex adapter 使用 MiniMax；
2. 2026-07-31 通过 `openclaw cron edit` 把 mercury 的 per-job model 改为
   `minimax/MiniMax-M2.7`，并清空失效 fallback；禁止手改 `jobs.json`；
3. 真实运行会向 Telegram 外发运营日报，须取得明确外发批准后执行；运行成功前
   保持 `waiting_external`，不得冒充已修好。

**never_again**：
- **fallback 链是凭据的坟场**：兜底位置的失效凭据不会主动报错。凭据轮换/停用时必须**全链 grep**，不能只改 primary
- 模型切换必须横查 defaults、agent、cron per-job、adapter 四层覆盖；上层已改不代表
  独立 job 自动继承
- 「修好了」的验收必须是**自然运行下的真实通过**，不是为了让它变绿而人为触发一次

---

## E007 · 笔记本合盖 → launchd 停跳；「日志连续」被误读成「一直在跑」

| 字段 | 内容 |
|------|------|
| **id** | E007 |
| **date** | 2026-07-28 |
| **status** | closed |
| **related_skill** | cortex-loop |

**symptom**：心跳日志看起来一行接一行很连续，但中间有大段时间机器其实是睡着的，环**完全没在跑**。人看日志会以为「一直在跑」。

**root_cause**：笔记本合盖必睡，睡着时 launchd **不跳**；醒来只**补跑一次**（不会把睡过去的 N 拍全补上）。日志上呈现为「若干条正常记录」，时间戳之间的巨大空洞不显眼。

**fix**：`e007fc7ec` `sleep_gap_note()` 从心跳日志读上一次 tick 时间，间隔 > 2× 预期（默认 15min × 2）即在 tick 开头打印并写日志：
> `唤醒补跑：距上次心跳 N 分钟（预期 15）→ 机器大概率睡过，这段时间心跳是真空`

配套：`loop_node.can_sleep` 让蜂群用**差异化尺子**判存活——笔记本静默 14h 内正常，常开机静默 3h 即异常（详见 SKILL.md §蜂群）。

**never_again**：
- **心跳系统必须能观测自己的空洞**。只记「我跑了」不记「我该跑没跑」= 假可用性
- 「会睡的机器」和「常开机」不能用同一把尺子判死活，否则要么误报要么漏报

---

## E008 · 表头被后续表冲空 → 唯一写入口崩溃而非报红

| 字段 | 内容 |
|------|------|
| **id** | E008 |
| **date** | 2026-07-29 |
| **status** | closed |
| **related_skill** | cortex-loop |

**symptom**：`TASKS.md` 在账本表**之后**再出现任何一张表，`try-complete` / `submit` / `tick --auto` 全部抛 `ValueError: 表中无此列: status` **未捕获崩溃**——不是报红，是整个 tick 中断，后面的线一条都轮不到。

**root_cause**：`read_table()` 每遇新表就重置 `header`，表头无主键列则置空。于是返回的是**文件里最后一张表的表头**。`rows` 仍正确（所以 `load_tasks` 看着一切正常），`header` 却空了——而 `set_cell` 是账本唯一写入口，命中即炸。当时没爆只是因为真账本的「字段规矩」恰好写成了编号列表、CLOCK 的说明表恰好在数据表前面：**「数据表必须是文件里最后一张表」是一条没写进合同、也没人知道的隐式约束。**

**fix**：`89fa34d9e` — 只认第一张命中主键的表，之后的表不得覆盖已认下的表头。

**never_again**：
- 结构化解析器返回「部分正确」的结果（rows 对、header 空）比整个失败更危险，因为调用方看不出问题
- 任何「文件布局必须满足某种顺序」的约束，要么写进合同并由 gate 校验，要么就别让它存在
- 由测试套件的变异测试逮到——**改引擎前先拿改坏的副本过一遍门**，能证明测试不是摆设

---

## E015 · 认领与执行互相把对方算成负载 → 节点满载但零产出（闲置 59% 的直接原因）

| 字段 | 内容 |
|------|------|
| **id** | E015 |
| **date** | 2026-07-29 |
| **status** | closed |
| **related_skill** | cortex-loop |

**symptom**：`discover --publish` 发出 15 条真待办 → `claim --plan X` 成功占了 3 个坑
→ 紧接着 `run --plan X` 对**同样这 3 个任务**报：
```
pass | fm-ins-20260709-lilia — 超载（当前 3 + 本任务 1 > 上限 3）
本节点 laptop 执行 0 个：-
```
15 条真活排队、节点有额度有算力，**却一条都执行不了**。dashboard 显示闲置 59%。

**root_cause**：`cmd_run` 里对每个任务都跑一次 `fit_score(task, prof, load, max_load)`，
而 `load` 来自 `node_load(me)` —— 它统计「我持有的、未过期、无 result 的 claim」。
`claim` 刚占的 3 个坑正好全部符合这个条件。
于是：**认领把负载顶满 → 执行时这 3 个坑把自己挡在门外**。
`claim` 和 `run` 互相把对方的结果算成自己的负载，节点卡死在「满载但零产出」。

这不是负载判据算错了（`node_load` 逻辑本身正确，今天修过一次僵尸 claim 已生效），
是**同一个额度被计了两次**：占坑时算一次，兑现时又算一次。

**fix**：`cmd_run` 加自持豁免 —— `holder == me` 时按 `load=0` 计分：
```python
_mine_already = (holder == me)
score, why = fit_score(task, prof, 0 if _mine_already else load, args.max_load)
```
坑是我的，执行它是**兑现**而非新增占用。别的节点持有的 claim 仍照常计入我的负载
（那是真的抢不到，该让）。

**never_again**：
- **「占用」和「兑现占用」是两件事**，同一份额度不能计两次 ——
  这是 E013 维度坍缩母题在资源计量上的化身：把两种性质不同的状态压成同一个计数。
- **有活干却闲着 = 派发链断了**，要从「发→认→跑」逐段验，不能只看总量。
  本例中 discover 正常、publish 正常、claim 正常，断点在 run 的准入。
- 负载类判据要问一句：**这个数字里有没有包含"我自己刚做的动作"**。

---

## E014 · 空转刷分：判据已满足的任务重跑仍计 passed，信任被刷高

| 字段 | 内容 |
|------|------|
| **id** | E014 |
| **date** | 2026-07-29 |
| **status** | closed |
| **related_skill** | cortex-loop |

**symptom**：laptop 16:39–17:59 连续做完 8 个 `island-*` 任务，**全部 `gate=passed`**，
信任 L1→L3（0.492→0.774），账面上是全群最漂亮的节点。
operator 追问「涨的原因是什么」时查证：那些 skill 的 `host:` 字段
**12:18–13:10 就已经加好了**，节点做的是判据早已满足的任务。
`cortex-loop why --node laptop` 输出：**真做成 0 ／ 空转 8**。

**root_cause**：`cmd_run` 在执行前**不检查判据是否已经满足**。
流程变成：认领 → 调模型（烧额度）→ 跑 `short_test`（一跑就过，因为本来就过）
→ `gate=passed` → 信任 +1。**产出为零，分照涨。**

触发条件是「先接旧计划再发新计划」那次修复：它让节点回头接旧计划，
而旧计划里的任务在这几小时里**已被别的路径解决**（sub-agent 批量挂 host、
readjudicate 复核改判），于是旧任务变成空壳。

**为什么这比「做失败」危险得多**：失败会被 gate 拦、会扣分、会被看见；
**空转全程绿灯**。它同时污染三个指标 —— 过门率虚高、信任虚高、负载率虚高，
而 dashboard 上每一项都是绿的。这是「静默失败」母题在计分层的化身。

**fix**：
① `cmd_run` 加**空转门**（在六定律三关之前、烧额度之前）：
   `short_test` 已通过 → 打印 `noop | <task> — 判据已满足，无活可干`，
   **不写 result、不计分、不调模型**。红→绿双向实测：
   判据满足 → 退出码 0 → 跳过 ✅；判据未满足 → 退出码 2 → 正常执行 ✅。
② 新增 `cortex-loop why --node <n>` —— 信任涨跌逐条追溯并标注性质
   （真做成 / 空转 / 复核改判 / 被拒），末尾给「真做成 N ｜ 空转 M」。
③ 存量清算：8 条空转 result 改判 `gate=noop`（**不删 ref**），
   laptop 信任 0.774(L3) → **0.634(L2)**，并记 `noop-inflation` 违约一条。

**never_again**：
- **任何计分动作前先问「这次做完，世界有没有变化」** —— 没变化就不该计分。
  判据用 `short_test` 本身：它就是「这件事做完了没」的唯一真相源。
- **信任涨了要能说出涨在哪一条**。说不出来的涨幅默认可疑 —— 这是 `why` 存在的理由。
- **「全绿」不是健康的证据**，可能是没在干活。空转的账面比真干活还好看。
- 存量修正**改判不删账**：删 ref 等于抹账，违反计分机制存在的意义。

---

## E013 · 维度坍缩：把不同性质的信号压成一个判断，丢掉的是「为什么」

| 字段 | 内容 |
|------|------|
| **id** | E013 |
| **date** | 2026-07-29 |
| **status** | closed（4 处已修 · 1 处已发现待修，见 fix） |
| **related_skill** | cortex-loop |

**symptom**：同一天在完全不相关的 5 处代码里现形，表现各不相同：
① `cmd_health` 把「openclaw 编排层故障」和「本节点执行能力」压成一个
`RED/GREEN`，够不着时判 GREEN、够得着如实报故障反而判 RED——**越瞎越能干活**。
② `discover_candidates` 扫描器超时/崩溃时 `code` 从未被检查，`out` 空
就静默产出 0 条候选，系统报「一切都绿」。③ 传播门 v1 用 `git log -1` 非空
判断「本次改动进了历史」，实际查的是「这个文件曾经有过历史」——两者被
压成同一个布尔，真机判出一个 origin 上没有 host 字段的文件为 `done`。
④ `node_load` 把「任务在跑」和「任务刚做完」压成同一个 claim 状态，
节点干完 3 个就顶满上限，一小时接不了新活。⑤（已发现未修）`read_ref`
把「ref 不存在」（正常态）和「git 命令出错」（异常态）都压成同一个 `""`。

**root_cause**：
operator 2026-07-29 拍板命名，这是本条的核心。
**真实世界的状态天然是高维的**——「openclaw 故障」≠「节点故障」，
「扫描器无匹配」≠「扫描器挂了」，「文件有历史」≠「本次改动入史」，
「在跑」≠「刚做完」，「无数据」≠「读取异常」。**把高维状态压缩成一个
低维布尔/状态码，压缩时丢的信息恰好是「为什么」——而「为什么」往往才是
下一步该怎么办的关键。** 这不是「少查了几种情况」，是维度不匹配：
状态空间的维度必须与真实世界的维度对齐，该展开的地方硬要塞进一个
布尔，就是维度坍缩。

**fix**：
① health 分层——阻断域只留「本节点可确定性自验+因果直连」的三条
（交付通道断/账本通道断/合同不自洽），外部编排层降为告警域永不 red，
够不着时报 `UNVERIFIABLE` 而不是冒充 OK（`22b23217c`）。
② SCANNER-DOWN 门——`run()` 超时单独还原成 124（GNU timeout 约定码），
与「正常无匹配」的 1 区分开（`991016f78`）。
③ 传播门 v2——改查 `git status --porcelain` 必须为空（磁盘内容==HEAD内容），
不再查「文件是否曾入史」（`28f7d5d41`）。
④ `node_load` 改批量取 result ref 集合判断「已完成 vs 仍占用」
（`3ffc0fcb5`）。
⑤ **待修**：`read_ref`/`list_refs` 应返回三态（有数据/确认无数据/读取
异常无法确认），复用已有的 `UNVERIFIABLE` 范式。这两个函数被调用 20 次，
是全引擎最基础的读操作，比①-④更底层。

**never_again**：
以下规定动作写进所有新代码，扩展 E001-E003 的“压轴教训”。
- **任何二元判断（RED/GREEN、成功/失败、有/无）落笔前先问：真实世界这里
  有几种性质不同的状态？** 有 3 种就展开成 3 种，不要为了"简单"硬压成 2 种
- **"查不到"必须是独立的第三态，不能倒向任何一边**——倒向"健康"是
  fail-open（越瞎越能干活），倒向"故障"是过度保守，两者都是压缩的产物
- **同一个返回值不能同时表达两种不同性质的原因**——`""` 不能同时表示
  「本来没有」和「读取失败」；`False, ""` 不能同时表示三种不同的本地
  git plumbing 失败
- **修一个压缩点时，立刻问"这个母题还有几处"**——本条 5 处全部是同一天
  内靠这个问题扩大化搜出来的，最后一处（read_ref）是主线程用
  `grep 'if code ==\|== "OK"'` 扫出来的，不是巧合碰见的

**机械化沉淀**：`bin/cortex-loop-tests/dimensional-collapse-scan.sh`——
grep 全文件里「二元判断吞掉多种失败原因」的特征模式，作为 pre-commit/定期
扫描项，防止这个模子在新代码里复发而不是只查一次。

---

## E012 · 跨环境不一致：交互式 shell 能跑 ≠ 无人值守能跑

| 字段 | 内容 |
|------|------|
| **id** | E012 |
| **date** | 2026-07-29 |
| **status** | closed |
| **related_skill** | cortex-loop |

**symptom**：同一晚同一根因**三次现形**，每次都戴不同马甲：① `ollama pull` 断在 79%；② worker 侧 50 个任务全部 `Not logged in`；③ Mac 端 launchd 4 小时里 7 次任务全挂 `403 Request not allowed`。共同特征：**人在交互式终端手动跑一模一样的命令立刻成功**，于是极易误判成"偶发/网络抖动/额度问题"。

**root_cause**：调度器（launchd / systemd / cron）启动的进程**不继承登录 shell 的环境变量**。三次分别缺：① `HTTPS_PROXY`（本机走 Privoxy，无代理连不上）② `ANTHROPIC_BASE_URL/AUTH_TOKEN/MODEL`（由 `~/.bashrc` → `node-env.sh` 设置，systemd 不走这条链）③ `HTTP(S)_PROXY`（plist 只注入了 `PATH`）。

**更值得记的是我第一次的处置错误**：撞到 ① 时我只在**当次命令**里补了 `HTTPS_PROXY` 就过去了，**没有横向推广到调度器配置**，于是同一根因换个马甲又咬了两次。

**并且我给出过一个错误的根因**：③ 发生时我推断是"Mac 锁屏导致拿不到 keychain 凭据"，operator 质疑后实测推翻——`pmset -g log` 显示 02:51–07:00 全程 `Powerd - Prevent sleep while display is on` 断言持续存在且时长累积，**屏幕一直亮着、机器从未睡眠**。推断当结论是二次伤害。

**fix**：`724117356` — ① plist 补齐代理变量并 `plutil -lint` + 真实 launchd 环境隔离探针验证（返回「在线」，403 消失）② systemd unit 改用 `bash -lc 'source node-env.sh; exec ...'`，密钥不进 git ③ 新增 `bin/cortex-loop-tests/env-parity.sh` 机械门，**runtime 无关**：从 adapter 头部 `# cortex-loop:requires-env` 自声明取需求并集，与本机调度器配置比对，加新 runtime 只改 adapter ④ 接进 `scan_self_defects()`，退化时自动变成蜂群任务。

**never_again**：
- **任何"已验证"必须标注验证环境**：沙箱验证 ≠ 生产验证，交互式验证 ≠ 无人值守验证，两者不能互相替代
- **跨环境行为差异先对比 `env`，不要猜行为**——这次三个坑全是 env 差异，猜因果（如"锁屏"）浪费了一轮
- **修完一个环境的坑，立刻横向问"同类调度器还有几个"**——这正是三次现形的直接原因

---

## E011 · 假完成：short_test 复用扫描器退出码 + 验证器失败开放，两层同时失守

| 字段 | 内容 |
|------|------|
| **id** | E011 |
| **date** | 2026-07-29 |
| **status** | closed |
| **related_skill** | cortex-loop |

**symptom**：真机全自动闭环首次跑通时，`skill-reg-1`（"把 huashu-doubao-search 注册进 SKILLS-TAXONOMY"）被引擎标记 `status=done, gate=passed`，但独立重跑同一条 `short_test` 立刻证伪——`bash bin/verify-skill-integration.sh --check registry` 仍报 `未注册：huashu-doubao-search`，问题根本没修。

**root_cause**：两个缺陷叠加，任一个单独存在都不会漏。
1. `verify-skill-integration.sh` 这类扫描器的退出码只在 **FAIL** 时非零，**WARN 不影响退出码**。`discover_candidates` 把整个扫描器命令原样当 `short_test`——于是这类任务的机械门**永远通过**，不管有没有真的修，因为重跑扫描器本身就恒为 exit 0。
2. `ai_judge` 的独立验收在这次真机运行中也没拦住：验证器（`claude-sonnet-5`）当场遇到本地网关 `502 unknown provider` 报错，输出是一段错误信息（不含 `REJECT` 字样）。旧逻辑「不含 REJECT 就当 ACCEPT」——**验证器自己没跑起来，被当成"内容没问题"放行**，失败开放而非失败关闭。

**fix**：
- `discover_candidates` 的 `short_test` 从「复用扫描器命令」改成「针对具体那一条问题的否定判据」：`bash -c '! (<扫描器> 2>&1 | grep -qF "<具体命中项>")'`，重跑后精确判断这一条是否还在，不再看扫描器整体退出码
- `run_adapter` 捕获 adapter 真实退出码，非零时给输出加 `[ADAPTER_FAILED rc=N]` 前缀
- `ai_judge` 见到该前缀或空输出 → 直接 `REJECT`（"验证器未能正常运行，看不清就不算过，不是默认放行"），不再"没见 REJECT 字样就默认 ACCEPT"

**never_again**：
- **判据永远要问"这一条具体的事有没有变"，不能问"重跑一遍会不会报错"**——扫描器可以整体健康（exit 0）但你要修的那一条问题原封不动
- **验证器本身失败 ≠ 内容通过**。任何"看不懂/没跑起来/报错"都必须映射到拒绝，不能映射到默认值里刚好等于放行的那一支
- 这是本项目「静默降级」DNA 第 9 次现形（E001/E002/E003/第4次push/E005/E008/E009/本条），且是危害最大的一次——**它让假完成第一次真的写进了执行账本**，不是设计推演，是真机全自动闭环首跑就撞见

---

## E010 · 长跑进程绑在终端上 → 会话一崩全灭

| 字段 | 内容 |
|------|------|
| **id** | E010 |
| **date** | 2026-07-29 |
| **status** | closed |
| **related_skill** | cortex-loop |

**symptom**：会话崩溃的同一秒，`ollama pull` 死在 79%（2.0GB/2.5GB 白下）、三个正在跑的 sub-agent 全灭。已烧掉的 token 与带宽全部作废。

**root_cause**：这些进程是从会话里裸起的，**父进程死则子进程陪葬**。而 launchd / systemd 的定时心跳毫发无伤——**因为它们本来就不挂在终端上**。同一台机器上两类进程命运迥异，差别只在「有没有脱离终端」。

**fix**：`6ea6f12e2` 之后新增 `bin/cortex-loop-detach.sh` —— 一律 tmux 起、tee 落盘、幂等（同名不重复启动）、可 `--status` / `--wait`。实测重拉 ollama 时终端与它已解耦。

**never_again**：
- **任何可能超过 30 秒的命令一律进 tmux**，不做「这次应该很快」的赌博
- 自愈要分层，因为 tmux 自己也是单点：**终端死 → tmux 兜；tmux 死 → launchd/systemd 重拉；全死 → git 账本还在，下一拍从状态续**
- 真正救回这三路的不是 tmux，是 **SUBAGENT-PERSIST 边做边落盘**：三个 agent 的 `reports/_work/*.md` 分别留下 5.3–5.8KB 真内容，续跑时 `cat` 一下就接上了。**没落盘的工作等于没做过**

---

## E009 · CAS 拒绝与网络故障压成同一个返回值

| 字段 | 内容 |
|------|------|
| **id** | E009 |
| **date** | 2026-07-29 |
| **status** | closed |
| **related_skill** | cortex-loop |

**symptom**：纯网络故障被报成「同一瞬间有别的节点先推上去了 — CAS 生效」，于是 `tick` 静默跳过该线，日志看上去一切正常，运维会往「并发争抢」的错方向排查。

**root_cause**：`write_ref()` 把 push 的所有失败压成同一个 `False`。本机 GitHub 走 Privoxy，实测约每 6 次抖 1 次 `SSL_ERROR_SYSCALL`。

**fix**：`89fa34d9e` — 区分 `REJECTED`（输出含 non-fast-forward/rejected）与 `ERROR`；`acquire_lease` 遇 ERROR 明说「网络故障不是被抢，本节点此刻看不清蜂群，按 fencing 不动手」。

**never_again**：
- 分布式系统里「我被拒绝」和「我没连上」是两个完全不同的世界观，压成一个布尔值必然误导
- fencing 的正确姿势：**看不清就别动手**，而不是假设自己输了比赛

---

## E016 · 无时区回执被当 UTC → 26 条真实 lineage 全部判成“未来时间”

| field | value |
|---|---|
| **error_type** | evidence-timezone |
| **status** | closed |
| **related_skill** | cortex-loop |

**symptom**：origin 的 discovery/result/learning 三类源均为 `OK`，26 条任务已经结算，Dashboard 却显示 `S0 UNKNOWN / S1 UNKNOWN / receipt=0 / invalid=141`。

**root_cause**：Cortex v1 用本机墙钟写 `2026-07-30T02:45`，没有 offset；metrics 把 naive 时间强行当 UTC。上海 02:45 被解释为 UTC 02:45，相对真实 UTC 18:45 变成“未来 8 小时”，整批 discovery 被拒。

**fix**：
1. 兼容旧账：naive receipt 按本机时区解析，再统一转 UTC
2. 新账：`cortex-loop` 写 timezone-aware `%Y-%m-%dT%H:%M%z`
3. 跨节点 beat 保留 Git `%ci` 的 offset，不再截掉 `+0800`
4. 负测：真实本地无 offset 回执必须仍能形成 S1 canary

**never_again**：
- 分布式账本时间戳必须带 offset；“所有机器现在恰好同一时区”不是合同
- `source=OK` 与 `evidence=valid` 必须分开显示；否则会把量具 bug 误说成业务没跑
- Dashboard 的最大阻塞必须按阶段状态排序：S1 已过后，不能继续叫人“补 lineage”

**机械门**：`python3 bin/cortex-loop-tests/fixtures/negtest-dashboard-json.py`

---

## E017 · 有 cohort 被显示成“无样本”＋回执绑定被夸成 VERIFIED

| field | value |
|---|---|
| **error_type** | dashboard-evidence-overclaim |
| **status** | closed |
| **related_skill** | cortex-loop |

**symptom**：同一份 Dashboard 一边显示已有 frozen discoveries/full lineages，一边把 G1 写成
`UNMEASURED（无 discovery cohort）`；同时仅凭 40 位 `origin_commit` 和两份 receipt 字符串一致，
就输出 `world_verification=VERIFIED`。

**root_cause**：
1. 指标层把“滚动窗口未批准”编码成 `denominator=0`，展示层又把所有 0 分母解释成“没有 cohort”
2. 历史 `gate=noop` 在滚动窗截取前被全历史扫描，导致窗口外旧账永久毒死 G2
3. “回执字段绑定”“origin 分支可达”“现场重放验证命令”三个证据层被压成一个 VERIFIED

**fix**：
1. G1 无窗口时展示 frozen all-history baseline；只有 eligible cohort 真为空才 `UNMEASURED`
2. G2 窗口外 legacy gate 进入 `unclassified` 数据债；窗口内未知 gate 仍 fail-closed
3. artifact 必须绑定安全的仓库相对路径，并机械证明该路径在 origin 可达 commit 中确为 blob
4. Dashboard 改用 `receipt_binding=BOUND`、`origin_reachability=REACHABLE`、
   `verification_replay=NOT_REPLAYED`
5. invalid reasons 只给有界摘要，不在 JSON 两处重复整包

**never_again**：
- “有数据但合同未批准”与“没有数据”是两种状态
- 证据命名不得超过验证器实际做过的动作
- 历史数据债必须可见，但不得越窗改变当前 cohort 判决

**机械门**：`python3 bin/cortex-loop-tests/fixtures/negtest-dashboard-json.py`

---

## E018 · 蜂群模式下即兴工作绕过账本 — 白盒失明，且覆盖的只是少数

| 字段 | 内容 |
|------|------|
| **id** | E018 |
| **date** | 2026-07-30 |
| **status** | closed（原因已查清，修复见 T11） |
| **related_skill** | cortex-loop · hive · sub-agent-dispatch |

**symptom**：`_swarm/orchestrator-laptop.md` 画像 `executors: human-in-loop`、
`last_seen: 2026-07-29T15:37`（停在昨天下午）；`cortex-loop status` 显示
`cortex-immune executor=human blocked=1 pending=9`，无一条 `running`。但同一晚
该节点实际派发了 8+ 条 HIVE 线、20+ commit。逐条核对：8 条线里**只有 T2
对应账本里预先建好的任务，其余 7 条**（外部审计整改、体系接线、模型热切换、
廉价 adapter 接入…）**从未在账本出现过**——不是「忘了 claim」，是账本机制
本身只覆盖「提前建好的任务」，而当晚真实工作里即兴的占了大多数（7/8）。

**root_cause**：两层，浅层是深层的症状。
- **浅层**：`cmd_checkin()`（`bin/cortex-loop` 约 2363 行）把 orchestrator
  节点的 `executors` 字段**硬编码**为字符串 `"human-in-loop"`，不论本次会话
  实际用了什么工具（含 HIVE sub-agent）都不体现；HIVE 派发被实现成账本外
  的平行编排，`claim → submit → try-complete` 生命周期被整体绕过。
- **深层（operator 2026-07-30 拍板升级）**：蜂群缺一个**机器可判的成员资格
  判据**——当前有没有处于「蜂群模式」，全靠自觉。而多数真实工作是**现干
  现想**的即兴活，现有机制只对「先有任务卡」的活生效，即兴工作天然绕过。
  决策者（orchestrator）注册在案却不心跳不认领，元治理层对自己免检——
  这正是 [[steer-doctrine|STEER 律]]写明「决策者不豁免自己」但**写明不等于
  生效**的实证：规则在文档里，机制里没有。

**fix**：暂未修，契约见 `brain-network/directions/cortex-immune/TASKS.md` T11
（HIVE 执行器化 + orchestrator 节点归位 + 蜂群模式即兴入账）。
`cmd_checkin()` 硬编码字符串所在的 `bin/cortex-loop` 本次未改动——
该文件当晚由另一条线并行加 `select` 子命令，避免多线路撞同文件。

**never_again**：
- **蜂群模式下「是否入账」不能是自觉行为**，必须有机器判据 + 默认偏置；
  判不出处于 solo 还是 swarm 时，**默认按 swarm 处理**——漏记比误记危害
  更大（漏记 = 白盒永久失明；误记顶多多一条噪音记录，可事后订正）
- **覆盖「预建任务」的机制不等于覆盖「真实工作」**。即兴工作可能是大多数
  （本例 7/8），设计入账机制时要让**派发动作本身自动生成任务记录**，而不是
  「先建任务卡再干活」（规则一重，人会绕过）或「事后补记」（依赖记性，
  等价于不修）
- **计分不能只记成功**：对错都要进 HAAS，只记成功 = 制造刷分漏洞
  （呼应 E014 空转刷分——「全绿」不是健康的证据，可能是没在记账）
- **决策者不豁免自己**这条律要落到机械层才算数，写进文档不算——本条
  就是「写了但没生效」在同一个系统里第二次现形（第一次是 E014 的空转门
  上线前，规则同样先写后落）

---

## E019 · 文本补全冒充执行器：心跳在动，任务根本没执行

| 字段 | 内容 |
|------|------|
| **id** | E019 |
| **date** | 2026-07-31 |
| **status** | closed |
| **related_skill** | cortex-loop · bug-master |

**symptom**：Dashboard 持续有心跳，任务反复从 `running` 回到 `pending`，
artifact 永远缺失；每次失败还被 `advance_window_min=240` 推迟四小时。

**root_cause**：
1. `cheap.sh` 调的是 raw MiniMax/GLM completion，只能生成文本，没有 Read/Edit/Write/Bash。
2. adapter 非零或完成门失败仍走成功提交路径，失败被成功窗口隐藏。
3. 人工 tick 与 launchd 可重叠；父进程被杀后工具子进程会孤儿化。
4. Claude Code 默认加载插件/MCP，T18 实测拉起无关 doubao-search 并空等八分钟。
5. 执行 Agent 可直接改 TASKS/short_test；T22 实测越过唯一完成门自行写 `done`。

**fix**：
- `cheap` 改为 MiniMax-backed Claude Code 工具层；真实 Write+Read 冒烟通过。
- tick 单实例锁 + cheap worker PID 锁；失败走 15/30/60/120 分钟退避。
- 工具回执可被后续心跳恢复；legacy 文本回执标 `rc=96`，不进完成门。
- safe-mode + 空 MCP 配置 + 禁插件/斜杠技能 + 禁 Git 写操作。
- 执行前冻结任务合同与 short_test；越权修改机械还原并记 C1 违约。
- task-add/list/show/retry/run 原子化，禁止手拼任务表。

**mechanical_gate**：
`bash bin/cortex-loop-tests/cheap-tool-smoke.sh` ·
`python3 bin/cortex-loop-tests/fixtures/negtest-execution-control.py` ·
`bash bin/cortex-loop-tests/suite.sh`（49 PASS / 0 FAIL）。

**never_again**：执行能力必须由“世界发生可验证变化”证明，不能由模型自报或文字回执证明。
失败与成功必须使用不同的时间语义；无人值守执行器的插件面、Git 权限、完成权默认关闭。

---

## E020 · Repair 历史被指标当冲突，控制 ref 被当结果事件

| 字段 | 内容 |
|------|------|
| **id** | E020 |
| **date** | 2026-07-31 |
| **status** | closed |
| **related_skill** | cortex-loop |

**symptom**：Worker/Controller、suite 和 S1 canary 均在推进，但 live autonomy 的 G1
长期 UNKNOWN，G2 一启用滚动窗就被 malformed 记录毒死。

**root_cause**：

1. Repair Controller 对同一 frozen discovery 的失败→重试会产生多个 terminal attempt；
   G1 把所有不同 payload 直接判成 conflicting duplicate。
2. `result/<plan>/_settled` 是计划结算控制 ref，却被采集器当普通 result，因无
   `finished/gate` 令所有滚动窗 UNKNOWN。

**fix**：

- 同 discovery 的 attempt 按可读 `finished` 选择最新；严格同时间不同内容仍 UNKNOWN。
- result namespace 在采集入口排除 basename 以 `_` 开头的控制 ref。
- G1/G2 分别批准 7 天与 24 小时窗口，累计战绩继续独立展示。

**mechanical_gate**：
`negtest-g1-discovery-cohort.py` · `cortex-metrics.py --validate-contract` ·
`autonomy-acceptance.sh`。

**never_again**：重试是事件序列，不是重复数据；控制 ref 与业务事件必须在命名空间
采集入口分型，不能把“都在 result/ 下”压成同一种东西。

---

## E021 · 全局 tick 锁把一个长任务扩散成全队列冻结

| 字段 | 内容 |
|------|------|
| **symptom** | Dashboard 有心跳、有一个 running，但 task-add/resume/submit 全部 BUSY，待办不再认领 |
| **root_cause** | 同一把 `cortex-loop.tick.lock` 覆盖调度、25 分钟 LLM、网络、验收和 Git；为防旧快照覆盖而把所有不相关任务强制串行 |
| **fix** | 删除运行时全局 tick 锁；同任务 flock；账本微锁 + atomic replace；状态 `expected_status` CAS；adapter 继承 task lock；MiniMax 账号级 lease；Git tx 只保护本地 mutation |
| **mechanical_gate** | suite H23；Git V4 stale/live/index/deploy-outside-lock 矩阵；完整 suite |
| **never_again** | 锁按共享资源最小化：长任务不持全局锁，跨网络/模型/部署的临界区一律视为设计红旗 |
| **related_skill** | cortex-loop |

三横一纵扩查同时发现：task-add 先发布后 gate 的可见窗口、CC Switch JSON 无锁丢更新、
Git tx SIGKILL 永久残锁、worker 锁前生成快照、pre-commit 裸提交自造无 PID 锁，已一并修复。

---

## E022 · 控制面已分布式，Worker 却共写根 worktree

| 字段 | 内容 |
|------|------|
| **symptom** | 多 Agent 与 Cortex 不同任务能同时认领，却争同一 index/worktree；Git 锁缩短后仍会互相污染、结算排队，candidate 在任意远端分支可达还可能被误判 done |
| **root_cause** | ref 层已有 CAS/lease 分布式控制面，但 adapters 全部 `cd` 根仓；执行面、candidate 面、canonical 集成面被压成一次根树提交 |
| **fix** | 每 attempt 稀疏 linked worktree（共享 objects、独立 index）；不可变 candidate ref；低磁盘 blobless integrator；master 只做极短 lease-CAS；完成门只认 canonical master 上可机械证明的精确交付 |
| **mechanical_gate** | suite H26–H30：workspace 崩溃恢复、candidate 不可变发布、integration 双写 CAS、master landing、交付面统计 |
| **never_again** | “origin 可达”不等于“已交付”；“多 Worker”不等于“能并行写”。不同任务必须隔离 index，只有真实写集重叠和 canonical ref 更新可以串行 |
| **related_skill** | cortex-loop |

磁盘实测：完整对象库约 3.4G 但 Cortex 稀疏舱新增占用 6.4M；因此默认用共享 objects + bounds
稀疏物化，不复制完整 vault。调度目标是约束下最大化 landed throughput，而不是最大化表面 Worker 数。

---

## E023 · Dashboard Ctrl-C 经影子 pkill 批量终止 GUI

| 字段 | 内容 |
|------|------|
| **symptom** | 退出 Dashboard 后 Finder、Terminal、iTerm2、ChatGPT/Codex、浏览器等同时崩溃并出现黑屏 |
| **root_cause** | EXIT handler 调用 PATH 里的 `pkill -P`；实际命中旧 x86 `proctools/0.4pre1`，在 macOS 26.3 忽略父 PID 过滤并向全系统可访问进程发 SIGTERM |
| **fix** | watch 改为单前台同步采集、零后台 collector/进程树追杀；备用屏只负责原位显示且退出恢复；隔离影子 pgrep/pkill；所有运行脚本显式 `/usr/bin/pgrep`，终止只认确切 PID |
| **mechanical_gate** | suite H33/H34；恶意关键字静态门；PTY SIGINT 无残留进程组；TTY echo、备用屏、光标逐项恢复；watch 焦点视图 ≤34 行 |
| **never_again** | 进程生命周期必须由创建者持有确切 handle/PID；PATH 是依赖注入面，安全关键工具不能按名字盲信 |
| **related_skill** | cortex-loop · bug-master |

系统日志把两次批量终止明确归因到 `pkill[27500]`（63 个）与 `pkill[48487]`（42 个）。
WindowServer 高 CPU、Crashpad 重启风暴是次生污染；没有 OOM/Jetsam 证据。

---

## E024 · V4 tree 回滚丢 sparse index 元数据

| 字段 | 内容 |
|------|------|
| **symptom** | attempt 提交失败前只有 1 个脏文件，失败后 Dashboard 报异常，`git status` 显示约 2.9 万个删除 |
| **root_cause** | `write-tree/read-tree` 只保存树内容，不保存 index 的 `skip-worktree` 位；稀疏工作区回滚后把未物化文件误视为删除 |
| **fix** | V4 改为每 worktree 原始 index 字节快照与原子恢复；旧舱产物先归档，再 `sparse-checkout reapply` 后 broker release |
| **mechanical_gate** | `test-commit-v4.sh` 强制 hook failure 前后 `git ls-files -v` 完全一致 |
| **never_again** | tree 相同不等于 index 状态相同；任何 index 回滚必须保留扩展位与 sparse 语义 |
| **related_skill** | git-management · cortex-loop |

---

## E025 · squash/replay 后源提交不可达导致永久 settling

| 字段 | 内容 |
|------|------|
| **symptom** | artifact 与 check 已进入 canonical master，短测全绿，但任务持续显示“等待 git 传播” |
| **root_cause** | 集成器把多个 source commit 重放成一个 canonical commit；旧完成门只用 source OID 祖先关系证明落地，把提交身份与交付内容错误绑定 |
| **fix** | 统一结算 helper 先验证本地路径存在、非空、tracked、clean 且绑定 source commit，再逐一比较 `source_commit:path` 与 `canonical_tip:path` 的 blob OID；全部一致即 `content-equivalent` landed |
| **mechanical_gate** | suite H35：无祖先 squash/replay 正例、canonical blob 不同、本地脏改、check 未落地、只读零副作用；完成门与 `task-show --settlement` 共用同一 helper |
| **never_again** | 提交 OID 是运输身份，不是内容真相；允许 squash/replay 的交付链必须验证 canonical 上完整写集，而不是只验 source commit ancestry |
| **related_skill** | cortex-loop · git-management |

---

## E026 · 分叉 candidate 缺少 canonical 精确合成入口

| 字段 | 内容 |
|------|------|
| **symptom** | 本地语义提交已完成，但它的父链落后并分叉；直接交 integrator 会冲突，只剩手搓临时 index 或污染共享 worktree 两条路 |
| **root_cause** | candidate 工具只有 validate/publish/inspect，没有“从 source commit 向最新 canonical base 覆盖精确文件”的 compose 原语 |
| **fix** | `cortex-candidate.sh compose --source OID --base OID --allow FILE...` 用私有临时 index 生成 canonical 单父 candidate；只接收精确文件，缺路径或目录 fail-closed |
| **mechanical_gate** | suite H30：分叉 source 合成、canonical 未声明文件保留、缺路径拒绝、HEAD 与共享 index 前后不变 |
| **never_again** | 分叉交付必须有正式 rebase-by-write-set 原语；禁止把临时 plumbing 手艺当运行流程，更禁止为避冲突直接 merge/reset/stash 共享仓 |
| **related_skill** | cortex-loop · git-management |

---

## E027 · 工具存在不等于生产 producer 已接线

| 字段 | 内容 |
|------|------|
| **id** | E027 |
| **symptom** | 越权、独立验证反证和预算超限的 `record/status` 工具与单元测试都存在，任务被记为 done；真实运行数日后生产 JSONL 仍不存在，Dashboard 只能显示 UNKNOWN |
| **root_cause** | 弱成功合同只验证“可以手工写一条事件”，没有从真实 bounds/integrator/完成门/daily cap/quota 判定点触发 producer；把 capability existence 错当 production wiring |
| **fix** | 三源统一原子 `init/status/record`；在真实判定点窄语义接线；确定性 event-id 幂等；测试重定向状态目录；H36 覆盖正样本、误报边界、并发与 HOME 隔离 |
| **never_again** | 凡声称“事件源已接通”，验收必须从生产入口制造业务事件并读回 canonical source；直接调用 recorder 只证明工具能力，不证明机制接线 |
| **related_skill** | cortex-loop · cortex-immune |

---

## E028 · schema 形状合法不等于语义有效日历值

| 字段 | 内容 |
|------|------|
| **id** | E028 |
| **symptom** | incident JSON 拥有字符串 `timestamp` 且匹配表面格式，但不存在的月份、日期或时间仍可能被当成有效事件，健康与信任统计被污染 |
| **root_cause** | validator 只检查字段类型/正则形状，没有把 UTC 时间解析为真实日历值；结构合同停在 syntax，没有进入 semantic validity |
| **fix** | 三类 incident validator 使用严格 UTC 日历解析；坏日期返回 UNKNOWN，`validate` 非零；H36 对不存在日历值做破坏性负测 |
| **never_again** | 日期、金额、枚举、ID、路径等字段必须验证业务语义，不得以“类型正确/正则匹配”代替值域有效；每个语义门至少一条形状合法但值无效的负测 |
| **related_skill** | cortex-loop · evolve-ecosystem |

---

## E029 · 逻辑会话隔离被错误实现成完整 worktree 复制

| 字段 | 内容 |
|------|------|
| **id** | E029 |
| **date** | 2026-08-16 |
| **status** | closed |
| **symptom** | 为 ROSACE/ROSEUM 建立知识交接会话时，沿用 Git 项目默认值创建完整 worktree；即使磁盘空间足够，也会复制整棵 OB1、制造重复入口，并让知识落盘分散到错误的 checkout。 |
| **root_cause** | 把 Agent/Topic/Session 的逻辑隔离误当成文件系统 worktree 隔离；没有在 Hatch 前区分知识交接、共享数据任务、并发代码写入和高风险实验。 |
| **fix** | 共享 OB1 的 Codex 会话统一使用 `target.environment.type=local`，直接共用 `${CORTEX_WORKSPACE_ROOT}`；需要文件隔离且能列出写集时才调用 `bin/cortex-workspace.sh` 的 `--allow` 稀疏工作区；只有写集未知且确有并发冲突时才允许原生完整 worktree。错题、规则、报告和记忆一律写回主真相源。 |
| **mechanical_gate** | 创建前记录 `target.environment`；共享 OB1 若不是 `local` 必须拒绝；创建后核对会话 `cwd` 为主仓，并对比 `git worktree list`，数量和路径不得因知识交接增加。磁盘余量不是放宽条件。 |
| **never_again** | **Session ≠ worktree。** 知识交接、品牌规划、只读审计、数据读取和跨 Runtime 迁移默认不创建 worktree；“空间够”不能成为整包复制理由。 |
| **related_skill** | cortex-loop · session-resume · agent-runtime-knowledge-portability |

---

## 压轴教训 · 静默降级比报错更危险

> **E001 / E002 / E003 是同一个 DNA。**

| 错题 | 静默降级成了什么 | 表面现象 |
|------|-----------------|---------|
| E001 | 说明表被当数据表 | 读出一堆垃圾行，但**不报错** |
| E002 | 表头不匹配 → 整张表跳过 | 返回 0 行，**退出码 0** |
| E003 | ref 层读空 → 退回文件快照 | `beat=True` 一切正常，**就是少一个节点** |

三次全部是：**功能坏了，但程序声称自己好着呢。** 表现形式是「结果不对」而不是「命令失败」，所以：
- 退出码骗人 → 上层 `if code == 0` 白判
- 日志骗人 → 人看日志以为在跑
- 越自动化的系统，静默降级的破坏力越大——因为**没有人在旁边看**

**规定动作（写进 cortex-loop 的所有新代码）**：

1. **任何 fallback / 跳过 / 退回分支，必须 `print(..., file=sys.stderr)` 出声**（E003 的修复就是加了这一行）
2. **「读到 0 条」必须能和「本来就 0 条」区分**，不能共用一个返回值
3. **拿不到就返回 `None`，绝不返回空串**——空串会被静默拼进命令（E004 差点删远端 ref）
4. **健康/自检类代码禁止 `except: pass`**——`run()` 的 `except` 分支显式返回 `(1, str(exc))`，注释写死「自检不能因异常静默变绿」

---

## 错题 → Layer 0 律（哪条坑生出了哪条律）

> 2026-07-29 新增的六条律**不是先有律再有实现**，是这些错题反复现形后被逼出来的。
> 反向读法：撞到某类症状 → 先看它对应的律有没有机械后盾能挡住下一次。

| 错题 | 生出/印证的律 | 机械后盾 |
|------|--------------|---------|
| E009 CAS 拒绝与网络故障压成同一返回值 · E013 单日五处坍缩 · E015 第四态 `moot` 无落脚点 | [[dimensional-expansion-doctrine\|DIMENSIONAL]]（= SKILL T7） | `bin/cortex-loop-tests/dimensional-collapse-scan.sh` |
| E010 长跑进程绑终端 · 四次手搓量具失灵（`grep -E` 或运算 / 管道吞退出码 / `ls` 多路径） | [[atomize-tools-doctrine\|ATOMIZE]] | `bin/cortex-probe.sh`（10 探针三态）· `cortex-loop-detach.sh` |
| E011 假完成：short_test 复用扫描器退出码 + 验证器失败开放 | [[pulse-doctrine\|PULSE]] L 问「过机械门不是自报」（= T3/T4） | `bin/cortex-pulse.sh` · `autonomy-acceptance.sh` |
| E012 交互式 shell 能跑 ≠ 无人值守能跑 | [[pulse-doctrine\|PULSE]] P 问「系统还在跑吗」（= T2） | `bin/cortex-loop-tests/env-parity.sh` |
| E014 空转刷分：判据已满足仍计 passed | [[ground-first-doctrine\|GROUND]] U 步「查验强度随信任」（= T9） | 空转门 + `moot` ref + `inspection_mode()` |
| E005 把「投递失败」当「执行失败」· E007 「日志连续」被误读成「一直在跑」 | [[glassbox-doctrine\|GLASSBOX]] 人机同读一份真相 | `bin/cortex-dashboard.sh --json` · `bin/cortex-trace.sh` |
| 「我不在账本里」= 元治理层默认豁免自己 | [[steer-doctrine\|STEER]] 决策者也在账本里 | `orchestrator-*` 节点 + `fault` / `credit` |

六律成链与全表见 [[cortex-loop/SKILL|SKILL.md]] §关联 Layer 0 律 · 铁律代价全文见 [[cortex-loop/references/tenets|references/tenets.md]]。

---

## Nav

| 文档 | 关系 |
|------|------|
| [[cortex-loop/SKILL\|SKILL.md]] | 主文档 |
| [[cortex-loop/JOURNAL\|JOURNAL.md]] | 建设日记（这些错题的发生顺序） |
| [[cortex-loop/EXPECTATIONS\|EXPECTATIONS.md]] | 还没做到的（含由本文件 never_again 提炼的欠账） |
| [[cortex-loop-intent]] | 心跳总纲 |
| [[cortex-loop-cron-error-triage]] | E005 的逐条证据来源 |
| [[recipe-and-errors-contract]] | 本文件字段合同 |

---

*建立: 2026-07-28 | E001–E007 全部为 2026-07-28 当日实证，每条带 commit sha*

---

<!-- cortex:map-backlink d-8ae6ef1fbe379db0a350896a -->
关联地图：[[skills/cortex-loop/MAP|Cortex Loop 全景地图]]
## E030 · 固定 4+3+2 被并发槽位覆盖，Codex 子席越界

**症状**：GLASSBOX 没有逐席展示 provider/model/provenance，编排器把空闲并发槽位误当成可新增 Codex worker，导致 Codex quota 被错误消耗。

**根因**：运行时缺少固定编组 admission gate；主线程、Codex child cap 和 inherited model provenance 没有在派发前硬校验。

**修复**：`formation-boundary.test.mjs` 先于任何派发运行；`codex.slot_cap=1`；所有新 Codex child 显式 `gpt-5.6-luna`；旧继承席位模型未知则 UNKNOWN；不满足即 BLOCKED。

**never_again**：固定 4+3+2 roster 必须在派发前机械校验；主线程不计执行席；Codex child 只能 1 席且必须显式 Luna；GLASSBOX 必须逐席展示 provider/model/provenance/cooldown；Eval 失败即 BLOCKED。

**related_skill**：cortex-loop · hive-orchestrator · codex-master

## E031 · 清理归一的快照漂移与仓库边界误判

**症状**：同一轮清理先后出现 135、140、142 个 worktree；批次审计把交叉视角当成互斥分工，并把 `${CORTEX_WORKSPACE_ROOT}/` 下实际属于 Cortex Harness 的 worktree 与 OB1 worktree 混在一起。

**根因**：并行执行会新增/回收 worktree，旧数字被继续当作当前分母；处置清单缺少 Git common-dir、remote、是否注册、快照时间和唯一 owner 字段。

**修复**：Cortex 清理分两层：先固定 exact 快照并建立逐项 manifest，再按 manifest 生成互斥执行批次。归属只认 `git worktree list --porcelain` + `git rev-parse --git-common-dir` + remote；OB1 common-dir 的项永不触碰。删除必须在同一项的最新复读中同时满足 clean、无 lock、无活动进程、无 lease、非 canonical、无未迁移价值；否则保留为 `ARCHIVE_REVIEW`。

**never_again**：不把旧快照数字当当前事实；不以路径名判断仓库；不让交叉审计 worker 直接执行删除；不把 `MIGRATE` 意向当成已迁移；不在迁移冲突时强行恢复已从 canonical tree 删除的运行时。

**补充硬门**：执行批次开始前必须重新读取 registry、HEAD、dirty/lock、活动进程和 lease；若 worktree 数或 canonical HEAD 发生变化，旧处置清单立即失效，先生成新 snapshot，再继续。

## E033 · clean 不等于可删除

**症状**：把 `git status` 干净的 worktree 当成无价值副本，忽略其相对 canonical 的独有代码、测试、分支恢复路径或尚未收纳的集成文件。

**根因**：把 filesystem cleanliness、代码价值和可恢复性压成一个布尔值；同时用错误的基线解释大量历史删除差异。

**硬修**：clean 只允许进入价值复核；必须分别核对 `canonical...HEAD` 的真实文件差异、是否仅 probe/evidence、是否有独有代码/测试、commit 是否仍被 ref 保留，以及当前 canonical 是否已有后续实现。只有独有价值已迁移或明确无价值且可恢复时，才允许归档 worktree；dirty、locked、active 或未决 lease 一律 HOLD。

**never_again**：不以 clean、旧日期、目录名或“已完成”文字单独触发删除。

## E034 · 清理工作树与丢弃代码对象必须分离

**症状**：为了节省磁盘直接删除旧 worktree，导致仍需复核的 commit 无恢复路径；或反过来因为害怕丢对象而永不清理目录。

**硬修**：先证明 canonical 已包含后续实现，再即时复读 clean、lock、active process、lease 和 branch/ref；写入 archive ref 后只移除冗余 worktree，默认保留原 branch/ref，最后独立确认 registry 不再登记目标路径。分支删除必须另有明确证据和授权。

**never_again**：不把“移除 worktree”与“删除分支/丢弃 commit”混成一个动作。

**补充样例**：probe-only detached tree 可以在保留 archive ref 后移除；代码/测试树仍须进入价值与可达性复核，不能因同一目录前缀而批量删除。

## E032 · worktree 登记与实际 Git common-dir 分离

**症状**：canonical registry 仍列出一个目录，但该目录的 `.git` 已指向另一套临时仓库；直接执行 canonical `git worktree remove` 被拒绝。

**根因**：把 registry 路径误当成所有权证明，没有在破坏性处置前复读 common-dir、remote 和 owner-side worktree 元数据。

**硬修**：validation failure 立即停项；先判断目标是否属于另一仓库。跨仓库由 owner 处理；若只是失效登记，单独 prune；目录明确无价值且 clean/inactive 时才用可恢复 Trash。远端分支保留，canonical registry 重新复核。

**never_again**：不对跨 common-dir 目标重试硬删，不把孤立目录当 canonical 代码，不把一次成功 remove 推广为全量清理完成。

## E035 · 第二轮复核没有原子化、可复跑的快照门

**症状**：第一轮经验已写入文档，但第二轮仍依赖人工重新拼接路径、计数和处置清单；并行 worker 改变 registry 后，旧清单继续被当作当前状态。

**根因**：缺少统一的 read-only snapshot tool，把 canonical HEAD、Git common-dir/remote、worktree 状态、进程、lease/ref、精确差异和唯一分类一次性绑定；文档是规则，不能替代执行门。

**硬修**：以 `snapshot_id + canonical_head` 为输入，原子工具即时读取 registry，输出稳定 JSON manifest 和每项唯一 `disposition`。clean/dirty/locked/active/value/reachability 分轴记录；只要 HEAD 或 registry 漂移就返回 `STALE_SNAPSHOT`。工具不能删除、prune、迁移或把分类升级成授权。

**验收**：负例覆盖 stale snapshot、dirty、locked、unknown owner/runtime、fsmonitor 排除、OB1 boundary；同一快照重复运行保持字段与分类稳定；输出能直接供下一轮 worker 和独立 Guardian 复用。

**never_again**：第二轮不复制第一轮文字清单；先跑原子快照工具，再按互斥 scope 复核；没有 machine manifest 就不进入处置。

---

## E023 · 只写规则/报告，不做实际动作（2026-09-06）

**症状**：纠错规则、计划或报告写得完整，但没有继续执行 Gate A、contract 核验、DeepSeek 三席实证和独立 read-back，却把文档完成说成任务完成。

**根因**：把证据/报告层当成执行层，把 plan、dry-run、ACK 或模型自报当成真实动作和结算证据。

**硬修**：实际完成必须绑定目标动作、范围、独立验证和 read-back；没有动作只能 `PLAN_ONLY`/`REPORT_ONLY`，外部闸缺失只能 `BLOCKED`。失败保留首阻塞、owner、repair/replay 下一步。

**never_again**：命名误解/ASR 复发走 NameGuard 与 codex-master #006；实际不执行走 Agent Anti-Bureaucracy 与 codex-master #007；两类根因分别诊断、分别验收，不能用一份长报告混过去。
