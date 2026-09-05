---
name: llm-wiki
description: 使用 wiki_ingest、wiki_query、wiki_lint 导入、查询或维护用户指定的本地 LLM Wiki。
---

# 本地 LLM Wiki

仅用于用户指定的 Wiki 知识库；普通文件读取或摘要不自动导入文档。

工具按当前 schema 使用：
- `wiki_ingest(source, workspace)`：用户授权的 PDF、MD、TXT 或目录导入。
- `wiki_query(query, workspace)`：查询并用返回证据回答。
- `wiki_lint(workspace)`：检查链接和孤立页面。

指定 source 和 workspace 时解析绝对路径。后端 `_resolve_workspace` 将空 workspace 定位到 Agent workspace 下的 `.llm_wiki`；路径末尾已是 `.llm_wiki` 时不再追加，否则在指定目录下追加一次。三个工具使用同一目标，查询时正确传给 `wiki_query`，不要误调用 lint。

结构为 `sources/` 原始材料、`wiki/` 编译知识、`schema/` 内部规则。编辑前读取该 Wiki 的 `schema/AGENT.md` 和 `wiki/index.md`；不改原始 `sources/` 或去重 manifest。导入工具负责遍历、去重和编译；完成后核对 index/log，仅补缺失的索引链接和摘要，避免重复写入。

查询仅据实际返回事实作答，引用原始文件并说明无证据部分。lint 请求本身先报告结果；用户要求维护/修复时，可在 `wiki/` 内修复有依据的相对 Markdown 链接并记录 log，无法确认目标的链接不猜填。

工具缺失或调用失败时可分析用户提供的原文，但明确未导入、未查询或未修复 Wiki，不伪造后台成功。
