# 报告运行说明

用实际技能目录的绝对路径调用脚本。以下是默认安装布局，运行环境给出其他技能根目录时以它为准：

```bash
python ~/.jiuwenswarm/agent/workspace/skills/advanced-daily-report/run_report.py daily --no-ai --save
python ~/.jiuwenswarm/agent/workspace/skills/advanced-daily-report/run_report.py daily --date 2026-03-06 --no-ai --save
python ~/.jiuwenswarm/agent/workspace/skills/advanced-daily-report/run_report.py monthly --year 2026 --month 3 --save
```

日期只是参数示例，替换为用户请求的日期。Windows PowerShell 使用 `python "$env:USERPROFILE\.jiuwenswarm\agent\workspace\skills\advanced-daily-report\run_report.py" daily --no-ai --save`。

当前 CLI 的 `weekly` 仅调用单日 `generate_daily_report(date)`，且忽略 `--no-ai`；
即使文件名以 weekly 开头，也不证明一周覆盖。周报应在已授权的数据源范围内
逐日收集并实际汇总整周，或使用已有周材料；日期/来源缺口明确报告。不要将
单日输出改标题后交付为完整周报。

`daily` 的 AI 默认为开：会向配置模型提交提交记录、待办、部分记忆，并额外
采集当前近七天 Git 模式。只有该数据范围和 Provider 分析已获授权时才省略
`--no-ai`；它不是所有类型通用的禁用开关。`monthly` 当前没有这条 AI 调用。

现有 CLI 支持 `--date`、`--year`、`--month`、`--save`、`--no-save`、`--output-file`、`--ai`、`--no-ai`；按请求选择，不臆造 `--git-repo` 或来源过滤参数。需要准确了解数据范围时检查当前脚本的路径解析和采集函数，不把历史机器上的 `D:/Download/jiuwenswarm` 当作本机事实。

保存成功会打印 `REPORT_FILE:<path>`，默认报告位于脚本解析出的 Agent root 下 `reports/`。读取该文件后交付；`--no-save` 则报告从标准输出返回，不声称生成了文件。

数据包括 Git 提交/变更、已配置邮箱 IMAP、工作记忆与会话待办。邮箱通常使用 `EMAIL_ADDRESS`、`EMAIL_TOKEN`、`EMAIL_PROVIDER`；授权码不是登录密码。配置是否存在不表示用户授权本次读取所有来源。脚本不能满足请求的来源范围时，说明限制并使用范围内已有材料提供标明来源的汇总，不声称该汇总来自完整脚本采集。

脚本错误、邮箱不可达、空数据或 AI 分析失败分别说明；可交付已成功采集的部分。启用新邮箱、提供模型凭据、改心跳配置、重启服务或向飞书推送均不由本报告操作自动授权。
