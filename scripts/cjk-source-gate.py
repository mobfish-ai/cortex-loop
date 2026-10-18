#!/usr/bin/env python3
"""Fail when CJK characters appear outside the explicit allowlist.

Allowlist globs live in scripts/cjk-allowlist.txt. Simplified Chinese
documentation mirrors (*.zh-CN.md) and deliberate test fixtures are listed
there. Everything else — engine, adapters, tests, English docs — must be
English.

The pattern is written with \\u escapes so this file itself stays ASCII.
"""

from __future__ import annotations

import fnmatch
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ALLOW = os.path.join(ROOT, "scripts", "cjk-allowlist.txt")

# Ideographs, CJK punctuation, fullwidth forms, kana, and hangul.
CJK = (
    "["
    "\u3400-\u4dbf"
    "\u4e00-\u9fff"
    "\uf900-\ufaff"
    "\u3000-\u303f"
    "\uff00-\uffef"
    "\u3040-\u30ff"
    "\u31f0-\u31ff"
    "\uac00-\ud7af"
    "]"
)

import re

CJK_RE = re.compile(CJK)
# The required language switch is the one CJK sequence allowed in English docs.
SWITCH_RE = re.compile(
    r"^(?:English \| \[\u7b80\u4f53\u4e2d\u6587\]\([^)\n]+\)"
    r"|\[English\]\([^)\n]+\) \| \u7b80\u4f53\u4e2d\u6587)\s*$"
)


def load_globs():
    globs = []
    with open(ALLOW, encoding="utf-8") as fh:
        for raw in fh:
            line = raw.split("#", 1)[0].strip()
            if line:
                globs.append(line)
    return globs


def allowed(rel, globs):
    rel = rel.replace(os.sep, "/")
    for pattern in globs:
        if fnmatch.fnmatch(rel, pattern):
            return True
        # Also match when the pattern is a directory prefix written with **.
        if pattern.endswith("/**") and (
            rel == pattern[:-3] or rel.startswith(pattern[:-3] + "/")
        ):
            return True
    return False


def main():
    globs = load_globs()
    hits = 0
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d != ".git"]
        for name in filenames:
            path = os.path.join(dirpath, name)
            rel = os.path.relpath(path, ROOT)
            if allowed(rel, globs):
                continue
            try:
                with open(path, encoding="utf-8") as fh:
                    text = fh.read()
            except (UnicodeDecodeError, OSError):
                continue
            if not CJK_RE.search(text):
                continue
            for lineno, line in enumerate(text.splitlines(), 1):
                if not CJK_RE.search(line) or SWITCH_RE.match(line.strip()):
                    continue
                hits += 1
                if hits <= 80:
                    print(f"CJK {rel}:{lineno}: {line.strip()[:160]}")
    if hits:
        print(f"cjk source gate: FAIL ({hits} lines outside allowlist)")
        return 1
    print("cjk source gate: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
