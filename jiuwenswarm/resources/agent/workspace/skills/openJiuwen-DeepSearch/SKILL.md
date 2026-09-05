---
name: openJiuwen-DeepSearch
description: 使用 openJiuwen-DeepSearch 生成有来源的深度研究报告，适用于需要多步检索和综合分析的研究请求。
---

# openJiuwen-DeepSearch

围绕用户的研究问题生成并核对报告。复用已读取的技能指导；只有文件发生变化
或需要不同操作时才重新阅读相关部分。

## 准备和运行

从宿主提供的技能位置取得绝对目录，并在该目录执行命令。首次运行、环境缺失
或配置无效时读 [environment.md](references/environment.md)。复用可用的
`.venv` 和 `.env`，不重复安装。配置由用户在本地维护，检查时不输出配置值、
不要求在聊天中提供密钥，不擅自修改模型、Provider 或外部账户。

```text
uv run scripts/main.py --foreground --mode query --query "研究题目"
```

`--foreground` 是现有脚本参数，适合由当前任务持续跟踪到结果。使用宿主的
持续进程/异步执行能力，执行期间报告有意义的进展；不要仅因启动成功就结束
并要求用户稍后回来询问。若当前宿主无法持续跟踪，说明确切限制和任务状态，
不要承诺并不存在的后续通知。

已有后台任务或用户要求后台运行/停止时，读
[background-and-stop.md](references/background-and-stop.md)。不要重复启动同一研究。

## 完成

核对本次运行在 `<skill-dir>/output/reports/` 产生的 Markdown、DOCX、HTML
文件，确认内容对应研究问题并检查所请求格式实际存在、可读。旧文件和进程
退出本身都不能证明本次成功；区分正文完成、格式转换失败和全部完成。
交付实际文件链接、主要结论与必要来源，明确缺失证据或未完成格式。
运行失败时诊断可恢复的调用问题；缺少用户维护的凭据等外部前提时报告具体
阻塞。不得用估计的 15 分钟或 PID 存在代替完成证据。
