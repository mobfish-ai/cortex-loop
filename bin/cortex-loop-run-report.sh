#!/usr/bin/env bash
# cortex-loop-run-report — 每次跑批后自动吐「精简但可对账」报告
#
# 铁律：数字只来自 TASKS 账本 + /tmp/spotlight 结果文件 + cortex-loop 日志。
# 时长三口径分列，禁止混用 claim→done 当「干活速度」。
# token 查不到必须写 UNKNOWN，禁止编造。
#
# 用法：
#   bin/cortex-loop-run-report.sh --line cortex-immune
#   bin/cortex-loop-run-report.sh --line cortex-immune --id-min 34 --id-max 44
#   bin/cortex-loop-run-report.sh --line cortex-immune --out reports/2026-07-31/cortex-loop/run.md
#   bin/cortex-loop-run-report.sh --line cortex-immune --json
#
# 退出码：0=报告生成  1=参数错  2=关键数据探不清（仍尽量输出）
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT" || exit 1

LINE=""
ID_MIN=""
ID_MAX=""
OUT=""
JSON=0
PREFIX=""  # e.g. IMM-T — auto-detect from line tasks

usage() {
  sed -n '2,18p' "$0" | sed 's/^# \{0,1\}//'
  exit 1
}

while [ $# -gt 0 ]; do
  case "$1" in
    --line) LINE="${2:?}"; shift 2 ;;
    --id-min) ID_MIN="${2:?}"; shift 2 ;;
    --id-max) ID_MAX="${2:?}"; shift 2 ;;
    --out) OUT="${2:?}"; shift 2 ;;
    --json) JSON=1; shift ;;
    -h|--help) usage ;;
    *) echo "unknown arg: $1" >&2; usage ;;
  esac
done

[ -n "$LINE" ] || { echo "需要 --line" >&2; usage; }

export CORTEX_REPORT_LINE="$LINE"
export CORTEX_REPORT_ID_MIN="${ID_MIN:-}"
export CORTEX_REPORT_ID_MAX="${ID_MAX:-}"
export CORTEX_REPORT_JSON="$JSON"
export CORTEX_REPORT_OUT="${OUT:-}"
export CORTEX_REPORT_ROOT="$ROOT"

python3 - <<'PY'
import json, os, re, statistics, subprocess, sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(os.environ["CORTEX_REPORT_ROOT"])
LINE = os.environ["CORTEX_REPORT_LINE"]
ID_MIN = os.environ.get("CORTEX_REPORT_ID_MIN") or ""
ID_MAX = os.environ.get("CORTEX_REPORT_ID_MAX") or ""
JSON_MODE = os.environ.get("CORTEX_REPORT_JSON") == "1"
OUT = os.environ.get("CORTEX_REPORT_OUT") or ""
TZ = timezone(timedelta(hours=8))
unknowns = []

def parse_ts(s):
    s = (s or "").strip()
    if not s or s == "-":
        return None
    for fmt in ("%Y-%m-%dT%H:%M%z", "%Y-%m-%dT%H:%M"):
        try:
            t = datetime.strptime(s, fmt)
            return t if t.tzinfo else t.replace(tzinfo=TZ)
        except ValueError:
            continue
    return None

def clock_row(line):
    p = ROOT / "brain-network/directions/CLOCK.md"
    if not p.is_file():
        return {}
    for row in p.read_text(encoding="utf-8", errors="replace").splitlines():
        if not row.startswith("|"):
            continue
        cols = [c.strip() for c in row.strip("|").split("|")]
        if len(cols) >= 6 and cols[0] == line:
            return {
                "enabled": cols[1],
                "executor": cols[2],
                "advance_window_min": cols[3],
                "max_advance_per_day": cols[4],
                "owner": cols[5],
                "driver": cols[6] if len(cols) > 6 else "",
            }
    return {}

def load_tasks(line):
    p = ROOT / f"brain-network/directions/{line}/TASKS.md"
    if not p.is_file():
        return []
    hdr = None
    rows = []
    for line_s in p.read_text(encoding="utf-8", errors="replace").splitlines():
        if line_s.startswith("| id |") or (line_s.startswith("|") and "short_test" in line_s and "status" in line_s and hdr is None):
            hdr = [c.strip() for c in line_s.strip("|").split("|")]
            continue
        if not line_s.startswith("|") or hdr is None:
            continue
        cols = [c.strip() for c in line_s.strip("|").split("|")]
        if len(cols) < len(hdr):
            continue
        if cols[0] in ("id", "----") or cols[0].startswith("-"):
            continue
        d = dict(zip(hdr, cols))
        if d.get("id") and d.get("status"):
            rows.append(d)
    return rows

def id_num(tid):
    m = re.search(r"(\d+)$", tid or "")
    return int(m.group(1)) if m else None

def in_range(tid):
    n = id_num(tid)
    if n is None:
        return True
    if ID_MIN and n < int(ID_MIN):
        return False
    if ID_MAX and n > int(ID_MAX):
        return False
    return True

tasks = [t for t in load_tasks(LINE) if in_range(t.get("id", ""))]
if not tasks:
    # if filter empty, fall back all + warn
    tasks = load_tasks(LINE)
    if ID_MIN or ID_MAX:
        unknowns.append("id 过滤无命中，已回退为该线全部任务")

by_status = {}
for t in tasks:
    by_status.setdefault(t.get("status", "?"), []).append(t["id"])

# --- logs ---
log_paths = [
    Path("/tmp/spotlight/cortex-loop.log"),
    Path.home() / ".openclaw/state/cortex-loop.launchd.log",
    Path("/tmp/spotlight/cortex-loop.manual-kick.log"),
    Path("/tmp/spotlight/cortex-loop.post-fix-tick.log"),
]
claim_re = re.compile(
    rf"(\d{{4}}-\d{{2}}-\d{{2}}T\d{{2}}:\d{{2}}(?:[+-]\d{{4}})?)\s*\|\s*claim\s+{re.escape(LINE)}/(\S+)"
)
done_re = re.compile(
    rf"(\d{{4}}-\d{{2}}-\d{{2}}T\d{{2}}:\d{{2}}(?:[+-]\d{{4}})?)\s*\|\s*done\s+{re.escape(LINE)}/(\S+)"
)
fail_re = re.compile(
    rf"(\d{{4}}-\d{{2}}-\d{{2}}T\d{{2}}:\d{{2}}(?:[+-]\d{{4}})?)\s*\|\s*attempt FAIL\s+{re.escape(LINE)}/(\S+)"
)
# failure stage from result files
stage_re = re.compile(r'"stage":\s*"([^"]+)"')
detail_re = re.compile(r'"detail":\s*"([^"]{0,200})"')

events = []  # (ts, kind, tid, extra)
for lp in log_paths:
    if not lp.is_file():
        continue
    try:
        text = lp.read_text(encoding="utf-8", errors="replace")
    except OSError:
        continue
    for line_s in text.splitlines():
        for rx, kind in ((claim_re, "claim"), (done_re, "done"), (fail_re, "fail")):
            m = rx.search(line_s)
            if not m:
                continue
            tid = m.group(2)
            if not in_range(tid):
                continue
            ts = parse_ts(m.group(1))
            if ts:
                events.append((ts, kind, tid, str(lp)))

# worker prompt→result
workers = []  # (tid, mins, t0, t1)
spot = Path("/tmp/spotlight")
fails_detail = []  # (tid, stage, detail_snip)
for prompt in spot.glob(f"cortex-loop-{LINE}-*.prompt"):
    # cortex-loop-cortex-immune-IMM-T34.prompt
    name = prompt.name
    # extract task id after last known pattern
    m = re.search(r"cortex-loop-%s-(.+)\.prompt$" % re.escape(LINE), name)
    if not m:
        continue
    tid = m.group(1)
    if not in_range(tid):
        continue
    result = prompt.with_suffix(".result")
    if not result.is_file():
        continue
    t0, t1 = prompt.stat().st_mtime, result.stat().st_mtime
    if t1 <= t0:
        continue
    mins = (t1 - t0) / 60.0
    if 0 < mins < 24 * 60:
        workers.append((tid, mins, t0, t1))
    try:
        rtext = result.read_text(encoding="utf-8", errors="replace")
    except OSError:
        continue
    if "attempt-fail" in rtext or "artifact-clean" in rtext or "FAIL" in rtext:
        st = stage_re.search(rtext)
        de = detail_re.search(rtext)
        fails_detail.append((
            tid,
            st.group(1) if st else "unknown",
            (de.group(1) if de else rtext[-200:].replace("\n", " "))[:160],
        ))
    # tokens
    # leave for aggregate

# token hunt（IMM-T45：优先 [usage] footer，避免与正文重复计数）
token_input = token_output = None
token_sources = 0
usage_lines = 0
usage_unknown = 0
tok_re = re.compile(
    r'"(?:input_tokens|prompt_tokens)"\s*:\s*(\d+)|"(?:output_tokens|completion_tokens)"\s*:\s*(\d+)|total_tokens["\s:=]+(\d+)',
    re.I,
)
for result in spot.glob(f"cortex-loop-{LINE}-*.result"):
    m = re.search(r"cortex-loop-%s-(.+)\.result$" % re.escape(LINE), result.name)
    if not m or not in_range(m.group(1)):
        continue
    try:
        rtext = result.read_text(encoding="utf-8", errors="replace")
    except OSError:
        continue
    saw_usage_footer = False
    for line in rtext.splitlines():
        if not line.startswith("[usage]"):
            continue
        usage_lines += 1
        saw_usage_footer = True
        try:
            payload = json.loads(line[len("[usage]"):].strip())
        except Exception:
            usage_unknown += 1
            continue
        st = str(payload.get("status", "")).upper()
        if st == "UNKNOWN" or (
            payload.get("input_tokens") in (None, "UNKNOWN")
            and payload.get("output_tokens") in (None, "UNKNOWN")
        ):
            usage_unknown += 1
            continue
        # 每个 footer 只计一对 in/out（prompt/completion 别名不双计）
        got_in = got_out = False
        for key, acc in (("input_tokens", "in"), ("prompt_tokens", "in"),
                         ("output_tokens", "out"), ("completion_tokens", "out")):
            v = payload.get(key)
            if not isinstance(v, (int, float)):
                continue
            if acc == "in" and not got_in:
                token_input = (token_input or 0) + int(v)
                got_in = True
                token_sources += 1
            elif acc == "out" and not got_out:
                token_output = (token_output or 0) + int(v)
                got_out = True
                token_sources += 1
    if saw_usage_footer:
        continue
    # 无 footer 时回退扫正文（旧 result）
    for mm in tok_re.finditer(rtext):
        token_sources += 1
        if mm.group(1):
            token_input = (token_input or 0) + int(mm.group(1))
        if mm.group(2):
            token_output = (token_output or 0) + int(mm.group(2))

if token_sources == 0:
    if usage_lines:
        token_note = (
            f"UNKNOWN（{usage_lines} 条 [usage] footer 均为 UNKNOWN/不可解析；"
            f"energy 诚实缺数，非 0）"
        )
    else:
        token_note = "UNKNOWN（result 无 usage/token 字段；cheap 未强制吐 JSON）"
else:
    token_note = (
        f"input≈{token_input} output≈{token_output} "
        f"(解析命中 {token_sources} 处；[usage]行={usage_lines} unknown行={usage_unknown})"
    )

# claim→done durations
from collections import defaultdict
claims = defaultdict(list)
dones = defaultdict(list)
fails_n = defaultdict(int)
for ts, kind, tid, _ in events:
    if kind == "claim":
        claims[tid].append(ts)
    elif kind == "done":
        dones[tid].append(ts)
    elif kind == "fail":
        fails_n[tid] += 1

claim_done_mins = []
for tid, dts in dones.items():
    for dt in sorted(dts):
        before = [c for c in claims.get(tid, []) if c <= dt]
        if before:
            claim_done_mins.append((tid, (dt - before[-1]).total_seconds() / 60.0))

# busy/idle: merge claim→fail/done intervals
busy_iv = []
open_c = {}
for ts, kind, tid, _ in sorted(events, key=lambda x: x[0]):
    if kind == "claim":
        open_c[tid] = ts
    elif kind in ("fail", "done") and tid in open_c:
        busy_iv.append((open_c[tid], ts))
        del open_c[tid]

def merge_iv(ivs):
    if not ivs:
        return []
    ivs = sorted(ivs)
    out = [[ivs[0][0], ivs[0][1]]]
    for a, b in ivs[1:]:
        if a <= out[-1][1]:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return out

merged = merge_iv(busy_iv)
busy_min = sum((b - a).total_seconds() for a, b in merged) / 60.0 if merged else 0.0
all_ts = [e[0] for e in events]
if all_ts:
    wall_start, wall_end = min(all_ts), max(all_ts)
    wall_min = (wall_end - wall_start).total_seconds() / 60.0
    idle_min = max(0.0, wall_min - busy_min)
else:
    wall_start = wall_end = None
    wall_min = idle_min = None
    unknowns.append("日志无 claim/done 事件，墙钟/闲忙 UNKNOWN")

worker_mins = [m for _, m, _, _ in workers]
# last per tid for median
last_w = {}
for tid, m, _, _ in workers:
    last_w[tid] = m
wvals = list(last_w.values())

def fmt_stats(vals):
    if not vals:
        return "UNKNOWN（无样本）"
    vals = sorted(vals)
    mean = sum(vals) / len(vals)
    med = vals[len(vals) // 2]
    return f"n={len(vals)} 均={mean:.1f}min 中位={med:.1f}min 最小={vals[0]:.1f} 最大={vals[-1]:.1f}"

clock = clock_row(LINE)
try:
    node = subprocess.check_output(
        [str(ROOT / "bin/cortex-loop"), "node-id"], text=True, timeout=15
    ).strip().splitlines()[-1]
except Exception:
    node = "UNKNOWN"
    unknowns.append("node-id 探不清")

n_total = len(tasks)
n_done = len(by_status.get("done", []))
n_pending = len(by_status.get("pending", []))
n_running = len(by_status.get("running", []))
n_wait = len(by_status.get("waiting_external", []))
n_blocked = len(by_status.get("blocked", []))
n_fail_events = sum(fails_n.values())

# settle-first heuristic: done without claim in window
done_ids = set(by_status.get("done", []))
claimed = set(claims.keys())
settle_only = sorted(done_ids - claimed) if done_ids else []

now = datetime.now(TZ)
title_range = ""
if ID_MIN or ID_MAX:
    title_range = f" · id {ID_MIN or '*'}–{ID_MAX or '*'}"

md = []
md.append(f"# 跑批报告 · {LINE}{title_range}")
md.append("")
md.append(f"> 生成：`bin/cortex-loop-run-report.sh` · {now.strftime('%Y-%m-%d %H:%M %z')}")
md.append("")
md.append("## TL;DR")
md.append("")
md.append("| 项 | 值 |")
md.append("|----|-----|")
md.append(f"| 账本任务数（过滤后） | **{n_total}** |")
md.append(f"| done | **{n_done}** |")
md.append(f"| pending / running | {n_pending} / {n_running} |")
md.append(f"| waiting_external / blocked | {n_wait} / {n_blocked} |")
md.append(f"| attempt FAIL 次数（日志） | {n_fail_events} |")
md.append(f"| 节点（本机） | {node} |")
md.append(f"| CLOCK owner / executor | {clock.get('owner','?')} / {clock.get('executor','?')} |")
if wall_min is not None:
    md.append(f"| 墙钟跨度 | **{wall_min:.0f} min**（{wall_start.strftime('%H:%M')}→{wall_end.strftime('%H:%M')}） |")
    md.append(f"| busy / idle（claim 占用） | **{busy_min:.0f} / {idle_min:.0f} min**（{100*busy_min/wall_min:.0f}% / {100*idle_min/wall_min:.0f}%） |")
else:
    md.append("| 墙钟 / busy / idle | UNKNOWN |")
md.append(f"| worker 中位（prompt→result） | **{(sorted(wvals)[len(wvals)//2] if wvals else float('nan')):.1f} min**" if wvals else "| worker 中位 | UNKNOWN |")
if wvals:
    md[-1] = f"| worker 中位（prompt→result） | **{sorted(wvals)[len(wvals)//2]:.1f} min**（均 {sum(wvals)/len(wvals):.1f}，n={len(wvals)}） |"
md.append(f"| token | {token_note} |")
md.append("")

md.append("## 在哪跑")
md.append("")
md.append(f"- **线**：`{LINE}`")
md.append(f"- **本机 node-id**：`{node}`")
md.append(f"- **CLOCK**：owner=`{clock.get('owner','?')}` executor=`{clock.get('executor','?')}` "
          f"window={clock.get('advance_window_min','?')}min cap/day={clock.get('max_advance_per_day','?')} "
          f"driver=`{clock.get('driver','?')}`")
if settle_only:
    md.append(f"- **settle-first 嫌疑**（done 但日志无 claim）：{', '.join(settle_only[:20])}"
              + ("…" if len(settle_only) > 20 else ""))
else:
    md.append("- **settle-first 嫌疑**：无（或过滤后无）")
md.append("")

md.append("## 时长三口径（禁止混用）")
md.append("")
md.append("| 口径 | 结果 | 用途 |")
md.append("|------|------|------|")
if wall_min is not None:
    md.append(f"| ① 墙钟总跨度 | {wall_min:.1f} min | 整场日历时间 |")
    md.append(f"| ①b busy/idle | {busy_min:.1f} / {idle_min:.1f} min | 有没有 claim 在飞 |")
else:
    md.append("| ① 墙钟 / busy/idle | UNKNOWN | — |")
md.append(f"| ② worker prompt→result | {fmt_stats(wvals)} | **评价干活速度** |")
cd_vals = [m for _, m in claim_done_mins]
# unique last per tid
last_cd = {}
for tid, m in claim_done_mins:
    last_cd[tid] = m
md.append(f"| ③ claim→done | {fmt_stats(list(last_cd.values()))} | 仅解释日历被拉长 |")
md.append("")
md.append("> ② 才是效率 KPI；③ 含失败重试/等人修门，**不能**当平均干活时间。")
md.append("")

if wvals:
    md.append("### worker 明细")
    md.append("")
    md.append("| 任务 | min |")
    md.append("|------|-----|")
    for tid in sorted(last_w.keys(), key=lambda x: (id_num(x) or 0, x)):
        md.append(f"| {tid} | {last_w[tid]:.1f} |")
    md.append("")

md.append("## 失败清单（result/日志）")
md.append("")
if fails_detail or fails_n:
    md.append("| 任务 | FAIL 次数(log) | stage(result) | detail 摘要 |")
    md.append("|------|----------------|---------------|-------------|")
    # merge
    stages = {}
    for tid, st, de in fails_detail:
        stages[tid] = (st, de)
    tids = sorted(set(list(fails_n) + list(stages)), key=lambda x: (id_num(x) or 0, x))
    for tid in tids:
        if not in_range(tid):
            continue
        st, de = stages.get(tid, ("—", "—"))
        md.append(f"| {tid} | {fails_n.get(tid, 0)} | {st} | {de.replace('|', '/')} |")
else:
    md.append("（过滤范围内无 attempt FAIL 样本，或日志不在本机 /tmp）")
md.append("")

md.append("## 队列终态（账本）")
md.append("")
for st in ("pending", "running", "done", "waiting_external", "blocked"):
    ids = by_status.get(st, [])
    md.append(f"- **{st}** ({len(ids)}): {', '.join(ids[:30]) or '—'}"
              + ("…" if len(ids) > 30 else ""))
md.append("")

md.append("## 证据路径")
md.append("")
md.append(f"- 账本：`brain-network/directions/{LINE}/TASKS.md`")
md.append("- 日志：`/tmp/spotlight/cortex-loop.log` · `~/.openclaw/state/cortex-loop.launchd.log`")
md.append(f"- worker 现场：`/tmp/spotlight/cortex-loop-{LINE}-*.{{prompt,result}}`")
md.append("- 本脚本：`bin/cortex-loop-run-report.sh`")
if unknowns:
    md.append("")
    md.append("## UNKNOWN / 数据缺口")
    md.append("")
    for u in unknowns:
        md.append(f"- {u}")
md.append("")
md.append("---")
md.append("*自动生成 · 禁止把推测写成确定数字*")

text = "\n".join(md) + "\n"

payload = {
    "line": LINE,
    "generated_at": now.isoformat(),
    "counts": {
        "total": n_total,
        "done": n_done,
        "pending": n_pending,
        "running": n_running,
        "waiting_external": n_wait,
        "blocked": n_blocked,
        "fail_events": n_fail_events,
    },
    "node": node,
    "clock": clock,
    "wall_min": wall_min,
    "busy_min": busy_min if wall_min is not None else None,
    "idle_min": idle_min if wall_min is not None else None,
    "worker_stats": fmt_stats(wvals),
    "claim_done_stats": fmt_stats(list(last_cd.values())),
    "token": token_note,
    "unknowns": unknowns,
    "markdown": text,
}

if JSON_MODE:
    print(json.dumps({k: v for k, v in payload.items() if k != "markdown"}, ensure_ascii=False, indent=2))
    print(text)
else:
    print(text)

if OUT:
    outp = Path(OUT)
    if not outp.is_absolute():
        outp = ROOT / outp
    outp.parent.mkdir(parents=True, exist_ok=True)
    # light frontmatter for vault reports if under reports/
    if "reports/" in str(outp):
        fm = (
            "---\n"
            f"date: {now.strftime('%Y-%m-%d')}\n"
            f"owner: {os.environ.get('CORTEX_REPORT_OWNER', 'operator')}\n"
            f"report_id: cortex-loop-run-{LINE}\n"
            "status: final\n"
            "topic: cortex-loop\n"
            f"campaign: {LINE}\n"
            "---\n\n"
            "## Timeline\n\n"
            f"| 时间 | 事件 |\n|------|------|\n"
            f"| {now.strftime('%Y-%m-%d %H:%M')} | run-report 自动生成 line={LINE} |\n\n"
        )
        outp.write_text(fm + text, encoding="utf-8")
    else:
        outp.write_text(text, encoding="utf-8")
    print(f"\n[wrote] {outp}", file=sys.stderr)

sys.exit(2 if unknowns and wall_min is None else 0)
PY
