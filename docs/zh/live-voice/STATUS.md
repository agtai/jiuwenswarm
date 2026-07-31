# Live Voice 当前状态

- 最后更新：2026-07-31
- 工作分支：`hx/0731_live_voice_ux`
- 远端跟踪：`agtai/hx/0731_live_voice_ux`
- 建立方案时的代码基线：`7b69fdeb`
- 已推送实现基线：`f6f428be946298ada154448bc04adfcd661652d8`
- 当前里程碑：两周纵向 Demo
- 实现状态：核心前端链路已实现并通过自动化验证；真实“说话 → 后端 Agent/Tool → 朗读”端到端联调尚未完成

跨机器恢复先读 [HANDOFF.md](HANDOFF.md)；启动、固定环境和真实验收按 [E2E_RUNBOOK.md](E2E_RUNBOOK.md) 执行。

当前量化判断：代码实现约 **93%**，整体 Demo 约 **82%**，上台成熟度约 **65%–70%**。差距主要是固定演示机上的真实麦克风、Agent/Tool、TTS、打断和稳定性证据，不是再增加大量功能。

## 当前结论

本轮已经把 Live Voice 从方案推进到可运行的前端 Demo 原型：有独立入口和状态 UI，浏览器识别得到的 **final** 文本会复用现有 `chat.send` / `supplement` 调用真实 Chat/Agent 链路，`chatStore` 中完成的 Agent 消息会进入浏览器 TTS FIFO，打断或退出会用本地 `responseEpoch` 立即废弃旧声音。

这说明核心流程已经在代码层接通，并且关键的“只提交一次、partial 无副作用、旧声音不复活、文字仍可用”等约束可以自动化验证。它还不能证明真实中文语音、目标后端 Agent/Tool、网络和扬声器组合在演示机上已经完整跑通；本轮自动化环境没有可注入的麦克风音频，也没有启动需要外部模型 Provider 的后端链路。

## 已实现

### Live Voice 入口和状态

- 在 ChatPanel 增加带 feature flag 的 `LiveVoiceDemoBar`，支持进入、退出、主要操作以及 `idle`、`listening`、`thinking`、`speaking`、`interrupted`、`error` 状态展示。
- 显示 interim 字幕、已提交文本、不可用原因和可见错误；Live Voice 失败时不隐藏、不破坏原文字输入框。
- 当前只允许 **Agent 模式**启用。Team 模式会显示不可用并退出 Live Voice，避免把多成员/Leader 输出错误地当成单一回答朗读。

### 语音到真实 Agent 路径

- 复用 `useSpeechRecognition`，固定 `zh-CN`、浏览器 Web Speech 和约 1.2 秒静音窗口。
- interim 只更新字幕，不发送消息；一个识别周期只接受一次完整 final。
- 空闲时 final 调用现有 `chat.send`；已有 Agent 请求处理中重新开麦，final 调用现有 `supplement`。没有伪造 Agent 答案或工具结果。
- SpeechRecognition 实例按代次隔离；旧实例迟到的 `onend` / `onresult` 不能污染重试或新录音。
- 新会话从特殊 `new` session 晋升为真实 session 时，通过一次性 promotion signal 保留当前语音 Turn；切换到其他既有 session 时退出并清理 Live Voice。
- 当前存在待确认问题或演进流程时禁止进入/继续 Live Voice，避免把 Gateway 的排队语义误当成普通 supplement 取消语义。

### Agent 回答朗读与打断

- 只朗读已经由 `chatStore` 落地、位于当前语音用户消息之后且下一条 user 消息之前、`isStreaming !== true` 的完整 assistant 消息；不直接朗读原始 WebSocket delta，也不朗读历史消息或后续文字 Turn 的回答。
- 浏览器 SpeechSynthesis 通过小型 FIFO 顺序播放，按消息 ID 去重，并在播放前清理不适合朗读的文本。
- 每次 final、打断、退出和错误都会推进本地 `responseEpoch`；旧队列及旧播放器回调无法改变新 Turn 状态或恢复旧声音。
- thinking / speaking 时点击主要操作会先本地停播，再重新开始识别；识别 final 后走 `supplement`。

### supplement 输出隔离

- 普通 Agent supplement 发出时建立短期前端 quarantine：先清除尚未刷新的旧 delta、封口旧 assistant 流，再丢弃同一 session 的 `chat.delta`、`chat.final`、`chat.reasoning` 和 `chat.media`。
- 收到有序的 `chat.interrupt_result(intent=supplement)` ACK 后解除隔离，让替代回答正常进入 `chatStore` 和 TTS。
- 请求失败、断开连接或 Hook 清理时会释放隔离。该机制只保护当前有序 WebSocket 的 Demo 路径，不是服务端 response ID / generation fence。

### 错误和文字降级

- 识别不支持、合成不支持、麦克风权限拒绝、无语音、识别失败和播放失败都有可见状态或不可用说明。
- 错误后可以重试或退出；原有文字聊天入口始终保留。
- 浏览器全局 TTS 停止事件会同步使 Live Voice 的当前朗读失效，避免文字发送等既有操作后声音继续播放。

## 验证记录

| 日期 | 验证 | 结果 |
|---|---|---|
| 2026-07-31 | `liveVoiceCore`、消息朗读门控和 supplement quarantine 的纯逻辑测试 | **21/21 通过**（core 9 + message gate 7 + quarantine 5）；覆盖单周期唯一提交、partial 无副作用、FIFO、去重、epoch、新录音废弃已播完旧 epoch、迟到回调、错误恢复、完成消息及下一 user 边界筛选、session 隔离和 ACK 计数 |
| 2026-07-31 | 全前端 TypeScript：`node node_modules/typescript/bin/tsc --noEmit` | 通过 |
| 2026-07-31 | Vite production build：`node node_modules/vite/bin/vite.js build` | 通过 |
| 2026-07-31 | 既有相关回归：stream delta、session creation、chat store/settle | **22/22 通过**（7 + 8 + 7） |
| 2026-07-31 | Codex 内置浏览器，麦克风权限不可授予/被拒绝路径 | 页面显示可见的语音错误和文字降级，原文字输入仍可操作 |
| 2026-07-31 | 本机 Chrome 手动进入 Live Voice，未提供语音后停止 | 成功进入 `listening`；停止后出现可见的 `no-speech` 错误，没有静默失败 |
| 2026-07-31 | Chrome 状态与模式回归 | Listening、No speech detected、Retry、Exit 均正常；Cluster 禁用，切回 Agent 后恢复 |

测试入口和可直接复制的命令见 [README.md](README.md)。

## 尚未完成与不能宣称的内容

- **尚未完成真实语音到 Agent 的 E2E**：还没有启动本机 AgentServer/WebChannel/Gateway 并允许外部模型 Provider 调用，再用真实麦克风说中文观察 `final → chat.send/supplement → Agent/Tool → chatStore 完成消息 → 扬声器朗读` 全链路。当前配置与依赖静态检查通过，但自动化没有可注入的麦克风音频；启动整套服务还会连接已启用的 Slack channel，因此本轮没有擅自启动并产生额外外部连接。
- 因而也尚未验证 10 个真实语音 Turn、真实工具调用、真实 supplement 打断 10/10、20 分钟稳定性和延迟指标。
- 当前只覆盖 Agent 模式；Team、多成员和 Team Leader 输出语义没有纳入 Demo。
- supplement quarantine 依赖当前 WebSocket 帧有序和 `chat.interrupt_result` ACK；它没有 response ID，不能解决断线重放、多端并发或服务端跨生成乱序。
- supplement quarantine 尚未覆盖所有迟到的 `chat.tool_call` / `chat.tool_update` UI 事件；通常不会恢复旧文字或声音，但真实打断测试中可能出现旧工具 UI，必须专项观察。
- 未验证 Desktop/WebView2 的权限持久性，也未接入 Azure 等 Speech Provider fallback。
- 可选的 `schedule.run/status/cancel` 后台任务 stretch **未实现**；继续保持可砍，不阻塞核心语音闭环。
- 本轮仍是固定 Windows/Chrome、`zh-CN`、默认设备和耳机的 Demo，不是生产级全双工实时媒体。

## 下一步

1. 按 [E2E_RUNBOOK.md](E2E_RUNBOOK.md) 固定依赖、配置和演示机，启动可真实调用工具的 JiuwenSwarm 后端，在 Chrome + 耳机 + 麦克风环境跑完整验收脚本。
2. 用浏览器和后端日志核对每个语音周期只产生一个用户 Turn，partial 产生零副作用；分别验证空闲 `chat.send` 和处理中 `supplement`。
3. 连续运行 10 个真实语音 Turn，并重复 10 次 speaking/thinking 中的确定性打断，记录静音延迟、final 提交延迟、首音延迟和任何迟到输出。
4. 验证通过后再决定是否补 WebView2/Azure fallback；核心链路未稳定前不开始后台任务 stretch。

## 接手者注意事项

- 开始工作前执行 `git status --short --branch`，确认位于 `hx/0731_live_voice_ux` 且没有混入其他分支修改。
- Demo 的关键实现入口是 `useLiveVoiceDemo.ts`；纯状态、TTS FIFO 和 epoch 在 `liveVoiceCore.ts`，完成消息筛选在 `liveVoiceMessageGate.ts`，旧 supplement 输出隔离在 `supplementOutputQuarantine.ts`。
- partial transcript 绝不能触发 Agent、Tool 或 Task。
- 插话或退出必须先本地停播；不要把 ACK quarantine 或本地 epoch 描述成生产一致性协议。
- 真实 E2E 通过前，不要把“代码路径已接通”写成“语音 Agent Demo 已完整验收”。
- 任何新增 shortcut 都必须同步更新 `TWO_WEEK_DEMO.md` 的 Shortcut Ledger。
