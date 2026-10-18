---
name: cortex-loop
description: |
  CORTEX heartbeat and swarm: a git clock advances work (tick/try-complete/swarm/DRIFT). AI has veto power only; done can be written only by the mechanical gate.
  Triggers: cortex-loop / heartbeat / auto-advance / direction-line advance / tick / swarm / lease / HAAS /
  cortex-dashboard / cortex-probe / cortex-pulse / DRIFT.
  WHEN NOT: one-shot tasks or a strategic call go straight to the work or /hive; if you cannot write a short_test, clarify the completion bar first.
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
English | [简体中文](SKILL.zh-CN.md)

# cortex-loop — CORTEX heartbeat and swarm

> **v2.1.0** · established 2026-07-28 · swarm form 2026-07-29 · reorganized around the four questions 2026-07-29
> **Source of truth**: `bin/cortex-loop` (engine) · `bin/cortex-loop-adapters/*.sh` (muscle) · [[CLOCK]] (schedule declaration)
> **Terminal intent** [[cortex-loop/INTENT|INTENT.md]] · **error log** [[cortex-loop/ERRORS|ERRORS.md]] (includes the E031–E035 normalize / snapshot gates) · **journal** [[cortex-loop/JOURNAL|JOURNAL.md]] · **expectations** [[cortex-loop/EXPECTATIONS|EXPECTATIONS.md]]
> **Default quality gate** (2026-08-02): the main thread is an orchestration and verification node; execution is HIVE / sub-agent / worker. Code, multi-file, and high-risk tasks must have `success_criteria` + `short_test` + a local gate first. Production databases, money, permissions, accounting, destructive actions, or an ambiguous goal take the human gate in [[AGENT-CORE|AGENT-CORE §3.2]]. Ordinary reversible local changes and code PRs may advance automatically, and Merger auto-merges after Guardian passes. Small edits, pure queries, and low-risk mechanical commands may be done directly on the main thread. L2 minimum mechanical preflight: `python3 bin/agent-dispatch-contract-gate.py <contract.md> --json`. When `collaboration_pattern=distributed|long_proof` is declared, the same gate also blocks a missing critic/falsifier and a missing `failed_route_keep`.
> **Five-layer orchestration kernel** (decided 2026-08-13): this `success_criteria` / `short_test` contract is the dispatch-contract, the Hatch layer of the five-layer orchestration kernel. The full five-layer placement is in [[../loop-engineering-hub/SKILL|loop-engineering-hub §2.4]]. Collaboration-pattern fields are in [[../../aboutme/methods/structure-as-contract/dispatch-contract#03a-collaboration-pattern-spec-not-a-third-role-table|dispatch-contract §0.3a]].

---

## 1 · Who you are

> **cortex-loop moves the trigger that "keeps work moving" off a person's memory and onto a clock that lives in git.**
> The person supplies **intent**. A call is required only for the production, money, permission, destructive, or goal-ambiguity cases named in §3.2. Decomposition, advance, completion judgment, and nagging when stuck belong to the loop.

| Layer | What it is | Where it lives | Can it die |
|----|--------|--------|---------|
| **Ledger** | intent + tasks + evidence | git: `CLOCK.md` / `INTENT.md` / `TASKS.md` / `JOURNAL.md` | no |
| **Heartbeat** | wakes the ledger on time; plain code, zero LLM | launchd `com.cortex.loop` (900s) | recovers on restart; an OpenClaw outage does not affect it |
| **Muscle** | the AI that actually does the work or judges it | `bin/cortex-loop-adapters/{cheap,claude,codex,ollama,mock}.sh` | an adapter must have workspace tool capability; returning text alone is not execution |

**Boundary**: it does not invent goals and it does not cross the §3.2 human gate. Inside the authorized range it decomposes, advances, and recovers on its own. It only does the two things a person does badly: **not forgetting** and **not stopping**.

## 2 · Where it came from

**The disease**: every CORTEX asset is passive (MEMORY / STATUS / Directions / every skill). It exists only in the moment someone comes to read it. **The clock source is the operator** — if the operator does not remember a thing, it stays stopped forever, the same as if it had never been written.

**Two facts that forced it into existence** (seen firsthand on 2026-07-28): (1) the proactivity topic had already accumulated **8 reports and 0 lines of runnable code**; (2) the previous generation of nine `*-advance` lines **evaporated across the board, live=0**, dead for months with **no file, no commit, and no person noticing** — because it lived in OpenClaw's store and **did not live in git**. Conclusion: **a heartbeat cannot be a parasite.**

| Phase | Turn | Evidence |
|------|------|------|
| 07-28 | from zero to a two-node swarm: engine + CLOCK contract + launchd clock + git ref CAS lease | 8 commits, `93ae328c5`→`62b597a8b` |
| 07-29 morning | "it runs" is not "it runs correctly": propagation gate, PULSE on a clock, fail-open family cleared | E011/E012/E013 |
| 07-29 afternoon | glass-box trio + the "I am unconstrained" hole closed (`orchestrator-*` node + fault/credit) | `22d5ccb62` `ab69450ee` |
| 07-29 evening | is trust earned or farmed: no-op gate + fourth state `moot` + inspection intensity by tier | E014/E015 |
| 07-30 | 26 real lineages misjudged as future time by naive timestamps; a readable source is not a correct interpretation | E016 |

The full text is in [[cortex-loop/JOURNAL|JOURNAL.md]]. **All six Layer 0 laws added that day were born from pitfalls in this Skill**, not written as laws before the implementation (see the related Layer 0 laws section).

## 3 · Where it is going

**The terminal-direction source of truth** is [[cortex-loop/INTENT|INTENT]].
[[brain-network/directions/loop-ops/CHARTER-SWARM|CHARTER-SWARM]] defines the S0/S1 operating boundary.
`brain-network/directions/loop-ops/METRICS.json` defines the G1/G2 cohort, window, sample, baseline,
target, and approval evidence. `bin/cortex-ci.sh` checks that the contract is intact and the gates have not drifted (exit code 2). It does not freeze spoken numbers into the gate.

| Stage | Current criterion | Where to look |
|------|----------|--------|
| S0 trusted base | a run receipt can trace source/claim/origin/world; missing any one of them means no settlement | `fixture-result-receipt.py` + origin result ref |
| S1 self-ops | eligible known tasks complete the discovery→learning lineage unattended | `cortex-metrics.py --json` + Dashboard |
| G1/G2 | do not activate a target without a complete baseline, rolling window, minimum sample, and approval evidence | `METRICS.json` |
| Auxiliary diagnosis | health, trust, idle, and backlog cannot replace stage evidence | `cortex-dashboard.sh` |
| G6 | swarm health score ≥85 | 92 "healthy" | ✅ (weights still need review: a 44pt gate-pass gap only costs 8 points) |

**The full list of "we should have this and still do not" is in [[cortex-loop/EXPECTATIONS|EXPECTATIONS.md]]** (including the machine-readable `--json` exit).

## 4 · What it is here to do

Subcommands fall into seven families. Task query, create, and requeue are atomic. `task-run` and the AI mount points burn quota; the rest of the control plane is zero-LLM plain code.
Unattended, the default is to advance only 1 task per line per tick. `max_advance_per_day` is a daily cap and must not be mistaken again for per-tick concurrency.
When more throughput is truly required, set `CORTEX_MAX_ADVANCE_PER_TICK` explicitly. It is still bound by the daily cap.
Exit codes are uniform: `0` = ok / `1` = red or failed / `2` = usage error.

| Family | What it does | Subcommands |
|----|--------|--------|
| Heartbeat and ledger | advance on time; atomically create / query / requeue / hold / resume / undo a false completion; judge completion | `tick` `task-add` `task-list` `task-show` `task-retry` `task-hold` `task-resume` `task-reopen` `task-run` `next` `submit` `try-complete` `status` `idle` |
| Self-check and reconcile | is the foundation healthy; have declaration and reality come apart | `health` `reconcile` `dashboard` `why` `value` |
| Swarm coordination | who is online, which line belongs to whom, how locks are taken | `swarm` `sync` `lease` `caps` `checkin` |
| Decentralized dispatch | how one plan is claimed autonomously by many machines and then gathered | `discover` `plan` `claim` `run` `result` `gather` |
| Trust and constraint | who may do how much, and on what evidence | `trust` `attest` `fault` `credit` `readjudicate` `model` |
| **AI mount points (burn quota)** | decompose intent; independent acceptance | `decompose` `judge` |
| External and self-heal | how other systems call in, what to do when an executor dies, how the sister-repo agent-runtime actually runs | `api` `revive` `harness-run` |

**Arguments and "when to use" for every command are in [[cortex-loop/references/commands|references/commands.md]]**

---

## ⚡ Pinned hard rules T1–T11 (read before touching anything · a violation is rework)

> These are not "best practices". They are **the same few root causes** that kept reappearing across 15 ERRORS entries. Relying on memory guarantees a relapse, so each rule has a mechanical gate.
> T1–T6 were set on 2026-07-28 (`c858a9ef9`); T7–T9 were set on 2026-07-29 (three-state judgment / cross-machine propagation / trust scoring).
> **What each rule cost (the pitfall + commit + ERRORS id) is in [[cortex-loop/references/tenets|references/tenets.md]]**

| # | Hard rule | Mechanical gate |
|---|------|--------|
| **T1** | **Runtime-agnostic**: the engine knows no concrete runtime. Capability and requirements are **self-declared** by the adapter | `env-parity.sh` reads `# cortex-loop:requires-env` |
| **T2** | **Cross-environment parity**: an interactive shell can run it does not mean unattended can run it | `bash bin/cortex-loop-tests/env-parity.sh` |
| **T3** | **Fail closed, not fail open**: the verifier itself failing to run is not content passing | `ai_judge` sees `[ADAPTER_FAILED]` or empty output and REJECTs immediately |
| **T4** | **A criterion must ask "did this specific thing change"**, not "will a rerun report an error" | `short_test` uses a negative criterion `! (<scanner> \| grep -qF <specific item>)` |
| **T5** | **Silent degradation is more dangerous than an error**: every "degrade / fall back / catch-all" must make a sound | falling back to a snapshot must warn; a push failure goes to stderr; a non-zero exit adds `[ADAPTER_FAILED]` |
| **T6** | **The placeholder `-` is a legal value, not a path** | `fit_score` / `covenant_check` / the three mechanical gates all have the exception |
| **T7** | **Three states, not two**: "cannot tell" is independent of "absent". **UNKNOWN never collapses toward either side** | `dimensional-collapse-scan.sh` (wired into the suite) · probe exit codes 0/1/**2** |
| **T8** | **Done means propagated to a place others can see**: output that only sits on the local disk is not done | propagation gate v2: check whether the artifact **is in history reachable from origin** |
| **T9** | **Trust can be bought only with a real change**: rerunning a task whose criterion was already met is a no-op. No points added, no points removed | the no-op gate blocks before quota is burned + the fourth state `moot` has its own namespace + inspection intensity is tiered by trust |
| **T10** | **"The model returned text" is not "the task was executed"**: an automatic executor must have a Read/Edit/Write/Bash tool layer, and the task contract, status, and short_test are protected by the engine | `cheap-tool-smoke.sh` real Write+Read · task/short_test guard · worker single-instance lock |
| **T11** | **Process boundaries cannot be guessed from PATH or from a pattern**: automation must not use `pkill`; queries use explicit `/usr/bin/pgrep`; termination accepts only the creator's record and checks the exact PID | suite H33/H34 · `verify-process-tool-safety.py` |

**One-shot self-check**: `bash bin/cortex-loop-tests/env-parity.sh && bash bin/cortex-loop-tests/suite.sh`
(the suite contains 8 negative tests `fixtures/negtest-*.py`, each proven by a destructive check to "actually go red")

---

## 🔧 Toolbox: five tools + two helpers (look up the tool first; do not hand-roll)

> **A command that has fooled you once has the highest priority. It has already proved it will fool you again** ([[atomize-tools-doctrine|ATOMIZE law]]).
> The five tools are **orthogonal and do not overlap**. Each answers a different question.

| Tool | What question it answers | Key use |
|------|-----------|---------|
| `bin/cortex-probe.sh` | **One point: is this one thing YES or NO?** (passive; it answers only when asked) | `list` shows 10 probes; exit 0=YES / 1=NO / **2=UNKNOWN** |
| `bin/system-load-alert.sh` | **Active alert on CPU overload** (same idea as alerting when disk is low; do not wait for someone to ask) | reuses `cortex-probe.sh system-load-pressure`; launchd probes every 5 minutes; **WeCom fires once per overload episode**; recovery counts only after about 30 continuous minutes and does not send "recovered" (prevents a 5-minute flap from flooding the channel; see git-management ERRORS §4.5); detect-only, it cannot conjure more CPU |
| `bin/cortex-trace.sh` | **Why: how was this judgment reached?** | `state` `clocks` `wiring` `chain ci` `task <id>` `history [days]` |
| `bin/cortex-dashboard.sh` | **Right now: health / tasks / CI / goals on one screen** | bare run · `--json` machine-readable · `--watch` resident · `--md <path>` writes a living md |
| `bin/cortex-pulse.sh` | **Trend: worse than last time?** | exit 0=healthy / 1=red items / **2=regressed since last time** |
| `bin/cortex-ci.sh` | **Is this still the same thing? (stop drift)** | exit 0=all green / 1=failures / **2=a goal was loosened** (more serious than a test failure) |

**The difference between pulse and ci is the question, not the frequency**: pulse asks "is it healthy today"; ci asks "**is this still the same thing**" —
a system can **drift while looking perfectly healthy** (metrics all green, a gate quietly widened).
**Two helpers**: `bin/cortex-loop-detach.sh <name> "<command>"` (long runs hang in tmux; a session crash does not take them down · E010) ·
`bin/cortex-loop-mcp.py` (external MCP exit; shares the same six-law gate as `cortex-loop api`).

## ⏰ Three clocks (launchd · duties are orthogonal)

| Clock | Period | What it does |
|------|------|--------|
| `com.cortex.loop` | **900s** | **advances** tasks (does the work) |
| `com.cortex.pulse` | **3600s** | **checks** the health trend (the five P·U·L·S·E questions) |
| `com.cortex.ci` | **every day at 09:30** | **constrains** drift (full test suite + goal anchor) |

Plists live in `work-studio/devops/dotfiles/launchd/`. **Check the live state**: `bash bin/cortex-trace.sh clocks` · `bin/cortex-loop reconcile` (declaration vs reality; a split reports DRIFT).

---

## When to Use / When NOT to Use

| ✅ Use it | Why |
|---------|--------|
| A thing "stays stopped forever unless someone remembers it" | this is exactly the disease the heartbeat exists to cure |
| A direction line should advance automatically and **completion must be mechanically checkable** | artifact + short_test + propagation gate, three checks; AI saying done does not count |
| You need to catch "declared deployed but not actually running" | `reconcile` upgrades a name/reality split from a documentation discipline to a machine red light |
| Multi-machine work: who is online, who takes over, one plan claimed autonomously by many machines and then gathered | `swarm`/`sync`/`lease`/`caps` · `plan`→`claim`→`run`→`result`→`gather` (no leader) |
| Someone has to pick the work up after a session is cut | `stall_min` reclaims and re-pushes |
| You want to know whether the system is healthy, and on what evidence | dashboard + trace + `cortex-loop why` |
| You need to judge "is it there / did it succeed" and the only command at hand is one that lies | `bin/cortex-probe.sh` (three-state; UNKNOWN does not collapse to NO) |
| Code, a multi-file change, or a high-risk task should advance automatically | set `success_criteria` + `short_test` first, then dispatch an executor; the main thread only integrates and verifies — the full 4 default actions are in [[agent-code-gauntlet\|aboutme/methods/agent-code-gauntlet]] (set 2026-08-02) |

| ❌ Do not use it | Use this instead |
|-----------|-----------|
| A one-shot task, or a strategic decision that needs a human call | do it directly / `/hive`; the loop does not invent goals, and a strategic goal ambiguity is clarified only once |
| The completion bar cannot be stated and a `short_test` cannot be written | freeze the bar with one clarification; at the same time finish authorized diagnosis and continue independent DAG branches |
| You want the main thread to carry a long execution flow or a multi-file implementation | use HIVE / sub-agent / worker; the main thread is not an executor by default |
| You want to upgrade form inside a tick (script → Skill) | **`transform-emit` is forbidden inside a tick**; use the REAP / detect-* after-the-fact path |
| You want to save quota by lowering the tick frequency | wrong direction. Avalanche protection is `advance_window_min` + `max_advance_per_day` |
| You want to hand-roll a command that judges "is it there" | `bin/cortex-probe.sh list` first, to see whether a probe already exists |
| You want to change a gate or a goal so the metrics look better | `CHARTER-SWARM.out_of_scope` states the prohibition in writing; `cortex-ci.sh` exit code **2** exists to catch this |

## Autonomous advance bound to closeout (reuse AGENT-CORE §3.2)

This Skill does not define a separate autonomy, approval, or completion policy. The command mapping is:
`task-run` advances automatically inside the authorized range, `task-hold` only records a real external blocker,
`task-retry` / `task-reopen` carry a repair/replay next action, and `try-complete`
is the only mechanical gate that writes `done`. `task-add` freezes success criteria, the short test,
owned scope, and the verifier. Completion evidence is supplied jointly by a non-author rerun (Guardian may execute it) and by machine
evidence, with freshness judged by task type. A failure suspends only the affected dependencies; the independent DAG continues.
Failure settlement must keep `first_blocker` and `repair/replay_next_action`. The Harness
mapping stays `M1 → M3 → M2`; failure takes `M1_REPLAY → M3 → M2`.

## Most-used commands

```bash
bin/cortex-loop tick [--auto]        # see what is due / actually advance (launchd runs --auto every 900s)
bin/cortex-loop task-list --line cortex-immune --json
bin/cortex-loop task-show --line cortex-immune --task T18
bin/cortex-loop task-add --line X --title ... --success-criteria ... --failure-modes ... --artifact-paths ... --short-test ...
bin/cortex-loop task-retry --line X --task T --reason "root cause fixed"
bin/cortex-loop task-hold --line X --task T --status waiting_external --reason "waiting for explicit external authorization"
bin/cortex-loop task-resume --line X --task T --reason "authorization obtained"
bin/cortex-loop task-reopen --line X --task T --reason "short test only checked the doc; the real function is not wired"
bin/cortex-loop task-run --line X --task T       # exact path claim → tool execution → completion gate
bin/cortex-loop health && bin/cortex-loop reconcile   # foundation self-check + declaration vs reality (a split reports DRIFT)
bin/cortex-loop try-complete --line loop-ops --task T2   # the only command that can write done
bin/cortex-loop swarm / trust / why / idle            # who is online / trust / on what evidence / idle rate
bin/cortex-loop harness-run --json                    # actually drive the sister-repo agent-runtime once (scaffold check, not a substitute for tick)
bash bin/cortex-dashboard.sh         # one-screen overview (--json is machine-readable)
bash bin/cortex-probe.sh list        # 10 three-state probes
bash bin/cortex-loop-tests/suite.sh  # full test suite
```

Full cheatsheet → [[cortex-loop/references/operations|references/operations.md]]

---

## Load-on-demand index (the detail lives in these files; SKILL.md does not repeat it)

| File | When to read it |
|------|---------|
| [[cortex-loop/references/commands\|references/commands.md]] | you forgot a subcommand's arguments, or when to use it |
| [[cortex-loop/references/tenets\|references/tenets.md]] | you want the cost that bought each of T1–T9 |
| [[cortex-loop/references/architecture\|references/architecture.md]] | you are changing engine behavior, adding a gate, or tuning quota; or someone asks "why not let AI judge completion directly" |
| [[cortex-loop/references/swarm\|references/swarm.md]] | multi-machine trouble (who owns this line / how to judge offline / whether to take over) or you are adding a machine |
| [[cortex-loop/references/contracts\|references/contracts.md]] | you are changing CLOCK / INTENT / TASKS / node-profile fields; a contract gate reports a missing field |
| [[cortex-loop/references/operations\|references/operations.md]] | opening a new direction line, installing clocks, the full command table, or finding related docs |
| [[cortex-loop/EXPECTATIONS\|EXPECTATIONS.md]] | "what is still missing / what we still have not done / where to push next" |
| [[cortex-loop/ERRORS\|ERRORS.md]] | odd behavior; check the known root patterns first. Cleanup normalization starts at E031–E035 |
| [[aboutme/methods/asset-evolve/red-flower-board\|red-flower board]] | human-readable positive incentive. L4/L5 scoring still belongs to this Skill's `credit` / `trust`; the board does not re-score |

---

## Related skills (bidirectional index)

**host (upstream)** [[loop-engineering-hub/SKILL|loop-engineering-hub]] — to choose "which Loop to use", start at the hub.
**Same origin** [[hive/SKILL|hive]] (`stall_min` reclaim-and-repush is R·Resume made mechanical) · [[epiplexity/SKILL|epiplexity]] (axiom 1 = the acceptor must be independent).
**Companions** [[sub-agent-dispatch/SKILL|sub-agent-dispatch]] (complex orchestration) · [[model-fingerprint/SKILL|model-fingerprint]] (`attest` L-print criterion).
**Adjacent** [[cron/SKILL|cron]] (an object observed by `health`, not the heartbeat itself) · [[openclaw-master/SKILL|openclaw-master]] (job edits go through it).
**Upstream governance** [[evolve-ecosystem/SKILL|evolve-ecosystem]] — the four contracts and seven ref namespaces are registered inside the Evolve contract system.
**Architecture front door** [[cortex-architecture/SKILL|cortex-architecture]] — multi-stack lattice routing; the loop sits in **zone C, execution / enforcement** (heartbeat), Evolve sits on **edge B, knowledge**; CLI `bash bin/cortex-architecture-map.sh hang loop`.
**Default standard for code tasks** [[agent-code-gauntlet|aboutme/methods/agent-code-gauntlet]] (set 2026-08-02 · Uncle Bob Agent Code Gauntlet · acceptance before implementation / local gate / high-risk human gate / worktree isolation; currently an L1 documentation default, with L2 mechanical enforcement in the backlog).
**ACP headless / local Builder** [[acp-headless/SKILL]] — patch contract and model tier; the L2 DECIDE lane still uses the sibling Recipe and is not folded into the heartbeat engine.
**Thin peak-seeking route** [[peak-compound-loop/SKILL|peak-compound-loop]] — after the "when to advance" judgment passes, ROUND_CLOSE hangs the PEAK + TaskOptimizer peak gate. It does not replace this Skill's mechanical completion gate.

## Related Layer 0 laws (this Skill is their mechanical landing)

> The six laws added on 2026-07-29 **were all born from pitfalls in this Skill**. The laws did not exist before the implementation.
> **The six laws form a chain** (source of truth `rules/on-demand/ground-first-doctrine-guide.md` §11):
> [[ground-first-doctrine|GROUND]] look first → [[dimensional-expansion-doctrine|DIMENSIONAL]] do not flatten → [[atomize-tools-doctrine|ATOMIZE]] measuring tools must be reliable → [[glassbox-doctrine|GLASSBOX]] human and machine read the same thing → [[steer-doctrine|STEER]] the loop keeps moving → [[pulse-doctrine|PULSE]] periodic self-check

| Law | Mechanical backing (in this domain) |
|----|------------------|
| [[ground-first-doctrine]] look at the present before talking about direction; inspection intensity follows trust | `cortex-loop fault --kind decision-dodge` · `inspection_mode()` |
| [[dimensional-expansion-doctrine]] do not flatten state into a boolean (= T7) | `bin/cortex-loop-tests/dimensional-collapse-scan.sh` |
| [[atomize-tools-doctrine]] the second hand-roll must become a tool; three-state output | `bin/cortex-probe.sh` (10 probes) |
| [[glassbox-doctrine]] human and machine read one truth | `bin/cortex-dashboard.sh --json` · `bin/cortex-trace.sh` |
| [[steer-doctrine]] the main thread is the decision-maker and re-feels every round | `orchestrator-*` node + `checkin` / `credit` / `fault` |
| [[pulse-doctrine]] five questions before delivery, each with evidence | `bin/cortex-pulse.sh` · `autonomy-acceptance.sh` |
| [[latch-doctrine]] a reminder does nothing against a repeated violation → build a Hook | putting pulse / ci on a clock is itself a LATCH product |
| [[hive-doctrine]] R·Resume | `stall_min` reclaim and re-push |

---

*v2.1.0 (2026-07-29, reorganized around the four guard questions + detail sunk into references/) · source of truth `bin/cortex-loop` · charter [[cortex-loop-intent]]*

---

<!-- cortex:map-backlink d-94388841c8da3735ac51e296 -->
Related map: [[skills/cortex-loop/MAP|Cortex Loop panorama]]
