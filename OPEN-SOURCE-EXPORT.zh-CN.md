[English](OPEN-SOURCE-EXPORT.md) | 简体中文

# cortex-loop 开源导出

目标仓库：`mobfish-ai/cortex-loop`。
许可证：Apache-2.0。

## 包含

- `bin/cortex-loop` — 心跳 / 账本 / 蜂群引擎
- 目录树里列出的 `bin/cortex-loop-*.sh|py` 辅助脚本
- `bin/cortex-loop-adapters/` — 运行时 adapter（密钥只经环境变量）
- `bin/cortex-loop-tests/` — 套件与夹具
- `skills/cortex-loop/` — 操作者技能与参考文档
- `examples/launchd/` 与 `examples/systemd/` — 通用调度器示例
- `LICENSE` `NOTICE` `README.md` `CHANGELOG.md`
- `.github/workflows/test.yml`、`scripts/public-hygiene.sh` 与 `scripts/cjk-source-gate.py`

## 永不发布

- 绝对个人家目录路径
- 操作者邮箱、客户域名或邮箱服务商令牌
- 私有供应商凭据、保险库导出、`reports/`、`governance/`
- PEM 或 OpenSSH 私钥材料
- 内部主机名和个人 launchd 标签

`scripts/public-hygiene.sh` 检查工作区里的这些类别。
它不扫描 git 历史。历史仍需另行审查。

## 公开之前

不要在 agent 运行里改这个仓库的可见性。公开需要：

1. `bash scripts/public-hygiene.sh` 退出码为 0。
2. `bash bin/cortex-loop-tests/suite.sh` 退出码为 0。
3. Git 历史里不再含有个人邮箱或卫生门拒绝的字符串。在旧提交之上再加一个提交不会擦掉那些 blob。如果历史不干净，应发布一份干净的单提交导出，而不是直接公开这段历史。
