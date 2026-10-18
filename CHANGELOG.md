# Changelog

## Unreleased

- Scrub personal names, machine nicknames, and the default harness path from the tree.
- Node nicknames and the MiniMax CN provider list are environment settings.
- Suite skips private companion tools instead of failing, and GitHub Actions runs the suite plus a sensitive-string gate.
- Ship generic launchd and systemd examples.

## 0.1.0 — 2026-10-15

Initial open-source export of the cortex-loop swarm heartbeat engine.

- Engine (`bin/cortex-loop`), adapters, helpers, and the test suite.
- Operator skill and references under `skills/cortex-loop/`.
- Apache-2.0 `LICENSE` and `NOTICE` (copyright mobfish-ai).
- Private ledgers, vault dumps, and provider credentials stay out of this tree.
