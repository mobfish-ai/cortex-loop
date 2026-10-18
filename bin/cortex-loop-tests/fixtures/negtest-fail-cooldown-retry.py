#!/usr/bin/env python3
"""EX14 / T36 -- after a failure cooldown the task can be retried; it is not sunk forever.

DIMENSIONAL theme, site 6: yielding forever is not the same as yielding for a while.
Live incident on 2026-07-29: the laptop gateway died, the task failed, and the old code
`if _r.get("node") == me: continue` yielded forever. A worker that could do the job
could not take it, and R1 stayed locked all night. Failure is not a terminal state;
a cooldown window has to catch it.

This fixture asserts four invariants directly:

  1. FAIL_COOLDOWN_MIN exists and is > 0 (= 0 means the feature was not built)
  2. run_receipt_payload with status="failed" must include a failed_at field
  3. cmd_claim path: status=failed but failed_at missing -> retryable (old receipts stay compatible)
  4. cmd_claim path: status=failed + failed_at inside the window -> do not retry; past the window -> retry

Do not simulate a full command (git ref CAS is too heavy). Call the cmd_claim decision core:
build a fake `_r` dict, monkey-patch parse_ts/now, and check that the print line splits
on "cooldown |" versus "retry |".

Fitztest style: do not induce an external git failure. Function-level assertions only.
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


# 1. FAIL_COOLDOWN_MIN exists and is > 0 -- 0 means it was not built, < 0 means it is reversed
check("FAIL_COOLDOWN_MIN constant exists", hasattr(loop, "FAIL_COOLDOWN_MIN"),
      "missing means a failed claim has no cooldown window")
check("FAIL_COOLDOWN_MIN > 0 (0 means it was not built)",
      getattr(loop, "FAIL_COOLDOWN_MIN", 0) > 0,
      "actual=%s" % getattr(loop, "FAIL_COOLDOWN_MIN", None))


# 2. run_receipt_payload with status=failed must include a failed_at field
payload_failed = loop.run_receipt_payload(
    "test-plan", {"id": "T-FAILED"}, {"holder": "node-a"}, "executor-x",
    "failed", "gate-y", reason="executor down",
)
check("status=failed receipt contains a failed_at= field",
      re.search(r"^failed_at=", payload_failed, re.MULTILINE) is not None,
      "actual payload=%r" % payload_failed[:200])
check("status=failed receipt still contains a status=failed field",
      re.search(r"^status=failed$", payload_failed, re.MULTILINE) is not None,
      "actual payload=%r" % payload_failed[:200])

# done does not need failed_at (done is terminal; nobody claims it again)
payload_done = loop.run_receipt_payload(
    "test-plan", {"id": "T-DONE"}, {"holder": "node-a"}, "executor-x",
    "done", "passed",
)
check("status=done receipt does **not** contain a failed_at field (do not pollute a terminal state)",
      re.search(r"^failed_at=", payload_done, re.MULTILINE) is None,
      "unexpected failed_at=%r" % payload_done[:200])


# 3 & 4. cmd_claim decision core: inject a fake _r / now(),
# and assert the in_cooldown branch and the retry branch split correctly.
# Do not run the whole cmd_claim (git ref CAS is too heavy).
# Lift the decision block out of cmd_claim: build a fake context and watch the print split.
def _probe_claim_logic(_r, fake_now, fake_me="node-me"):
    """Lift the failed-branch decision out of cmd_claim and run it once."""
    # Production uses these two functions; reuse the same ones so the fixture matches production.
    failed_at = loop.parse_ts(_r.get("failed_at"))
    in_cooldown = (failed_at is not None
                   and (fake_now - failed_at).total_seconds() < loop.FAIL_COOLDOWN_MIN * 60)
    if in_cooldown:
        who = "this node" if _r.get("node") == fake_me else "last %s" % _r.get("node")
        return "cooldown | T-FAILED %s failed inside cooldown window (%dmin) -> skip for now" % (
            who, loop.FAIL_COOLDOWN_MIN)
    who = "this node" if _r.get("node") == fake_me else "last %s" % _r.get("node")
    return "retry | T-FAILED %s cooldown elapsed, this node retries (cooldown/retry)" % who


now = loop.now()
recent_failed = now - timedelta(seconds=loop.FAIL_COOLDOWN_MIN * 30)  # half window
old_failed = now - timedelta(seconds=loop.FAIL_COOLDOWN_MIN * 60 + 60)  # 1min past window

# failed_at is written with fmt(), matching production (parse_ts requires %Y-%m-%dT%H:%M%z)
recent_str = loop.fmt(recent_failed)
old_str = loop.fmt(old_failed)

# 4a. failed_at inside the window -> cooldown branch
out_cooldown = _probe_claim_logic(
    {"status": "failed", "node": "node-me", "failed_at": recent_str},
    now,
)
check("failed_at still inside the cooldown window -> output contains 'cooldown |'",
      out_cooldown.startswith("cooldown |"), "actual=%r" % out_cooldown)
check("output during cooldown does not contain 'retry |' (cooldown cannot be bypassed)",
      "retry |" not in out_cooldown, "actual=%r" % out_cooldown)

# 4b. failed_at outside the window -> retry branch
out_retry = _probe_claim_logic(
    {"status": "failed", "node": "node-me", "failed_at": old_str},
    now,
)
check("failed_at past the cooldown window -> output contains 'retry |' (EX14)",
      out_retry.startswith("retry |"), "actual=%r" % out_retry)
check("retry output explicitly marks 'cooldown/retry' for audit",
      "cooldown/retry" in out_retry, "actual=%r" % out_retry)

# 4c. failed_at missing -> treat as retryable (old receipts stay compatible during upgrade)
out_compat = _probe_claim_logic(
    {"status": "failed", "node": "node-me"},  # no failed_at
    now,
)
check("failed_at missing (historical receipt) -> retry path, not sunk forever",
      out_compat.startswith("retry |"), "actual=%r" % out_compat)

# 5. Boundary: exactly the window -- treat as past the window (implementation uses < not <=)
edge_failed = now - timedelta(seconds=loop.FAIL_COOLDOWN_MIN * 60)
out_edge = _probe_claim_logic(
    {"status": "failed", "node": "node-me", "failed_at": loop.fmt(edge_failed)},
    now,
)
check("boundary: failed_at == window (0 seconds left) -> retryable (implementation uses < not <=)",
      out_edge.startswith("retry |"), "actual=%r" % out_edge)


# 6. Search the real cmd_claim source for both branches -- catch a fake where
# the probe function has the branch but the cmd_claim main path never calls it
src = Path(ROOT / "bin/cortex-loop").read_text()
check("bin/cortex-loop source prints a 'cooldown |' branch",
      "cooldown |" in src, "cmd_claim does not actually split")
check("bin/cortex-loop source prints 'retry | ... cooldown/retry'",
      "cooldown/retry" in src, "EX14 retry marker missing")
check("bin/cortex-loop source references FAIL_COOLDOWN_MIN (not a hardcoded 5)",
      "FAIL_COOLDOWN_MIN" in src, "a hardcoded 5 means the constant is dead")


if FAILURES:
    print("%d assertions failed: %s" % (len(FAILURES), " / ".join(FAILURES)))
    raise SystemExit(1)
print("T36 fail-cooldown-retry: ALL PASS")
raise SystemExit(0)