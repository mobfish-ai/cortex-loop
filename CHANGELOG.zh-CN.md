[English](CHANGELOG.md) | 简体中文

# 变更记录

## 未发布

- 代码、注释和 CLI 文本默认使用英语。面向用户的文档有简体中文镜像（`*.zh-CN.md`），顶部有 English | 简体中文 切换行。
- 当 CJK 字符出现在这些镜像和 `bin/cortex-loop-tests/fixtures/` 之外时，CI 失败。
- 从目录树中清除个人姓名、机器昵称和默认 harness 路径。
- 节点昵称和 MiniMax 国内供应商列表改为环境设置。
- 套件在缺少私有配套工具时跳过而不是失败。GitHub Actions 运行套件和敏感字符串门。
- 附带通用的 launchd 与 systemd 示例。

## 0.1.0 — 2026-10-15

cortex-loop 蜂群心跳引擎的首次开源导出。

- 引擎（`bin/cortex-loop`）、adapter、辅助脚本和测试套件。
- `skills/cortex-loop/` 下的操作者技能与参考文档。
- Apache-2.0 的 `LICENSE` 与 `NOTICE`（版权 mobfish-ai）。
- 私有账本、保险库导出和供应商凭据不进入本目录树。
