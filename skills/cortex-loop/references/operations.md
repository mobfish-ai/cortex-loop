English | [简体中文](operations.zh-CN.md)

# cortex-loop operations manual (new line / clock deploy / full command table / cohabitation index)

> **When to read this**: you are opening a new direction line, installing or checking the three clocks, you want a full command cheatsheet,
> or you are looking for "what other documents belong to this system".
> **Parent**: [[cortex-loop/SKILL|SKILL.md]]

---

## Open a new direction line (SOP)

1. `mkdir brain-network/directions/<line>/`
2. Write `INTENT.md` — frontmatter must contain `line · status · created · updated · claim · success_criteria · out_of_scope · related`, and the body has the seven sections `Why / Done / Proof / Anti / Bounds / Trade / Unknown`
3. Add a row to [[CLOCK]]: **`executor` is always `human` first** (safe default; deliver, do not execute)
4. `bin/cortex-loop decompose --line <line>` → check that `TASKS.proposed.md` is right → `--apply` to merge
5. `bin/cortex-loop reconcile` and confirm DRIFT=0
6. Run a few human rounds until it looks right, then change `executor` to `claude` / `codex` / `cheap`
7. **L2 headless (acp-lane)**: write `CLOCK.executor=acp-lane` for the whole line, or `requires_executor=acp-lane` on a single task (it wins over the line default). Run it straight from a terminal: `bash bin/acp-policy-client.sh run --topic T --backend grok --cwd /tmp/xxx --prompt "…"`. cwd=vault root is forbidden. Acceptance: `bash bin/verify-acp-l2-grok-mvp.sh`

Hard field rules are in [[cortex-loop/references/contracts|contracts.md]].

---

## Three clocks (launchd · duties are orthogonal)

| Clock | Period | What it does | plist |
|------|------|--------|-------|
| `com.cortex.loop` | **900s** | **advances** tasks (does the work) | `work-studio/devops/dotfiles/launchd/com.cortex.loop.plist` |
| `com.cortex.pulse` | **3600s** | **checks** the health trend (the five P·U·L·S·E questions) | `…/com.cortex.pulse.plist` |
| `com.cortex.ci` | **every day at 09:30** | **constrains** drift (full test suite + goal anchor) | `…/com.cortex.ci.plist` |

**Check the live clocks**: `bash bin/cortex-trace.sh clocks` · `bin/cortex-loop reconcile` (declaration vs reality; a split reports DRIFT)
The chosen time and the LATCH basis are in [[cortex-loop/references/architecture|architecture.md]] §why the five tools are orthogonal.

---

## Full command cheatsheet

```bash
# ── heartbeat and ledger ──────────────────────────────
bin/cortex-loop tick                                     # see what is due (does not advance)
bin/cortex-loop tick --auto                              # actually advance (launchd runs this every 900s)
bin/cortex-loop next --line loop-ops --claim             # take the prompt + take the slot
bin/cortex-loop submit --line loop-ops --task T2 --result /tmp/r.txt
bin/cortex-loop try-complete --line loop-ops --task T2   # the only command that can write done
bin/cortex-loop status
bin/cortex-loop idle                                     # honest idle rate (the denominator excludes sleep ticks)

# ── self-check and reconcile ──────────────────────────────
bin/cortex-loop health
bin/cortex-loop reconcile
bin/cortex-loop why                                      # why trust was judged this way
bin/cortex-loop value                                    # V1/V2/V3 + leverage

# ── swarm ────────────────────────────────────
bin/cortex-loop swarm                                    # who is online, which line has no owner
bin/cortex-loop sync                                     # ref-layer heartbeat (does not touch the worktree)
bin/cortex-loop caps                                     # capability matrix + single-point capability alert
bin/cortex-loop lease --line loop-ops
bin/cortex-loop checkin        /  checkin --out          # main thread joins / leaves

# ── decentralized dispatch ────────────────────────────
bin/cortex-loop discover --publish
bin/cortex-loop plan  /  claim  /  run  /  result  /  gather --settle

# ── trust and constraint ──────────────────────────────
bin/cortex-loop trust
bin/cortex-loop attest --executor claude
bin/cortex-loop fault  /  credit
bin/cortex-loop readjudicate                             # rejudge historical rejected after the criterion is tightened
bin/cortex-loop model

# ── five tools (look up the tool first; do not hand-roll) ────────────────
bash bin/cortex-probe.sh list              # 10 probes, three-state YES/NO/UNKNOWN
bash bin/cortex-trace.sh wiring            # internal wiring: discover→rank→claim→admit→execute→completion gate
bash bin/cortex-trace.sh task <id>         # one task's full lifecycle
bash bin/cortex-trace.sh state / clocks / chain ci / history [days]
bash bin/cortex-dashboard.sh               # one-screen overview (--json machine-readable / --watch resident / --md writes a living md)
bash bin/cortex-pulse.sh                   # periodic checkup (exit code 2 = regressed since last time)
bash bin/cortex-ci.sh                      # daily constraint (exit code 2 = a goal was loosened)

# ── tests ────────────────────────────────────
bash bin/cortex-loop-tests/env-parity.sh
bash bin/cortex-loop-tests/suite.sh                      # 36 PASS / 0 FAIL / 1 SKIP (live run 2026-07-29)
bash bin/cortex-loop-tests/autonomy-acceptance.sh        # A1-A6 autonomous closed-loop acceptance
bash bin/cortex-loop-tests/dimensional-collapse-scan.sh  # dimensional-collapse scan (T7 mechanical backing)

# ── detach a long run from the terminal (a session crash does not take it down · E010) ──
bin/cortex-loop-detach.sh <name> "<command>"
bin/cortex-loop-detach.sh --status <name>   /  --wait  /  --list

# ── contract gate ──────────────────────────────────
python3 bin/knowledge-contract-gate.py check-path brain-network/directions/CLOCK.md --strict
python3 bin/knowledge-contract-gate.py check-path skills/cortex-loop/SKILL.md
```

---

## Related documents (cohabitation index)

| Kind | Path | Note |
|------|------|------|
| **Charter report** | [[cortex-loop-intent]] | canonical reading entry: intent / three parts / SHIFT / 7 red→green live checks |
| **Swarm charter** | [[brain-network/directions/loop-ops/CHARTER-SWARM\|CHARTER-SWARM]] | goals G1–G6 / scope / out_of_scope; **ci uses it to check that goals were not loosened** |
| **Expectations list** | [[cortex-loop/EXPECTATIONS\|EXPECTATIONS.md]] | should be done and still is not (machine-readable `--json`) |
| Pilot-line output | [[cortex-loop-cron-error-triage]] | loop-ops T1: 10 error jobs, five root-cause classes |
| Engine | `bin/cortex-loop` | python3, zero LLM (1093 lines at the 07-28 close → 4125 lines on 07-29) |
| Muscle | `bin/cortex-loop-adapters/{human,claude,codex,ollama,mock}.sh` | the only channel that calls an LLM |
| Five tools | `bin/cortex-{probe,trace,dashboard,pulse,ci}.sh` | see SKILL.md §toolbox |
| Helpers | `bin/cortex-loop-detach.sh` · `bin/cortex-loop-mcp.py` | detach from the terminal with tmux · MCP exit |
| Three clocks | `work-studio/devops/dotfiles/launchd/com.cortex.cortex-{loop,pulse,ci}.plist` | 900s / 3600s / every day at 09:30 |
| Tests | `bin/cortex-loop-tests/suite.sh` + `fixtures/negtest-*.py` | 8 negative tests, each proved by a destructive check to "actually go red" |
| Schedule declaration | [[CLOCK]] | changing this table changes the schedule |
| Pilot line | [[brain-network/directions/loop-ops/INTENT\|loop-ops INTENT]] · [[brain-network/directions/loop-ops/INTENT-P2\|INTENT-P2]] · [[brain-network/directions/loop-ops/TASKS\|TASKS]] | the loop repairs its own foundation |
| Contract registry | [[knowledge-contract-registry]] §4.12 / §4.12a | see [[cortex-loop/references/contracts\|contracts.md]] |
| Collaboration laws | [[mobfish-six-laws]] | source of truth for the C1/C2/C3 three gates + the V1/V2/V3 three value laws |
| Error log | [[cortex-loop/ERRORS\|ERRORS.md]] | E001–E015, including "silent degradation is more dangerous than an error" |
| Build journal | [[cortex-loop/JOURNAL\|JOURNAL.md]] | 07-28 from zero to a two-node swarm · 07-29 from swarm to an autonomous closed loop |

---

## Nav

[[cortex-loop/SKILL|SKILL.md]] · [[cortex-loop/references/commands|commands]] · [[cortex-loop/references/architecture|architecture]] · [[cortex-loop/references/swarm|swarm]] · [[cortex-loop/references/contracts|contracts]]

---

<!-- cortex:map-backlink d-6907ff16c7030089e243be51 -->
Related map: [[skills/cortex-loop/MAP|Cortex Loop panorama]]
