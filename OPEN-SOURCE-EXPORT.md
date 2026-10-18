English | [简体中文](OPEN-SOURCE-EXPORT.zh-CN.md)

# cortex-loop open-source export

Target repo: `mobfish-ai/cortex-loop`.
License: Apache-2.0.

## Include

- `bin/cortex-loop` — heartbeat / ledger / swarm engine
- `bin/cortex-loop-*.sh|py` helpers listed in the tree
- `bin/cortex-loop-adapters/` — runtime adapters (keys only via env)
- `bin/cortex-loop-tests/` — suite + fixtures
- `skills/cortex-loop/` — operator skill and references
- `examples/launchd/` and `examples/systemd/` — generic schedulers
- `LICENSE` `NOTICE` `README.md` `CHANGELOG.md`
- `.github/workflows/test.yml`, `scripts/public-hygiene.sh`, and `scripts/cjk-source-gate.py`

## Never publish

- Absolute personal home paths
- Operator mailboxes, customer domains, or mailbox-provider tokens
- Private provider credentials, vault dumps, `reports/`, `governance/`
- PEM or OpenSSH private-key material
- Internal hostnames and personal launchd labels

`scripts/public-hygiene.sh` checks the working tree for those classes.
It does not scan git history. History still has to be reviewed separately.

## Before a public flip

Do not change this repository's visibility from an agent run. A public
flip needs:

1. `bash scripts/public-hygiene.sh` exits 0.
2. `bash bin/cortex-loop-tests/suite.sh` exits 0.
3. Git history does not still contain personal emails or the strings the
   hygiene gate rejects. A later commit on top of an old commit does not
   erase those blobs. If history is dirty, publish a clean single-commit
   export instead of flipping this history.
