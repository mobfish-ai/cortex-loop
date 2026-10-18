#!/usr/bin/env python3
"""cortex-loop expectations reader -- so dashboard / CI can machine-read EXPECTATIONS.md.

Design constraints (three; drop one and it degrades):
  1. Three states do not collapse (DIMENSIONAL): met / gap / unknown stay side by side.
     unknown never falls over to met (fail-open) or to gap (too conservative).
  2. Carry the error (ATOMIZE): if the table cannot be parsed, exit code 2 plus an explanation; do not silently return an empty list.
     "cannot read the file" and "the file has no gap" are two different facts.
  3. Humans and machines read one source of truth (GLASSBOX): the only data source is EXPECTATIONS.md itself.
     Do not keep a second JSON -- two copies will diverge.

IMM-T67 fixes:
  - Table-aware column splits (a pipe inside backticks is not a separator), so EX19
    `grep -qE 'budget orchestration|usage API|window timing'` does not truncate short_test on its `|`.
  - Check that the short_test command can run (syntax check + anti-pattern block); an illegal command
    is forced ineligible, so a poisoned command cannot enter the promote pipeline.
  - EX19 state is derived from `bin/cortex-budget-incident.sh status`, not from a handwritten literal
    in a markdown cell (removes the "copy a second budget truth" failure_mode).

Usage:
  python3 bin/cortex-loop-expectations.py            # human-readable summary
  python3 bin/cortex-loop-expectations.py --json     # machine-readable (dashboard / CI)
  python3 bin/cortex-loop-expectations.py --id EX01  # one item

Exit code: 0=all met | 1=has gap | 2=has unknown or parse failure (cannot tell is not a pass)
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOC = ROOT / "skills" / "cortex-loop" / "EXPECTATIONS.md"

STATES = ("met", "gap", "unknown")
ROW_RE = re.compile(r"^\|\s*(EX\d+)\s*\|(.+)$")
SECTION_RE = re.compile(r"^##\s+([A-D])\s*·\s*(.+?)\s*$")

# ── IMM-T67: table column-boundary awareness ─────────────────────────────
# Find `|` positions that really separate markdown columns -- skip pipes inside backtick spans
# and inside wiki-link targets. EX19's `grep -qE 'budget orchestration|usage API|window timing'`
# then keeps its inner pipes, so short_test is not truncated.
_BACKTICK_RE = re.compile(r"`([^`]*)`")
_HREF_PIPE_RE = re.compile(r"\[\[([^\]|]+)\|([^\]]+)\]\]")


def strip_md(cell: str) -> str:
    """Strip markdown emphasis/link wrappers and keep the readable text."""
    cell = _HREF_PIPE_RE.sub(r"\2", cell)
    cell = re.sub(r"\[\[([^\]]+)\]\]", r"\1", cell)
    cell = cell.replace("**", "").replace("`", "")
    return cell.strip()


def _mask_inner_pipes(line: str) -> str:
    """Replace `|` inside backtick spans with \\x00 so they are not treated as column separators."""
    def _sub(m: re.Match) -> str:
        return "`" + m.group(1).replace("|", "\x00") + "`"
    return _BACKTICK_RE.sub(_sub, line)


def column_count(line: str) -> int:
    """Count `|` that really separate columns (skip backtick spans / wiki aliases).

    Walk characters with an "inside backtick / wiki" state machine. That is more robust than slicing by header position:
    header column widths and data column widths differ, so positions cannot be reused.
    """
    n = len(line)
    count = 0
    backtick = False
    wiki = False
    i = 0
    while i < n:
        ch = line[i]
        if ch == "`":
            backtick = not backtick
            i += 1
            continue
        if backtick:
            i += 1
            continue
        if ch == "[" and i + 1 < n and line[i + 1] == "[":
            wiki = True
            i += 2
            continue
        if wiki and ch == "|" and i + 1 < n and line[i + 1] != "]":
            # skip the | inside a wiki alias
            i += 1
            continue
        if wiki and ch == "]" and i + 1 < n and line[i + 1] == "]":
            wiki = False
            i += 2
            continue
        if ch == "|" and not wiki:
            count += 1
            i += 1
            continue
        i += 1
    return count


def smart_split_row(line: str) -> list:
    """Split a markdown table row into columns -- skip `|` inside backticks and wiki aliases.

    Returns the cell list (including the decorative empty cells at both ends); length equals column_count(line).
    """
    cells = []
    cur = []
    n = len(line)
    backtick = False
    wiki = False
    i = 0
    while i < n:
        ch = line[i]
        if ch == "`":
            backtick = not backtick
            cur.append(ch)
            i += 1
            continue
        if backtick:
            cur.append(ch)
            i += 1
            continue
        if ch == "[" and i + 1 < n and line[i + 1] == "[":
            wiki = True
            cur.append(ch)
            cur.append(line[i + 1])
            i += 2
            continue
        if wiki and ch == "]":
            cur.append(ch)
            if i + 1 < n and line[i + 1] == "]":
                cur.append(line[i + 1])
                i += 2
                wiki = False
                continue
            i += 1
            continue
        if ch == "|" and not wiki:
            cells.append("".join(cur).strip())
            cur = []
            i += 1
            continue
        cur.append(ch)
        i += 1
    if cur:
        cells.append("".join(cur).strip())
    return cells


# ── IMM-T67: short_test command check ────────────────────────────────────
def validate_short_test(st: str) -> tuple:
    """Return (ok, reason). An illegal command becomes ineligible.

    Rules:
      1. Must not be empty, must not be only shell metacharacters, must not contain a bare newline (truncation signal).
      2. Run `bash -n -c <cmd>` as a syntax check; non-zero exit = broken syntax.
      3. Reject fake-green prefixes such as `|| true` / `; exit 0`.
      4. Reject a comment-only / echo-ok command that tests nothing.
    """
    if not st:
        return False, "empty"
    if "\n" in st and not st.rstrip().endswith(("fi", "esac", "done", "}", ")", "\"")):
        # multiline, but the last line is not closed -- truncation signal
        return False, "truncated-multiline"
    # anti-cheat: fake-green prefixes that are explicitly banned
    banned_prefixes = (
        "true && ", "true||", ": &&", "exit 0",
        "|| true", "; true", "&& true",
    )
    for bp in banned_prefixes:
        if bp in st:
            return False, f"fake-green-prefix:{bp.strip()}"
    # must contain at least one real command character (letter / digit / dot / slash)
    if not re.search(r"[A-Za-z0-9./]", st):
        return False, "no-command-chars"
    # comment only (empty after removing # and spaces) = tests nothing; reject
    body = re.sub(r"#.*", "", st).strip()
    if not body:
        return False, "comment-only-noop"
    # syntax check: call bash -n
    bash = shutil.which("bash")
    if bash:
        try:
            proc = subprocess.run(
                [bash, "-n", "-c", st],
                capture_output=True, text=True, timeout=5,
            )
            if proc.returncode != 0:
                return False, f"bash-syntax-fail:{(proc.stderr or '').strip()[:80]}"
        except (subprocess.TimeoutExpired, OSError):
            return False, "bash-syntax-timeout"
    return True, "ok"


# ── IMM-T67: EX19 state is derived from budget-incident ──────────────────
def resolve_ex19_state() -> tuple:
    """Derive EX19 state: (state, source_state, observed_events).

    Rules:
      source UNKNOWN  → state=unknown   (orchestration has not recorded evidence yet)
      source OK       → state=met       (orchestration exists and has zero events)
      source BREACH   → state=gap       (orchestration recorded a real event)
    """
    script = ROOT / "bin" / "cortex-budget-incident.sh"
    if not script.exists():
        return "unknown", "UNKNOWN", None
    try:
        proc = subprocess.run(
            [str(script), "status"], capture_output=True, text=True, timeout=10,
            cwd=str(ROOT),
        )
    except (subprocess.TimeoutExpired, OSError):
        return "unknown", "UNKNOWN", None
    if proc.returncode != 0 or not proc.stdout.strip():
        return "unknown", "UNKNOWN", None
    try:
        data = json.loads(proc.stdout.strip().splitlines()[-1])
    except Exception:
        return "unknown", "UNKNOWN", None
    src_state = data.get("state", "UNKNOWN")
    observed = data.get("observed_events")
    if src_state == "OK":
        return "met", src_state, observed
    if src_state == "BREACH":
        return "gap", src_state, observed
    return "unknown", src_state, observed


def detect_state(cells) -> str:
    """State must come from a **standalone state cell** (the whole cell equals met, gap, or unknown).

    Do not search the whole row for a substring -- a citation such as "CHARTER-SWARM §Unknown" in the prose
    would misread a gap as unknown (EX19 hit this in practice).
    If no standalone state cell is found, return unknown. Never default to met (fail-closed).
    """
    for cell in cells:
        # State cells are human-facing Markdown and often use **met** emphasis.
        # Detection must normalize presentation without weakening the exact-cell
        # rule; otherwise a visually valid row silently collapses to unknown.
        token = strip_md(cell).lower().rstrip("\u3002.")
        if token in STATES:
            return token
    return "unknown"


def parse(path: Path):
    if not path.exists():
        return None, f"EXPECTATIONS.md does not exist: {path}"
    section = ""
    headers = []
    header_cols = 0
    items = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        sec = SECTION_RE.match(raw_line)
        if sec:
            section = f"{sec.group(1)} · {sec.group(2)}"
            headers = []
            header_cols = 0
            continue
        stripped = raw_line.lstrip()
        if stripped.lower().startswith("| id |"):
            headers = [strip_md(c).lower() for c in smart_split_row(raw_line)]
            header_cols = column_count(raw_line)
            continue
        m = ROW_RE.match(raw_line.strip())
        if not m:
            continue
        if not headers:
            # data row before any header -- defensive
            continue
        row_cells = smart_split_row(raw_line)
        # A data row can have more real columns than the header when a cell contains `|`.
        # That is the truncation signal IMM-T67 wants to expose -- mark ineligible.
        row_real_cols = column_count(raw_line)
        truncated = row_real_cols > header_cols
        # Still slice to the header width and keep the first header_cols cells
        cells = row_cells[:header_cols] if len(row_cells) >= header_cols else row_cells
        # Older expectation rows legitimately omit the trailing owner/short_test
        # columns. Preserve the known fact and pad the absent automation contract;
        # dropping the entire row made Dashboard undercount reality. Missing
        # contract fields remain mechanically non-eligible below.
        if len(cells) < len(headers):
            cells += [""] * (len(headers) - len(cells))
        mapped = dict(zip(headers, cells))
        owner = mapped.get("owner")
        short_test = mapped.get("short_test")
        owner = None if owner in (None, "", "-") else owner
        short_test = None if short_test in (None, "", "-") else short_test

        ex_id = m.group(1)
        # IMM-T67: EX19 state is derived from budget-incident
        if ex_id == "EX19":
            derived, src_state, observed = resolve_ex19_state()
            state = derived
            ex19_sync = {
                "ex_id": ex_id,
                "derived_state": state,
                "budget_source_state": src_state,
                "observed_events": observed,
                "rule": "budget-incident UNKNOWN→unknown; OK→met; BREACH→gap",
            }
        else:
            state = detect_state(cells)
            ex19_sync = None

        # IMM-T67: validate short_test -- illegal becomes ineligible
        if short_test:
            v_ok, v_reason = validate_short_test(short_test)
        else:
            v_ok, v_reason = False, "empty"
        # IMM-T67: truncation (a pipe inside a cell makes real columns > header columns) is also illegal
        if truncated and short_test:
            v_ok, v_reason = False, "truncated-cell-pipe-leak"
        eligible = (state != "met") and bool(owner and short_test and v_ok)

        item = {
            "id": ex_id,
            "section": section,
            "state": state,
            "fields": cells,
            "owner": owner,
            "short_test": short_test,
            "eligible": eligible,
        }
        if not v_ok and short_test:
            item["short_test_invalid"] = v_reason
        if truncated:
            item["truncated_by_pipe_leak"] = True
        if ex19_sync:
            item["ex19_sync"] = ex19_sync
        items.append(item)
    if not items:
        return None, "parsed 0 expectations -- the table format may have changed; this is a fault, not 'nothing owed'"
    return items, None


def main() -> int:
    ap = argparse.ArgumentParser(description="Read cortex-loop EXPECTATIONS.md (three states)")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--id", help="show one item, e.g. EX01")
    args = ap.parse_args()

    items, err = parse(DOC)
    if err:
        if args.json:
            print(json.dumps({"ok": False, "error": err, "state": "unknown"},
                             ensure_ascii=False))
        else:
            print(f"⚠️  UNKNOWN — {err}", file=sys.stderr)
        return 2

    if args.id:
        items = [i for i in items if i["id"] == args.id.upper()]
        if not items:
            msg = f"no such item: {args.id}"
            print(json.dumps({"ok": False, "error": msg, "state": "unknown"},
                             ensure_ascii=False) if args.json else f"⚠️  UNKNOWN — {msg}")
            return 2

    counts = {s: sum(1 for i in items if i["state"] == s) for s in STATES}
    code = 1 if counts["gap"] else (2 if counts["unknown"] else 0)

    if args.json:
        print(json.dumps(
            {"ok": True, "source": str(DOC.relative_to(ROOT)), "total": len(items),
             "counts": counts, "exit": code, "items": items},
            ensure_ascii=False))
        return code

    print(f"cortex-loop expectations | {DOC.relative_to(ROOT)}")
    print(f"{len(items)} items | met {counts['met']} | gap {counts['gap']} "
          f"| unknown {counts['unknown']}")
    print("─" * 60)
    mark = {"met": "✅", "gap": "❌", "unknown": "❓"}
    cur = None
    for i in items:
        if i["section"] != cur:
            cur = i["section"]
            print(f"\n▸ {cur}")
        head = i["fields"][0] if i["fields"] else ""
        print(f"  {mark[i['state']]} {i['id']} {head[:70]}")
    print("\nexit code 0=all met | 1=has gap | 2=has unknown (cannot tell is not a pass)")
    return code


if __name__ == "__main__":
    sys.exit(main())
