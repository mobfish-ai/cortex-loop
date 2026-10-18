English | [简体中文](ERRORS.zh-CN.md)

# cortex-loop — error log

> **Established**: 2026-07-28
> **Scope**: the `bin/cortex-loop` engine + adapters + the four contracts + the swarm bus
> **Field contract**: [[recipe-and-errors-contract]] §ERRORS — `id · symptom · root_cause · fix · never_again · related_skill`
> **Hard rule**: any pitfall enters here first, then the code changes. A fix must carry a commit sha.
> **Main document**: [[cortex-loop/SKILL|SKILL.md]]

---

---

## E021 · Execution welded to settlement: a git transaction lock or a push failure still shows "not running" after short_test is green

| Field | Value |
|------|------|
| **id** | E021 |
| **date** | 2026-08-01 |
| **status** | closed |
| **related_skill** | cortex-loop |

**symptom**: IMM-T54–T57, four `pending` rows, sat in the ledger. `short_test` had already PASS locally. `try-complete` returned `FAIL artifact landing failed rc=75` (another commit transaction) or push behind/SSL. A person saw "nothing running, the stand-in will not move" and thought the task had not executed.

**root_cause**: the completion gate flattened three things into one synchronous chain:
1. disk truth + short_test (**execution plane**)
2. pathspec commit + push + origin reachable (**settlement / propagation plane**)
3. a repo-wide `ob1-transaction.lock.d` mutex (stop index collisions)

When 2 or 3 failed it returned a hard FAIL and status stayed `pending` → "already verified green" and "not done yet" became the same state (a DIMENSIONAL collapse). The propagation gate itself is sound (it stops a worker ghost completion). The mistake was **equating a settlement failure with an execution failure**.

**fix**:
- new state **`settling`**: short_test has passed and only git propagation remains; not terminal, and it cannot claim an LLM
- `try-complete`: a retryable land failure → `SETTLING` (exit 0), and it is not recorded as an attempt-fail
- `tick --auto` runs `settle_line_tasks` on each line first (land→done only), then claims pending
- `commit_own_profile`: if the transaction lock is busy, skip; **do not block claim**
- `advance_once` is settle-first and recognizes settling on the way out; it does not burn a model and does not wash the failure backoff
- contract / task-add / probe recognize `settling`

**never_again**:
- **the execution plane must not wait on a git lock**; **the settlement plane may queue**; the two states must be distinguishable
- "the swarm cannot see it = not done" still holds, but it must not be inverted into "do not claim / treat it as not done"
- every `FAIL` exit asks: did the world not change, or is the propagation channel busy? The latter is forbidden from being sent back to pending-failure semantics

---

## E001 · read_table treated the "column meaning" legend table as the data table

| Field | Value |
|------|------|
| **id** | E001 |
| **date** | 2026-07-28 |
| **status** | closed |
| **related_skill** | cortex-loop |

**symptom**: on the first smoke test the engine read a pile of nonsense rows out of the markdown ledger (the text was legend copy such as "column / meaning"), not tasks.

**root_cause**: one markdown file can hold **many tables**. The top usually has a "column meaning" legend table, and the data table is below it. The old `read_table` treated the first block that started with `|` as the data table and ate the whole legend.

**fix**: `93ae328c5` `read_table(path, key=...)` recognizes only the table **whose header contains the `key` column**. A header without key → `header=[]`, and the whole table is skipped.

**never_again**:
- when markdown is structured storage, **table recognition must use header field names**. It cannot use a position convention such as "the first table" or "the Nth table"
- a position convention collapses silently the moment anyone adds a legend table at the top of the document

---

## E002 · The wrong primary key silently read 0 rows

| Field | Value |
|------|------|
| **id** | E002 |
| **date** | 2026-07-28 |
| **status** | closed |
| **related_skill** | cortex-loop |

**symptom**: `tick` ran, exit code 0, no error at all, and **not a single line was scanned**. The behavior was identical to "no line is enabled".

**root_cause**: `read_table` defaults to `key="id"`, but the primary-key column of `CLOCK.md` is **`line`**, not `id`. A wrong key → the header does not match → the whole table is skipped as a legend → 0 rows returned. **The E001 fix itself created E002's failure mode**: skipping the legend is correct, but the skip made no sound.

**fix**: `93ae328c5` `clock_lines()` calls `read_table(CLOCK, key="line")` explicitly, and a dead warning comment was left above the function:
```python
# CLOCK's primary key column is line (not id); a wrong key silently reads 0 rows
```

**never_again**:
- "read 0 rows" and "the table really has 0 rows" are **two different things**, and the code must be able to tell them apart
- every contract table's primary-key column name is written into the contract registry (registry §4.12 already lists all 7 fields). Callers may not pass it from memory

---

## E003 · A for-each-ref format-string escape silently fell back to the file snapshot

| Field | Value |
|------|------|
| **id** | E003 |
| **date** | 2026-07-28 |
| **status** | closed |
| **related_skill** | cortex-loop |

**symptom**: `sync` reported `beat=True` and everything looked fine, but `swarm` could see only the laptop node and **could not see the worker** — even though the worker's ref had already been pushed.

**root_cause**:
```python
git("for-each-ref --format='%%(refname)' " + namespace)   # ❌
```
`%%` is the escape form in a **`%` formatting** context. Here the construction is **string concatenation** (`+`), which does not go through `%` formatting → git received the literal `%%(refname)` → the output was the literal `%(refname)` → the `startswith(namespace)` filter was always empty → `read_swarm()` got 0 nodes → **it silently fell back to the local file snapshot**, so only the `.md` written by this machine itself was visible.

**fix**: `62b597a8b`
1. `--format='%(refname)'` (drop the extra escape)
2. **falling back to the snapshot must warn explicitly**: `print("WARNING: ref layer sees no nodes, falling back to the local file snapshot...", file=sys.stderr)`

**never_again**:
- when a shell command is built by concatenation, `%` does not need escaping; only `"..." % args` needs `%%`. When code changes from `%` formatting to concatenation (or the reverse), **the whole string must be rescanned for `%`**
- **every fallback branch must make a sound**. A silent fallback disguises a bug as normal operation

---

## E004 · [Fatal] rev-parse returns empty when the local ref is missing → push becomes a remote ref deletion

| Field | Value |
|------|------|
| **id** | E004 |
| **date** | 2026-07-28 |
| **status** | closed |
| **severity** | fatal (irreversible remote data deletion) |
| **related_skill** | cortex-loop |

**symptom**: a latent defect, stopped before it caused a loss. If `<sha>` in `git push origin <sha>:<ref>` is the empty string, the command degenerates into `git push origin :<ref>` — git's syntax for **deleting a remote ref**.

**root_cause**: when the local ref does not exist, `rev_ref()` gets an **empty string** back from `git rev-parse --verify --quiet` (not an error, and not None). The empty string was treated as a normal parent/commit sha and spliced into the push command. An empty left side of the colon deletes the remote ref.
A missing local ref is **the most common normal case** (a new node's first sync, a failed fetch, a ref not yet pushed), not an exception path.

**fix**: `51d317f9a`
1. `rev_ref()` returns `None` strictly, never an empty string: `return sha if re.fullmatch(r"[0-9a-f]{40}", sha or "") else None`
2. `write_ref()` hard-checks before push: the sha must match 40 hex digits, otherwise **return False immediately and do not push**
3. `acquire_lease()` `fetch_refs()` first, then judges the holder — a missing local ref would be misjudged as "nobody holds it"
4. **no `--force` anywhere**: a non-fast-forward must be rejected, and the rejection is the signal that the lock is working

**never_again**:
- any value spliced onto the left of the colon in a git push **must first be regex-checked as a 40-digit sha**. An empty value is not "absent". It is "delete"
- a "could not get it" return value uses `None`, never an empty string — an empty string gets spliced silently into a command string
- a command whose destructive meaning is triggered by **syntactic sugar** (`:ref` = delete) must have the defense written dead at the call site. It cannot depend on the caller remembering

---

## E005 · health treated "delivery failed" as "execution failed" → the loop was paralyzed by notification-channel jitter

| Field | Value |
|------|------|
| **id** | E005 |
| **date** | 2026-07-28 |
| **status** | closed |
| **related_skill** | cortex-loop · openclaw-master · cron |

**symptom**: 10 of 32 jobs in `openclaw cron list` were `error` (31%). The old `health` rule "error ratio > 15% means RED" → judged RED → `tick --auto` refused to advance → **the whole self-heal system stopped**.

**root_cause**: each `lastError` from `openclaw cron get <id>` was read by hand. See [[cortex-loop-cron-error-triage]].
**7 of the 10 errors were not task failures at all** —

| Class | Count | Really a failure |
|----|------|-----------|
| A delivery failure (`OutboundDeliveryError: sendMessage failed`; local Privoxy/Clash cut Telegram) | 6 | **no**; the task finished and only the notice was not delivered |
| D delivery-target ambiguity (`Refusing implicit isolated cron delivery`) | 1 | **no**; execution was refused |
| B every model down / C execution timeout / E tool-call failure | 1 each | yes |

**Only 3 were real task failures (9%).** The other 7 were delivery-side problems. Treating a failed report as failed work → **jitter on one notification channel can stop the whole self-heal system**.

**fix**: `f63bd4430` `cmd_health` reads `lastError` one by one and splits on a regex:
```python
delivery_re = re.compile(r"OutboundDeliveryError|Refusing implicit.*delivery", re.I)
```
- a hit → `WARN | delivery degraded`, **does not block advance**
- the rest → counted in the RED ratio

Measured: real execution failures 3/32 (9%) → `HEALTH: GREEN`.

**never_again**:
- **a health check must separate "the work failed" from "the report failed"**. If a self-heal system's red rule counts a fault in the observation channel as a fault in the observed object, it kills itself when its own sensor jitters
- any rule of the form "ratio over a threshold means red" must, before it lands, **read the raw errors one by one** and confirm they are the same kind. Counting rows is not enough

**2026-08-03 addendum: the class-A "delivery failure" root cause was found and actually fixed. It is no longer a known defect accepted for the long term** —

Before, `OutboundDeliveryError` was only split into a non-blocking WARN. Nobody had looked up why it failed. This time
the `channels` section of `~/.openclaw/openclaw.json` showed that the **`discord` channel had
`"proxy": "http://127.0.0.1:10794"`, and the `telegram` channel had no proxy at all**. A direct curl to
`api.telegram.org` worked (GET and POST were both tested), but OpenClaw's internal Node/undici client
did not know to use the proxy. The direct connection was blocked, so only the telegram channel kept reporting `sendMessage` failures. Discord
did not have the problem.

**fix**: `openclaw config set channels.telegram.proxy "http://127.0.0.1:10794"`
(CLI entrance; the json was not edited by hand). Hot reload took effect. No manual `launchctl kickstart` was required. **Real verification**:
`openclaw message send --channel telegram --target 7803302841 --message "..."` →
`Sent via telegram. Message ID: 4685`. It went through the real delivery channel, not a bypass test.

The earlier 6 "delivery failed" rows, and the 8 "delivery degraded" rows seen by the PULSE check at the start of that session, were very likely
all this one root cause — **no longer a known defect to be endured. It was actually fixed.** If telegram
delivery fails again later, first confirm this proxy setting was not dropped by some `openclaw setup` / `configure` run.

---

## E006 · A dead credential hung at the end of the fallback chain, unnoticed for a long time

| Field | Value |
|------|------|
| **id** | E006 |
| **date** | 2026-07-28 |
| **status** | waiting_external |
| **related_skill** | cortex-loop · openclaw-master |

**symptom**: `mercury-daily-ops-report` failed 13 times in a row. `lastError` = `FallbackSummaryError: All models failed (2): gemini timeout | zhipu/glm-4-flash: 401 authentication failed`.

**root_cause**: the GLM key was already invalid (401), and that cron has its own per-job model/fallback
override: `gemini/gemini-2.5-flash → zhipu/glm-4-flash`. Changing only agent defaults
and the Cortex adapter does not pierce that override, so the system layer had already switched to MiniMax while mercury kept running
the old chain. A dead credential at the end of a fallback chain is not called in ordinary times. It is exposed only when Gemini also times out.

**fix**:
1. agent defaults and the Cortex adapter use MiniMax;
2. on 2026-07-31, `openclaw cron edit` changed mercury's per-job model to
   `minimax/MiniMax-M2.7` and cleared the dead fallback; hand-editing `jobs.json` is forbidden;
3. a real run sends an operations daily to Telegram and must wait for explicit outbound approval before it runs. Until the run succeeds,
   stay `waiting_external`. Do not pass it off as fixed.

**never_again**:
- **a fallback chain is a graveyard of credentials**: a dead credential in the catch-all position does not report itself. When a credential rotates or is retired, **grep the whole chain**. Do not change only the primary
- a model switch must look across all four override layers: defaults, agent, cron per-job, and adapter. An upper layer already changed does not mean
  an independent job inherits it
- acceptance of "fixed" must be **a real pass under a natural run**, not one artificial trigger arranged so it turns green

---

## E007 · Laptop lid closed → launchd stopped firing; "the log is continuous" was misread as "it has been running"

| Field | Value |
|------|------|
| **id** | E007 |
| **date** | 2026-07-28 |
| **status** | closed |
| **related_skill** | cortex-loop |

**symptom**: the heartbeat log looked like one line after another, continuous, but there were long stretches when the machine was actually asleep and the loop **was not running at all**. A person reading the log would think "it has been running the whole time".

**root_cause**: a closed laptop lid sleeps. While asleep, launchd **does not fire**. On wake it **catches up once** (it does not replay all N ticks that were slept through). The log presents as "several normal records", and the huge hole between timestamps is easy to miss.

**fix**: `e007fc7ec` `sleep_gap_note()` reads the previous tick time from the heartbeat log. An interval greater than 2× expected (default 15min × 2) prints at the start of tick and writes the log:
> `wake catch-up: N minutes since the last heartbeat (expected 15) → the machine very likely slept, and the heartbeat was a vacuum for that stretch`

Companion: `loop_node.can_sleep` lets the swarm judge liveness with a **differentiated ruler** — 14h of laptop silence is normal; 3h of silence on an always-on machine is abnormal (see SKILL.md §swarm).

**never_again**:
- **a heartbeat system must be able to observe its own holes**. Recording only "I ran" and not "I was supposed to run and did not" is fake availability
- "a machine that sleeps" and "always on" cannot be judged alive or dead with the same ruler, or the result is either a false alarm or a miss

---

## E008 · A later table wiped the header → the only write entrance crashed instead of going red

| Field | Value |
|------|------|
| **id** | E008 |
| **date** | 2026-07-29 |
| **status** | closed |
| **related_skill** | cortex-loop |

**symptom**: any table appearing in `TASKS.md` **after** the ledger table made `try-complete` / `submit` / `tick --auto` all throw an uncaught `ValueError: column not in table: status` **crash** — not a red report. The whole tick aborted, and no later line got a turn.

**root_cause**: `read_table()` reset `header` on every new table, and a header with no primary-key column was cleared. So what came back was **the header of the last table in the file**. `rows` stayed correct (so `load_tasks` looked fine) while `header` was empty — and `set_cell` is the ledger's only write entrance, so a hit exploded. It had not exploded only because the real ledger's "field rules" happened to be written as a numbered list, and CLOCK's legend table happened to sit in front of the data table. **"The data table must be the last table in the file" was an implicit constraint written into no contract and known to nobody.**

**fix**: `89fa34d9e` — recognize only the first table that hits the primary key. Later tables must not overwrite a header already recognized.

**never_again**:
- a structured parser that returns a "partly correct" result (rows right, header empty) is more dangerous than a total failure, because the caller cannot see the problem
- any constraint of the form "the file layout must satisfy some order" is either written into the contract and checked by a gate, or it is not allowed to exist
- caught by the suite's mutation test — **before changing the engine, run a deliberately broken copy through the gate**. That proves the test is not decoration

---

## E015 · Claim and execute each counted the other as load → the node was full and produced nothing (the direct cause of 59% idle)

| Field | Value |
|------|------|
| **id** | E015 |
| **date** | 2026-07-29 |
| **status** | closed |
| **related_skill** | cortex-loop |

**symptom**: `discover --publish` emitted 15 real todos → `claim --plan X` successfully took 3 slots
→ immediately `run --plan X` reported, for **those same 3 tasks**:
```
pass | fm-ins-20260709-lilia — overloaded (current 3 + this task 1 > cap 3)
this node laptop executed 0: -
```
15 real jobs queued, the node had quota and compute, and **not one of them could execute**. The dashboard showed 59% idle.

**root_cause**: `cmd_run` ran `fit_score(task, prof, load, max_load)` once per task,
and `load` came from `node_load(me)` — which counts "claims I hold that are unexpired and have no result".
The 3 slots `claim` had just taken all matched that condition.
So: **claim filled the load → at execute time those 3 slots locked themselves out**.
`claim` and `run` each counted the other's result as their own load. The node stuck at "full, zero output".

The load criterion was not computed wrong (`node_load` itself is correct; a zombie-claim fix earlier that day was already in effect).
**The same quota was counted twice**: once when the slot was taken, again when it was fulfilled.

**fix**: `cmd_run` adds a self-hold exemption — when `holder == me`, score with `load=0`:
```python
_mine_already = (holder == me)
score, why = fit_score(task, prof, 0 if _mine_already else load, args.max_load)
```
The slot is mine. Executing it is **fulfillment**, not a new occupation. Claims held by other nodes still count toward my load
(those really cannot be taken, and they should yield).

**never_again**:
- **"occupation" and "fulfilling an occupation" are two things**. The same slice of quota cannot be counted twice —
  this is the E013 dimensional-collapse root pattern in resource accounting: two states of different kinds flattened into one count.
- **work available and the node idle means the dispatch chain is broken**. Check "publish → claim → run" segment by segment. Do not look only at the total.
  In this case discover was normal, publish was normal, claim was normal, and the break was run's admission.
- a load criterion should ask: **does this number include "the action I just took myself"**.

---

## E014 · No-op score farming: rerunning a task whose criterion was already met still counted as passed, and trust was farmed up

| Field | Value |
|------|------|
| **id** | E014 |
| **date** | 2026-07-29 |
| **status** | closed |
| **related_skill** | cortex-loop |

**symptom**: from 16:39 to 17:59 the laptop finished 8 `island-*` tasks in a row, **all `gate=passed`**.
Trust went L1→L3 (0.492→0.774). On the books it was the best-looking node in the swarm.
When the operator asked "what caused the rise", the check showed those skills' `host:` fields
**had already been added between 12:18 and 13:10**. The node was doing tasks whose criterion had long been met.
`cortex-loop why --node laptop` printed: **really done 0 / no-op 8**.

**root_cause**: `cmd_run` **did not check whether the criterion was already met** before executing.
The flow became: claim → call the model (burn quota) → run `short_test` (it passes immediately, because it already passed)
→ `gate=passed` → trust +1. **Output was zero. The score still rose.**

The trigger was the fix "accept the old plan before publishing a new one": it made the node go back and take the old plan,
and the tasks in that old plan **had already been solved by another path during those hours** (a sub-agent batch-set host,
and readjudicate changed the judgment). The old tasks became empty shells.

**Why this is much more dangerous than "doing it and failing"**: a failure is stopped by the gate, loses points, and is seen.
**A no-op is green the whole way.** It pollutes three metrics at once — gate-pass rate inflated, trust inflated, load rate inflated —
and every one of them is green on the dashboard. This is the "silent failure" root pattern in the scoring layer.

**fix**:
(1) `cmd_run` adds a **no-op gate** (before the six-law three gates, and before quota is burned):
   `short_test` already passed → print `noop | <task> — criterion already met, nothing to do`,
   **write no result, score nothing, call no model**. Red→green measured both ways:
   criterion met → exit 0 → skip; criterion not met → exit 2 → execute normally.
(2) new `cortex-loop why --node <n>` — traces every trust rise and fall and labels its nature
   (really done / no-op / rejudged / rejected), and ends with "really done N | no-op M".
(3) stock cleared: 8 no-op results rejudged to `gate=noop` (**refs not deleted**),
   laptop trust 0.774 (L3) → **0.634 (L2)**, and one `noop-inflation` breach recorded.

**never_again**:
- **before any scoring action, ask "when this finishes, did the world change"** — no change means it should not score.
  The criterion uses `short_test` itself: it is the only source of truth for "is this thing done".
- **a trust rise must be able to name which row it rose on**. A rise that cannot be named is suspicious by default — that is why `why` exists.
- **"all green" is not evidence of health**. It may mean nobody is working. A no-op's books look better than real work.
- a stock correction **rejudges and does not delete the ledger**: deleting a ref erases the books, which violates the reason the scoring mechanism exists.

---

## E013 · Dimensional collapse: signals of different kinds flattened into one judgment, and what is lost is "why"

| Field | Value |
|------|------|
| **id** | E013 |
| **date** | 2026-07-29 |
| **status** | closed (4 sites fixed · 1 site found and still to fix; see fix) |
| **related_skill** | cortex-loop |

**symptom**: it appeared the same day in 5 completely unrelated places in the code, each looking different:
(1) `cmd_health` flattened "an openclaw orchestration-layer fault" and "this node's execution ability" into one
`RED/GREEN`. When it could not reach, it judged GREEN; when it could reach and reported the fault honestly, it judged RED — **the blinder it is, the more work it can do**.
(2) when the `discover_candidates` scanner timed out or crashed, `code` was never checked. An empty `out`
silently produced 0 candidates, and the system reported "everything is green". (3) propagation gate v1 used a non-empty `git log -1`
to judge "this change entered history". What it actually checked was "this file has had history" — the two were
flattened into the same boolean, and a live machine judged `done` for a file that had no host field on origin.
(4) `node_load` flattened "the task is running" and "the task just finished" into the same claim state.
After 3 tasks the node hit the cap and could take no new work for an hour. (5) (found, not yet fixed) `read_ref`
flattened "the ref does not exist" (a normal state) and "the git command errored" (an abnormal state) into the same `""`.

**root_cause**:
the operator named it on 2026-07-29. That naming is the core of this entry.
**Real-world state is naturally high-dimensional** — "an openclaw fault" is not "a node fault",
"the scanner matched nothing" is not "the scanner is down", "the file has history" is not "this change entered history",
"running" is not "just finished", "no data" is not "the read failed". **Compressing high-dimensional state into one
low-dimensional boolean or status code drops, in the compression, exactly the "why" — and "why" is often
the key to what to do next.** This is not "a few cases were not checked". It is a dimension mismatch:
the dimension of the state space must line up with the dimension of the real world. Forcing a place that should expand into one
boolean is dimensional collapse.

**fix**:
(1) health layered — the blocking domain keeps only the three items that are "deterministically self-checkable on this node and causally direct"
(delivery channel down / ledger channel down / contract not self-consistent). The external orchestration layer is demoted to an alert domain and never red.
When it cannot be reached, report `UNVERIFIABLE` instead of pretending OK (`22b23217c`).
(2) SCANNER-DOWN gate — a `run()` timeout is restored on its own to 124 (the GNU timeout convention code),
separated from the 1 of "normal, no match" (`991016f78`).
(3) propagation gate v2 — check that `git status --porcelain` must be empty (disk content == HEAD content).
No longer check "whether the file was ever in history" (`28f7d5d41`).
(4) `node_load` batch-fetches the result-ref set to judge "finished vs still occupying"
(`3ffc0fcb5`).
(5) **still to fix**: `read_ref` / `list_refs` should return three states (has data / confirmed no data / read
failed and cannot confirm), reusing the existing `UNVERIFIABLE` pattern. These two functions are called 20 times.
They are the engine's most basic read, lower than (1)–(4).

**never_again**:
the following required actions are written into all new code, extending the capstone lesson of E001–E003.
- **before writing any binary judgment (RED/GREEN, success/failure, present/absent), ask: how many states of different kinds does the real world have here?** If there are 3, expand into 3. Do not flatten into 2 for the sake of "simple"
- **"cannot tell" must be an independent third state. It cannot collapse toward either side** — collapsing toward "healthy" is
  fail-open (the blinder, the more work), collapsing toward "fault" is over-conservative, and both are products of compression
- **the same return value cannot express two causes of different kinds at once** — `""` cannot mean both
  "it was never there" and "the read failed"; `False, ""` cannot mean three different local
  git plumbing failures at once
- **when one compression point is fixed, immediately ask "how many other sites does this root pattern have"** — all 5 sites in this entry were
  found the same day by widening the search with that question. The last site (`read_ref`) was swept by the main thread with
  `grep 'if code ==\|== "OK"'`. It was not stumbled into

**Mechanical residue**: `bin/cortex-loop-tests/dimensional-collapse-scan.sh` —
greps the whole file for the signature of "a binary judgment swallowing several failure causes", as a pre-commit / periodic
scan item, so this mold does not recur in new code and is not checked only once.

---

## E012 · Cross-environment inconsistency: an interactive shell can run it does not mean unattended can run it

| Field | Value |
|------|------|
| **id** | E012 |
| **date** | 2026-07-29 |
| **status** | closed |
| **related_skill** | cortex-loop |

**symptom**: the same root cause **appeared three times** the same night, each time in a different coat: (1) `ollama pull` died at 79%; (2) all 50 tasks on the worker side were `Not logged in`; (3) the Mac launchd hung every task 7 times in 4 hours with `403 Request not allowed`. The shared feature: **a person running the identical command by hand in an interactive terminal succeeded immediately**, so it was very easy to misjudge as "flaky / network jitter / a quota problem".

**root_cause**: a process started by a scheduler (launchd / systemd / cron) **does not inherit the login shell's environment variables**. The three misses were: (1) `HTTPS_PROXY` (this machine goes through Privoxy; without a proxy it cannot connect) (2) `ANTHROPIC_BASE_URL/AUTH_TOKEN/MODEL` (set by `~/.bashrc` → `node-env.sh`; systemd does not walk that chain) (3) `HTTP(S)_PROXY` (the plist injected only `PATH`).

**What is more worth recording is my first wrong response**: when I hit (1) I only added `HTTPS_PROXY` **on that one command** and moved on. **I did not spread it sideways into the scheduler configuration**, so the same root cause bit twice more in a different coat.

**And I gave a wrong root cause**: when (3) happened I inferred "the Mac lock screen meant keychain credentials could not be read". After the operator challenged it, measurement overturned the inference — `pmset -g log` showed the `Powerd - Prevent sleep while display is on` assertion present the whole time from 02:51 to 07:00 and accumulating duration. **The screen stayed on. The machine never slept.** Treating an inference as a conclusion is a second injury.

**fix**: `724117356` — (1) the plist was filled in with the proxy variables, `plutil -lint`, and a real launchd environment-isolation probe (it returned "online"; the 403 disappeared) (2) the systemd unit was changed to `bash -lc 'source node-env.sh; exec ...'`; secrets do not enter git (3) new mechanical gate `bin/cortex-loop-tests/env-parity.sh`, **runtime-agnostic**: it takes the union of requirements from each adapter's `# cortex-loop:requires-env` self-declaration and compares them with this machine's scheduler configuration. A new runtime changes only the adapter (4) wired into `scan_self_defects()`, so a regression automatically becomes a swarm task.

**never_again**:
- **any "verified" must name the verification environment**: sandbox verification is not production verification, interactive verification is not unattended verification, and the two cannot stand in for each other
- **a cross-environment behavior difference starts by comparing `env`. Do not guess the behavior** — all three pits this time were env differences. Guessing the cause (such as "lock screen") wasted a round
- **after fixing a pit in one environment, immediately ask sideways "how many sibling schedulers are there"** — that is the direct reason it appeared three times

---

## E011 · False completion: short_test reused the scanner exit code, and the verifier failed open. Both layers fell at once

| Field | Value |
|------|------|
| **id** | E011 |
| **date** | 2026-07-29 |
| **status** | closed |
| **related_skill** | cortex-loop |

**symptom**: the first time a fully automatic closed loop ran through on a live machine, `skill-reg-1` ("register huashu-doubao-search into SKILLS-TAXONOMY") was marked `status=done, gate=passed` by the engine, but an independent rerun of the same `short_test` falsified it immediately — `bash bin/verify-skill-integration.sh --check registry` still reported `not registered: huashu-doubao-search`. The problem had not been fixed at all.

**root_cause**: two defects stacked. Either one alone would not have leaked.
1. The exit code of a scanner such as `verify-skill-integration.sh` is non-zero only on **FAIL**. **WARN does not affect the exit code**. `discover_candidates` used the whole scanner command as the `short_test` as-is — so this class of task's mechanical gate **always passed**, whether or not anything was really fixed, because rerunning the scanner itself is constantly exit 0.
2. `ai_judge`'s independent acceptance also failed to stop it on this live run: the verifier (`claude-sonnet-5`) hit a local gateway `502 unknown provider` on the spot. The output was an error message (it did not contain the word `REJECT`). The old logic "no REJECT means ACCEPT" — **the verifier itself never started, and that was treated as "the content is fine" and let through**. Fail open, not fail closed.

**fix**:
- `discover_candidates`' `short_test` changed from "reuse the scanner command" to "a negative criterion aimed at that specific problem": `bash -c '! (<scanner> 2>&1 | grep -qF "<the specific hit>")'`. After a rerun it judges exactly whether this one item is still there. It no longer looks at the scanner's overall exit code
- `run_adapter` captures the adapter's real exit code and, on non-zero, prefixes the output with `[ADAPTER_FAILED rc=N]`
- `ai_judge` sees that prefix or empty output → immediate `REJECT` ("the verifier did not run normally; if we cannot see it, it does not pass; the default is not to let it through"), and no longer "ACCEPT by default because the word REJECT was not seen"

**never_again**:
- **a criterion must always ask "did this specific thing change". It cannot ask "will a rerun report an error"** — a scanner can be healthy overall (exit 0) while the one problem you meant to fix is untouched
- **the verifier itself failing is not the content passing**. Any "cannot understand / did not start / errored" must map to reject. It must not map to the branch of the default that happens to equal let-through
- this is the 9th appearance of this project's "silent degradation" DNA (E001/E002/E003/the 4th push/E005/E008/E009/this entry), and the most harmful — **it was the first time a false completion was actually written into the execution ledger**. Not a design deduction. It was hit on the first live fully automatic closed-loop run

---

## E010 · A long-running process bound to the terminal → one session crash killed everything

| Field | Value |
|------|------|
| **id** | E010 |
| **date** | 2026-07-29 |
| **status** | closed |
| **related_skill** | cortex-loop |

**symptom**: in the same second the session crashed, `ollama pull` died at 79% (2.0GB/2.5GB downloaded for nothing) and three running sub-agents were wiped. The tokens and bandwidth already burned were all wasted.

**root_cause**: these processes were started bare from the session. **When the parent dies, the children are buried with it.** The launchd / systemd timed heartbeat was untouched — **because it was never attached to a terminal**. On the same machine the two classes of process had opposite fates. The only difference was "whether it had detached from the terminal".

**fix**: after `6ea6f12e2`, `bin/cortex-loop-detach.sh` was added — always start under tmux, tee to disk, idempotent (the same name does not start twice), and `--status` / `--wait` available. A measured re-pull of ollama was already decoupled from the terminal.

**never_again**:
- **any command that might run longer than 30 seconds goes into tmux**. Do not gamble on "this one should be quick"
- self-heal is layered, because tmux is itself a single point: **terminal dies → tmux catches it; tmux dies → launchd/systemd pulls it back up; everything dies → the git ledger is still there, and the next tick resumes from state**
- what actually saved these three paths was not tmux. It was **SUBAGENT-PERSIST writing to disk while working**: the three agents' `reports/_work/*.md` each left 5.3–5.8KB of real content, and a resume only had to `cat` to pick up. **Work that was not written to disk was never done**

---

## E009 · A CAS rejection and a network fault were flattened into the same return value

| Field | Value |
|------|------|
| **id** | E009 |
| **date** | 2026-07-29 |
| **status** | closed |
| **related_skill** | cortex-loop |

**symptom**: a pure network fault was reported as "another node pushed first in the same instant — CAS held", so `tick` silently skipped that line. The log looked entirely normal, and operations would investigate in the wrong direction of "concurrent contention".

**root_cause**: `write_ref()` flattened every push failure into the same `False`. This machine's GitHub goes through Privoxy. Measurement was about 1 `SSL_ERROR_SYSCALL` jitter in every 6 attempts.

**fix**: `89fa34d9e` — distinguish `REJECTED` (output contains non-fast-forward/rejected) from `ERROR`. When `acquire_lease` hits ERROR it says plainly "a network fault is not being beaten to the push; this node cannot see the swarm right now, and under fencing it does not touch anything".

**never_again**:
- in a distributed system "I was rejected" and "I did not connect" are two completely different world-views. Flattening them into one boolean necessarily misleads
- the correct fencing posture: **if you cannot see, do not touch**, rather than assuming you lost the race

---

## E016 · A receipt with no timezone was treated as UTC → all 26 real lineages were judged "future time"

| field | value |
|---|---|
| **error_type** | evidence-timezone |
| **status** | closed |
| **related_skill** | cortex-loop |

**symptom**: origin's discovery/result/learning sources were all `OK`, 26 tasks had already settled, and the Dashboard showed `S0 UNKNOWN / S1 UNKNOWN / receipt=0 / invalid=141`.

**root_cause**: Cortex v1 wrote the local wall clock as `2026-07-30T02:45` with no offset. Metrics forced the naive time to be UTC. Shanghai 02:45 was interpreted as UTC 02:45, which relative to the real UTC 18:45 became "8 hours in the future", and the whole discovery batch was rejected.

**fix**:
1. compatible with old books: parse a naive receipt in the local timezone, then convert uniformly to UTC
2. new books: `cortex-loop` writes timezone-aware `%Y-%m-%dT%H:%M%z`
3. a cross-node beat keeps the offset of Git `%ci` and no longer truncates `+0800`
4. negative test: a real local receipt with no offset must still be able to form an S1 canary

**never_again**:
- a distributed-ledger timestamp must carry an offset. "Every machine happens to be in the same timezone right now" is not a contract
- `source=OK` and `evidence=valid` must be shown separately; otherwise a measuring-tool bug is mis-said as "the business did not run"
- the Dashboard's biggest blocker must be ordered by stage state: after S1 has passed, it must not keep telling people to "fill in the lineage"

**Mechanical gate**: `python3 bin/cortex-loop-tests/fixtures/negtest-dashboard-json.py`

---

## E017 · A cohort that existed was displayed as "no sample", and receipt binding was inflated into VERIFIED

| field | value |
|---|---|
| **error_type** | dashboard-evidence-overclaim |
| **status** | closed |
| **related_skill** | cortex-loop |

**symptom**: the same Dashboard showed frozen discoveries/full lineages on one side, and on the other wrote G1 as
`UNMEASURED (no discovery cohort)`. At the same time, a 40-digit `origin_commit` plus two receipt strings matching
was enough to emit `world_verification=VERIFIED`.

**root_cause**:
1. the metrics layer encoded "rolling window not approved" as `denominator=0`, and the display layer interpreted every 0 denominator as "there is no cohort"
2. historical `gate=noop` was scanned across all history before the rolling window was cut, so old books outside the window permanently poisoned G2
3. three evidence layers — "receipt fields bound", "origin branch reachable", "replay the verification command on the spot" — were flattened into one VERIFIED

**fix**:
1. when G1 has no window, show the frozen all-history baseline; `UNMEASURED` only when the eligible cohort is truly empty
2. a legacy gate outside the G2 window enters `unclassified` data debt; an unknown gate inside the window still fails closed
3. an artifact must bind a safe repo-relative path, and mechanically prove that path is a blob in an origin-reachable commit
4. Dashboard uses `receipt_binding=BOUND`, `origin_reachability=REACHABLE`,
   `verification_replay=NOT_REPLAYED`
5. invalid reasons give only a bounded summary and do not repeat the whole package twice in JSON

**never_again**:
- "there is data but the contract is not approved" and "there is no data" are two states
- an evidence name must not exceed the action the verifier actually performed
- historical data debt must be visible, but it must not change the current cohort verdict by crossing the window

**Mechanical gate**: `python3 bin/cortex-loop-tests/fixtures/negtest-dashboard-json.py`

---

## E018 · Improvised work in swarm mode bypassed the ledger — the glass box went blind, and what was covered was only the minority

| Field | Value |
|------|------|
| **id** | E018 |
| **date** | 2026-07-30 |
| **status** | closed (the cause is clear; the fix is T11) |
| **related_skill** | cortex-loop · hive · sub-agent-dispatch |

**symptom**: the `_swarm/orchestrator-laptop.md` profile had `executors: human-in-loop` and
`last_seen: 2026-07-29T15:37` (stopped the previous afternoon). `cortex-loop status` showed
`cortex-immune executor=human blocked=1 pending=9`, and not one `running`. But the same night
that node actually dispatched 8+ HIVE lines and 20+ commits. Checked one by one: of the 8 lines **only T2
corresponded to a task pre-built in the ledger. The other 7** (external-audit remediation, system wiring, hot model switch,
cheap adapter join…) **never appeared in the ledger** — not "forgot to claim". The ledger mechanism
itself covers only "tasks built in advance", and improvised work was the majority of the real work that night (7/8).

**root_cause**: two layers. The shallow one is a symptom of the deep one.
- **Shallow**: `cmd_checkin()` (about line 2363 of `bin/cortex-loop`) **hardcodes** the orchestrator
  node's `executors` field as the string `"human-in-loop"`, regardless of what tools this session
  actually used (including a HIVE sub-agent). HIVE dispatch was implemented as parallel orchestration outside the ledger,
  and the `claim → submit → try-complete` lifecycle was bypassed as a whole.
- **Deep (upgraded by an operator decision on 2026-07-30)**: the swarm lacks a **machine-judgeable membership
  criterion** — whether it is currently in "swarm mode" depends entirely on conscientiousness. And most real work is **thought up
  while doing it**. The existing mechanism works only for work that "already has a task card". Improvised work bypasses it by nature.
  The decision-maker (orchestrator) is registered and yet does not heartbeat and does not claim. The meta-governance layer exempts itself —
  this is empirical proof of what [[steer-doctrine|STEER law]] writes as "the decision-maker does not exempt itself", and of the fact that **writing it down is not
  the same as it being in effect**: the rule is in the document. It is not in the mechanism.

**fix**: not fixed yet. The contract is T11 in `brain-network/directions/cortex-immune/TASKS.md`
(HIVE made into an executor + the orchestrator node seated + improvised work in swarm mode entered in the ledger).
`bin/cortex-loop`, where `cmd_checkin()` hardcodes the string, was not changed this time —
that file had a `select` subcommand added in parallel by another line the same night, to avoid several lines colliding on the same file.

**never_again**:
- **in swarm mode, "does this enter the ledger" cannot be a conscientious act**. There must be a machine criterion plus a default bias.
  When solo versus swarm cannot be told apart, **default to swarm** — a miss hurts more than a false entry
  (a miss = the glass box is permanently blind; a false entry is at most one extra noise record, correctable afterward)
- **a mechanism that covers "pre-built tasks" is not a mechanism that covers "real work"**. Improvised work may be the majority
  (7/8 in this case). When designing the entry mechanism, **the dispatch action itself must generate the task record**,
  not "build the task card first, then do the work" (one more rule, and a person will bypass it) or "backfill afterward" (depends on memory,
  equivalent to not fixing it)
- **scoring cannot record only success**: right and wrong both enter HAAS. Recording only success manufactures a score-farming hole
  (echoes E014 no-op score farming — "all green" is not evidence of health; it may mean nobody is booking the ledger)
- the law "the decision-maker does not exempt itself" counts only when it lands in the mechanical layer. Writing it into a document does not count — this entry
  is the second appearance, in the same system, of "written but not in effect" (the first was before E014's no-op gate
  went live; the rule was likewise written first and landed later)

---

## E019 · Text completion impersonated an executor: the heartbeat was moving, and the task was never executed

| Field | Value |
|------|------|
| **id** | E019 |
| **date** | 2026-07-31 |
| **status** | closed |
| **related_skill** | cortex-loop · bug-master |

**symptom**: the Dashboard kept showing a heartbeat. Tasks repeatedly went from `running` back to `pending`.
The artifact was always missing. Each failure was also postponed four hours by `advance_window_min=240`.

**root_cause**:
1. `cheap.sh` called a raw MiniMax/GLM completion. It could only generate text. It had no Read/Edit/Write/Bash.
2. a non-zero adapter or a failed completion gate still took the success-submit path, so the failure was hidden by the success window.
3. a manual tick and launchd can overlap; after the parent is killed, tool child processes orphan.
4. Claude Code loads plugins/MCP by default. T18 was measured pulling up an unrelated doubao-search and waiting empty for eight minutes.
5. the executing Agent could edit TASKS/short_test directly. T22 was measured writing `done` itself, past the only completion gate.

**fix**:
- `cheap` became a MiniMax-backed Claude Code tool layer. A real Write+Read smoke passed.
- a single-instance tick lock + a cheap worker PID lock; failure takes a 15/30/60/120 minute backoff.
- a tool receipt can be recovered by a later heartbeat; a legacy text receipt is marked `rc=96` and does not enter the completion gate.
- safe-mode + an empty MCP config + plugins/slash skills forbidden + Git writes forbidden.
- the task contract and short_test are frozen before execution; an out-of-authority edit is restored mechanically and recorded as a C1 breach.
- task-add/list/show/retry/run are atomic. Hand-stitching the task table is forbidden.

**mechanical_gate**:
`bash bin/cortex-loop-tests/cheap-tool-smoke.sh` ·
`python3 bin/cortex-loop-tests/fixtures/negtest-execution-control.py` ·
`bash bin/cortex-loop-tests/suite.sh` (49 PASS / 0 FAIL).

**never_again**: execution ability must be proved by "a verifiable change happened in the world". It cannot be proved by a model self-report or a text receipt.
Failure and success must use different time semantics. An unattended executor's plugin surface, Git permission, and completion right are closed by default.

---

## E020 · Repair history was treated as a conflict by metrics, and a control ref was treated as a result event

| Field | Value |
|------|------|
| **id** | E020 |
| **date** | 2026-07-31 |
| **status** | closed |
| **related_skill** | cortex-loop |

**symptom**: Worker/Controller, the suite, and the S1 canary were all advancing, but live autonomy's G1
stayed UNKNOWN for a long time, and G2 was poisoned by a malformed record the moment a rolling window was enabled.

**root_cause**:

1. the Repair Controller's failure→retry against the same frozen discovery produces several terminal attempts;
   G1 judged every different payload a conflicting duplicate outright.
2. `result/<plan>/_settled` is a plan-settlement control ref, but the collector treated it as an ordinary result. With no
   `finished/gate` it made every rolling window UNKNOWN.

**fix**:

- attempts of the same discovery pick the latest by a readable `finished`; strictly identical time and different content stays UNKNOWN.
- the result namespace excludes, at the collection entrance, control refs whose basename starts with `_`.
- G1 and G2 were approved for a 7-day window and a 24-hour window. Cumulative track record stays displayed separately.

**mechanical_gate**:
`negtest-g1-discovery-cohort.py` · `cortex-metrics.py --validate-contract` ·
`autonomy-acceptance.sh`.

**never_again**: a retry is a sequence of events, not duplicate data. A control ref and a business event must be typed
at the namespace collection entrance. "They are both under result/" must not be flattened into one kind of thing.

---

## E021 · A global tick lock spread one long task into a freeze of the whole queue

| Field | Value |
|------|------|
| **symptom** | the Dashboard has a heartbeat and one running, but task-add/resume/submit are all BUSY, and the backlog is no longer claimed |
| **root_cause** | the same `cortex-loop.tick.lock` covered scheduling, a 25-minute LLM, the network, acceptance, and Git; to stop an old snapshot from overwriting, every unrelated task was forced to serialize |
| **fix** | delete the runtime global tick lock; flock the same task; a ledger micro-lock + atomic replace; status `expected_status` CAS; the adapter inherits the task lock; a MiniMax account-level lease; the Git tx protects only the local mutation |
| **mechanical_gate** | suite H23; Git V4 stale/live/index/deploy-outside-lock matrix; full suite |
| **never_again** | minimize a lock to the shared resource: a long task does not hold a global lock. A critical section that crosses network, model, or deploy is a design red flag |
| **related_skill** | cortex-loop |

A three-across, one-down widened search found at the same time: task-add's visible window of publish-then-gate, CC Switch JSON losing updates with no lock,
a Git tx SIGKILL leaving a permanent stale lock, a worker generating a snapshot before the lock, and pre-commit's bare commit manufacturing a lock with no PID. All were fixed together.

---

## E022 · The control plane was already distributed, but Workers still co-wrote the root worktree

| Field | Value |
|------|------|
| **symptom** | several Agents and different Cortex tasks can claim at the same time, yet they fight over the same index/worktree; even after the Git lock was shortened they still pollute each other and queue settlement, and a candidate reachable from any remote branch can still be misjudged done |
| **root_cause** | the ref layer already had a CAS/lease distributed control plane, but every adapter `cd`s the root repo; the execution plane, the candidate plane, and the canonical integration plane were flattened into one root-tree commit |
| **fix** | a sparse linked worktree per attempt (shared objects, private index); an immutable candidate ref; a low-disk blobless integrator; master does only a very short lease-CAS; the completion gate accepts only an exact delivery that can be proved mechanically on canonical master |
| **mechanical_gate** | suite H26–H30: workspace crash recovery, immutable candidate publish, integration dual-write CAS, master landing, delivery-plane stats |
| **never_again** | "reachable from origin" is not "delivered"; "many Workers" is not "able to write in parallel". Different tasks must isolate their index. Only a real write-set overlap and a canonical ref update may serialize |
| **related_skill** | cortex-loop |

Disk measurement: the full object store is about 3.4G, but a Cortex sparse cabin adds 6.4M. So the default is shared objects plus bounded
sparse materialization, not a copy of the full vault. The scheduling goal is to maximize landed throughput under the constraints, not to maximize the surface Worker count.

---

## E023 · Dashboard Ctrl-C batch-killed the GUI through a shadow pkill

| Field | Value |
|------|------|
| **symptom** | after leaving the Dashboard, Finder, Terminal, iTerm2, ChatGPT/Codex, the browser, and others crashed together and a black screen appeared |
| **root_cause** | the EXIT handler called `pkill -P` from PATH; it actually hit an old x86 `proctools/0.4pre1`, which on macOS 26.3 ignores the parent-PID filter and sends SIGTERM to every process the system can reach |
| **fix** | watch became a single foreground synchronous collection, with zero background collector and zero process-tree hunting; the spare screen only displays in place and restores on exit; shadow pgrep/pkill isolated; every running script uses explicit `/usr/bin/pgrep`, and termination accepts only an exact PID |
| **mechanical_gate** | suite H33/H34; a static gate on malicious keywords; PTY SIGINT leaves no residual process group; TTY echo, spare screen, and cursor restored item by item; the watch focus view is ≤34 lines |
| **never_again** | a process lifetime must be held by the creator as an exact handle/PID. PATH is a dependency-injection surface. A safety-critical tool cannot be trusted blind by name |
| **related_skill** | cortex-loop · bug-master |

The system log attributes the two batch terminations explicitly to `pkill[27500]` (63) and `pkill[48487]` (42).
WindowServer high CPU and the Crashpad restart storm are secondary contamination. There is no OOM/Jetsam evidence.

---

## E024 · A V4 tree rollback dropped sparse-index metadata

| Field | Value |
|------|------|
| **symptom** | before the attempt commit failed there was only 1 dirty file; after the failure the Dashboard reported an anomaly and `git status` showed about 29,000 deletions |
| **root_cause** | `write-tree/read-tree` saves only tree content, not the index `skip-worktree` bit; after a sparse worktree rolls back, unmaterialized files are mistaken for deletions |
| **fix** | V4 changed to a raw index-byte snapshot and atomic restore per worktree; old cabin products are archived first, then `sparse-checkout reapply`, then broker release |
| **mechanical_gate** | `test-commit-v4.sh` forces `git ls-files -v` to be identical before and after a hook failure |
| **never_again** | the same tree is not the same index state. Any index rollback must keep extension bits and sparse semantics |
| **related_skill** | git-management · cortex-loop |

---

## E025 · After squash/replay the source commit is unreachable and settling becomes permanent

| Field | Value |
|------|------|
| **symptom** | the artifact and the check have entered canonical master, the short test is all green, and the task keeps showing "waiting for git propagation" |
| **root_cause** | the integrator replays several source commits into one canonical commit; the old completion gate proved landing only by source-OID ancestry, and wrongly bound commit identity to delivered content |
| **fix** | a unified settlement helper first verifies that the local path exists, is non-empty, is tracked, is clean, and is bound to the source commit, then compares the blob OID of `source_commit:path` with `canonical_tip:path` one by one; all matching means `content-equivalent` landed |
| **mechanical_gate** | suite H35: a positive squash/replay case with no ancestry, a different canonical blob, a local dirty edit, a check not landed, and a read-only zero side effect; the completion gate and `task-show --settlement` share the same helper |
| **never_again** | a commit OID is a transport identity, not the content truth. A delivery chain that allows squash/replay must verify the full write set on canonical, not only source-commit ancestry |
| **related_skill** | cortex-loop · git-management |

---

## E026 · A forked candidate had no exact canonical compose entrance

| Field | Value |
|------|------|
| **symptom** | the local semantic commit is done, but its parent chain is behind and forked; handing it straight to the integrator conflicts, leaving only two paths: hand-roll a temporary index, or pollute the shared worktree |
| **root_cause** | the candidate tools had only validate/publish/inspect. They had no compose primitive that "overlays exact files from a source commit onto the latest canonical base" |
| **fix** | `cortex-candidate.sh compose --source OID --base OID --allow FILE...` uses a private temporary index to generate a canonical single-parent candidate; it accepts only exact files, and a missing path or a directory fails closed |
| **mechanical_gate** | suite H30: compose a forked source, keep a file not declared on canonical, reject a missing path, and HEAD plus the shared index are unchanged before and after |
| **never_again** | a forked delivery must have a formal rebase-by-write-set primitive. Temporary plumbing craft must not be an operating procedure, and merging, resetting, or stashing the shared repo to avoid a conflict is forbidden |
| **related_skill** | cortex-loop · git-management |

---

## E027 · A tool existing is not the same as the production producer being wired

| Field | Value |
|------|------|
| **id** | E027 |
| **symptom** | the `record/status` tools and unit tests for an authority breach, an independent-verification counterexample, and a budget overrun all exist, and the task was marked done; days into a real run the production JSONL still does not exist, and the Dashboard can only show UNKNOWN |
| **root_cause** | a weak success contract only verified "a person can hand-write one event". It did not fire the producer from the real bounds/integrator/completion-gate/daily-cap/quota decision point. Capability existence was mistaken for production wiring |
| **fix** | three sources unified into atomic `init/status/record`; narrow-semantic wiring at the real decision points; deterministic event-id idempotence; tests redirect the state directory; H36 covers the positive sample, the false-positive boundary, concurrency, and HOME isolation |
| **never_again** | any claim that "the event source is wired" must be accepted by manufacturing a business event from the production entrance and reading it back from the canonical source. Calling the recorder directly proves only tool capability. It does not prove the mechanism is wired |
| **related_skill** | cortex-loop · cortex-immune |

---

## E028 · A legal schema shape is not a semantically valid calendar value

| Field | Value |
|------|------|
| **id** | E028 |
| **symptom** | an incident JSON has a string `timestamp` that matches the surface format, but a month, day, or time that does not exist can still be treated as a valid event, and health and trust statistics are polluted |
| **root_cause** | the validator checks only field type and regex shape. It does not parse the UTC time into a real calendar value. The structural contract stopped at syntax and never entered semantic validity |
| **fix** | the three incident validators use strict UTC calendar parsing; a bad date returns UNKNOWN and `validate` is non-zero; H36 does a destructive negative test on a calendar value that does not exist |
| **never_again** | fields such as date, amount, enum, ID, and path must validate business semantics. "The type is right / the regex matches" must not stand in for a valid value domain. Every semantic gate needs at least one negative test whose shape is legal and whose value is invalid |
| **related_skill** | cortex-loop · evolve-ecosystem |

---

## E029 · Logical session isolation was wrongly implemented as a full worktree copy

| Field | Value |
|------|------|
| **id** | E029 |
| **date** | 2026-08-16 |
| **status** | closed |
| **symptom** | when a knowledge-handoff session was created for ROSACE/ROSEUM, the Git project default was reused and a full worktree was created. Even with enough disk, it copies the whole OB1, manufactures a duplicate entrance, and scatters knowledge onto the wrong checkout. |
| **root_cause** | the logical isolation of Agent/Topic/Session was mistaken for filesystem worktree isolation. Knowledge handoff, a shared-data task, concurrent code writes, and a high-risk experiment were not distinguished before Hatch. |
| **fix** | Codex sessions that share OB1 uniformly use `target.environment.type=local` and share `${CORTEX_WORKSPACE_ROOT}` directly. Call `bin/cortex-workspace.sh` `--allow` for a sparse workspace only when file isolation is needed and the write set can be listed. A native full worktree is allowed only when the write set is unknown and a concurrent conflict is real. Error entries, rules, reports, and memory are always written back to the main source of truth. |
| **mechanical_gate** | record `target.environment` before creation; a shared OB1 that is not `local` must be refused; after creation, check that the session `cwd` is the main repo and compare `git worktree list`. Count and path must not grow because of a knowledge handoff. Free disk is not a reason to relax. |
| **never_again** | **Session is not a worktree.** Knowledge handoff, brand planning, a read-only audit, a data read, and a cross-runtime migration do not create a worktree by default. "There is enough space" is not a reason to copy the whole repo. |
| **related_skill** | cortex-loop · session-resume · agent-runtime-knowledge-portability |

---

## Capstone lesson · silent degradation is more dangerous than an error

> **E001 / E002 / E003 are the same DNA.**

| Error | What the silent degradation became | Surface appearance |
|------|-----------------|---------|
| E001 | the legend table was treated as the data table | a pile of garbage rows was read, and **there was no error** |
| E002 | header mismatch → the whole table skipped | 0 rows returned, **exit code 0** |
| E003 | the ref layer read empty → fell back to the file snapshot | `beat=True` and everything looks normal, **it is just missing one node** |

All three times: **the function was broken, and the program claimed it was fine.** The form is "the result is wrong", not "the command failed", so:
- the exit code lies → an upper `if code == 0` clears it
- the log lies → a person reading the log thinks it is running
- the more automated the system, the more destructive a silent degradation is — because **nobody is standing there watching**

**Required actions (written into all new cortex-loop code)**:

1. **every fallback / skip / fall-back branch must `print(..., file=sys.stderr)` and make a sound** (the E003 fix was adding that line)
2. **"read 0 items" must be distinguishable from "there really were 0 items"**. They cannot share one return value
3. **if you cannot get it, return `None`, never an empty string** — an empty string gets spliced silently into a command (E004 nearly deleted a remote ref)
4. **health and self-check code forbids `except: pass`** — `run()`'s `except` branch explicitly returns `(1, str(exc))`, and the comment is written dead: "a self-check must not turn silently green because of an exception"

---

## Errors → Layer 0 laws (which pit gave birth to which law)

> The six laws added on 2026-07-29 **were not laws first and an implementation second**. They were forced out after these errors kept reappearing.
> Read it backward: hit a class of symptom → first see whether the matching law has mechanical backing that can stop the next time.

| Error | Law it produced or confirmed | Mechanical backing |
|------|--------------|---------|
| E009 a CAS rejection and a network fault flattened into one return value · E013 five collapses in one day · E015 the fourth state `moot` had nowhere to land | [[dimensional-expansion-doctrine\|DIMENSIONAL]] (= SKILL T7) | `bin/cortex-loop-tests/dimensional-collapse-scan.sh` |
| E010 a long run bound to the terminal · four hand-rolled measuring tools failed (`grep -E` OR / a pipe swallowed the exit code / `ls` with multiple paths) | [[atomize-tools-doctrine\|ATOMIZE]] | `bin/cortex-probe.sh` (10 three-state probes) · `cortex-loop-detach.sh` |
| E011 false completion: short_test reused the scanner exit code + the verifier failed open | [[pulse-doctrine\|PULSE]] question L, "passing a mechanical gate is not a self-report" (= T3/T4) | `bin/cortex-pulse.sh` · `autonomy-acceptance.sh` |
| E012 an interactive shell can run it does not mean unattended can run it | [[pulse-doctrine\|PULSE]] question P, "is the system still running" (= T2) | `bin/cortex-loop-tests/env-parity.sh` |
| E014 no-op score farming: a criterion already met still counted as passed | [[ground-first-doctrine\|GROUND]] step U, "inspection intensity follows trust" (= T9) | no-op gate + `moot` ref + `inspection_mode()` |
| E005 treating "delivery failed" as "execution failed" · E007 "the log is continuous" misread as "it has been running" | [[glassbox-doctrine\|GLASSBOX]] human and machine read one truth | `bin/cortex-dashboard.sh --json` · `bin/cortex-trace.sh` |
| "I am not in the ledger" = the meta-governance layer exempts itself by default | [[steer-doctrine\|STEER]] the decision-maker is in the ledger too | `orchestrator-*` node + `fault` / `credit` |

The six-law chain and the full table are in [[cortex-loop/SKILL|SKILL.md]] §related Layer 0 laws. The full cost of the hard rules is in [[cortex-loop/references/tenets|references/tenets.md]].

---

## Nav

| Document | Relation |
|------|------|
| [[cortex-loop/SKILL\|SKILL.md]] | main document |
| [[cortex-loop/JOURNAL\|JOURNAL.md]] | build journal (the order these errors happened) |
| [[cortex-loop/EXPECTATIONS\|EXPECTATIONS.md]] | not done yet (including debts distilled from this file's never_again) |
| [[cortex-loop-intent]] | heartbeat charter |
| [[cortex-loop-cron-error-triage]] | the per-item evidence source for E005 |
| [[recipe-and-errors-contract]] | this file's field contract |

---

*Established: 2026-07-28 | E001–E007 are all same-day evidence from 2026-07-28, each with a commit sha*

---

<!-- cortex:map-backlink d-8ae6ef1fbe379db0a350896a -->
Related map: [[skills/cortex-loop/MAP|Cortex Loop panorama]]

## E030 · The fixed 4+3+2 was overwritten by concurrency slots, and a Codex child seat crossed the bound

**Symptom**: GLASSBOX did not show provider/model/provenance seat by seat. The orchestrator mistook an idle concurrency slot for permission to add a Codex worker, and Codex quota was consumed wrongly.

**Root cause**: the runtime had no fixed-formation admission gate. The main thread, the Codex child cap, and inherited model provenance were not hard-checked before dispatch.

**Fix**: `formation-boundary.test.mjs` runs before any dispatch; `codex.slot_cap=1`; every new Codex child is explicitly `gpt-5.6-luna`; an old inherited seat whose model is unknown is UNKNOWN; anything that does not satisfy the rule is BLOCKED.

**never_again**: the fixed 4+3+2 roster must be checked mechanically before dispatch. The main thread does not count as an execution seat. A Codex child can be only 1 seat and must be explicit Luna. GLASSBOX must show provider/model/provenance/cooldown seat by seat. An Eval failure is BLOCKED.

**related_skill**: cortex-loop · hive-orchestrator · codex-master

## E031 · Snapshot drift and a wrong repo-boundary judgment during cleanup normalization

**Symptom**: the same cleanup round showed 135, then 140, then 142 worktrees. A batch audit treated crossing viewpoints as mutually exclusive division of labor, and mixed worktrees under `${CORTEX_WORKSPACE_ROOT}/` that actually belong to Cortex Harness together with OB1 worktrees.

**Root cause**: parallel execution adds and reclaims worktrees, and an old number kept being used as the current denominator. The disposition list lacked Git common-dir, remote, whether it is registered, snapshot time, and a unique owner field.

**Fix**: Cortex cleanup has two layers: first freeze an exact snapshot and build a per-item manifest, then generate mutually exclusive execution batches from the manifest. Ownership is recognized only by `git worktree list --porcelain` + `git rev-parse --git-common-dir` + remote. An item whose common-dir is OB1 is never touched. Deletion must, on the latest reread of the same item, be clean, have no lock, have no live process, have no lease, not be canonical, and have no unmigrated value, all at once. Otherwise it is kept as `ARCHIVE_REVIEW`.

**never_again**: do not treat an old snapshot number as the current fact; do not judge the repo by the path name; do not let a cross-audit worker delete directly; do not treat a `MIGRATE` intention as already migrated; do not force-restore a runtime already deleted from the canonical tree when the migration conflicts.

**Extra hard gate**: before an execution batch starts, reread the registry, HEAD, dirty/lock, live processes, and leases. If the worktree count or canonical HEAD has changed, the old disposition list is immediately invalid. Generate a new snapshot first, then continue.

## E033 · Clean is not deletable

**Symptom**: a worktree with a clean `git status` was treated as a valueless copy, ignoring code, tests, a branch recovery path, or an integration file not yet taken in that it alone has relative to canonical.

**Root cause**: filesystem cleanliness, code value, and recoverability were flattened into one boolean, and a wrong baseline was used to interpret a large historical deletion diff.

**Hard fix**: clean may enter only a value review. Separately check the real file diff of `canonical...HEAD`, whether it is only probe/evidence, whether it has unique code/tests, whether the commit is still kept by a ref, and whether current canonical already has a later implementation. A worktree may be archived only when its unique value has been migrated, or it is clearly valueless and recoverable. Dirty, locked, active, or an undecided lease is always HOLD.

**never_again**: do not trigger deletion from clean, an old date, a directory name, or the words "already done" alone.

## E034 · Cleaning a worktree and discarding a code object must be separated

**Symptom**: an old worktree was deleted directly to save disk, so a commit that still needed review had no recovery path; or, the other way, directories were never cleaned because of fear of losing objects.

**Hard fix**: first prove canonical already contains the later implementation, then reread clean, lock, active process, lease, and branch/ref on the spot. After writing an archive ref, remove only the redundant worktree, keep the original branch/ref by default, and finally confirm independently that the registry no longer lists the target path. Deleting a branch needs separate explicit evidence and authorization.

**never_again**: do not mix "remove the worktree" and "delete the branch / discard the commit" into one action.

**Extra sample**: a probe-only detached tree may be removed after the archive ref is kept. A code/test tree must still enter a value and reachability review. It cannot be batch-deleted because of the same directory prefix.

## E032 · Worktree registration separated from the actual Git common-dir

**Symptom**: the canonical registry still listed a directory, but that directory's `.git` already pointed at another temporary repo. A direct canonical `git worktree remove` was refused.

**Root cause**: a registry path was mistaken for proof of ownership. Common-dir, remote, and owner-side worktree metadata were not reread before a destructive disposition.

**Hard fix**: a validation failure stops that item immediately. First judge whether the target belongs to another repo. A cross-repo target is handled by its owner. If it is only a stale registration, prune it alone. Use recoverable Trash only when the directory is clearly valueless and clean/inactive. The remote branch is kept. The canonical registry is reviewed again.

**never_again**: do not retry a hard delete against a cross-common-dir target, do not treat an orphan directory as canonical code, and do not promote one successful remove into "the whole cleanup is done".

## E035 · The second review round had no atomic, rerunnable snapshot gate

**Symptom**: the first round's experience was written into documents, but the second round still depended on a person re-stitching paths, counts, and the disposition list. After parallel workers changed the registry, the old list kept being treated as the current state.

**Root cause**: there was no unified read-only snapshot tool that binds, in one pass, canonical HEAD, Git common-dir/remote, worktree state, processes, lease/ref, the exact diff, and a unique classification. A document is a rule. It cannot replace an execution gate.

**Hard fix**: take `snapshot_id + canonical_head` as input. An atomic tool reads the registry on the spot and emits a stable JSON manifest and a unique `disposition` per item. Clean/dirty/locked/active/value/reachability are recorded on separate axes. Any drift of HEAD or the registry returns `STALE_SNAPSHOT`. The tool cannot delete, prune, migrate, or promote a classification into authorization.

**Acceptance**: negative cases cover a stale snapshot, dirty, locked, unknown owner/runtime, fsmonitor exclusion, and the OB1 boundary. Repeating the same snapshot keeps fields and classification stable. The output can be reused directly by the next round of workers and by an independent Guardian.

**never_again**: the second round does not copy the first round's prose list. Run the atomic snapshot tool first, then review by mutually exclusive scope. No machine manifest means no disposition.

---

## E023 · Only rules and reports were written; no actual action was taken (2026-09-06)

**Symptom**: the correction rule, plan, or report was written completely, but Gate A, the contract check, the DeepSeek three-seat live check, and the independent read-back were not carried on, and finishing the document was called finishing the task.

**Root cause**: the evidence/report layer was treated as the execution layer. A plan, a dry-run, an ACK, or a model self-report was treated as a real action and as settlement evidence.

**Hard fix**: actual completion must bind the target action, the scope, independent verification, and a read-back. No action can only be `PLAN_ONLY` / `REPORT_ONLY`. A missing external gate can only be `BLOCKED`. A failure keeps the first blocker, the owner, and the repair/replay next step.

**never_again**: a recurring name misunderstanding or ASR goes to NameGuard and codex-master #006. Not actually executing goes to Agent Anti-Bureaucracy and codex-master #007. The two root causes are diagnosed separately and accepted separately. They cannot be waved through with one long report.
