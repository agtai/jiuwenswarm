# JiuwenSwarm Live Voice：方案与接续入口

本目录是 JiuwenSwarm Live Voice 的 Git 版本化事实来源，用于跨机器、跨 Codex 会话持续开发。完整方案、Demo 范围、重要取舍和当前进度必须保存在这里，不能只留在某一次 Codex 对话中。

- 本次文档总审计：2026-08-02
- 共享开发分支：`hx/0731_live_voice_ux`，跟踪 `agtai/hx/0731_live_voice_ux`
- 当前 D-037 V0 Candidate：`ee2896a4afb186e693c720476b6de10797e66f72`（父=`d4c3e32a`）；focused hotfix tests **20/20** 与配置接线冒烟 PASS，完整 Gate 0/1 尚未重跑，V0 未 Released
- 当前动作：本轮在重跑 Gate 3 前停止并关闭验收服务，等待用户调整模型配置；之后只从 detached `ee2896a4` 的全新 Session 先完成 Gate 0/1，再重跑 Gate 3

## 新机器五分钟恢复

推荐用以下 PowerShell 命令直接检出正确共享分支：

```powershell
$env:GIT_LFS_SKIP_SMUDGE = '1'
git clone --origin agtai --branch hx/0731_live_voice_ux --single-branch https://github.com/agtai/jiuwenswarm.git
Set-Location jiuwenswarm
git pull --ff-only agtai hx/0731_live_voice_ux
git status --short --branch
git status --porcelain
git rev-parse HEAD
git rev-list --left-right --count HEAD...agtai/hx/0731_live_voice_ux
git merge-base --is-ancestor ee2896a4afb186e693c720476b6de10797e66f72 HEAD
$LASTEXITCODE
```

通过条件是：当前分支为 `hx/0731_live_voice_ux`、upstream 差异为 `0 0`、`git status --porcelain` 为空，且最后的祖先检查返回 `0`。新 clone 中没有 `7f4c...` stash 是正常现象；Foundation 已经进入共享提交，禁止寻找、重建或再次 apply 该本机历史 stash。

`GIT_LFS_SKIP_SMUDGE=1` 是当前必要的仓库级 clone 绕过：截至 2026-08-02，agtai 的 LFS 端点缺少与 Live Voice 无关的 `docs/assets/videos/compression.mp4` 对象，普通 smudge 会返回 404 并让 checkout 失败。跳过 LFS 不影响 Live Voice 代码、文档、测试或运行；在仓库维护者补传对象前，不要把 `git lfs pull` 作为 Live Voice 恢复前置条件。

拉下代码后，Git 能完整恢复源码、测试、方案、决策、当前阶段和下一任务；lockfile 能恢复依赖集合。Git **不能**恢复模型密钥/完整 API base、用户配置、code project 注册、Session/Task 数据、Chrome 麦克风权限、默认音频设备、网络和真人听感。缺少这些私有条件不阻塞 D-031 的文档预审、纯逻辑/fake-time/接线测试与普通开发，但会阻塞真实 Agent、真实语音和 V0 Release Gate。

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

`d4c3e32aa34a4d26b346cdf0396788d39930cd6b` 保留为精确失败恢复点：其父 `2c700934...` 因 `.agent_history/` 污染在 Gate 1 FAIL；它自身的 Gate 0–2 PASS，但 Gate 3 Turn 3 暴露 Git for Windows 非 ASCII 日期格式 OOM 和重复确定性失败放大器，因此不能 Released。D-037 最小熔断 Candidate 已建立为 `ee2896a4afb186e693c720476b6de10797e66f72`；旧 stash 只保留为本机备份，新机器只认共享 Git。

当前 foundation 已把任务边界推进到：服务端对 `schedule.list/status/cancel/logs/delete` 执行单用户 request owner + project 一致性 scope（Web 身份来自请求，不是生产鉴权）；同一进程、同一 JSON store 路径用共享锁和 ledger 保证 create command 幂等；前端为一次 committed mutation 固定 command ID，只接受严格 exact-key 对账，允许任务在请求期间从 pending 漂移到后续真实状态，并显示真实 task card。它仍不提供跨进程一致性、exactly-once、D1/D2 或持续后台结果监控。稳定句与任务分别由 `VITE_FEATURE_LIVE_VOICE_STREAMING_SPEECH=true`、`VITE_FEATURE_LIVE_VOICE_TASK_DEMO=true` 开启，二者默认关闭。

## 文档地图与权威边界

| 类别 | 文件 | 唯一职责 | 何时读取/更新 |
|---|---|---|---|
| 当前事实 | [STATUS.md](STATUS.md) | 已完成、证据、缺口、双轨下一步和每个模块的 D-032 closure 记录 | 每次实质性工作前后；运行事实的文档真源 |
| 当前交接 | [HANDOFF.md](HANDOFF.md) | 可复制的 Git 恢复步骤、当前恢复结论、接手入口和禁止事项 | 跨机器/新 Session；阶段或恢复条件变化时更新 |
| 文档路由 | 本文件 | 当前摘要、阅读顺序、冲突优先级、代码/验证入口 | 文档拓扑或恢复方式变化时更新 |
| 有效决策 | [DECISIONS.md](DECISIONS.md) | D-001 起的 Accepted/Superseded 取舍 | 做范围或技术选择前；新取舍追加，不静默改历史 |
| 当前路线 | [POST_V0_DELIVERY_ROADMAP.md](POST_V0_DELIVERY_ROADMAP.md) | Post-V0 优先级、D-031，以及 D-032 唯一详细测试闭环规范/模板 | Post-V0 规划和每个模块开发前后 |
| V0 范围 | [TWO_WEEK_DEMO.md](TWO_WEEK_DEMO.md) | V0 定义、shortcut ledger；D1–D10 日程是历史原始计划 | 判断 V0 shortcut 或修改 V0 边界时 |
| V0 Gate | [V0_ACCEPTANCE.md](V0_ACCEPTANCE.md) | `d4c3e32a` 失败历史、D-037 新 Candidate 的 Release Gate、detached-safe 语料和证据模板 | 只在 V0 验收轨使用 |
| 故障复盘 | [GIT_DATE_FORMAT_OOM_INCIDENT_2026-08-02.md](GIT_DATE_FORMAT_OOM_INCIDENT_2026-08-02.md) | Gate 3 Git 日期格式 OOM、重复失败放大、责任边界、当前修复与生产资源保护缺口 | 调查 D-037、工具资源治理或类似重复失败前 |
| 运行操作 | [E2E_RUNBOOK.md](E2E_RUNBOOK.md) | 依赖、私有状态边界、隔离数据目录、启动、健康和真实 E2E | 启动任何服务或做真机验证前 |
| 展示操作 | [DEMO_SHOWCASE.md](DEMO_SHOWCASE.md) | detached V0 候选的成功率优先展示脚本和退场方案 | 彩排/演示前 |
| 历史证据 | [POST_V0_STASH_HANDOFF.md](POST_V0_STASH_HANDOFF.md) | D-022/D-030 stash 历史、Foundation 取证和本机灾难恢复说明 | 普通续作不读；仅取证/灾难恢复 |
| 不可变架构源 | [FULL_SOLUTION_2026-07-30.md](FULL_SOLUTION_2026-07-30.md) | 截至 2026-07-30 的完整方案、P1/P2/P3 和竞品证据 | 长期架构/协议/生产边界任务完整阅读；不作为当前任务表 |

`FULL_SOLUTION_2026-07-30.md` 保持日期化源快照，不直接改写；后续变化进入新版本方案、`DECISIONS.md` 和 Roadmap。用户原文件的 **LF 规范化内容** SHA-256 为：

```text
0294909A79B258194B7B454CF336F164ECF998211E87DC26B453580171EEE3AA
```

Windows `core.autocrlf=true` checkout 会把 LF 变为 CRLF，因此直接对工作区文件执行 `Get-FileHash` 会得到不同字节哈希；将 CRLF 规范化回 LF 后必须得到上述值。这是行尾差异，不是方案内容丢失。源快照中的代码链接按仓库根路径理解；当前可导航代码入口以本文件“关键代码入口”为准。

## 新 Codex 会话的阅读顺序

任何规划、开发、review 或测试先读当前事实集：

1. 本文件：恢复目标、文档权威和不可恢复边界。
2. [STATUS.md](STATUS.md)：确认 Git 对应的实际进度、证据和下一步。
3. [HANDOFF.md](HANDOFF.md)：执行接手检查，确认没有沿用旧聊天或本机 stash。
4. [DECISIONS.md](DECISIONS.md)：至少读 D-018～D-036 和当前任务涉及的更早决策。
5. [POST_V0_DELIVERY_ROADMAP.md](POST_V0_DELIVERY_ROADMAP.md)：读当前优先级；开发模块前执行 D-032/§3.1。
6. [TWO_WEEK_DEMO.md](TWO_WEEK_DEMO.md)：确认 V0 shortcut 和正式替换边界。

随后按任务路由：

- 验收 V0：读 [V0_ACCEPTANCE.md](V0_ACCEPTANCE.md)、[E2E_RUNBOOK.md](E2E_RUNBOOK.md)、[DEMO_SHOWCASE.md](DEMO_SHOWCASE.md)。
- 启动服务、配置模型或做真实 Agent/Tool/语音：读 [E2E_RUNBOOK.md](E2E_RUNBOOK.md)。
- 改长期架构、P1/P2/P3、协议、ownership、取消、持久化或生产 Gate：完整读不可变 [FULL_SOLUTION_2026-07-30.md](FULL_SOLUTION_2026-07-30.md)。
- 只有调查历史 Foundation/stash 或本机灾难恢复时才读 [POST_V0_STASH_HANDOFF.md](POST_V0_STASH_HANDOFF.md)；普通新 clone 不需要它执行任何 stash 操作。

新 Session 在修改文件前应能准确复述：共享分支与 `2c700934 → d4c3e32a → ee2896a4` 的关系；两次失败分别证明了什么；为什么 Gate 3 不能只改题做绿；D-037 focused tests 与尚未重跑的 Gate 0/1；Foundation、D-033/D-034 和私有运行条件边界。答不出来时继续阅读，不开始实现。

## 信息冲突时的优先级

范围、路线或目标冲突时先分轨：

1. 用户在当前任务中的最新明确要求。
2. `DECISIONS.md` 中状态为 `Accepted` 的较新决策。
3. V0 范围、shortcut 与放行：分别以 `TWO_WEEK_DEMO.md` 和 `V0_ACCEPTANCE.md` 为准；它们不覆盖 Post-V0 当前路线。
4. Post-V0 当前优先级、切片边界和 D-032 详细执行：以 `POST_V0_DELIVERY_ROADMAP.md` 为准；实际 inventory/证据/gap 以较新的 `STATUS.md` 为准。
5. 长期 P1/P2/P3 架构目标：以不可变 `FULL_SOLUTION_2026-07-30.md` 为源，再由较新的 Accepted decisions 明确修订。

运行事实冲突时，以实际 Git 和证据为准：远端分支/commit 和干净状态 → 较新的 `STATUS.md` → 较新的 `HANDOFF.md`。环境与启动步骤以 `E2E_RUNBOOK.md` 为准，V0 放行以 `V0_ACCEPTANCE.md` 为准，现场操作以 `DEMO_SHOWCASE.md` 为准。现有代码只能证明“目前怎么实现”，不能单独决定产品最终应该是什么样。

如果代码和方案不同，应在 `STATUS.md` 记录差距，不要静默把当前实现当作最终设计。

模块测试闭环的原则以 `DECISIONS.md` 的 D-032 为准，详细执行和模板只以 `POST_V0_DELIVERY_ROADMAP.md` §3.1 为准，当前切片的实际 inventory、场景、tested SHA、结果和 gap 以 `STATUS.md` 为准；V0 是否放行仍只以 `V0_ACCEPTANCE.md` 为准。

## 每次工作结束前

- 更新 `STATUS.md`：完成了什么、验证结果、已知问题和下一步。
- 对每个受影响模块完成 D-032 开发后回顾，在 `STATUS.md` 更新 test inventory、每项 test 的 why、scenario 覆盖、exact tested SHA、精确命令、结果和 gap；未满足闭环 Gate 时如实标记 `PARTIAL` 或 `BLOCKED`。
- 如果改变了范围或技术选择，更新 `DECISIONS.md`。
- 如果引入了新的临时简化，在 `TWO_WEEK_DEMO.md` 的 Shortcut Ledger 中记录替换计划。
- 按 D-030 正常审阅、提交并推送 Post-V0 代码与文档；仅保存在本地、stash 或对话中的信息无法跨机器恢复。D-037 修复以 `d4c3e32a` 为基线建立新 Candidate，后续 V0 验收只使用新 SHA 的独立 checkout/worktree，不通过反复 stash 当前开发分支实现。
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

`d4c3e32a` V0 Candidate 继承父提交 `2c700934` 的 Live Voice 代码；七组 Live Voice 纯逻辑 **47/47**、相关回归 **22/22**、TypeScript、Vite build、Ruff 和 diff-check 已在新候选 Gate 1 通过，固定 Windows/Chrome 环境也曾真实贯通一次“麦克风 → Agent → Terminal Tool → 完整 TTS → 自动回听”。2026-08-02 Gate 1 Attempt 1 虽然真实走完 `chat.send → chat.tool_call → chat.tool_result → chat.final`，但返回 `2c700934,1`，因运行时生成 `.agent_history/` 导致工作区不干净，不能计为 PASS；修复后的新候选再次走完真实主链并返回 `d4c3e32a,0`，当前 Gate 0–2 已 PASS。上述证据仍不能替代连续 10 Turn、分阶段 10 次打断、soak 和连续 3 次主演示的 V0 放行验收。

foundation review 修复合入时的历史确认结果是：Live Voice 前端精确测试 **155/155**，chatStore marker 与相关回归 **24/24**，`tsc --noEmit` 通过，Vite build **4494 modules transformed**；Python contract + TaskStore/service + AgentServer schedule request + Web handler 统一精确回归 **226/226**。155 与 24 两组有 9 项重叠，不能相加；Git 保存测试代码、命令和结果记录，但未保存 JUnit 产物，新机器只有实际复跑后才能声称本机通过。后端 `3da101cf`、前端 `42e76d30` 已落地；自动化结果仍不能替代稳定句听感和真实有副作用任务 E2E。详细能力和边界见 [STATUS.md](STATUS.md)、[HANDOFF.md](HANDOFF.md) 与 [POST_V0_STASH_HANDOFF.md](POST_V0_STASH_HANDOFF.md)。

## 分支

当前开发分支：`hx/0731_live_voice_ux`，跟踪 `agtai/hx/0731_live_voice_ux`。
