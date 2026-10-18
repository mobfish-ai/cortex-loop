---
name: cortex-loop-map
title: "cortex-loop panorama: asset inventory and viewpoint index"
type: reference
status: active
created: 2026-07-29
updated: 2026-07-29
host: cortex-loop
related:
  - "[[cortex-loop/SKILL]]"
  - "[[cortex-loop/ERRORS]]"
  - "[[cortex-loop/EXPECTATIONS]]"
  - "[[cortex-loop/JOURNAL]]"
  - "[[CHARTER-SWARM]]"
tags: [cortex-loop, map, panorama, index]
---
English | [简体中文](MAP.zh-CN.md)

# cortex-loop panorama

> **This file answers one question**: what parts this cortex-loop system is made of, how they lock together,
> and what we figured out while building it.
> File sizes were measured at 2026-07-29 23:22. The §6 swarm metrics were counted at 22:55. Neither is an estimate.
> **It does not redefine anything** — every cell points at a source of truth. This file only makes "all of it visible at a glance" possible.
>
> **For Codex / an external agent**: read [[cortex-loop/MAP|§12 asset index]] first (one flat row per asset,
> with role and the bidirectional counterpart), then drill down as needed. **Do not** start reasoning from the §0 structure diagram — the diagram is for a person. The table is for you.

---

## 0 · One-screen structure

```
                    ┌─────────────── intent layer (a person sets direction) ───────────────┐
                    │  cortex-loop/INTENT.md       terminal direction (the only SSOT)      │
                    │  CHARTER-SWARM.md            S1 operating target and thresholds      │
                    │  METRICS.json                S1 machine metrics contract             │
                    └──────────────────────┬───────────────────────────┘
                                           │ constrains
   ┌───────────────────────────────────────┼───────────────────────────────────┐
   │                            engine layer (the machine executes)            │
   │   bin/cortex-loop  216KB / 31 subcommands  ← the only place that can write done │
   │   └ adapters/  claude · codex · ollama · human · mock (muscle, swappable runtime) │
   └───────────────────────────────────────┬───────────────────────────────────┘
                     ┌─────────────────────┼─────────────────────┐
                     │                     │                     │
              ┌──────┴──────┐      ┌───────┴───────┐     ┌───────┴────────┐
              │  ledger     │      │   heartbeat   │     │  observation   │
              │ git refs ×7 │      │ 3 clocks      │     │ five tools + 2 │
              │ 177 records │      │ zero LLM      │     │ human+machine  │
              └──────┬───────┘      └───────┬───────┘     └───────┬────────┘
                     └──────────────────────┴─────────────────────┘
                                           │ produces experience
   ┌───────────────────────────────────────┴───────────────────────────────────┐
   │                       residue layer (do not make the same mistake)        │
   │  ERRORS.md E001–E015 · six Layer 0 laws · suite regression · EXPECTATIONS │
   └───────────────────────────────────────────────────────────────────────────┘
```

**How to read it**: the intent layer is decided by a **person**. The engine layer is decided by the **machine**. The **ledger** reconciles the two.
The observation layer exists so the two layers **see the same truth** ([[glassbox-doctrine|GLASSBOX law]]).

---

## 1 · Engine and tools (`bin/`)

| File | Size | What it does | When to use it |
|------|------|--------|-------------|
| `cortex-loop` | 216 KB | **engine**. 31 subcommands, the only place that can write `done` | every advance / claim / judgment |
| `cortex-dashboard.sh` | 29 KB | glass-box overview + `--json` machine-readable + `--watch` | "what is the situation now" |
| `cortex-pulse.sh` | 9.7 KB | the five P·U·L·S·E questions, hourly clock | periodic self-check, exit 0/1/2 |
| `cortex-probe.sh` | 9.5 KB | **10 three-state probes** (YES/NO/**UNKNOWN**) | judging "present/absent" or "success/failure" |
| `cortex-trace.sh` | 8.9 KB | glass-box drill-down: state/clocks/wiring/chain/task | "why was it judged this way" |
| `cortex-ci.sh` | 5.6 KB | daily CI: regression + **goal anchor** (exit 2 = drifted) | stop regression and drift |
| `cortex-loop-expectations.py` | 5.0 KB | EXPECTATIONS machine reader | "what is still not done" |
| `cortex-capability-bundle.py` | 4.8 KB | pack a node's capabilities | dispatch work by capability |
| `cortex-loop-mcp.py` | 4.9 KB | MCP interface | an external agent connects |
| `cortex-loop-detach.sh` | 2.7 KB | detach a long command from the terminal | stop an E010 session crash from killing everything |

**Muscle (adapters, swappable runtime)**: `claude.sh` · `codex.sh` · `ollama.sh` · `human.sh` · `mock.sh`

> **Design point**: every tool emits **three states**. `UNKNOWN` never collapses toward `NO` —
> collapsing toward healthy is fail-open, and collapsing toward fault is over-conservative. See [[dimensional-expansion-doctrine]].

---

## 2 · Ledger layer (git refs · 177 measured)

| Namespace | Count | Meaning |
|---------|------|------|
| `refs/swarm/cortex/claim/` | 61 | claim (a git ref CAS used as a distributed lock) |
| `refs/swarm/cortex/result/` | 52 | output result |
| `refs/swarm/cortex/plan/` | 36 | plan |
| `refs/swarm/cortex/moot/` | 16 | no-op (criterion already met; burns no quota and scores nothing) |
| `refs/swarm/cortex/incident/` | 8 | incident |
| `refs/swarm/cortex/beat/` | 3 | heartbeat |
| `refs/swarm/cortex/lease/` | 1 | lease |

**Why git refs and not a database**: the non-fast-forward rejection of `git push <sha>:<ref>`
is a CAS (compare-and-swap) by nature — many machines contending for a lock need no extra middleware, and the ledger carries its own audit history.

**Text ledgers**: `CLOCK.md` (schedule declaration) · `loop-ops/TASKS.md` (todos) —
the suite's F15 case checks them byte for byte so tests have not polluted them.

---

## 3 · Heartbeat layer (3 clocks · zero LLM)

| Clock | Period | Duty | State on this machine |
|------|------|------|---------|
| `com.cortex.loop` | 15 min | main advance (tick) | EXIT=0 ✅ |
| `com.cortex.pulse` | 1 h | the five health questions | EXIT=1 (items below the bar; expected) |
| `com.cortex.ci` | daily | regression + goal anchor | EXIT=0 ✅ |

**Duties are orthogonal**: the one that advances does not judge health, the one that judges health does not judge drift, and a failure of one does not hide a failure of another.
**Hard time budget**: one tick's cap must be `≥600s` (long enough to finish a real task) and `<900s` (shorter than the clock period,
or one stuck tick occupies the slot forever). The resident criterion is suite `H10`.

---

## 4 · Skill family (`skills/cortex-loop/`)

| File | Size | What it answers |
|------|------|---------|
| **INTENT.md** | 5.5 KB | **terminal state: why it exists, where it is going, the human-machine covenant, promotion bounds** |
| **SKILL.md** | 17.3 KB | **the four guard questions** (who you are / where it came from / where it is going / what it is here to do) + hard rules T1–T9 |
| **ERRORS.md** | 32.7 KB | mistakes already made (E001–E015) |
| **JOURNAL.md** | 19.9 KB | build journal (how it grew into this, step by step) |
| **EXPECTATIONS.md** | 10.0 KB | **not done yet** (20 rows, machine-readable with `--json`) |
| **MAP.md** | this file | the panorama: which parts exist + what was figured out |

**Detail that was sunk** (`references/`, read on demand, not loaded by default):

| File | Size | When to read it |
|------|------|---------|
| [[cortex-loop/references/architecture\|architecture.md]] | 12.0 KB | changing the engine / understanding the three-part architecture |
| [[cortex-loop/references/commands\|commands.md]] | 8.9 KB | the concrete use of the 31 subcommands |
| [[cortex-loop/references/operations\|operations.md]] | 8.2 KB | deploy / operate / add a direction line |
| [[cortex-loop/references/tenets\|tenets.md]] | 5.5 KB | the real cost of each of T1–T9 |
| [[cortex-loop/references/contracts\|contracts.md]] | 4.4 KB | writing or changing contract fields |
| [[cortex-loop/references/swarm\|swarm.md]] | 4.2 KB | multi-node, sharding, lease, trust |

---

## 5 · Residue layer

### 5.1 Error log E001–E015 (15 entries)

| # | One sentence | Root pattern |
|---|--------|------|
| E001 | treated the "column meaning" legend table as the data table | definition |
| E002 | wrong primary key → silently read 0 rows | **silent failure** |
| E003 | for-each-ref format-string escape → silent fallback to the file snapshot | **measuring tool** |
| E004 | rev-parse returns empty when the local ref is missing → push becomes a remote deletion | **fatal · silent failure** |
| E005 | health treated "delivery failed" as "execution failed" | **dimensional collapse** |
| E006 | a dead credential hung at the end of the fallback chain, unnoticed for a long time | silent degradation |
| E007 | lid closed → launchd stopped firing; "the log is continuous" was misread as "it has been running" | measuring tool |
| E008 | a later table wiped the header → the only write entrance crashed | data |
| E009 | a CAS rejection and a network fault flattened into the same return value | **dimensional collapse** |
| E010 | a long-running process bound to the terminal → one session crash killed everything | runtime |
| E011 | false completion: short_test reused the scanner exit code + the verifier failed open | **false green** |
| E012 | cross-environment inconsistency: interactive can run it does not mean unattended can | environment |
| E013 | dimensional collapse: flattened into one judgment, and what is lost is "why" | **dimensional collapse** |
| E014 | no-op score farming: rerunning a task whose criterion was already met still counted as passed | **false green** |
| E015 | claim and execute each counted the other as load → full, zero output | deadlock |

**Four root patterns keep reappearing**: silent failure · an unreliable measuring tool · dimensional collapse · false green.
These four are exactly what the six laws below are there to stop.

### 5.2 Six Layer 0 laws (this Skill is their mechanical landing)

```
GROUND look first (start) → DIMENSIONAL do not flatten (model) → ATOMIZE measuring tools are reliable (collect)
→ GLASSBOX human and machine both read (present) → STEER the loop keeps moving (run) → PULSE periodic self-check (conserve)
```

| Law | Short trigger | Mechanical backing |
|----|---------|---------|
| [[ground-first-doctrine\|GROUND]] | 2414 B | `fault --kind decision-dodge` · `inspection_mode()` |
| [[dimensional-expansion-doctrine\|DIMENSIONAL]] | 2076 B | `dimensional-collapse-scan.sh` |
| [[atomize-tools-doctrine\|ATOMIZE]] | 2068 B | `cortex-probe.sh` (10 probes) |
| [[glassbox-doctrine\|GLASSBOX]] | 2028 B | `cortex-dashboard.sh` · `cortex-trace.sh` |
| [[steer-doctrine\|STEER]] | 2033 B | `orchestrator-*` node + `checkin`/`credit`/`fault` |
| [[pulse-doctrine\|PULSE]] | 2168 B | `cortex-pulse.sh` (hourly) |

All six are paired with the full text of `rules/on-demand/*-guide.md`, and **the links are already bidirectional**.

### 5.3 Test suite (`bin/cortex-loop-tests/` · the live exit code is what counts)

Groups A–F plus the H specials. The negative tests that matter (**each one was destructively verified to go red**):

| Case | What it stops |
|------|--------|
| `H08` | mechanical check of acceptor labels (out of bounds is rejudged SCOPE; inside the bounds, not one is widened) |
| `H10` | one tick's time budget (too short and a real task cannot finish; too long and it jams the clock slot) |
| `H11` | load-rate numerator and denominator in the same window (no fail-open across days) |
| `F15` | the real ledgers `CLOCK.md` / `TASKS.md` are unchanged byte for byte (tests must not pollute production) |
| `T3` sentinel | **must stay blocked** — turning green means the completion gate was widened |

---

## 6 · Swarm as measured (2026-07-29 22:55 · gate-pass rate 46 and islands 0 rechecked consistent at 23:22)

| Node | HAAS | Level | Autonomy | Samples | Breaches |
|------|------|------|--------|------|------|
| worker | 0.762 | L3 | ✅ reversible automatic | 16 | 0 |
| laptop | 0.590 | L2 | ❌ mostly advice | 18 | 1 |
| **orchestrator-laptop** (main thread) | **0.195** | L1 | ❌ confirm every step | 3 | **5** |

**Swarm-wide 0.195** = mean 0.435 × bottleneck factor 0.45.
**Credibility depends on the weakest one, not the average one** — so the main thread is the current bottleneck.

| Metric | Current | Target | Gap |
|------|------|------|-----|
| G1/G2 | cumulative track record and rolling cohort are separated | approved: G1 7 days / G2 24 hours, both targets ≥90% | `python3 bin/cortex-metrics.py --json` |
| idle rate | 66% | <30% | 36 pt |
| true islands | 0 | 0 | ✅ |
| suite | live run | 0 FAIL | `bash bin/cortex-loop-tests/suite.sh` |

---

## 7 · Viewpoint layer — what was figured out while building this

> This is **the most valuable section of the map**. The inventory above will go stale. These will not.
> Two classes: **set by the operator** (direction and criteria) and **earned by engineering evidence** (stepped in).

### 7.1 Set by the operator (direction and criteria)

| # | Viewpoint | Where it lands |
|---|------|--------|
| 1 | **you can start without knowing the direction** — first turn the real situation inside out. The problem surfaces on its own | [[ground-first-doctrine\|GROUND]] G |
| 2 | low-hanging fruit first; **talk about "a better improvement" only after those are clear**. That is the next layer of decision | GROUND R/O |
| 3 | **inspection intensity follows trust** (a new supplier is fully inspected, an established supplier is sampled) — garment-factory inspection | GROUND U · `inspection_mode()` |
| 4 | **what is mine to judge, I judge. I do not push it onto a person** — a person's attention is the scarcest resource | GROUND N · `fault decision-dodge` |
| 5 | **the main thread is the decision-maker, not the executor**, and it is itself a peer node that has to level up the same way | [[steer-doctrine\|STEER]] · `orchestrator-*` |
| 6 | **each round's "feel" must be felt again**. Do not push from the previous round's conclusion (a conclusion's half-life is measured in hours) | STEER S |
| 7 | **human and machine reading one truth is the human-machine interface**; the whiter and more traceable it is, the more trust it can build | [[glassbox-doctrine\|GLASSBOX]] |
| 8 | **do not flatten state into a boolean**. What gets flattened is exactly "why", and "why" decides the next step | [[dimensional-expansion-doctrine\|DIMENSIONAL]] |
| 9 | **hand-rolling once is allowed. The second time it must become a tool.** One that has fooled us has the highest priority | [[atomize-tools-doctrine\|ATOMIZE]] |
| 10 | before delivery, **ask five questions, each with evidence**. The question that cannot produce evidence is the real gap | [[pulse-doctrine\|PULSE]] |
| 11 | **the four guard questions are the lowest acceptance bar** — who you are / where it came from / where it is going / what it is here to do | SKILL.md §1–§4 |
| 12 | idle rate down → full rate up → economic return up. **The three steps cannot be skipped** | dashboard load rate |
| 13 | **rejudging is allowed. Erasing the ledger is not** — deleting a ref to "clean up" a number is forbidden | `readjudicate` |
| 14 | "found it, and still cannot fix it stably" must not happen | CHARTER-SWARM G1 |
| 15 | **an honest UNKNOWN beats a good-looking fake number** | CHARTER-SWARM Trade section |
| 16 | after a whole-machine restart it must be able to **resume from the breakpoint**, not start over | HIVE R·Resume made mechanical |

### 7.2 Earned by engineering evidence (stepped in)

| # | Viewpoint | Evidence |
|---|------|------|
| 17 | **a no-op is worse than a failure** — rerunning a task whose criterion was already met still counts as passed, and farms trust up | E014 · 16 rows of the fourth state `moot` |
| 18 | **output must reach git history visible from origin**. Landing only on the local disk is not completion | propagation gate v2 |
| 19 | **fix one layer, and the next layer becomes visible** — a 300s timeout was hidden all day by health staying red | H10 |
| 20 | **code that was fixed and cannot be propagated equals not fixed** — the worker was 532 commits behind and locked itself out with an old ruler | today's real cause of the no-op |
| 21 | **an inflated denominator turns a debt that does not exist into a debt that can never return to zero** | islands "56" → actually 0 |
| 22 | **different windows on the same quantity = fail-open across days**, and the longer there is no output the thicker the historical stock and the better the number looks (it hides itself) | H11 · idle rate |
| 23 | **the measuring tool itself lies**, 6 times so far: `grep -cE` escaping · `tail` swallowing an exit code · `ls` with multiple paths · a CJK variable name · `--json` line breaks · `for-each-ref`'s `*` does not cross `/` | the basis for enacting ATOMIZE |
| 24 | **every new gate is slapped by its own live check on day one** (propagation gate v1→v2, two PULSE holes on day one, SCANNER-DOWN welded shut) — so a negative test must be verified destructively | tenets.md |
| 25 | **a numeric target with no baseline, window, minimum sample, and approval evidence is not a gate** | the `METRICS.json` contract |
| 26 | **"cannot tell" must be an independent third state** — collapsing toward healthy is fail-open, collapsing toward fault is over-conservative | 10 probes' UNKNOWN |
| 27 | **the heartbeat keeps firing and output stays zero, and that is harder to notice than death** — the illusion of alive and healthy is the most expensive | worker 300s |
| 28 | **swarm credibility = the weakest node, not the average node** | bottleneck factor 0.45 |
| 29 | **two failure classes with opposite fixes must be distinguishable**: `status=1/FAILURE` (the criterion will not let it run; fix the criterion) vs `15/TERM` (it was killed while running; give it time) | H10 assertion |
| 30 | **the organizing principle of a split is the four questions, not "used often / used rarely"** — the file got smaller and the reader still does not know what this is, which equals not splitting | SKILL.md 40.7→17.1 KB |

---

## 8 · Intent and goals (set by a person; the machine may not change them itself)

| File | Size | What it governs |
|------|------|--------|
| [[cortex-loop/INTENT]] | 5.5 KB | **the only SSOT of terminal direction: autonomous fulfillment kernel + human-machine covenant + S0–S4** |
| [[CHARTER-SWARM]] | operating Charter | **S0/S1 bounds and promotion evidence** |
| `METRICS.json` | JSON | **G1/G2 cohort, window, baseline, target, and approval** |
| `INTENT-P2.md` | historical | superseded; it does not take part in the current stage judgment |
| `GOAL-throughput.md` | historical | superseded; it does not take part in the current metrics judgment |
| `INTENT.md` | 3.2 KB | the direction line's original intent |
| `TASKS.md` | 3.6 KB | todo ledger (consumed by the machine) |
| `PROGRESS.md` | 19.4 KB | resume-from-breakpoint progress |
| `JOURNAL.md` | 11.7 KB | direction-line journal |

---

## 9 · Related skills

| Skill | Relation |
|-------|------|
| [[loop-engineering-hub/SKILL]] | **upstream console** (this Skill hangs under it) |
| [[hive/SKILL]] | the mechanical landing of R·Resume is this engine's "reclaim a stalled running and re-push" |
| [[sub-agent-dispatch/SKILL]] | the other dispatch path (when a person is present) |
| `skills/cron` (**a soft link outside the vault** → `~/.aionui/builtin-skills/`) · [[openclaw-master/SKILL]] | clocks and the external orchestration layer |
| [[evolve-ecosystem/SKILL]] · [[model-fingerprint/SKILL]] · [[epiplexity/SKILL]] | ecosystem / model side |
| [[cortex-architecture/SKILL]] | **front door of the whole multi-stack lattice**; this engine = lattice **zone C (execution / enforcement / heartbeat)** |

### 9.1 Multi-stack lattice hang (2026-08-02 · division of labor with Evolve)

> Full text: [[reports/2026-08-02/architecture/cortex-multi-stack-coherence-map|coherence map]] · CLI: `bash bin/cortex-architecture-map.sh hang all`

| Zone | Who | How cortex-loop uses it |
|----|-----|-------------------|
| **B knowledge net** | Evolve (edges) + insight/memory/skill-ecosystem (points) | **consumes** Skills/Methods/Rules that are already hardened; after completion, REAP may trigger detect-*. **`transform-emit` inside a tick is forbidden** |
| **C execution / enforcement** | **this engine** + Runtime-L2 + L-git | clock advance, claim, mechanical completion gate, swarm |
| **A delivery profile** | Ankole HTML 01–05 | tells a person "the loop is in the orchestration layer"; it does not replace this MAP |
| **Data vertical** | D-Tier / data governance | a business task's short_test is often pinned to a D0–D2 source of truth; the loop does not replace the data stack |
| **Coordinates** | 5D Gravity | an entity may fill C2/ETCLOVG; HAAS trust and loop trust share the mobfish six laws |

**Flywheel**: loop executes → evidence → REAP → Evolve raises the dimension (if it hits) → the next loop spends fewer tokens = CIE.

---

## 10 · Related reports from that day (`reports/2026-07-29/_standalone/`)

`cortex-loop-throughput-fix` 22 KB · `cortex-loop-modernization` 19 KB ·
`cortex-loop-engine-fixes` 15 KB · `cortex-loop-consolidation` 15 KB ·
`island-skills-cleanup` 9.5 KB · `layer0-compression` 8.1 KB ·
`cortex-loop-handoff` 7.6 KB · `idle-rate-fix` 6.8 KB ·
`cortex-loop-next-round-design` 5.4 KB · `dashboard-async` 4.5 KB

---

## 11 · How to use this map

| What you want to do | Where to enter |
|-----------|--------|
| first contact; you want to know what this is | [[cortex-loop/SKILL]] §1–§4 (the four guard questions, first 94 lines) |
| what is the situation now | `bash bin/cortex-dashboard.sh` |
| why a task is stuck on Git delivery | `python3 bin/cortex-workspace-inspect.py` · Dashboard "delivery pipeline" |
| which Agent worktrees are really in use, and which can be reclaimed | `python3 bin/git-worktree-doctor.py --json` · Dashboard "development workspaces" |
| why it was judged this way | `bash bin/cortex-trace.sh` · `python3 bin/cortex-loop why <id>` |
| what is still not done | [[cortex-loop/EXPECTATIONS]] · `python3 bin/cortex-loop-expectations.py --json` |
| do not make the same mistake again | [[cortex-loop/ERRORS]] |
| before changing the engine | `references/architecture.md` + `references/tenets.md` |
| where the terminal state is going, and what the human-machine boundary is | [[cortex-loop/INTENT]] (**read only**) |
| how current S1 runs, and whether the metrics are in effect | [[CHARTER-SWARM]] + `METRICS.json` (**read only**) |

---

## 12 · Asset index (machine-readable)

> **One row, one asset.** For Codex / an external agent to reason and plan completely.
> The `↔` column is the **bidirectional counterpart** (who points at it / who it points at). `—` means not markdown, and it does not take part in the wikilink network.
> Sizes are byte counts measured at 2026-07-29 23:22.

### 12.1 Intent layer (set by a person; the machine may not change it itself)

| Asset | Kind | Size | Role | ↔ counterpart |
|------|------|------|------|-----------|
| [[cortex-loop/INTENT]] | md | 5.5 K | **the only SSOT of terminal direction** | [[cortex-loop/SKILL]] · [[CHARTER-SWARM]] · [[cortex-loop/MAP]] |
| [[CHARTER-SWARM]] | md | operating Charter | **S0/S1 bounds and evidence** | [[cortex-loop/INTENT]] · [[cortex-loop/SKILL]] · [[cortex-loop/MAP]] |
| `METRICS.json` | json | metrics contract | **the only machine source of truth for G1/G2** | Dashboard · PULSE · CI |
| [[GOAL-throughput]] | md | historical | superseded | `METRICS.json` |
| [[loop-ops/INTENT-P2\|INTENT-P2]] | md | historical | superseded | [[cortex-loop/INTENT]] |
| [[loop-ops/INTENT\|INTENT]] | md | 3.2 K | the direction line's original intent | [[cortex-loop/MAP]] |
| [[loop-ops/TASKS\|TASKS]] | md | 3.6 K | todo ledger (**consumed by the machine**) | the engine's `tick` reads it · [[cortex-loop/MAP]] |
| [[loop-ops/PROGRESS\|PROGRESS]] | md | 19.4 K | resume-from-breakpoint progress | HIVE R·Resume · [[cortex-loop/MAP]] |
| [[loop-ops/JOURNAL\|loop-ops/JOURNAL]] | md | 11.7 K | direction-line journal | [[cortex-loop/MAP]] |

### 12.2 Engine and tools (`bin/` · not md)

| Asset | Size | Role | Three-state | ↔ document counterpart |
|------|------|------|------|-----------|
| `bin/cortex-loop` | 216 K | **engine · 31 subcommands · the only writer of done** | — | `references/commands.md` · `architecture.md` |
| `bin/cortex-dashboard.sh` | 29 K | glass-box overview + `--json` + `--watch` | ✅ | [[glassbox-doctrine]] |
| `bin/cortex-pulse.sh` | 9.7 K | five-question self-check (hourly) | ✅ 0/1/2 | [[pulse-doctrine]] |
| `bin/cortex-probe.sh` | 9.5 K | **10 probes** YES/NO/UNKNOWN | ✅ | [[atomize-tools-doctrine]] |
| `bin/cortex-trace.sh` | 8.9 K | glass-box drill-down | ✅ | [[glassbox-doctrine]] |
| `bin/cortex-ci.sh` | 5.6 K | daily regression + **goal anchor** (exit 2 = drifted) | ✅ | [[CHARTER-SWARM]] |
| `bin/cortex-loop-expectations.py` | 5.0 K | EXPECTATIONS machine reader | ✅ 0/1/2 | [[cortex-loop/EXPECTATIONS]] |
| `bin/cortex-workspace.sh` | dynamic | sparse attempt cabin: private index / crash recovery / disk gate | ✅ | `references/architecture.md` · `references/commands.md` |
| `bin/cortex-candidate.sh` | dynamic | Candidate scope check / immutable publish / query | ✅ 0/2/75 | `references/swarm.md` · `references/commands.md` |
| `bin/cortex-integrator.sh` | dynamic | blobless integration + canonical lease-CAS | ✅ 0/1/2/75 | `references/architecture.md` · `references/commands.md` |
| `bin/cortex-workspace-inspect.py` | dynamic | delivery-plane stats for workspace/candidate/landed/stale locks | ✅ 0/1 | `cortex-dashboard.sh` · `references/commands.md` |
| `bin/git-worktree-doctor.py` | dynamic | worktree claim / live process / dirty edit / recoverable reclaim | ✅ 0/1/2/3 | `cortex-dashboard.sh` · `references/commands.md` |
| `bin/cortex-capability-bundle.py` | 4.8 K | pack a node's capabilities | — | `references/swarm.md` |
| `bin/cortex-loop-mcp.py` | 4.9 K | MCP interface (an external agent connects) | — | — |
| `bin/cortex-loop-detach.sh` | 2.7 K | detach a long command from the terminal | — | [[cortex-loop/ERRORS]] E010 |
| `bin/cortex-loop-adapters/*.sh` | ×5 | muscle: claude/codex/ollama/human/mock | — | `references/architecture.md` |

### 12.3 Skill family (`skills/cortex-loop/`)

| Asset | Size | What it answers | ↔ counterpart |
|------|------|---------|-----------|
| [[cortex-loop/INTENT]] | 5.5 K | **terminal state + human-machine covenant + promotion bounds** | [[cortex-loop/SKILL]] · [[CHARTER-SWARM]] · [[cortex-loop/MAP]] |
| [[cortex-loop/SKILL]] | 17.3 K | **the four guard questions** + T1–T9 | the whole family · the six laws · [[cortex-loop/INTENT]] · [[CHARTER-SWARM]] |
| [[cortex-loop/ERRORS]] | 32.7 K | mistakes already made, E001–E015 | the six laws (error→law map) · [[cortex-loop/MAP]] |
| [[cortex-loop/JOURNAL]] | 19.9 K | build journal | [[cortex-loop/SKILL]] · [[cortex-loop/MAP]] |
| [[cortex-loop/EXPECTATIONS]] | 10.0 K | **20 things not done yet** (`--json`) | [[CHARTER-SWARM]] · [[cortex-loop/MAP]] |
| [[cortex-loop/MAP]] | this file | panorama + viewpoint index | **all of them** |
| [[cortex-loop/references/architecture\|references/architecture]] | 12.0 K | three-part architecture (required reading before an engine change) | [[cortex-loop/SKILL]] · [[cortex-loop/MAP]] |
| [[cortex-loop/references/commands\|references/commands]] | 8.9 K | the 31-subcommand detail table | [[cortex-loop/SKILL]] · [[cortex-loop/MAP]] |
| [[cortex-loop/references/operations\|references/operations]] | 8.2 K | deploy / operate / add a direction line | [[cortex-loop/SKILL]] · [[cortex-loop/MAP]] |
| [[cortex-loop/references/tenets\|references/tenets]] | 5.5 K | the real cost of each of T1–T9 | [[cortex-loop/SKILL]] · [[cortex-loop/MAP]] |
| [[cortex-loop/references/contracts\|references/contracts]] | 4.4 K | contract fields | [[knowledge-contract-registry]] · [[cortex-loop/MAP]] |
| [[cortex-loop/references/swarm\|references/swarm]] | 4.2 K | multi-node / sharding / lease / trust | [[CHARTER-SWARM]] · [[cortex-loop/MAP]] |

### 12.4 Residue layer · six Layer 0 laws (this Skill = their mechanical landing)

| Law | Short trigger | Full guide | Mechanical backing |
|----|---------|-----------|---------|
| [[ground-first-doctrine\|GROUND]] | 2414 B | [[ground-first-doctrine-guide]] | `fault decision-dodge` · `inspection_mode()` |
| [[dimensional-expansion-doctrine\|DIMENSIONAL]] | 2076 B | [[dimensional-expansion-doctrine-guide]] | `dimensional-collapse-scan.sh` |
| [[atomize-tools-doctrine\|ATOMIZE]] | 2068 B | [[atomize-tools-doctrine-guide]] | `cortex-probe.sh` |
| [[glassbox-doctrine\|GLASSBOX]] | 2028 B | [[glassbox-doctrine-guide]] | `cortex-dashboard.sh` · `cortex-trace.sh` |
| [[steer-doctrine\|STEER]] | 2033 B | [[steer-doctrine-guide]] | `orchestrator-*` · `checkin`/`credit`/`fault` |
| [[pulse-doctrine\|PULSE]] | 2168 B | [[pulse-doctrine-guide]] | `cortex-pulse.sh` |

### 12.5 Ledger and heartbeat (runtime · not files)

| Asset | Measured | Role |
|------|------|------|
| `refs/swarm/cortex/{claim,result,plan,moot,incident,beat,lease}` | 177 rows | a git ref CAS used as a distributed lock |
| `com.cortex.loop` (launchd) | 15 min · EXIT=0 | main advance |
| `com.cortex.pulse` | 1 h · EXIT=1 | the five health questions |
| `com.cortex.ci` | daily · EXIT=0 | regression + goal anchor |
| `work-studio/devops/dotfiles/systemd/cortex-loop.service` | 840 s | the worker side's one-tick budget |

### 12.6 Test suite (`bin/cortex-loop-tests/` · live run)

| Case | What it stops | Destructive check |
|------|--------|-----------|
| `H08` | acceptor-label check (out of bounds is SCOPE; inside the bounds, not widened) | ✅ |
| `H10` | one tick's time budget (lower bound 600s / upper bound <900s) | ✅ |
| `H11` | load-rate numerator and denominator in the same window (no fail-open across days) | ✅ |
| `F15` | the real ledger is unchanged byte for byte (tests must not pollute production) | ✅ |
| `T3` sentinel | **must stay blocked**; turning green means the gate was widened | ✅ |
| `dimensional-collapse-scan.sh` | boolean-collapse scan | — |
| `autonomy-acceptance.sh` | autonomy acceptance | — |
| `env-parity.sh` | interactive is not unattended (E012) | — |

### 12.7 Reports (`reports/2026-07-29/_standalone/`)

| Report | Size | Contents |
|------|------|------|
| [[cortex-loop-throughput-fix]] | 22 K | throughput push: the real cause of the worker no-op + the 300s kill |
| [[cortex-loop-modernization]] | 19 K | SKILL reorganized around the four guard questions + bidirectional edges filled in |
| [[cortex-loop-engine-fixes]] | 15 K | engine-defect fixes (E014 no-op gate / E015 deadlock) |
| [[cortex-loop-consolidation]] | 15 K | system merge and governance |
| [[island-skills-cleanup]] | 9.5 K | islands 56 → actually 0 (evidence of an inflated denominator) |
| [[layer0-compression]] | 8.1 K | Layer 0 short-trigger compression |
| [[cortex-loop-handoff]] | 7.6 K | handoff notes |
| [[idle-rate-fix]] | 6.8 K | the idle-rate deadlock broken |
| [[cortex-loop-next-round-design]] | 5.4 K | next-round design |
| [[dashboard-async]] | 4.5 K | Dashboard asynchronous collection |

---

## 13 · A reasoning entrance for Codex

> This is not asking you to restate it. It is asking you to **find what we have not seen**. Each row below states our current position.
> **Attack the position first. Do not add agreement.**

| # | To reason about | Our current position | Attack surface |
|---|--------|-------------|--------|
| 1 | how the G1/G2 target is maintained | there is already a baseline, a rolling window, a minimum sample, and human approval evidence; a change still needs a new approval record | are sample independence and window length still enough to support a decision? |
| 2 | swarm-wide trust = mean × **bottleneck factor 0.45** | credibility depends on the weakest node | does the bottleneck factor over-punish? Should main-thread L1 be counted separately? |
| 3 | the main thread is both the **decision-maker** and a **scored node** | only peer status has binding force | how is the referee problem of scoring and penalizing oneself broken? |
| 4 | the six laws chain GROUND→DIMENSIONAL→ATOMIZE→GLASSBOX→STEER→PULSE | the order is the dependency | is the chain a real dependency or a story told afterward? Is there a cycle? |
| 5 | "no-op" enacted as the fourth state `moot` | burns no quota and scores nothing | can it be abused as an excuse to avoid execution? |
| 6 | viewpoint #24, "every new gate is slapped by itself on day one", was not made a law (the LATCH bar was not met) | written only into `tenets.md` | has it already reached the ≥3 bar and should be enacted? |
| 7 | whether EXPECTATIONS is consumed | Dashboard already takes total/eligible/non-eligible | how is a row that has an owner and a short_test promoted safely into an S1 task? |
| 8 | the worker git-sync cron is still off (269 files of divergence undecided) | **the largest stock risk** | recovery strategy? How is the divergence adjudicated? |

---

*Size count 2026-07-29 23:22 · swarm metrics 22:55 · numbers will go stale; §7 viewpoints and the §13 reasoning entrance will not ·
when the numbers change, rerun the count commands in §1–§6 of this file · bidirectional edges are guarded by `bin/verify-wikilinks.py`*
