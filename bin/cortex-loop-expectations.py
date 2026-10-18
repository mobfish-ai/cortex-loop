#!/usr/bin/env python3
"""cortex-loop 期待清单读取器 —— 让 dashboard / CI 能机读 EXPECTATIONS.md。

设计约束（三条，缺一即退化）：
  1. 三态不坍缩（DIMENSIONAL）：met / gap / unknown 三态并列，
     unknown 绝不倒向 met（fail-open）也不倒向 gap（过度保守）。
  2. 携带错题（ATOMIZE）：解析不到表格 → 退出码 2 + 说明，不静默返回空清单。
     「读不到文件」和「文件里没有 gap」是两件完全不同的事。
  3. 人机同读一份真相（GLASSBOX）：唯一数据源是 EXPECTATIONS.md 本身，
     不维护第二份 JSON —— 两套必然分叉。

IMM-T67 修补：
  - 表格感知的列切分（管道符在 backtick 内不计为分隔符），避免 EX19
    `grep -qE '预算编排|usage API|窗口计时'` 内的 `|` 把 short_test 截断。
  - 校验 short_test 命令可执行性（语法检查 + 反模式拦截）；不合法命令
    强制 ineligible，不让带毒命令混进 promote 流水线。
  - EX19 状态由 `bin/cortex-budget-incident.sh status` 推导，不靠 markdown
    表格单元里的手写字面（消除「复制第二份预算真相」failure_mode）。

用法：
  python3 bin/cortex-loop-expectations.py            # 人读摘要
  python3 bin/cortex-loop-expectations.py --json     # 机读（dashboard / CI）
  python3 bin/cortex-loop-expectations.py --id EX01  # 单条

退出码：0=全部 met · 1=有 gap · 2=有 unknown 或解析失败（判不出来 ≠ 通过）
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

# ── IMM-T67: 表格列边界感知 ──────────────────────────────────────────────
# 找到 markdown 表格中真正作为列分隔的 `|` 位置 —— 跳过 backtick 包裹的代码段
# 与 `&` 链接目标里的 `|`。这样 EX19 的 `grep -qE '预算编排|usage API|窗口计时'`
# 里的内部管道符不会把 short_test 截断。
_BACKTICK_RE = re.compile(r"`([^`]*)`")
_HREF_PIPE_RE = re.compile(r"\[\[([^\]|]+)\|([^\]]+)\]\]")


def strip_md(cell: str) -> str:
    """去掉 markdown 强调/链接壳，保留可读文本。"""
    cell = _HREF_PIPE_RE.sub(r"\2", cell)
    cell = re.sub(r"\[\[([^\]]+)\]\]", r"\1", cell)
    cell = cell.replace("**", "").replace("`", "")
    return cell.strip()


def _mask_inner_pipes(line: str) -> str:
    """把 backtick 代码段里的 `|` 替换成 \\x00，避免被当作列分隔符。"""
    def _sub(m: re.Match) -> str:
        return "`" + m.group(1).replace("|", "\x00") + "`"
    return _BACKTICK_RE.sub(_sub, line)


def column_count(line: str) -> int:
    """数出 markdown 行里真正作为列分隔的 `|` 个数（跳过 backtick / wiki alias）。

    用「在不在 backtick / wiki 里」的状态机走字符，比「按 header 位置切」更鲁棒：
    header 列宽与 data 列宽不同，位置根本不能复用。
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
            # wiki alias 的 | 跳过去
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
    """按 markdown 表格列切分行 —— 跳过 backtick 与 wiki alias 内的 `|`。

    返回 cell 列表（含首尾装饰空 cell）；长度等于 column_count(line)。
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


# ── IMM-T67: short_test 命令校验 ─────────────────────────────────────────
def validate_short_test(st: str) -> tuple:
    """返回 (ok, reason)。不合法命令 → ineligible。

    规则：
      1. 不可为空、不可只含 shell 元字符、不可含裸换行（截断信号）。
      2. 调用 `bash -n -c <cmd>` 做语法检查；非 0 退出 = 语法坏。
      3. 拒收带 `|| true` / `; exit 0` 的假绿前缀。
      4. 拒收纯注释 / echo ok 这种「什么也不测」的命令。
    """
    if not st:
        return False, "empty"
    if "\n" in st and not st.rstrip().endswith(("fi", "esac", "done", "}", ")", "\"")):
        # 多行但最后一行未正常收尾 —— 截断信号
        return False, "truncated-multiline"
    # 反作弊：明确禁掉的假绿前缀
    banned_prefixes = (
        "true && ", "true||", ": &&", "exit 0",
        "|| true", "; true", "&& true",
    )
    for bp in banned_prefixes:
        if bp in st:
            return False, f"fake-green-prefix:{bp.strip()}"
    # 必须含至少一个真实命令字符（字母 / 数字 / 点 / 斜杠）
    if not re.search(r"[A-Za-z0-9./]", st):
        return False, "no-command-chars"
    # 纯注释（去掉 # 与空格后为空）= 什么也不测，应拒收
    body = re.sub(r"#.*", "", st).strip()
    if not body:
        return False, "comment-only-noop"
    # 语法检查：调用 bash -n
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


# ── IMM-T67: EX19 状态由 budget-incident 推导 ────────────────────────────
def resolve_ex19_state() -> tuple:
    """EX19 state 推导：(state, source_state, observed_events)。

    规则：
      source UNKNOWN  → state=unknown   （orchestration 尚未落证据）
      source OK       → state=met       （orchestration 存在且零事件）
      source BREACH   → state=gap       （orchestration 真实记录到事件）
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
    """状态必须来自**独立的状态格**（整格等于 met/gap/unknown 之一）。

    刻意不做全行子串搜索 —— 正文里出现「CHARTER-SWARM §Unknown」这种引用
    会把一条 gap 误判成 unknown（实测 EX19 踩过）。
    找不到独立状态格 → unknown，绝不默认 met（fail-closed）。
    """
    for cell in cells:
        # State cells are human-facing Markdown and often use **met** emphasis.
        # Detection must normalize presentation without weakening the exact-cell
        # rule; otherwise a visually valid row silently collapses to unknown.
        token = strip_md(cell).lower().rstrip("。.")
        if token in STATES:
            return token
    return "unknown"


def parse(path: Path):
    if not path.exists():
        return None, f"EXPECTATIONS.md 不存在：{path}"
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
            # 没见到 header 就来数据行 —— 防御
            continue
        row_cells = smart_split_row(raw_line)
        # 数据行的真实列数可能因 cell 内含 `|` 而多于 header 列数，
        # 那正是 IMM-T67 想暴露的「截断」信号 —— 标记 ineligible。
        row_real_cols = column_count(raw_line)
        truncated = row_real_cols > header_cols
        # 但我们还是按 header 列宽来切，取前 header_cols 个 cell
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
        # IMM-T67: EX19 状态由 budget-incident 推导
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

        # IMM-T67: 校验 short_test —— 不合法 → ineligible
        if short_test:
            v_ok, v_reason = validate_short_test(short_test)
        else:
            v_ok, v_reason = False, "empty"
        # IMM-T67: 截断（cell 内 pipe 让真实列数 > header 列数）也算不合法
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
        return None, "解析到 0 条期待 —— 表格格式可能已变，这是故障不是「没有欠账」"
    return items, None


def main() -> int:
    ap = argparse.ArgumentParser(description="读 cortex-loop EXPECTATIONS.md（三态）")
    ap.add_argument("--json", action="store_true", help="机读输出")
    ap.add_argument("--id", help="只看某一条，如 EX01")
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
            msg = f"没有这一条：{args.id}"
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

    print(f"cortex-loop 期待清单 ｜ {DOC.relative_to(ROOT)}")
    print(f"共 {len(items)} 条 ｜ met {counts['met']} · gap {counts['gap']} "
          f"· unknown {counts['unknown']}")
    print("─" * 60)
    mark = {"met": "✅", "gap": "❌", "unknown": "❓"}
    cur = None
    for i in items:
        if i["section"] != cur:
            cur = i["section"]
            print(f"\n▸ {cur}")
        head = i["fields"][0] if i["fields"] else ""
        print(f"  {mark[i['state']]} {i['id']} {head[:70]}")
    print("\n退出码 0=全部 met · 1=有 gap · 2=有 unknown（判不出来 ≠ 通过）")
    return code


if __name__ == "__main__":
    sys.exit(main())
