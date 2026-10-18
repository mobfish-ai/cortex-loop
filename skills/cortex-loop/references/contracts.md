English | [简体中文](contracts.zh-CN.md)

# cortex-loop contract system (four file contracts + seven ref namespaces)

> **When to read this**: you are changing fields on `CLOCK.md` / `INTENT.md` / `TASKS.md` / a node profile,
> adding a new ref namespace, or `knowledge-contract-gate.py` reports a missing field.
> **Registry**: [[knowledge-contract-registry]] §4.12 / §4.12a
> **Parent**: [[cortex-loop/SKILL|SKILL.md]]

---

## Four file contracts

| Contract | Path | Layer |
|------|------|----|
| `loop_clock` | `brain-network/directions/CLOCK.md` | L2 schedule truth |
| `loop_node` | `brain-network/directions/_swarm/<node>.md` | swarm node profile |
| `loop_intent` | `brain-network/directions/<line>/INTENT.md` | L0 intent (including the staged variants `CHARTER-SWARM.md` / `INTENT-P2.md`) |
| `loop_tasks` | `brain-network/directions/<line>/TASKS.md` | L1 execution truth |

**Shared-check alignment** (registry §3): `id / status / created / updated / claim / related / success_criteria / out_of_scope / short_test` are all reused under the same name and the same meaning. No alias was invented.

**Agent Code Gauntlet default gate** (2026-08-02): every code implementation, multi-file change, or high-risk execution task must write `success_criteria` + `short_test` + `out_of_scope` into the contract before execution. The main thread only orchestrates and V·Verify. Execution goes to HIVE / sub-agent / worker. Small edits, pure queries, and low-risk mechanical commands may be done directly on the main thread.

### Hard field rules (a violation is a half-contract)

- A cell must not contain `|`. `short_test` is always a script path, never a pipeline command
- `success_criteria` (positive) and `failure_modes` (negative) **both must be non-empty** — missing either corner is a half-contract (KE.3)
- empty `artifact_paths` or empty `short_test` → `try-complete` **refuses** `done` outright (not a warning; a refusal)
- a code task's `short_test` must point at a runnable local gate (unit/script; coverage/mutation/complexity when possible). It must not say "a person will look"
- a production-database / money / permission / accounting task stays in front of the human gate even when `short_test` is green, until the operator confirms explicitly
- `status=done` must have `evidence`
- the placeholder `-` is **a legal value, not a path** (T6): `fit_score` / `covenant_check` / the three mechanical gates must all exclude it explicitly

### Contract-gate check commands

```bash
python3 bin/knowledge-contract-gate.py check-path brain-network/directions/CLOCK.md --strict
python3 bin/knowledge-contract-gate.py check-path brain-network/directions/loop-ops/TASKS.md --strict
python3 bin/knowledge-contract-gate.py check-path skills/cortex-loop/SKILL.md
```

---

## Seven ref namespaces (no file contract · prefix `refs/swarm/<swarm>/`)

> Why not a file: multi-node realtime coordination **must still work when the worktree is unavailable**.
> The whole path is git plumbing (`hash-object` / `mktree` / `commit-tree` / `push <sha>:<ref>`).
> No checkout, and the worktree is not touched — a dirty tree, a conflict, or a stuck auto-sync cannot reach it.

| Namespace | Use | Who writes |
|----------|------|------|
| `beat/<node>` | heartbeat / node profile (= the same fields as `loop_node`) | only `<node>` itself |
| `lease/<line>` | that line's execution lease `holder · expires · since · task` | the node that won the CAS |
| `plan/<id>` | immutable plan (any node may publish) | the publisher |
| `claim/<task>` | claim slot (won by CAS) | the node that won it |
| `result/<task>` | execution result (enters the HAAS credit and fault ledger) | the claimer |
| `moot/<task>` | **fourth state**: the criterion was already met; neither credit nor fault, but **it is terminal** | the node that judged the no-op |
| `incident/<id>` | C3 breach record (the RECORD of `STOP→REPORT→WAIT→RECORD`) | the breaching party itself / the orchestrator |

**Why `moot` must stand alone and not be stuffed into `result`**: stuffing it into `result` pollutes HAAS and the gate-pass rate —
a no-op should neither add points nor remove them (T9). An independent namespace lets "there is no work to do" **be remembered and skipped, without entering any credit ledger**.
See [[cortex-loop/ERRORS|E015]].

**Why heartbeats do not collide**: each node writes only its own ref, and the parent hangs on **its own previous tick**, so it is always a fast-forward.
**A collision is structurally impossible.** It is not a convention that people agree not to collide.

> **The three-state debt of reading a ref**: `read_ref` / `list_refs` currently treat "read empty" as "absent".
> That is site 5 of the [[dimensional-expansion-doctrine|DIMENSIONAL law]] root pattern, and the lowest one
> (called 20 times; claim / plan / result / lease all pass through it). See [[cortex-loop/EXPECTATIONS|EXPECTATIONS]] D3.

---

## Nav

[[cortex-loop/SKILL|SKILL.md]] · [[cortex-loop/references/commands|commands]] · [[cortex-loop/references/architecture|architecture]] · [[cortex-loop/references/swarm|swarm]] · [[cortex-loop/references/operations|operations]] · [[knowledge-contract-registry]]

---

<!-- cortex:map-backlink d-1ce35905c560953da7787eff -->
Related map: [[skills/cortex-loop/MAP|Cortex Loop panorama]]
