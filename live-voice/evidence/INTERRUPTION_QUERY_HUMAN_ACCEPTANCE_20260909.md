# 中断与任务查询修复：人工验收通过

2026-09-09，用户对下述会话明确反馈“全部通过”。结论为此前准备的六个
人工场景 **PASS（用户确认）**，关闭 `d1beb113` / `5cd46346` 的本轮人工回归
待验项。人工听感以用户反馈为依据；页面核对和已有自动回归作为不同来源的证据保留。

## 版本、会话与运行环境

- 部署源码：`b4aa449017bfdd153b2ada24eabf203061f9617d`，分支
  `codex/demo-live-voice-20260909`；启动时源码干净。
- 目标提交：`d1beb113b0310f5ab508ea3f528ca8b77a5b469f`（同步中断后的 Native
  接收退休与 Runtime 输出停止）、`5cd46346d7e9638ee4077c555295163c94dfbb08`
  （任务查询在共享语音锁之外拥有独立生命周期）。两者均在部署源码的祖先链中。
- [用户确认的验收会话](http://127.0.0.1:5173/chat/web_1a08762c675_89915ec2992c)：
  `web_1a08762c675_89915ec2992c`，区别于此前的启动冒烟会话。
- 独立项目：`proj_7b115f2a`；任务：`task-47dc83a8d46b4f6da9372dd812762ccd`。
- Chrome、本机 `127.0.0.1:5173`、Code / 单 Agent；验收后页面所选 Agent
  显示 `gpt-5.6`。此前准备会话曾选 deepseek-v4-flash，不将其沿用为此会话事实。
- 运行合同：formal-web-validation / openai-realtime-native / gpt-realtime-2.1，
  speed 1.25 / minimal / server-vad-450；生成期打断开启，耳机 profile 为
  verified-headset-aec-v1；AgentCore 为 0.1.16+jiuwenswarm.responses2。

## 场景与证据来源

| 人工场景 | 用户结论 | 本次只读核对 |
| --- | --- | --- |
| 普通对话与真实文件读取 | PASS | 会话返回 README 中的验收范围和正确标记 |
| 普通播放中打断 | PASS | 页面显示旧响应“已打断”，随后一句话回答完成 |
| 任务回执中打断，后台工作继续 | PASS | 创建回执标记“已打断”，后续两轮问答完成；原任务最终完成 |
| 查询期间持续播放：列表刷新及任务卡片 | PASS | 用户确认听感通过；本次记录不另作逐帧查询重叠或锁等待定量审计 |
| 语音查询任务状态 | PASS | 查询“会议准备”返回已完成，与右侧任务状态一致 |
| 任务完成后读取文件、继续对话 | PASS | 完成通知及三个主持人问题已返回；生成文件实际存在 |

会话显示的主要旅程时间为本机 20:16:46–20:20:56（Europe/Paris）。这些是页面
时刻，不能据此推算声学延迟。任务面板显示完成 1、取消 0、失败 0。
项目新增 `会议准备.md`，原 README 无 Git 变更；保留产物，未代用户提交或删除。

部署准备阶段在同一源码运行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit_tests/live_voice/test_native_interaction_runtime.py tests/unit_tests/live_voice/test_conversation_runtime.py tests/unit_tests/live_voice/test_product_query_lifecycle.py -q --tb=short
```

结果为 59 passed，exit 0。前端构建、受控启动器、真实 TTS→STT、正式 receipt、
身份错配及伪造 claim 拒绝探针均通过。原实现边界和并发回归见
[中断／查询修复记录](../reviews/REALTIME_INTERRUPTION_QUERY_ROOT_CAUSE_20260908.md)。

## 证据保留与边界

原始材料留在忽略目录 `logs/livevoice-acceptance-20260909-182100/`：运行合同、
启动日志、测试结果、人工话术、验收前及本次验收后的浏览器诊断。
本次 `accepted-session-browser-diagnostics.json` 的 SHA-256 为
`39283aa00ca8201a147ac61ad037330942b85f0738e1c486d8f916e72d5d44e9`；产物
`会议准备.md` 的 SHA-256 为
`c6ff92868643caeb5e123e21b3e472b9029625886cc70887f6edf92e5ceb4b5b`。
服务日志为 `logs/swarm-20260909-182251.log`。密钥、原始配置和完整对话不进入 Git。

此前准备会话曾出现 `response_generation / PAGE_HIDDEN` 恢复错误，其导出仍保留。
此次成功不抹去该记录及更早的传输／输入饱和失败。没有新增逐帧时序、锁等待、
完整物理延迟测量或全套测试结论；此次不是仅两提交的 A/B，也不关闭完整
A/B/A2、Task 调整／取消、离线恢复、跨设备矩阵或全产品准备度边界。

后续范围由 [STATUS](../STATUS.md) 决定；用户确认不自动启动剩余广泛修复工作。
