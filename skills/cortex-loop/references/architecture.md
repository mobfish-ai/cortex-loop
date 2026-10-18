English | [简体中文](architecture.zh-CN.md)

# cortex-loop design principles (why it is built this way)

> **When to read this**: you want to change engine behavior, add a gate, tune the quota policy, or someone asks "why not let AI judge completion directly".
> Commands only → [[cortex-loop/references/commands|commands.md]]. Deploy only → [[cortex-loop/references/operations|operations.md]].
> **Parent**: [[cortex-loop/SKILL|SKILL.md]]

---

## The disease and the remedy

**The disease**: every CORTEX asset is passive (MEMORY / STATUS / Directions / every skill). It exists only in the moment someone comes to read it. **The clock source is the operator** — if the operator does not remember a thing, it stays stopped forever, the same as if it had never been written.

**Why it has to be native**: a heartbeat cannot be a parasite. The previous generation of nine `*-advance` lines evaporated across the board (seen firsthand on 2026-07-28, live=0). The cause of death was not a bad design. **It lived in OpenClaw's store and did not live in git** — so it was dead for months with no file, no commit, and no person noticing.

**Boundary**: it does not decide for a person, invent a goal, or make the call for a person. It only does the two things a person does badly: **not forgetting** and **not stopping**.

---

## Three-part architecture

| Layer | What it is | Where it lives | Can it die |
|----|--------|--------|---------|
| **Ledger** | intent + tasks + evidence | git: `CLOCK.md` / `INTENT.md` / `TASKS.md` / `JOURNAL.md` | no |
| **Heartbeat** | wakes the ledger on time; plain code, zero LLM | launchd `com.cortex.loop` (900s) | recovers on restart; an OpenClaw outage does not affect it |
| **Muscle** | the AI that actually does the work or judges it | `bin/cortex-loop-adapters/*.sh` | if it dies, swap it; the loop does not know who it is |

## Distributed delivery plane: shared objects, not a shared worktree

The control plane keeps using CAS/lease on `refs/swarm/*`. Execution and delivery split into five stages:

1. claim freezes `run_id/base_oid/allowed_paths`;
2. `cortex-workspace.sh` creates a bounds-sparse attempt cabin with its own index and shared objects;
3. the Worker produces only inside the cabin, and `cortex-candidate.sh` publishes an immutable candidate ref;
4. `cortex-integrator.sh` re-checks scope, read-only dependencies, and short_test in a blobless + sparse isolated repo, and integrates with an exact lease-CAS of the master tip;
5. a reachable candidate is only `integration_pending`; it is called done only after the landed commit is an ancestor of canonical master.

The only thing allowed to serialize globally is one atomic update of the canonical ref. LLM calls, network waits, file generation, tests, and deploys do not hold a global work lock.
Scheduling parallelism is decided jointly by write-set conflicts, Worker/account capacity, and the disk budget. Non-overlapping write sets run in parallel. Waiting on a conflict is not a failure.

**The precise meaning of "independent of Agent Runtime"**: it is not "use no runtime". It is **the loop recognizes none of them**. `CLOCK.md` says `executor: claude`. Change it to `codex` and the muscle changes. The ledger and the heartbeat do not change a word.

### Available muscle (adapter interface: `$1=prompt file $2=result file`)

| adapter | Behavior | When to use it |
|---------|------|-----------|
| `human` | the prompt is delivered to `/tmp/spotlight/cortex-loop-human-inbox.md`; **burns no tokens and produces no side effect** | **default for a new line**. Let a person watch a few rounds, then switch to automatic |
| `claude` | `timeout 1500 claude -p` (headless, no session) | the line is running smoothly and should truly advance automatically |
| `codex` | must go through the `bin/codex-validate.sh` wrapper (bare `codex exec` is forbidden) | when a second model's independent view is needed |
| `ollama` | a local model, **zero quota and zero network** | the bottom rung of the three-step degradation ladder: still able to advance when every cloud line hits quota or 403 (`3436107a5`) |
| `mock` | emits a fixed 3-line sample, zero model calls | self-test of "will structural acceptance correctly discard a bad row" |

**An executor must report the real model and the billing mode** (`9334868bb`): `exec.claude` is a **false equivalence** —
two machines both write `exec.claude`, one is a subscription and one is an API key, and they behave completely differently when quota runs out.
So the capability table splits into three layers, `exec.<name>` + `model.<vendor>.<id>` + `billing.<mode>`,
and model identity must be checkable by `attest` (see [[cortex-loop/references/commands|commands.md]] §Trust and constraint).

**How T1 lands (do this when wiring a new runtime)**: write one line at the top of `bin/cortex-loop-adapters/<new-runtime>.sh`:
`# cortex-loop:requires-env PATH HTTP_PROXY ...`. `env-parity.sh` picks it up automatically. **Neither the engine nor the gate needs a change.**

---

## SHIFT mix: where it must be rigid, where it must be soft

This is not "the code is too rigid, so mix in some AI". **Creativity in the act of judging completion is a disaster.**

| Must be rigid (code · zero LLM) | Must be soft (AI · through an adapter) |
|---|---|
| `tick` computes the window · `submit` books the ledger | **Decompose**: INTENT → task rows (`decompose`) |
| `try-complete` judges artifact / short_test | **Diagnose**: wake only after ≥2 consecutive failures, and ask why it is stuck |
| `reconcile` checks the books · `health` self-checks | **Accept**: quality judgment on exploratory tasks (`judge`) |
| budget window · daily cap · lease CAS | **Escalation copy**: how to tell a person it is stuck |

### ⛔ Asymmetric hard rule

> **AI has veto power only. It has no approval power.**

| AI can | AI cannot |
|-------|--------|
| propose a task (it enters the ledger only after structural acceptance; a row with missing fields is discarded mechanically) | write `status=done` |
| veto output whose quality fails (`judge` REJECT) | turn a task with no artifact green |
| judge whether it should be blocked or retried | bypass `short_test` |

**The acceptor must be a second AI** (not the one that did the work), and its conclusion goes into `evidence`, not into `status`.
The code guarantees it: inside `cmd_try_complete`, AI is called only after the mechanical gates **all pass**, and only the `REJECT` branch can change the result.
Same-origin axiom: [[epiplexity/SKILL|epiplexity]] axiom 1, "the same observer scoring its own output has a blind spot that coincides completely".

### Quota guardrails (4 layers, outside in)

1. `advance_window_min` — minimum gap between two advances of the same task (avalanche protection is the window, **not a lower tick frequency**)
2. `max_advance_per_day` — per-line daily advance cap
3. `health` red → `tick --auto` refuses to run (do not burn money on a bad foundation)
4. AI is woken only at three points (decompose / ≥2 consecutive failures / accept), **not asked every tick**

---

## The completion gate's three checks, plus one no-op gate

| Gate | What it asks | How it fails |
|----|--------|---------|
| **artifact** | the declared output file exists and is **non-empty** | the placeholder `artifact=-` was treated as a path (T6) |
| **short_test** | "did **this specific thing** change", not "will a rerun report an error" (T4) | reusing the scanner's exit code → the task always passes ([[cortex-loop/ERRORS\|E011]]) |
| **propagation gate** | did the artifact **enter history reachable from origin** (T8) | ghost completion: the local machine judged done, and nobody in the swarm can see it |

**One more no-op gate on top** (T9): a task whose criterion **was already met** is not work. It is a no-op — block it before quota is burned,
and land the fourth state `moot` (neither credit nor fault, but **it is a terminal state**).

> Why the fourth state must have its own namespace: no-op gate v1 recognized it and then only `continue`d.
> It had nowhere to land, so it was folded back into `pending` — the plan could therefore never close,
> and `tick`'s "pick up old work first" branch was locked by a plan that had no work left for **6 ticks of zero output** ([[cortex-loop/ERRORS\|E015]] / `34e8450f1`).
> Stuffing it into `result` is also wrong: it pollutes HAAS and the gate-pass rate.

The three gates are DIMENSIONAL applied in the positive direction ([[dimensional-expansion-doctrine|DIMENSIONAL law]]):
"done" is not a boolean. It has at least three orthogonal dimensions: **was it done / did the criterion change / can someone else see it**.

---

## Ledger principle: rejudge, do not erase the ledger

> Three independent implementations all held the same line. Before 2026-07-29 it was scattered in the code and had not been written down.

| Situation | What to do | The wrong move that was **not** taken |
|------|------|----------------|
| After a criterion is tightened or corrected, look at history again | `readjudicate` **rejudges with the current criterion**; the original rejected record stays on the ledger | a "pardon" — wipe the old rejected and reopen it |
| The task criterion was already met (a no-op) | land the fourth state `moot` in an **independent namespace**; it is terminal but does not enter the credit ledger | fold it back to `pending` (the plan can never close · [[cortex-loop/ERRORS\|E015]]), or stuff it into `result` (pollutes HAAS) |
| The orchestrator itself did wrong or did right | `fault` and `credit` **each leave a trace and do not cancel each other** | net accounting (one wrong + one right = nothing happened) |

**Why it is the same line**: all three resist the same temptation — **making history look better**.
The ledger's value comes exactly from the fact that it **cannot be rewritten after the fact**. The reason `why` can answer "was this L3 farmed or earned"
is that the no-op record was not deleted.

**Division of labor with [[one-step-truth|ONE-STEP-TRUTH]]** (they look opposite and are actually orthogonal):
ONE-STEP-TRUTH governs **document body** — keep only the correct terminal state; history belongs to git.
This principle governs **the ledger** — the terminal state may change, but every judgment leaves a trace.
One is a conclusion for a person to read. The other is an evidence chain for a machine to score. They are not the same thing.

**Why this is not a Layer 0 law**: these three are **repeatedly doing it right**, not a repeated violation.
[[latch-doctrine|LATCH]] governs "a violation pattern that reminders do not stop", and this does not clear that bar. The judgment is in
[[cortex-loop/EXPECTATIONS|EXPECTATIONS.md]] §D candidate laws.

---

## Six-law three gates (Mobfish collaboration laws, atomized and planted)

> Source of truth: [[mobfish-six-laws]]. Landing principle: **each law = one field + one mechanical gate, and no new infrastructure**.
> The three gates open inside `cmd_run`, **before money is spent** (`8c28d3775`) — blocking after the spend is the same as not blocking.

| Gate | Law | Mechanical criterion | What it stops |
|----|------|---------|---------|
| **C1** | intent is the bound | the output path must fall inside the task's declared `bounds` allowlist | unauthorized means out of bounds. The placeholder `-` is explicitly exempt (T6) |
| **C2** | trust is the ruler | this node's HAAS score ≥ the task's required `need_trust` | a low-trust node taking a high-risk task |
| **C3** | safety is the floor | an irreversible task requires ≥L4 **and** a human `approved_by` signature | an irreversible action executed automatically |

C2's HAAS weights come from the six laws as written: **intent alignment 30% / operational accuracy 25% / boundary compliance 25% / recovery 20%**,
all counted from actual ref-layer records — **a node cannot self-report**.
A C3 breach takes `STOP → REPORT → WAIT → RECORD`. RECORD lands in `refs/swarm/<swarm>/incident` and **enters the HAAS denominator**.

**The main thread is also a node** (`22d5ccb62` / `ab69450ee`): on the same machine, "the one running tick" and "the one talking to a person" must be scored separately,
so there is an independent node seat `orchestrator-<host>` (`kind=orchestrator`, a human-machine interface, not an executor).
What this closes is the "**I am unconstrained**" hole — the orchestrator must also be bound by the trust mechanism,
which is why `fault` (record one's own breach) and `credit` (record an autonomous completion) exist as a two-way scoring pair.
Same origin as [[steer-doctrine|STEER law]]: the main thread is the decision-maker, and the decision-maker is also in the ledger.

**Swarm-wide trust** = the weighted mean of the nodes **× the bottleneck factor** — not a plain average,
because the harm an L1 node can do does not shrink just because an L5 is standing next to it.

---

## Why the five tools are orthogonal (the GLASSBOX position)

> On 2026-07-29, four hand-rolled command measuring tools failed in a single day (`\|` under `grep -E` is not OR /
> a pipe swallowed the exit code ×2 / `ls` with multiple paths lied about its exit code). Each time **it looked like a result, not a fault**.
> That is exactly the trigger of [[atomize-tools-doctrine|ATOMIZE law]]: **a command that has fooled you once has the highest priority. It has already proved it will fool you again.**

**The difference between pulse and ci is the question, not the frequency**: pulse asks "is it healthy today"; ci asks "**is this still the same thing**" —
a system can **drift while looking perfectly healthy**: metrics all green, but a gate was quietly widened and a goal was quietly lowered.
So besides running tests, ci must **check that the goals in [[brain-network/directions/loop-ops/CHARTER-SWARM\|CHARTER-SWARM]] themselves were not loosened**.

**The GLASSBOX position** ([[glassbox-doctrine]]): dashboard and trace are **one truth that human and machine read together**.
There are not two copies — two copies will fork. `--json` and the human-readable side come from the same collection,
which is why `e5e61a678`, "`--json` emitted illegal JSON", is a defect at the level of **the self-heal chain breaking at the first link**,
not a "small format problem" — the human-readable side showed nothing wrong at the time.

**Why pulse must sit on a clock** ([[latch-doctrine|LATCH law]]): when PULSE was made a rule, the writing said "must run before delivery",
but a rule that **depends on AI remembering** will be bypassed under in-context inertia. One operator sentence, "weren't we supposed to do this on a schedule?", named it —
the third occurrence should build a Hook, not add a third reminder sentence.

The 09:30 ci time was chosen, not filled in at random: the operator can see it in the morning, and **it avoids the 00:00 day boundary and the 02:00 nightly crons**.

---

## Nav

[[cortex-loop/SKILL|SKILL.md]] · [[cortex-loop/references/commands|commands]] · [[cortex-loop/references/swarm|swarm]] · [[cortex-loop/references/contracts|contracts]] · [[cortex-loop/references/operations|operations]] · [[cortex-loop/ERRORS|ERRORS]] · [[cortex-loop/EXPECTATIONS|EXPECTATIONS]]

---

<!-- cortex:map-backlink d-a1444bf512a487ff1b89b25d -->
Related map: [[skills/cortex-loop/MAP|Cortex Loop panorama]]
