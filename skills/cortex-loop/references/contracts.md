# cortex-loop 合同体系（四份文件合同 + 七个 ref 命名空间）

> **何时该读**：要改 `CLOCK.md` / `INTENT.md` / `TASKS.md` / 节点画像的字段，
> 要加一个新的 ref 命名空间，或 `knowledge-contract-gate.py` 报字段缺失时。
> **注册处**：[[knowledge-contract-registry]] §4.12 / §4.12a
> **上级**：[[cortex-loop/SKILL|SKILL.md]]

---

## 四份文件合同

| 合同 | 路径 | 层 |
|------|------|----|
| `loop_clock` | `brain-network/directions/CLOCK.md` | L2 调度真相 |
| `loop_node` | `brain-network/directions/_swarm/<node>.md` | 蜂群节点画像 |
| `loop_intent` | `brain-network/directions/<line>/INTENT.md` | L0 意图（含 `CHARTER-SWARM.md` / `INTENT-P2.md` 阶段化变体） |
| `loop_tasks` | `brain-network/directions/<line>/TASKS.md` | L1 执行真相 |

**共享核对齐**（registry §3）：`id / status / created / updated / claim / related / success_criteria / out_of_scope / short_test` 全部同名同义复用，未自创别名。

**Agent Code Gauntlet 默认门**（2026-08-02）：所有代码实现 / 多文件改动 / 高风险执行任务，合同必须先于执行写清 `success_criteria` + `short_test` + `out_of_scope`。主线程只做编排与 V·Verify；执行交给 HIVE/sub-agent/worker。小改、纯查询、低风险机械命令可主线程直做。

### 字段硬规矩（违反即半合同）

- 单元格禁止出现 `|`；`short_test` 一律写脚本路径，不写管道命令
- `success_criteria`（正）与 `failure_modes`（负）**都不能空**——缺一角 = 半合同（KE.3）
- `artifact_paths` 空 或 `short_test` 空 → `try-complete` **直接拒绝** `done`（不是警告，是拒绝）
- 代码任务的 `short_test` 必须指向可跑本地门（unit/脚本；能则 coverage/mutation/复杂度），不得写“人工看看”
- 生产库 / 钱 / 权限 / 账务任务即使 `short_test` 绿，也只能停在人工闸前，等 operator 显式确认
- `status=done` 必须有 `evidence`
- 占位符 `-` 是**合法值不是路径**（T6）：`fit_score` / `covenant_check` / 三道机械门都必须显式排除它

### 合同门校验命令

```bash
python3 bin/knowledge-contract-gate.py check-path brain-network/directions/CLOCK.md --strict
python3 bin/knowledge-contract-gate.py check-path brain-network/directions/loop-ops/TASKS.md --strict
python3 bin/knowledge-contract-gate.py check-path skills/cortex-loop/SKILL.md
```

---

## 七个 ref 命名空间（无文件合同 · 前缀 `refs/swarm/<swarm>/`）

> 为什么不走文件：多节点实时协调**必须在工作区不可用时仍然工作**。
> 全程 git plumbing（`hash-object` / `mktree` / `commit-tree` / `push <sha>:<ref>`），
> 不 checkout、不碰工作区 —— 脏树、冲突、卡死的 auto-sync 都影响不到它。

| 命名空间 | 用途 | 谁写 |
|----------|------|------|
| `beat/<node>` | 心跳 / 节点画像（= `loop_node` 同字段） | 只有 `<node>` 自己 |
| `lease/<line>` | 该线的执行租约 `holder · expires · since · task` | 抢到 CAS 的那个节点 |
| `plan/<id>` | 不可变计划（任何节点都能发） | 发布者 |
| `claim/<task>` | 认领占坑（CAS 抢） | 抢到的节点 |
| `result/<task>` | 执行结果（进 HAAS 功过账） | 认领者 |
| `moot/<task>` | **第四态**：判据本来就满足，既无功也无过但**是终态** | 判定空转的节点 |
| `incident/<id>` | C3 违约记录（`STOP→REPORT→WAIT→RECORD` 的 RECORD） | 违约方自己 / 编排者 |

**为什么 `moot` 必须独立而不塞进 `result`**：塞进 `result` 会污染 HAAS 与过门率 ——
空转既不该加分也不该扣分（T9）。独立命名空间让「没活可干」**被记住、被跳过，却不进任何功劳账**。
详见 [[cortex-loop/ERRORS|E015]]。

**心跳为什么不会冲突**：每个节点只写自己那条 ref，parent 挂**自己上一拍**，永远 fast-forward。
**结构上不可能撞**，不是靠约定不撞。

> **读 ref 的三态债**：`read_ref` / `list_refs` 目前把「读到空」等同「没有」，
> 是 [[dimensional-expansion-doctrine|DIMENSIONAL 律]] 母题的第 5 处、也是最底层的一处
> （被调 20 次，claim / plan / result / lease 全经过它）。见 [[cortex-loop/EXPECTATIONS|EXPECTATIONS]] D3。

---

## Nav

[[cortex-loop/SKILL|SKILL.md]] · [[cortex-loop/references/commands|commands]] · [[cortex-loop/references/architecture|architecture]] · [[cortex-loop/references/swarm|swarm]] · [[cortex-loop/references/operations|operations]] · [[knowledge-contract-registry]]

---

<!-- cortex:map-backlink d-1ce35905c560953da7787eff -->
关联地图：[[skills/cortex-loop/MAP|Cortex Loop 全景地图]]
