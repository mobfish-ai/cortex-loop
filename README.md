English | [简体中文](README.zh-CN.md)

# cortex-loop

cortex-loop is the swarm-node heartbeat engine. It keeps a git ledger, a clock, and the lease / swarm / tick coordination that moves declared work forward when nobody is watching.

The ledger is the source of truth (`CLOCK.md` for the schedule, `TASKS.md` for the work). The heartbeat (`tick`, `health`, `reconcile`) is plain code and does not call a model. Adapters under `bin/cortex-loop-adapters/` are replaceable muscle. Only `try-complete` may write `status=done`, and only after the artifact, the short test, and propagation checks pass. A model may propose work or veto it. It may not approve completion.

## What this is not

This repository is not a pluggable Block inside [cortex-harness-open](https://github.com/mobfish-ai/cortex-harness-open).

cortex-harness-open is the protocol and reference tooling. A Block there has its own entrypoint, tests, and public contract. `discovery-chain-index` is the Block in that project. This tree is the heartbeat engine: ledger, clock, lease, swarm, and tick. It stays in this repository.

`bin/cortex-loop harness-run` can drive a local checkout of the harness agent-runtime (`scripts/cortex-local-mvp.mjs`) when that checkout is present. That checks a wiring path. It does not turn this engine into a Block, and it is not a substitute for `tick`.

## Layout

| Path | Role |
| --- | --- |
| `bin/cortex-loop` | Engine. Python 3, no package install. |
| `bin/cortex-loop-adapters/` | Executors. Credentials come from the environment only. |
| `bin/cortex-loop-*.sh` and `bin/cortex-loop-*.py` | Doctor, detach, MCP, expectations, cleanup helpers shipped with this slice. |
| `bin/cortex-loop-tests/` | Suite and fixtures. |
| `skills/cortex-loop/` | Operator skill: intent, errors, expectations, journal, and command references. |

The engine reads its ledger from the directory that contains `bin/cortex-loop`:

```text
brain-network/directions/CLOCK.md
brain-network/directions/<line>/TASKS.md
```

This export does not include a private ledger. `tick` with no `CLOCK.md` prints a degradation notice and exits 0. It does not invent work.

## Requirements

- Python 3
- git
- Optional Node.js 24 (`>=24.0.0 <25`) and pnpm, only for adapters or `harness-run`

## Quickstart

From the repository root:

```sh
python3 bin/cortex-loop tick
python3 bin/cortex-loop health
python3 bin/cortex-loop swarm
bash bin/cortex-loop-tests/suite.sh
```

`tick` without `--auto` only reports what is due. `--auto` advances work and needs a real ledger plus an executor. Do not pass `--auto` against an empty tree.

`health` checks the driver. Exit 0 means the blocking checks are green. A missing external cron is reported as unknown. It does not pretend to be healthy, and it does not block the heartbeat.

`swarm` prints this node's profile and who else is visible. It writes a local profile under `brain-network/directions/_swarm/` and a local git ref `refs/swarm/<swarm>/beat/<node>`. That is runtime state, not source. Set `CORTEX_NODE` if you do not want the hostname used as the node id.

Exit codes for the engine: `0` ok, `1` red or failed, `2` usage error.

The test suite builds a temporary ledger, symlinks the engine into it, and checks the completion gate, ledger reads, and ref-level swarm behavior. It does not call a model. See [Tests](#tests) for cases that still need the private tree.

## Environment

Workspace root and Node selection are the two knobs a new checkout actually needs.

| Variable | Purpose |
| --- | --- |
| `CORTEX_WORKSPACE_ROOT` | Directory for attempt, candidate, and integration receipt state, and for the free-disk admission check. Set this to the workspace root before any command that admits workers. If it is unset, the engine keeps the unexpanded placeholder `${CORTEX_WORKSPACE_ROOT}` and does not guess a home directory. |
| `CORTEX_WORKSPACE_MIN_FREE_KB` | Free-space floor for that admission check. Default `1048576` (1 GiB). |
| `CORTEX_NODE` | Stable swarm node id. Overrides hostname detection. |
| `CORTEX_NODE_ALIASES` | Optional `substring=id` list matched against the hostname. Use this for a stable nickname. The source does not ship machine names. |
| `CORTEX_SWARM` | Swarm name. Overrides the `swarm:` field in `CLOCK.md`. Default `cortex`. |
| `CORTEX_HARNESS_DIR` | Harness checkout used by `harness-run`. Default `~/cortex-harness`. Point this at a local clone of cortex-harness-open. |
| `CORTEX_MINIMAX_CN_NODES` | Comma-separated node ids that should try the MiniMax CN provider before the international one. |
| `CORTEX_MINIMAX_PROVIDERS` | Overrides MiniMax provider order entirely. |
| `CORTEX_LAUNCHD_LABEL` | launchd label. Default `com.cortex.loop`. |
| `CORTEX_REPORT_OWNER` | Owner field written into reports under `reports/`. Default `operator`. |
| `CORTEX_HARNESS_NODE_BIN` | Node binary for `harness-run`. If unset, the engine selects the highest `~/.nvm/versions/node/v24.*`. A missing Node 24 is reported as `node_v24_missing`. It is not silently replaced with an older Node. |
| `CORTEX_NODE24_BIN` | Node 24 binary for adapters that require it (`claude`, native ACP). `CORTEX_NODE24_PREFIX` is the same choice as a prefix (`$CORTEX_NODE24_PREFIX/bin/node`). |
| `CORTEX_PNPM_BIN` / `CORTEX_PNPM117_BIN` | pnpm binary for those adapters. |
| `OC_ADAPTERS_DIR` | Adapter directory. Default `bin/cortex-loop-adapters`. |
| `CORTEX_LOOP_LOG` | Engine log path. Default `/tmp/spotlight/cortex-loop.log`. |
| `CORTEX_LOOP_ENGINE` | Engine binary the suite invokes. Default `bin/cortex-loop`. |

Provider API keys are read from the process environment or from a local OpenClaw config (`OPENCLAW_JSON_PATH`, default `~/.openclaw/openclaw.json`). This repository does not contain keys.

## Tests

```sh
bash scripts/public-hygiene.sh
python3 scripts/cjk-source-gate.py
bash bin/cortex-loop-tests/suite.sh
```

On this tree the suite finishes **45 PASS, 0 FAIL, 25 SKIP**, exit 0. It does not call a model. It builds a temporary ledger for the completion-gate cases. Skips are cases whose private companion tool is not in this repository, plus H03 (the dimensional-collapse scan), which is informational.

What runs here:

- Completion gate: missing artifact, empty artifact, red short test, and a task with no artifact path or short test all stay pending. A green sample becomes `done`.
- Ledger reads, local swarm ref reads, fit-score globs, GitHub latency classification, beat-ref timestamps, and the ref write guard.
- Lease CAS against `origin`, using only `refs/swarm/test-*`, deleted afterward. The case skips when `origin` is unreachable.
- Scheduler eligibility: `CLOCK.owner` is an affinity hint. A node with a fresh heartbeat may compete for the short lease. `takeover_ready` still waits until twice the quiet limit.
- Canonical landing: `worktree-content-equivalent` can report an empty `candidate_oid` while `landed_oid` is the canonical tip.
- In-engine checks that do not load a second tool: scanner-down, propagation, six-laws, value laws, judge verdict and scope, plan reuse, run receipt, discovery/learning lineage, timeout process group, concurrent execution, ref tri-state, fail cooldown, asset health, and the public launchd/systemd examples.

`bash bin/cortex-loop-tests/harness-run-smoke.sh` exits 0 with a SKIP when `CORTEX_HARNESS_DIR` is absent or Node 24 is missing.

GitHub Actions (`.github/workflows/test.yml`) runs the hygiene gate, the CJK source gate, and the suite on push and pull request. The CJK gate fails when ideographs or fullwidth punctuation appear outside `*.zh-CN.md` and `bin/cortex-loop-tests/fixtures/`.

### Skips — private companions are not in this slice

These cases skip, with exit 0, when the companion file is absent:

| Cases | Companion |
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

H10 reads `examples/systemd/` when the private unit files are absent. H20 reads `examples/launchd/com.cortex.loop.plist`. H12 builds a temporary vendor symlink outside the repo and removes it.

The negtest bearer `sk-supersecretvalue` in `bin/cortex-loop-tests/fixtures/negtest-execution-control.py` is a deliberate fake. It is not a credential.

## License

Apache License, Version 2.0, including its patent grant. Copyright 2026 mobfish-ai. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
