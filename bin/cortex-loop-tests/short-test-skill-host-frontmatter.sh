#!/usr/bin/env bash
# Validate a Skill frontmatter using the same YAML parser as candidate preflight,
# then require a non-empty top-level host key.
set -euo pipefail

if [ "$#" -ne 1 ]; then
  echo "usage: $0 <skill-markdown>" >&2
  exit 2
fi

SCRIPT_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
python3 - "$1" "$SCRIPT_ROOT" <<'PY'
import importlib.util
import pathlib
import re
import sys

try:
    import yaml
except ImportError:
    print("FAIL missing pyyaml", file=sys.stderr)
    raise SystemExit(2)

path = pathlib.Path(sys.argv[1])
root = pathlib.Path(sys.argv[2])
if not path.is_file():
    print(f"FAIL missing file: {path}", file=sys.stderr)
    raise SystemExit(1)

validator_path = root / "bin" / "verify-frontmatter.py"
spec = importlib.util.spec_from_file_location("verify_frontmatter", validator_path)
if spec is None or spec.loader is None:
    print(f"FAIL cannot load {validator_path}", file=sys.stderr)
    raise SystemExit(2)
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)

try:
    text = path.read_text(encoding="utf-8")
except OSError as exc:
    print(f"FAIL unreadable file: {exc}", file=sys.stderr)
    raise SystemExit(1)

# Require an actual closed frontmatter block. verify-frontmatter.py deliberately
# treats an unclosed leading delimiter as plain text for broad repository scans;
# this short_test is stricter because the candidate gate needs frontmatter.
match = re.match(r"\A---\n(.*?)\n---(?:\n|\Z)", text, flags=re.DOTALL)
if not match:
    print("FAIL missing or unclosed frontmatter", file=sys.stderr)
    raise SystemExit(1)

ok, reason = validator.check(str(path))
if not ok:
    print(f"FAIL frontmatter YAML: {reason}", file=sys.stderr)
    raise SystemExit(1)

try:
    document = yaml.safe_load(match.group(1))
except Exception as exc:
    print(f"FAIL frontmatter YAML: {str(exc).splitlines()[0][:120]}", file=sys.stderr)
    raise SystemExit(1)

if not isinstance(document, dict):
    print("FAIL frontmatter must be a mapping", file=sys.stderr)
    raise SystemExit(1)
host = document.get("host")
if not isinstance(host, str) or not host.strip():
    print("FAIL frontmatter top-level host must be a non-empty string", file=sys.stderr)
    raise SystemExit(1)

print(f"PASS {path}: host={host.strip()}")
PY
