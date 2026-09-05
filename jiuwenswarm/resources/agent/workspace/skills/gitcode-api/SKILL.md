---
name: gitcode-api
description: 使用 gitcode-api CLI 查询或操作 GitCode 仓库、Issue 和 Pull Request，或汇总其变更记录。
version: 1.0.0
metadata:
  version: 1.0.0
---

# GitCode CLI

本技能覆盖 当前工程依赖声明的 `gitcode-api >=1.2.20` 的 API 调用，不接管完整开发、提交或发布流程。

先用 `gitcode-api --version` 确认可用性；具体能力以本机分级 `--help` 为准，不猜命令参数。只在 CLI 缺失、版本不符或认证失败时读 [安装与认证](references/install-and-auth.md)。复用已配置凭据，不把 token 写入命令历史或输出，不自动创建 token 或扩大权限。

按任务选读：

- 参数、JSON 输出、转义：[CLI 用法](references/cli-usage.md)。
- 不确定资源/方法：[命令发现](references/command-discovery.md)。
- 对应操作示例：[常见调用](references/common-recipes.md)。
- 调用失败：[排障](references/troubleshooting.md)。
- 最近 commit/PR/issue、责任人、模块和风险汇总：[变更汇总](tasks/summarize-repo-changes.md)。

基本形状为 `gitcode-api <resource> <method> [options]`，资源与方法用 kebab-case。机器处理可用 `--compact`，保存用 `--output-file`；额外字段用 `--set` 或 `--set-json`。Python 包入口 [scripts/gitcode_api_cli.py](scripts/gitcode_api_cli.py) 只是同一 CLI 的薄封装。

查询与写入权限分开判断。评论、Issue/PR 创建或编辑等外部变化必须属于用户明确授权；远端 Git ref 更新继续遵守仓库的精确批准要求。失败时报告实际响应，完成可独立的只读工作，不把本地草稿称为已发布。

企业 CA 使用 `GITCODE_CA_BUNDLE` 或 `REQUESTS_CA_BUNDLE` 指向有效证书；不要关闭证书验证。
