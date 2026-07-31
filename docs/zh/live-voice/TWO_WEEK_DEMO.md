# JiuwenSwarm Live Voice：两周纵向 Demo 方案

- 日期：2026-07-31
- 目标分支：`hx/0731_live_voice_ux`
- 人力假设：1 人，约 10 个工作日，可使用 Codex 辅助开发
- 交付名称：Live Voice UX / Vertical Slice Demo
- 交付性质：验证产品流程和感知效果，不宣称达到生产 Alpha

## 1. 先说结论

两周内最重要的不是把完整架构的所有模块各写一部分，而是完整走通一次真实用户旅程：

```text
用户说话
→ 系统听懂并显示字幕
→ 只在用户说完后提交
→ 真实 JiuwenSwarm Agent 理解请求并调用工具
→ 返回真实执行结果
→ 系统朗读结果
→ 用户可以打断、补充或改变要求
→ Agent 根据新要求继续工作
```

这条链路的起点、Agent 处理和最终结果都是真实的。Demo 简化的是语音底层、设备范围、异常恢复和通用任务管理，不是伪造回答或跳过 Agent。

可以把两者理解为：

- Demo 是先修通一条从起点到终点的单车道，确认目的地值得去、路线走得通。
- 完整版是在同一条路线上增加多车道、护栏、监控、备用路线和全天候运行能力。

## 2. Demo 必须验证的核心命题

### 2.1 语音能够驱动真实 Agent

用户说：

> 检查当前仓库的 Git 状态，并告诉我有哪些未提交修改。

系统必须把最终识别文字交给现有 Chat/Agent 主链。Agent 应真实调用 Git 或终端工具、读取实际结果，再把回答返回给用户。不能针对演示语句返回预设答案。

### 2.2 连续语音协作比单次听写更有价值

用户不只是说完一句、等待一句，还可以继续追问：

> 只看 Live Voice 相关文件。

Agent 应继承当前会话上下文，而不是从头开始一段互不相关的问答。

### 2.3 用户能够打断并修正 Agent

Agent 正在生成或朗读较长回答时，用户可以重新开麦并说：

> 停，不要分析前端，只看 Gateway。

系统要立即停止本地朗读，并将最终识别出的新要求通过现有 `supplement` 中断路径交给 Agent。旧回答的迟到文本和音频不能在新回答开始后复活。

### 2.4 状态让用户知道系统正在做什么

界面至少明确显示：

- `listening`：正在听用户说话；
- `thinking`：Agent 已收到请求，正在思考或调用工具；
- `speaking`：正在朗读 Agent 回答；
- `interrupted`：当前回答已被用户打断；
- `error`：麦克风、识别或播放失败，可退回文字聊天。

### 2.5 可选：语音控制一个真实后台任务

只有核心语音闭环在第 7 天前稳定，才增加下面的受限场景：

```text
“放到后台：检查当前仓库”
→ 调用现有 schedule.run
→ 得到真实 task_id
→ 用户继续语音对话
→ “检查后台任务进度”调用 schedule.status
→ “取消后台任务”调用 schedule.cancel
```

这里可以把口令和“最近一个任务”写死，但任务 ID、执行状态和取消结果必须来自真实接口。它只验证语音控制后台工作的产品感觉，不代表通用 Task Control 已经完成。

## 3. Demo 版与完整版的区别

| 用户关心的能力 | 两周 Demo | 完整版 | Demo 能验证什么 |
|---|---|---|---|
| 语音发起 Agent 请求 | 完成，最终识别文字进入现有 `chat.send` | 完成，并支持更多平台、语言和连接方式 | 用户能否自然地用语音驱动 Agent |
| Agent 调用工具 | 完成，复用现有真实 Agent/Tool 链 | 完成，并补齐统一进度、权限和可恢复语义 | 语音是否适合驱动真实工作，而不只是聊天 |
| 连续上下文 | 完成，复用现有 Session | 完成，并有更严格的会话事实和播放历史 | 多轮语音协作是否自然 |
| 判断用户说完 | 固定停顿时间或显式结束 | 声音、语义和上下文共同判断 | 固定规则下的交互节奏是否可接受 |
| 朗读回答 | 浏览器整段朗读；稳定后按完整句子排队 | 服务端流式 TTS、音频分片、背压和播放确认 | Agent 回答被听到时是否清楚、简洁、及时 |
| 插话 | 重新开麦/点击即可确定性打断；耳机下尝试自然开口 | 持续监听、回声消除、误打断恢复、精确历史修复 | 用户是否需要打断，以及 `supplement` 语义是否正确 |
| 旧回答隔离 | 前端递增 epoch，清空旧播放队列 | 客户端与服务端共同使用 response ID、fence 和 ACK | 新旧回答不会在主要演示路径中串音 |
| 音频传输 | 浏览器本地 STT/TTS；Agent 仍走现有文字 WebSocket | 独立实时音频链路、二进制帧、背压和重连 | 产品体验，而不是媒体基础设施能力 |
| 设备和平台 | 固定 Windows、Chrome/Edge、中文、默认设备和耳机 | 多设备、多平台、多语言、设备切换 | 固定目标环境能否成立 |
| 后台任务 | 可选，只支持一个最近任务和固定口令 | 多任务、稳定 ID、持久状态、恢复、审批和精确寻址 | 语音控制后台工作的价值，不验证完整耐久性 |
| 异常恢复 | 明确报错并回退文字聊天 | 自动重连、状态恢复、重复抑制、跨重启恢复 | 降级是否可理解，不验证生产可靠性 |
| 质量验证 | 固定机器的短时脚本和 20 分钟稳定性 | 大样本 p95、长时 soak、故障注入和多环境矩阵 | 是否值得进入下一阶段工程化 |

因此，Demo 不是“只完成说话”。它必须完成真实的：

```text
Speech → Agent → Tool → Result → Speech
```

Demo 暂时不完成的是这条链路周围的大规模可靠性和通用性。

## 4. 最小技术路径

### 4.1 首选路径

```text
Browser SpeechRecognition
→ final transcript
→ 现有 chat.send / chat.interrupt(supplement)
→ 现有 Agent、Harness 和工具
→ 现有 chat.delta / chat.final
→ 浏览器 SpeechSynthesis 队列
```

这样不增加音频后端、不增加媒体 WebSocket、不更换 Agent 大脑，只把现有能力串成一条语音体验。

### 4.2 Day 1 技术闸门

必须在最终演示机器上测试：

1. Chrome、Edge 和 Windows Desktop/WebView2 的麦克风授权；
2. `zh-CN` 连续识别、临时结果和最终结果；
3. 浏览器 TTS 是否有可用中文音色；
4. 开始、停止识别和取消 TTS 的实际延迟；
5. 戴耳机时能否在朗读期间再次识别用户；
6. WebView2 重新启动后是否反复丢失麦克风权限。

当天必须选择演示载体，不能连续数日修 WebView2 兼容问题：

- WebView2 稳定：以 Desktop 演示。
- WebView2 不稳但 Chrome/Edge 稳定：以 Web 前端演示。
- Web Speech 本身不稳：Day 2 切到单一云厂商的薄级联方案，优先考虑中文支持明确的 Azure Speech。

### 4.3 为什么本轮不直接使用原生 Realtime 模型或 LiveKit

原生 speech-to-speech 能较快做出很自然的独立语音样例，但通常会让新的实时模型成为对话大脑。为了保留 JiuwenSwarm 现有 Session、工具、审批和 Agent 行为，就需要迁移工具或额外包装现有 Agent，反而增加两周主线风险。

LiveKit 能解决大量实时媒体问题，但还会引入 Room、Token、Agent Worker、WebRTC 客户端以及现有 Agent Adapter。它更适合 Demo 验证成功后的生产化阶段。

参考资料：

- [MDN SpeechRecognition](https://developer.mozilla.org/en-US/docs/Web/API/SpeechRecognition)
- [OpenAI Voice agents：speech-to-speech 与 chained 的适用场景](https://developers.openai.com/api/docs/guides/voice-agents)
- [Azure Speech 连续识别](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/how-to-recognize-speech)
- [Azure Speech 语言支持](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/language-support)

## 5. 当前仓库可以直接复用的能力

| 现有能力 | 代码位置 | Demo 中的用途 |
|---|---|---|
| 浏览器 STT/TTS Hook | `jiuwenswarm/channels/web/frontend/src/hooks/useSpeech.ts` | 连续识别、interim/final、静音提交和本地朗读 |
| 语音输入骨架 | `jiuwenswarm/channels/web/frontend/src/components/ChatPanel/InputArea.tsx` | 参考或复用已有自动提交和处理中分流逻辑 |
| Chat 发送和中断 | `jiuwenswarm/channels/web/frontend/src/hooks/useWebSocket.ts` | `chat.send`、`supplement`、停止当前 TTS |
| Chat UI 容器 | `jiuwenswarm/channels/web/frontend/src/components/ChatPanel/index.tsx` | 挂载 Live Voice 入口和状态面板 |
| 本地音频停止 | `jiuwenswarm/channels/web/frontend/src/utils/tts.ts` | 用户插话或退出时立即静音 |
| Gateway 中断语义 | `jiuwenswarm/gateway/message_handler/message_handler.py` | 取消旧生成并把补充要求排入 Agent |
| 后台任务接口 | `schedule.run/status/cancel` | 可选的单一后台任务演示 |

服务端 `tts.synthesize` 当前没有注册，因此 Demo 主线使用浏览器 TTS，不花时间恢复服务端音频生成。

## 6. Demo 的最小代码划分

### 6.1 一个前端控制器

新增一个 `LiveVoiceDemo` 组件或 Hook，先集中负责：

- `idle/listening/thinking/speaking/interrupted/error` 状态；
- 开始、退出和重新开麦；
- interim/final 字幕；
- final transcript 的唯一提交；
- Agent 回复文本的朗读；
- TTS 队列和 epoch；
- 权限及识别失败时回退文字聊天。

Demo 阶段不需要为了架构美观提前拆成十个 Port。逻辑稳定后再按完整方案拆分。

### 6.2 复用现有 Agent 桥接

- 空闲时的 final transcript 调用现有 `onSendMessage`。
- Agent 正在工作时的 final transcript 调用现有 `onInterrupt`，意图使用 `supplement`。
- 不新建一套 Voice Agent，也不复制现有 Tool 调用逻辑。

### 6.3 一个本地回答编号

维护递增的 `responseEpoch`：

- 新用户 Turn、插话、退出 Live Voice 时都执行 `responseEpoch += 1`；
- TTS 队列项携带创建时的 epoch；
- 播放前如果 epoch 已过期，直接丢弃；
- 插话时立即 `stopAllTts()` 并清空待播句子。

它不是完整版的分布式回答生命周期，但足以保证固定演示路径中旧声音不会复活。

### 6.4 最小状态变化

```text
idle
  → listening
  → thinking
  → speaking
  → listening

speaking + 用户重新开麦
  → interrupted
  → listening

任意状态
  → error 或 idle
```

## 7. Demo 范围

### 7.1 必须完成

- `Experimental Live Voice` 功能开关。
- 明确的进入、退出和麦克风状态。
- interim 字幕可见，但只允许 final transcript 触发副作用。
- final transcript 调用真实 Agent。
- Agent 能真实调用现有工具，并展示真实执行结果。
- Agent 回答自动朗读。
- 重新开麦或点击打断时立即本地停止声音。
- 打断后的新要求进入现有 `supplement`。
- 旧 TTS 队列和迟到回调不能在新回答中恢复。
- 权限、识别或播放失败时显示原因并退回文字聊天。
- 关闭功能开关后，原文字聊天无回归。

### 7.2 有余量才做

- 根据标点分句，在整段回答完成前开始朗读。
- 戴耳机时持续监听，实现自然开口打断。
- 单一 `schedule.run/status/cancel` 后台任务场景。
- 任务完成时进行一次简短语音通知。

### 7.3 本轮明确不做

- WebRTC、独立二进制音频 WebSocket、20ms PCM 分片、ACK 和背压。
- 自研 AEC、降噪、自动增益和设备选择。
- 复杂 VAD、语义结束判断和误打断恢复。
- 完整 Conversation Runtime、服务端状态机和跨进程 fence。
- 字级播放游标和严格 presented history。
- Provider-neutral Adapter、能力协商和一致性测试套件。
- 多语言、多声音、移动端、设备热插拔。
- 自动重连后的语音续播。
- 通用 Task Core、多任务消歧、D1/D2 恢复和副作用协调。

## 8. Prototype Shortcut Ledger

这张表必须随实现更新。临时简化应明确写出来，而不是以后靠猜。

| 临时简化 | Demo 中仍然真实的部分 | Demo 不能证明的部分 | 完整版替换方向 |
|---|---|---|---|
| 固定 Windows + Chrome/Edge | 真实麦克风、真实用户操作 | 跨平台兼容性 | 完整设备和权限层 |
| 固定 `zh-CN` | 真实中文识别和朗读 | 多语言切换 | Speech Provider 能力协商 |
| 默认麦克风、耳机 | 真实输入输出 | 扬声器回声、设备切换 | Audio Device & I/O、AEC |
| 只在 Agent 模式启用 Live Voice | 单 Agent Session 中的真实 `chat.send` / `supplement`、Agent 和工具调用 | Team Leader、多成员并行输出应该由谁朗读，以及 Team 模式插话语义 | 建立统一 response ownership、Team 事件模型和可配置朗读策略后再开放 Team 模式 |
| 固定约 1 秒停顿提交 | final 后真实调用 Agent | 自然语义结束判断 | VAD/EOT/Interaction Engine |
| 浏览器 STT/TTS | 真实语音和真实回答 | 服务端流式媒体及 Provider 可替换性 | Speech Port + Realtime Media |
| 整段或按句 TTS | 真实回答内容被朗读 | token/audio 级实时性 | streaming TTS 与播放队列 |
| 重新开麦即打断 | 真实停止和真实 supplement | 完全免手操作和误打断恢复 | 持续采集、AEC、false-barge-in recovery |
| 前端 `responseEpoch` | 演示路径中旧音频不会复活 | 跨端乱序和断线一致性 | response ID、generation fence、ACK |
| supplement ACK 前前端 quarantine 旧输出 | 当前有序 WebSocket 路径中，真实 supplement 发出后旧 delta/final/reasoning/media 不进入消息和朗读，ACK 后替代回答恢复 | ACK 丢失、断线重放、多端并发、服务端跨生成乱序，以及任意模式的通用隔离 | 服务端分配 response/generation ID，客户端与服务端共同执行 fence，并定义可恢复 ACK 协议 |
| 一个 `lastTaskId` | 指定任务的真实状态和取消 | 多任务消歧和通用控制 | Task Control Core |
| 固定任务口令 | 真实任务接口 | 开放式任务意图理解 | Voice–Task Bridge 与确认策略 |

原则：可以写死环境和选择，不能写死 Agent 的回答、工具结果或成功状态。

## 9. 十个工作日计划

| 日期 | 工作内容 | 当日退出条件 |
|---|---|---|
| D1 | 真机 Spike：权限、中文 STT、TTS、停止延迟、耳机插话；选择 Desktop、浏览器或 Provider fallback | 当天确定演示载体和语音实现，不继续无期限排查 |
| D2 | Live Voice 面板、功能开关、五态显示、进入/退出、interim/final 字幕 | 能稳定开始、停止；退出后释放麦克风 |
| D3 | final → `chat.send`；处理中 final → `supplement`；增加重复提交保护 | 连续说 10 句，每句只产生一个用户 Turn，partial 副作用为 0 |
| D4 | Agent final 自动朗读、文本清洗、thinking/speaking 状态切换 | 完成“说一句 → Agent/Tool → 真实回答 → 自动朗读”闭环 |
| D5 | TTS FIFO、按句播放（若稳定）、`responseEpoch` 和退出清理 | 打断后旧音频不会恢复；分句不稳则退回整段朗读 |
| D6 | 确定性插话：重新开麦立即静音，final 走 supplement；耳机下尝试自然开口 | 点击/重新开麦打断 10/10；自然打断不足则保留显式路径 |
| D7 | 权限拒绝、识别错误、网络错误、会话切换、文字回归和 20 分钟运行 | 核心 Demo 稳定；未通过则砍掉全部后台任务增强 |
| D8 | 可选：固定口令调用 `schedule.run`，记录一个真实 `task_id`，显示状态卡 | 不影响语音主链；否则删除此增强 |
| D9 | 可选：`schedule.status/cancel`；或全部用于修复主链；完整脚本彩排 | 主脚本连续成功 3 次，代码冻结 |
| D10 | 只修缺陷，整理日志和已知限制，准备现场环境、文字降级和录屏 | 现场脚本与降级脚本分别成功两遍，不再加功能 |

排期纪律：6 天完成真实主链，1 天稳定，2 天可砍增强，1 天冻结。

## 10. 验收脚本

固定一台 Windows 机器、固定网络、中文和耳机：

1. 关闭 Live Voice，发送文字消息，确认原聊天正常。
2. 打开 Live Voice，允许麦克风，界面显示正在听。
3. 说：“检查当前仓库状态，并告诉我有哪些未提交修改。”
4. interim 字幕出现，但 final 前消息列表不能新增用户消息。
5. final 后只生成一条用户消息；Agent 真实调用工具并返回实际结果。
6. 系统自动朗读 Agent 结果。
7. 说：“继续分析最主要的三个架构问题。”
8. Agent 分析或朗读期间重新开麦，说：“停，只分析 Live Voice 相关代码。”
9. 旧朗读立即停止，新要求只提交一次；Agent 按新方向继续，旧声音不再恢复。
10. 说：“把结论整理成三点。”验证上下文延续。
11. 朗读期间退出 Live Voice，麦克风和声音同时停止，文字聊天仍可使用。
12. 拒绝麦克风权限或模拟识别失败，界面明确报错并提供文字降级。
13. 可选：用固定口令创建、查询并取消一个真实后台任务。

## 11. Demo 完成标准

- 连续 10 个语音 Turn，重复提交为 0。
- partial transcript 触发 Agent、Tool 或 Task 的次数为 0。
- 固定环境下，重新开麦/点击打断到本地静音目标小于 300ms，10/10 成功。
- 用户停止说话到 final 消息提交目标小于 2 秒。
- 可朗读文本就绪到开始播放目标小于 1 秒。
- 打断后旧音频恢复次数为 0。
- 连续 20 分钟或 20 Turn 不需要刷新页面。
- 主演示脚本连续成功 3 次。
- 语音失败后，文字聊天仍然正常。

这些是 Demo 的固定环境目标，不等同于完整版的跨环境 p95 服务承诺。

### 11.1 放行闸门与固定环境

“代码完成”不等于“可上台”。Demo 只有在固定演示机上同时满足以下条件才允许宣称完成：

1. 浏览器收到后端 `connection.ack`。
2. 真实麦克风产生中文 final，interim 不触发任何请求。
3. final 只产生一个用户 Turn。
4. 固定工具口令实际出现 `chat.tool_call`、`chat.tool_result`、`chat.final`。
5. 完整回答实际朗读。
6. 10 个连续语音 Turn 无重复提交。
7. 10 次打断均立即静音，旧声音恢复 0 次。
8. 20 分钟或 20 Turn 无需刷新。
9. 主演示脚本连续成功 3 次。
10. 失败后文字聊天仍正常。

环境、依赖、配置、服务启动和证据模板统一见 [E2E_RUNBOOK.md](E2E_RUNBOOK.md)。未通过的闸门是当前 Demo 阻塞项；Team、WebView2、多语言、全双工/AEC、流式 TTS 和生产级 generation fence 不属于本轮放行条件。

## 12. 绝不能为了赶进度而省略的内容

- final transcript 才能触发 Agent 或工具；partial 只能展示。
- 用户打断或退出时必须先本地停播，不能等待服务端响应。
- 旧 TTS 队列必须失效，不能和新回答串音。
- 麦克风是否开启必须可见，权限失败不能静默。
- 功能开关关闭后，原有文字路径必须通过回归。
- 如果演示后台任务，取消必须命中界面上可见的明确 `task_id`。
- 所有 fake、固定口令和 hardcode 必须明确标为 Demo。
- 不能把 Browser Speech + 文字 WebSocket 宣传为生产级全双工实时媒体。

## 13. 风险和降级路径

| 风险 | 最晚决策点 | 降级方式 |
|---|---:|---|
| WebView2 语音识别或权限不稳定 | D1 | 改用 Chrome/Edge Web 前端演示 |
| Web Speech 中文识别不稳定 | D1/D2 | 切单一 Azure Speech 薄级联 |
| TTS 被麦克风识别成用户声音 | D2/D6 | 固定耳机；TTS 期间暂停识别；使用重新开麦打断 |
| 连续识别自动结束或重启不稳 | D3 | 改为 tap-to-talk 或按住说话 |
| 分句流式朗读重复或乱序 | D5 | 只在 `chat.final` 后整段朗读 |
| supplement 行为不稳定 | D6 | 插话只立即停播；待当前生成结束后作为普通下一 Turn 提交，并明确记录限制 |
| Agent 首次结果较慢 | D4 | 显示真实 thinking/tool 状态；不伪造答案或任务进度 |
| 后台任务影响主链 | D7 | 完整删除 D8/D9 任务增强 |
| 现场 Provider 或网络异常 | 演示前 | 运行预检，保留文字入口并准备最近一次真实录屏 |

## 14. Demo 之后如何演进

Demo 完成后不要直接把临时代码宣布为架构，而是根据实测结果依次工程化：

1. 稳定 STT/TTS 和设备权限，确定首个正式 Provider。
2. 建立 Conversation Runtime 和服务端 response/generation fence。
3. 建设真正的实时媒体链路、背压和重连。
4. 实现持续监听、自然插话、回声处理和 presented history。
5. 再建设通用 Task Control、多个任务、恢复和副作用协调。

两周 Demo 的任务是回答“这个体验值不值得继续做、最痛的问题在哪里”，不是提前替完整版回答所有工程问题。
