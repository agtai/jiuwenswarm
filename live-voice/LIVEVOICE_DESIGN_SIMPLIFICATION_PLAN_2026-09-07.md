# LiveVoice 设计简化瘦身计划（语义变更路径）— 2026-09-07

> 标准：按"加上设计简化（减值类型、守卫、owner，属语义变更），目标 60,000–65,000 行；只有重写合同才到得了，
> 需要用户授权并重写测试"执行。本文是这条路径的计划与检查记录，不是行为保持的瘦身包；每个包都改变
> 合同语义，按 root `TESTING.md` 作为语义变更定级，先授权后开工。
>
> - 基线：`codex/live-voice-refactor-20260907@e8b8f85f6`（= `hx/0812_live_voice_w3@26eb034bc` + 7 个提交：
>   删除全部 live-voice 文档与测试、清理零 caller 代码）。远端 w3 tip 已前进到 `d8ee9e6d3`，本分支落后 19 个提交，
>   开工前先重基线。
> - 口径：physical LOC（空行、注释、docstring 计入）；Native（OpenAI Realtime）15 个文件 11,178 行按既有决定排除，
>   但 §3 标出它必须后续采用的合同。
> - 复现：`python scripts/live_voice/slimming/module_buckets.py --rev HEAD`（18 模块行数）、
>   `python scripts/live_voice/slimming/anatomy_modules.py --rev HEAD`（值类型/守卫/owner/codec 解剖）。

## 0. 结论先行

1. 本分支的 LiveVoice 专属生产代码 **158,594 行**（不含 Native），比 `7c7aad7b8` 的 171,431 少 12.8K：
   零 caller 退休已经做完，剩下的没有一行是"死"的。
2. 行数的去向不是重复而是合同密度：577 个值类型 14.1K 行、75 个 owner 类 68.0K 行、60 个异常类型、
   `if…: raise` 守卫 24.4K 行（15%）、`__post_init__` 校验 4.6K、codec/snapshot 3.8K；前端每 31 行一个 `throw`。
   官方 Hermes voice 同类代码 23 个类、2 个值类型、守卫 2%。
3. 机械地"保留合同只重写内部"只能到 **≈86K**（§2 公式列；探针实测单模块 −17.6%）。要到 60–65K，必须改合同：
   值类型 577 → ≤150，异常类型 60 → ≤12，守卫 24.4K → ≤4K，owner 75 → ≤30，前端 `throw` 1,073 → ≤150。
4. 按 §3 逐模块重写后的规划区间是 **48K–62K**，承诺带 **60–65K**（含约 10% 未知）。每个模块给出要合并的
   owner、要删的值类型与守卫、改变的语义，以及验收它的新测试。
5. 本分支已删除全部 LiveVoice 测试（−221K 行）与文档，所以重写期间没有回归网；§5 规定新 oracle 从哪里来，
   §6 的每个包都以"新测试 + 物理 journey"验收，而不是以旧测试通过验收。
6. 需要用户的五个决定见 §7：授权语义变更、退休从未启用的 OTel 产品观测链、退休 legacy 链与其 feature flag、
   Task 家族在仓库内重写为小台账（不等 AgentCore F1–F6）、错误码归并策略。

## 1. 标准与预算

### 1.1 允许改什么

| 维度 | 现在 | 目标 | 允许的动作 |
|---|---:|---:|---|
| 值类型（dataclass/enum/Protocol） | 577 个 / 14.1K 行 | ≤150 个 / ≤4K 行 | 合并同义值类型；去掉"每个 owner 一套 request/result/snapshot/reason"；enum 归并 |
| 异常类型 | 60 | ≤12（每包 1 个 + 4 个跨包） | 每包一个 `*Error` 携带 code；删除 `*Violation` 家族 |
| 守卫行（`if…: raise`） | 24.4K（15%） | ≤4K（≈6%） | 只保留产品边界校验（外部输入、授权、并发所有权）；内部一致性 assert 删除或降为 `assert` |
| owner 类 | 75 / 68.0K 行 | ≤30 | 一个责任一个 owner；lease/authority/registry/route 合并 |
| codec / snapshot 方法 | 3.8K 行 | ≤1K | 一个 canonical codec；snapshot 只在需要诊断的 3 个 owner 上 |
| 前端 `throw` | 1,073 | ≤150 | 同上；错误进入一个 `LiveVoiceError` 与 UI 文案表 |
| 前端类型声明 | 2,565 行手写 | 由 schema 生成 | 生成物不计入手写行数 |

### 1.2 不允许改什么

- 产品不变量：committed input 才能触发 Agent/Task；历史只记录被确认播放的内容（D-115）；插话只取消 exact
  response；Task 派发要经过授权与项目 scope；隐私零泄露（音频/凭据/URL 不进观测与日志）。
- 三进程拓扑（浏览器 / Gateway / AgentServer）与 E2A 边界不变。
- 一个事实一个 writer；迁移期不双写；旧数据以 importer 一次性导入。
- Native 不在本计划内；但 §3 的合同一旦落地，Native 段必须在其单独 commit 里采用，不得保留第二套。

### 1.3 估算方法

公式列（§2）：`(LOC − 值类型 − 守卫 − codec) × 0.75 + 值类型 × 0.2 + 守卫 × 0.15 + codec × 0.3`；前端模块按
0.6（音频边缘）、0.45（Web/UI）、0（legacy）。它只表示"内部重写 + 合同瘦身"的机械上界。§3 的区间在此之上
再计入 owner 合并与整块退休，每条都写明依据；两者的差就是需要用户授权的语义变更所换来的行数。

## 2. 当前解剖（`e8b8f85f6`，不含 Native）

| # | 模块 | LOC | 类 | 值类型/行 | owner/行 | 异常 | 守卫行 | raise | codec | 公式目标 |
|---:|---|---:|---:|---|---|---:|---:|---:|---:|---:|
| 1 | Browser Audio Edge（TS） | 8,544 | — | 类型声明 639 行 | — | — | throw 260 | — | — | 5,126 |
| 2 | Web/Gateway media transport | 17,386 | 68 | 54 / 1,098 | 7 / 8,335 | 3 | 1,837 | 375 | 18 | 11,325 |
| 3 | Speech provider | 9,908 | 95 | 77 / 783 | 5 / 1,757 | 4 | 2,202 | 444 | 155 | 5,609 |
| 4 | Committed input / product authority | 16,779 | 120 | 90 / 2,009 | 17 / 6,096 | 4 | 3,614 | 690 | 546 | 9,065 |
| 5 | Conversation Runtime | 7,475 | 59 | 45 / 355 | 3 / 5,901 | 7 | 1,758 | 279 | 104 | 4,309 |
| 6 | Agent bridge | 2,964 | 32 | 24 / 497 | 5 / 1,916 | 3 | 693 | 113 | 39 | 1,516 |
| 7 | Task domain/control | 4,650 | 53 | 50 / 2,623 | 1 / 1,354 | 2 | 1,666 | 237 | 448 | 844 |
| 8 | Task Store | 15,190 | 3 | 2 / 25 | 1 / 14,093 | 0 | 3,814 | 496 | 302 | 8,954 |
| 9 | Project executor | 6,289 | 15 | 10 / 241 | 4 / 4,649 | 0 | 1,012 | 187 | 0 | 3,977 |
| 10 | Checkpoint/effect | 2,768 | 25 | 18 / 1,290 | 2 / 36 | 5 | 531 | 112 | 480 | 832 |
| 11 | Task event/progress | 8,130 | 56 | 45 / 522 | 6 / 3,949 | 3 | 1,337 | 209 | 241 | 4,900 |
| 12 | Presentation/history | 2,063 | 18 | 11 / 198 | 4 / 1,518 | 3 | 665 | 120 | 22 | 1,029 |
| 13 | Formal Web/UI（TS） | 16,238 | — | 类型声明 615 行 | — | — | throw 451 | — | — | 7,307 |
| 14 | Composition/config | 19,793 | 79 | 55 / 1,080 | 10 / 16,554 | 9 | 3,307 | 540 | 261 | 12,149 |
| 15 | Observability | 12,309 | 88 | 54 / 1,920 | 7 / 1,517 | 16 | 1,318 | 368 | 140 | 7,322 |
| 16 | Schema/protocol | 4,869 | 47 | 42 / 1,506 | 3 / 343 | 1 | 660 | 123 | 996 | 1,979 |
| 17 | Legacy/compat（TS） | 3,083 | — | — | — | — | throw 17 | — | — | 0 |
| — | 未归桶（3 个小文件） | 156 | — | — | — | — | — | — | — | 116 |
| | **合计** | **158,594** | **758** | **577 / 14,147** | **75 / 68,018** | **60** | **24,416** | **4,294** | **3,752** | **86,361** |

（表中"类"列不含前端；owner 行数按类的整体跨度计，含其方法。）

## 3. 逐模块简化计划

每条格式：现状 → 目标合同 → 删掉/合并什么 → 改变的语义 → 新测试。区间为规划值。

### 3.1 Browser Audio Edge：8,544 → 4,000–5,000

- 现状：`productP1VoiceRoute.ts` 4,186（21 个顶层函数，只导出 1 个，混装 capture/recognition/playout/diagnostics/
  Native activation 解析）、`browserAudioIOAdapter.ts` 2,888（47 个导出）、设备选择 534、ownership 426、AudioWorklet 203。
- 目标合同：`AudioEdge`（capture + playout + device + ownership）一个对象，事件 6 种；playout receipt 一个类型；
  近端插话候选保留。
- 删/合：路由级诊断（约 400 行）移到观测 leaf；`throw` 260 → ≤40，其余失败走一个 `mapAudioFailure`；
  Native activation 解析留在 Native commit。
- 语义变化：浏览器侧不再区分十几种失败原因，只报 `permission/device/context/transport/playout` 五类；
  ownership 冲突从抛错改为返回"未获得"。
- 新测试：jsdom 下的 capture/playout/ownership 三条成功路径 + 设备切换；playout receipt 与 Gateway ACK 一致性。

### 3.2 Web/Gateway media transport：17,386（含 Native 段约 2.3K）→ 5,000–6,500

- 现状：`dedicated_media_registration.py` 7,724（`DedicatedMediaProductRegistry` 一个类 6,135 行）、
  `streaming_synthesis_route.py` 2,449、`dedicated_media_route.py` 1,680、`browser_gateway_media_transport.py` 1,298
  （20 个值类型）、TS 侧 `browserGatewayMediaTransport.ts` 1,516 + `browserDedicatedMediaRoute.ts` 1,413。
- 目标合同：一个 `MediaSession` owner（注册、票据、authority、downlink 分配、ACK 转发），一个 `RouteLifecycle`
  给 streaming STT / streaming TTS / dedicated media 三条 route 共用；`LVM1` 帧 codec 保留（约 600 行）；
  控制对象 20 → 6（attach/ack/detach/speech_start/end_of_turn/playback_stop）。
- 删/合：三条 route 各自的 lifecycle、fallback 投影、诊断 worker；`MediaDetachReason` 26 个值 → 6；
  首帧诊断 owner 并入观测 leaf；TS 镜像随 schema 生成。
- 语义变化：route 的降级原因只报六类；重复 attach 不再是违规而是幂等；ACK 序列失配统一为一次重同步。
- 新测试：三条 route 共用一套 lifecycle 用例（attach→frames→end→ack→detach）、reconnect/backpressure/ACK 各一条、
  合成语音 journey。

### 3.3 Speech provider：9,908 → 4,000–5,000

- 现状：`openai_streaming_speech.py` 2,920（`OpenAIStreamingSpeechProvider` 1,489 + 两个 cleanup/degradation
  owner）、`batch_speech.py` 2,745（`FormalBatchSpeechService` 1,207）、`streaming_speech.py` 2,230
  （`StreamingSpeechConformance` 1,108 + 27 个值类型）、`streaming_speech_route.py` 1,536、`speech_ports.py` 477。
- 目标合同：`SpeechProvider` ABC（recognize/stream_recognize/synthesize/stream_synthesize/capability）+ 注册表，
  一个 `Capability` struct（Hermes `StreamingTTSProvider` 的形态），一个 `Fallback` 枚举（≤8 值）；
  OpenAI 兼容批处理与 OpenAI 流式各一个实现（各 ≤900 行）。
- 删/合：conformance validator 整体（provider 自报能力，route 只信 capability）；`SpeechDegradationReason` 11 +
  `SpeechDegradationFact` + `TransportCleanupSnapshot` → 一个 fallback 记录；两个 cleanup owner → 传输对象自己的
  `aclose()`；`speech_ports.py` 的 18 个值类型 → 5。
- 语义变化：不再对 provider 会话做逐事件 conformance 校验，只校验能力声明与时序两条；降级理由粗粒度；
  TEXT 降级仍保留。
- 新测试：provider 注册与能力探测；批处理/流式各一条成功路径；provider 失败 → TEXT 降级；D-113 admission。

### 3.4 Committed input / product authority：16,779 → 6,500–8,500

- 现状：`p3_authenticated_composition.py` 5,446（`P3AuthenticatedComposition` 3,984 + 两个 resolver 618）、
  `production_task_intent.py` 2,004（19 个值类型）、`unified_committed_input.py` 1,694、`critical_token_safety.py`
  1,397（20 个值类型）、`product_authority.py` 1,253（15 个值类型 + 3 个 owner）、`task_semantics.py` 1,210、
  `p3_confirmation.py` 979、`semantic_continuity.py` 255、`voice_task_bridge.py` 197。四套一次性授权 CAS。
- 目标合同：`AuthorizationOwner`（principal 认证、项目 scope、确认签发/消费、澄清）一个；
  `CommittedInputJournal`（committed digest、控制恢复、semantic pending context、确认记录）一张 SQLite journal；
  `TaskSemantics` 保留（schema 生成器 304 行 → 100）；`Confirmation` 一个值类型。
- 删/合：`p3_confirmation` ledger、`product_authority` 的 CAS、`production_task_intent` 的确认消费、
  `critical_token_safety` 的授权/澄清记录合并进 `AuthorizationOwner`；`P3AuthenticatedComposition` 保留认证与
  项目解析（≤1,200），删除它重复的 Store/Core/executor 构造根；`AuthorityDecisionReason` 19 + `CriticalTokenReason` 22
  → 一个 `AuthorizationOutcome`（≤8 值）。
- 语义变化：确认的 TTL、scope 与一次性消费在四条路径上统一；critical token 的澄清与 P3 确认走同一条流程；
  拒绝原因归并；语义模型的输出 schema 不变。
- 新测试：正负授权各一组（成功路径必须断言成功而不只断言拒绝）；确认一次性消费的并发用例；
  语义路由探针（对话/任务/澄清三类）。

### 3.5 Conversation Runtime：7,475 → 3,000–4,000

- 现状：`agent_conversation_runtime.py` 4,552（一个 3,951 行的 owner + 21 个值类型）、`conversation_runtime_loop.py`
  1,559、`conversation_runtime.py` 686、`interaction_engine.py` 602、`speculative_dialogue.py` 459。
  播放期插话与生成期打断两套 fence（Native 第三套）。
- 目标合同：一个 `ConversationRuntime`（turn/response/generation 状态 + 优先级事件循环 + effect outbox），
  一个 `ResponseFence`（phase = playback | generation），`SpeculativeDialogue` 保留（≤350）。
- 删/合：`AgentConversationRuntime` 与 `ConversationRuntimeLoop` 合一；retained interrupt ledger 并入 fence；
  `interaction_engine` 只留 `InteractionAction` 端口（≤150）；`GenerationInterruptionFenceStatus`、
  `BargeInResult`、`GenerationInterruptionResult`、`ResponseCancelResult` → 一个 `FenceResult`。
- 语义变化：两类打断产生同一种记录，取消语义一致（exact response）；通知 lease 只保留一种；
  Native 的 `fence_response` 后续必须改用同一 fence。
- 新测试：播放期插话、生成期打断、无响应时的打断三条；效果 outbox 的顺序与幂等；speculation 的 attach/replay/discard。

### 3.6 Agent bridge：2,964 → 1,000–1,300

- 现状：`agent_bridge_runtime.py` 1,240 与 `jiuwenswarm_round_harness.py` 1,138 是同一 round 的两层；
  `formal_live_voice.py` 353；tool gate 75。
- 目标合同：一个 `RoundOwner`（预留、生命周期、精确取消、进度投影）；tool hold 是已安装 `AgentRail.before_tool_call`
  上的一个 rail element。
- 删/合：`AgentBridgeRuntime` 整体；两套 reservation/snapshot 值类型 → 一套。
- 语义变化：round 只有一个状态机；取消只有一个入口。
- 新测试：Agent/Tool 正负场景、生成期打断下的 round 取消、speculation 回归。

### 3.7 Task domain/control：4,650 → 1,200–1,500

- 现状：`formal_task_models.py` 2,615（41 个值类型、`__post_init__` 1,381 行）、`persistent_task_core.py` 1,562、
  `executor_capabilities.py` 373。
- 目标合同：`Task`、`Attempt`、`Command`、`Result`、`TaskEvent`、`Cursor` 六个记录 + 六个枚举（≤600 行）；
  admission 策略 ≤300；executor 选择 ≤300。
- 删/合：`ResolvedTaskContext` 233、`TaskAuthorizationGrant` 134、`FormalTaskSpec` 192 等合成 `Task`；
  retry/mutation precondition 五个类型 → 一个 `Precondition`；`PersistentTaskCore` 收缩为对台账的薄 facade。
- 语义变化：Task 的字段校验由 schema 承担，不再在每个记录的 `__post_init__` 里重复；重试前置条件统一。
- 新测试：记录的 canonical 编解码往返；admission 的四种处置。

### 3.8 Task Store：15,190 → 3,500–4,500

- 现状：`SqliteTaskStore` 一个类 14,093 行，守卫 3,814 行，SQL 只有 580 行；v1..v6 迁移与校验；outbox 投递、
  claim 续约、settlement、durability 诊断都在同一个类里。
- 目标合同：按 Hermes core 的形态拆成四张小台账，各自一个文件、一个 writer：`executions`（task/attempt，
  `claimed → running → completed/failed/unknown`，终态不可改写）、`delivery`（outbox：`pending → delivering →
  delivered/failed/unknown`，幂等入队、原子认领、`renew_claim`、死 owner fence 为 unknown、绝不重放不确定投递）、
  `events`（per-task 单调 sequence + consumer cursor 一行）、`facts`（checkpoint 与 external-effect 的 append-only 事实）。
  加一个一次性 importer（旧库 → 新台账，≤400 行）。
- 删/合：v1..v6 迁移；durability 诊断快照；双 reducer/verifier；`settle_unbound_queued_attempt`、
  `_settle_cancel_before_dispatch`、`project_has_unsettled_attempt` 作为台账的三条 invariant 保留（各 ≤40 行）。
- 语义变化：UNKNOWN 成为一等终态；不确定的投递不重放；恢复不再"证明后重试"而是"标记 unknown 等待 owner 决定"；
  旧数据库只读导入。
- 新测试：每张台账的 race/restart/corruption 各一组（从 `7c7aad7b8` 的 `test_persistent_task_core.py` 挑选
  oracle 重写）；importer 往返；单 writer 断言。
- 与 AgentCore 的关系：这四张台账就是 F1–F6 的 Jiuwen 实现；AgentCore 落地后以 adapter 采用，不再第二次重写。

### 3.9 Project executor：6,289 → 2,500–3,200

- 现状：`DirectProjectCodeExecutorAdapter` 3,422、`_DirectProjectAttemptJournal` 1,129（第二个效果 writer）、
  `_AttemptOwnershipLock` 86、`DirectProjectManagedBaselineReader` 134、`ProjectExecutionBinding` 147。
- 目标合同：`ProjectExecutor`（派发 Code Agent、流观察、结果结算）≤1,500；`WorktreeFacts`（Git/worktree/patch/
  tree 指纹）≤400；所有权与结算走 `executions` 台账，不再自持 journal。
- 删/合：attempt journal 的效果部分（归 `facts`）；ownership lock（归台账 lease）；legacy 过渡 profile。
- 语义变化：效果 truth 只有一份；执行器崩溃后的判定由台账 UNKNOWN + baseline reader 完成。
- 新测试：D0/D2 各一条成功路径、崩溃窗口、补偿。

### 3.10 Checkpoint/effect：2,768 → 800–1,000

- 现状：六个 `durability_*` 文件，18 个值类型 1,290 行，复制同一组 helper；prefix verifier。
- 目标合同：一个 `Fact` codec（kind = checkpoint | effect，digest/size/codec 元数据）+ 一个 reconcile 决策函数。
- 删/合：prefix verifier（由 `facts` 台账的 append-only 保证）；recovery facts 并入 `Attempt`。
- 语义变化：checkpoint 不再单独"发布"，它是一种 fact。
- 新测试：codec 往返、reconcile 决策表。

### 3.11 Task event/progress：8,130 → 2,500–3,200

- 现状：`task_progress_return.py` 2,275、`progress_notification_arbiter.py` 2,228（一个 1,772 行的 owner，
  17 个值类型）、`task_event_subscription.py` 1,559、`product_p3_text_adapter.py` 1,206、前端 `productTextProgress.ts` 870。
- 目标合同：`TaskEventSubscription`（读 `events` 台账 + cursor）≤600；`ProgressPolicy`（能不能出声、给谁、何时）
  ≤1,200，合并仲裁与进度返回；文本适配 ≤500；前端进度投影 ≤300。
- 删/合：两套 queue/ACK/lease 机制之一；live/authority 两种订阅模式 → 一种（durable cursor）；
  `TaskProgressReturnReason` 23 + `NotificationDisposition` 7 + `SpeechDisposition` 3 → 一个 `ProgressDecision`。
- 语义变化：进度通知只有一种投递路径；replay 由 cursor 决定，不再有"authority replay"模式。
- 新测试：通知/ACK/replay 三条；前台忙时的静默与恢复。

### 3.12 Presentation/history：2,063 → 1,500–1,800

- 现状：`presentation_ledger.py` 1,272（两个 owner）、`p2_response_generation_store.py` 436、`formal_history_writer.py` 266。
- 目标合同：`PresentationLedger` 一个 owner（含 Task 呈现消费）；history writer 保留。
- 删/合：`TaskPresentationConsumptionOwner` 并入 ledger；11 个值类型 → 5。
- 语义变化：无（D-115 不变）。
- 新测试：ACK 后才写历史；surface seal；Task 呈现的一次性消费。

### 3.13 Formal Web/UI：16,238 → 5,500–7,000

- 现状：`LiveVoiceIntegratedRoutePanel.tsx` 9,762（主组件 7,304 行，29 个顶层函数）、`productWebActivation.ts` 2,223
  （32 个函数）、`productP2ActivationJournal.ts` 1,314、`formalTaskIntentRoute.ts` 995、`formalTaskControlLeaf.ts` 941、
  `formalP3TaskExperience.ts` 952、其余约 1,000。
- 目标合同：`useLiveVoiceSession`（P1/P2/P3 三个 owner hook，各 ≤500）、`notificationArbitration.ts`（纯函数 ≤350）、
  一个 `TaskUi` owner（≤900）、一个 `DurableOperationClient`（≤800）、一本 `ActivationJournal`（≤500）、
  面板视图 ≤1,200。
- 删/合：三个 Task UI owner → 一个；三本同模式 journal → 一本；Panel 的 recovery/diagnostics 段移到 owner hook；
  `throw` 451 → ≤60。
- 语义变化：UI 错误进入统一文案表；Task 面板只有一个状态机。
- 新测试：三个 owner hook 的 mounted 测试；仲裁纯函数表驱动；feature-on/off。

### 3.14 Composition/config：19,793 → 2,500–3,200

- 现状：`product_composition_registry.py` 15,992（`AgentServerProductCompositionRegistry` 14,982 行；P1/P2/P3
  handler 工厂 + 每个 handler 重复 scope/session/principal 校验 + 语义 dispatch 约 600 行 + Native handler 约 1,500）、
  `product_p2_interaction_adapter.py` 2,117（`P2ActivationLease` 982）、`live_voice_configuration_declaration.py` 1,003、
  `product_composition_root.py` 459。
- 目标合同：`Registry`（注册 + 生命周期）≤1,200；handler 工厂搬回各 owner；语义 dispatch 搬到 §3.4；
  `CompositionRoot` ≤300（吸收 P2 activation lease）；配置声明 ≤300。
- 删/合：逐 handler 校验（授权在 `AuthorizationOwner` 做一次）；六种 lease 类 → 一种；
  `ProductCompositionSettings` 之外的配置值类型。
- 语义变化：请求进入时校验一次；feature-off 时 registry 不分配任何对象（不变）。
- 新测试：注册/关闭生命周期；feature-off；multi-Task；refresh/reconnect。

### 3.15 Observability：12,309 → 2,500–3,200（含一个产品决定）

- 现状：OTel 产品链（`product_observability_runtime.py` 1,413、adapter 847、correlation 876、codec 641、exporter 605）
  从未在任何部署启用；`observability.py` 1,821；`latency_measurement.py` 1,972；被动 profiling 与音频诊断 JSONL；
  前端 `liveVoiceObservability.ts` 等约 2,500。
- 目标合同：`Observation` 记录（≤700，隐私投影一个函数）、一个 sink（JSONL/回调，≤400）、一个 `@profiled`
  与音频诊断共用的 `DiagnosticSink`（≤500）、前端 ≤500；L0 测量整体移到 `scripts/`。
- 删/合：OTel 产品链整体（决定 §7.2）；三通道 exporter/投影 → 一个。
- 语义变化：不再产出 OTel backend 记录与 correlation receipt；隐私零泄露断言保留并覆盖唯一 sink。
- 新测试：隐私零泄露（合成秘密 canary）；sink 顺序与背压；profiling 报告脚本仍可解析。

### 3.16 Schema/protocol：4,869 → 2,000–2,500

- 现状：`live_voice_contract_v2.py` 3,796（42 个值类型 + `IdentityRegistry` 195、`TurnCommitLedger` 84、
  `ResponseFence` 64、`EventSequenceTracker` 508、codec 996）、`speech_rpc.py` 142、TS 副本已删。
- 目标合同：`Command/Query/Result/Event` 四个 envelope + `ScopeRef/ContextRef/IdentityRef/OriginRef`（≤1,000）；
  `ErrorCode` 15 → ≤20 但全仓只此一处；canonical JSON codec ≤300；TS 类型由生成器产出。
- 删/合：schema 内的 registry/ledger/fence/tracker（它们是 runtime owner 的第二副本）；`CapabilityDescriptor` 121 →
  归 §3.3 的 `Capability`；`WorkProgressEventV2` 156 → `TaskEvent`。
- 语义变化：事件序列的校验由 `events` 台账保证，schema 不再校验状态机；envelope 字段减少。
- 新测试：跨语言字节等价；生成器幂等。

### 3.17 Legacy/compat：3,083 → 0

`useLiveVoiceDemo`、`liveVoiceCore`、`liveVoiceStreamingSpeech`、`liveVoiceTurnLifecycle`、`integratedP1Route`、
两个 browserSpeech adapter、`liveVoiceMessageGate`、`LiveVoiceDemoBar` 的 legacy 部分与 `FEATURE_LIVE_VOICE_DEMO`
整体退休（决定 §7.3）。语义变化：普通 `vite build` 不再渲染 legacy bar。

### 3.18 汇总

| # | 模块 | 现在 | 区间 | 关键动作 |
|---:|---|---:|---:|---|
| 1 | Browser Audio Edge | 8,544 | 4,000–5,000 | 一个 AudioEdge，五类失败 |
| 2 | Media transport | 17,386 | 5,000–6,500 | MediaSession + 一个 RouteLifecycle |
| 3 | Speech provider | 9,908 | 4,000–5,000 | Provider ABC + Capability，删 conformance |
| 4 | Committed input / authority | 16,779 | 6,500–8,500 | 一个 AuthorizationOwner + 一张 journal |
| 5 | Conversation Runtime | 7,475 | 3,000–4,000 | 一个 runtime + 一个 fence |
| 6 | Agent bridge | 2,964 | 1,000–1,300 | 一个 RoundOwner |
| 7 | Task domain | 4,650 | 1,200–1,500 | 六记录六枚举 |
| 8 | Task Store | 15,190 | 3,500–4,500 | 四张小台账 + importer |
| 9 | Project executor | 6,289 | 2,500–3,200 | 效果 truth 归台账 |
| 10 | Checkpoint/effect | 2,768 | 800–1,000 | 一个 Fact codec |
| 11 | Task event/progress | 8,130 | 2,500–3,200 | 一个订阅 + 一个 ProgressPolicy |
| 12 | Presentation/history | 2,063 | 1,500–1,800 | 一个 ledger |
| 13 | Formal Web/UI | 16,238 | 5,500–7,000 | 三个 owner hook + 一个 TaskUi + 一本 journal |
| 14 | Composition/config | 19,793 | 2,500–3,200 | registry 只注册 |
| 15 | Observability | 12,309 | 2,500–3,200 | 退休 OTel 链，一个 sink |
| 16 | Schema/protocol | 4,869 | 2,000–2,500 | 四 envelope + 生成器 |
| 17 | Legacy | 3,083 | 0 | 退休 |
| — | 未归桶 | 156 | 100–200 | — |
| | **合计** | **158,594** | **48,100–61,600** | 承诺带 60–65K |

## 4. 语义变更目录（授权对象）

| 编号 | 变更 | 影响面 | 谁能看到 |
|---|---|---|---|
| SC-1 | 拒绝语义归并：约 200 个 reason 值 → ≤20 个 `ErrorCode`；内部一致性错误不再是类型化违规 | 全部 | 前端文案、日志、评审脚本 |
| SC-2 | 一个授权 owner：P2/P3 确认、critical-token 澄清、production intent 确认统一 TTL/scope/一次性消费 | 4、14 | 确认对话的时序与提示 |
| SC-3 | 一个 response fence：播放期插话与生成期打断同一记录、同一取消入口 | 5、6、12 | 打断后的呈现与历史 |
| SC-4 | Task 台账化：UNKNOWN 一等终态、不重放不确定投递、旧库一次性导入、无 authority replay 模式 | 7–11 | 崩溃/重启后的任务状态文案 |
| SC-5 | checkpoint 成为 fact 的一种，不再单独发布 | 10 | 无用户可见影响 |
| SC-6 | 观测：退休 OTel 产品链，三通道 → 一个 sink；L0 测量出生产树 | 15 | 运行手册、profiling 报告数据源 |
| SC-7 | schema 收缩：envelope 字段减少、状态机校验移出 schema、TS 由生成 | 16、2、13 | 协议版本号递增 |
| SC-8 | provider 合同：能力自报替代 conformance 校验，降级理由粗粒度 | 3、2 | 降级提示文案 |
| SC-9 | 前端：Panel 拆 owner hook，一个 Task UI，一本 journal，错误文案表 | 13、1 | UI 结构不变，错误提示变 |
| SC-10 | legacy 链与 `FEATURE_LIVE_VOICE_DEMO` 退休 | 17 | 普通 build 无 legacy bar |

## 5. 测试与 oracle

现状：本分支已删除 `tests/unit_tests/live_voice`（原 98 个文件约 125.6K 行）、前端 live-voice 测试与
`scripts/live_voice/semantic_audio_*`，只剩 `start_hands_free_demo`、`start_formal_web_validation`、L0 与
profiling 脚本。因此：

1. **oracle 回收**（S0）：从 `7c7aad7b8` 只读地挑出要重写的 oracle 清单，不恢复文件：Task 台账的 race/restart/
   corruption 用例（`test_persistent_task_core.py`、`test_p3_4_durability_*`、`test_project_code_executor.py`）、
   生成期打断与插话用例、隐私零泄露断言、D-113 admission、reconnect/backpressure/ACK、合成语音 journey 脚本。
2. **新测试预算**：目标生产 60–65K，按 Hermes 的测试/生产比 1.24 约 75–80K；按 root `TESTING.md` 分层：
   每包合同测试（成功路径必须断言成功，不只断言拒绝）、注释里每条不变量配一个能杀死反向变异体的用例、
   台账的并发/重启用例、隐私 canary、前端 mounted 测试、合成语音 journey、物理 demo journey。
3. **替身规则**：SDK/Provider 替身照源码写，不按假设写；夹具只观察不替换生产方法。
4. **验收**：每包以新测试 + journey 通过验收，不以"旧测试通过"验收（旧测试已不存在）。

## 6. 实施包

全部为语义变更（Tier 3），每包独立提交、独立 revert；旧台账在 S2 后只读保留一个包周期。

| 包 | capability | 风险 | 依赖 | 范围 | 排除 | 验收 | 回滚 |
|---|---|---|---|---|---|---|---|
| **S0 授权与基线** | 计划/文档 | 低 | §7 决定 | 记录 Decision；重基线到 `d8ee9e6d3`；oracle 回收清单；错误码表；测试分层 | 源码改动 | 清单覆盖 18 模块与 SC-1..10 | 单提交 revert |
| **S1 schema 与 Task 记录**（§3.16、§3.7） | 协议 | 中 | S0 | 四 envelope、六记录六枚举、canonical codec、TS 生成器 | 运行时切换 | 跨语言等价、生成器幂等 | 生成器不接入即无影响 |
| **S2 Task 台账**（§3.8、§3.10、§3.11 订阅、§3.9 所有权） | Task truth | 高 | S1 | 四张台账、importer、单 writer cutover、executor 改用台账 lease | 项目 seam 语义 | race/restart/corruption、importer 往返、UNKNOWN 路径 | 旧 Store 只读 + importer 反向演练 |
| **S3 授权 owner 与组合根**（§3.4、§3.14） | 授权/组合 | 高 | S1 | AuthorizationOwner、CommittedInputJournal、registry 只注册、语义 dispatch 独立 | Native handler | 正负授权、一次性消费并发、feature-off、multi-Task | 独立提交 revert |
| **S4 runtime、fence、round、呈现**（§3.5、§3.6、§3.12） | 前台对话 | 高 | S1 | 一个 runtime、一个 fence、一个 RoundOwner、ledger 合一 | Native fence | 三类打断、effect outbox、ACK 后写历史 | 独立提交 revert |
| **S5 媒体与 provider**（§3.2、§3.3、§3.1 后端段） | 媒体/语音 | 高 | S1、S4 | MediaSession、RouteLifecycle、Provider ABC、LVM1 codec | Native 段 | route lifecycle 三条、provider 降级、合成语音 journey | 独立提交 revert |
| **S6 前端**（§3.1、§3.13、§3.11 前端、§3.17） | Web/UI | 中 | S1、S5 | AudioEdge、owner hook、TaskUi、journal、legacy 退休 | Native activation 段 | mounted 测试、仲裁表、feature-on/off、物理 journey | 独立提交 revert |
| **S7 观测**（§3.15） | 诊断 | 中 | S0 决定 §7.2 | 退休 OTel 链、一个 sink、L0 出树 | — | 隐私 canary、profiling 报告可解析 | 独立提交 revert |
| **S8 验收与计量** | 全部 | 中 | 全部 | 物理 journey、独立评审、`anatomy_modules.py` 对照 §1.1 预算、多仓口径报告 | — | 预算全部达标；journey PASS | — |

顺序建议：S0 → S1 → S2 与 S3 并行 → S4 → S5 → S6 → S7 可随时 → S8。第一份实测比例来自 S1+S2，用它修正 §3.18。

## 7. 需要用户决定

1. **授权语义变更**：以 Decision 记录 SC-1..SC-10 与 §1.1 预算；否则本计划不能开工。
2. **退休 OTel 产品观测链**：`JIUWENSWARM_LIVE_VOICE_PRODUCT_OBSERVABILITY_ENABLED` 从未在部署、脚本、runbook 中设置。
3. **退休 legacy 链与 `FEATURE_LIVE_VOICE_DEMO`**。
4. **Task 家族在仓库内重写为四张小台账**，不等 AgentCore F1–F6；AgentCore 落地后以 adapter 采用。
5. **错误码归并策略**：约 200 个 reason 值归并为 ≤20 个 `ErrorCode`，UI 文案表由谁维护。

## 8. 计量与复现

- 每包结束运行 `module_buckets.py --rev HEAD` 与 `anatomy_modules.py --rev HEAD`，把 §2 表和 §1.1 预算重算一次；
  值类型、异常、守卫、owner、`throw` 五项预算任一超标即不通过 S8。
- 行数只记手写源码；生成物、迁移 importer 的一次性代码、测试分别记账。
- Native 段在其单独 commit 采用本计划合同后，再并入同一张表。

## 9. 风险

- 没有回归网：旧测试已删除，重写期间只有 journey 与新测试；S0 的 oracle 回收清单是唯一缓冲。
- 语义变更外溢：SC-1 的错误码归并会改变前端文案与评审脚本；S0 先出文案表。
- 第一份实测：§3.18 的区间全部是规划值；S1+S2 落地后若比例明显偏离，先修正区间再继续。
- 分支落后：19 个提交主要是 Native 修复，重基线时 §3.2/§3.14 的 Native 段可能变大，不影响本计划口径。
