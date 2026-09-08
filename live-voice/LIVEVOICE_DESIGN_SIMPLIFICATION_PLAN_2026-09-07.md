# LiveVoice 设计简化瘦身计划（语义变更路径）— v2，2026-09-07

> 标准：按"加上设计简化（减值类型、守卫、owner，属语义变更），目标 60,000–65,000 行；只有重写合同才到得了，
> 需要用户授权并重写测试"执行。第一部分是计划，第二部分是给执行者（任何模型或人）的逐包执行卡，第三部分是
> 自动生成的清单。执行卡的每一步都写明输入文件、目标文件、symbol 处置、验证命令与完成判据；执行者不需要
> 再做判断，只需要按卡片操作并在每步后运行验证。
>
> - 基线：`hx/0907_livevoice_slimming@48e6ec496`（= `agtai/hx/0812_live_voice_w3@d8ee9e6d3` + 三个提交：
>   退休 13 个零 caller 文件及其测试、导入分析文档与脚本）。全部 LiveVoice 测试仍在分支上（后端
>   `tests/unit_tests/live_voice` 等约 125K 行，前端 `tests/*.test.mjs` 与 `package.json` 的 `test:live-voice-*`），
>   按包退役，不整体删除。
> - 口径：physical LOC（空行、注释、docstring 计入）；Native（OpenAI Realtime）19 个文件 13,231 行按既有决定排除，
>   但第二部分标出 Native 段必须后续采用的合同。
> - 复现：`scripts/live_voice/slimming/module_buckets.py --rev HEAD`（18 模块行数）、
>   `anatomy_modules.py --rev HEAD`（值类型/守卫/owner/codec 解剖）、`symbol_inventory.py --rev HEAD --out …`
>   （逐文件 symbol 与 caller 数，附录 A）、`method_map.py --rev HEAD --out …`（巨型类方法图，附录 B）。

# 第一部分 计划

## 0. 结论先行

1. 本分支的 LiveVoice 专属生产代码 **170,706 行**（不含 Native）。零 caller 的整文件已退休；文件内的零 caller
   symbol 静态只剩 29 个 1,665 行（附录 A 的"两列都为 0"项），其余每一行都有调用方。
2. 行数来自合同密度而非重复：664 个值类型 15.6K 行、85 个 owner 类 70.8K 行、67 个异常类型、`if…: raise`
   守卫 25.9K 行（15%）、`__post_init__` 5.0K、codec/snapshot 3.8K；前端每 33 行一个 `throw`。官方 Hermes voice
   同类代码 23 个类、2 个值类型、守卫 2%。
3. 保留合同只重写内部，机械上界约 **93.5K**（§2 公式列；探针实测单模块 −17.6%）。要到 60–65K 必须改合同：
   值类型 664 → ≤150，异常类型 67 → ≤12，守卫 25.9K → ≤4K，owner 85 → ≤30，前端 `throw` 1,238 → ≤150。
4. 逐模块重写后的规划区间 **48.1K–61.6K**，承诺带 **60–65K**（含约 10% 未知）。每个模块（§3）与每个包
   （第二部分）都写明合并的 owner、删除的值类型与守卫、改变的语义、验收它的新测试。
5. 旧测试是重写期间唯一的回归网：每个包先给新合同写新测试，切换后在同一个包里删除该模块的旧测试；
   旧套件失败列表就是"这次改了哪些语义"的清单，逐条对照 §4 确认是预期变化还是缺陷。
6. §7 的五个决定已记录：授权语义变更与 Task 家族在仓库内重写由 D-121，观测退休、legacy 与标准构建由 D-122，
   错误模型与文案由 D-123；退休前检查见 D-122。
7. 本计划原为路线 A（分包重构到 60–65K）。**2026-09-08 用户选择路线 B（D-121）**：按[目标架构](LIVEVOICE_TARGET_ARCHITECTURE_2026-09-07.md)
   重写到 26–29K。本文的 S0、S1、S2、S5、S7 卡在路线 B 中原样使用（目标架构 §10 的 B0/B1/B4/B5/B7），S3、S4、S6
   由目标架构 §4–§5 与 B3/B6 替代；§4 的 SC-1..10 仍是语义变更的授权范围。

## 1. 标准与预算

### 1.1 允许改什么

| 维度 | 现在（不含 Native） | 目标 | 允许的动作 |
|---|---:|---:|---|
| 值类型（dataclass/enum/Protocol） | 664 个 / 15,605 行 | ≤150 个 / ≤4K 行 | 合并同义值类型；去掉"每个 owner 一套 request/result/snapshot/reason"；enum 归并 |
| 异常类型 | 67 | ≤12（每包 1 个 + 4 个跨包） | 每包一个 `*Error` 携带 code；删除 `*Violation` 家族 |
| 守卫行（`if…: raise`） | 25,944（15%） | ≤4K（≈6%） | 只保留产品边界校验（外部输入、授权、并发所有权）；内部一致性 assert 删除或降为 `assert` |
| owner 类 | 85 / 70,831 行 | ≤30 | 一个责任一个 owner；lease/authority/registry/route 合并 |
| codec / snapshot 方法 | 3,830 行 | ≤1K | 一个 canonical codec；snapshot 只在需要诊断的 3 个 owner 上 |
| 前端 `throw` | 1,238 | ≤150 | 错误进入一个 `LiveVoiceError` 与 UI 文案表 |
| 前端类型声明 | 2,846 行手写 | 由 schema 生成 | 生成物不计入手写行数 |

### 1.2 不允许改什么

- 产品不变量：committed input 才能触发 Agent/Task；历史只记录被确认播放的内容（D-115）；插话只取消 exact
  response；Task 派发要经过授权与项目 scope；隐私零泄露（音频/凭据/URL 不进观测与日志）。
- 三进程拓扑（浏览器 / Gateway / AgentServer）与 E2A 边界不变。
- 一个事实一个 writer；迁移期不双写；旧数据以 importer 一次性导入。
- Native 不在本计划内；但第二部分的合同一旦落地，Native 段必须在其单独 commit 里采用，不得保留第二套。
- 不推送远端；每包一个本地提交。

### 1.3 估算方法

公式列（§2）：`(LOC − 值类型 − 守卫 − codec) × 0.75 + 值类型 × 0.2 + 守卫 × 0.15 + codec × 0.3`；前端模块按
0.6（音频边缘）、0.45（Web/UI）、0（legacy）。它只表示"内部重写 + 合同瘦身"的机械上界。§3 的区间在此之上
再计入 owner 合并与整块退休；两者的差就是需要用户授权的语义变更所换来的行数。

## 2. 当前解剖（`48e6ec496`，不含 Native）

| # | 模块 | LOC | 类 | 值类型/行 | owner/行 | 异常 | 守卫行 | raise | codec | 公式目标 |
|---:|---|---:|---:|---|---|---:|---:|---:|---:|---:|
| 1 | Browser Audio Edge（TS） | 9,023 | — | 类型声明 672 行 | — | — | throw 276 | — | — | 5,414 |
| 2 | Web/Gateway media transport | 19,239 | 76 | 60 / 1,293 | 8 / 9,052 | 4 | 1,968 | 423 | 18 | 12,529 |
| 3 | Speech provider | 9,909 | 95 | 77 / 783 | 5 / 1,757 | 4 | 2,202 | 444 | 155 | 5,610 |
| 4 | Committed input/product authority | 16,902 | 121 | 90 / 2,009 | 18 / 6,129 | 4 | 3,625 | 694 | 532 | 9,157 |
| 5 | Conversation Runtime | 8,395 | 68 | 53 / 424 | 3 / 6,392 | 7 | 2,055 | 327 | 121 | 4,776 |
| 6 | Agent bridge | 3,078 | 36 | 26 / 515 | 6 / 1,972 | 4 | 715 | 116 | 39 | 1,579 |
| 7 | Task domain/control | 5,342 | 64 | 60 / 2,691 | 2 / 1,854 | 2 | 1,807 | 257 | 460 | 1,235 |
| 8 | Task Store | 15,190 | 3 | 2 / 25 | 1 / 14,093 | 0 | 3,814 | 496 | 302 | 8,954 |
| 9 | Project executor | 6,881 | 16 | 10 / 241 | 5 / 5,157 | 0 | 1,150 | 209 | 0 | 4,338 |
| 10 | Checkpoint/effect | 2,953 | 27 | 20 / 1,307 | 2 / 36 | 5 | 734 | 158 | 480 | 840 |
| 11 | Task event/progress | 8,164 | 57 | 46 / 528 | 6 / 3,949 | 3 | 1,337 | 209 | 244 | 4,921 |
| 12 | Presentation/history | 2,063 | 18 | 11 / 198 | 4 / 1,518 | 3 | 665 | 120 | 22 | 1,029 |
| 13 | Formal Web/UI（TS） | 16,517 | — | 类型声明 621 行 | — | — | throw 464 | — | — | 7,433 |
| 14 | Composition/config | 20,076 | 81 | 57 / 1,134 | 10 / 16,631 | 9 | 3,363 | 552 | 261 | 12,298 |
| 15 | Observability | 16,800 | 152 | 109 / 2,947 | 10 / 1,848 | 21 | 1,810 | 474 | 200 | 9,803 |
| 16 | Schema/protocol | 6,958 | 50 | 43 / 1,510 | 5 / 443 | 1 | 699 | 132 | 996 | 3,520 |
| 17 | Legacy/compat（TS） | 3,096 | — | 类型声明 342 行 | — | — | throw 17 | — | — | 0 |
| — | 未归桶（2 个 Native 相关小文件） | 120 | 0 | 0 / 0 | 0 / 0 | 0 | 0 | 0 | 0 | 90 |
| | **合计** | **170,706** | **864** | **664 / 15,605** | **85 / 70,831** | **67** | **25,944** | **4,611** | **3,830** | **93,526** |

（"类"列不含前端；owner 行数按类的整体跨度计，含其方法。数值类型的守卫行占比 15%，是 Hermes voice 的 7 倍。）

## 3. 逐模块简化计划

每条格式：现状 → 目标合同 → 删掉/合并什么 → 改变的语义 → 新测试。区间为规划值；文件级步骤在第二部分对应的执行卡。

### 3.1 Browser Audio Edge：9,023 → 4,000–5,000（执行卡 S6）

- 现状：`productP1VoiceRoute.ts` 4,408（22 个导出，只有 1 个被别的生产文件用；混装 capture/recognition/playout/
  diagnostics/Native activation 解析）、`browserAudioIOAdapter.ts` 3,088（53 个导出，其中 41 个 `*Like` 环境类型与
  事件类型只被本文件用）、`browserAudioDeviceSelection.ts` 534、`browserLiveVoiceOwnership.ts` 426、`audioPort.ts` 364、
  `liveVoiceCaptureProcessor.js` 203。
- 目标合同：`AudioEdge`（capture + playout + device + ownership）一个对象，事件 6 种；playout receipt 一个类型；
  近端插话候选保留。
- 删/合：路由级诊断（约 400 行）移到观测 leaf；`throw` 276 → ≤40，其余失败走一个 `mapAudioFailure`；
  Native activation 解析留在 Native commit；`*Like` 环境类型收成一个 `BrowserAudioEnvironment`。
- 语义变化：浏览器侧只报 `permission/device/context/transport/playout` 五类失败；ownership 冲突从抛错改为返回"未获得"。
- 新测试：jsdom 下 capture/playout/ownership 三条成功路径 + 设备切换；playout receipt 与 Gateway ACK 一致性。

### 3.2 Web/Gateway media transport：19,239（含 Native 段约 2.5K）→ 5,000–6,500（执行卡 S5）

- 现状：`dedicated_media_registration.py` 8,427（`DedicatedMediaProductRegistry` 一个类 6,726 行、55 个公开方法，
  其中只有 9 个被别的生产文件调用）、`streaming_synthesis_route.py` 2,449、`dedicated_media_route.py` 1,869、
  `browser_gateway_media_transport.py` 1,437（24 个值类型）、`task_notification_preparation.py` 327、
  `product_streaming_synthesis.py` 212、TS 侧 `browserGatewayMediaTransport.ts` 1,642 + `browserDedicatedMediaRoute.ts`
  1,442 + `gatewayBatchSpeechClient.ts` 1,431。
- 目标合同：一个 `MediaSession` owner（注册、票据、authority、downlink 分配、ACK 转发、通知准备），一个
  `RouteLifecycle` 给 streaming STT / streaming TTS / dedicated media 共用；`LVM1` 帧 codec 保留（约 600 行）；
  控制对象 24 → 6（attach/ack/detach/speech_start/end_of_turn/playback_stop）。
- 删/合：三条 route 各自的 lifecycle、fallback 投影、诊断 worker；`MediaDetachReason` 27 个值 → 6；
  首帧诊断 owner 并入观测 leaf；TS 镜像随 schema 生成。
- 语义变化：route 的降级原因只报六类；重复 attach 幂等；ACK 序列失配统一为一次重同步。
- 新测试：三条 route 共用一套 lifecycle 用例（attach→frames→end→ack→detach）、reconnect/backpressure/ACK 各一条、
  合成语音 journey。

### 3.3 Speech provider：9,909 → 4,000–5,000（执行卡 S5）

- 现状：`openai_streaming_speech.py` 2,921（`OpenAIStreamingSpeechProvider` 1,489 + 两个 cleanup/degradation owner）、
  `batch_speech.py` 2,745（`FormalBatchSpeechService` 1,207，49 个模块常量里 40 个无外部 caller）、
  `streaming_speech.py` 2,230（`StreamingSpeechConformance` 1,108，只被 provider 自己调用；27 个值类型）、
  `streaming_speech_route.py` 1,536、`speech_ports.py` 477。
- 目标合同：`SpeechProvider` ABC（recognize/stream_recognize/synthesize/stream_synthesize/capability）+ 注册表，
  一个 `Capability` struct，一个 `Fallback` 枚举（≤8 值）；OpenAI 兼容批处理与 OpenAI 流式各一个实现（≤900 行）。
- 删/合：conformance validator 整体（provider 自报能力，route 只信 capability）；`SpeechDegradationReason` 11 +
  `SpeechDegradationFact` + `TransportCleanupSnapshot` → 一个 fallback 记录；两个 cleanup owner → 传输对象自己的
  `aclose()`；`speech_ports.py` 18 个值类型 → 5。
- 语义变化：不再对 provider 会话做逐事件 conformance 校验，只校验能力声明与时序；降级理由粗粒度；TEXT 降级保留。
- 新测试：provider 注册与能力探测；批处理/流式各一条成功路径；provider 失败 → TEXT 降级；D-113 admission。

### 3.4 Committed input / product authority：16,902 → 6,500–8,500（执行卡 S3）

- 现状：`p3_authenticated_composition.py` 5,435（`P3AuthenticatedComposition` 3,982 行、38 个公开方法，18 个被
  registry 调用；两个 resolver 609 行只被本文件用）、`production_task_intent.py` 2,004（19 个值类型）、
  `unified_committed_input.py` 1,694（19 个公开方法只有 2 个被外部调用）、`critical_token_safety.py` 1,397、
  `product_authority.py` 1,302、`task_semantics.py` 1,210、`p3_confirmation.py` 979、`semantic_continuity.py` 255、
  `p3_model_resolution.py` 222、`voice_task_bridge.py` 197、`production_task_classifier.py` 162。四套一次性授权 CAS。
- 目标合同：`AuthorizationOwner`（principal 认证、项目 scope、确认签发/消费、澄清）一个；`CommittedInputJournal`
  一张 SQLite journal（committed digest、控制恢复、semantic pending context、确认记录）；`TaskSemantics` 保留
  （schema 生成器 304 行 → 100）；`Confirmation` 一个值类型。
- 删/合：`p3_confirmation` ledger、`product_authority` 的 CAS、`production_task_intent` 的确认消费、
  `critical_token_safety` 的授权/澄清记录合并进 `AuthorizationOwner`；`P3AuthenticatedComposition` 保留认证与项目
  解析（≤1,200），删除它重复的 Store/Core/executor 构造根；`AuthorityDecisionReason` 19 + `CriticalTokenReason` 22 →
  一个 `AuthorizationOutcome`（≤8 值）。
- 语义变化：确认的 TTL、scope 与一次性消费在四条路径上统一；critical token 的澄清与 P3 确认走同一条流程；拒绝原因
  归并；语义模型的输出 schema 不变。
- 新测试：正负授权各一组（成功路径必须断言成功）；确认一次性消费的并发用例；语义路由探针（对话/任务/澄清）。

### 3.5 Conversation Runtime：8,395 → 3,000–4,000（执行卡 S4）

- 现状：`agent_conversation_runtime.py` 5,089（一个 4,442 行的 owner，38 个公开方法，19 个被外部调用）、
  `conversation_runtime_loop.py` 1,559（35 个公开方法，20 个被外部调用）、`conversation_runtime.py` 686、
  `interaction_engine.py` 602（`ScriptedCascadeInteractionEngine` 250 行零 caller）、`speculative_dialogue.py` 459。
  播放期插话与生成期打断两套 fence（Native 第三套）。
- 目标合同：一个 `ConversationRuntime`（turn/response/generation 状态 + 优先级事件循环 + effect outbox），
  一个 `ResponseFence`（phase = playback | generation），`SpeculativeDialogue` 保留（≤350）。
- 删/合：`AgentConversationRuntime` 与 `ConversationRuntimeLoop` 合一；retained interrupt ledger 并入 fence；
  `interaction_engine` 只留 `InteractionEnginePort`/`InteractionAction`（≤150）；`GenerationInterruptionFenceStatus`、
  `BargeInResult`、`GenerationInterruptionResult`、`ResponseCancelResult` → 一个 `FenceResult`。
- 语义变化：两类打断产生同一种记录，取消语义一致（exact response）；通知 lease 只保留一种；Native 的
  `fence_response` 后续必须改用同一 fence。
- 新测试：播放期插话、生成期打断、无响应时的打断三条；效果 outbox 的顺序与幂等；speculation 的 attach/replay/discard。

### 3.6 Agent bridge：3,078 → 1,000–1,300（执行卡 S4）

- 现状：`agent_bridge_runtime.py` 1,240 与 `jiuwenswarm_round_harness.py` 1,151 是同一 round 的两层（都只被
  `agent_conversation_runtime` 调用）；`formal_live_voice.py` 401；`jiuwenswarm_agent_adapter.py` 106；`agent_bridge.py`
  105（`AgentBridgePort` 零 caller）；`formal_tool_gate.py` 75。
- 目标合同：一个 `RoundOwner`（预留、生命周期、精确取消、进度投影）；tool hold 是已安装 `AgentRail.before_tool_call`
  上的一个 rail element。
- 删/合：`AgentBridgeRuntime` 整体（保留 `reserve/commit/abort/rollback/next_delivery` 的语义到 `RoundOwner`）；
  两套 reservation/snapshot 值类型 → 一套。
- 语义变化：round 只有一个状态机；取消只有一个入口。
- 新测试：Agent/Tool 正负场景、生成期打断下的 round 取消、speculation 回归。

### 3.7 Task domain/control：5,342 → 1,200–1,500（执行卡 S1、S2）

- 现状：`formal_task_models.py` 2,628（41 个值类型、`__post_init__` 1,381 行）、`persistent_task_core.py` 1,627、
  `task_core.py` 714（`TaskCore` 500 行零 caller；`TaskState`/`AttemptState` 与 `FormalTaskState`/`FormalAttemptState`
  重复）、`executor_capabilities.py` 373。
- 目标合同：`Task`、`Attempt`、`Command`、`Result`、`TaskEvent`、`Cursor` 六个记录 + 六个枚举（≤600 行）；admission
  策略 ≤300；executor 选择 ≤300。
- 删/合：`ResolvedTaskContext` 233、`TaskAuthorizationGrant` 134、`FormalTaskSpec` 192 合成 `Task`；retry/mutation
  precondition 五个类型 → 一个 `Precondition`；`PersistentTaskCore` 收缩为对台账的薄 facade；`TaskCore` 删除。
- 语义变化：Task 字段校验由 schema 承担，不在每个记录的 `__post_init__` 重复；重试前置条件统一。
- 新测试：记录 canonical 编解码往返；admission 四种处置。

### 3.8 Task Store：15,190 → 3,500–4,500（执行卡 S2）

- 现状：`SqliteTaskStore` 一个类 14,093 行、58 个公开方法（46 个被外部调用，其中 40 个只被 `persistent_task_core`
  调用）、守卫 3,814 行、SQL 只有 580 行；v1..v6 迁移与校验；outbox 投递、claim 续约、settlement、durability 诊断
  都在同一个类里。
- 目标合同：四张小台账，各自一个文件、一个 writer：`executions`（task/attempt，`claimed → running →
  completed/failed/unknown`，终态不可改写）、`delivery`（outbox：`pending → delivering → delivered/failed/unknown`，幂等
  入队、原子认领、`renew_claim`、死 owner fence 为 unknown、绝不重放不确定投递）、`events`（per-task 单调 sequence +
  consumer cursor 一行）、`facts`（checkpoint 与 external-effect 的 append-only 事实）。一个一次性 importer（≤400）。
- 删/合：v1..v6 迁移；durability 诊断快照；双 reducer/verifier；`settle_unbound_queued_attempt`、
  `_settle_cancel_before_dispatch`、`project_has_unsettled_attempt` 作为台账 invariant 保留（各 ≤40 行）。
- 语义变化：UNKNOWN 一等终态；不确定的投递不重放；恢复是"标记 unknown 等 owner 决定"而不是"证明后重试"；旧库只读导入。
- 新测试：每张台账 race/restart/corruption 各一组（从旧 `test_persistent_task_core.py`、`test_p3_4_durability_*`
  移植）；importer 往返；单 writer 断言。
- 与 AgentCore 的关系：四张台账就是 F1–F6 的 Jiuwen 实现；AgentCore 落地后以 adapter 采用，不再第二次重写。

### 3.9 Project executor：6,881 → 2,500–3,200（执行卡 S2）

- 现状：`DirectProjectCodeExecutorAdapter` 3,438（19 个公开方法，8 个被外部调用）、`_DirectProjectAttemptJournal` 1,129
  （第二个效果 writer）、`ProjectCodeExecutorAdapter` 492（legacy，零 caller）、`_AttemptOwnershipLock` 86、
  `DirectProjectManagedBaselineReader` 134、`ProjectExecutionBinding` 147。
- 目标合同：`ProjectExecutor`（派发 Code Agent、流观察、结果结算）≤1,500；`WorktreeFacts`（Git/worktree/patch/tree 指纹）
  ≤400；所有权与结算走 `executions` 台账。
- 删/合：legacy adapter；attempt journal 的效果部分（归 `facts`）；ownership lock（归台账 lease）；过渡 profile。
- 语义变化：效果 truth 只有一份；执行器崩溃后的判定由台账 UNKNOWN + baseline reader 完成。
- 新测试：D0/D2 各一条成功路径、崩溃窗口、补偿。

### 3.10 Checkpoint/effect：2,953 → 800–1,000（执行卡 S2）

- 现状：六个 `durability_*` 文件，20 个值类型 1,307 行，复制同一组 helper；prefix verifier 689 行。
- 目标合同：一个 `Fact` codec（kind = checkpoint | effect，digest/size/codec 元数据）+ 一个 reconcile 决策函数。
- 删/合：prefix verifier（由 `facts` 台账的 append-only 保证）；recovery facts 并入 `Attempt`。
- 语义变化：checkpoint 不再单独"发布"，它是一种 fact。
- 新测试：codec 往返、reconcile 决策表。

### 3.11 Task event/progress：8,164 → 2,500–3,200（执行卡 S2、S4）

- 现状：`task_progress_return.py` 2,291、`progress_notification_arbiter.py` 2,228（一个 1,772 行 owner，17 个值类型）、
  `task_event_subscription.py` 1,568、`product_p3_text_adapter.py` 1,207、前端 `productTextProgress.ts` 870。
- 目标合同：`TaskEventSubscription`（读 `events` 台账 + cursor）≤600；`ProgressPolicy`（能不能出声、给谁、何时）
  ≤1,200，合并仲裁与进度返回；文本适配 ≤500；前端进度投影 ≤300。
- 删/合：两套 queue/ACK/lease 机制之一；live/authority 两种订阅模式 → 一种（durable cursor）；
  `TaskProgressReturnReason` 23 + `NotificationDisposition` 7 + `SpeechDisposition` 3 → 一个 `ProgressDecision`。
- 语义变化：进度通知只有一种投递路径；replay 由 cursor 决定。
- 新测试：通知/ACK/replay 三条；前台忙时的静默与恢复。

### 3.12 Presentation/history：2,063 → 1,500–1,800（执行卡 S4）

- 现状：`presentation_ledger.py` 1,272（两个 owner）、`p2_response_generation_store.py` 436、`formal_history_writer.py` 279、
  `task_control_presentation.py` 47。
- 目标合同：`PresentationLedger` 一个 owner（含 Task 呈现消费）；history writer 保留。
- 删/合：`TaskPresentationConsumptionOwner` 并入 ledger；11 个值类型 → 5。
- 语义变化：无（D-115 不变）。
- 新测试：ACK 后才写历史；surface seal；Task 呈现的一次性消费。

### 3.13 Formal Web/UI：16,517 → 5,500–7,000（执行卡 S6）

- 现状：`LiveVoiceIntegratedRoutePanel.tsx` 9,814（59 个导出，只有 2 个被别的生产文件用；主组件 7,304 行）、
  `productWebActivation.ts` 2,223、`productP2ActivationJournal.ts` 1,314、`formalP3TaskExperience.ts` 972、
  `formalTaskControlLeaf.ts` 952、`integratedWebRouteShell.ts` 587、`productP3ProgressGenerationJournal.ts` 236、
  `productP3TaskTargetJournal.ts` 148、其余约 600。
- 目标合同：`useLiveVoiceSession`（P1/P2/P3 三个 owner hook，各 ≤500）、`notificationArbitration.ts`（纯函数 ≤350）、
  一个 `TaskUi` owner（≤900）、一个 `DurableOperationClient`（≤800）、一本 `ActivationJournal`（≤500）、面板视图 ≤1,200。
- 删/合：两个 Task UI owner → 一个；三本同模式 journal → 一本；Panel 的 recovery/diagnostics 段移到 owner hook；
  `throw` 464 → ≤60。
- 语义变化：UI 错误进入统一文案表；Task 面板只有一个状态机。
- 新测试：三个 owner hook 的 mounted 测试；仲裁纯函数表驱动；feature-on/off。

### 3.14 Composition/config：20,076 → 2,500–3,200（执行卡 S3）

- 现状：`product_composition_registry.py` 16,070（`AgentServerProductCompositionRegistry` 15,059 行、184 个方法，27 个
  公开方法里 22 个是 `agent_ws_server` 调用的 `handle_*`/`close_active_routes`/`stop`，其余 5 个零 caller；P1/P2/P3 handler 工厂 + 每个 handler 重复 scope/session/principal
  校验 + 语义 dispatch 约 600 行 + Native handler 约 1,500）、`product_p2_interaction_adapter.py` 2,117（`P2ActivationLease`
  982）、`live_voice_configuration_declaration.py` 1,003、`product_composition_root.py` 459、`product_composition_contract.py` 424。
- 目标合同：`Registry`（注册 + 生命周期）≤1,200；handler 工厂搬回各 owner；语义 dispatch 搬到 §3.4；
  `CompositionRoot` ≤300（吸收 P2 activation lease）；配置声明 ≤300。
- 删/合：逐 handler 校验（授权在 `AuthorizationOwner` 做一次）；六种 lease 类 → 一种；配置值类型只留
  `ProductCompositionSettings`。
- 语义变化：请求进入时校验一次；feature-off 时 registry 不分配任何对象（不变）。
- 新测试：注册/关闭生命周期；feature-off；multi-Task；refresh/reconnect。

### 3.15 Observability：16,800 → 2,500–3,200（执行卡 S7，含一个产品决定）

- 现状：OTel 产品链（`product_observability_runtime.py` 1,425、adapter 847、correlation 876、codec 641、exporter 734）从未
  在任何部署启用；`observability.py` 1,960（15 个生产 importer）；`latency_measurement.py` 1,972；Alpha 支持
  `alpha_benchmark.py` 633、`alpha_privacy_conformance.py` 1,025、`observability_fault_harness.py` 391（零生产 caller，
  只被 S7 脚本与测试引用）；部署观测 1,494（S7 脚本引用）；被动 profiling 与音频诊断 JSONL 约 0.7K；前端约 2.9K。
- 目标合同：`Observation` 记录（≤700，隐私投影一个函数）、一个 sink（JSONL/回调，≤400）、一个 `DiagnosticSink`
  （profiling + 音频诊断，≤500）、前端 ≤500；L0 测量整体移到 `scripts/`。
- 删/合：OTel 产品链整体（决定 §7.2）；S7 探针脚本及其支持模块整体（决定 §7.2，随 Alpha 工具退休）；三通道
  exporter/投影 → 一个。
- 语义变化：不再产出 OTel backend 记录与 correlation receipt；隐私零泄露断言保留并覆盖唯一 sink。
- 新测试：隐私零泄露（合成秘密 canary）；sink 顺序与背压；profiling 报告脚本仍可解析。

### 3.16 Schema/protocol：6,958 → 2,000–2,500（执行卡 S1）

- 现状：`live_voice_contract_v2.py` 4,000（43 个值类型；`IdentityRegistry` 195、`TurnCommitLedger` 84、`ResponseFence` 64、
  `EventSequenceTracker` 508、`CommandResultLedger` 64 是 runtime owner 的第二副本；codec 996）、TS 副本
  `liveVoiceContractV2.ts` 2,785（81 个导出，只有 `parseEventEnvelope` 与 `canonicalJson` 被别的生产文件用）、
  `speech_rpc.py` 142、`live_voice_operation_budgets.py` 13。
- 目标合同：`Command/Query/Result/Event` 四个 envelope + `ScopeRef/ContextRef/IdentityRef/OriginRef`（≤1,000）；
  `ErrorCode` 全仓只此一处，数量为 ERROR_CODES 映射的结果（D-123），并带白名单诊断字段；canonical JSON codec ≤300；TS 类型由生成器产出。
- 删/合：schema 内的 registry/ledger/fence/tracker；`CapabilityDescriptor` → §3.3 `Capability`；`WorkProgressEventV2` →
  `TaskEvent`；TS 副本除 `parseEventEnvelope` 外删除。
- 语义变化：事件序列校验由 `events` 台账保证，schema 不再校验状态机；envelope 字段减少。
- 新测试：跨语言字节等价；生成器幂等。

### 3.17 Legacy/compat：3,096 → 0（执行卡 S6，决定 §7.3）

`useLiveVoiceDemo` 873、`LiveVoiceDemoBar.tsx` 637 的 legacy 部分、`liveVoiceCore` 445、`liveVoiceStreamingSpeech` 321、
`liveVoiceTurnLifecycle` 256、`browserSpeechSynthesisAdapter` 178、`integratedP1Route` 150、`liveVoiceMessageGate` 119、
`browserSpeechRecognitionAdapter` 117 与 `FEATURE_LIVE_VOICE_DEMO` 整体退休。语义变化：普通 `vite build` 不再渲染 legacy bar。

### 3.18 汇总

| # | 模块 | 现在 | 区间 | 执行卡 |
|---:|---|---:|---:|---|
| 1 | Browser Audio Edge | 9,023 | 4,000–5,000 | S6 |
| 2 | Web/Gateway media transport | 19,239 | 5,000–6,500 | S5 |
| 3 | Speech provider | 9,909 | 4,000–5,000 | S5 |
| 4 | Committed input/product authority | 16,902 | 6,500–8,500 | S3 |
| 5 | Conversation Runtime | 8,395 | 3,000–4,000 | S4 |
| 6 | Agent bridge | 3,078 | 1,000–1,300 | S4 |
| 7 | Task domain/control | 5,342 | 1,200–1,500 | S1/S2 |
| 8 | Task Store | 15,190 | 3,500–4,500 | S2 |
| 9 | Project executor | 6,881 | 2,500–3,200 | S2 |
| 10 | Checkpoint/effect | 2,953 | 800–1,000 | S2 |
| 11 | Task event/progress | 8,164 | 2,500–3,200 | S2/S4 |
| 12 | Presentation/history | 2,063 | 1,500–1,800 | S4 |
| 13 | Formal Web/UI | 16,517 | 5,500–7,000 | S6 |
| 14 | Composition/config | 20,076 | 2,500–3,200 | S3 |
| 15 | Observability | 16,800 | 2,500–3,200 | S7 |
| 16 | Schema/protocol | 6,958 | 2,000–2,500 | S1 |
| 17 | Legacy/compat | 3,096 | 0–0 | S6 |
| — | 未归桶（2 个 Native 相关小文件） | 120 | 100–200 | — |
| | **合计** | **170,706** | **48,100–61,600** | 承诺带 60–65K |

## 4. 语义变更目录（授权对象）

| 编号 | 变更 | 影响模块 | 谁能看到 | 落在哪个包 |
|---|---|---|---|---|
| SC-1 | 拒绝语义归并：27 个 reason 枚举 311 个值 → 类别 `code` + 白名单诊断字段（D-123，数量为映射结果）；内部一致性错误不再是类型化违规 | 全部 | 前端文案、日志、评审脚本 | S0 定表，S1 落地，其余包采用 |
| SC-2 | 一个授权 owner：P2/P3 确认、critical-token 澄清、production intent 确认统一 TTL/scope/一次性消费 | 4、14 | 确认对话的时序与提示 | S3 |
| SC-3 | 一个 response fence：播放期插话与生成期打断同一记录、同一取消入口 | 5、6、12 | 打断后的呈现与历史 | S4 |
| SC-4 | Task 台账化：UNKNOWN 一等终态、不重放不确定投递、旧库一次性导入、无 authority replay 模式 | 7–11 | 崩溃/重启后的任务状态文案 | S2 |
| SC-5 | checkpoint 成为 fact 的一种，不再单独发布 | 10 | 无用户可见影响 | S2 |
| SC-6 | 观测：退休旧 OTel 实现与 S7 探针工具，三通道 → 一个 sink，第一版不外部导出；L0 测量出生产树（D-122，含退休前检查） | 15 | 运行手册、profiling 报告数据源 | S7 |
| SC-7 | schema 收缩：envelope 字段减少、状态机校验移出 schema、TS 由生成 | 16、2、13 | 协议版本号递增 | S1 |
| SC-8 | provider 合同：能力自报替代 conformance 校验，降级理由粗粒度 | 3、2 | 降级提示文案 | S5 |
| SC-9 | 前端：Panel 拆 owner hook，一个 Task UI，一本 journal，错误文案表 | 13、1 | UI 结构不变，错误提示变 | S6 |
| SC-10 | legacy 链与 `FEATURE_LIVE_VOICE_DEMO` 退休 | 17 | 普通 build 无 legacy bar | S6 |

## 5. 测试与 oracle

旧测试都在分支上，是重写期间唯一的回归网。规则：

1. **旧套件不整体删除，按包退役**：每个包先给新合同写新测试，切换后在同一个包里删除该模块的旧测试文件。
   包结束时不允许存在"引用已删 symbol 而无法收集"的旧测试。
2. **基线先记录**（S0）：后端 `tests/unit_tests/{live_voice,agentserver,gateway,channel,common}`（排除
   `tests/unit_tests/gateway/test_agent_client.py`，它连接真实 websocket 会挂起）与前端 `package.json` 里
   `test:live-voice-*`、`test:task-notification-*` 的失败清单存入 `live-voice/slimming/BASELINE_2026-09-07.md`。
   已知基线失败：前端 `test:live-voice-gateway-batch-speech`（用例调用系统 Python，缺 `httpx`）与
   `test:live-voice-integrated-web`（三个 mounted 用例）；后端在 w3 tip `d8ee9e6d3` 上 106 个失败（7,731 通过），主要在
   `test_product_composition_registry.py` 68、`agentserver/test_debug_trace.py` 8、`test_semantic_registry.py` 7、
   `test_task_progress_return.py` 5、`test_p3_authenticated_composition.py` 4、`gateway/test_native_business_observation_gateway.py` 4；
   本分支与基线失败集相同（`test_p3_8a_sli_privacy_contracts.py` 随其两个已退休模块一起退役）。S0 重跑一次并存档。
3. **失败分类**：包切换后旧套件的新增失败逐条对照 §4：属于本包声明的语义变更 → 删除或改写该用例；
   不属于 → 缺陷，先修再继续。分类结果写进包的提交说明。
4. **新测试预算**：目标生产 60–65K，按 Hermes 的测试/生产比 1.24 约 75–80K；分层：每包合同测试（成功路径必须
   断言成功，不只断言拒绝）、注释里每条不变量配一个能杀死反向变异体的用例、台账的并发/重启用例、隐私
   canary、前端 mounted 测试、合成语音 journey（`scripts/live_voice/semantic_audio_*` 需从 `7c7aad7b8` 回收）、
   物理 demo journey。
5. **替身规则**：SDK/Provider 替身照源码写，不按假设写；夹具只观察不替换生产方法。
6. **验收**：每包以"新测试全过 + 旧套件失败集只含本包声明的变更 + journey"验收。

## 6. 实施包总表与顺序

全部为语义变更（Tier 3），每包独立提交、独立 revert；旧台账在 S2 后只读保留一个包周期。细节见第二部分执行卡。

| 包 | 模块 | 风险 | 依赖 | 主要产出 | 回滚 |
|---|---|---|---|---|---|
| S0 授权与基线 | — | 低 | §7 决定 | Decision、基线记录、错误码表、oracle 清单 | 单提交 revert |
| S1 schema 与 Task 记录 | 16、7 | 中 | S0 | `common/schema/live_voice/` 新包、TS 生成器 | 生成器不接入即无影响 |
| S2 Task 台账 | 8、10、11（订阅）、9（所有权）、7 | 高 | S1 | `server/live_voice/task/` 四张台账、importer、执行器改用台账 | 旧 Store 只读 + importer 反向演练 |
| S3 授权 owner 与组合根 | 4、14 | 高 | S1 | `AuthorizationOwner`、`CommittedInputJournal`、registry 只注册 | 独立提交 revert |
| S4 runtime、fence、round、呈现 | 5、6、12、11（策略） | 高 | S1 | 一个 runtime、一个 fence、一个 RoundOwner、ledger 合一、ProgressPolicy | 独立提交 revert |
| S5 媒体与 provider | 2、3 | 高 | S1、S4 | `MediaSession`、`RouteLifecycle`、`SpeechProvider` | 独立提交 revert |
| S6 前端 | 1、13、17 | 中 | S1、S5 | `AudioEdge`、owner hook、TaskUi、journal、legacy 退休 | 独立提交 revert |
| S7 观测 | 15 | 中 | S0 决定 §7.2 | 退休 OTel 链与 S7 工具、一个 sink、L0 出树 | 独立提交 revert |
| S8 验收与计量 | 全部 | 中 | 全部 | 物理 journey、独立评审、预算对照、多仓口径报告 | — |

顺序：S0 → S1 → S2 与 S3 并行 → S4 → S5 → S6 → S7 随时 → S8。第一份实测比例来自 S1+S2，用它修正 §3.18。

## 7. 需要用户决定

1. **授权语义变更**：已由 D-121（选择路线 B）记录，范围 SC-1..SC-10 与 §1.1 预算。
2. **退休 OTel 产品观测链与 S7 探针工具**：已由 D-122 决定一记录。退休旧实现，保留必要观测，第一版不提供外部导出；
   B7 前逐项记录 D-122 的四条退休前检查。
3. **退休 legacy 链与 `FEATURE_LIVE_VOICE_DEMO`**：已由 D-122 决定二记录。正式入口进入标准构建、未配置时说明；
   入口迁移完成后删除 legacy；旧演示模式归档，仍需展示的能力迁到新 journey。
4. **Task 家族在仓库内重写为四张小台账**，不等 AgentCore F1–F6；AgentCore 落地后以 adapter 采用。
5. **错误码归并策略**：已由 D-123 记录。类别 `code` + 白名单诊断字段 + 用户文案；码的数量是映射结果；文案由工程维护、
   产品审阅，中文为主、英文随界面语言切换。

## 8. 计量与复现

- 每包结束运行 `module_buckets.py --rev HEAD` 与 `anatomy_modules.py --rev HEAD`，把 §2 表和 §1.1 预算重算一次；
  值类型、异常、守卫、owner、`throw` 五项预算任一超标即不通过 S8。
- 行数只记手写源码；生成物、迁移 importer 的一次性代码、测试分别记账。
- Native 段在其单独 commit 采用本计划合同后，再并入同一张表。

## 9. 风险

- 旧套件里有基线失败：不先记录就分不清哪些失败是重构造成的（S0 强制）。
- 语义变更外溢：SC-1 的错误码归并会改变前端文案与评审脚本；S0 先出文案表。
- 第一份实测：§3.18 的区间全部是规划值；S1+S2 落地后若比例明显偏离，先修正区间再继续。
- 巨型类的隐藏调用：附录 A/B 的 caller 数是静态名字匹配，同名方法会高估、通过工厂或 `getattr` 的调用会漏计；
  执行卡要求删除前 `grep` 复核，并以测试集为准。
- 分支落后：`agtai/hx/0812_live_voice_w3` 若再前进，按 §8 重基线后再开新包。

# 第二部分 执行卡

每张卡按同一结构写：目的 → 前置条件 → 输入清单 → 目标结构 → symbol 处置 → 步骤（每步带验证）→ 测试 →
完成判据 → 禁止事项 → 回滚。执行者只需按步骤操作；遇到卡片没有写明的情况，停下来记录，不要自行猜测。

## 10. 通用规程

### 10.0 新会话启动（另一台机器，从零到全部完成）

本节给一个全新会话用：它只拿到分支 `hx/0907_livevoice_slimming`，目标是把路线 B 做完。读完本节再读下面列的文档，然后
从目标架构 §10 的 B0 开始。

**前提（由用户提供）**

- 分支已在 `agtai/hx/0907_livevoice_slimming`。新机器：`git fetch agtai` 后
  `git checkout -b hx/0907_livevoice_slimming agtai/hx/0907_livevoice_slimming`。基线 `agtai/hx/0812_live_voice_w3` 可能已
  前进，先 `git log --oneline HEAD..agtai/hx/0812_live_voice_w3` 看差距；rebase 与否由用户定，不自行 rebase。
- Python ≥3.11 与 uv、Node LTS、Git。独立 clone 里允许 `uv sync` 与 `npm ci`（§10.1 的 `uv sync` 禁令只针对共享 venv 的
  worktree）。测试命令见 §10.2；`--no-cov`、不传 `-o addopts=''`。
- 私有配置按 runbook `live-voice/runbooks/E2E_RUNBOOK.md` §3、§4.1、§4.2：固定依赖、隔离数据目录、provider 凭据与设备。
  没有凭据时 B2 只能录 fake provider 的 journey，真实 provider 的差分等凭据到位后补录。
- 物理验收（B9 的 demo journey）需要带麦克风与扬声器的机器和人；服务器会话只准备证据绑定与报告，不宣称 PASS。

**读什么，按顺序（约 2,000 行）**

1. root `AGENTS.md`（每次 push 单独批准、worker 不推）与 `TESTING.md` 的分级。
2. `live-voice/decisions/DECISIONS.md` 的 D-121、D-122、D-123：授权范围、退休边界、错误模型。
3. `live-voice/LIVEVOICE_TARGET_ARCHITECTURE_2026-09-07.md` 全文：§1 能力与不变量、§3 原则、§4–§5 设计、§6 正确性、
   §10 包序列。
4. 本文 §10.1–10.5、§4（SC-1..10）、§1.2（不变量）；然后只读正在执行的卡：S0（§11）、S1（§12）、S2（§13）、S5（§16）、
   S7（§18）、S8（§19）。S3/S4/S6 只用其 symbol 处置表做完整性核对。
5. 附录 INVENTORY 与 METHOD_MAP 只查不读。官方 Hermes 对比与总计划只作背景，不作指令。

**执行顺序与每包的第一件事**

按目标架构 §10 的 B0 → B9。文档已足够直接执行的包：B0、B1、B4、B5、B7、B9（复用卡片）。下列包的线级规格尚未写，
执行者在编码前先写规格，本地提交交用户审阅，审阅通过再编码：

| 包 | 先写的规格 | 落点 |
|---|---|---|
| B1 | 15 种事件的 payload 字段与折叠规则；16 个方法的请求、响应、错误码；服务与前端的构建标识字段（D-122） | schema 包 docstring、生成的 TS、`live-voice/slimming/EVENTS_AND_METHODS.md` |
| B2 | 录放 harness：录什么、摘要怎么算、差异如何分类为 SC 项或回归、常驻 canary 断言 | `scripts/live_voice/replay/README.md` |
| B3 | 会话、响应围栏、任务尝试、媒体会话、浏览器视图五张状态转移表；旧责任台账（旧机制 → 新组件，或按哪条 SC 放弃） | `live-voice/slimming/STATE_TABLES.md`、`RESPONSIBILITY_LEDGER.md` |
| B6 | 界面必须呈现的状态与文案键（含未配置状态）；旧演示模式中需迁移的能力清单 | `live-voice/slimming/UI_STATES.md` |
| B8 | flag 形态、新旧并跑期的数据处理、Native mixin 需要的 `MediaSession` 接口 | `live-voice/slimming/CUTOVER.md` |

**门与批准**

- B3 完成后停下，交用户审阅行数比例与差分结果，再进入 B4。
- 每包按 §10.4 收尾，本地提交；任何 push 先按 `AGENTS.md` 报出 remote、ref、commits、mode，等批准。
- D-122 的退休前检查 1–2 由用户或运维给结果；执行者只记录，不等待。
- 模型与强度：规格写作与 B3 探针用最高推理强度；按卡执行的 B0/B4/B5/B7 可用较低强度。

**完成的定义**：目标架构 §6.3 的三条 journey PASS、anatomy 预算达标、B8 的旧 symbol grep 为零、B9 报告与 STATUS 更新；
其中物理 journey 由用户在有设备的机器上跑。

**启动提示词**（粘贴给新会话）：

```text
你是 LiveVoice 路线 B 的执行者。分支 hx/0907_livevoice_slimming。先读
live-voice/LIVEVOICE_DESIGN_SIMPLIFICATION_PLAN_2026-09-07.md 的 §10.0，按它列的顺序读完文档，再从
live-voice/LIVEVOICE_TARGET_ARCHITECTURE_2026-09-07.md §10 的 B0 开始。规则：每包本地提交，不 push；
B1/B2/B3/B6/B8 先写规格交我审阅再编码；B3 之后停下等我审阅；不改 D-098..D-115 的不变量；
语义变更只限计划 §4 的 SC-1..10；Native 不动。目标是做完 B0–B9。
```

### 10.1 环境

- 工作区：本仓库的 git worktree，分支 `hx/0907_livevoice_slimming`；所有命令在仓库根目录运行。
- Python：`D:/XGG AI/openjiuwen/jiuwenswarm/.venv/Scripts/python.exe`（主仓库共享 venv）。不要在 worktree 里运行
  `uv sync`（会把共享 venv 的 editable 映射改到本 worktree）。
- 前端：`jiuwenswarm/channels/web/frontend`，`node_modules` 是指向主仓库 `jiuwenswarm/channels/web/frontend/node_modules`
  的 junction。缺失时用 PowerShell 创建：`New-Item -ItemType Junction -Path <worktree>/…/node_modules -Target <主仓库>/…/node_modules`。
  在任何 `git worktree remove` 之前必须先删掉这个 junction（`--force` 会穿透 junction 删空主仓库依赖）。
- 文本文件一律 UTF-8 无 BOM、LF；用 Python 或编辑工具写文件，不用 PowerShell 的重定向。

### 10.2 命令

| 用途 | 命令 |
|---|---|
| 后端相关套件 | `python -m pytest tests/unit_tests/live_voice tests/unit_tests/agentserver tests/unit_tests/gateway tests/unit_tests/channel tests/unit_tests/common --ignore=tests/unit_tests/gateway/test_agent_client.py -q --no-cov -p no:cacheprovider` |
| 单个测试文件 | 同上，把目录换成文件；不要传 `-o addopts=''`（会清掉 asyncio 模式，凭空制造几十个假失败） |
| 前端某脚本 | `cd jiuwenswarm/channels/web/frontend && npm run --silent test:<name>` |
| 前端全部 live-voice 脚本 | `for s in $(node -e "const p=require('./package.json');console.log(Object.keys(p.scripts).filter(k=>/^test:(live-voice|task-notification)/.test(k)).join(' '))"); do npm run --silent "$s" >/dev/null 2>&1 && echo "PASS $s" \|\| echo "FAIL $s"; done` |
| 前端整体编译 | `cd jiuwenswarm/channels/web/frontend && npm run build:live-voice` |
| 行数与解剖 | `python scripts/live_voice/slimming/module_buckets.py --rev HEAD`；`python scripts/live_voice/slimming/anatomy_modules.py --rev HEAD` |
| symbol 与方法清单 | `python scripts/live_voice/slimming/symbol_inventory.py --rev HEAD --out live-voice/LIVEVOICE_DESIGN_SIMPLIFICATION_INVENTORY_2026-09-07.md`；`python scripts/live_voice/slimming/method_map.py --rev HEAD --out live-voice/LIVEVOICE_DESIGN_SIMPLIFICATION_METHOD_MAP_2026-09-07.md` |
| 引用复核 | `grep -rn "\bName\b" jiuwenswarm tests scripts --include=*.py --include=*.ts --include=*.tsx --include=*.mjs` |

### 10.3 规则

1. **一包一提交，不推送**。提交说明列出：改了哪些 SC、退役了哪些旧测试、新增了哪些测试、行数变化。
2. **删除前复核**：附录 A/B 的 `callers`/`文件内引用` 是静态名字匹配。任何删除前先跑 10.2 的引用复核；grep 只在
   测试里命中的 symbol 可以删（同时处理测试），在生产里命中的不能删，回到卡片对应的处置行。
3. **输家在同一个包里消失**：被替代的类、表、合同、测试文件、`package.json` 脚本在同一提交里删除。
   不允许"先留着以后删"。
4. **不碰 Native**：`server/live_voice/native_*`、`server/live_voice/openai_realtime_*`、
   `gateway/live_voice/native_*`、`frontend/.../native*.ts`、`product_composition_registry.py` 与
   `dedicated_media_registration.py` 里名字含 `native` 的方法。只允许改它们的 import 路径以指向新模块；改动的行数
   单独记入提交说明。
5. **失败分类**：一步验证失败时，先判断是否属于本包声明的 SC；是 → 改写或删除该用例并在提交说明记录；否 →
   修代码，不改测试。禁止注释掉测试、跳过测试或放宽断言来让套件通过。
6. **单 writer**：新模块不得 import 它要替代的旧模块（importer 除外）；旧模块不得 import 新模块。
7. **接口稳定的命名**：被别的生产文件调用的公开方法保留原名（附录 B 的 `callers > 0` 项），除非卡片写明改名。
8. **每步的验证必须通过才能进下一步**；一个包内允许多次本地提交（WIP），包结束时 squash 成一个提交。
9. **行数口径**：每张卡的完成判据用 `module_buckets.py` 的模块行数与 `anatomy_modules.py` 的预算列核对。

### 10.4 每包固定的收尾清单

1. `python scripts/live_voice/slimming/module_buckets.py --rev HEAD` 的目标模块行数在区间内。
2. `anatomy_modules.py --rev HEAD` 的值类型、异常、守卫、owner、`throw` 五项没有超过 §1.1 的目标按模块分摊值
   （卡片里给出）。
3. 后端相关套件与前端脚本：失败集 = 基线失败集 ∪ 本包声明退役的旧测试（已删）；没有其他失败。
4. `git grep -n "<被删 symbol>"` 为零（卡片给出清单）。
5. 提交说明按 10.3 第 1 条写完整。

### 10.5 执行者需要做什么判断

本文把每个包的意图、范围、去向、验证固定下来，但不能替执行者做设计。按可机械执行的程度分三档：

| 档 | 包 | 执行者要做的判断 |
|---|---|---|
| 机械 | S0、S7、S1 的删除项与生成器 | 只需按步骤操作；唯一的判断是 10.3 第 2 条的 grep 复核 |
| 有界设计 | S1 的记录字段、S2 的四张台账、S5 的 provider 与 route lifecycle | 卡片给出保留的方法名、状态集合、行数上限、必须移植的用例；执行者要设计字段与内部状态机，并让移植的用例通过 |
| 合并设计 | S3 的授权 owner、S4 的 runtime/fence、S6 的 owner hook | 卡片给出输入 owner、保留的公开方法、退役的值类型与验收用例；执行者要决定内部结构，并在旧套件失败集里逐条分类（10.3 第 5 条） |

执行者遇到卡片没写的选择时，按 §1.2 的不变量与 §4 的 SC 编号决定：能归到某条 SC 的是允许的变更，归不到的必须保持行为。
无法归类时停下记录，不猜。

## 11. S0 授权与基线

- **目的**：把执行的前提固定下来：决定、基线失败集、错误码表、oracle 回收。
- **前置**：§7 的五个决定已由 D-121、D-122、D-123 记录。
- **输入**：`live-voice/decisions/DECISIONS.md`；`scripts/live_voice/slimming/*`；`git show 7c7aad7b8:scripts/live_voice/`
  下的 `semantic_audio_runtime.py`、`semantic_audio_browser.py`、`semantic_audio_journey.py`、`semantic_audio_assertions.py`。
- **目标结构**：
  - `live-voice/decisions/DECISIONS.md` 已有 D-121（路线 B 与语义变更授权）；补记 §7.2、§7.3、§7.5 的结论。
  - `live-voice/slimming/BASELINE_2026-09-07.md`：后端与前端失败清单（10.2 的两条命令的输出），18 模块行数，解剖表。
  - `live-voice/slimming/ERROR_CODES.md`：D-123 的七列映射表（原触发条件、对应操作、结果确定性、处理动作、目标 `code`、
    诊断字段、文案键），覆盖 27 个 reason 枚举的 311 个值；码的数量是映射结果。
  - `scripts/live_voice/semantic_audio_*.py` 四个文件从 `7c7aad7b8` 回收。
- **错误码表的写法**：目标码固定为 `invalid_input, unauthorized, forbidden, not_found, conflict, stale, expired, busy,
  unavailable, cancelled, interrupted, timeout, provider_failed, transport_failed, result_unknown, capacity, degraded,
  internal`（18 个，留 2 个备用）。把下列枚举的每个值映射到其中之一，一行一个：`live_voice_contract_v2.ErrorCode`（15）、
  `product_authority.AuthorityDecisionReason`（19）、`critical_token_safety.CriticalTokenReason`（22）、
  `task_progress_return.TaskProgressReturnReason`（23）、`browser_gateway_media_transport.MediaDetachReason`（27）、
  `openai_streaming_speech.SpeechDegradationReason`（11）、`streaming_synthesis_route.StreamingSynthesisReason`（14）、
  `dedicated_media_route.DedicatedMediaRouteReason`（8）、`product_p2_interaction_adapter.P2ActivationReason`（12）、
  `product_p3_text_adapter.ProductP3TextReason`（15）、`production_task_intent.ProductionTaskPolicyOutcome`（7）、
  `live_voice_configuration_declaration.ConfigurationDeclarationReason`（6）。前端文案：为 18 个码各写一条中文与英文
  文案，放同一文件的第二张表。
- **步骤**：
  1. 运行 10.2 的后端与前端命令，把输出原样存入 BASELINE 文件（含 `passed/failed` 汇总行）。验证：文件里有两段输出。
  2. 运行 `module_buckets.py` 与 `anatomy_modules.py`，把表贴进 BASELINE。验证：模块合计 = 170,706（不含 Native）。
  3. 写 DECISIONS 条目与 ERROR_CODES。验证：ERROR_CODES 的映射覆盖上面 12 个枚举的全部值（用脚本数：
     `python - <<EOF` 读取每个枚举的成员数并与表中行数比对）。
  4. 回收四个 `semantic_audio_*.py`：`git checkout 7c7aad7b8 -- scripts/live_voice/semantic_audio_runtime.py …`。
     验证：`python -c "import ast,io;[ast.parse(io.open(f,encoding='utf-8').read()) for f in [...]]"` 无语法错误。
  5. 提交：`docs(live-voice): authorize the design-simplification path and record its baseline`。
- **完成判据**：四个文件存在；DECISIONS 的 D-121 之后补记了 §7.2/7.3/7.5 的结论；BASELINE 的失败集可被后续包引用。
- **禁止**：改任何生产代码。
- **回滚**：revert 该提交。

## 12. S1 schema 与 Task 记录

- **目的**：建立唯一的 canonical schema 包与 Task 记录，生成 TS 类型；后续所有包只依赖它。
- **前置**：S0 完成；`ERROR_CODES.md` 存在。
- **输入**：`jiuwenswarm/common/schema/live_voice_contract_v2.py`（4,000）、`server/live_voice/formal_task_models.py`
  （2,628）、`server/live_voice/task_core.py`（714）、`server/live_voice/executor_capabilities.py`（373）、
  `gateway/live_voice/speech_rpc.py`（142）、`common/live_voice_operation_budgets.py`（13）、前端
  `features/live-voice/formal/liveVoiceContractV2.ts`（2,785）；测试 `tests/unit_tests/common/test_live_voice_contract_v2.py`、
  `tests/unit_tests/live_voice/test_task_core.py`、前端 `tests/liveVoiceContractV2.test.mjs`。
- **目标结构**（新包 `jiuwenswarm/common/schema/live_voice/`）：

| 文件 | 内容 | 行数上限 |
|---|---|---:|
| `errors.py` | `ErrorCode`（S0 的 18 个）、`LiveVoiceError(code, message, details)`；全仓唯一异常基类 | 80 |
| `refs.py` | `ScopeRef`、`ContextRef`、`IdentityRef`、`OriginRef`、`ProducerRef`、`ResponseRef`、`IdentityKind` | 200 |
| `envelopes.py` | `CommandEnvelope`、`QueryEnvelope`、`ResultEnvelope`、`EventEnvelope`、`TurnCommit`、`KnownFact`、`Assurance`、`TerminalOutcome`、`CancelScope`、`Speakability`、`InputCommitState`、`LifecycleKind` | 450 |
| `task_records.py` | `Task`、`Attempt`、`Command`、`Precondition`、`Result`、`TaskEvent`、`Cursor`、`OutboxItem` + 枚举 `TaskState`、`AttemptState`、`OutboxState`、`AdmissionDisposition`、`ResultAvailability`、`AdjustmentState`、`WorkState`、`WorkUrgency`、`WorkSourceAuthority` | 600 |
| `codec.py` | `canonical_json`、`canonical_json_bytes`、`CONTRACT_VERSION`、`MAX_SAFE_INTEGER`、记录的 `to_wire/from_wire` | 300 |
| `__init__.py` | 只 re-export | 40 |
| `scripts/live_voice/schema/generate_ts.py` | 由上述记录生成 `frontend/src/features/live-voice/contract/generated.ts` | 300 |

- **symbol 处置（`live_voice_contract_v2.py`）**：

| 处置 | symbol |
|---|---|
| 迁入 `refs.py`（保留名） | `ScopeRef`(39 callers)、`ContextRef`(8)、`IdentityRef`(2)、`OriginRef`(4)、`ProducerRef`(4)、`ResponseRef`(22)、`IdentityKind`(4) |
| 迁入 `envelopes.py`（保留名） | `CommandEnvelope`(9)、`QueryEnvelope`(4)、`ResultEnvelope`(7)、`EventEnvelope`(6)、`TurnCommit`(20)、`KnownFact`(1)、`Assurance`(20)、`TerminalOutcome`(15)、`CancelScope`(2)、`Speakability`(2)、`InputCommitState`(4)、`LifecycleKind`(4) |
| 迁入 `task_records.py` | `WorkProgressEventV2`(5) → `TaskEvent`；`WorkProgressSource`(1) → `TaskEvent.source`；`WorkState`(3)、`WorkUrgency`(1)、`WorkSourceAuthority`(3) |
| 迁入 `errors.py` | `ErrorCode`(39，按 ERROR_CODES 映射重编)、`ContractError`(1) 与 `ContractViolation`(9) → `LiveVoiceError` |
| 迁入 `codec.py` | `canonical_json`、`canonical_json_bytes`(36)、`CONTRACT_VERSION`(9)、`MAX_SAFE_INTEGER`(19) |
| 留在 shim，S4 删除 | `IdentityRegistry`、`TurnCommitLedger`(6)、`ResponseFence`(3)、`EventSequenceTracker`(1)、`CommandResultLedger`、`validate_transition`(4)、`EventApplyStatus`(1)、`EventApplyResult` |
| 留在 shim，S5 删除 | `CapabilityDescriptor`(1)、`Availability`(1)、`Knowledge`(1) |
| 本包删除（零引用） | `CapabilityRegistry`、`parse_v2_envelope`、`dispatch_cancel`、`dispatch_committed_input`、`classify_contract`、`default_barge_in_scopes`、`ContextRevision`、`ContextRedaction`、`IdentityRecord`、`SideEffectTarget`、`ContextRevisionKind`、`ConnectionEpochRef`（先 grep：若只被 shim 内将删的 owner 用则删）、`V1_CONTRACT_VERSION`、`FrozenJson` |

- **symbol 处置（`formal_task_models.py` → `task_records.py`）**：

| 目标记录 | 合并自 |
|---|---|
| `Task` | `FormalTaskSpec`(5)、`PersistentTaskRecord`(8)、`ResolvedTaskContext`(6) 的持久字段、`TaskAuthorizationGrant`(8) 的 scope 字段、`PersistentAdmissionRecord`(3) |
| `Attempt` | `PersistentAttemptRecord`(5)、`PersistedExecutorSelection`(4)、`ExecutorObservation`(3)、`ExecutorRetryReadiness`(2)、`DurableRecoveryAuthoritySnapshot`(1)、`TaskRetryAuthoritySnapshot`(2)、`AppliedTaskRetryReplay`(2) |
| `Command` + `Precondition` | `TaskAdjustmentRequest`(2)、`TaskMutationPrecondition`(3)、`TaskRetryPrecondition`(3)、`TaskRetryProductRequestFingerprint`(4)、`TaskCommandDisposition`(2)、`TaskMutationDisposition`(2)、`TaskMutationResult`(2)、`TaskAdjustmentDeliveryResult`(3)、`TaskAdjustmentSettlement`(3)、`ExecutorDeliveryResult`(2) |
| `Result` | `TaskResultRecord`(5)、`TaskResultArtifact`(3)、`TaskResultAvailability`(5) |
| `TaskEvent` + `Cursor` | `PersistentTaskEvent`(9)、`TaskUnreadPage`(3)、`TaskEventConsumerAuthorityPage`(2)、`TaskEventAuthoritySnapshot`(2)、`TaskEventConsumerCursorBaseline`(3) |
| `OutboxItem` | `PersistentOutboxItem`(4)、`OutboxKind`(5)、`OutboxState`(2) |
| 枚举保留 | `FormalTaskState`(5) 改名 `TaskState`（吸收 `task_core.TaskState`）、`FormalAttemptState`(4) 改名 `AttemptState`、`AdmissionDisposition`、`AdmissionPriority`(2)、`ReconciliationState`(1)、`ExecutorResolution`(3)、`TaskAdjustmentState`(3) |
| 函数保留到 `codec.py` | `command_result_extensions`(2)、`require_exact_payload`(1)、`canonical_task_adjustment_rejection_reason`(1)、`utc_now`(8)、常量 `TASK_RETRY_PRODUCT_REQUEST_EXTENSION`（只被本文件的 4 处用，随 `Precondition` 迁入 `task_records.py`） |
| 删除 | `AdmissionPolicy`(3，归 S2 `admission.py`)、`safe_json_value`(0)、`FormalTaskViolation` → `LiveVoiceError`；`task_core.py` 的 `TaskCore`、`project_work_progress`、`TaskCoreSnapshot`、`TaskQuery`、`DispatchIntent`、`CancelIntent`、`WorkProgress`、`AuthorizationContext`、`TaskCoreViolation`（`TaskCommand`(1)、`TaskSpec`(1) 的两个 caller 改用 `Command`/`Task`） |

  `__post_init__` 的校验只保留"外部输入边界"一类：非空、长度上限、枚举成员；删除"字段之间一致性"与"版本一致"
  类校验（这些由台账写入时保证）。

- **步骤**：
  1. 建包，先写 `errors.py`、`refs.py`、`codec.py`。验证：`python -c "import jiuwenswarm.common.schema.live_voice as s"`。
  2. 写 `envelopes.py`。写等价测试 `tests/unit_tests/common/test_live_voice_schema.py`：对
     `tests/unit_tests/common/test_live_voice_contract_v2.py` 里现有的每个 envelope fixture，旧类与新类的
     `canonical_json_bytes` 相等（字段减少的地方在测试里列出减少的字段名）。验证：新测试通过。
  3. 写 `task_records.py`；等价测试对 `test_persistent_task_core.py` 中的记录 fixture 做同样比对。验证：通过。
  4. 写生成器与 `generated.ts`；`npx tsc --noEmit generated.ts`（用 `test:live-voice-contract-v2` 的 tsc 参数）。验证：通过。
  5. `live_voice_contract_v2.py` 改为 shim：删除本包删除项，保留项改为 `from jiuwenswarm.common.schema.live_voice import …`
     再 re-export；owner 类原样保留。验证：后端相关套件失败集 = 基线 ∪ 本包退役的用例（下条）。
  6. `liveVoiceContractV2.ts`：只保留 `parseEventEnvelope`(2 callers)、`canonicalJson`(1) 与它们的依赖；其余导出改为
     `export … from './contract/generated'` 或删除。验证：`npm run build:live-voice` 通过；`test:live-voice-contract-v2`
     里引用已删导出的用例删除，其余通过。
  7. 退役测试：`test_task_core.py` 全部（`TaskCore` 删除）；`test_live_voice_contract_v2.py` 中针对本包删除项的用例；
     `tests/liveVoiceContractV2.test.mjs` 同上。
  8. 提交：`refactor(live-voice): introduce the canonical schema package and task records (SC-1, SC-7)`。
- **完成判据**：新包 ≤1,700 行；`generated.ts` 由脚本生成且 `git diff` 为零；模块 16 ≤2,500；`formal_task_models.py`
  仍存在但只剩 shim（≤150 行，S2 删除）；`throw`/守卫按 §1.1 分摊：模块 16 守卫 ≤120。
- **禁止**：改 runtime/registry/store 的行为；在新包里放任何 owner。
- **回滚**：revert；生成器与新包未被接入时无影响。

## 13. S2 Task 台账

- **目的**：用四张小台账替代 `SqliteTaskStore`，`PersistentTaskCore` 变薄 facade，executor 的所有权与效果 truth 归台账。
- **前置**：S1 完成；§7.4 决定为"是"。
- **输入**：`server/live_voice/task_store.py`（15,190）、`persistent_task_core.py`（1,627）、`project_code_executor.py`
  （6,881）、`durability_effects.py`（920）、`durability_readers.py`（689）、`durability_checkpoint.py`（499）、
  `durability_recovery_facts.py`（466）、`durability_authority.py`（229）、`durability_identity.py`（150）、
  `task_event_subscription.py`（1,568）、`task_admission.py`、`executor_capabilities.py`（373）；测试
  `test_persistent_task_core.py`（10,906）、`test_p3_4_durability_store.py`、`test_p3_4_durability_runtime.py`、
  `test_durability_effects.py`、`test_task_admission.py`、`test_task_result_event_consumption.py`、
  `test_project_code_executor.py`（5,762）、`test_project_task_handoff.py`、`test_authorized_project_snapshots.py`。
- **目标结构**（新包 `jiuwenswarm/server/live_voice/task/`）：

| 文件 | 内容 | 行数上限 |
|---|---|---:|
| `executions.py` | `ExecutionLedger`：task/attempt 行；状态 `claimed → running → completed/failed/unknown`；终态不可改写；`claim_task/renew/settle_unbound/settle_cancel_before_dispatch/has_unsettled(project)` | 900 |
| `delivery.py` | `DeliveryLedger`：outbox 行；`enqueue(idempotent by command_id)`、`claim_next`、`renew_claim`、`complete/reject/release`、`recover_abandoned → unknown`、`reset_expired_claims` | 700 |
| `events.py` | `EventLog`：per-task 单调 `sequence`，`append/page/unread_page/ack`；`Subscription(consumer_id)` 一行 cursor，`next_event` | 700 |
| `facts.py` | `FactLedger`：append-only `Fact(kind=checkpoint\|effect, digest, size, codec_version, payload_ref)`；`claim_mutator/release_mutator`；`latest_settled_effect(project_root)`；reconcile 决策函数 | 600 |
| `core.py` | `TaskCore` facade：`execute/query/reconcile/reconcile_status/drain_inflight_adjustments/read_applied_retry_replay/read_consumer_task/read_consumer_task_result/read_current_retry_authority`（保留这些名字，它们被 `p3_authenticated_composition` 调用）；原 `FormalExecutor` Protocol 改名 `Executor`、`ReconciliationEventSink`(1 caller) 保留；`project_task_event`(0) 删除 | 800 |
| `admission.py` | 原 `task_admission.py` + `AdmissionPolicy` | 300 |
| `executor_profile.py` | 原 `executor_capabilities.py`，去掉 schema 版本常量与 `__post_init__` 一致性校验 | 250 |
| `project_executor.py` | 原 `DirectProjectCodeExecutorAdapter` 的 `dispatch/adjust/settle_adjustment/cancel/status/prepare_startup/capability_profiles/construction_capability_profiles`；所有权改用 `ExecutionLedger.claim_task/renew` | 1,500 |
| `worktree_facts.py` | 原 `_DirectProjectAttemptJournal` 与 `DirectProjectManagedBaselineReader` 中 Git/worktree/patch/tree 指纹部分 | 400 |
| `importer.py` | 旧库 → 四张台账，一次性，只读旧库 | 400 |
| `db.py` | 连接、PRAGMA、事务 helper（唯一的 `sqlite3.connect`） | 120 |

- **`SqliteTaskStore` 58 个公开方法的去向**（附录 B 有行数与 caller）：

| 台账 | 方法 |
|---|---|
| `executions.py` | `create`、`create_successor`、`get_task`、`get_attempt`、`task_read_snapshot`、`list_tasks`、`list_tasks_page`、`list_task_read_snapshots_page`、`nonterminal_attempts`、`retry`、`reprioritize`、`cancel`、`update`、`adjust`、`decide_unsupported_control`、`defer_admission`、`settle_unbound_queued_attempt`、`resolve_lost_attempt`、`recover_durable_attempt`、`mark_reconciliation_pending`、`mark_reconciliation_resolved`、`read_retry_authority`、`read_current_retry_authority`、`read_applied_retry_replay`、`apply_observations`、`task_result`、`consumer_task_result`、`get_consumer_task` |
| `delivery.py` | `claim_outbox`、`renew_outbox_claim`、`complete_outbox`、`reject_outbox`、`release_outbox`、`complete_adjustment_outbox`、`reset_expired_outbox_claims` |
| `events.py` | `events`、`events_page`、`unread_events_page`、`ack_events`、`consumer_events`、`consumer_progress_authority_page`、`event_authority_snapshot`、`consumer_event_authority_snapshot`（后四个合并为 `Subscription.next_event/page`） |
| `facts.py` | `claim_durability_mutator`、`release_durability_mutator`、`append_durability_checkpoint`、`append_durability_effect_fact`、`read_durability_checkpoints`、`read_durability_effects`、`read_durability_binding`、`read_durable_recovery_dispatch`、`read_durable_recovery_authority`、`fork_durability_lineage` |
| 删除 | `read_task_durability_diagnostics`、`counts`、`has_pending_adjustments`、`admission_projection`、`get_current_background_task`（零 caller；`p3_authenticated_composition.read_current_background_task` 改查 `executions`） |

  外部 caller 改点（按附录 B）：`persistent_task_core`（全部 → 新 facade 内部）、`p3_authenticated_composition`
  （`read_applied_retry_replay/list_tasks_page/read_current_retry_authority/get_attempt/task_read_snapshot/list_tasks`）、
  `p3_production_intent_composition`（`list_task_read_snapshots_page/events_page/task_result`）、`project_code_executor`
  （5 个 durability 读方法）、`product_composition_registry`（`dispatch`）、`jiuwenswarm_agent_adapter`（`events`）。

- **durability 六文件的去向**：`D1Checkpoint`(3)、`ExternalEffect*`(2–3 each)、`EffectDispatchReceipt`(2)、
  `EffectFact`(2)、`effect_fact_bytes/from_bytes` → `facts.py` 的一个 `Fact` 记录与 codec；`verify_effect_prefix`、
  `verify_checkpoint_prefix`、`DurabilityReadBinding`、`*PrefixRow`、`Verified*Prefix` 删除（append-only 台账不需要
  prefix 校验）；`ExecutorRecoveryFacts`(3) → `Attempt.recovery` 字段；`DurabilityMutationAuthorization`(3) →
  `facts.claim_mutator` 返回值；`DurabilityProfileBinding`(8) 保留为 `facts.py` 内的记录；六个文件各自的
  `_scope/_text/_digest/_profile/_reject_duplicate_keys` 复制 helper 只在 `codec.py` 留一份。
- **步骤**：
  1. `db.py` + `executions.py` + 测试 `tests/unit_tests/live_voice/task/test_executions.py`：从旧 `test_persistent_task_core.py`
     里移植名字含 `restart`、`race`、`concurrent`、`corrupt`、`crash`、`unknown`、`cancel_before_dispatch`、`unbound` 的用例
     （`grep -n "def test_" tests/unit_tests/live_voice/test_persistent_task_core.py | grep -E "restart|race|concurrent|corrupt|crash|unknown|before_dispatch|unbound"`），
     改写为对台账 API 的断言。验证：新测试通过。
  2. `delivery.py` + 测试：移植 `claim/renew/reject/release/reset_expired` 用例；新增"死 owner → unknown，不重放"用例。
  3. `events.py` + 测试：移植 `events_page/unread/ack` 用例；`Subscription` 替代 `TaskEventSubscription` 的 live 与
     authority replay 两种模式（SC-4）。硬要求：从 cursor 起的事件流必须连续无缺口（`task_progress_return.py` 的 docstring
     写明通知仲裁需要 complete, contiguous lifecycle stream，语音进度只在这个前提下激活）；测试里加一条
     "cursor 之后追加 N 条、崩溃重启、再读到的序列连续且不重复"的用例。
  4. `facts.py` + 测试：移植 `test_p3_4_durability_store.py`、`test_durability_effects.py` 的 codec 往返与 reconcile 决策表。
  5. `core.py`：以旧 `PersistentTaskCore` 的 13 个公开方法为签名，内部改调台账；`drain_outbox/drain_outbox_once/
     read_current_retry_admission/recover_durable_attempt` 四个零 caller 方法删除。验证：
     `tests/unit_tests/agentserver/test_live_voice_p3_route.py` 与 `test_p3_authenticated_composition.py` 通过（它们经由
     composition 调用 core）。
  6. `project_executor.py` + `worktree_facts.py`：外部调用的 8 个方法保留名；`_AttemptOwnershipLock` 删除（改用
     `executions.claim_task/renew`）；`_DirectProjectAttemptJournal` 的效果记录改写 `facts.append`；`ProjectCodeExecutorAdapter`
     （legacy）与 `LegacyProjectTaskService` 删除。测试：从 `test_project_code_executor.py` 移植名字含 `direct`、`d0`、`d2`、
     `crash`、`compensat`、`baseline` 的用例（≤1,500 行），其余（legacy adapter 用例）删除。
  7. `importer.py` + 测试：用旧 `SqliteTaskStore` 在 `tests/fixtures` 里生成一个样本库（或从旧测试的 fixture 构造），
     导入后逐表比对计数与终态。旧库表名从 `task_store.py` 的 `CREATE TABLE` 语句读取（`grep -n "CREATE TABLE" task_store.py`）。
  8. 切换 caller（上表），删除 `task_store.py`、`persistent_task_core.py`、`durability_*.py`（6）、
     `task_event_subscription.py`、`task_admission.py`、`executor_capabilities.py`、`task_core.py`、`formal_task_models.py`
     shim；退役对应旧测试文件。验证：10.2 后端套件失败集 = 基线 ∪ 本包退役文件；
     `git grep -n "SqliteTaskStore\|PersistentTaskCore\|_DirectProjectAttemptJournal\|TaskEventSubscription\b"` 为零；
     `git grep -n "sqlite3.connect" jiuwenswarm/server/live_voice` 只命中 `task/db.py` 与 `task/importer.py`。
  9. 提交：`refactor(live-voice): replace the task store with four ledgers (SC-4, SC-5)`。
- **完成判据**：模块 7 ≤1,500、8 ≤4,500、9 ≤3,200、10 ≤1,000、11 的订阅部分 ≤700；模块 7–10 的守卫合计 ≤1,200；
  `anatomy_modules.py` 显示模块 8 只有一个 owner 类且 ≤900 行。
- **禁止**：在新台账里保留旧 Store 的双 verifier；importer 之外读写旧库；改 `native_*` 文件的行为。
- **回滚**：revert 提交；旧库文件不被 importer 修改，可直接回到旧 Store。

## 14. S3 授权 owner 与组合根

- **目的**：四套授权 CAS 合成一个 `AuthorizationOwner` + 一张 journal；registry 只做注册；组合根吸收 P2 lease。
- **前置**：S1 完成（可与 S2 并行；用到 Task 读取的地方先经旧 `PersistentTaskCore` 接口，S2 合入后改一次 import）。
- **输入**：`server/live_voice/p3_authenticated_composition.py`（5,435）、`production_task_intent.py`（2,004）、
  `unified_committed_input.py`（1,694）、`critical_token_safety.py`（1,397）、`product_authority.py`（1,302）、
  `task_semantics.py`（1,210）、`p3_confirmation.py`（979）、`semantic_continuity.py`（255）、`p3_model_resolution.py`（222）、
  `voice_task_bridge.py`（197）、`production_task_classifier.py`（162）、`product_composition_registry.py`（16,070）、
  `product_p2_interaction_adapter.py`（2,117）、`live_voice_configuration_declaration.py`（1,003）、
  `product_composition_root.py`（459）、`product_composition_contract.py`（424）；测试
  `test_product_composition_registry.py`（19,178）、`test_product_composition_registry_speculation.py`、
  `test_p3_authenticated_composition.py`（9,603）、`test_product_authority.py`、`test_p3_confirmation*.py`、
  `test_production_task_intent*.py`、`test_critical_token_safety*.py`、`test_unified_committed_input*.py`、
  `test_task_semantics*.py`、`test_semantic_registry.py`、`test_live_voice_configuration_declaration.py`、
  `test_product_composition_contract.py`、`test_product_p2_interaction_adapter*.py`。
- **目标结构**（新包 `jiuwenswarm/server/live_voice/authorization/`，registry 留在原文件）：

| 文件 | 内容 | 行数上限 |
|---|---|---:|
| `owner.py` | `AuthorizationOwner`：`authenticate(principal)`、`resolve_scope(project)`、`authorize(request) -> Authorization`、`issue_confirmation`、`consume_confirmation`（一次性、TTL、scope）、`clarify`；一个 `AuthorizationOutcome` 枚举（≤8 值） | 900 |
| `journal.py` | `CommittedInputJournal`（原 `SqliteUnifiedCommittedInputJournal`，保留 `complete`、`checkpoint_foreground_effect_result` 两个外部调用名；新增 `confirmations` 表；`admit/renew/read_*/consume_semantic_context` 合并为 ≤12 个方法） | 900 |
| `intent.py` | 原 `ProductionMultiTaskResolver` + `BoundedClarificationOwner` + `ProductionTaskIntentClassifier`，输出 `TaskIntent` | 800 |
| `critical_token.py` | 原 `CriticalTokenPolicy` + `CriticalTokenSafetyGate`，澄清与授权记录改调 `owner` | 500 |
| `semantics.py` | 原 `task_semantics.py`（`TaskSemanticResolver`、`TaskSemanticDecision`、`TaskSemanticContext`），`task_semantic_output_schema` 改为从 `task_records` 生成 | 900 |
| `semantic_dispatch.py` | 从 registry 抽出的 `_run_unified_submit_decided`(399)、`_dispatch_semantic_agent_turn`(133)、`_resolve_semantic_input`(48) | 500 |
| `model_resolution.py` | 原 `p3_model_resolution.py` | 200 |
| `p3_composition.py` | 原 `P3AuthenticatedComposition` 的 18 个被 registry 调用的方法（`handle_production_resolution`、`prepare_mutation_confirmation`、`resolve_production_semantics`、`read_task_control_snapshot`、`reauthorize_mutation_replay`、`prepare_product_presentation_ack`、`execute_product_presentation_ack`、`read_background_task`、`read_task_notification_facts`、`read_product_status_retry_admission`、`require_local_artifact_delegation_capability`、`read_product_unread_events`、`next_product_p2_response_generation`、`read_product_task_result`、`require_local_task_control_capability`、`handle`、`query`、`stop`）；认证与项目解析用 `owner`；删除本文件里的 Store/Core/executor 构造（改由 `composition_root` 注入） | 1,200 |
| `product_composition_root.py`（改） | 吸收 `P2ActivationLease`、六种 `_*Lease` → 一个 `RouteLease`；构造 Task core、executor、journal、owner 一次 | 400 |
| `product_composition_registry.py`（改） | 27 个 `handle_*` 保留名与签名，每个 ≤40 行：校验一次（`owner.authorize`）→ 委托给 owner/runtime；Native 的 `handle_native_*` 三个方法原样保留 | 1,500（含 Native 段约 1,000） |

- **symbol 处置**：`SqliteP3ConfirmationLedger`、`BoundedP3ConfirmationOwner`、`ProductAuthorityService`、
  `P2AuthorityAdapter`、`P3AuthorityAdapter`、`SpeechAuthorityResolverAdapter`、`ProductionConfirmationConsumer` →
  `owner.py`；`AuthorityDecisionReason`(19)、`CriticalTokenReason`(22)、`ProductionTaskPolicyOutcome`(7) →
  `AuthorizationOutcome`；`ResolvedProductAuthority`(3)、`P3AuthorityContext`(2)、`AuthorityRouteContext`(3)、
  `AuthorityResourceBinding`(2)、`P2AuthenticatedContext`(2)、`TrustedAuthorityCandidate`(2) → 一个 `Authorization`
  记录；`P3ConfirmationBinding`(5)、`VerifiedP3Confirmation`(4)、`ValidatedP3ConfirmationForwarding`(3)、
  `ProductionConfirmationBinding`(2) → 一个 `Confirmation` 记录；`semantic_continuity.SemanticContinuity` → `journal.py`
  的 `retain/consume_semantic_context`；`voice_task_bridge.VoiceTaskBridge`(1) → `intent.py`；
  `live_voice_configuration_declaration.py` 保留 `ValidatedLiveVoiceConfiguration`(2)、`LiveVoiceCapabilityDeclaration`(1)、
  `declare_live_voice_capabilities`(1) 与 5 个 capability 枚举，删除 replay 评估（`evaluate_*_replay`、
  `ConfigurationReplayResult/Reason`）；`product_composition_contract.py` 保留（3 个 caller 的 5 个值类型）。
- **步骤**：
  1. `owner.py` + `journal.py` + 测试：正负授权各一组（成功路径断言成功）；确认一次性消费的并发用例（两个线程同时
     `consume_confirmation`，恰好一个成功）；TTL 过期。验证：通过。
  2. `intent.py`、`critical_token.py`、`semantics.py`、`model_resolution.py`：搬迁，改调 owner；旧文件删除；旧测试改
     import 后运行，只删针对已删 reason 值的用例。验证：通过。
  3. `semantic_dispatch.py`：从 registry 抽出三个方法，registry 的 `handle_unified_submit` 只剩校验 + 委托。验证：
     `test_semantic_registry.py`、`test_product_composition_registry_speculation.py` 通过。
  4. `p3_composition.py`：18 个方法搬入，`create_p3_composition_from_environment` 改在 `product_composition_root.py`。
     验证：`test_p3_authenticated_composition.py`、`tests/unit_tests/agentserver/test_live_voice_p3_route.py` 通过
     （针对已删 resolver 的用例删除）。
  5. `product_composition_root.py` 吸收 lease；`product_p2_interaction_adapter.py` 删除（`P2ActivationLease` 982、
     `ProductP2InteractionAdapter` 465 → root 的 `activate_p2` ≤200）。验证：`test_product_p2_interaction_adapter*.py`
     退役，root 新测试通过。
  6. registry 瘦身：逐个 `handle_*` 改成"校验一次 → 委托"，删除每个 handler 内重复的 scope/session/principal 校验
     （grep `_require_scope\|_require_session\|_require_principal` 之类的私有校验方法，确认它们只剩 owner 调用后删除）。
     验证：`test_product_composition_registry.py` 里失败的用例逐条分类：断言拒绝 reason 的 → 删除或改为
     `AuthorizationOutcome`；断言成功路径的 → 必须通过。
  7. 提交：`refactor(live-voice): one authorization owner, one committed-input journal, registry only registers (SC-1, SC-2)`。
- **完成判据**：模块 4 ≤8,500、模块 14 ≤3,200（含 Native 段）；`anatomy_modules.py`：模块 4 owner ≤4 个、模块 14
  owner ≤2 个；`git grep -n "class .*Lease" jiuwenswarm/server/live_voice` ≤2 处。
- **禁止**：改 `handle_native_*` 的行为；改语义模型的输出 schema 字段。
- **回滚**：revert。

## 15. S4 runtime、fence、round、呈现、进度策略

- **目的**：一个 `ConversationRuntime`，一个 `ResponseFence`，一个 `RoundOwner`，一个 `PresentationLedger`，一个
  `ProgressPolicy`。
- **前置**：S1 完成；S3 的 `semantic_dispatch.py` 存在（runtime 的调用方）。
- **输入**：`server/live_voice/agent_conversation_runtime.py`（5,089）、`conversation_runtime_loop.py`（1,559）、
  `conversation_runtime.py`（686）、`interaction_engine.py`（602）、`speculative_dialogue.py`（459）、
  `agent_bridge_runtime.py`（1,240）、`jiuwenswarm_round_harness.py`（1,151）、`agent_bridge.py`（105）、
  `jiuwenswarm_agent_adapter.py`（106）、`server/runtime/agent_adapter/formal_live_voice.py`（401）、
  `formal_tool_gate.py`（75）、`presentation_ledger.py`（1,272）、`p2_response_generation_store.py`（436）、
  `formal_history_writer.py`（279）、`task_control_presentation.py`（47）、`progress_notification_arbiter.py`（2,228）、
  `task_progress_return.py`（2,291）、`product_p3_text_adapter.py`（1,207）；`live_voice_contract_v2.py` shim 里的
  owner 类；测试 `test_agent_conversation_runtime*.py`、`test_generation_time_interruption.py`、
  `test_conversation_runtime*.py`、`test_interaction_engine.py`、`test_speculative_dialogue.py`、`test_agent_bridge*.py`
  （round harness 的用例在 `test_agent_conversation_runtime.py` 与 `test_generation_time_interruption.py` 里，没有独立文件）、
  `test_presentation_*.py`、`test_task_presentation_consumption.py`、
  `test_running_notification_policy.py`、`test_task_notification_ownership.py`、`test_task_progress_return.py`、
  `test_progress_notification_arbiter*.py`、`test_product_p3_text_adapter*.py`。
- **目标结构**（新包 `jiuwenswarm/server/live_voice/conversation/`）：

| 文件 | 内容 | 行数上限 |
|---|---|---:|
| `runtime.py` | `ConversationRuntime`：合并 `AgentConversationRuntime` 与 `ConversationRuntimeLoop`；保留外部调用的方法名（下表）；turn/response/generation 状态（原 `conversation_runtime.py` 的记录）内嵌；优先级事件循环与 effect outbox 保留 | 2,000 |
| `fence.py` | `ResponseFence`：`barge_in(phase='playback')`、`interrupt_generation(phase='generation')`、`cancel_response(exact ResponseRef)`、`settle`、`snapshot`；一个 `FenceResult` 记录；吸收 `_RetainedGenerationInterrupt`、shim 里的 `ResponseFence`、`TurnCommitLedger`、`EventSequenceTracker`、`validate_transition` | 400 |
| `round.py` | `RoundOwner`：`reserve/begin_commit/commit/cancel/rollback_unstarted/abort_reservation/detach/next_delivery/submit`（原 harness + bridge runtime 两层合一，保留 `agent_conversation_runtime` 调用的这 12 个名字） | 700 |
| `presentation.py` | `PresentationLedger`（原两个 owner 合一；保留 `acknowledge/enqueue/produce/begin_response/invalidate_response/seal_surface/close_surface/presentation_complete/presented_history`）+ `SessionFormalHistoryWriter` + `next_task_presentation_event` | 700 |
| `progress_policy.py` | `ProgressPolicy`：原 `ProgressNotificationArbiter.offer/drain/acknowledge` + `TaskProgressReturnBridge.activate/drain_voice`；一个 `ProgressDecision` 枚举（≤8 值） | 1,200 |
| `text_progress.py` | 原 `product_p3_text_adapter.py` 的 `ProductP3TextAdapter` + `ProductP3ProgressCleanupHandle` | 500 |
| `speculation.py` | 原 `speculative_dialogue.py` | 350 |
| `agent_facade.py` | 原 `formal_live_voice.py`（`FormalAgentExecution` 等 4 个记录、两段 instructions）+ `jiuwenswarm_agent_adapter.py` + `InteractionEnginePort`/`InteractionAction` | 500 |
| `tool_hold.py` | 原 `formal_tool_gate.py`，改为注册到已安装 `AgentRail.before_tool_call` 的一个 element | 80 |

- **`ConversationRuntime` 必须保留的公开方法**（有外部 caller，附录 B）：`present_authoritative_text`、
  `task_presentation_runtime_authority`、`submit_committed_turn`、`execute_native_delegate`、`select_formal_context`、
  `persist_native_assistant_history`、`persist_native_user_history`、`fail_task_presentation`、`execute_native_work`、
  `acknowledge_presentation`、`commit_turn`、`presented_agent_analysis`、`interrupt_generation`、
  `task_notification_foreground_safe`、`start_turn`、`next_notification`、`barge_in`、`request_response_cancel`、
  `open_interaction`、`response_fence_state`；以及 loop 上被 `native_interaction_runtime.py` 调用的 13 个：`accept_response`、
  `transition_response`、`transition_interaction`、`commit_native_turn`、`cancel_response_if_running`、`seal_presentation`、
  `presentation_complete`、`enqueue_unit`、`produce_unit`、`barge_in`、`acknowledge_presentation`、`start_turn`、
  `open_interaction`（`grep -o -E "\.[a-z_]+\(" native_interaction_runtime.py` 复核）。`claim_effects`、`invalidate_presentation`、
  `acknowledge_presentation_with_history` 只被 runtime 自己调用，合并后成为内部方法。构造函数必须保留
  `native_business_router.py` 与 `product_composition_registry.py` 里 `AgentConversationRuntime(scope=…, instance_id=…, …)`
  用到的关键字参数；类名改为 `ConversationRuntime` 时在新模块里导出别名 `AgentConversationRuntime = ConversationRuntime`，
  Native 文件只改 import 路径。
  其余 `post_*`、`drain_notifications_for`、`attach/detach_notification_consumer`、`schedule_native_assistant_history`、
  `retry_*_history`、`accept_task_origin`、`accept_task_progress_notification`、`claim_conversation_effects`、
  `acknowledge_conversation_effects`、`begin_speculative_dialogue`、`speculation_snapshot`、
  `create_native_interaction_runtime_owner` 只要 `grep` 确认无外部 caller 就内联或删除。
- **值类型处置**：`AgentConversationRuntimeSnapshot`、`ConversationRuntimeLoopSnapshot`、`ConversationSnapshot` →
  一个 `RuntimeSnapshot`；`GenerationInterruptionFenceStatus`、`GenerationInterruptionResult`、`BargeInResult`、
  `ResponseCancelResult`、`AgentGenerationInterruption` → `FenceResult`；`AgentConversationNotification`、
  `AgentConversationNotificationLease`、`_QueuedNotification` → 一个 `Notification`；`RuntimeEvent`、`RuntimeEffect`、
  `ConversationEffect`、`EffectRecord`、`EffectState` → `Effect` + `EffectState`；harness/bridge 的
  `HarnessRoundReservation/HarnessRoundBinding/HarnessRoundSnapshot/RoundCancelResult/AgentRoundRequest/
  AgentBridgeDispatchReservation/AgentBridgeCompletion*/AgentBridgeSubmission` → `Round`、`RoundResult` 两个记录；
  `ScriptedCascadeInteractionEngine`、`CASCADE_GOLDEN_SCRIPT`、`CascadeObservation*`、`ScriptedCascadeSnapshot`、
  `AgentBridgePort`、`project_round_work_progress`、`TaskPresentationRuntimeAuthorityPort` 删除。
  `TaskProgressReturnReason`(23)、`NotificationDisposition`、`SpeechDisposition`、`NoProjectionAdvanceDisposition`、
  `TaskProgressHandoffKind`、`TaskProgressSourceDecision` → `ProgressDecision`；`ProductP3TextReason`(15) → `ErrorCode`。
- **步骤**：
  1. `fence.py` + 测试：播放期插话、生成期打断、无响应时打断、exact response 取消、重复打断幂等。验证：通过。
  2. `round.py` + 测试：reserve→commit→deliver、cancel、rollback、abort；从 `test_agent_bridge*.py`、
     `test_agent_conversation_runtime.py`（名字含 `round`、`reserve`、`harness` 的用例）移植成功路径用例。
  3. `presentation.py` + 测试：ACK 后才写历史、seal、一次性消费；移植 `test_presentation_*.py`、
     `test_task_presentation_consumption.py` 的用例。
  4. `progress_policy.py` + `text_progress.py` + 测试：通知/ACK/replay；前台忙时静默与恢复；移植
     `test_running_notification_policy.py`、`test_task_notification_ownership.py` 的用例。
  5. `runtime.py`：以保留方法表为签名合并两层；`native_interaction_runtime.py` 只改 import。验证：
     `test_generation_time_interruption.py`、`test_agent_conversation_runtime*.py` 的成功路径用例通过（改 import 后运行；
     断言已删 reason/snapshot 字段的用例删除）；`tests/unit_tests/live_voice/test_native_*.py` 全部与基线相同。
  6. 删除旧文件与 shim 里的 owner 类。三处 owner 使用点改到 `fence.py`：`conversation_runtime.py`（`TurnCommitLedger`、
     `ResponseFence`、`validate_transition`，随文件合并消失）、`agent_bridge_runtime.py`（`EventSequenceTracker`，随文件消失）、
     `agent_ws_server.py` 的 `_start_live_voice_product_composition` 里 `commit_ledger = TurnCommitLedger()`（改为
     `ResponseFence`/`ConversationRuntime` 提供的 commit 记录）。`live_voice_contract_v2.py` 若只剩 re-export 则删除并把 caller
     改到新包（`grep -rln "live_voice_contract_v2" jiuwenswarm` 逐个改）。验证：后端套件失败集 = 基线 ∪ 退役文件。
  7. 提交：`refactor(live-voice): one conversation runtime, one response fence, one round owner (SC-3)`。
- **完成判据**：模块 5 ≤4,000、6 ≤1,300、12 ≤1,800、11 的策略部分 ≤1,700；模块 5 只有 1 个 owner 类，守卫 ≤500；
  `git grep -n "class .*Fence\|class .*Ledger" jiuwenswarm/server/live_voice` 各 ≤1 处。
- **禁止**：改 `native_interaction_runtime.py` 的逻辑（只改 import）；改 D-115 的历史写入时机。
- **回滚**：revert。

## 16. S5 媒体与 provider

- **目的**：一个 `MediaSession`、一个 `RouteLifecycle`、一个 `SpeechProvider` 合同；删除 conformance 与三套 route 生命周期。
- **前置**：S1、S4 完成（route 通过 runtime 的 `barge_in/acknowledge_presentation`）。
- **输入**：`gateway/live_voice/dedicated_media_registration.py`（8,427）、`streaming_synthesis_route.py`（2,449）、
  `dedicated_media_route.py`（1,869）、`streaming_speech_route.py`（1,536）、`browser_gateway_media_transport.py`（1,437）、
  `task_notification_preparation.py`（327）、`product_streaming_synthesis.py`（212）、`speech_rpc.py`（142）、
  `server/live_voice/openai_streaming_speech.py`（2,921）、`batch_speech.py`（2,745）、`streaming_speech.py`（2,230）、
  `speech_ports.py`（477）；前端 `browserGatewayMediaTransport.ts`（1,642）、`browserDedicatedMediaRoute.ts`（1,442）、
  `gatewayBatchSpeechClient.ts`（1,431）；测试 `tests/unit_tests/gateway/test_dedicated_media_registration.py`、
  `test_dedicated_live_voice_media_route.py`、`test_browser_gateway_media_transport.py`、`test_streaming_speech_route.py`
  （3,202）、`test_product_streaming_synthesis.py`、`test_task_notification_preparation.py`、
  `tests/unit_tests/live_voice/test_openai_streaming_speech.py`、`test_batch_speech*.py`、`test_streaming_speech*.py`、
  `test_speech_lifecycle.py`、`test_speech_precision_diagnostics.py`；前端 `liveVoiceBrowserGatewayMediaTransport.test.mjs`、
  `liveVoiceBrowserDedicatedMediaRoute.test.mjs`、`liveVoiceGatewayBatchSpeech.test.mjs`。
- **目标结构**：

| 文件 | 内容 | 行数上限 |
|---|---|---:|
| `gateway/live_voice/media/session.py` | `MediaSession`：原 registry 的注册/票据/authority/downlink 分配/ACK 转发/通知准备；保留外部调用名 `activate`、`authorize`、`revoke`、`observe_agent_response`、`try_streaming_synthesis`、`configure_streaming_synthesis`、`configure_streaming_recognition`、`from_environment`、`set_provider_available`；吸收 `task_notification_preparation.py` | 1,800 |
| `gateway/live_voice/media/native_segment.py` | `NativeMediaMixin`：registry 里名字含 `native` 的 54 个方法（15 个公开 + 39 个私有）与 `_NativeMediaSession`、`_NativePlayoutReplay`、`_NativeNotificationSequenceFence` 原样搬入，作为 `MediaSession` 的 mixin 基类；它们引用 65 个 `self._*` 字段，这些字段仍由 `MediaSession.__init__` 初始化，名字不改 | 原样（约 1,500） |
| `gateway/live_voice/media/route_lifecycle.py` | `RouteLifecycle`：`begin/offer/finish/abort/wait_speech_start/wait_end_of_turn/next_chunk/cancel/available/close`，三条 route 共用；原 `StreamingRecognitionRouteOwner`、`StreamingSynthesisRouteOwner`、`run_dedicated_media_socket_leaf`、`run_dedicated_media_downlink_socket_leaf`、`DedicatedMediaLeafCleanupOwner`、`ProductStreamingSynthesisSource` | 1,200 |
| `gateway/live_voice/media/codec.py` | `LVM1` 帧：`encode_audio_frame/decode_audio_frame/serialize_media_control/deserialize_media_control`、`MediaFrameFormat`、`MediaAudioFrame` | 400 |
| `gateway/live_voice/media/control.py` | 六个控制对象 `MediaAttach/MediaAck/MediaDetach/MediaSpeechStart/MediaEndOfTurn/MediaPlaybackStop` + `MediaAuthorityBinding` + `MediaDetachReason`（6 值） | 250 |
| `gateway/live_voice/media/rpc.py` | 原 `speech_rpc.py` + `register_dedicated_media_rpc_handlers` + `handle_registered_media_socket` | 300 |
| `server/live_voice/speech/provider.py` | `SpeechProvider` ABC（`recognize/stream_recognize/synthesize/stream_synthesize/capability/close`）、`Capability`、`Fallback` 枚举（≤8）、注册表 | 300 |
| `server/live_voice/speech/openai_batch.py` | 原 `FormalBatchSpeechService` 的 `recognize/synthesize/cancel/capability_payload` + `OpenAICompatibleBatchSpeechProvider` | 900 |
| `server/live_voice/speech/openai_streaming.py` | 原 `OpenAIStreamingSpeechProvider` 的 9 个外部调用方法；传输对象自带 `aclose()`；一个 fallback 记录 | 900 |
| `server/live_voice/speech/ports.py` | 原 `speech_ports.py` 的 `RecognitionPort`、`SynthesisPort`、`RecognitionHypothesis`、`RecognitionEventKind`、`SynthesisEventKind`、`ProviderRef`、`SpeechMode`（5 个值类型） | 200 |
| 前端 `adapters/browserGatewayMediaTransport.ts` | `BrowserGatewayMediaRegistrationOwner` + `BoundedMediaSender` + `StrictMediaReceiver` + codec；类型改为 `generated.ts` | 600 |
| 前端 `adapters/browserDedicatedMediaRoute.ts` | `BrowserDedicatedMediaSocketLeaf` + `createBrowserDedicatedMediaRoute` | 700 |
| 前端 `gatewayBatchSpeechClient.ts` | `GatewayBatchSpeechClient` + 6 个类型 | 800 |

- **`DedicatedMediaProductRegistry` 55 个公开方法的去向**：保留名并搬入 `session.py`：上面 9 个外部调用方法；
  搬入 `route_lifecycle.py`：`start_streaming_recognition`、`accept_streaming_frame`、`finish_streaming_recognition`、
  `abort_streaming_recognition`、`begin_streaming_recognition`、`wait_streaming_speech_start`、`wait_streaming_end_of_turn`、
  `streaming_recognition_result`、`prepare_streaming_provider`、`prepare_synthesis_downlink`、`complete_downlink`、
  `mark_downlink_started`、`accept_frame`、`observe_uplink_frame_accepted`、`observe_uplink_ack_sent`、`complete_route`、
  `abort_route`、`context_for`、`consume_ticket`；搬入 `session.py` 的通知准备：`prepare_task_notification`、
  `claim_task_notification`、`cancel_task_notification`、`task_preparation_capabilities`、`acknowledge_playout`；
  搬入 `native_segment.py`（mixin）：`acknowledge_native_playout`、`take_native_notification_response`、`accept_native_playback_stop`、
  `stop_native_playout`、`mark_native_notification_forwarded`、`accept_native_frame`、`begin_native_interaction`、
  `read_native_text`、`close_native_interaction`、`wait_native_speech_start`、`wait_native_end_of_turn`、
  `abort_native_activation`、`take_native_notification`、`next_native_notification`、`native_runtime_client` 与全部
  `_*native*` 私有方法（用 `grep -n "def .*native" dedicated_media_registration.py` 取完整清单）；删除：
  `close_streaming_diagnostics`、`close_streaming_observability`、`streaming_observability`、`streaming_diagnostics_cleanup_complete`、
  `retry_media_leaf_cleanup`、`close_media_leaf_cleanup`、`media_leaf_cleanup_snapshot`（诊断归 S7 sink；leaf cleanup 归
  `RouteLifecycle.close`）。
- **值类型处置**：`browser_gateway_media_transport.py` 41 个公开 symbol 保留 `MediaAuthorityBinding`、`MediaAudioFrame`、
  `MediaFrameFormat`、`MediaAttach/MediaAck/MediaDetach/MediaSpeechStart/MediaEndOfTurn`、`MediaPlaybackStopReceipt`
  （改名 `MediaPlaybackStop`）、`MediaDetachReason`（27 → 6：`local_close, remote_close, transport_failed, sequence_error,
  authority_revoked, timeout`）、`MediaDirection`、`MediaGenerationKind`、codec 四函数；删除 `MediaCapability`、
  `MediaActivationRequest`、`ActiveMediaActivation`、`InactiveMediaActivation`、`MediaDrainResult`、`MediaEnqueueResult`、
  `MediaCloseResult`、`MediaPlaybackStopOutcome`、`MediaGenerationBinding`、`MediaPlayoutBinding`、`BinarySendDisposition`、
  `create_gateway_media_activation`、`create_playback_stop_receipt`、`validate_playback_stop_receipt`、`MediaControl`、
  `MediaActivation`、5 个常量。`streaming_speech.py` 的 `StreamingSpeechConformance`、`SpeechStreamAuthority`、
  `SpeechResponseAuthority`、`require_stream_authority`、`authorize_stream_request` 与 27 个值类型全部删除，
  `StreamingProviderCapability` + `RecognitionProviderSupport` + `SynthesisProviderSupport` + `speech_ports.SpeechCapability`
  + `batch_speech.ProviderCapability` → `provider.Capability`；`SpeechDegradationReason`(11) + `SpeechDegradationFact` +
  `TransportCleanupSnapshot` + `StreamingSynthesisReason`(14) + `StreamingSynthesisFallbackAction` +
  `DedicatedMediaRouteReason`(8) → `provider.Fallback`（≤8 值）+ `ErrorCode`；`batch_speech.py` 的 40 个无外部 caller 常量
  → 一个 `Limits` 记录。
- **步骤**：
  1. `speech/provider.py` + `ports.py` + 测试（注册、能力探测、`Fallback` 映射）。
  2. `openai_batch.py`、`openai_streaming.py`：搬迁保留方法；删除 conformance 与 cleanup owner；测试从
     `test_openai_streaming_speech.py`、`test_batch_speech*.py` 移植成功路径与 TEXT 降级用例。验证：通过。
  3. `media/codec.py`、`control.py`：搬迁 + 字节等价测试（现有 `test_browser_gateway_media_transport.py` 的帧 fixture）。
  4. `route_lifecycle.py` + 测试：attach→frames→end→ack→detach 一套用例三条 route 各跑一次；reconnect、backpressure、
     ACK 失配重同步各一条。
  5. `session.py` + `native_segment.py` + `rpc.py`：从 `dedicated_media_registration.py` 搬出；`app_web_handlers.py`、
     `web_connect.py`、`product_composition_registry.py` 的 import 改到新包。验证：`test_dedicated_media_registration.py`
     的成功路径用例通过；`tests/unit_tests/gateway/test_native_*.py` 与基线相同。
  6. 前端三文件重写，类型改用 `generated.ts`；`test:live-voice-browser-gateway-media`、`test:live-voice-browser-dedicated-media`、
     `test:live-voice-gateway-batch-speech` 的用例按本包 SC 分类后通过。
  7. 删除旧文件与旧测试；提交：`refactor(live-voice): one media session, one route lifecycle, one speech provider contract (SC-8)`。
- **完成判据**：模块 2 ≤6,500（含 `native_segment.py`）、模块 3 ≤5,000；模块 2 owner ≤3、模块 3 owner ≤2；
  `git grep -n "Conformance" jiuwenswarm/server/live_voice` 为零。
- **禁止**：改 `native_segment.py` 的逻辑；改 `LVM1` 帧格式。
- **回滚**：revert。

## 17. S6 前端

- **目的**：一个 `AudioEdge`，三个 owner hook，一个 TaskUi，一本 journal，legacy 退休。
- **前置**：S1（`generated.ts`）、S5（媒体 TS 三文件）完成；§7.3 决定为"是"。
- **输入**：模块 1（`productP1VoiceRoute.ts` 4,408、`browserAudioIOAdapter.ts` 3,088、`browserAudioDeviceSelection.ts` 534、
  `browserLiveVoiceOwnership.ts` 426、`audioPort.ts` 364、`liveVoiceCaptureProcessor.js` 203）、模块 13
  （`LiveVoiceIntegratedRoutePanel.tsx` 9,814、`productWebActivation.ts` 2,223、`productP2ActivationJournal.ts` 1,314、
  `formalP3TaskExperience.ts` 972、`formalTaskControlLeaf.ts` 952、`integratedWebRouteShell.ts` 587、
  `productP3ProgressGenerationJournal.ts` 236、`productP3TaskTargetJournal.ts` 148、`useProductVoiceSessionStart.ts` 99、
  `RecentTasksPanel.tsx` 70、`createLiveVoiceConversation.ts` 55、`taskNotificationIdentity.ts` 47）、模块 11 的
  `productTextProgress.ts` 870、模块 17 全部、`components/ChatPanel/index.tsx` 的 legacy 段（用
  `grep -n "useLiveVoiceDemo\|LiveVoiceDemoBar\|FEATURE_LIVE_VOICE_DEMO\|legacyLiveVoiceDemoProps" index.tsx` 定位：import、
  `useLiveVoiceDemo(` 构造、`<LiveVoiceDemoBar {...legacyLiveVoiceDemoProps} />`、两处 `FEATURE_LIVE_VOICE_DEMO && liveVoiceDemoBar`）、`src/featureFlags.ts` 的 `FEATURE_LIVE_VOICE_DEMO`、`package.json` 的
  `test:live-voice-core/-turn-lifecycle/-streaming-speech/-message-gate/-browser-speech-adapters` 与对应 `tests/*.test.mjs`。
- **目标结构**（`features/live-voice/`）：

| 文件 | 内容 | 行数上限 |
|---|---|---:|
| `audio/audioEdge.ts` | `AudioEdge`：capture（含 worklet 加载）、playout（含 receipt）、device、ownership；事件 `captured/played/device_changed/ownership_changed/failed/level`；`mapAudioFailure` 五类 | 1,600 |
| `audio/captureProcessor.js` | 原 worklet | 203 |
| `audio/nearEndCandidate.ts` | 原 `browserAudioIOAdapter.ts` 里的 verified-headset 近端插话候选（RMS/峰值/回声相似度） | 400 |
| `session/useP1Owner.ts` | 原 `productP1VoiceRoute.ts` 的 P1 owner（capture→recognition→commit）；Native activation 解析原样搬到 `session/nativeActivation.ts`（不改） | 500 |
| `session/useP2Owner.ts` | 原 Panel 与 `productWebActivation.ts` 的 P2 activation/notification/presentation-ack 段 | 500 |
| `session/useP3Owner.ts` | 原 Panel 的 P3 progress/mutation 段 + `formalP3TaskExperience` 的选择逻辑 | 500 |
| `session/notificationArbitration.ts` | 纯函数：`classifyProductP2Notification` 与 Panel 里 `terminalTextFallback*`、`capturedTaskNotification*`、`productP2Notification*`、`progressMatchesOwnedBinding`、`isCurrentProgressOwner` 等 13 个函数 | 350 |
| `session/taskUi.ts` | 原 `formalTaskControlLeaf.ts` + `formalP3TaskExperience.ts` 一个 owner | 900 |
| `session/durableOperationClient.ts` | 原 `productWebActivation.ts` 的 `ProductWebP2ActivationOwner/ProductWebP3ProgressOwner/ProductWebP3MutationOwner` 合一 | 800 |
| `session/activationJournal.ts` | 原三本 journal 合一 | 500 |
| `session/textProgress.ts` | 原 `productTextProgress.ts` | 300 |
| `components/ChatPanel/LiveVoicePanel.tsx` | 原 `LiveVoiceIntegratedRoutePanelView` + 状态显示；不再持有 owner 逻辑 | 1,200 |
| `errors.ts` | `LiveVoiceError` + 18 个码的文案表（S0 的表） | 120 |

- **处置**：`browserAudioIOAdapter.ts` 的 41 个 `*Like`/事件类型 → `audioEdge.ts` 内部的一个 `BrowserAudioEnvironment`
  类型；`ProductP1*Diagnostics` 三个类型与 `audioDiagnostics` 调用 → S7 的前端 sink；`integratedWebRouteShell.ts` 的
  `IntegratedWebRouteShell` 与 registry → `session/index.ts` 的一个 `createLiveVoiceSession`；`useProductVoiceSessionStart.ts`、
  `createLiveVoiceConversation.ts`、`taskNotificationIdentity.ts`、`RecentTasksPanel.tsx` 保留（≤300 合计）。
  模块 17 全部删除，`LiveVoiceDemoBar.tsx` 只保留 `FormalProductLiveVoiceDemoBar` 与其 props（≤120 行），
  `ChatPanel/index.tsx` 删除 `useLiveVoiceDemo` 构造与 `FEATURE_LIVE_VOICE_DEMO` 分支。
- **步骤**：
  1. `errors.ts`、`audio/*` + 测试（`test:live-voice-audio-edge` 新脚本：capture/playout/ownership 三条成功路径、设备切换）。
     验证：新脚本通过；`test:live-voice-browser-audio-io`、`-audio-port`、`-device-selection` 的用例分类后退役。
  2. `session/notificationArbitration.ts` + 表驱动测试（从 `test:task-notification-*` 与 Panel 内联用例移植）。
  3. `session/taskUi.ts`、`durableOperationClient.ts`、`activationJournal.ts`、`textProgress.ts` + mounted 测试；
     `test:live-voice-integrated-web`、`-p2-notification-ab` 的用例分类。
  4. 三个 owner hook + `LiveVoicePanel.tsx`；`ChatPanel/index.tsx` 改为只构造 `createLiveVoiceSession`。验证：
     `npm run build:live-voice` 与普通 `npm run build` 都通过。
  5. legacy 退休：删除模块 17 文件、`FEATURE_LIVE_VOICE_DEMO`、五个 `test:*` 脚本与其测试。验证：
     `git grep -n "useLiveVoiceDemo\|FEATURE_LIVE_VOICE_DEMO\|liveVoiceCore\b" jiuwenswarm` 为零；普通 build 不再包含
     legacy bar（`grep -c "LiveVoiceDemoBar" dist/assets/*.js` 为 0）。
  6. 物理 journey（`scripts/live_voice/start_hands_free_demo.ps1`）与合成语音 journey 跑通。
  7. 提交：`refactor(live-voice): audio edge, session owner hooks, one task ui, legacy retirement (SC-9, SC-10)`。
- **完成判据**：模块 1 ≤5,000、13 ≤7,000、17 = 0；`anatomy_modules.py` 前端 `throw` ≤150、类型声明 ≤400 行手写。
- **禁止**：改 `session/nativeActivation.ts` 的逻辑；改 LVM1 帧处理。
- **回滚**：revert。

## 18. S7 观测

- **目的**：退休旧 OTel 产品实现与 S7 探针工具，三通道合一个 sink，L0 测量出生产树；第一版不提供外部导出（D-122）。
- **前置**：D-122 决定一；退休前检查 1–4 已逐项记录结果；四类性质（隐私 canary、有界与溢出、关闭排空、观测失败
  隔离）在新实现上各有指名测试。
- **输入**：`server/live_voice/product_observability_runtime.py`（1,425）、`product_observability_adapter.py`（847）、
  `observability_correlation_contract.py`（876）、`observability_otel_codec.py`（641）、`observability_exporter.py`（734）、
  `observability.py`（1,960）、`latency_measurement.py`（1,972）、`alpha_benchmark.py`（633）、`alpha_privacy_conformance.py`
  （1,025）、`observability_fault_harness.py`（391）、`channels/web/live_voice_deployment_observer.py`（1,045）、
  `live_voice_deployment_preflight.py`（449）、`common/live_voice_profiling.py`（226）、`live_voice_audio_diagnostics.py`（182）、
  `speech_http_diagnostics.py`（63）、`speech_socket_diagnostics.py`（210）、`agent_adapter/formal_model_diagnostics.py`（320）、
  `scripts/live_voice/s7_*.py`（7 个，3,479）、`scripts/live_voice/l0_*.py`；前端 `liveVoiceObservability.ts`（1,598）、
  `liveVoiceRouteTelemetry.ts`（257）、`audioDiagnostics.ts`（371）、`audioDiagnosticJournal.ts`（109）、
  `webPlatformDiagnostics.ts`（326）、`l0Measurement.ts`（390）、`l0OrdinaryChromeBatch.ts`（645）、
  `L0OrdinaryChromeBatchPanel.tsx`（105）；`agent_ws_server.py` 里 `_start_live_voice_product_composition` 内的观测启动块
  （`observability_enabled`…`observability_runtime.close()`）与使用 `ProductDiagnosticIdentity/ProductDiagnosticSeam` 的方法
  （`grep -n "ProductDiagnostic" agent_ws_server.py`）；
  registry 的 `consume_product_observation/consume_product_metric`、`_observability_runtime`、
  `activate_product_observability_adapter` 调用；测试 `test_observability*.py`、`test_product_observability_*.py`、
  `test_latency_measurement.py`、`test_alpha_benchmark.py`、`test_s7_alpha_verification.py`、`test_s7_real_probes.py`、
  `tests/unit_tests/channel/test_live_voice_deployment_*.py`、`test_live_voice_retirement_manifest.py` 与
  `tests/fixtures/live_voice_retirement_manifest_v1/manifest.json`。
- **目标结构**：

| 文件 | 内容 | 行数上限 |
|---|---|---:|
| `server/live_voice/observability/observation.py` | `LiveVoiceObservation`(8 callers)、`LiveVoiceMetric`(8)、`TraceBinding`、`RouteDescriptor`、`create_observation/create_metric/create_route_descriptor/create_trace_binding`、`contains_private_observability_content`(6)、`validate_observability_timestamp`；删除 `EVENT_SEMANTIC_MATRIX`、`METRIC_SEMANTIC_MATRIX`、`*_MATRIX`、`LiveVoiceObservabilityCollector`、`observation_from_task_*`、`create_queue_metric` | 700 |
| `server/live_voice/observability/sink.py` | 一个 `DiagnosticSink`：JSONL 文件 + 回调；吸收 `live_voice_audio_diagnostics.record_audio_diagnostic`(9)、`live_voice_profiling` 的 `profiled/ProfileSpan/identity_fields/error_fields/profile_*`(20 个 importer)、`speech_http_diagnostics`、`speech_socket_diagnostics`、`formal_model_diagnostics` | 500 |
| `scripts/live_voice/l0/latency_measurement.py` | 原文件整体搬出生产树；生产里的三处调用（`dedicated_media_registration`/S5 后的 `media/session.py`、`agent_bridge_runtime`/S4 后的 `round.py`、registry）改为向 `sink` 发一条 `l0_milestone` 事件 | 原样 |
| 前端 `observability.ts` | `createObservation` + `LiveVoiceObservation/TraceBinding/RouteDescriptor` 类型（由 `generated.ts`）+ `createRouteTelemetryRecord` | 300 |
| 前端 `diagnosticsSink.ts` | 原 `audioDiagnostics.ts` + `audioDiagnosticJournal.ts` + `webPlatformDiagnostics.ts` 的一个 sink | 400 |
| `scripts/live_voice/l0/` | `l0Measurement.ts`、`l0OrdinaryChromeBatch.ts`、`L0OrdinaryChromeBatchPanel.tsx` 与 `scripts/live_voice/l0_*.py` 一起搬出生产树（按总计划 §7.6 的决定；若决定保留面板则只搬 `.py` 与 `l0Measurement.ts`） | 原样 |

- **步骤**：
  1. 退休 OTel 链：删除五个文件与其五个测试文件；`agent_ws_server.py` 删除 `_start_live_voice_product_composition` 里的
     观测启动块（从 `observability_enabled = …` 到 `observability_runtime = None` 的 try/except 整块）与 `ProductDiagnostic*`
     的 import 及其使用（改为不注入 `observability_runtime`）；registry 删除 `consume_product_observation/consume_product_metric`、
     `_observability_runtime` 字段与 `activate_product_observability_adapter` 调用及 `observability_holder`；
     `ProductDiagnosticSeam/ProductDiagnosticIdentity` 的三处使用改为 `sink.emit`。验证：
     `git grep -n "product_observability\|observability_exporter\|observability_otel_codec\|observability_correlation_contract" jiuwenswarm tests` 为零；
     `test_product_composition_registry.py` 与 `test_live_voice_p3_route.py` 通过（针对观测 runtime 的用例删除）。
  2. 退休 S7 工具与 Alpha 支持：删除 `scripts/live_voice/s7_*.py`（7）、`alpha_benchmark.py`、`alpha_privacy_conformance.py`、
     `observability_fault_harness.py`、`live_voice_deployment_observer.py`、`live_voice_deployment_preflight.py` 与它们的测试；
     `tests/fixtures/live_voice_retirement_manifest_v1/manifest.json` 的 `retired_s7_s8_runners` 条目：把
     `current_disposition` 改为该 fixture 里已退休条目使用的值（先 `grep -n "current_disposition" manifest.json | sort | uniq -c`
     看已有取值），使 `test_live_voice_retirement_manifest.py` 的"已退休路径不存在且存在于 `b2_execution_baseline`"断言成立。
     验证：该测试通过。
  3. `observation.py` + `sink.py`：搬迁保留 symbol；20 个 `live_voice_profiling` importer 与 9 个 `record_audio_diagnostic`
     caller 改 import；隐私 canary 测试（合成秘密与音频字节喂给 sink，断言零泄露）。验证：通过；
     `python scripts/live_voice/analyze_demo_profile.py` 仍能解析 sink 产出的 JSONL（用一次本地 demo 的输出验证）。
  4. L0 出树：搬文件，改三处调用。验证：`git grep -n "latency_measurement" jiuwenswarm` 为零。
  5. 前端两个文件重写；`test:live-voice-observability`、`-route-telemetry`、`-audio-diagnostics`、`-l0-*` 脚本按决定退役或改路径。
  6. 提交：`refactor(live-voice): retire the product OTel chain and S7 tooling, one diagnostic sink (SC-6)`。
- **完成判据**：模块 15 ≤3,200；`anatomy_modules.py` 模块 15 异常类型 ≤2、值类型 ≤12。
- **禁止**：删除 `contains_private_observability_content` 的任何检查项；把音频字节写进 sink。
- **回滚**：revert。

## 19. S8 验收与计量

1. 运行 10.2 的全部命令；失败集必须等于 S0 基线失败集减去已退役的文件（记录在每包提交说明里）。
2. `module_buckets.py --rev HEAD`：18 模块合计在 48,100–65,000 之间；`anatomy_modules.py`：值类型 ≤150、异常 ≤12、
   守卫 ≤4,000、owner ≤30、`throw` ≤150；任一超标，回到对应包补做，不得用"移到别处"满足。
3. `symbol_inventory.py --rev HEAD`：公开 symbol 里 `callers = 0 且 文件内引用 = 0` 的项 ≤10 个。
4. 物理 demo journey（`start_hands_free_demo.ps1`）、formal web 验证（`start_formal_web_validation.cmd`）、合成语音 journey
   三者 PASS，证据存 `live-voice/slimming/S8_EVIDENCE.md`。
5. 独立评审：另一个执行者按本文第二部分逐卡核对完成判据，不看提交说明只看代码与测试。
6. 更新 `live-voice/STATUS.md`、`README.md`、总计划 §1.4/§3 的数字；提交 `docs(live-voice): design-simplification acceptance`。

# 第三部分 附录

- 附录 A：[逐文件 symbol 清单](LIVEVOICE_DESIGN_SIMPLIFICATION_INVENTORY_2026-09-07.md)（自动生成；每个文件的顶层 symbol、
  行数、其他生产文件的调用数、本文件内引用数、调用方示例）。
- 附录 B：[巨型 owner 类方法图](LIVEVOICE_DESIGN_SIMPLIFICATION_METHOD_MAP_2026-09-07.md)（自动生成；20 个类的每个方法、
  行数、外部调用文件数）。
- 两者在每包结束后重新生成并随包提交；执行卡里的 caller 数以生成时的 HEAD 为准。
