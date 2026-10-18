English | [简体中文](JOURNAL.zh-CN.md)

# cortex-loop — build journal

> **Scope**: key events and decision turns of the engine / contracts / swarm
> **Main document**: [[cortex-loop/SKILL|SKILL.md]] · **error log**: [[cortex-loop/ERRORS|ERRORS.md]]
> **Charter report**: [[cortex-loop-intent]]
> **Rule**: record only "turns" and "measured evidence". Process logs do not enter (ONE-STEP-TRUTH)

---

## 2026-07-30 · S0/S1 real closed loop + an S2 joint-link portal shadow pilot

- **S0/S1**: two `map-backlink-gap` batches ran 26 strict discovery→result→world verify→learning lines through launchd `clock-auto`. MAP `48/48 OK`
- **S2**: the joint-link portal did read-only shadow only, 91 comparable cases. The conclusion relative to the inventory baseline is `SUPPORTED`. Authority stays `FORBIDDEN` for automatic promotion
- **Dashboard**: four questions on the first screen. Manual/auto, canary/production, UNKNOWN/0, and cumulative/rolling are separated. It truly shows S0/S1 passed and guardrails UNKNOWN
- **Reflexive fix**: after v3.34 located a lost stash owner, it finally rose to Git commit transaction V4 and removed background stash/reset/bulk add/merge for good. A receipt with no timezone is no longer misjudged as future. The three origin namespaces changed from per-ref fetch to a batch read
- **Verification**: suite `49 PASS / 0 FAIL / 1 SKIP`. H03 is a human cost-benefit candidate and is not disguised as green

---

## 2026-07-28 · From "8 reports, 0 lines of code" to a two-node swarm that passed live

### Starting point: 8 reports, and not one line of runnable code

Before this, the proactivity / autonomous-advance topic had already accumulated **8 reports** (listed in full in [[cortex-loop-intent]] §7):

`proactive-intent-master-brief` · `proactive-intent-loop-cortex-deliberation` ·
`nova-proactive-listen-spec` · `direction-cron-proactive-archaeology` ·
`proactive-intent-loop-codex-review` · `nova-60s-proactive-cortex-fusion` ·
`recap-35e58e01-agent-proactivity-extract` · `external-nova-agent-import-analysis`

The four-layer model, the state machine, the matrix, and the Codex cross-review were all there — **nothing was running**.
Another fact seen firsthand the same day nailed it: the previous generation of nine `*-advance` lines **evaporated across the board, live=0**, dead for months, with **no file, no commit, and no person noticing**. The cause of death was not a wrong design. It lived in OpenClaw's store and did not live in git.

Conclusion: **a heartbeat cannot be a parasite.**

### The day's 8 commits (`git log --oneline`, actually checked)

| # | sha | Time | Turn |
|---|-----|------|------|
| 1 | `93ae328c5` | 23:06 | **heartbeat engine + swappable muscle adapter** — the engine is zero LLM; all three AI mount points go through an adapter; the asymmetric hard rule was set |
| 2 | `8d49d74b2` | — | **schedule declaration CLOCK + the loop-ops pilot line's three contracts** — the pilot line was "the loop repairs its own foundation", not a market-research line |
| 3 | `ea254e217` | — | **launchd main clock + the front-door report** — the clock is not a parasite; the 8 old reports were demoted to satellites |
| 4 | `f63bd4430` | 23:12 | **health separates "the work failed" from "the report failed"** + pilot-line T1 delivered (see ERRORS [[cortex-loop/ERRORS\|E005]]) |
| 5 | `e007fc7ec` | 23:20 | **sleep awareness** + after the T2 credential-chain fix, moved to pending to wait for a natural verification (E006 / E007) |
| 6 | `f227f2868` | 23:32 | **swarm** — self-perception + swarm perception + owner sharding + offline takeover |
| 7 | `51d317f9a` | 23:42 | **the swarm bus moved onto the git ref layer** — a distributed CAS lease lock with zero external dependency (E004 was stopped here) |
| 8 | `62b597a8b` | 23:44 | **fix**: `list_refs` format-string escape → silent fallback to the file snapshot (E003) |

---

## Key decision turns (4)

### 1. The pilot line does not push the business. It pushes the loop itself first

The pilot line could have been something that "looks valuable", such as market research. What was chosen is **`loop-ops`: the loop repairs its own scheduling base**.

Reason (the original words of [[brain-network/directions/loop-ops/INTENT|INTENT]]): the heartbeat currently hangs on a base that **itself has a 31% error rate**. Running automatic advance on that foundation produces **automated fake progress**.
And this is the strongest self-proof — **if the loop cannot even push its own operations, it certainly cannot push market research**.

### 2. Completion judgment must be able to go red before it deserves to go green

T3 is a **counter-test sentinel**: its output file (`cortex-loop-never-exists.md`) should never exist.
If it turns green, someone widened the completion gate.

Seven red→green counter-proofs (the full table is [[cortex-loop-intent]] §5). The three that matter most:
- `try-complete --task T3` → `FAIL T3: artifact missing` exit=1 (the gate can go red)
- `try-complete --task T0` → `PASS T0 → done` exit=0 (the gate can turn green)
- `reconcile` (before launchd was installed) → `driver not found → split DRIFT` DRIFT=1; after load → `running → OK` DRIFT=0

### 3. The operator decided "no Redis; plain git solves it naturally and completely"

The swarm bus was going to pull in an external dependency for a distributed lock. The operator rejected that outright.

The answer: **`git push` updating a remote ref is itself an atomic compare-and-swap**. Two nodes build a commit from the same parent and push at the same time. The server lets only one fast-forward succeed. The other is necessarily `[rejected] non-fast-forward` — semantically equivalent to Redis SETNX, **zero external services**.

Measured (real concurrency, not a simulation; see the `51d317f9a` commit message):
```
shared parent b568f07f4 → nodeA 1f3579ca8 push succeeded / nodeB 824a2e238 [rejected] non-fast-forward
final holder=nodeA, deterministic
```

Companion decision: **the whole path is git plumbing, and the worktree is not touched**. The worker's live state was 267 uncommitted files and a broken auto-sync. Any pull/rebase/checkout is blocked by the dirty tree → the swarm goes blind with it. The ref layer bypasses the worktree completely.

### 4. Acceptance of "fixed" must be a natural run, not an artificial trigger

After T2 (fix `mercury-daily-ops-report`) had its root cause found and handled, the daily was **not** force-run at 23:20 to make it green.
Instead: the task moved to `pending`, waited for the natural 0729-0800 run, and the loop checked itself in the 09:00 window.

This extends the same principle as the INTENT `Anti` section, "deleting a job and calling it fixed / editing short_test to make it green" — **one success triggered in order to turn green is not fixed**.

---

## Two-node swarm, measured (closing evidence of the day)

`/tmp/spotlight/cortex-loop.log`, read firsthand:

```
23:38 | sync nodes=1 beat=True     ← E003 not yet fixed: the ref layer read empty, silently fell back to the local file snapshot, and could see only itself
23:43 | sync nodes=2 beat=True     ← after the 62b597a8b fix
23:44 | sync nodes=2 beat=True
```

`git for-each-ref refs/swarm` really has two: `refs/swarm/beat/laptop` · `refs/swarm/beat/worker`.

**From 8 reports and 0 lines of code → an engine with 12 subcommands + four contracts past the gate + launchd loaded + 7 red→green live checks + a two-node swarm at nodes=2, finished the same day.**

---

## The books left that day (unfinished, not prettified)

| Item | State | Note |
|----|------|------|
| `loop-ops` T2 | `pending` fails=1 | GLM removed from the chain + primary changed to MiniMax, done; waiting for the natural 0729-0800 run to verify |
| `loop-ops` T3 | `pending` fails=1 | counter-test sentinel; **it is supposed to stay red forever**. It is not a todo |
| `CLOCK.loop-ops.executor` | `human` | safe default. Change to `claude` only after it runs smoothly |
| Pilot-line count | 1 line | only loop-ops. No business line is connected yet |

---

## 2026-07-29 · From "it can run" to "it can run correctly when nobody is watching"

> That day the engine grew from **1093 lines to 4125 lines** (nearly 4×), subcommands 12 → 31, tools 0 → 5, Layer 0 laws +5.
> But the real turn was not how many features were added. It was **discovering that "it can run" and "it runs correctly" are two things** —
> at the 07-28 close the loop could already advance itself. The question 07-29 spent the whole day answering was:
> **of the things it advanced, how many were real?**

---

### 00:00–01:00 · Hit the moment it went live: three engine-level defects

`2eda7fa95`, one commit, fixed three: the heartbeat was strangled by health / `reconcile` reported "cannot detect" as "broken" / internal definitions were not self-consistent.

The second was especially typical — it is **the first appearance of the E013 dimensional collapse**, only it had no name yet:
"**cannot detect it**" and "**detected that it is broken**" were flattened into the same return value, so a machine with no systemd was reported as "the driver is broken".

Two things built in the same stretch are still in use:
- `9422cca9b` **a 24-case suite + mutation tests** — not only "did it pass", but **deliberately break the code and verify the test really goes red**.
  This rule saved us later: the 10:36 negative test caught "**the fix I wrote myself is dead**" (`991016f78`).
- `6e5944883` **external API + MCP** — the same six-law gate inside and outside. Not two entrances with two rule sets.

### 01:00–02:30 · From "being assigned work" to "finding work itself"

`6192092af` `discover` finds work on its own. Right after, `8f0b45897` **changed the find-work strategy from "pick the most valuable" to "fill the low spots"**.

The reason was not efficiency. **The objective function was wrong**: maximizing makes the loop pounce on the same hot spot again and again,
and what a swarm wants is **lower variance** — the weakest leg should not stay lame. This is the same idea as the later "swarm-wide trust = weighted mean **× bottleneck factor**".

`b1189b725` `tick --auto` truly closed the loop (discover → auto-publish → auto-claim and execute). **The closed loop had an incident the day it closed**:

| Time | commit | What the live machine caught |
|------|--------|-------------|
| 02:25 | `bac0c69b7` | the placeholder `artifact='-'` was treated as a **real path** by C1 and the mechanical gate |
| 02:52 | `314d641ef` | **false completion**: `short_test` reused the scanner exit code + the verifier failed open, and both layers fell at once (E011 → T3/T4) |

> **The value of the first fully automatic closed-loop run is not that it ran through. It is that it exposed a false completion immediately.**
> Ten thousand manual runs would not have found it — because the person running it by hand would have understood `-` as a placeholder in passing.

### 03:00–08:00 · A 4-hour unattended window: the most expensive stretch, and the most worth it

Nobody was watching this stretch. On waking:

1. `2ebcf66d2` **`revive` never triggered automatically** — self-heal was written and not wired. The loop was blindly retrying the same bad executor.
2. `724117356` **the real cause of 4 hours of 403 across the line was launchd missing the proxy variables, not the lock screen**.
   The earlier hypothesis ("caused by the lock screen") was wrong. The commit message explicitly wrote "**correcting a wrong hypothesis**".
   → this directly produced **hard rule T2, cross-environment parity** (`c858a9ef9` set 6 pinned hard rules and E012 at the same time).

**Why these 4 hours were worth it**: everything looks normal in an interactive shell. The difference is exposed only **unattended**.
A defect of this class, environment inconsistency, **appears only when nobody is there to patch it by hand**.

A large parallel batch of `fix(frontmatter)` / `fix(data-recovery)` / `fix(conflict-markers)` in the same period was not this domain's work.
It was gaps **the loop scanned out itself** (633 broken mossriver YAML files, 50+ AI outputs lost to a fake merge) —
the first time "find work on its own" really produced something a person did not know about.

### 08:00–09:10 · PULSE onto a clock + the propagation gate

`bb07bba02` **PULSE changed from "depends on AI remembering to run it" to "the machine runs it itself"**.

The trigger was one operator sentence: "**weren't we supposed to do this on a schedule?**".
This is a textbook scene of [[latch-doctrine|LATCH law]]: the rule is written "must run before delivery", but **a rule that depends on AI remembering will be bypassed under in-context inertia**.
The third occurrence should build a Hook, not add a third reminder sentence.

`54b1dd836` **added the propagation gate** — caught ghost completion `real1/R2`: the worker judged done, and **the output had never entered git history**.
A file on the local disk is not completion. A swarm sees each other's work through git.

> An hour later `28f7d5d41` slapped it: **propagation gate v1 was a fake gate**.
> v1 only checked that `git log -1 -- <artifact>` was non-empty — but "the file has entered git in its history" and "**this change entered git**" are two different things.
> A live machine proved on the spot that v1 let through "it has history, and the edit was not committed". → v2 checks origin reachability. **This later rose to T8.**

### 10:30–11:30 · The fail-open family cleared, and E013 was named

`22b23217c` **three fail-open silent blindnesses**. The commit message's own words: "**the absurdity of the blinder it is, the more work it can do, is fully plugged**".

This was the day's most important jump in abstraction — before, each one was fixed as an isolated bug. This time it was finally seen as **the same root pattern**:
> when a judgment cannot be made, the code tends to **collapse toward "pass"**, because collapsing toward pass does not raise an error.
> So **the worse a node's ability to observe, the higher its pass rate**.

`9415010f2` made it the **[[dimensional-expansion-doctrine|high-dimension expansion hard rule]]**, and did two things beyond "fix the bug":
- **widen**: grep the whole domain for the same class, and make each site three-state (`02c3edacb` is site 5)
- **mechanical residue**: the `dimensional-collapse-scan.sh` scanner was wired into the suite — relying on memory guarantees a relapse

**The criterion is not "can it be enumerated exhaustively". It is "if these two states are merged, will someone therefore take the wrong next action".**
Yes → expand. No → merge. Not infinite enumeration.

### 12:00–14:00 · Three laws took shape + the swarm charter

| Time | commit | What was set | The pit that triggered it |
|------|--------|---------|-----------|
| 12:52 | `a923e1072` | [[steer-doctrine\|STEER law]] | **6 rotten conclusions inside one session** — standing on the previous round's conclusion and pushing further, all of it wrong |
| 13:39 | `f32f0b96f` | [[atomize-tools-doctrine\|ATOMIZE law]] + `cortex-probe.sh` | **four hand-rolled command measuring tools failed in one day**, and each time it looked like a result rather than a fault |
| 13:28 | `02d53a821` | [[brain-network/directions/loop-ops/CHARTER-SWARM\|CHARTER-SWARM]] | goals scattered everywhere → ci had nothing to check "was it loosened" against |

ATOMIZE's four failures are worth a note of their own, because **none of them raised an error**:
`\|` inside `grep -E` is not OR (it silently matches nothing) · a pipe swallowed the exit code ×2 · `ls` with multiple paths lied about its exit code.
So the criterion is not "is it a bother". It is "**has this command fooled us before**" — **one that has fooled us has the highest priority. It has already proved it will fool us again**.

`d747af8da` + `742ba002c` filled in the six-law **negative tests** for C1/C2/C3 + V1/V2/V3.
The motive for writing negative tests was to answer a concrete challenge: "**is it really mechanical, or does the document only say it is mechanical**".

### 14:00–15:30 · The glass-box trio + an error that had to be written down

`6d16a350c` `cortex-trace.sh` (transparent case) → `e78d6fdd3` `cortex-dashboard.sh` (one-screen overview) → `e002c7438` `cortex-ci.sh` (daily constraint).

The three plus probe/pulse make five tools, **orthogonal and not overlapping**. The split between ci and pulse was thought through that day:
> **a system can drift while looking perfectly healthy** — metrics all green, but a gate was quietly widened and a goal was quietly lowered.
> So pulse asks "is it healthy today", ci asks "**is this still the same thing**", and ci exit code **2 = a goal was loosened**, which is more serious than a test failure.

`e5e61a678` **dashboard `--json` emitted illegal JSON**.
This bug is recorded on its own because it is not a format problem: **the human-readable side showed nothing wrong, and the machine-readable side broke outright** —
the first link of the self-heal chain broke here, and nobody would notice. This is the opposite of [[glassbox-doctrine|GLASSBOX law]], "human and machine read **the same** truth":
as long as the two sides come from different sources, **a fork is inevitable, and the machine side always rots first**.

Two self-corrections in the same stretch, recorded as they were:
- the `e78d6fdd3` commit message wrote "**withdrawing a fix of mine that rested on a wrong premise**"
- `7f3f05678` review found that the 13:34 live run **ran the pre-fix code** (proved by a printed string) —
  whether the conclusion was right is a separate question. **The premise itself was false**, and the whole inference is void

### 15:00–16:00 · The "I am unconstrained" hole was closed

`22d5ccb62` → `ab69450ee` **the main thread was promoted to a full peer node**.

The cause was an uncomfortable question asked of itself: the loop computes trust and deducts breach points for every automatic node,
**but the one giving the orders (me) is in no ledger**. That equals "whoever sets the rules is exempt".

The solution is to make the main thread an independent node `orchestrator-<host>` (`kind=orchestrator`, a human-machine interface, not an executor),
with three subcommands `checkin` / `credit` / `fault` — **a penalty requires a reward, or nobody dares to act autonomously**.
`c739cc3a1` immediately fixed "the breach was deducted from the wrong node", and **a mistaken record is exempt from deletion** — a wrong record is still a record. Delete it and there is no review.

**Swarm-wide trust = weighted mean × bottleneck factor**, not an average and done:
the harm an L1 node can do does not shrink because an L5 is standing next to it.

`216a194d0` `readjudicate`, a review of wrong judgments. Gate-pass rate **20% → 75%**.
The point is that it is "**rejudge with the current criterion**", not a pardon — after the criterion is corrected, what a rotten criterion wrongly killed has to be given back,
but **the criterion itself must not be relaxed to look better** (that is what ci exit code 2 exists to catch).

### 16:00–20:00 · Was the trust farmed or earned

`0f167ca4d` **E014 no-op score farming**: a task whose criterion **was already met**, rerun, still counted as passed.
17 let through at once. Afterward **7 were no-ops**.

The root cause was not a wrongly written criterion. **The wrong strictness was used**:
> at trust **L1**, **sampling** strictness was used.

`d121dc721` added the tiers (garment-factory inspection logic): a new supplier is fully inspected; an established supplier is sampled.

| Trust | Intensity | What is checked |
|------|------|--------|
| low | **full check** | not only "the criterion passes now", but also "**did the world change when this finished**" |
| mid | sample | still passes AI acceptance, but timestamps are not checked item by item |
| L4/L5 | exempt | if the mechanical gate passed, accept it, and save the acceptance call (acceptance itself burns a model call) |

`34e8450f1` + `6a3bd6d3c` **the cause chain of E015's 59% idle rate**, the longest cause chain of the day:

```
the no-op gate recognized a fourth state → but only continued, and gave it nowhere to land
  → moot was folded back into pending → the plan could never close
  → tick's "pick up old work first" branch was locked by a plan that had long had no work
  → 6 ticks of zero output
  + claim and execute each counted the other as load → the node showed full, and output was actually zero
```

The fix gives the fourth state **its own namespace**, `refs/swarm/<swarm>/moot`.
Why not stuff it into `result`: **a no-op should neither add points nor remove them**. Stuffing it in pollutes HAAS and the gate-pass rate.
— This later rose to **T9**.

`bin/cortex-loop idle` was born at the same time, because discussing the idle rate showed **the denominator itself was wrong**:
wall clock should have run 96 ticks, but the ticks while the laptop lid was closed **never ran**. Using wall clock as the denominator makes the idle rate fiction.
Four-state definition: produced / terminal recorded / truly idle / **cannot tell** (an independent third state; it does not collapse toward either side).

---

## Three meta-patterns that kept reappearing (what most needed remembering that day)

### 1. Every new gate is slapped by its own live check on day one

Propagation gate v1 (set at 9:00 → falsified at 10:52) · PULSE (set at 8:56 → two defects it exposed on day one were fixed at 9:09) ·
`991016f78`, "a negative test caught my own fix being dead".

**Corollary**: setting the gate is not completion. **The gate counts only after its own test has gone red once.**
So every negative test in the suite must pass a destructive check — a test that does not prove "it really goes red" is itself a fake gate.

### 2. A criterion's strictness must change with trust. A fixed strictness pleases neither end

Fixed strict = a high-trust node burns acceptance calls for nothing. Fixed loose = a low-trust node farms score with no-ops (E014 measured 7/17).
This is the same principle as "AI has veto power and no approval power", on two layers: **asymmetry** is the essence. Symmetry is laziness.

### 3. "I am not in the ledger" is the easiest hole to miss

Making rules for other people is natural. Putting yourself inside the same rules takes a deliberate thought.
The `orchestrator-*` node + `fault` / `credit` were added that day, but what they expose is a more general blind spot:
**the meta-governance layer exempts itself by default.** — Same origin as [[epiplexity]] axiom 1: the same observer scoring its own output has a blind spot that coincides completely.

---

## The books left that day (unfinished, not prettified)

| Item | State | Note |
|----|------|------|
| suite H03 dimensional-collapse scan | **SKIP** | 1 candidate waiting for a person to judge "is the cost-benefit worth expanding"; neither red nor green |
| `loop-ops` T2 | not confirmed fixed | round 4 confirmed it is an **openclaw CLI structural block**, not a problem in mercury itself (`f176a2594`) |
| gate-pass rate | 20% → 75% (after readjudicate) | cumulative track record only; the target is not approved, and it is not a completion gate |
| idle rate | 59% → root cause fixed, **the effect waits for the next full unattended window to verify** | fixed at 19:40; that day had no window long enough to re-check |
| self-inflicted damage | recorded as it was (`e8efd0a34`) | `ANTHROPIC_API_KEY` polluted the adapter + an orphan claim I caused myself |

---

## 2026-07-30 · Independent audit after the S0/S1/S2 closed loop

- two `clock-auto` plan batches formed 26 complete discovery/result/learning lineages. MAP 48/48
- the S2 joint-link portal read-only shadow replay finished, and automatic promotion is still forbidden
- the first Dashboard round could show lineage, but it miswrote "window not approved" as "no cohort", and inflated receipt-field binding into VERIFIED
- after the independent audit it was split into: `BASELINE` / `UNMEASURED`, legacy `unclassified` debt,
  `receipt_binding` / `origin_reachability` / `verification_replay`
- a second independent re-check punched through once more with "a reachable commit + an artifact path that does not exist", and it was finally tightened to
  **an origin-head reachable commit × a safe repo-relative path × the blob exists**, all three at once
- the Dashboard's local origin path has a `<15s` budget. The current fixture passes live. JSON invalid reasons keep only a 5-item summary

Mechanical gate: `python3 bin/cortex-loop-tests/fixtures/negtest-dashboard-json.py`

---

## 2026-07-31 · The execution engine upgraded from "it can reply" to "it really does the work"

### 15:28 · Repair Controller, MiniMax, and the metrics contract finally closed

- the daily cumulative budget was upgraded to a Git ref CAS; a named task gained the three checks clean/commit/origin.
- failure context moved from `/tmp` to a bounded, redacted, atomic persistent ledger, and can still enter repair after a restart.
- raw MiniMax/GLM was demoted from `exec.*` to `text.*`; `cheap` uses Claude Code + CC Switch
  MiniMax as the only cheap workspace executor.
- Mercury really ran MiniMax successfully. T2 and T18 completed. Three trust refs are on origin.
- any HIVE PENDING is fail-closed. The live WeCom inline webhook changed to a shared resolver.
- the G1 retry duplicate and the G2 `_settled` pollution were fixed. G1 7 days and G2 24 hours were approved, both at 90%.
  Current G1 69.2% is honestly red. G2 100% is green.
- fresh suite `49/0/1`. Live autonomy `10 PASS / 0 FAIL / 0 UNKNOWN`.

### 13:57 · The mercury old-model override came to light

`openclaw cron get` proved `mercury-daily-ops-report` still had an independent per-job override:
after a Gemini timeout it fell back to a dead GLM 401, 13 errors accumulated. Switching defaults and the Cortex adapter
to MiniMax does not pierce a cron override. The official CLI was used to change it to
`minimax/MiniMax-M2.7` and clear the fallback. A real run would send the operations daily to Telegram.
Acceptance waits for explicit outbound approval. It is not judged done before it has run.

- a live machine confirmed `cheap` had originally been only a raw MiniMax/GLM text completion. Tasks never got workspace tools.
- it was changed to a MiniMax-backed Claude Code tool layer, and a real execution was proved with `/tmp` Write+Read.
- T21, T15, T19, and T22 have passed their own short_test and the completion gate. Launchd's first tick really claimed T18.
- added a single-instance tick, a worker PID lock, a short failure backoff, orphan-receipt recovery, and tamper protection for the task contract / short_test.
- the Dashboard parses both TASKS files live and shows per-line running, fails, and launchd runs/last-exit/heartbeat.
- added the atomic commands task-add/list/show/retry/run. The task lifecycle no longer depends on hand-rolled Markdown.
- the production-permission full suite: 49 PASS / 0 FAIL / 1 SKIP (H03 is a human cost-benefit candidate).

Root cause and evidence: `reports/2026-07-31/cortex-loop/cortex-loop-execution-engine-closure.md`.

## 2026-08-01 · The lock domain changed from global serialization to minimum-resource exclusion

- deleted the whole-lifetime tick lock. Different tasks run concurrently. The same task is deduped by a task flock.
- TASKS multi-field atomic write + status CAS. task-add's private candidate passes the gate before it is published.
- cheap changed to 3 Worker slots + a MiniMax account lease. Cooldown state gained flock/fsync/replace.
- the Git transaction gained live-owner/stale/index/merge judgment. Candidate scan and deploy moved out of the lock.
  pre-commit forbids a bare commit from creating its own lock.
- H23 and the Git V4 special all green. Dashboard H09 no-origin fixture no longer leaks the real repo.

### 23:13–23:45 · The execution plane upgraded to low-disk distributed delivery

- the review proved that shrinking the Git transaction was not enough: control refs were already distributed, and Workers still co-wrote the root worktree/index.
- a measured sparse linked worktree added only 6.4M, while the shared object store is about 3.4G. On that basis the plan "copy a full worktree per task" was rejected.
- added a workspace broker, a candidate publisher, a blobless integrator, and a delivery-plane inspector. Crash, stale lock, low disk, out of bounds, a read-only dependency, a red short_test, and a dual-write CAS all have negative tests.
- completion semantics split into candidate-visible and master-landed. The former enters only `integration_pending`. Only the latter may be done.
- the Dashboard added a delivery pipeline, showing the isolation cabin, Candidate, integration receipt, landed, retryable, and anomalies separately.
- the EXPECTATIONS reader fixed a `**met**` misjudgment and the silent drop of short rows: the real total recovered from a wrong 8 to 20 (met 12 / gap 4 / unknown 4).

## 2026-08-02 · Dashboard Ctrl-C batch mis-kill rooted out

- the two GUI cascades were not a memory leak: the system log explicitly records an old `pkill` terminating 63 and 42 processes.
- PATH was hijacked by the `proctools/0.4pre1` shadow tool in `/usr/local/bin`. On macOS 26.3 it ignores `-P`.
- Dashboard watch deleted the background collector, the 1Hz full redraw, and the parent-PID hunt, and changed to a single foreground synchronous snapshot. The spare screen only displays in place, and restores the original terminal state on exit.
- shadow pgrep/pkill were moved into a recoverable isolation directory. Running scripts uniformly use explicit `/usr/bin/pgrep`.
- H33 verifies SIGINT exits 130 with no residual process group. H34 stops the shadow binary and a bare process-query call from regressing.

### 06:54–07:11 · Squash/replay settlement semantics closed

- the integrator replays several source commits into one canonical commit. The old completion gate accepted only a source commit that had become an ancestor of master, so content already live stayed in permanent settling.
- a unified settlement check was added: the local path must exist, be non-empty, be tracked, be clean, and be bound to the source commit, then the exact blob OID of the source commit and the canonical tip are compared.
- when the source OID is unreachable but every artifact/check path blob matches exactly, landing is proved by `content-equivalent`. Any different path still refuses completion.
- `task-show --settlement` and the completion gate share the same helper. T64–T67 each entered done from settling through the atomic completion gate.
- H35 covers the squash/replay positive case, canonical content mismatch, a local dirty edit, a check not landed, and a read-only query with zero side effect. The full suite is 62 PASS / 0 FAIL.
- the integrator's first re-check correctly refused a forked content conflict. `candidate compose` was then added as an atomic entrance, projecting the exact write set onto the latest canonical with a temporary index, so hand-rolling and a shared-repo merge are avoided.

## 2026-08-02 · Sparse attempt failure rollback and old-cabin closeout

- after a V4 hook failure, three old T66 attempts each swelled from 1 dirty file to about 29,000 deletions. The cause was a tree rollback dropping `skip-worktree` metadata.
- V4 changed to a raw index-file snapshot. A skip-worktree regression was added and the full special passed.
- three different artifacts were archived at their original SHA-256. After the sparse rules were reapplied, all were clean, then safely released by the workspace broker. Branch and content were both kept.

---

## 2026-08-16 · Logical session isolation must not degrade into a full worktree

- during the ROSACE/ROSEUM knowledge handoff, the project's default full-worktree entrance was reused by mistake. The error has nothing to do with free disk. The root cause was mistaking the logical isolation of Session/Agent/Topic for filesystem isolation.
- E029 was written into `ERRORS.md`, and the hard rule was synced to Layer0 and the long HIVE guide: a Codex session that shares OB1 must be `environment=local`. When isolation is needed and the write set is known, use the sparse broker. A full worktree is reserved for the exception where a concurrent code conflict or a high-risk exploration is real.
- knowledge handoff, a read-only audit, brand planning, a data read, and a cross-runtime migration must never copy the whole repo because "there is enough disk". Error entries, rules, reports, and memory land in the main OB1 source of truth.

---

## Nav

| Document | Relation |
|------|------|
| [[cortex-loop/SKILL\|SKILL.md]] | main document: 9 pinned hard rules / five tools / three clocks / 31 subcommands / the contract system |
| [[cortex-loop/ERRORS\|ERRORS.md]] | E001–E029 + the capstone lesson "silent degradation is more dangerous than an error" |
| [[cortex-loop-intent]] | heartbeat charter (canonical reading entry) |
| [[brain-network/directions/loop-ops/CHARTER-SWARM\|CHARTER-SWARM]] | swarm charter: goals G1–G6 / scope |
| [[cortex-loop-cron-error-triage]] | pilot-line T1 output: 10 error jobs, five root-cause classes |
| [[CLOCK]] | schedule declaration |
| [[knowledge-contract-registry]] | §4.12 four-file contract · §4.12a ref-layer protocol |
| [[steer-doctrine]] · [[pulse-doctrine]] · [[dimensional-expansion-doctrine]] · [[atomize-tools-doctrine]] · [[glassbox-doctrine]] | five Layer 0 laws born that day from pitfalls in this domain |

---

*Established: 2026-07-28 · continued: 2026-07-29*

---

<!-- cortex:map-backlink d-112009e679396742854f3a6a -->
Related map: [[skills/cortex-loop/MAP|Cortex Loop panorama]]

## 2026-08-27 · CORTEX Harness normalization cleanup: identity first, then disposition

- this round turned 5 crossing audit viewpoints into 5 mutually exclusive handling batches. Each batch owns only its own path set. The final disposition is still gathered by one list.
- the live snapshot changes with parallel workers, so 135/140/142 can only be snapshots with a time. They cannot be a fixed denominator. The final list must freeze `origin/main`, the worktree registry, common-dir, remote, dirty/lock/process, and a unique disposition.
- `${CORTEX_WORKSPACE_ROOT}/` is a mixed path: distinguish Cortex Harness from OB1 by Git common-dir. Do not delete by directory name. The OB1 main repo and its mirrors stay put.
- 7 candidates hit `modify/delete` or a missing dependency on canonical `origin/main`. Source evidence was kept and a forced integration was refused. 10 temporary directories that were clearly unregistered, unlocked, and had no process were moved into recoverable Trash.
- further cleanup found one cross-repo registration: the target directory's `.git` pointed at an independent temporary common-dir, and canonical `git worktree remove` refused because ownership did not match. After re-checking that it was clean, had no process, and was 6.4 MB, it was moved into recoverable Trash, then the stale canonical registration was pruned. 4 confirmed-duplicate local branches were deleted at the same time. Remote branches were kept. The current canonical registry is 127, with 18 dirty and 1 locked/initializing. The remaining clean trees were not automatically treated as garbage.

## 2026-08-27 · The second audit round was made into a tool

- the first round's useful experience was turned into an atomic contract: an on-the-spot snapshot, Git identity, state on separate axes, a value review, a recoverable reference, and drift invalidation. The second round does not reuse old numbers or the old list directly.
- the tool boundary is fixed as a read-only manifest: it can generate a unique disposition and `STALE_SNAPSHOT`, and it does not execute migration, deletion, prune, or authorization. Later rounds only consume that manifest, and an independent execution gate decides the action.
- the experience was synced into the dispatch/cortex-loop error log and MEMORY. Canonical Cortex Harness already has a legacy repository audit tool. Later work is only a minimum increment. A synonymous tool is not built again.

## 2026-08-20 · Fixed formation before concurrency: a Codex child seat crossed the bound

This round exposed that "there is a concurrency slot" does not imply "a Codex child seat may be added". CORTEX's formation contract must come before scheduling: 4+3+2 is fixed as Grok×2, Claude×2, MiniMax×3, Codex Luna×1, DeepSeek×1. An Eval negative case and a Layer-0 prohibition were added.
