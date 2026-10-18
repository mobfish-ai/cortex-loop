English | [简体中文](swarm.zh-CN.md)

# cortex-loop swarm mechanism (many nodes writing one git ledger)

> **When to read this**: multi-machine coordination is in trouble (who should own this line / two machines moving at once / judging whether a machine dropped offline / whether to take over),
> or you are adding a new machine to the swarm.
> **Parent**: [[cortex-loop/SKILL|SKILL.md]] · **commands**: [[cortex-loop/references/commands|commands.md]] §swarm coordination / §decentralized dispatch

---

**The problem**: many nodes writing one git ledger is a conflict source.
**The solution is not a consensus algorithm. It is sharding plus a CAS lease.**

---

## 1. Owner sharding (stop the everyday fight)

`CLOCK.owner` assigns each line a single responsible node → **a natural single writer**, so git does not fight.
A non-owner node `skip`s on tick: `skip | X is owned by Y`.

## 2. Git ref CAS lease (stop split brain · zero external dependency)

> **Core insight**: `git push` updating a remote ref is itself an **atomic compare-and-swap**. Two nodes build a commit from the same parent and push at the same time. The server lets only one fast-forward succeed. The other is necessarily `[rejected] non-fast-forward`. **Semantically equivalent to Redis SETNX, with zero external services.**

- Namespaces: `refs/swarm/lease/<line>` (lease) · `refs/swarm/beat/<node>` (heartbeat)
- Each node pushes only its own beat ref → a collision is structurally impossible
- The whole path is git plumbing (`hash-object` / `mktree` / `commit-tree`). **No checkout, and the worktree is not touched**
- Why it must go through the ref layer: the worker's live state was 267 uncommitted files and a broken auto-sync. Any pull/rebase/checkout is blocked by the dirty tree → the swarm goes blind with it

> A CAS rejection and a network fault **must be separated**. Flattening them into one return value is [[cortex-loop/ERRORS|E009]] (the [[dimensional-expansion-doctrine|DIMENSIONAL law]] root pattern).

## 3. can_sleep differentiated silence thresholds (stop misjudgment)

The `loop_node` profile detects this automatically: a battery means a laptop that sleeps; no battery, or `SleepDisabled=1`, means always-on.

| Node type | Silence that is still normal | Takeover threshold (2× buffer) |
|----------|-------------|----------------------|
| `can_sleep=yes` (laptop) | 14h (lid closed overnight is normal) | 28h |
| `can_sleep=no` (always on) | 3h | 6h |

**Takeover must exceed the threshold by 2×** — better to take over late than to seize it and hand it back (**flapping hurts more than a stall**).
The taker is the first surviving node in name order (no election; deterministic).
`last_seen` is taken at **hour precision** → a repeated heartbeat inside one hour has no file diff → the swarm does not manufacture commit noise.

> "The log is continuous" is not "it has been running the whole time" — a closed laptop lid makes launchd stop firing ([[cortex-loop/ERRORS|E007]]).
> So the `idle` denominator contains only **ticks that actually ran**, not wall clock.

## 4. Automatic takeover when a session dies (HIVE R·Resume made mechanical)

The loop **does not know how the session died** (API disconnect / quota hit / the machine slept). It only recognizes "`running` has been quiet past `stall_min` (default 45min)" → reclaim and re-push.
**What takes over is not that session. It is the external clock.**

This is R·Resume in [[hive-doctrine|HIVE law]] — the law says "the first thing on reconnect is to resume". Here that becomes a mechanical action that does not depend on anyone remembering.

## 5. Multi-runtime execution isolation (stop the shared-worktree fight)

- The ref layer owns claim/lease/result. Do not wrap an Agent lifetime in a global Git lock.
- Each attempt uses a unique sparse linked worktree. Git objects are shared; the index and worktree are not.
- A Candidate is published to `refs/cortex/candidate/<attempt>/<oid>`, immutable and consumable across nodes.
- The Integrator is the only logical lander, and it is not a long-lived global lock: each time it does one server-side CAS against the observed master tip.
- A CAS loser returns retryable and replays against the latest tip. Only a path or semantic conflict is blocked. Ordinary contention is not counted as an execution failure.
- A successful settlement immediately reclaims a clean workspace. A dirty cabin, a foreign/live owner, or an identity mismatch is fail-closed.

---

## The main thread's seat in the swarm

On the same machine, "the one running tick" and "the one talking to a person" are two nodes:

| Node | kind | Meaning |
|------|------|------|
| `<host>` | executor | the automatic executor started by launchd |
| `orchestrator-<host>` | orchestrator | the human-machine interface, not an executor. Join with `checkin` / leave with `checkin --out` |

The orchestrator must also be bound by the trust mechanism → two-way scoring with `fault` (record one's own breach) + `credit` (record an autonomous completion).
Source of truth: [[cortex-loop/references/architecture|architecture.md]] §six-law three gates · the law side is [[steer-doctrine|STEER]].

---

## Nav

[[cortex-loop/SKILL|SKILL.md]] · [[cortex-loop/references/commands|commands]] · [[cortex-loop/references/architecture|architecture]] · [[cortex-loop/references/contracts|contracts]] · [[cortex-loop/references/operations|operations]] · [[cortex-loop/ERRORS|ERRORS]]

---

<!-- cortex:map-backlink d-66b637004ace09ce92612c5c -->
Related map: [[skills/cortex-loop/MAP|Cortex Loop panorama]]
