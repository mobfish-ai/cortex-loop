[English](README.md) | 简体中文

# cortex-loop

cortex-loop 是蜂群节点的心跳引擎。它维护 git 账本、时钟，以及租约 / 蜂群 / tick 协调，在无人值守时把已声明的工作向前推进。

账本是真相源（`CLOCK.md` 管调度，`TASKS.md` 管工作）。心跳（`tick`、`health`、`reconcile`）是普通代码，不调用模型。`bin/cortex-loop-adapters/` 下的 adapter 是可替换的肌肉。只有 `try-complete` 可以写 `status=done`，而且必须在产出物、短测试和传播检查都通过之后。模型可以提议工作或否决工作，不能批准完成。

## 这不是什么

本仓库不是 [cortex-harness-open](https://github.com/mobfish-ai/cortex-harness-open) 里的可插拔 Block。

cortex-harness-open 是协议和参考工具。那里的 Block 有自己的入口、测试和公开合同。`discovery-chain-index` 是那个项目里的 Block。本目录树是心跳引擎：账本、时钟、租约、蜂群和 tick。它留在这个仓库里。

`bin/cortex-loop harness-run` 可以在本机检出 harness 的 agent-runtime（`scripts/cortex-local-mvp.mjs`）时驱动它。那只检查一条接线路径。它不把本引擎变成 Block，也不能代替 `tick`。

## 布局

| 路径 | 作用 |
| --- | --- |
| `bin/cortex-loop` | 引擎。Python 3，无需安装包。 |
| `bin/cortex-loop-adapters/` | 执行器。凭据只来自环境变量。 |
| `bin/cortex-loop-*.sh` 与 `bin/cortex-loop-*.py` | 随本切片发布的 doctor、detach、MCP、期待清单和清理辅助脚本。 |
| `bin/cortex-loop-tests/` | 测试套件与夹具。 |
| `skills/cortex-loop/` | 操作者技能：意图、错题、期待、日记和命令参考。 |

引擎从包含 `bin/cortex-loop` 的目录读取账本：

```text
brain-network/directions/CLOCK.md
brain-network/directions/<line>/TASKS.md
```

本次导出不含私有账本。没有 `CLOCK.md` 时，`tick` 打印降级说明并退出 0。它不会编造工作。

## 依赖

- Python 3
- git
- 可选 Node.js 24（`>=24.0.0 <25`）和 pnpm，仅 adapter 或 `harness-run` 需要

## 快速开始

在仓库根目录：

```sh
python3 bin/cortex-loop tick
python3 bin/cortex-loop health
python3 bin/cortex-loop swarm
bash bin/cortex-loop-tests/suite.sh
```

不带 `--auto` 的 `tick` 只报告到期项。`--auto` 会推进工作，需要真实账本和执行器。不要对空目录树传 `--auto`。

`health` 检查驱动。退出码 0 表示阻断项为绿。缺失的外部 cron 报为 unknown。它不会假装健康，也不会挡住心跳。

`swarm` 打印本节点画像以及还能看见谁。它在 `brain-network/directions/_swarm/` 写下本地画像，并写本地 git ref `refs/swarm/<swarm>/beat/<node>`。那是运行时状态，不是源码。不想用主机名当节点 id 时设置 `CORTEX_NODE`。

引擎退出码：`0` 正常，`1` 红灯或失败，`2` 用法错误。

测试套件会建一份临时账本，把引擎符号链接进去，并检查完成门、账本读取和 ref 层蜂群行为。它不调用模型。仍依赖私有目录树的用例见 [测试](#测试)。

## 环境变量

新检出真正需要的两个旋钮是工作区根目录和 Node 选择。

| 变量 | 作用 |
| --- | --- |
| `CORTEX_WORKSPACE_ROOT` | attempt、candidate、集成回执状态目录，以及空闲磁盘准入检查。在任何会准入 worker 的命令之前把它设为工作区根。未设置时，引擎保留未展开的占位符 `${CORTEX_WORKSPACE_ROOT}`，不会猜测家目录。 |
| `CORTEX_WORKSPACE_MIN_FREE_KB` | 该准入检查的空闲空间下限。默认 `1048576`（1 GiB）。 |
| `CORTEX_NODE` | 稳定的蜂群节点 id。覆盖主机名检测。 |
| `CORTEX_NODE_ALIASES` | 可选的 `substring=id` 列表，按主机名匹配。用来得到稳定昵称。源码不附带机器名。 |
| `CORTEX_SWARM` | 蜂群名。覆盖 `CLOCK.md` 里的 `swarm:`。默认 `cortex`。 |
| `CORTEX_HARNESS_DIR` | `harness-run` 使用的 harness 检出。默认 `~/cortex-harness`。指向 cortex-harness-open 的本地克隆。 |
| `CORTEX_MINIMAX_CN_NODES` | 逗号分隔的节点 id。这些节点先试 MiniMax 国内供应商，再试国际站。 |
| `CORTEX_MINIMAX_PROVIDERS` | 完全覆盖 MiniMax 供应商顺序。 |
| `CORTEX_LAUNCHD_LABEL` | launchd 标签。默认 `com.cortex.loop`。 |
| `CORTEX_REPORT_OWNER` | 写入 `reports/` 下报告的 owner 字段。默认 `operator`。 |
| `CORTEX_HARNESS_NODE_BIN` | `harness-run` 的 Node 二进制。未设置时，引擎选择最高的 `~/.nvm/versions/node/v24.*`。缺少 Node 24 时报 `node_v24_missing`，不会悄悄换成更旧的 Node。 |
| `CORTEX_NODE24_BIN` | 需要 Node 24 的 adapter（`claude`、原生 ACP）所用的二进制。`CORTEX_NODE24_PREFIX` 是同一选择的前缀形式（`$CORTEX_NODE24_PREFIX/bin/node`）。 |
| `CORTEX_PNPM_BIN` / `CORTEX_PNPM117_BIN` | 这些 adapter 使用的 pnpm 二进制。 |
| `OC_ADAPTERS_DIR` | adapter 目录。默认 `bin/cortex-loop-adapters`。 |
| `CORTEX_LOOP_LOG` | 引擎日志路径。默认 `/tmp/spotlight/cortex-loop.log`。 |
| `CORTEX_LOOP_ENGINE` | 套件调用的引擎二进制。默认 `bin/cortex-loop`。 |

供应商 API key 从进程环境或本地 OpenClaw 配置读取（`OPENCLAW_JSON_PATH`，默认 `~/.openclaw/openclaw.json`）。本仓库不含密钥。

## 测试

```sh
bash scripts/public-hygiene.sh
python3 scripts/cjk-source-gate.py
bash bin/cortex-loop-tests/suite.sh
```

在本目录树上，套件结果为 **45 PASS、0 FAIL、25 SKIP**，退出码 0。它不调用模型。它为完成门用例建立临时账本。SKIP 是本仓库没有的私有配套工具，外加信息性的 H03（维度坍缩扫描）。

这里会跑的内容：

- 完成门：缺少产出物、空产出物、短测试报红，以及没有产出路径或短测试的任务都保持 pending。全绿样本变成 `done`。
- 账本读取、本地蜂群 ref 读取、fit-score 通配、GitHub 延迟分类、beat ref 时间戳，以及 ref 写入防护。
- 针对 `origin` 的租约 CAS，只用 `refs/swarm/test-*`，结束后删除。`origin` 不可达时该用例跳过。
- 调度资格：`CLOCK.owner` 是亲和提示。有新鲜心跳的节点可以竞争短租约。`takeover_ready` 仍要等到静默上限的两倍。
- 规范落地：`worktree-content-equivalent` 可以在 `landed_oid` 已是规范 tip 时报告空的 `candidate_oid`。
- 不加载第二套工具的引擎内检查：扫描器宕机、传播、六定律、价值定律、验收员裁决与范围、计划复用、运行回执、发现/学习血缘、超时进程组、并发执行、ref 三态、失败冷却、资产健康，以及公开的 launchd/systemd 示例。

`CORTEX_HARNESS_DIR` 不存在或缺少 Node 24 时，`bash bin/cortex-loop-tests/harness-run-smoke.sh` 以 SKIP 退出 0。

GitHub Actions（`.github/workflows/test.yml`）在 push 和 pull request 上运行卫生门、CJK 源码门和套件。CJK 门会在 `*.zh-CN.md` 和 `bin/cortex-loop-tests/fixtures/` 之外出现表意文字或全角标点时失败。

### 跳过 — 本切片没有私有配套

配套文件不存在时，这些用例跳过，退出码仍为 0：

| 用例 | 配套 |
| --- | --- |
| E13, E14 | `bin/knowledge-contract-gate.py` |
| H09, H11, H33 | `bin/cortex-dashboard.sh` |
| H15, H16, H17, H18 | `bin/cortex-metrics.py` |
| H19 | `bin/cortex-s2-scm-shadow.py` |
| H22, H26, H29, H31 | `bin/cortex-workspace.sh` |
| H27 | `bin/cortex-integrator.sh` |
| H30 | `bin/cortex-candidate.sh` |
| H32 | `bin/git-worktree-doctor.py` |
| H34 | `bin/verify-process-tool-safety.py` |
| H36 | `bin/cortex-authorization-incident.sh` |
| H37, H38 | `bin/control-plane-cockpit.py` |
| H39, H40 | `bin/_cortex_acp.py` |
| H41 | `bin/git-commit-preflight.py` |

私有 unit 文件不在时，H10 读取 `examples/systemd/`。H20 读取 `examples/launchd/com.cortex.loop.plist`。H12 在仓库外建立临时 vendor 符号链接，并在结束后删除。

`bin/cortex-loop-tests/fixtures/negtest-execution-control.py` 里的 negtest bearer `sk-supersecretvalue` 是故意放的假密钥，不是凭据。

## 许可证

Apache License 2.0，含专利授权。Copyright 2026 mobfish-ai。见 [LICENSE](LICENSE) 与 [NOTICE](NOTICE)。
