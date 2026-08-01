# JiuwenSwarm Live Voice：方案与接续入口

本目录是 JiuwenSwarm Live Voice 的 Git 版本化事实来源，用于跨机器、跨 Codex 会话持续开发。完整方案、Demo 范围、重要取舍和当前进度必须保存在这里，不能只留在某一次 Codex 对话中。

## 一句话目标

让用户能够通过语音驱动真实 JiuwenSwarm Agent 工作，并在 Agent 思考、调用工具或朗读回答时自然地补充、纠正和打断。

Live Voice 不是单纯的“语音转文字 + 文字朗读”。最终产品还要支持连续会话、真实工具调用、插话修改、后台任务控制以及可靠的异常恢复。

## 当前实施策略

先用两周完成一条真实但受限的纵向链路：

```text
用户说话
→ 语音识别
→ 现有 chat.send / supplement
→ 真实 Agent 与工具调用
→ 真实回答
→ 语音朗读
→ 用户打断、补充并继续
```

Demo 先验证产品流程和体验是否成立；完整方案描述验证通过后需要建设的生产级能力。两者不是互相替代，而是“先走通，再扩宽和加固”。

## 文档地图

| 文件 | 作用 | 更新频率 |
|---|---|---|
| [HANDOFF.md](HANDOFF.md) | 当前可跨机器恢复的实现快照、量化进度、真实阻塞项和接手优先级 | 每个开发阶段或重要验证后更新 |
| [E2E_RUNBOOK.md](E2E_RUNBOOK.md) | 固定环境、锁定依赖、启动服务和真实麦克风/Agent/Tool/TTS 验收步骤 | 环境或启动方式改变时更新 |
| [DEMO_SHOWCASE.md](DEMO_SHOWCASE.md) | 当前能做/不能做、与最终版差异，以及成功率优先的三轮现场展示脚本 | 展示能力、环境或已知风险变化时更新 |
| [FULL_SOLUTION_2026-07-30.md](FULL_SOLUTION_2026-07-30.md) | 完整目标架构、P1/P2/P3 边界、模块和竞品证据；从用户提供的原始方案逐字节复制 | 低，重大架构变化时更新或新增版本 |
| [TWO_WEEK_DEMO.md](TWO_WEEK_DEMO.md) | 两周 Demo 的真实范围、完整版区别、实施日程、验收和降级路径 | Demo 期间按范围变化更新 |
| [DECISIONS.md](DECISIONS.md) | 已接受的关键决策及其原因，避免后续会话反复推翻已有结论 | 每次作出实质性取舍时更新 |
| [STATUS.md](STATUS.md) | 当前进度、已验证内容、阻塞和下一步 | 每次实质性工作结束前更新 |

完整方案原文件的 SHA-256 为：

```text
0294909A79B258194B7B454CF336F164ECF998211E87DC26B453580171EEE3AA
```

## 新 Codex 会话的阅读顺序

1. 先读本文件，理解目标和文档关系。
2. 读 [HANDOFF.md](HANDOFF.md)，恢复最后一次可交接快照和唯一主线。
3. 读 [STATUS.md](STATUS.md)，确认实际进度和下一步。
4. 读 [TWO_WEEK_DEMO.md](TWO_WEEK_DEMO.md)，确认当前交付范围。
5. 准备现场展示时读 [DEMO_SHOWCASE.md](DEMO_SHOWCASE.md)。
6. 启动服务或做真实语音联调前读 [E2E_RUNBOOK.md](E2E_RUNBOOK.md)。
7. 涉及架构、协议或长期边界时，再完整阅读 [FULL_SOLUTION_2026-07-30.md](FULL_SOLUTION_2026-07-30.md)。
8. 涉及取舍时读 [DECISIONS.md](DECISIONS.md)，不要只根据代码现状猜测意图。

## 信息冲突时的优先级

1. 用户在当前任务中的最新明确要求。
2. `DECISIONS.md` 中状态为 `Accepted` 的较新决策。
3. `TWO_WEEK_DEMO.md` 的当前 Demo 范围。
4. `FULL_SOLUTION_2026-07-30.md` 的长期目标。
5. 现有代码只能证明“目前怎么实现”，不能单独决定产品最终应该是什么样。

如果代码和方案不同，应在 `STATUS.md` 记录差距，不要静默把当前实现当作最终设计。

## 每次工作结束前

- 更新 `STATUS.md`：完成了什么、验证结果、已知问题和下一步。
- 如果改变了范围或技术选择，更新 `DECISIONS.md`。
- 如果引入了新的临时简化，在 `TWO_WEEK_DEMO.md` 的 Shortcut Ledger 中记录替换计划。
- 提交并推送到共享远端；仅保存在本地或对话中的信息无法跨机器恢复。
- 不在文档中写入密钥、访问令牌、本机临时目录或仅某台机器可用的绝对路径。

## 关键代码入口

- Live Voice React 编排（识别、`chat.send` / `supplement`、完成消息朗读）：`jiuwenswarm/channels/web/frontend/src/features/live-voice/useLiveVoiceDemo.ts`
- 可纯测试的状态机、TTS FIFO 和 `responseEpoch`：`jiuwenswarm/channels/web/frontend/src/features/live-voice/liveVoiceCore.ts`
- 新会话 promotion 与无声回答恢复判定：`jiuwenswarm/channels/web/frontend/src/features/live-voice/liveVoiceTurnLifecycle.ts`
- 当前语音 Turn 的完成消息筛选：`jiuwenswarm/channels/web/frontend/src/features/live-voice/liveVoiceMessageGate.ts`
- Demo 面板：`jiuwenswarm/channels/web/frontend/src/components/ChatPanel/LiveVoiceDemoBar.tsx`
- supplement ACK 前的旧输出隔离：`jiuwenswarm/channels/web/frontend/src/services/supplementOutputQuarantine.ts`
- 浏览器 STT/TTS：`jiuwenswarm/channels/web/frontend/src/hooks/useSpeech.ts`
- 浏览器识别实例重启、尾段合并与 no-speech 判定：`jiuwenswarm/channels/web/frontend/src/hooks/speechRecognitionLifecycle.ts`
- 现有语音输入骨架：`jiuwenswarm/channels/web/frontend/src/components/ChatPanel/InputArea.tsx`
- Chat 发送、流式消息与中断：`jiuwenswarm/channels/web/frontend/src/hooks/useWebSocket.ts`
- Chat 主面板：`jiuwenswarm/channels/web/frontend/src/components/ChatPanel/index.tsx`
- 浏览器/生成音频停止工具：`jiuwenswarm/channels/web/frontend/src/utils/tts.ts`
- Live Voice 全文清洗、技术标识符朗读化与 TTS 分片：`jiuwenswarm/channels/web/frontend/src/utils/ttsText.ts`
- 浏览器 TTS 与服务端 TTS 的进程内 owner/revision：`jiuwenswarm/channels/web/frontend/src/utils/ttsOutputOwnership.ts`
- Gateway 中断处理：`jiuwenswarm/gateway/message_handler/message_handler.py`
- 可选后台任务入口：`jiuwenswarm/server/agent_ws_server.py` 中的 `schedule.run/status/cancel`

## 直接验证

依赖已经安装后，在 `jiuwenswarm/channels/web/frontend` 目录执行。下面刻意使用本地可执行文件，不要求全局安装 TypeScript 或 Vite：

```text
node node_modules/typescript/bin/tsc --noEmit

npm run test:live-voice-core
npm run test:live-voice-turn-lifecycle
npm run test:live-voice-tts-text
npm run test:live-voice-message-gate
npm run test:supplement-output-quarantine
npm run test:speech-recognition-lifecycle
npm run test:tts-output-ownership

npm run test:stream-delta-batcher
npm run test:create-conversation-session
npm run test:chat-store-streaming
npm run test:settle-historical-tool-executions

node node_modules/vite/bin/vite.js build

cd ../../../..
uv run ruff check jiuwenswarm/gateway/message_handler/message_handler.py
git diff --check
```

截至 2026-08-01，七组 Live Voice 纯逻辑测试共 **47/47**（9 + 6 + 10 + 7 + 6 + 7 + 2），相关既有回归 **22/22**，全前端 TypeScript、Vite build（4490 modules）、Python `ruff` 和 `git diff --check` 已通过。固定 Windows/Chrome 环境也已真实贯通一次“麦克风 → Agent → Terminal Tool → 完整 TTS → 自动回听”；这仍不能替代 10 Turn、10 次打断、20 分钟和连续 3 次脚本的放行验收，详见 [STATUS.md](STATUS.md) 与 [E2E_RUNBOOK.md](E2E_RUNBOOK.md)。

## 分支

当前开发分支：`hx/0731_live_voice_ux`，跟踪 `agtai/hx/0731_live_voice_ux`。
