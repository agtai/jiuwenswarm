# Live Voice 跨机器交接快照

- 快照日期：2026-07-31
- 开发分支：`hx/0731_live_voice_ux`
- 共享远端：`agtai`（`https://github.com/agtai/jiuwenswarm.git`）
- 已推送实现基线：`f6f428be946298ada154448bc04adfcd661652d8`
- 当前目标：先完成可现场演示的两周纵向 Demo，不提前扩成生产完整版

## 接手后先做什么

1. `git fetch agtai`，切换并更新 `hx/0731_live_voice_ux`。
2. 依次阅读 [README.md](README.md)、本文件、[STATUS.md](STATUS.md)、[TWO_WEEK_DEMO.md](TWO_WEEK_DEMO.md) 和 [DECISIONS.md](DECISIONS.md)。
3. 准备或检查演示机时，严格执行 [E2E_RUNBOOK.md](E2E_RUNBOOK.md)。
4. 第一优先级不是继续增加功能，而是跑通并留证“真实麦克风 → 真实 Agent/Tool → 浏览器朗读”。

不要从旧对话、未提交的本地文件或某台机器的 `.codex` / `.agent` 目录恢复项目事实；本目录是 Git 中的接续入口。

## 当前已经能做什么

- Live Voice 只在 Agent 模式开放；Team 模式明确禁用。
- 浏览器语音识别的 interim 只显示字幕，final 才生成一个用户 Turn。
- 空闲时 final 走真实 `chat.send`；Agent 正在处理时 final 走真实 `supplement`。
- 完整 assistant 消息进入浏览器 TTS FIFO；不会直接朗读原始 delta。
- 用户重新开麦、退出或出错时立即停止本地声音，并用 `responseEpoch` 废弃旧队列和迟到回调。
- supplement 发出到 ACK 之间隔离同一 session 的旧 delta/final/reasoning/media，降低旧回答复活风险。
- 麦克风权限、无语音、识别和播放失败均有可见错误，文字聊天始终可降级使用。

关键实现位于 `jiuwenswarm/channels/web/frontend/src/features/live-voice/`，详细入口见 [README.md](README.md)。

## 已完成的验证

- Live Voice 纯逻辑测试：21/21 通过（core 9、message gate 7、quarantine 5）。
- 相关既有回归：22/22 通过（stream delta 7、session creation 8、chat store/settle 7）。
- 全前端 TypeScript 检查通过。
- Vite production build 通过（4486 modules）。
- Chrome UI 已验证：Agent 模式进入 Listening；无音频停止显示 No speech detected；Retry 可重新 Listening；Exit 可退出；Cluster 禁用；切回 Agent 后恢复。
- 最后一个浏览器问题已修复：React 重渲染不再因为变化中的 cleanup 依赖而误触发 Live Voice 退出；清理现在只在真实卸载时执行。

## 尚未完成：当前唯一主线

代码路径已接通不等于现场 Demo 已验收。下面这些必须在固定演示机上真实完成：

- 麦克风产生可用中文 final transcript。
- 后端实际收到 `chat.send` / `supplement`。
- 一条固定口令实际产生 `chat.tool_call`、`chat.tool_result` 和 `chat.final`，工具结果不能伪造。
- `chat.final` 对应的完整回答实际从扬声器或耳机朗读。
- 连续 10 个语音 Turn 无重复提交。
- thinking/speaking 中重复 10 次打断，旧声音 0 次恢复。
- 连续运行 20 分钟或 20 Turn 无需刷新。
- 主演示脚本连续成功 3 次，并记录结果。

任何一项未通过，都不能写成“Demo 已完成”。

## 量化进度口径

截至本快照，按不同维度评估：

| 维度 | 完成度 | 含义 |
|---|---:|---|
| 代码实现 | 约 93% | 纵向闭环、状态、打断隔离、降级和自动化基本完成 |
| 整体 Demo | 约 82% | 已有可运行原型，但真实 Agent/Tool/音频 E2E 尚未放行 |
| 上台成熟度 | 约 65%–70% | 尚缺固定机器反复演练、稳定性与延迟证据 |

这些数字是项目判断，不是测试覆盖率。真实 E2E 失败时，整体和上台完成度必须下调。

## 当前限制如何分类

### 当前 Demo 放行阻塞项

- 目标演示机的 Chrome Web Speech 无法稳定产生 final。
- 模型 Provider 或网络不可用，真实 Agent 无法完成请求。
- 固定工具口令没有出现真实 tool call/result/final。
- 回答无法实际朗读，或打断后旧声音恢复。
- 10 Turn、10 次打断、20 分钟和连续 3 次脚本没有通过。

### 可控制、但不是本轮 Demo 阻塞项

- 没有服务端 response/generation ID；当前仅用本地 epoch 和 ACK quarantine。
- 没有全双工媒体和 AEC；Demo 固定耳机并显式重新开麦打断。
- 只支持 Agent、`zh-CN`、默认设备、单浏览器和稳定网络。
- 只在完整消息后朗读，不做 token/audio 流式 TTS。
- 不支持 Team、后台任务 stretch、多语言和 WebView2。

这些都必须在演示说明中诚实标注，后续仍是生产化工作，不能被解释为“无需处理”。

## 已知技术风险

supplement quarantine 当前覆盖旧 `chat.delta`、`chat.final`、`chat.reasoning` 和 `chat.media`，但没有完整隔离所有迟到的 `chat.tool_call` / `chat.tool_update` UI 事件。它通常不会让旧文字或声音复活，但可能在打断后短暂显示旧工具 UI。

真实 E2E 必须专门观察这一点。若现场可复现，Demo 阶段优先选择以下最小修复之一：

1. 活跃工具调用期间暂不允许 supplement，并给出可见提示；或
2. 给工具 UI 增加当前生成归属/取消状态过滤。

不要为了解决这一点直接重构完整生产协议；正式方案仍需要服务端 generation ID 与端到端 fence。

## 不要重复做或提前做的事情

- 不要另写一套语音专用 Agent 请求协议；继续复用现有 chat 链路。
- 不要把 partial transcript 发给 Agent 或工具。
- 不要写死 Agent 答案、工具结果或成功状态。
- 不要在核心 E2E 稳定前实现后台任务 stretch、Team、多语言、WebView2 或全双工媒体。
- 不要提交 API key、Slack token、用户配置文件、浏览器 profile、`.venv`、`node_modules` 或本机绝对路径。

## 每次继续工作后的交接要求

- 更新 [STATUS.md](STATUS.md) 的真实验证结果、问题和下一步。
- 范围或技术选择改变时更新 [DECISIONS.md](DECISIONS.md)。
- 新增临时简化时更新 [TWO_WEEK_DEMO.md](TWO_WEEK_DEMO.md) 的 Shortcut Ledger。
- 提交并推送到 `agtai/hx/0731_live_voice_ux`；仅存在本机或对话中的信息不算交接完成。
