English | [简体中文](commands.zh-CN.md)

# cortex-loop subcommand catalog (by family)

> **When to read this**: you need a subcommand and have forgotten what it does, what arguments it takes, or when to use it;
> or you want to know "what else is in this family that I have not used".
> **Parent**: [[cortex-loop/SKILL|SKILL.md]] §subcommand families (that page has only the family-level table)
> **Source of truth**: `bin/cortex-loop` (engine)

Exit codes are uniform: `0` = ok / `1` = red or failed / `2` = usage error.
**Only the "AI mount points" family burns quota.** Everything else is zero-LLM plain code.

---

## Heartbeat and ledger (zero LLM)

| Subcommand | What it does | When to use it |
|--------|--------|-----------|
| `tick [--auto]` | scans every enabled line and computes the tasks that have reached their window; `--auto` is what actually advances one round | launchd knocks every 900s. A human run without `--auto` only shows what is due |
| `next --line X [--task T] [--claim]` | renders the next **self-contained prompt** to stdout; `--claim` also takes the slot as `running` | you want to execute one round by hand, or see how the loop would dispatch |
| `submit --line X --task T [--result F] [--window-min N]` | takes the execution result → writes JOURNAL + pushes the window; **never writes done** | backfill after a hand-run round |
| `try-complete --line X --task T [--judge]` | **independent completion gate**: artifact + `short_test` pass → then land/origin; when propagation is temporarily unavailable it writes **`settling`** (execution is already green) and does not send already-green work back to "not done"; it is **`done`** only when origin is reachable | the only command that can write `done`. `settling` is landed-only by the next tick. `--judge` adds an AI veto |
| `status` | human-readable overview: each line's enabled / executor / counts by state | you want the whole picture in one glance |
| `idle [--date D] [--json]` | **four-state census in tick units**: produced / terminal recorded / truly idle / **cannot tell**. The denominator contains only ticks that actually ran | when someone asks "what is the idle rate". **Do not use wall clock as the denominator** — the ticks while a laptop lid was closed never ran |
| `task-list --line X [--status S] [--json]` | atomically queries one line's tasks; no more grep/awk hand-rolled tables | Dashboard or an Agent needs to list the queue or filter by status |
| `task-show --line X --task T [--json] [--settlement]` | fetches one task exactly; human-readable by default; `--json` emits `cortex-loop/task-show-v1`; `--settlement` is a read-only explanation of the artifact→commit→origin→canonical exact-blob binding, and missing evidence is explicitly `UNKNOWN`; after an integrator squash/replay, landing is proved by `content-equivalent` and is not mis-bound to commit ancestry | troubleshooting, audit, reading the contract before dispatch, or finding out why a task is stuck in settling; do not hand-roll `git log/ref` into a judgment again |
| `task-add --line X ...` | generates a task row from the ledger's real header; missing a positive or negative criterion is refused, and a failed contract gate rolls back automatically | adding a task; hand-stitching Markdown columns is forbidden |
| `task-retry --line X --task T --reason R [--reset-fails]` | atomically requeues a failed task into the current window; done/blocked/human-gate are not quietly reopened | retry immediately after the root cause is fixed |
| `task-hold --line X --task T --status blocked\|waiting_external --reason R` | atomically holds and stops automatic retry | waiting for external authorization, or a confirmed technical block |
| `task-resume --line X --task T --reason R` | atomically clears blocked/waiting_external, keeps the failure history, and returns to pending | the blocking condition is resolved |
| `task-reopen --line X --task T --reason R` | undoes one false completion, clears evidence, increments fails, and atomically returns to pending | the short test was misleading, or the completion claim was overturned by new evidence |
| `task-run --line X --task T` | executes one task exactly, still through claim → tool adapter → submit → completion gate | an end-to-end smoke, or running only a named task; it burns model quota |

## Self-check and reconcile (zero LLM)

| Subcommand | What it does | When to use it |
|--------|--------|-----------|
| `health` | driver self-check: cron real-execution failure rate >15% → RED (exit code 1) | runs automatically before every `tick --auto`; also run it by hand when you suspect the foundation is bad |
| `reconcile` | CLOCK **declaration** vs launchd/cron **reality** → emits DRIFT | "it says deployed, but is it really running?"; required after a CLOCK edit |
| `dashboard` | the engine's built-in ledger overview (complements the one-screen overview in `bin/cortex-dashboard.sh`) | you only want the ledger layer, not the whole system |
| `why [--node N]` | **why trust rose or fell**: traces every point added or removed, and identifies no-op score farming | someone asks "why is this node L3"; you suspect the score was farmed |
| `value` | mechanical check of the V1/V2/V3 value laws plus leverage (the value side of the six laws) | "what value did this thing actually produce" |

## Swarm coordination (multi-node · zero LLM)

| Subcommand | What it does | When to use it |
|--------|--------|-----------|
| `swarm` | refreshes this node's profile and prints the swarm liveness table (including lines nobody has claimed) | you want to know which machine is online and which line has no owner |
| `sync` | sends and receives the heartbeat on the ref layer (`refs/swarm/<swarm>/beat/<node>`); **does not touch the worktree** | every machine runs it on a schedule; a dirty tree or a broken auto-sync cannot stop it |
| `lease --line X [--ttl-min N]` | takes the line's scheduler lease (a git ref CAS atomic lock) | checking the lock by hand; `tick --auto` competes internally with a short lease; a worker lifetime is not held by this lock |
| `caps` | the swarm-wide capability matrix plus a **single-point capability alert** (a capability only one machine has is a single point of failure) | "if this machine drops, which leg goes lame" |
| `checkin [--out]` | **the main thread joins or leaves the swarm** — a heartbeat on equal footing with the automatic nodes | join at the start of a session that will produce output; `--out` when it ends |

## Decentralized dispatch (plan-claim-result · zero LLM)

> **No leader, no election, no quorum.** The git server provides only storage plus atomic CAS on refs.
> CLOCK.owner provides only an affinity hint. A short scheduler lease plus a task-level claim decides "who schedules right now". This family decides "how one plan is split, claimed autonomously by many machines, and gathered".

| Subcommand | What it does | When to use it |
|--------|--------|-----------|
| `discover [--publish]` | **find work on its own**: scan mechanically checkable gaps → candidate tasks; `--publish` is what actually publishes | the loop finds its own work when it has none. The strategy is **fill the low spots** (the objective lowers variance; it does not maximize) |
| `plan` | publish an immutable plan — **any node may publish** = the decentralized orchestration entrance | hand-placing a batch of tasks |
| `claim` | self-score capability / shape / load → CAS for the task | checking a claim by hand; `tick --auto` runs it automatically inside |
| `run` | claim → execute → write back, in one chain (the dispatch-layer execution entrance) | you want a full round rather than three separate steps |
| `result` | the claimer writes the result back | the third stage of `run`, run alone |
| `gather [--settle]` | any node gathers; **an incomplete gather refuses to claim completion**. `--settle` uses CAS to prevent a double settlement | settling after a plan has run |

### Distributed Git delivery atomics

| Tool | Atomic action | Key boundary |
|------|----------|----------|
| `bin/cortex-workspace.sh create/status/release` | create a sparse execution cabin per attempt, query status, reclaim after clean | shared objects, private index; low disk / live owner / foreign owner / dirty cabin is fail-closed |
| `bin/cortex-candidate.sh compose/validate/publish/inspect` | overlay exact files from any source commit onto the latest canonical base, then check the write set and publish an immutable candidate ref | `compose` does not checkout and does not touch the shared index; it rejects a directory or a missing path; same OID is idempotent, a different OID cannot overwrite |
| `bin/cortex-integrator.sh` | blobless sparse re-check and lease-CAS update of canonical master | `--allow` writable, `--read` read-only; a CAS loser returns 75 and retries |
| `bin/cortex-workspace-inspect.py [--json]` | summarize workspace/candidate/integration/stale locks/disk | read-only; Dashboard `runtime.delivery_plane` comes from the same source |
| `bin/git-worktree-doctor.py --json [--skip-disk]` | inventory registered Agent cabins, claims, live processes, dirty edits, and reclaimable count | Dashboard `runtime.worktree_fleet` comes from the same source; an unreadable process is UNKNOWN |
| `bin/git-worktree-doctor.py --claim PATH --owner ID --task ID [--ttl-hours 24]` | the user claims or renews a worktree | the central claim holds owner/task/host/pid/heartbeat/expiry; someone else's live claim cannot be overwritten |
| `bin/git-worktree-doctor.py --release-claim PATH --owner ID` | release a claim on purpose | an owner mismatch is fail-closed |
| `bin/git-worktree-doctor.py --reclaim PATH` | reclaim an old worktree inside a managed directory | only clean + no claim + no live process; the branch is kept; a detached unmerged tip gets an archive ref first |

Debug order: `workspace status` first to see the execution cabin, then `candidate inspect` for cross-node visibility, then the
integrator receipt's `landed/retryable_*/rejected_*`. When a candidate is visible remotely but has not landed on master, the task must stay settling.

## Trust and constraint (six laws landed · zero LLM)

| Subcommand | What it does | When to use it |
|--------|--------|-----------|
| `trust` | **HAAS computed live, L1–L5** (six-law C2): counted entirely from actual ref-layer records; a node **cannot self-report** | you want to know who may do how much |
| `attest [--executor X]` | verify that the executor **really is** the declared model, three strengths L-env / L-say / **L-print** | a new node joins; you suspect the self-reported model is false |
| `fault` | **the main thread records its own breach** — the orchestrator must also be bound by the trust mechanism | I did it wrong. A constraint without a penalty is not a constraint |
| `credit` | **the main thread records one autonomous completion** — a penalty requires a matching reward | I closed one thing autonomously |
| `readjudicate` | rejudge historical rejected with the **current criterion** (a review of a wrong judgment, **not a pardon**) | after a criterion is tightened or corrected. Measured gate-pass rate 20%→75% (`216a194d0`) |
| `model` | availability of each model tier plus the current selection (automatic step-down when quota is tight) | you hit quota and want to know what is still usable |

**Why L-print is the hardest layer**: self-report and environment variables are both a **declaration**, and a declaration can lie;
a behavior distribution is a **performance**, and it cannot be faked. The strongest `attest` tier goes through [[model-fingerprint/SKILL|model-fingerprint]] (Bruckner PAMELA) —
a single-token output distribution is model identity, compared by Jensen-Shannon divergence.
That skill's 2026-07-21 evidence: a cosplay of "claude pasted over gemini" was caught on the spot at JSD=0.0.

**Transparency cap** (operator decision, 2026-07-29): the more transparent and verifiable the structured information, the higher trust can go;
missing or unverifiable information → **trust is capped**. So **disguise has no payoff** — however pretty the costume, it does not buy autonomy.

| Transparency state | Cap |
|-----------|------|
| fields complete + attest passed | no cap (can reach L5) |
| a field missing / `model.*` `billing.*` not published / attest not done | capped at **0.70** (L3 at most; only reversible work) |
| attest **failed** (self-report ≠ measured) | a breach is recorded + capped at **0.49** (back to L1; read only) |

## AI mount points (the only two that burn quota)

| Subcommand | What it does | When to use it |
|--------|--------|-----------|
| `decompose --line X [--apply]` | AI splits INTENT into task rows → writes `TASKS.proposed.md` **after structural acceptance**; `--apply` is what merges into the ledger | a new line has only intent and no task table yet |
| `judge --line X --task T` | an independent AI acceptor looks at the output and returns only `REJECT:` or `ACCEPT` (the third state `SCOPE` is listed on its own and is not flattened into REJECT) | an exploratory task; the mechanical gate passed but the content looks empty |

> Structural acceptance in `decompose` is **mechanical**: 11 columns not aligned / `status≠pending` / `success_criteria` or `failure_modes` is `-` / duplicate id → the whole row is discarded and the reason is printed. Mock measurement: 3 proposed rows, 2 discarded (M2 missing `failure_modes`, M3 `status` illegal), 1 passed.
> **Agent Code Gauntlet default gate** (2026-08-02): when `decompose` generates a code implementation, a multi-file change, or a high-risk execution task, acceptance must be written before implementation: `success_criteria` + a runnable `short_test` + `out_of_scope`. The main thread only orchestrates and verifies by default; execution goes to HIVE / sub-agent / worker. Production databases, money, permissions, and accounting stop for an operator gate even when the gate is green. Parallel code tasks use an independent worktree / isolated cwd. Small edits, pure queries, and low-risk mechanical commands may be done directly.

## External and self-heal

| Subcommand | What it does | When to use it |
|--------|--------|-----------|
| `api` | **the single external entrance**: the same six-law gate, JSON out | another system needs to call the loop. `bin/cortex-loop-mcp.py` uses the same gate |
| `revive` | self-heal: diagnose the executor → fix it if it can be fixed → **if it cannot, drop the capability so the swarm routes around it** → come back online automatically after recovery | an executor is down |
| `harness-run [title...] [--timeout N] [--json]` | actually drive the **sister repo** `cortex-harness/packages/agent-runtime` through one local-MVP (`scripts/cortex-local-mvp.mjs` → `executeCliEntry()`), closing the hand-typed `pnpm --filter @cortex/agent-runtime` into one entrance | checking that the agent-runtime wiring is still alive; **not** a substitute for tick |

> **The most effective revival is not repairing the model that died. It is switching to the one that is still alive.**
> Quota exhaustion is a single-point problem. The swarm has many nodes and many models — the move is to route around it, not to wait for it to recover.
> The "declare the capability offline" step is the critical one: **the loop can keep running without the repair**.
> `diagnose_executor` classifies the root cause in plain code first (missing / path / auth / quota / network / proxy / config / ok).
> **Do not call a model first** — the cause class decides whether it can be fixed automatically. A `quota` class **should not be fixed. It should be routed around**.

> **`harness-run` honesty boundary** (2026-08-21 HANDOFF Q2 wiring): `agent-runtime` currently has only one verification
> runtime scaffold (session/goal/lease/durable-autonomy loop) with a **synthetic 2-step executor**. It calls no
> LLM and does no real business task. A successful run proves only that "the wiring from ob1 to cortex-harness is reachable". It does not mean agent-runtime
> can really execute. The path can be overridden with `CORTEX_HARNESS_DIR` (default `~/cortex-harness`).
> The node version follows that repo's `engines` (`>=24.0.0 <25`) and automatically picks the highest patch under `~/.nvm/versions/node/v24.*`.
> If none is found it reports `node_v24_missing` explicitly and does not silently degrade to a version that fails the declaration (T5).

---

## Nav

[[cortex-loop/SKILL|SKILL.md]] · [[cortex-loop/references/architecture|architecture]] · [[cortex-loop/references/swarm|swarm]] · [[cortex-loop/references/contracts|contracts]] · [[cortex-loop/references/operations|operations]] · [[cortex-loop/ERRORS|ERRORS]]

---

<!-- cortex:map-backlink d-299b7f1d69b17515abad28ce -->
Related map: [[skills/cortex-loop/MAP|Cortex Loop panorama]]
