# OpenJiuwen LiveVoice 当前分支重分析与瘦身计划更新 — 2026-09-05

> 状态：Integration Owner 的当前计划（文档-only 批次；root `TESTING.md` Live Voice risk
> tiers 与 D-046 的 Tier 0 口径）。基线是 `hx/0812_live_voice_w3@076065f1b`，其生产代码（`jiuwenswarm/` 下的
> py/ts/tsx/js）与 `ebd2b4575` 逐字节相同；执行分支 `hx/0905_livevoice_refactor` 已 rebase 到该 tip。
> 本文修订同日[计划重适配](OPENJIUWEN_LIVEVOICE_SLIMMING_PLAN_REFIT_2026-09-05.md)
> 的 §3 规划区间与 §4 实施包：只列变化的行与包，未列出的继续以重适配为准；事实基线仍是同日
> [激活预检](OPENJIUWEN_LIVEVOICE_SLIMMING_ACTIVATION_PRECHECK_2026-09-05.md)。
> 本文只分析与规划：不迁移、不删代码、不实现 AgentCore 能力、不更新远端；§7 的决定
> 仍由用户作出。

## 1. 结论先行

1. **AgentCore 下沉范围不变，合同更精确。** 新增代码里没有任何新的通用 Task /
   Event / Execution / Effect truth；仍是 K1–K4 四个事务能力族、F1–F6 六个最小 seam，
   规划中心约 5,300、区间约 3,600–8,100 不变。新增代码把四个 invariant 写得更具体：
   F2 的 claim 续约必须校验完整 binding，F1/F4 的“已选定但未绑定 Executor 的 Attempt
   是队列工作而非状态不确定”，F4 的 settlement fence 必须独立于不合作的 delivery，并在 Executor close 之后、
   释放 binding 之前 drain，F6 需要“某资源最近一次已结算效果”的读端口。
2. **留在 jiuwenswarm 的 LiveVoice 部分要改四处结构判断。** (i) Native engine /
   session / contract / carrier 放在 `server/live_voice/` 却由 Gateway 进程实例化并被
   Gateway 导入，是层级倒置：contract/carrier 应进 canonical schema，engine/session 应进
   Gateway provider 层；(ii) `dedicated_media_registration.py` 因 Native 增加了 47 个 symbol、
   约 2,300 行（整文件净增 2,965），registry 增加了约 1,500 行 Native handler，两者的拆分从“结构债务”升为
   第一优先结构包；(iii) 观测现在有三条并行通道（OTel adapter/runtime/exporter、被动
   profiling JSONL、audio diagnostics JSONL），后端约 8,100 行、前端约 2,600 行，需要收敛到
   一个 exporter 加隐私投影，且可适配复用已安装 AgentCore 的 tracer；(iv) 回答的 fence
   现在有三套（播放期插话、生成期打断、Native barge/fence），要收敛成 ConversationRuntimeLoop
   里的一个 response fence 状态机。
3. **tool-pause seam 的建议是 JIUWEN_KEEP，不是 F4。** 它是进程本地、无重启语义的
   rail 门，已安装的 AgentRail 已有 `before_tool_call` 钩子；当前“进程本地 gate 注册表 +
   rail pause event”两处实现应收敛为一个 Jiuwen rail element，不需要 AgentCore 改动。
4. **新代码已经自然完成了一部分退休：** demo bypass 环境开关、关键词/正则分类器、Alpha
   意图启发式、`FEATURE_LIVE_VOICE_TASK_DEMO` 都已从生产源码消失（后者仍被 2 个前端测试与 2 个脚本引用）；剩余零生产 importer 集群约
   9,450 行（A1），legacy 活跃集群约 3,209 行（D1）。
5. **规划区间小幅内部重分配：** Native 行中心 4,500 → 3,800（contract/carrier 归 Schema
   行），18 模块中心约 54,200、区间约 43,400–68,000；相对当前约 187K 仍是约 −70%。
6. 执行分支已 rebase 到本文写作时的特性分支 tip；该 tip 仍在以 docs/launcher 提交前进，
   A0 的冻结点应取激活时的实际 tip。demo 期可开工的 A 期包不变（A0–A3），B 期结构包按
   §6 重排为 B2a–B2e 并新增 B4 观测收敛。

## 2. 基线与 Git

| 对象 | 事实 |
|---|---|
| 特性分支 | `hx/0812_live_voice_w3@076065f1b`（2026-09-05 09:44 +0200）；`ebd2b4575..076065f1b` 没有 `jiuwenswarm/` 下 py/ts/tsx/js 的改动，只有文档、包内 skill 资源、launcher 脚本及其测试；新增 D-114（受控 Formal 生成期打断默认开启）；STATUS 仍为 PARTIAL，HUMAN_PHYSICAL_ACCEPTANCE 仍 FAIL / INCOMPLETE |
| 执行分支 | `hx/0905_livevoice_refactor` = `076065f1b` + 预检、重适配、本文三个 docs 提交，无 upstream，未推送 |
| 用户主检出 | `hx/0812_live_voice_w3` 相对 `agtai` ahead 5，仍是用户并发工作，本文不纳入 |
| AgentCore 锁定 | `openjiuwen 0.1.16@94e10cb6`；已安装包 `agent_teams` 与 `core` 中整词 `outbox` 零命中，`lease` / `cursor` / `settle` 的命中只是数据库 `cursor()` 与文档串里的 settle，没有 Task outbox / claim lease / consumer cursor 的公开合同；F1–F6 缺口结论未变 |
| 新增代码计量 | 27 个专属生产路径 11,455 行；热点文件内部新增 symbol：registry +33、`dedicated_media_registration.py` +47、`agent_conversation_runtime.py` +20、`p3_authenticated_composition.py` +16、`unified_committed_input.py` +14、`streaming_speech.py` +15、`conversation_runtime_loop.py` +13 |

## 3. 新增代码逐组分析

下表的“处置”用用户指定的五个执行码，“层”用五层归属。“发现”是本轮阅读新增
代码得到的、影响计划的结构事实。

### 3.1 Native Interaction（D-101–D-103，新增 7,758 行 + 后端热点文件内约 3,800 行 + 前端约 700 行）

| 模块 | LOC | 责任 | 实际进程 / 层 | 处置 | 发现 |
|---|---:|---|---|---|---|
| `server/live_voice/openai_realtime_session.py` | 1,073 | 一条官方 Realtime WebSocket 的唯一生命周期 owner：握手、事件序列、唯一 close、cleanup owner | Gateway / L2 provider transport | `JIUWEN_KEEP`，迁到 Gateway provider 目录 | 无 jiuwenswarm 依赖，可整体移动；吸收了 AR-157 的 `RealtimeSocket` |
| `server/live_voice/openai_realtime_native_engine.py` | 2,350 | Provider 事件 → 有界 proposal 的映射；response/audio item 簿记；delegate 结果回送 | Gateway（`app_web_handlers.py:1678` 实例化）/ L1–L2 | `JIUWEN_KEEP`，`SPLIT_REQUIRED`（事件映射 vs response/audio 簿记） | 单类 1,747 行、45 个方法；复用 `interaction_engine.InteractionAction` 端口，证明该端口是 Cascade/Native 共用 seam |
| `server/live_voice/native_interaction_contract.py` | 852 | 闭合值：binding、audio observation、turn commit、input transcript、delegate proposal、presentation cursor、replay ledger | Gateway 与 AgentServer 共用 / schema | `JIUWEN_KEEP`，归 Schema/protocol 行，进 canonical source | `NativeContractLedger` 是第二个 replay/conflict fence，与 PresentationLedger 平行 |
| `server/live_voice/native_interaction_carrier.py` | 507 | Gateway→AgentServer 的 JSON carrier（不含 PCM） | 共用 / schema | 同上 | 与 contract 一起构成第三套 Python schema 家族 |
| `server/live_voice/native_interaction_runtime.py` | 1,485 | `NativeInteractionRuntimeOwner`：唯一把 Native proposal 变成 Runtime 写入的 adapter；audio admission、delegate admission、history reconcile、barge/fence | AgentServer / L1 | `JIUWEN_KEEP` | 自带 `barge_in` / `fence_response`，与 `ConversationRuntimeLoop.interrupt_generation` 和播放期插话构成三套 fence |
| `gateway/live_voice/native_interaction_runtime_client.py` | 1,089 | 持有进程私有 capability 的 E2A 客户端；结果校验 | Gateway / L2 | `JIUWEN_KEEP` | 导入 `server.live_voice.{native_interaction_carrier,native_interaction_contract,openai_realtime_native_engine,presentation_ledger,voice_task_bridge}`：Gateway 依赖 AgentServer 内部模块，是层级倒置的直接证据 |
| `gateway/live_voice/native_response_downlink.py` | 291 | 一个 response 的有界音频源，复用 dedicated media | Gateway / L2 | `JIUWEN_KEEP` | 符合 D-103“复用 synthesis downlink leaf”的方向 |
| `server/live_voice/native_interaction_config.py` | 111 | 引擎选择与模型名校验 | AgentServer / L3 | `JIUWEN_KEEP` | — |
| `dedicated_media_registration.py` 的 Native 段 | ≈2,300 | Gateway 侧 Native session：engine 启动、帧入队、事件泵、downlink 分配/封印、通知序列 fence、playout ACK 转发 | Gateway / L2 | `SPLIT_REQUIRED`（AR-102 加重） | `_allocate_native_downlink` 280 行、`acknowledge_native_playout` 248 行、`_queue_native_user_transcript` 217 行；应抽成 `NativeMediaSession` owner |
| registry 的 Native handler | ≈1,500 | `handle_native_propose` 499、`handle_native_presentation_ack` 334、`handle_native_close` 170、delegate propose 312、`_run_native_close` 96 与 6 个 helper | AgentServer / L3 composition | `SPLIT_REQUIRED`（AR-175 加重） | 应抽成 Native composition handler 模块 |
| 前端 `productP1VoiceRoute.ts` Native 段 | ≈700 | activation 解析、native audio 播放、chat projection | Browser / L2 | `JIUWEN_KEEP` | — |

### 3.2 生产语义（D-107–D-112，新增约 2,900 行，退役约 1,700 行）

| 模块 | LOC | 责任 | 层 | 处置 | 发现 |
|---|---:|---|---|---|---|
| `task_semantics.py` | 1,207 | 唯一模型语义实现：闭合 JSON Schema、bounded context、结构化重试、冻结记录复验 | L3 | `JIUWEN_KEEP` | 直接使用 `openjiuwen.core.foundation.llm`（正确的 `DIRECT_REUSE`）；`task_semantic_output_schema` 304 行、`_decode` 222 行是生成器候选 |
| `semantic_continuity.py` | 255 | Registry 拥有的有界 pre-command 连续性协调器 | L3 | `JIUWEN_KEEP` | — |
| `unified_committed_input.py` 新段 | +599 | `semantic_pending_contexts` 表：scope/version/expiry/consumed CAS | L3 | `JIUWEN_KEEP` | 是 committed-input journal 内的第二张表族，不是 Task truth（符合 D-107）；其 schema 必须进 canonical source |
| `task_control_presentation.py` | 47 | 控制事实的呈现文案 | L1/L3 | `JIUWEN_KEEP` | — |
| registry 的语义段 | ≈600 | `_run_unified_submit_decided` 399、`_dispatch_semantic_agent_turn` 133、`_resolve_semantic_input` 48 | L3 | `SPLIT_REQUIRED` | 应抽成 semantic dispatch 模块 |
| 已退役 | −1,666 | `voice_task_bridge.py` 1,447→197，`production_task_classifier.py` 578→162，registry 移除 `_PendingTaskIntent` 与 frozen one-current-task 语句 | — | 自然退休 | 与 HARDCODE_RETIREMENT 方向一致 |

### 3.3 Speculative dialogue 与 tool hold（`ebd2b4575`，新增约 700 行）

| 模块 | LOC | 责任 | 层 | 处置 | 发现 |
|---|---:|---|---|---|---|
| `speculative_dialogue.py` | 407 | 决策前的候选推理：有界缓冲、attach/replay/discard、工具暂停 | L1 | `JIUWEN_KEEP` | 通过 `SpeculativeFormalFacade` Protocol 只依赖 formal seam |
| `formal_tool_gate.py` | 75 | 进程本地 session→paused/released 注册表 | L3 | `JIUWEN_KEEP`，与 rail 收敛 | 存在只因为 rail 在流开始前尚不存在 |
| `interface.py` +5 方法、`stream_event_rail.py` +3 方法 | ≈80 | 把 gate 施加到 `JiuSwarmStreamEventRail` 的 tools-only pause event | L3 harness | `JIUWEN_KEEP` | 已安装 `AgentRail.before_tool_call` 钩子可承载一个 hold；`AsyncToolRuntime` 只有 launch/cancel/wait，无 pause，也不需要 |
| `agent_conversation_runtime.begin_speculative_dialogue` 等 | ≈170 | 候选与 admitted round 的接管 | L1 | `JIUWEN_KEEP` | — |

建议：tool hold 不作为 F4 提交。它没有 durable owner、lease、restart reconcile；把它下沉只会给
AgentCore 增加一个无 adopter 的 public surface。

### 3.4 生成期打断（D-104/D-106，新增约 750 行）

`conversation_runtime_loop.py` +13 symbol（retained interrupt ledger、settle、evict）、
`agent_conversation_runtime.py` 的 `interrupt_generation` 与 fence、`presentation_ledger.seal_surface`、
registry `handle_p2_interrupt_generation` 188 行、前端 `interruptGeneration` 与
`FEATURE_LIVE_VOICE_GENERATION_INTERRUPTION`。处置 `JIUWEN_KEEP`（L1）。发现：这是
第二套 fence；与播放期插话和 Native `fence_response` 合并为一个 response fence 状态机是
S5 的核心收敛项。

### 3.5 观测与诊断（2026-09-04 profiling 包，新增约 1,400 行）

| 通道 | 后端 | 前端 | 处置 |
|---|---|---|---|
| OTel/产品观测 | `observability.py` 1,960、`product_observability_runtime.py` 1,425、`product_observability_adapter.py` 847、`observability_correlation_contract.py` 876、`observability_exporter.py` 734、`observability_otel_codec.py` 641 | `liveVoiceObservability.ts` 1,598、`liveVoiceRouteTelemetry.ts` 257、`webPlatformDiagnostics.ts` 326 | `JIUWEN_KEEP` 的 runtime leaf，但要收敛 |
| 被动 profiling | `live_voice_profiling.py` 221（被 15 个生产模块引用）、`formal_model_diagnostics.py` 320、`agent_client.py` 的 `@profiled` | — | `ADAPT_REUSE` 候选：已安装 `agent_teams.observability.setup.get_tracer` 与 `ObservabilityRail` 可承载 span，LiveVoice 只留隐私投影 |
| 音频诊断 JSONL | `live_voice_audio_diagnostics.py` 168、`speech_http_diagnostics.py` 63、`speech_socket_diagnostics.py` 210 | `audioDiagnostics.ts` 326、`audioDiagnosticJournal.ts` 88、`webClient.ts` 段 | `JIUWEN_KEEP` 作为离线诊断 sink，与 exporter 共用隐私投影 |
| 无 caller | `observability_fault_harness.py` 391、`telemetry_privacy_contract.py` 221 | — | A1 退休 |

后端观测生产代码约 8,100 行（A1 退休 612 行无 caller 文件后约 7,500）、前端约 2,600 行，规划中心 3,500 不变，因此这是第二大
收敛缺口，仅次于 Task/Store。

### 3.6 Task 投递、Store 与 Executor 的新增（D-098–D-100、D-112）

| 新 symbol | 行为 | 通用性判断 | 处置 |
|---|---|---|---|
| `SqliteTaskStore.renew_outbox_claim` | 只续约完全相同 binding（task/attempt/command/kind/scope/selection/executor_ref/adjustment）且未终态的 claimed 项 | F2 claim lease 续约的精确合同 | `AGENTCORE_FOUNDATION_ADD`（F2 内，不新增族） |
| `SqliteTaskStore.settle_unbound_queued_attempt` | 证明“已选定、无 Executor 绑定、pending dispatch、delivery_count 与 admission 次数一致”的 Attempt 仍是 Store 拥有的队列工作，只清除 `ATTEMPT_NOT_YET_BOUND` 标记 | F1/F4 restart reconcile 的 admission 合同 | `AGENTCORE_FOUNDATION_ADD`（F4 内） |
| `_AdjustmentDeliveryOwner`、`_deliver_outbox`、`_own_adjustment_settlement`、`_fence_adjustment_delivery`、`drain_inflight_adjustments` | outbox item → executor dispatch/cancel/adjust → complete/release/reject/defer；settlement 绑定冲突拒绝；fence 独立于不合作 delivery；Executor close 之后、释放 binding 之前 drain | 通用部分是 K2/K3 的 dispatch drain（历史候选缺的正是生产 consumer）；`executor.settle_adjustment` 是 Jiuwen executor 策略 | drain/settlement 归 `AGENTCORE_FOUNDATION_ADD`（F2/F4），adjustment 策略 `ADAPT_REUSE` |
| `_DirectProjectAttemptJournal.latest_completed_project_effect` | 按 project root 读最近一次 COMPLETED 且有 expected_tree 的 Direct 记录 | “某资源最近一次已结算效果”的读端口是 F6 通用查询；当前由 Direct journal 表回答 | 查询端口 `AGENTCORE_FOUNDATION_ADD`（F6 读 seam），表本身不下沉 |
| `DirectProjectManagedBaselineReader` | 只承认干净 Git 状态或一个精确结算的 D2 效果：交叉核对 Direct 记录、Store Task/Attempt、durability effects/checkpoints、Git head、protected support 指纹 | Jiuwen 项目证明策略 | `JIUWEN_KEEP`（L3 executor） |
| `_LEGACY_DIRECT_D0/D2_CAPABILITY_PROFILE` | v1 记录不得授权 v2 dispatch 的过渡 | 过渡物 | `CONSOLIDATE_RETIRE`（迁移 gate 后） |

发现：`DirectProjectManagedBaselineReader` 同时读 Direct journal 与 Store durability
effects 才能证明一个效果，证实 Direct journal 已是第二份效果 truth；F6 落地后 Direct
journal 只保留 Git/worktree 事实。

### 3.7 前端产品/UI 新增（约 3,900 行）

| 模块 | 增量 | 处置 | 发现 |
|---|---:|---|---|
| `LiveVoiceIntegratedRoutePanel.tsx` | +1,819 | `SPLIT_REQUIRED` 加重 | 新增 13 个导出（11 个函数含 2 个 async、2 个常量；同时移除 2 个导出），主题是通知播放仲裁与文本回退，应先抽成 `taskNotificationArbitration.ts` 纯策略模块 |
| `browserAudioIOAdapter.ts` | +677 | `JIUWEN_KEEP`（L2） | verified-headset 近端候选：RMS/峰值/回声相似度常量与 tentative pause；是 Hermes 没有的真实责任 |
| `productWebActivation.ts` | +266 | `JIUWEN_KEEP`（L2） | 通知序列失配重同步、generation interrupt 方法 |
| `formalP3TaskExperience.ts` | +106 | `JIUWEN_KEEP`（L3） | definitive rejection 分类 |
| `RecentTasksPanel.tsx`、`liveVoiceTaskStore.ts`、`taskPresentationView.ts`、`ToolPanel/index.tsx` 段 | 148 | `JIUWEN_KEEP`（L3），读路径依赖 `ADAPT_REUSE` 的 Task datasource | 承接 AR-013 迁移 |
| `useProductVoiceSessionStart.ts`、`createLiveVoiceConversation.ts` | 154 | `JIUWEN_KEEP`（L3） | — |
| `buildTurnTimeline.ts` 段 | +23 | `JIUWEN_KEEP`（L3） | 按 presentation owner 铸造的 id 命名空间识别 Task 通知，正确 |

### 3.8 共享宿主 segment 与脚本

预检 §6.3 的 ≥8 个新 segment 全部 `JIUWEN_KEEP`（tool hold 见 §3.3）。新增 9 个
`scripts/live_voice` 文件是 L5 support；其中 `semantic_audio_{runtime,browser,journey,assertions}.py`
是可复用的合成语音 journey oracle，B 期结构包以它加物理 demo journey 作为行为保持证据。

## 4. AgentCore 下沉部分（更新）

### 4.1 范围与规模

不变：K1 Scoped Durable Task、K2 Ordered Event Consumption、K3 Durable Execution
Ownership、K4 Checkpoint/External Effect Durability；F1–F6 六个 seam；一个
transaction/reducer owner；复用 `TaskDao`/`TeamTaskManager`（31 个 public 方法）、
`TaskScheduler`、`AsyncToolRuntime`（launch/get/cancel/wait）、`Checkpointer`/`Storage`；
禁止复制 `SqliteTaskStore`、`PersistentTaskCore`、`_DirectProjectAttemptJournal`；禁止
replay 15,128 行历史候选。规划中心约 5,300、区间约 3,600–8,100 不变。

### 4.2 F1–F6 合同更新

| Seam | 本轮新增的 invariant（来自 §3.6） | 复用什么 | 明确不新增 |
|---|---|---|---|
| F1 Task/Attempt/Command/Result | selected-but-unbound Attempt 的 recover admission；adjustment 的 settlement binding 冲突拒绝 | `TaskDao` 事务、Task 状态 | Voice envelope、FormalTaskSpec、adjustment 的产品含义 |
| F2 Event/Outbox | claim 续约必须校验完整 binding 与 claimed_at 单调；busy/capacity 的 defer 是 claim 结果之一 | Task 事务、Scheduler delivery | Voice progress event、Web delivery truth |
| F3 Cursor | 无变化 | F2 event identity | DOM/audio truth |
| F4 Execution ownership | settlement fence 独立于不合作 delivery；Executor close 之后、释放 binding 之前 drain，未 settle 即 RESULT_UNKNOWN | `AsyncToolRuntime` cancel、`TaskDao` | Git/worktree/patch、tool hold（§3.3） |
| F5 Checkpoint publication | 无变化 | `Checkpointer`/`Storage`、GraphStore | Jiuwen D1 codec |
| F6 Effect journal | 读端口：某 scope/resource 最近一次 RESOLVED settlement 及其 evidence digest | `ToolCard.idempotent`、统一事务 | 项目 Git 证明、protected support 指纹、compensation 策略 |

### 4.3 明确不下沉的新增代码

§3.1 全部 Native 模块、§3.2 语义与 pending context、§3.3 tool hold 与 speculation、
§3.4 生成期打断、§3.5 观测通道（可 `ADAPT_REUSE` tracer，但不下沉）、§3.6 的
`DirectProjectManagedBaselineReader` 与 Direct journal 的 Git 事实、§3.7 全部前端。

### 4.4 A2 需要的 zero-baseline decision record

按 AgentCore 零基线审计 §9 每个 seam 一份，共六份；jiuwenswarm 侧提供 adoption oracle：
`tests/unit_tests/live_voice/test_persistent_task_core.py`（10,906 行）、
`test_p3_4_durability_store.py` / `test_p3_4_durability_runtime.py`、
`test_project_code_executor.py`（5,762 行）中与 §3.6 对应的 race/restart/corruption 用例。
每份记录回答：最近 public owner、被扩展的事务 owner、最小 invariant 集与 oracle、Jiuwen
Adapter 只映射什么、拒绝的历史 candidate symbol、public export 最小性、唯一 codec/digest/
reducer、仓内外 adopter、避免双写的迁移/canary/rollback、同口径 LOC 报告。

### 4.5 切换顺序

不变：C1 薄 Adapter → C2 single-writer cutover → C3 checkpoint/effect 与 executor 拆分。
C1 之前 LiveVoice 不改 Task/Store/Executor 的 authority；A2 完全在 agent-core 仓库内进行。

## 5. 留在 jiuwenswarm 的 LiveVoice 部分（更新）

### 5.1 目标布局

```text
common/schema/live_voice/            canonical schema 单源：contract v2、native contract/carrier、
                                     semantic pending context、method catalog → 生成 TS 与 allowlist
server/live_voice/core/   (L1)       conversation runtime + 一个 response fence、speech port/policy、
                                     presentation ledger、native runtime owner、speculation、progress 仲裁
gateway/live_voice/       (L2)       薄 dedicated media registration、media transport、streaming
                                     speech/synthesis route、providers/（openai streaming、openai
                                     realtime session+engine）、native downlink、native runtime client
server/live_voice/product/(L3)       committed input + semantic（task_semantics、continuity、journal）、
                                     P3 authenticated composition、intent/policy、project executor adapter、
                                     薄 composition root、observability leaf（一个 exporter）
frontend features/live-voice/{core,audio,media,web,task-presentation}
tests/ · scripts/ · validation/      L5：oracle、合成语音 journey、探针
```

### 5.2 规划区间（取代重适配 §3）

只列相对重适配变化的行；其余行沿用。

| 责任模块 | 重适配中心（区间） | 本文中心（区间） | 变化原因 |
|---|---:|---:|---|
| Native interaction engine | 4,500（3.0–5.5K） | 3,800（2.5–4.8K） | contract/carrier 单源化后计入 Schema 行（Schema 行 2,000 的假设已含其单源后的体积，不再是当前的 1,359 行）；engine/session 迁 Gateway provider 层 |
| Schema/protocol | 2,000（1.4–2.6K） | 2,000（1.4–2.6K） | 已含 native contract/carrier 的单源化 |
| Observability | 3,500（2.8–4.5K） | 3,500（2.8–4.5K） | 三通道收敛到一个 exporter；tracer `ADAPT_REUSE` |
| Composition/configuration | 2,700（2.0–3.7K） | 2,700 | Native/semantic handler 抽出后 registry 才可能接近该值 |
| **合计** | **54,900（43,900–68,700）** | **≈54,200（43,400–68,000）** | 相对当前约 187K 仍约 −70% |

### 5.3 收敛清单（留在 jiuwenswarm 的部分具体要做什么）

1. 一个 response fence：播放期插话、生成期打断、Native barge/fence 合并进
   `ConversationRuntimeLoop`，surface 只做 adapter。
2. 观测三通道 → 一个 exporter + 一份隐私投影；被动 span 适配到已安装 tracer。
3. `dedicated_media_registration.py` 抽出 `NativeMediaSession`（≈2,300 行）与 diagnostics；
   registry 抽出 Native handler（≈1,500 行）与 semantic dispatch（≈600 行）。
4. tool hold 收敛为一个 Jiuwen rail element，删除进程本地 gate 注册表。
5. Native contract/carrier 进 canonical schema；engine/session 迁 Gateway provider 目录，
   消除 Gateway 对 `server/live_voice` 的导入。
6. Panel 的 13 个通知仲裁纯函数抽成独立模块；Panel 拆 P1/P2/P3 owner。
7. Python 三套 schema 家族与 TS 副本 → 单源生成（`liveVoiceContractV2.ts` 2,785 行随之退休）。
8. F6 落地后 Direct journal 只留 Git/worktree 事实；legacy D0/D2 profile 在迁移 gate 后退休。
9. 零 importer 集群约 9,450 行（A1）；legacy 活跃集群 3,209 行与 AutoHarness segment 493 行（D1）。
10. 十项既有结构债务中第 8 项（media registration）与 registry/Panel 优先级前移。

## 6. 实施包更新（相对重适配 §4）

| 包 | 变化 | 范围补充 | 验收补充 |
|---|---|---|---|
| A0 冻结与文档前置 | 增加：tool hold 归属决定（§7.4 建议 JIUWEN_KEEP）；三套 schema 家族与 pending context 表的清单 | — | — |
| A1 零 caller 退休 | 不变（§3.5 的 fault harness 与 privacy contract 在其中） | — | — |
| A2 AgentCore F1–F6 | 合同按 §4.2 更新；adoption oracle 按 §4.4 指定 | 6 份 decision record 先于代码 | 每个新增 invariant 有正向、负向、race、restart 用例 |
| A3 canonical schema 设计 | 增加 native contract/carrier、semantic pending context、`task_semantic_output_schema` 生成 | 只设计与等价测试，不切换 | 三套 Python 家族与 TS 副本字节/语义等价 |
| **B2a media registration 拆分** | 新拆分顺序第一 | `NativeMediaSession` owner、registration、diagnostics、product authority 四个文件 | 合成语音 journey + 物理 demo journey + reconnect/barge-in/ACK 回归 |
| **B2b registry 抽取** | 第二 | Native handler、semantic dispatch、P1/P2/P3 handler factory 抽出，registry 只留注册与生命周期 | 同上 + multi-Task、feature-off |
| **B2c 一个 response fence** | 第三；Tier 3 | 三套 fence 合并，行为保持 | 生成期打断、播放期插话、Native barge 各自的既有用例全部通过；零 Task/history 副作用 |
| **B2d Panel 拆分** | 第四 | 仲裁纯函数模块、P1/P2/P3 owner | 前端测试等价 + journey |
| **B2e executor seam** | 第五 | project seam 与 generic attempt 记录分离，为 C3 铺路 | D0/D2 用例通过 |
| **B4 观测收敛（新增）** | Tier 2 | 三通道 → 一个 exporter；tracer 适配；隐私投影单源 | 隐私零泄露断言、export 等价、profiling 报告脚本仍可解析 |
| B1 / B3 / C1–C3 / D1–D2 | 不变 | — | — |

每包仍按 root `TESTING.md` 单独定级；上表的 tier 是提案。

## 7. 需要用户决定的产品边界（更新）

1. 触发条件变更写成新 Decision（重适配 §7.1），建议顺延在 D-114 之后。
2. 冻结 tag：建议以 A0 启动时的特性分支 tip（写作时 `076065f1b`，生产代码与 `ebd2b4575` 相同）作为 A 期源码冻结点；B 期 oracle 冻结点等 demo 物理 PASS。
3. Native 纳入本轮：**建议纳入**，但 B 期只做 relocate/extract（§5.3 第 3、5 项），不改
   Provider 语义与 D-101–D-103 合同。
4. tool hold 归属：**建议 JIUWEN_KEEP**，作为一个 Jiuwen rail element；不向 AgentCore 提
   F4 扩展。
5. 瘦身先于 `develop` 集成落地（重适配 §7.5）。
6. 新增：是否接受观测三通道收敛为一个 exporter 并适配已安装 tracer（B4）；这会改变
   离线 profiling 报告的数据源，需要运行手册同步。

## 8. 本文不授予什么

本文不改变 STATUS 判断，不宣告任何包已开始或完成，不把处置码当作已执行的迁移，不授予
AgentCore 能力接受或安装信用，也不授权任何远端操作。A 期各包在用户接受 §7.1 与 §7.2
后才进入实施。

## 9. 增量（`7c7aad7b8`，2026-09-05 第二次 rebase）

- **F1/F4 合同再增两条 invariant**：`task_store.py` 新增 `_settle_cancel_before_dispatch`（队列
  派发前先结算已请求的取消）与 `_is_exact_unbound_queue`；`project_code_executor.py` 新增
  `project_has_unsettled_attempt` 与 `_require_project_available`（同一项目存在未结算 Attempt
  时拒绝新的派发）。它们分别落在 F4 的 settlement 与 F1 的 admission，不新增能力族；A2 的
  decision record 与 adoption oracle 应包含这两条。
- **Agent bridge 收缩**：`formal_live_voice.py` 的口语修订策略（8 个 symbol，142 行）被撤除，
  §3.7/§5.2 中 Agent bridge 的规划中心可从 1,500 回落到约 1,300。
- **legacy 旧 Task lane 已删**：§3.8 与 A1 清单中的 AR-075–078 变为自然退休。
- **TTS 共享宿主段变化**：`ttsText.ts` 收缩到 113 行，新增播放队列与消息播放服务两个小文件；
  它们属于 Channel Adapter 的 TTS 输出 segment，冻结后重算归因。
- 其余：registry +83、`speculative_dialogue.py` +52、round harness −11；无新增路径。
