#!/usr/bin/env python3
"""C9 -- a node's self-portrait has every field, and can_sleep can only be yes/no.

can_sleep is the only field that tells "lid closed, asleep" from "offline". If it is missing or wrong,
an overnight laptop is judged failed and its line is taken (flapping hurts more than a stall). So this is a hard assert.

Read-only: node_profile() writes nothing (write_profile does the disk write; this case does not call it).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _engine import check, finish, load  # noqa: E402

m = load()
prof = m.node_profile()
print("    profile: %s" % prof)

REQUIRED = ("node", "kind", "can_sleep", "executors", "telegram_reach", "last_seen", "owns")
missing = [f for f in REQUIRED if f not in prof or prof[f] in ("", None)]
check("all 7 fields are present", not missing, "missing %s" % missing)
check("can_sleep in {yes,no}", prof.get("can_sleep") in ("yes", "no"),
      "actual %r" % prof.get("can_sleep"))
check("kind in {laptop,always-on}", prof.get("kind") in ("laptop", "always-on"),
      "actual %r" % prof.get("kind"))
check("telegram_reach in {yes,no}", prof.get("telegram_reach") in ("yes", "no"),
      "actual %r" % prof.get("telegram_reach"))
check("last_seen parses and is hour precision", (m.parse_ts(prof.get("last_seen")) is not None
                                and prof.get("last_seen", "").endswith(":00")),
      "actual %r" % prof.get("last_seen"))
check("executors contains mock (the zero-cost executor must be registered)", "mock" in prof.get("executors", ""),
      "actual %r" % prof.get("executors"))
check("node is a legal identifier (no spaces)", prof.get("node") and " " not in prof["node"],
      "actual %r" % prof.get("node"))

# Consistency: quiet_limit must follow can_sleep; two machines must not share one ruler
check("can_sleep=yes -> limit 14h", m.quiet_limit({"can_sleep": "yes"}) == 14)
check("can_sleep=no -> limit 3h", m.quiet_limit({"can_sleep": "no"}) == 3)

finish()
