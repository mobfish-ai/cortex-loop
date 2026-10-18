#!/usr/bin/env python3
"""Positive and negative coverage for the Skill host frontmatter short_test."""

import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SHORT_TEST = ROOT / "bin/cortex-loop-tests/short-test-skill-host-frontmatter.sh"


def check(path: Path, expected: int) -> None:
    proc = subprocess.run(
        [str(SHORT_TEST), str(path)],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    if proc.returncode != expected:
        raise AssertionError(
            f"{path.name}: expected rc={expected}, got {proc.returncode}\n"
            f"stdout={proc.stdout}\nstderr={proc.stderr}"
        )


with tempfile.TemporaryDirectory(prefix="cortex-host-frontmatter-") as tmp:
    base = Path(tmp)

    valid = base / "valid.md"
    valid.write_text(
        "---\nname: valid\nhost: self\ndescription: clean\n---\nbody\n",
        encoding="utf-8",
    )
    check(valid, 0)

    # A weak `grep '^host:'` sees the body line, but candidate YAML parsing
    # must reject the malformed description value.
    malformed = base / "malformed.md"
    malformed.write_text(
        "---\nname: malformed\ndescription: broken: value\n---\n"
        "host: self\n",
        encoding="utf-8",
    )
    check(malformed, 1)

    missing_host = base / "missing-host.md"
    missing_host.write_text(
        "---\nname: missing-host\ndescription: 'host: self'\n---\nbody\n",
        encoding="utf-8",
    )
    check(missing_host, 1)

print("PASS short-test host frontmatter fixture: valid=PASS malformed=FAIL no-host=FAIL")
