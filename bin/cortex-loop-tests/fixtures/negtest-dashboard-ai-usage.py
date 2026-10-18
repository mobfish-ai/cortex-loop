#!/usr/bin/env python3
"""T19 regression: dashboard exposes truthful, separated AI usage facts."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[3]
DASH = ROOT / "bin" / "cortex-dashboard.sh"
fails = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global fails
    if condition:
        print("PASS  " + name)
    else:
        fails += 1
        print("FAIL  %s%s" % (name, " — " + detail if detail else ""))


with tempfile.TemporaryDirectory(prefix="cortex-dashboard-ai-") as tmp:
    fixture = Path(tmp)
    local_file = fixture / "local.json"
    quota_file = fixture / "quota.json"
    trust_file = fixture / "trust.json"
    local_file.write_text(
        json.dumps(
            {
                "schema_version": "cortex-dashboard/ai-local-usage-v1",
                "observed_at": "2026-07-31T00:00:00Z",
                "channels": {
                    "claude": {
                        "state": "OK",
                        "metrics": {"assistant_responses": 7, "usage_fields_sum": 1234},
                        "source": "fixture claude jsonl",
                        "window": "2026-07-31",
                        "scope": "local fixture; not billable quota",
                    },
                    "codex": {
                        "state": "OK",
                        "metrics": {"validate_shots": 2, "sessions": 3},
                        "source": "fixture codex local counter",
                        "window": "2026-07-31",
                        "scope": "local counters only; not OpenAI quota",
                    },
                    "minimax": {
                        "state": "OK",
                        "metrics": {
                            "openclaw_responses": 4,
                            "openclaw_reported_tokens": None,
                            "token_counter_state": "UNKNOWN",
                        },
                        "source": "fixture minimax local records",
                        "window": "2026-07-31",
                        "scope": "local fixture",
                    },
                    "glm": {
                        "state": "UNKNOWN",
                        "metrics": None,
                        "source": "fixture glm unavailable",
                        "window": "2026-07-31",
                        "scope": "local fixture",
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    quota_file.write_text(
        json.dumps(
            {
                "generated_at": "2026-07-31T00:00:00Z",
                "services": [
                    {
                        "service": "anthropic",
                        "safe_accounts": [{"active": True, "live_remaining_quota": None}],
                    },
                    {
                        "service": "openai",
                        "safe_accounts": [{"active": True, "live_remaining_quota": 44}],
                    },
                    {
                        "service": "minimax",
                        "safe_accounts": [{"active": True, "live_remaining_quota": None}],
                    },
                    {
                        "service": "glm",
                        "safe_accounts": [{"active": True, "live_remaining_quota": 88}],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    trust_file.write_text(
        json.dumps(
            {
                "schema_version": "cortex-dashboard/trust-events-v1",
                "state": "OK",
                "source": "fixture refs",
                "events": [],
                "by_node": {},
            }
        ),
        encoding="utf-8",
    )

    env = os.environ.copy()
    env.update(
        {
            "CORTEX_DASH_TEST_MODE": "1",
            "CORTEX_DASH_AI_LOCAL_FILE": str(local_file),
            "CORTEX_DASH_AI_QUOTA_FILE": str(quota_file),
            "CORTEX_DASH_TRUST_EVENTS_FILE": str(trust_file),
            "CORTEX_DASH_TRUST_TIMEOUT": "1",
        }
    )
    result = subprocess.run(
        ["bash", str(DASH), "--json"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    check("dashboard --json exits zero", result.returncode == 0, result.stderr[:300])
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        check("dashboard --json is valid JSON", False, str(exc))
        payload = {}

    usage = payload.get("runtime", {}).get("ai_usage", {})
    channels = usage.get("channels", [])
    indexed = {item.get("id"): item for item in channels}
    check(
        "exactly four required channels",
        set(indexed) == {"claude", "codex", "minimax", "glm"} and len(channels) == 4,
        str(indexed.keys()),
    )
    check(
        "each channel separates local and official facts with sources",
        all(
            isinstance(item.get("local_observed"), dict)
            and isinstance(item.get("official_live_quota"), dict)
            and item["local_observed"].get("source")
            and item["official_live_quota"].get("source")
            for item in channels
        ),
        str(channels),
    )
    check(
        "unknown official quota is null, never fake zero",
        indexed["claude"]["official_live_quota"]["state"] == "UNKNOWN"
        and indexed["claude"]["official_live_quota"]["value"] is None
        and indexed["minimax"]["official_live_quota"]["value"] is None,
        str(channels),
    )
    check(
        "known official quota remains vendor data",
        indexed["codex"]["official_live_quota"]["value"] == 44
        and indexed["glm"]["official_live_quota"]["value"] == 88,
        str(channels),
    )
    check(
        "Codex local counters cannot masquerade as quota",
        indexed["codex"]["local_observed"]["metrics"] == {
            "validate_shots": 2,
            "sessions": 3,
        }
        and "not OpenAI quota" in indexed["codex"]["local_observed"]["scope"],
        str(indexed.get("codex")),
    )
    check(
        "unreported provider tokens stay UNKNOWN/null",
        indexed["minimax"]["local_observed"]["metrics"]["openclaw_reported_tokens"]
        is None
        and indexed["minimax"]["local_observed"]["metrics"]["token_counter_state"]
        == "UNKNOWN",
        str(indexed.get("minimax")),
    )

    human = subprocess.run(
        ["bash", str(DASH)],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    check("human dashboard exits zero", human.returncode == 0, human.stderr[:300])
    check(
        "human view labels both sources and all four channels",
        "AI usage (local observation != official live quota)" in human.stdout
        and all(name in human.stdout for name in ("Claude", "Codex", "MiniMax", "GLM"))
        and "local=" in human.stdout
        and "official=" in human.stdout
        and "[src:" in human.stdout,
        human.stdout[-1800:],
    )
    check(
        "human view renders missing token/quota as UNKNOWN",
        "openclaw_reported_tokens=UNKNOWN" in human.stdout
        and "official=UNKNOWN" in human.stdout,
        human.stdout[-1800:],
    )

print("dashboard AI usage truth: %s" % ("PASS" if fails == 0 else f"FAIL ({fails})"))
raise SystemExit(1 if fails else 0)
