# OpenJiuwen LiveVoice “理论上可去掉”代码的原理、验证与重新判断 — 2026-09-05

> 状态：Integration Owner 的验证记录（文档-only 批次；root `TESTING.md` Live Voice risk
> tiers 与 D-046 的 Tier 0 口径）。基线 `hx/0812_live_voice_w3@076065f1b`，其 `jiuwenswarm/`
> 下的 py/ts/tsx/js 与 `ebd2b4575` 逐字节相同。按用户要求 Native engine 本轮不处理。
> 本文只回答三件事：准备文档为什么说某些代码理论上可去掉；这些判断在当前分支上是否
> 仍然成立；重新判断后现在能去掉什么、什么时候能去掉。本文没有删除任何代码。

## 1. 结论先行

1. **准备文档的“可去掉”只有一种合法来源：原子表里 52 条 `CONSOLIDATE_RETIRE` 行，每行
   绑定自己的 gate。** `AGENTCORE_PR` 13 行授权的是“被 accepted 且 installed 的公共能力
   替换”，不是删除；`SPLIT_REQUIRED` 31 行授权的是拆分，不是删除。任何按文件路径或
   LOC 目标的删除都不被这些文档授权。
2. **52 条行的 gate 归为四族。** G1 零生产 caller 且 oracle 已迁；G2 legacy 与 formal
   的单 owner cutover；G3 AgentCore 替换 cutover；G4 schema 单源生成。这是本文对 gate
   文字的归纳，不是文档新增的分类。
3. **在 `076065f1b` 上逐行验证后，现在就满足 G1 的代码为 21 个整文件 9,761 行加 5 个
   Python 混合文件内 1,946 行，合计约 11,700 行。** 全部经精确 import 扫描证明没有生产
   importer，或只被同样死亡的文件引用；其中 19 个文件仍有测试引用，删除前要先迁 oracle。
4. **G2 的 legacy lane 仍然活着。** `ChatPanel` 无条件执行 `useLiveVoiceDemo` hook（React
   hook 不能条件调用）；`build:live-voice` 构建不渲染 legacy bar，而普通 `vite build`
   （`.env.production` 把两个 formal flag 置为 false）仍渲染它；链上 8 个文件 2,459 行加 L0 批量
   面板 2 个文件 750 行。AutoHarness 的 4 段 LiveVoice 分支在前端已无生产 producer，只剩
   AgentServer 的 `schedule` RPC 入口可达。
5. **五处判断被增量改变。** AR-126、AR-213 已自然退休；AR-051–054 把 `liveVoiceContractV2.ts`
   判为“零生产 importer”，现在 `parseEventEnvelope` 被 Panel 与 `productTextProgress.ts`
   导入，整文件不可删，须先拆出活的 parser；AR-010/050 的 L0 面板现在挂在 formal flag
   下，但没有 URL 批量参数时渲染 null，仍是批量支持路径；AR-198 的 `TaskCore` 类只被
   `fake_verticals` 实例化，但同文件的值类型仍被 3 个生产模块使用，行判断要拆开读。
6. **G3 与 G4 的 gate 都还没过。** `PersistentTaskCore` 仍是唯一 Task 编排 owner；
   Task 数据库有两个 writer（`SqliteTaskStore` 与 `_DirectProjectAttemptJournal`）；三套
   Python schema 加 TS 副本仍并存。这些行现在不能删。

## 2. 准备文档的“可去掉”原理

### 2.1 原子表（`OPENJIUWEN_LIVEVOICE_ATOMIC_DISPOSITION_2026-08-31.md`）

八个处置码里只有 `CONSOLIDATE_RETIRE` 允许物理删除，且“remains conditional on its row
gate”。52 行 gate 的共同模板是：核实 caller 证据 → 迁走仍有效的测试 oracle 与兼容行为 →
证明 replacement/formal 路径 → 可恢复地退休或 re-home。按 gate 文字归纳：

| 族 | gate 要点 | 行数 | 典型行 |
|---|---|---:|---|
| G1 零 caller | “zero production importer / reachable only from benchmark, conformance, deployment or batch-support flows / only fake_verticals instantiates” | 28 | AR-038/039/044/058/070、AR-075–078、AR-086/087、AR-092、AR-119/120/136/137/152/183/194/195/210、AR-115/142/145/198/228、AR-049/056 |
| G2 legacy 单 owner | “reachable only through the legacy demo/AutoHarness browser subtree / ChatPanel still renders the legacy branch / preserve every non-LiveVoice AutoHarness path / legacy compatibility shape” | 16 | AR-032/033/046/072/073/074/079/080、AR-015、AR-010/050、AR-001–004、AR-065 |
| G3 AgentCore cutover | “remains authoritative until the accepted shared facade is installed, migrated and cut over” | 4 | AR-169、AR-208、AR-126、AR-213 |
| G4 schema 单源 | “unused browser … contract copy” | 4 | AR-051–054 |

### 2.2 零基线审计（`OPENJIUWEN_LIVEVOICE_ZERO_BASE_MODULE_AUDIT_2026-08-31.md`）

§3.2 把 163,264 行分成六个责任桶，其中 “Legacy/support（仍在生产树）15,123” 与
“AgentCore duplicate/PR candidate 26,568” 是未来可减少的桶，“Truly mixed 38,215” 必须先按
symbol 分账；§6 记录“至少 7,837 行 test/reference 不在产品 runtime 调用链”；§8.2 的
十项结构债务是收敛，不是删除。

### 2.3 AgentCore 零基线审计（`OPENJIUWEN_AGENTCORE_FOUNDATION_ZERO_BASE_AUDIT_2026-09-01.md`）

`REJECT/RETIRE` 只用于历史 15,128 行候选中重复/无 adopter 的层级；LiveVoice 侧的 Task/
Event/Execution/Effect truth 在 replacement accepted 且 installed 之前一行都不能删（§9 停止
条件最后一条）。

### 2.4 预算文档（`OPENJIUWEN_LIVEVOICE_HERMES_ALIGNED_SLIMMING_BUDGET_2026-08-31.md`）

§2 明令禁止“按旧文件路径或整文件主责任直接删除”；§9 八条最低 Gate；§7 第 8 条规定冻结代码
已自然删除的责任只记录事实、不重建。

## 3. 验证方法与局限

- 生产 importer 用精确边界扫描：Python 按完整模块路径或同包相对导入；TypeScript 允许
  `.js/.ts` 后缀与动态 `import()`。生产集合是 `jiuwenswarm/` 下排除 `tests/` 与 `test_*`
  的源码。第一轮子串扫描曾把 `live_voice_contract` 误命中 `_v2`、漏掉带 `.js` 后缀的
  TS import，本文数字来自修正后的第二轮。
- 另统计测试 importer 数、`package.json` 的 `test:*` 脚本引用、`scripts/` 与文档引用，
  以及类实例化点与残留分支的外层函数。
- 局限：只做静态分析，不覆盖以字符串拼出的动态引用；TypeScript 混合文件内的部分
  symbol 行数未量测；没有运行任何测试或构建。

## 4. 逐项验证

“LOC”是 `076065f1b` 上 `wc -l`；“测试”是测试文件 importer 数。

### 4.1 G1：零生产 caller（现在可退休，先迁 oracle）

| 行 | 路径 | LOC | 文档理由 | HEAD 验证 | 判断 |
|---|---|---:|---|---|---|
| AR-038 | `formal/conversationRuntimeReplica.ts` | 258 | 参考副本 | prod 0；测试 1；`package.json` 仅 `test:*` 脚本 | 可退休 |
| AR-039 | `formal/fakeP1Vertical.ts` | 104 | 参考 fake | prod 0；测试 1 | 可退休 |
| AR-044 | `formal/formalTaskResultRoute.ts` | 311 | 未使用的结果查询 owner | prod 0；测试 1；`package.json` 仅测试脚本 | 可退休（重适配 §5 曾标“需核对”，现已核清） |
| AR-058 | `formal/productCompositionContract.ts` | 289 | 未使用的 manifest/parser | prod 0；测试 1 | 可退休 |
| AR-070 | `formal/webLifecycleObservationRecorder.ts` | 383 | 未使用的 recorder | prod 0；测试 1 | 可退休 |
| AR-075 | `liveVoiceTaskAdapter.ts` | 279 | 旧 Task lane | prod 0 | 可退休 |
| AR-077 | `liveVoiceTaskClient.ts` | 162 | 旧 Task RPC client | prod 0 | 可退休 |
| AR-078 | `liveVoiceTaskMonitor.ts` | 499 | 旧轮询 monitor | 只被死亡的 adapter 导入 | 可退休 |
| AR-076 | `liveVoiceTaskBridge.ts` | 1,486 | 旧 AutoHarness bridge | 只被 adapter/client/monitor 三个死文件导入；`LIVE_VOICE_AUTO_HARNESS_PIPELINE` 只在此定义 | 可退休；它退休后前端不再有 `project_code_pipeline` producer |
| AR-086 | `channels/web/live_voice_deployment_observer.py` | 1,045 | 部署观测支持 | prod 0；测试 2；只被历史 `scripts/live_voice/s7_*` 引用，runbook/STATUS/launcher 无引用 | 可退休（re-home 到 scripts 或删） |
| AR-087 | `channels/web/live_voice_deployment_preflight.py` | 449 | 部署 preflight | 只被 observer 导入 | 随 AR-086 |
| AR-092 | `common/schema/live_voice_contract.py` | 235 | v1 schema | prod 0（第一轮误报来自 `_v2` 子串）；测试 1 | 可退休 |
| AR-119 | `alpha_benchmark.py` | 633 | Alpha benchmark 支持 | prod 0；测试 1 | 可退休 |
| AR-120 | `alpha_privacy_conformance.py` | 1,025 | Alpha 隐私 conformance | prod 0；测试 1 | 可退休 |
| AR-137 | `fake_verticals.py` | 404 | fake 集成 vertical | prod 0；测试 1；它是 `TaskCore()` 与 `AgentBridgePort()` 唯一实例化者 | 可退休 |
| AR-136 | `executor_port.py` | 117 | 过时的内存 Executor 状态机 | 只被 `fake_verticals` 导入 | 随 AR-137 |
| AR-152 | `observability_fault_harness.py` | 391 | 故障注入支持 | prod 0；测试 1 | 可退休 |
| AR-183 | `product_p2_readiness.py` | 262 | 未使用的 readiness | prod 0；测试 1 | 可退休 |
| AR-194 | `realtime_media.py` | 822 | 未组合的 media 工厂 | prod 0；测试 1 | 可退休 |
| AR-195 | `sli_window_contract.py` | 386 | 未使用的 SLI 计算 | prod 0；测试 0 | 可退休 |
| AR-210 | `telemetry_privacy_contract.py` | 221 | 未使用的隐私声明 | prod 0；测试 0 | 可退休 |
| **整文件小计** | 21 个文件 | **9,761** | | 前端 3,771、后端 5,990 | |
| AR-228 | `project_code_executor.py` 内 `LegacyProjectTaskService`、`ProjectCodeExecutorAdapter` | 504 | 未实例化的 legacy carrier | 全仓无实例化；formal 组合只构造 `DirectProjectCodeExecutorAdapter` | 可退休（部分文件） |
| AR-198 | `task_core.py` 内 `TaskCore` 等 13 个 symbol | 581 | 遗留内存 Task authority | `TaskCore()` 只在 `fake_verticals` 实例化；`DispatchIntent` 只被死亡的 `executor_port` 导入；同文件 `TaskState`/`AttemptState`/`TaskCommand`/`TaskSpec` 不在本行，仍被 3 个生产模块使用 | 本行 581 行可退休；值类型留到 F1 schema 单源 |
| AR-145 | `latency_measurement.py` 内离线 L0 collector/report/corpus 6 个 symbol | 510 | 离线工具 | 3 个生产 importer 只导入 runtime 的 `L0Milestone`/`L0RoundBinding`/`L0RoundClassification`/`emit_runtime_l0_milestone`/`register_runtime_l0_binding`/`resolve_runtime_l0_binding`；离线 symbol 只被 `scripts/live_voice/l0_*` 与测试引用 | 可 re-home 到 scripts（L0 已由 D-095–D-097 闭环） |
| AR-142 | `interaction_engine.py` 内 `ScriptedCascadeInteractionEngine` 等 4 个 symbol | 286 | 脚本化 Cascade fake | 生产零 caller；`InteractionEnginePort`（AR-141）现同时被 Cascade 与 Native engine/carrier 使用，保留 | 本行 286 行可退休 |
| AR-115 | `agent_bridge.py` 内 `AgentBridgePort`/`AgentRequest`/`AgentHandler` | 65 | 线程池 fixture seam | 只被 `fake_verticals` 实例化；`AgentEvent`（AR-116）仍被 3 个 runtime 使用 | 本行 65 行可退休 |
| **部分文件小计** | 5 个文件 | **1,946** | | | |
| AR-049 | `l0Measurement.ts` 内 `browserL0Control` | 未量测 | 批量控制面 | 只被 `l0OrdinaryChromeBatch.ts` 引用 | 随 §4.2 的 L0 面板 |
| AR-056 | `liveVoiceObservability.ts` 内 collector/metric/route helper | 未量测 | 未使用的 bundle | 文件仅经 `l0Measurement.ts` 被 `productP1VoiceRoute.ts` 间接引用（AR-055 的 schema 部分）；helper 无生产 caller | 需 symbol 级拆分后退休 |

G1 合计：整文件 9,761 行 + 部分文件 1,946 行 = **11,707 行**，另有两处未量测的 TS 片段（AR-049、AR-056）。

### 4.2 G2：legacy 单 owner cutover（现在不能删）

| 行 | 路径 | LOC | 文档理由 | HEAD 验证 | 判断 |
|---|---|---:|---|---|---|
| AR-080 | `useLiveVoiceDemo.ts` | 873 | legacy capture/TTS hook | `ChatPanel/index.tsx:1240` 无条件调用；`FEATURE_LIVE_VOICE_DEMO` 是常量 `true`；`build:live-voice` 构建（`.env.live-voice` 把 `INTEGRATED_WEB`/`INTEGRATED_P1` 置为 true，launcher 使用它）走 `FormalProductLiveVoiceDemoBar`；普通 `vite build` 用 `.env.production`，两个 flag 为 false，仍渲染 legacy bar；hook 在 P1 flag 为真时仍构造 `IntegratedP1Route` 与 `LiveVoiceCore`。`startListening()` 只出现在回调内，本轮未发现挂载即开始捕获的 effect | gate 未过：需要 ChatPanel 只构造一套 owner |
| AR-072/073/074/079 | `liveVoiceCore.ts` 445、`liveVoiceMessageGate.ts` 119、`liveVoiceStreamingSpeech.ts` 321、`liveVoiceTurnLifecycle.ts` 256 | 1,141 | legacy 状态/门/流式/turn | 只被 `useLiveVoiceDemo` 导入（`liveVoiceCore.ts` 另被同链的 `integratedP1Route.ts` 导入） | 随 AR-080 |
| AR-046 | `formal/integratedP1Route.ts` | 150 | legacy-only P1 route | 只被 `useLiveVoiceDemo` 导入 | 随 AR-080 |
| AR-032/033 | `browserSpeechRecognitionAdapter.ts` 117、`browserSpeechSynthesisAdapter.ts` 178 | 295 | legacy-only 浏览器语音 adapter | 只被 `integratedP1Route` 导入（第一轮因 `.js` 后缀漏扫） | 随 AR-080 |
| AR-015 | `LiveVoiceDemoBar.tsx` 内 `CommandCenter` | 未量测 | legacy 命令中心 | legacy bar 分支仍存在于 ChatPanel | 随 AR-080 |
| AR-010/050 | `L0OrdinaryChromeBatchPanel.tsx` 105、`l0OrdinaryChromeBatch.ts` 645 | 750 | L0 批量支持 | 变化：面板现在挂在 `formalProductVoiceEnabled` 下（`index.tsx:1604`），但 `parseOrdinaryChromeBatchConfig` 只在 URL 带批量 flag、9222–9322 范围的 4 位端口与 32 位 hex nonce 时返回配置，否则渲染 null | 仍是批量支持路径；D-095–D-097 已闭环 L0，可与 AR-145 一起 re-home |
| AR-001–004 | AutoHarness 4 个共享宿主的 LiveVoice 段 | 493（零基线审计 §3.2 表四段 47+72+331+43 之和） | LiveVoice-only 兼容分支 | 前端 producer（`liveVoiceTaskBridge.ts`）已死；仅 AgentServer `_handle_schedule_request`（`agent_ws_server.py` L9693–9946）在 `action=run` 且 `pipeline=project_code_pipeline` 时可达，无生产客户端调用；`AutoHarnessService.reconcile_task_statuses` 在 `jiuwenswarm/` 非测试代码中没有静态调用方 | gate 未过：先关闭 AgentServer 入口并迁 branch oracle，再删 4 段 |

| AR-065 | `productTextProgress.ts` 内 `ProductTextProgressLegacyDeliveryAck` | 未量测 | legacy 投递 envelope 兼容形状 | 冷复核纠正本文第一稿：`createProductTextProgressDeliveryAck` 在事件被判为 `legacy_delivery` 时仍返回该形状，`ProductTextProgressPresentationAck` 继承它，`sameDeliveryAck` 消费它 | gate 未过：服务端不再发出 legacy 投递 envelope 后 |

G2 合计：前端 3,209 行（2,459 + 750）+ CommandCenter + AutoHarness 493 行 + AR-065 兼容形状。

### 4.3 G3：AgentCore 替换 cutover（现在不能删）

| 行 | 路径 | LOC | HEAD 验证 | 判断 |
|---|---|---:|---|---|
| AR-169 | `persistent_task_core.py` 的本地编排 carrier | 部分 | `p3_authenticated_composition` 仍构造 `PersistentTaskCore` 作为唯一 Task 编排 owner；增量还给它加了调整投递 owner | gate 未过 |
| AR-208 | `task_store.py` 的 v1..v6 migration/verify | 581 | `_initialize` 仍调用 migration/verification | gate 未过；只有 cutover 与 rollback 证明后 |
| AR-126 / AR-213 | `demo_fixture_contract.py` / `BoundedAlphaTaskIntentResolver` | 0 | 已在增量中删除 | 已完成，按预算 §7 第 8 条只记录 |

补充发现：Task 数据库 `live_voice_formal_project_attempts_v1` 与 `…adjustments` 两张表由
`_DirectProjectAttemptJournal` 在同一个 SQLite 文件内独立写入（`project_code_executor.py:1495`
自开连接），`DirectProjectManagedBaselineReader` 要同时读它和 Store 的 durability 表才能证明
一个效果。这证实 F6 落地前该文件是第二个 writer，也说明 G3 的 cutover 必须同时覆盖它。
另有三个独立 SQLite 文件：`.p2-response-generations`（AR-158 L1）、`p3_confirmations`
（AR-162 L3）、`.unified-committed-input`（AR-211 L3，含 `semantic_pending_contexts`），
它们不是 Task truth，不在 G3 范围。

### 4.4 G4：schema 单源（判断已变）

| 行 | 文档理由 | HEAD 验证 | 判断 |
|---|---|---|---|
| AR-051–054 `liveVoiceContractV2.ts` 2,785 行 | 四段“零生产 importer 的 TS 合同副本” | 增量后 `LiveVoiceIntegratedRoutePanel.tsx:3` 与 `productTextProgress.ts:1` 导入 `parseEventEnvelope`；文件 81 个 export 中 52 个与 Python v2 的 95 个 class/def 同名，按 `[a-z_.]{4,}` 小写字面量正则计 408 个中 383 个与 Python 共享（该数依赖正则，仅作定性） | 整文件不可删；先拆出活的 event parser 或由单源生成替换，其余仍是无 caller 副本 |

## 5. 重新判断汇总

| 类别 | 行数 | 现在能否删 | 条件 |
|---|---:|---|---|
| G1 零 caller 整文件（21 个） | 9,761 | 能 | 迁走 19 个测试文件里仍有效的 oracle；`package.json` 删对应 `test:*` 脚本；`scripts/live_voice/s7_*` 与 `l0_*` 随 re-home |
| G1 部分文件（5 个 Python） | 1,946 | 能 | 同上；`task_core.py` 只删本行 13 个 symbol |
| G1 未量测 TS 片段（2 处：AR-049、AR-056） | — | 拆分后能 | symbol 级拆分 |
| G2 legacy 投递 envelope（AR-065） | 未量测 | 不能 | 服务端停止发出 legacy 投递 envelope |
| G2 legacy 前端链 + L0 面板 | 3,209 | 不能 | ChatPanel 单 owner；L0 面板可先随 AR-145 re-home |
| G2 AutoHarness 段 | 493 | 不能 | 关闭 AgentServer `schedule` 的 `project_code_pipeline` 入口并迁 oracle |
| G3 AgentCore cutover | 581 + AR-169 部分 | 不能 | F1–F6 accepted、installed、single-writer cutover、rollback |
| G4 TS 合同副本 | ≈2,700（2,785 减活的 parser） | 不能整删 | 单源生成或先拆 parser |
| 已自然退休 | — | 已完成 | 只记录 |

与准备文档的关系：零基线审计的“≥7,837 行不在调用链”现在实测为 11,707 行（增量没有
增加死代码，而是本轮扫描更完整并把部分 symbol 计入）；“Legacy/support 15,123”桶中
现在可立即处理的是上述 G1，其余 G2 仍在等单 owner cutover。

## 6. 判断变化清单（相对原子表对 `59998e2c` 代码的记录）

1. AR-051–054：从“零生产 importer”变为“`parseEventEnvelope` 活，其余死”。
2. AR-010/050：从“只从批量支持流可达”变为“挂在 formal flag 下但无 URL 参数时渲染 null”。
3. AR-198：行内 `TaskCore` 死亡确认，但同文件值类型活；行判断须按 symbol 读。
4. AR-044：本轮确认为死文件（重适配 §5 曾留待核对）。
5. AR-126、AR-213：已退休。
6. AR-001–004：前端 producer 已死，仅剩 AgentServer RPC 入口；比原记录更接近可删。
7. 第一轮扫描的两处方法误差（`_v2` 子串、`.js` 后缀）已修正，不影响以上结论。
8. AR-065：本文第一稿误判为“只有定义”，冷复核纠正为运行时仍消费（`legacy_delivery` 事件）。
9. 普通 `vite build` 仍渲染 legacy bar；“正式构建不渲染”只对 `build:live-voice` 成立。

## 7. Native 暂不处理的边界

本文不判断 §3.1（当前分支重分析）列出的任何 Native 模块。与本文相交的三处只记录：
`InteractionEnginePort`（AR-141）现在同时被 Cascade 与 Native 使用，因此 AR-142 只删 fake
不删端口；`app_gateway.py` 与 `dedicated_media_registration.py` 的 Native 段不进入任何
G1–G4 判断；Native 的 contract/carrier 不计入 G4 的“三套 schema”结论所需的删除量。

## 8. 对实施包的修正建议

- **A1（零 caller 退休）** 建议以 §4.1 为准：21 个整文件 9,761 行 + 5 个部分文件
  1,946 行；新增 `formalTaskResultRoute.ts`、AR-228、AR-198、AR-145、AR-142、AR-115。
  排除：`liveVoiceContractV2.ts`（G4）、legacy 链与 AR-065 兼容形状（G2）、L0 面板
  （与 AR-145 一起 re-home，需用户确认）。验收增加：`package.json` 的 `test:*` 脚本同步删除、前端 build
  通过、`scripts/live_voice` 引用核对。
- **D1（legacy 退休）** 增加“先关闭 AgentServer `_handle_schedule_request` 的
  `project_code_pipeline` 分支”作为 AR-001–004 的前置。
- **B3（协议单源）** 增加“先从 `liveVoiceContractV2.ts` 拆出 `parseEventEnvelope` 及其
  依赖，或由生成器替换”作为退休该文件的前置。
- **C2（single-writer cutover）** 增加 `_DirectProjectAttemptJournal` 两张表作为 cutover
  范围，不能只切 `SqliteTaskStore`。

## 9. 需要用户决定

1. L0 批量面板与离线 L0 工具（AR-010/049/050/145，约 1,260 行）：D-095–D-097 已闭环
   L0，是随 A1 一起 re-home 到 `scripts/`，还是保留为批量测试入口。
2. 部署观测/preflight（AR-086/087，1,494 行）：只被历史 `s7_*` 脚本引用，是删除还是
   re-home 到 `scripts/`。
3. AutoHarness 的 AgentServer `schedule` 入口：是否允许在 D1 之前先关闭
   `project_code_pipeline` 分支（无生产客户端，但对外 RPC 仍可达）。

## 10. 本文不授予什么

本文不删除代码、不改变 STATUS 判断、不把 G1 的“可退休”当作已执行，不授予 AgentCore
能力接受或安装信用，也不授权任何远端操作。A1 仍按 root `TESTING.md` 单独定级并在用户
接受触发条件后实施。

## 11. 增量更新（`7c7aad7b8`，2026-09-05 第二次 rebase）

分支自身在 `7c7aad7b8` 删除了旧 Task lane 四个文件（AR-075/076/077/078，
2,426 行）。§4.1 的 G1 整文件从 21 个 9,761 行变为 **17 个 7,335 行**，部分文件 1,946 行不变，
G1 合计约 **9,281 行**；§5 中“整文件 retire 路径合计 15,755”变为 13,329。其余行的判断
不变：`useLiveVoiceDemo` 集群仍被 ChatPanel 构造，`liveVoiceContractV2.ts` 仍被生产导入，
`PersistentTaskCore` 仍是唯一 Task 编排 owner，AR-065 仍在运行时被消费。
