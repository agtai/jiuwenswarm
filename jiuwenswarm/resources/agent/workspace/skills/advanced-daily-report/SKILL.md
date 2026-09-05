---
name: advanced-daily-report
version: 2.0.0
description: 从已配置的工作记录生成日报、周报或月报；用于用户要求工作汇总，不用于普通 Git 查询。
tags: [report, automation, productivity, daily, weekly, monthly, advanced]
allowed_tools: [read_memory, write_memory, bash, read_file, write_file]
---

# 工作报告

按用户指定的日期和报告类型生成报告，保留来源、缺失数据和统计口径。日报/月报可使用当前技能目录中的 `run_report.py`；安装目录名是 `advanced-daily-report`。当前 `weekly` 分支只生成单日日报，不能作为完整周报证据；周报需真正汇总授权的一周材料。

- 生成或保存报告：读 [运行说明](references/run-report.md)。
- 只有请求 AI 分析或需要理解该分析输出时，读 [AI 分析说明](AI_ANALYSIS_TASKS.md)。
- 调度、飞书推送、邮箱或模型配置是独立操作；生成一次报告不代表已授权创建定时任务或发送给他人。

运行前确认脚本将读取的数据源与任务范围一致。脚本可访问已配置邮箱、工作记忆、会话待办和 Git；不要将配置中的凭据显示给用户。`daily` 默认还会调用外部 AI 并读取近七天 Git 模式；未授权该分析时传 `--no-ai`。`weekly` 不传递这个开关，不能用它绕过分析授权。缺少某一来源时说明缺口，不把缺失记录当作零工作量或完整采集。

成功后读取输出的 `REPORT_FILE:` 实际路径，展示报告内容并提供文件；用户要求摘要时按其要求缩写。只报告实际生成、保存或发送成功的结果。
