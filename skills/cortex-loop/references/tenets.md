English | [简体中文](tenets.zh-CN.md)

# cortex-loop pinned hard rules T1–T9 (full text · including the real cost)

> **When to read this**: the T1–T9 quick table in SKILL.md gives only "the hard rule + the mechanical gate".
> Read this when you want **what each rule cost** (which pitfall, which commit, which ERRORS entry).
> **Parent**: [[cortex-loop/SKILL|SKILL.md]] §pinned hard rules · **error log**: [[cortex-loop/ERRORS|ERRORS.md]]

---

These 9 rules are not "best practices". They are distilled from **the same few root causes** that kept reappearing across 15 ERRORS entries.
Each one has a mechanical gate — relying on memory guarantees a relapse, and the same root cause biting three times inside two days is the evidence.
T1–T6 were set on 2026-07-28 (`c858a9ef9`); **T7–T9 were set on 2026-07-29**, because that day added three layers that did not exist on 07-28:
three-state judgment ([[cortex-loop/ERRORS|E013]]), cross-machine propagation (the propagation gate), and trust scoring ([[cortex-loop/ERRORS|E014]]).

| # | Hard rule | Why (the real cost) | Mechanical gate |
|---|------|-------------------|--------|
| **T1** | **Runtime-agnostic**: the engine knows no concrete runtime. Capability and requirements are **self-declared** by the adapter. Adding a runtime changes only the adapter, not the engine | hardcoding `claude` / `ANTHROPIC_*` would force an engine-core edit when wiring Codex, Gemini, or an in-house runtime | `env-parity.sh` takes requirements from the `# cortex-loop:requires-env` self-declaration, zero hardcoding |
| **T2** | **Cross-environment parity**: an interactive shell can run it does not mean unattended can run it. A scheduler does not inherit the login shell environment | three times in one night: ollama died at 79%, the worker line was entirely `Not logged in`, the Mac hit 403 seven times | `bash bin/cortex-loop-tests/env-parity.sh` |
| **T3** | **Fail closed, not fail open**: the verifier itself failing to run is not content passing; if you cannot see it, reject it | E011: the verifier hit a 502, and the old logic "no REJECT seen, so ACCEPT" let a false completion through | `ai_judge` sees `[ADAPTER_FAILED]` or empty output and REJECTs immediately |
| **T4** | **A criterion must ask "did this specific thing change"**. It must not ask "will a rerun report an error" | E011: a scanner WARN does not affect the exit code → the task "passes" forever, whether or not it was really fixed | `short_test` uses a negative criterion `! (<scanner> \| grep -qF <specific item>)` |
| **T5** | **Silent degradation is more dangerous than an error**: every "degrade / fall back / catch-all" must make a sound | occurrences 1–9 of this project's DNA (E001/E002/E003/E005/E008/E009/E011…) are all "exit code 0, logs look normal, the function is already broken" | falling back to a snapshot must warn; a push failure goes to stderr; a non-zero `run_adapter` exit adds an `[ADAPTER_FAILED]` prefix |
| **T6** | **The placeholder `-` is a legal value, not a path**: every place that reads the `-` convention must exclude it explicitly | the same class of bug appeared twice: `requires="-"` was treated as a capability name, `artifact="-"` was treated as a file path | `fit_score` / `covenant_check` / the three mechanical gates all have the exception |
| **T7** | **Three states, not two**: "cannot tell" must be independent of "absent". **UNKNOWN never collapses toward either side** | E013 appeared in **five places** in one day: `read_ref` / `list_refs` treated a read of empty as absent, a gate flattened scope-gap into FAIL, `ai_judge` flattened SCOPE into REJECT, and a health classifier that failed across versions was treated as healthy | `bash bin/cortex-loop-tests/dimensional-collapse-scan.sh` (wired into the suite) · every probe exits 0/1/**2** |
| **T8** | **Done means propagated to a place others can see**: output that only sits on the local disk is not done | ghost completion real1/R2 — the worker judged done, the output had never entered git history, and nobody in the swarm could see it (`54b1dd836`); v1 only checked that `git log -1 -- <path>` was non-empty, and a live machine slapped it on the spot (`28f7d5d41`) | propagation gate v2: check whether the artifact **entered history reachable from origin**, not whether a local file exists |
| **T9** | **Trust can be bought only with a real change**: rerunning a task whose criterion was already met is a no-op. No points added, no points removed | E014: 17 items let through at once; afterward 7 of them were no-op score farming — **sampling-level strictness was used at trust L1** (`0f167ca4d` / `d121dc721`) | the no-op gate blocks before quota is burned + the fourth state `moot` has its own namespace (it does not enter the credit ledger) + inspection intensity is tiered by trust (full check / sample / exempt) |

---

## How T1 lands (do this when wiring a new runtime)

Write one line at the top of `bin/cortex-loop-adapters/<new-runtime>.sh`:

```bash
# cortex-loop:requires-env PATH HTTP_PROXY ...
```

`env-parity.sh` picks it up automatically. **Neither the engine nor the gate needs a change.**

---

## Meta-pattern: every new gate is slapped by its own live check on day one

Propagation gate v1 (set at 9:00 → falsified at 10:52) · PULSE (set at 8:56 → two defects it exposed on day one were fixed at 9:09) ·
`991016f78`, "a negative test caught my own fix being dead".

**Corollary**: setting the gate is not completion. **The gate counts only after its own test has gone red once.**
So every negative test in the suite must pass a destructive check — a test that does not prove "it really goes red" is itself a fake gate.
(This is already filed in [[cortex-loop/JOURNAL|JOURNAL.md]] §three meta-patterns that kept reappearing. Whether it is promoted to a law is in [[cortex-loop/EXPECTATIONS|EXPECTATIONS.md]] §candidate laws.)

---

## Nav

[[cortex-loop/SKILL|SKILL.md]] · [[cortex-loop/references/commands|commands]] · [[cortex-loop/references/architecture|architecture]] · [[cortex-loop/references/swarm|swarm]] · [[cortex-loop/references/contracts|contracts]] · [[cortex-loop/references/operations|operations]]

---

<!-- cortex:map-backlink d-8c94cb5cf6b251f5ea1f210b -->
Related map: [[skills/cortex-loop/MAP|Cortex Loop panorama]]
