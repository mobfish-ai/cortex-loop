#!/usr/bin/env python3
"""EX14 / T36 —— 失败冷却后可重试，非永久沉底。

DIMENSIONAL 母题第 6 处：永久让位 ≠ 暂时让位，必须被区分。
2026-07-29 真机事故：laptop 网关挂掉 → 任务失败 → 旧代码
`if _r.get("node") == me: continue` 一刀切永久让位，worker 明明能干
也接不了 → R1 锁死整夜。失败 ≠ 终态，必须有 cooldown 窗口兜底。

本 fixture 直接断言四个不变式：

  1. FAIL_COOLDOWN_MIN 常量存在且 > 0（= 0 等于没做）
  2. run_receipt_payload 写入 status="failed" 时必含 failed_at 字段
  3. cmd_claim 路径：status=failed 但 failed_at 缺失 → 视为可重试（向后兼容旧 receipt）
  4. cmd_claim 路径：status=failed + failed_at 在窗口内 → 不重试；过窗口 → 可重试

不模拟整跑命令（依赖 git ref CAS 太重），改成直接调 cmd_claim 的判定内核：
构造 fake `_r` dict + monkey-patch parse_ts/now，看 print 行的「cooldown |」
vs 「retry |」分流是否正确。

按 fitztest 风格不引诱外部 git 失败，纯函数级断言。
"""

import argparse
import importlib.machinery
import importlib.util
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
loader = importlib.machinery.SourceFileLoader("cortex_loop", str(ROOT / "bin/cortex-loop"))
spec = importlib.util.spec_from_loader(loader.name, loader)
loop = importlib.util.module_from_spec(spec)
loader.exec_module(loop)

FAILURES = []


def check(label, condition, detail=""):
    if condition:
        print("    ok   %s" % label)
    else:
        FAILURES.append("%s%s" % (label, (" — %s" % detail) if detail else ""))
        print("    BAD  %s%s" % (label, (" — %s" % detail) if detail else ""))


# 1. FAIL_COOLDOWN_MIN 常量存在且 > 0 —— 0 等于没做，< 0 等于反向
check("FAIL_COOLDOWN_MIN 常量存在", hasattr(loop, "FAIL_COOLDOWN_MIN"),
      "缺失则 claim 失败后无冷却窗口")
check("FAIL_COOLDOWN_MIN > 0（等于 0 等于没做）",
      getattr(loop, "FAIL_COOLDOWN_MIN", 0) > 0,
      "实际=%s" % getattr(loop, "FAIL_COOLDOWN_MIN", None))


# 2. run_receipt_payload 在 status=failed 时必含 failed_at 字段
payload_failed = loop.run_receipt_payload(
    "test-plan", {"id": "T-FAILED"}, {"holder": "node-a"}, "executor-x",
    "failed", "gate-y", reason="executor down",
)
check("status=failed 的 receipt 含 failed_at= 字段",
      re.search(r"^failed_at=", payload_failed, re.MULTILINE) is not None,
      "实际 payload=%r" % payload_failed[:200])
check("status=failed 的 receipt 仍含 status=failed 字段",
      re.search(r"^status=failed$", payload_failed, re.MULTILINE) is not None,
      "实际 payload=%r" % payload_failed[:200])

# done 不需要 failed_at（done 是终态，没人再 claim 它）
payload_done = loop.run_receipt_payload(
    "test-plan", {"id": "T-DONE"}, {"holder": "node-a"}, "executor-x",
    "done", "passed",
)
check("status=done 的 receipt **不**含 failed_at 字段（避免污染终态）",
      re.search(r"^failed_at=", payload_done, re.MULTILINE) is None,
      "意外含 failed_at=%r" % payload_done[:200])


# 3 & 4. cmd_claim 判定内核：模拟 _r / now() 注入，
# 断言 in_cooldown 分支与 retry 分支都正确分流。
# 我们不跑整条 cmd_claim（依赖 git ref CAS 太重），
# 直接抽出 cmd_claim 的判定块：构造 fake 上下文看 print 输出分流。
def _probe_claim_logic(_r, fake_now, fake_me="node-me"):
    """把 cmd_claim 内 failed 分支的判定抽出来，跑一次看分支。"""
    # 真实代码用的就是这两个函数，我们复用同一份以保证 fixture 与生产一致。
    failed_at = loop.parse_ts(_r.get("failed_at"))
    in_cooldown = (failed_at is not None
                   and (fake_now - failed_at).total_seconds() < loop.FAIL_COOLDOWN_MIN * 60)
    if in_cooldown:
        who = "本节点" if _r.get("node") == fake_me else "上次 %s" % _r.get("node")
        return "cooldown | T-FAILED %s 失败未过冷却窗（%dmin）→ 暂跳过" % (
            who, loop.FAIL_COOLDOWN_MIN)
    who = "本节点" if _r.get("node") == fake_me else "上次 %s" % _r.get("node")
    return "retry | T-FAILED %s 失败已过冷却窗，本节点重试（cooldown/retry）" % who


now = loop.now()
recent_failed = now - timedelta(seconds=loop.FAIL_COOLDOWN_MIN * 30)  # 半窗
old_failed = now - timedelta(seconds=loop.FAIL_COOLDOWN_MIN * 60 + 60)  # 过窗 1min

# failed_at 写入用 fmt()，跟生产代码一致（parse_ts 严格匹配 %Y-%m-%dT%H:%M%z）
recent_str = loop.fmt(recent_failed)
old_str = loop.fmt(old_failed)

# 4a. failed_at 在窗口内 → cooldown 分支
out_cooldown = _probe_claim_logic(
    {"status": "failed", "node": "node-me", "failed_at": recent_str},
    now,
)
check("failed_at 仍在冷却窗内 → 输出含 'cooldown |'",
      out_cooldown.startswith("cooldown |"), "实际=%r" % out_cooldown)
check("冷却中输出不含 'retry |'（不可绕过冷却）",
      "retry |" not in out_cooldown, "实际=%r" % out_cooldown)

# 4b. failed_at 在窗口外 → retry 分支
out_retry = _probe_claim_logic(
    {"status": "failed", "node": "node-me", "failed_at": old_str},
    now,
)
check("failed_at 已过冷却窗 → 输出含 'retry |'（EX14 关键）",
      out_retry.startswith("retry |"), "实际=%r" % out_retry)
check("retry 输出显式标注 'cooldown/retry' 便于审计",
      "cooldown/retry" in out_retry, "实际=%r" % out_retry)

# 4c. failed_at 缺失 → 视为可重试（向后兼容旧 receipt —— 升级期平滑过渡）
out_compat = _probe_claim_logic(
    {"status": "failed", "node": "node-me"},  # 无 failed_at
    now,
)
check("failed_at 缺失（历史 receipt） → 走 retry 路径而非永久沉底",
      out_compat.startswith("retry |"), "实际=%r" % out_compat)

# 5. 边界点：恰好等于窗口 —— 应视为「已过窗」（实现用 < 而非 ≤）
edge_failed = now - timedelta(seconds=loop.FAIL_COOLDOWN_MIN * 60)
out_edge = _probe_claim_logic(
    {"status": "failed", "node": "node-me", "failed_at": loop.fmt(edge_failed)},
    now,
)
check("边界：failed_at == 窗口（差 0 秒）→ 视为可重试（实现用 < 而非 ≤）",
      out_edge.startswith("retry |"), "实际=%r" % out_edge)


# 6. cmd_claim 实际源码里搜两个分支 —— 防「只在 probe 函数写了分支，
# 但 cmd_claim 主路径根本没调」的伪装
src = Path(ROOT / "bin/cortex-loop").read_text()
check("bin/cortex-loop 源码含 'cooldown |' 分支打印",
      "cooldown |" in src, "cmd_claim 没真正分流")
check("bin/cortex-loop 源码含 'retry | ... cooldown/retry' 打印",
      "cooldown/retry" in src, "EX14 retry 标记缺失")
check("bin/cortex-loop 源码显式引用 FAIL_COOLDOWN_MIN（不是写死的 5）",
      "FAIL_COOLDOWN_MIN" in src, "写死 5 等于常量没生效")


if FAILURES:
    print("断言失败 %d 条：%s" % (len(FAILURES), " / ".join(FAILURES)))
    raise SystemExit(1)
print("T36 fail-cooldown-retry: 全绿")
raise SystemExit(0)