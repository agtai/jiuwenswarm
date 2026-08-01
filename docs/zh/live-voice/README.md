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

V0 先验证产品流程和体验是否成立；之后沿同一条真实工程路线逐步替换临时实现。两者不是互相替代，而是“先走通，再扩宽和加固”。不会另建一套覆盖所有功能、但与正式实现脱节的模拟 UX 原型。

当前累计版本路线是（版本号与架构 P1/P2/P3 不强行一一对应）：

| 版本 | 主要增量 | 定位 |
|---|---|---|
| V0 | 两周核心体验纵向切片 | 核心旅程完整，不要求所有最终功能完整 |
| V1 Foundation Alpha | P1 Speech Port + P2 最小 response/generation lifecycle 基础 | 正式接口和一致性地基 |
| V2 Realtime Alpha | P2 Conversation Runtime、Realtime Media、流式语音与自然插话 | 最明显的实时语音体验跃迁 |
| V3α | P3α 最小 Task Control 与 D0 | Task Alpha，只覆盖 create/get/list/status/cancel/events |
| V3 | 完整 P1 + P2 + P3 能力 | Full Capability Beta，接近正式能力但仍未生产放行 |
| RC / Production | 可靠性、安全、兼容、可观测和运营加固 | 正式发布 |

版本能力累计保留；共享协议和 ownership 边界冻结后，P1/P2/P3 的部分工程可以并行。后台任务的 A→B 更新需要完整 P3 的 update/provide-input，或显式 cancel/create；不能把 P3α 的状态查询冒充任务更新。

`2c700934aa0024a7ab229644bf15934e9e8170e7` 现在永久保留为**尚未放行**的 V0 Candidate 精确恢复点。D-022 的临时 dirty 窗口已经由 D-030 结束：stash `7f4cfd2eedfb3a177b94f69417143fba441f3671` 已经 apply，原 stash 只作为额外备份保留；Post-V0 foundation 按正常 Git 流程审阅、commit、push，稍后从 `2c700934` 的独立 checkout/worktree 验收 V0，不再反复 stash 当前开发分支。新机器应从共享分支 pull 已推送事实，不能再次 apply 这份本机 stash。

当前 foundation 已把任务边界推进到：服务端对 `schedule.list/status/cancel/logs/delete` 派生 owner + project scope；同一进程、同一 JSON store 路径用共享锁和 ledger 保证 create command 幂等；前端为一次 committed mutation 固定 command ID，只接受严格 exact-key 对账，允许任务在请求期间从 pending 漂移到后续真实状态，并显示真实 task card。它仍不提供跨进程一致性、exactly-once、D1/D2 或持续后台结果监控。稳定句与任务分别由 `VITE_FEATURE_LIVE_VOICE_STREAMING_SPEECH=true`、`VITE_FEATURE_LIVE_VOICE_TASK_DEMO=true` 开启，二者默认关闭。

## 文档地图

| 文件 | 作用 | 更新频率 |
|---|---|---|
| [HANDOFF.md](HANDOFF.md) | 当前可跨机器恢复的实现快照、量化进度、真实阻塞项和接手优先级 | 每个开发阶段或重要验证后更新 |
| [E2E_RUNBOOK.md](E2E_RUNBOOK.md) | 固定环境、锁定依赖、启动服务和真实麦克风/Agent/Tool/TTS 验收步骤 | 环境或启动方式改变时更新 |
| [V0_ACCEPTANCE.md](V0_ACCEPTANCE.md) | V0 放行 Gate、固定语料、分阶段打断口径、证据模板和跨机器冷启动测试 | 验收口径或结果变化时更新 |
| [DEMO_SHOWCASE.md](DEMO_SHOWCASE.md) | 当前能做/不能做、与最终版差异，以及成功率优先的三轮现场展示脚本 | 展示能力、环境或已知风险变化时更新 |
| [FULL_SOLUTION_2026-07-30.md](FULL_SOLUTION_2026-07-30.md) | 完整目标架构、P1/P2/P3 边界、模块和竞品证据；从用户提供的原始方案逐字节复制 | 低，重大架构变化时更新或新增版本 |
| [TWO_WEEK_DEMO.md](TWO_WEEK_DEMO.md) | 两周 Demo 的真实范围、完整版区别、实施日程、验收和降级路径 | Demo 期间按范围变化更新 |
| [POST_V0_DELIVERY_ROADMAP.md](POST_V0_DELIVERY_ROADMAP.md) | V0 之后的双目标优先级、当前切片，以及 D-032 模块测试闭环的唯一详细规范和模板 | Post-V0 开发期间持续更新 |
| [POST_V0_STASH_HANDOFF.md](POST_V0_STASH_HANDOFF.md) | 已 apply stash 的历史内容、备份 SHA、foundation 增量、验证证据和灾难恢复边界；正常续作不重复 apply | stash 状态或恢复保险变化时更新 |
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
4. 读 [TWO_WEEK_DEMO.md](TWO_WEEK_DEMO.md)，确认 V0 原始范围和 shortcut。
5. 读 [POST_V0_DELIVERY_ROADMAP.md](POST_V0_DELIVERY_ROADMAP.md)，确认当前两周目标、下一切片，并在开发任何模块前执行 D-032/§3.1 的测试闭环前置回顾。
6. 读 [POST_V0_STASH_HANDOFF.md](POST_V0_STASH_HANDOFF.md)，理解 stash 已 apply 的历史和额外恢复保险；当前分支已有 foundation 时不要重复 apply。
7. 读 [V0_ACCEPTANCE.md](V0_ACCEPTANCE.md)，确认候选版与已放行版的区别、当前验收 Gate 和证据口径。
8. 读 [DECISIONS.md](DECISIONS.md)，不要只根据代码现状猜测意图。
9. 准备现场展示时读 [DEMO_SHOWCASE.md](DEMO_SHOWCASE.md)。
10. 启动服务或做真实语音联调前读 [E2E_RUNBOOK.md](E2E_RUNBOOK.md)。
11. 涉及架构、协议或长期边界时，再完整阅读 [FULL_SOLUTION_2026-07-30.md](FULL_SOLUTION_2026-07-30.md)。

## 信息冲突时的优先级

产品范围和目标冲突时：

1. 用户在当前任务中的最新明确要求。
2. `DECISIONS.md` 中状态为 `Accepted` 的较新决策。
3. `TWO_WEEK_DEMO.md` 的当前 V0 范围。
4. `FULL_SOLUTION_2026-07-30.md` 的长期目标。

运行事实冲突时，以实际 Git 和证据为准：远端分支/commit 和干净状态 → 较新的 `STATUS.md` → 较新的 `HANDOFF.md`。环境与启动步骤以 `E2E_RUNBOOK.md` 为准，V0 放行以 `V0_ACCEPTANCE.md` 为准，现场操作以 `DEMO_SHOWCASE.md` 为准。现有代码只能证明“目前怎么实现”，不能单独决定产品最终应该是什么样。

如果代码和方案不同，应在 `STATUS.md` 记录差距，不要静默把当前实现当作最终设计。

模块测试闭环的原则以 `DECISIONS.md` 的 D-032 为准，详细执行和模板只以 `POST_V0_DELIVERY_ROADMAP.md` §3.1 为准，当前切片的实际 inventory、场景、tested SHA、结果和 gap 以 `STATUS.md` 为准；V0 是否放行仍只以 `V0_ACCEPTANCE.md` 为准。

## 每次工作结束前

- 更新 `STATUS.md`：完成了什么、验证结果、已知问题和下一步。
- 对每个受影响模块完成 D-032 开发后回顾，在 `STATUS.md` 更新 test inventory、每项 test 的 why、scenario 覆盖、exact tested SHA、精确命令、结果和 gap；未满足闭环 Gate 时如实标记 `PARTIAL` 或 `BLOCKED`。
- 如果改变了范围或技术选择，更新 `DECISIONS.md`。
- 如果引入了新的临时简化，在 `TWO_WEEK_DEMO.md` 的 Shortcut Ledger 中记录替换计划。
- 按 D-030 正常审阅、提交并推送 Post-V0 代码与文档；仅保存在本地、stash 或对话中的信息无法跨机器恢复。V0 验收使用 `2c700934` 的独立 checkout/worktree，不通过反复 stash 当前开发分支实现。
- 不在文档中写入密钥、访问令牌、本机临时目录或仅某台机器可用的绝对路径。

## 关键代码入口

- Live Voice React 编排（识别、`chat.send` / `supplement`、完成消息朗读）：`jiuwenswarm/channels/web/frontend/src/features/live-voice/useLiveVoiceDemo.ts`
- 可纯测试的状态机、TTS FIFO 和 `responseEpoch`：`jiuwenswarm/channels/web/frontend/src/features/live-voice/liveVoiceCore.ts`
- 新会话 promotion 与无声回答恢复判定：`jiuwenswarm/channels/web/frontend/src/features/live-voice/liveVoiceTurnLifecycle.ts`
- 当前语音 Turn 的完成消息筛选：`jiuwenswarm/channels/web/frontend/src/features/live-voice/liveVoiceMessageGate.ts`
- feature flag 下的稳定句预读、rewrite 降级和 final suffix 对账：`jiuwenswarm/channels/web/frontend/src/features/live-voice/liveVoiceStreamingSpeech.ts`
- 受控任务口令、稳定 command ID、严格 exact-key reconciliation、真实状态归一化、确认、cancel+successor 与剩余未知结果防线：`jiuwenswarm/channels/web/frontend/src/features/live-voice/liveVoiceTaskBridge.ts`
- 将任务 Bridge 固定接到 persisted session、`auto_harness` 和 `extended_evolve_pipeline`，并携带 owner/target 与 command identity 的 Web request adapter：`jiuwenswarm/channels/web/frontend/src/features/live-voice/liveVoiceTaskClient.ts`
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
- 最小 Live Voice contract/conformance：`jiuwenswarm/common/schema/live_voice_contract.py`
- Web schedule 单一转发所有权：`jiuwenswarm/gateway/channel_manager/web/app_web_handlers.py`
- 受限后台任务入口和服务端 scope：`jiuwenswarm/server/agent_ws_server.py` 中的 `schedule.run/list/status/cancel/logs/delete`
- AutoHarness 状态、调度和 JSON store：`jiuwenswarm/agents/harness/common/auto_harness/service.py`、`scheduler.py`、`task_store.py`
- 任务请求/响应 adapter 与状态投影：`jiuwenswarm/channels/web/frontend/src/features/live-voice/liveVoiceTaskAdapter.ts`

## 直接验证

依赖已经安装后，在 `jiuwenswarm/channels/web/frontend` 目录执行。下面刻意使用本地可执行文件，不要求全局安装 TypeScript 或 Vite：

这些命令只保存 Foundation 的已知回归基线，不是以后所有模块的固定充分条件。每个新切片必须先按 D-032/路线 §3.1 审阅相关 tests、补齐完整场景矩阵，再根据实际影响增加 targeted、相邻回归、跨层 integration/E2E 和人工证据；不得把下面的历史总数当作模块闭环证明。

```text
node node_modules/typescript/bin/tsc --noEmit

npm run test:live-voice-core
npm run test:live-voice-turn-lifecycle
npm run test:live-voice-tts-text
npm run test:live-voice-message-gate
npm run test:supplement-output-quarantine
npm run test:speech-recognition-lifecycle
npm run test:tts-output-ownership
npm run test:live-voice-streaming-speech
npm run test:live-voice-task-bridge
npm run test:live-voice-task-client
npm run test:live-voice-task-adapter

npm run test:stream-delta-batcher
npm run test:create-conversation-session
npm run test:chat-store-streaming
npm run test:settle-historical-tool-executions

node node_modules/vite/bin/vite.js build

cd ../../../..
uv run ruff check --ignore E402,E712 jiuwenswarm/common/schema/live_voice_contract.py jiuwenswarm/agents/harness/common/auto_harness/scheduler.py jiuwenswarm/agents/harness/common/auto_harness/service.py jiuwenswarm/agents/harness/common/auto_harness/task_store.py jiuwenswarm/gateway/channel_manager/web/app_web_handlers.py jiuwenswarm/server/agent_ws_server.py tests/unit_tests/common/test_live_voice_contract.py tests/unit_tests/agentserver/test_schedule_request.py tests/unit_tests/auto_harness/test_schedule_task_service.py tests/unit_tests/test_app_web_handlers.py
uv run pytest -p no:cacheprovider tests/unit_tests/common/test_live_voice_contract.py
uv run pytest -p no:cacheprovider tests/unit_tests/agentserver/test_schedule_request.py tests/unit_tests/auto_harness/test_schedule_task_service.py
uv run pytest -p no:cacheprovider tests/unit_tests/test_app_web_handlers.py
git diff --check
```

上述 Ruff 命令只检查本批 Foundation 的十个 Python 代码/测试路径；`E402` 与 `E712` 的忽略仅用于保留这些文件中不属于本 diff 的既有基线问题，出处与复核口径见 [POST_V0_STASH_HANDOFF.md](POST_V0_STASH_HANDOFF.md)，不能扩展成全仓 lint 豁免。

`2c700934` V0 baseline 的历史结果是七组 Live Voice 纯逻辑 **47/47**、相关回归 **22/22** 和 Vite build 4490 modules；固定 Windows/Chrome 环境真实贯通一次“麦克风 → Agent → Terminal Tool → 完整 TTS → 自动回听”。这些仍不能替代连续 10 Turn、分阶段 10 次打断、soak 和连续 3 次主演示的 V0 放行验收。

foundation review 修复合入后的最终确认结果是：Live Voice 前端精确测试 **155/155**，chatStore marker 与相关回归 **24/24**，`tsc --noEmit` 通过，Vite build **4494 modules transformed**；Python contract + TaskStore/service + AgentServer schedule request + Web handler 统一精确回归 **226/226**。后端 `3da101cf`、前端 `42e76d30` 已落地；自动化结果仍不能替代稳定句听感和真实有副作用任务 E2E。详细能力和边界见 [STATUS.md](STATUS.md)、[HANDOFF.md](HANDOFF.md) 与 [POST_V0_STASH_HANDOFF.md](POST_V0_STASH_HANDOFF.md)。

## 分支

当前开发分支：`hx/0731_live_voice_ux`，跟踪 `agtai/hx/0731_live_voice_ux`。
