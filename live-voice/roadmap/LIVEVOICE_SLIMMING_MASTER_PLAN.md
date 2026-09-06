# LiveVoice 瘦身重构总计划（Slimming Master Plan）

> 状态：本文是 LiveVoice 代码瘦身重构与 AgentCore 下沉的**唯一执行入口**。以后处理任何
> 瘦身任务只从本文出发，细节通过链接查阅。基线 `hx/0812_live_voice_w3@7c7aad7b8`
> （2026-09-05 14:34 +0200），执行分支 `hx/0905_livevoice_refactor` 已 rebase 到该 tip。
> 按用户决定，Native（OpenAI Realtime）支持作为单独 commit 另行处理，**不在本计划的任何
> 包内**。本文不改变 `STATUS.md` 的产品判断，不授予任何验收或远端更新；每个包落地时仍按
> root `TESTING.md` 单独定级。数字口径是 physical LOC（含空行注释），只作解释线，不是 KPI。

## 0. 如何使用本文

| 你要做的事 | 读本文哪里 | 再查哪份细节 |
|---|---|---|
| 判断现在能不能开工、开工哪些包 | §1.3 触发条件、§5 实施包 A 期 | [激活预检](../reviews/OPENJIUWEN_LIVEVOICE_SLIMMING_ACTIVATION_PRECHECK_2026-09-05.md) |
| 删除臃肿、无用、堆积的代码 | §2 移除清单 | [可去掉性验证](../reviews/OPENJIUWEN_LIVEVOICE_REMOVABILITY_VERIFICATION_2026-09-05.md)、[原子归属表](../reviews/OPENJIUWEN_LIVEVOICE_ATOMIC_DISPOSITION_2026-08-31.md) |
| 对比 Hermes 收敛某个模块 | §3 模块收敛清单、§9.4 拆分行 | [官方 Hermes Voice 对比](../reviews/OPENJIUWEN_LIVEVOICE_OFFICIAL_HERMES_VOICE_COMPARISON_2026-09-06.md)（模块对照、Hermes 术语解释、AgentCore 校准）、[逐模块验证](../reviews/OPENJIUWEN_LIVEVOICE_SLIMMING_THESIS_VERIFICATION_2026-09-05.md)、[零基线模块审计](../reviews/OPENJIUWEN_LIVEVOICE_ZERO_BASE_MODULE_AUDIT_2026-08-31.md)；个人仓库对标的[中文架构指南](../reviews/OPENJIUWEN_LIVEVOICE_HERMES_MODULE_ARCHITECTURE_ZH_2026-08-31.md)只作历史读物 |
| 下沉到 AgentCore（直接复用、适配复用、PR） | §4 | [AgentCore 零基线审计](../reviews/OPENJIUWEN_AGENTCORE_FOUNDATION_ZERO_BASE_AUDIT_2026-09-01.md)、[symbol 迁移映射](../reviews/OPENJIUWEN_LIVEVOICE_SYMBOL_MIGRATION_MAP_2026-08-24.md) |
| 分支又前进了，要重基线 | §8 | `scripts/live_voice/slimming/README.md` |
| 某个包的验收与回滚 | §5、§6 | root `TESTING.md`、[预算文档 §9](../reviews/OPENJIUWEN_LIVEVOICE_HERMES_ALIGNED_SLIMMING_BUDGET_2026-08-31.md) |
| 新增代码的归属 | §9.2 临时 key | [当前分支重分析](../reviews/OPENJIUWEN_LIVEVOICE_CURRENT_BRANCH_ANALYSIS_AND_PLAN_2026-09-05.md) |

准备分支的十四份审计与 PR 准备材料已逐字移植到 `live-voice/reviews/`（每份带来源说明）；
其中提到的 `D-096`/`D-097` 是准备分支自己的决定，见
[摘录](../reviews/PREP_BRANCH_DECISIONS_D096_D097_2026-09-01.md)，与本分支 `DECISIONS.md` 的
同编号决定无关，也未被接受为产品决定。

## 1. 目标与边界

### 1.1 目标形态

```text
common/schema/live_voice/            canonical schema 单源：contract v2、task envelope、semantic pending
                                     context、method catalog → 生成 TS client/types 与 allowlist
server/live_voice/core/   (L1)       conversation runtime + 一个 response fence、speech port/policy、
                                     presentation ledger、speculation、progress 仲裁
gateway/live_voice/       (L2)       薄 dedicated media registration、media transport、streaming
                                     speech/synthesis route、providers/（openai streaming）
server/live_voice/product/(L3)       committed input + semantic、一个 authorization/confirmation owner、
                                     P3 authenticated composition、intent/policy、project executor adapter、
                                     薄 composition root、observability leaf（一个 exporter）
frontend features/live-voice/{core,audio,media,web,task-presentation}
AgentCore (L4)                       existing Agent/Tool/Runner/DeepAgent/Harness + F1–F6 公共能力
tests/ · scripts/ · validation/      L5：oracle、合成语音 journey、探针、重基线脚本
```

五层归属、8 条真实链路与 18 个责任模块的定义见零基线模块审计 §4–§6；本文不重复。

### 1.2 v1 边界

- 范围：Cascade 路径的 LiveVoice 核心（L1/L2/L3）加 AgentCore F1–F6。
- 排除：Native engine、session、contract、carrier、runtime owner、gateway client、downlink，以及
  `dedicated_media_registration.py` 与 registry 内的 Native 段（合计约 12K 行）。它们由单独
  commit 处理；本计划的拆分包只搬不碰这些段。
- `develop` 集成触发仍按 D-084：feature-complete PASS 之后。瘦身在 w3 上落地后再集成，
  避免先合入约 17 万行再删。

### 1.3 触发条件（待用户以 Decision 记录，建议编号 D-116）

| 期 | 触发 | 现在状态 |
|---|---|---|
| A 期（demo 并行） | demo 源码冻结 tag（建议取 A0 启动时的 w3 tip） | 可开工，待 §7.1/§7.2 确认 |
| B 期（结构收敛） | demo 物理验收 PASS 作为行为 oracle | 未达成：STATUS `HUMAN_PHYSICAL_ACCEPTANCE` 仍 FAIL / INCOMPLETE |
| C 期（AgentCore 切换） | F1–F6 accepted 且 installed（uv.lock 锁定新版本） | 未达成：锁定仍是 `openjiuwen 0.1.16@94e10cb6` |
| D 期（收尾） | 全部前置包关闭 | — |

### 1.4 规模口径与预期

| 口径 | 值 | 来源 |
|---|---:|---|
| 当前专属生产文件（不含 Native 8 个文件） | 171,431 行，137 个文件 | `module_buckets.py --rev HEAD` |
| 共享宿主 LiveVoice segment | 4,054（59998e2c 归因）+ 未归因新增约 0.3K | 零基线审计 §3.2；冻结后重算 |
| v1 规划中心 | 约 50,200（18 模块中心之和，Native 行剔除） | §3 表 |
| 实测预期 | 60K 到 65K | 逐模块验证 §1.3：第五种机制约 69K 只确认方向 |
| Hermes 对照 | 官方 `NousResearch/hermes-agent@9a84bee26` 语音生产面 20,265（可比集 17,887，非行为行 32%）；个人仓库 25,254 只作历史 | [官方对比](../reviews/OPENJIUWEN_LIVEVOICE_OFFICIAL_HERMES_VOICE_COMPARISON_2026-09-06.md) §6 |

### 1.5 不变约束

- 一个事实一个 writer；迁移期不得无事务/回滚合同双写；cutover 后旧 owner 不再分配。
- 禁止复制 `SqliteTaskStore`、`PersistentTaskCore`、`_DirectProjectAttemptJournal`；禁止重复
  reducer/verifier；禁止整体 replay 历史 15,128 行 AgentCore 候选。
- 只有原子归属表的 `CONSOLIDATE_RETIRE` 行授权删除，且受各自 gate 约束；`AGENTCORE_PR`
  授权替换，`SPLIT_REQUIRED` 授权拆分，都不授权删除；不按文件路径或 LOC 目标删除。
- 仍有效的测试 oracle 先迁后删；删除不能通过丢失覆盖获得。
- 任何远端更新按 root `AGENTS.md` 逐次精确批准。

## 2. 移除清单（臃肿、无用、开发过程中堆积的内容）

四个 gate 族的定义与逐行证据见可去掉性验证 §2、§4；本节只给执行清单。

### 2.1 现在就能删（G1，零生产 caller）— 包 A1

| 类别 | 内容 | 行数 |
|---|---:|---:|
| 前端参考/替身/未使用合同 | AR-038 `conversationRuntimeReplica.ts` 258、AR-039 `fakeP1Vertical.ts` 104、AR-044 `formalTaskResultRoute.ts` 311、AR-058 `productCompositionContract.ts` 289、AR-070 `webLifecycleObservationRecorder.ts` 383 | 1,345 |
| 后端支持/未组合/未使用 | AR-086 `live_voice_deployment_observer.py` 1,045、AR-087 `live_voice_deployment_preflight.py` 449、AR-092 `live_voice_contract.py`（v1）235、AR-119 `alpha_benchmark.py` 633、AR-120 `alpha_privacy_conformance.py` 1,025、AR-137 `fake_verticals.py` 404、AR-136 `executor_port.py` 117、AR-152 `observability_fault_harness.py` 391、AR-183 `product_p2_readiness.py` 262、AR-194 `realtime_media.py` 822、AR-195 `sli_window_contract.py` 386、AR-210 `telemetry_privacy_contract.py` 221 | 5,990 |
| 混合文件内的死 symbol | AR-228 `LegacyProjectTaskService`/`ProjectCodeExecutorAdapter` 504、AR-198 `TaskCore` 等 13 个 symbol 581、AR-145 离线 L0 collector/report 510、AR-142 `ScriptedCascadeInteractionEngine` 等 286、AR-115 `AgentBridgePort` 等 65 | 1,946 |
| 未量测的 TS 片段 | AR-049 `browserL0Control`、AR-056 `liveVoiceObservability.ts` 的 collector/metric helper | — |
| **合计** | 17 个整文件 + 5 个部分文件 | **9,281** |

执行规则：每项先核对 `package.json` 的 `test:*` 脚本、`scripts/`（含 `s7_alpha_verification.py`、`s7_real_probe_support.py` 对 Alpha 支持模块的 import）、runbook 与动态引用；仍有效的
测试 oracle 迁到 `tests/`、`scripts/` 或 support；静态 import 扫描为零后才删；按文件独立提交。
`task_core.py` 只删本行 13 个 symbol，`TaskState`/`AttemptState`/`TaskCommand`/`TaskSpec` 留到
F1 schema 单源。

### 2.2 legacy 单 owner cutover 后才能删（G2）— 包 D1

| 内容 | 行数 | 前置 |
|---|---:|---|
| legacy 浏览器链：AR-080 `useLiveVoiceDemo.ts` 873、AR-072 `liveVoiceCore.ts` 445、AR-074 `liveVoiceStreamingSpeech.ts` 321、AR-079 `liveVoiceTurnLifecycle.ts` 256、AR-046 `integratedP1Route.ts` 150、AR-032/033 `browserSpeech{Recognition,Synthesis}Adapter.ts` 295、AR-073 `liveVoiceMessageGate.ts` 119 | 2,459 | `ChatPanel` 只构造一套 owner；普通 `vite build` 现在仍渲染 legacy bar，`build:live-voice` 才不渲染 |
| AR-015 `CommandCenter`（`LiveVoiceDemoBar.tsx` 内） | 未量测 | 随上行 |
| L0 批量面板：AR-010 `L0OrdinaryChromeBatchPanel.tsx` 105、AR-050 `l0OrdinaryChromeBatch.ts` 645 | 750 | 见 §7.6；可与 AR-145 一起 re-home |
| AutoHarness 四段：AR-001–004 | 493（审计四段之和） | 先关闭 AgentServer `_handle_schedule_request` 的 `project_code_pipeline` 分支（见 §7.8）并迁 branch oracle |
| AR-065 `ProductTextProgressLegacyDeliveryAck` | 未量测 | 服务端不再发出 legacy 投递 envelope |

### 2.3 AgentCore cutover 后才能删（G3）— 包 C2/C3

AR-169 `PersistentTaskCore` 的本地编排 carrier、AR-208 `task_store.py` 的 v1..v6 迁移与校验
（581 行）、`_DirectProjectAttemptJournal` 在同一 SQLite 文件里的两张表（第二个 writer）。

### 2.4 schema 单源后才能删（G4）— 包 B3

AR-051–054 `liveVoiceContractV2.ts` 2,785 行中除 `parseEventEnvelope` 及其依赖之外的部分；
先拆出活的 parser 或由生成器替换。

### 2.5 已自然退休（只记录，不重建）

AR-126 demo fixture、AR-213 Alpha 意图启发式、AR-075–078 旧 Task lane（2,426 行，`7c7aad7b8`）、`FEATURE_LIVE_VOICE_TASK_DEMO`、`PRODUCT_DEMO_POLICY_BYPASS_ENV`、
关键词/正则分类器、`formal_live_voice.py` 的口语修订策略。残留引用（两个前端测试、
`scripts/live_voice/s7_*`、`start_hands_free_demo.ps1` 的旧 env 名）随 A1 清理。

## 3. 对比 Hermes 的收敛清单（18 个责任模块）

HEAD 实测来自 `module_buckets.py`（文件名规则粗分）；Hermes 列自 2026-09-06 起为官方
`NousResearch/hermes-agent@9a84bee26` 语音可比集 17,887 行按责任分配到 18 模块的值（[官方对比](../reviews/OPENJIUWEN_LIVEVOICE_OFFICIAL_HERMES_VOICE_COMPARISON_2026-09-06.md) §4；
模块 7–11 在 Hermes 语音层为 0，对照改为 core substrate 约 3.3K，见其 §8.1）；目标是规划中心，不是 Gate。

| # | 模块 | HEAD | Hermes | v1 目标 | 收敛机制 | 包 | 确认 |
|---:|---|---:|---:|---:|---|---|---|
| 1 | Browser Audio Edge | 8,429 | 4,671 | 5,500 | 拆 `productP1VoiceRoute.ts`（capture/recognition/playout/diagnostics 混装）；音频诊断归观测 | B2d | 方向确认 |
| 2 | Web/Gateway media transport | 17,409 | 2,070 | 5,500 | 拆 `dedicated_media_registration.py` 为 registration/product authority/diagnostics（Native 段不动）；三条 route 的 lifecycle 与 fallback 投影合一 | B2a | 幅度存疑 |
| 3 | Speech provider | 9,909 | 6,018 | 6,000 | `batch_speech`/`openai_streaming_speech`/`streaming_speech` 各拆 contract、传输、orchestration | B2e | 确认 |
| 4 | Committed input / product authority | 16,850 | 391 | 3,800 | 四套一次性授权 CAS ledger 合成一个 authorization owner + 一个 journal；`p3_authenticated_composition` 拆认证、翻译、构造根 | B2b | 目标偏激进（5K–7K） |
| 5 | Conversation Runtime | 8,224 | 3,150 | 4,500 | 播放期插话与生成期打断合成一个 response fence；fake 退休 | B2c | 确认 |
| 6 | Agent bridge | 3,015 | 36 | 1,300 | `AgentBridgeRuntime` 与 `JiuWenSwarmRoundHarness` 合为一层；tool hold 收敛为一个 rail element（fixture seam 与 ScriptedCascade 已在 A1 删除） | B1 | 确认 |
| 7 | Task domain/control | 5,342 | 0 | 1,000 | 通用值类型归 F1–F3；`TaskCore` 死；`PersistentTaskCore` 成薄 facade | C1 | 确认（需 installed） |
| 8 | Task Store | 15,175 | 0 | 600 | 整个通用 Store 由 F1–F6 替代；只留 importer/rollback reader | C2 | 确认（转移，非删除） |
| 9 | Project executor | 6,755 | 0 | 3,200 | legacy carrier 死；generic attempt/lease/settlement 归 F4/F6；Direct journal 只留 Git/worktree 事实 | C3 | 确认 |
| 10 | Checkpoint/effect | 2,953 | 0 | 800 | prefix verifier 归 F5/F6；六文件复制的 helper 合一；只留 codec/identity 映射 | C3 | 确认 |
| 11 | Task event/progress | 8,078 | 0 | 1,500 | 游标订阅归 F2/F3；arbiter 与 progress_return 的 queue/ACK/lease 机制合一 | C1 + B2b | 目标偏激进（2K–3K） |
| 12 | Presentation/history | 2,045 | 88 | 2,500 | 不需削减 | — | 确认 |
| 13 | Formal Web/UI | 16,906 | 1,372 | 5,600 | 拆 Panel 为 P1/P2/P3 owner；三个 Task UI owner 合一；三本同模式 journal 合一；通知仲裁纯函数独立 | B2d | 目标偏激进（6K–8K） |
| 14 | Composition/config | 19,826 | 75 | 2,700 | registry 只留注册与生命周期；handler 工厂搬回各 owner，删除逐 handler 重复的 scope/session/principal 校验 | B2b | 约 10K 是搬迁，删除量取决于目标模块吸收 |
| 15 | Observability | 17,322 | 16 | 3,500 | 无 caller 支持代码退休（A1）；L0 工具 re-home；OTel/被动 profiling/音频诊断三通道合成一个 exporter，适配已安装 tracer | B4 | 确认 |
| 16 | Schema/protocol | 7,474 | 0 | 2,000 | canonical source 生成 TS client/types 与 allowlist；手写副本退休 | A3/B3 | 确认 |
| 17 | Legacy/compat | 3,058 | 0 | 0 | 单 owner cutover 后退休 | D1 | 确认 |
| 18 | Test/reference in prod | 2,661 | 0 | 200 | 零 caller，先迁 oracle | A1 | 确认 |
| | **合计** | **171,431** | **17,887** | **≈50,200** | | | |

削减按机制分账（逐模块验证 §3.1）：死代码与 legacy 约 12K（已验证）、AgentCore 转移约 25K、
观测收敛约 10K、schema 单源约 5K、并行 owner 与逐层重复校验的收敛约 69K（只确认方向）。

### 3.1 必须完成的收敛项

1. 一个 response fence：播放期插话与生成期打断合并进 `ConversationRuntimeLoop`（Native fence
   留在其单独 commit）。
2. 一个 authorization/confirmation owner：`p3_confirmation`、`product_authority`、
   `production_task_intent` 的确认消费、`unified_committed_input` 的 request binding 与
   semantic pending context 收敛到一个 journal + 一个 CAS。
3. 观测三通道 → 一个 exporter + 一份隐私投影；被动 span 适配已安装
   `agent_teams.observability` tracer。
4. registry 抽出 semantic dispatch（约 600 行）与 P1/P2/P3 handler 工厂；registry 只留注册与
   生命周期。
5. `dedicated_media_registration.py` 抽出 registration / product authority / diagnostics。
6. Panel 抽出 13 个通知仲裁纯函数与 P1/P2/P3 owner；`formalTaskIntentRoute`、
   `formalTaskControlLeaf`、`formalP3TaskExperience` 合为一个 Task UI owner。
7. tool hold 收敛为一个 Jiuwen rail element（基于已安装 `AgentRail.before_tool_call`），删除
   进程本地 gate 注册表。
8. 三条 route lifecycle（streaming speech、streaming synthesis、dedicated media）共用一个
   lifecycle/fallback 投影。
9. 六个 `durability_*` 文件的重复 helper 合一（随 C3）。
10. 十项既有结构债务（零基线审计 §8.2）按上述包吸收，不单列。

## 4. 下沉到 AgentCore

判定规则见 AgentCore 零基线审计 §3：`DIRECT_REUSE`（已安装 public API 拥有生命周期与 truth）、
`ADAPT_REUSE`（已有 primitive 拥有机制，只缺 Jiuwen 映射或窄 Port）、
`AGENTCORE_FOUNDATION_ADD`（原子表的 `AGENTCORE_PR`；语义不依赖 Voice/Project/UI 且 public
API 缺失）、`JIUWEN_KEEP`、`REJECT/RETIRE`。锁定依赖 `openjiuwen 0.1.16@94e10cb6` 至今未变，
已安装包的 `agent_teams`/`core` 中没有 Task outbox / claim lease / consumer cursor 的公开合同。

### 4.1 直接复用（DIRECT_REUSE，14 行）

这些是 LiveVoice 已经在直接调用的既有 seam；动作是**保持直接调用并删除与之竞争的 facade/替身**
（包 B1），不是迁移。

| 行 | 宿主 | 复用的 symbol | 提供方 |
|---|---|---|---|
| AR-219 | `interface_deep.py` | `create_deep_agent`、`attach_output`、`send_input` | 已安装 openjiuwen DeepAgent/Harness |
| AR-221 / AR-223 / AR-216 | `interface.py`、`agent_manager.py`、`agent_adapters.py` | `JiuWenSwarm.process_message_stream`、`AgentManager.get_agent`、`create_adapter` | Jiuwen Agent adapter 生命周期 |
| AR-225 | `session_history.py` | `load/append/truncate_history_records` | Jiuwen Session History |
| AR-094 / AR-098 / AR-108 / AR-005 / AR-006 / AR-008 | `app_gateway.py`、`web_connect.py`、`agent_ws_server.py`、`app_web.py`、`App.tsx`、`ChatPanel/index.tsx` | `GatewayServer`、`WebChannel`、`AgentWebSocketServer`、`_SpaStaticHandler`、`App`、`ChatPanel` | Jiuwen 共享宿主 |
| AR-082 / AR-083 / AR-085 | `supplementOutputQuarantine.ts`、`tts.ts`、`ttsText.ts` | quarantine 工厂、`stopAllTts`/`onTtsStop`、`sanitizeTtsText` | Jiuwen Web TTS/Chat host |

### 4.2 适配复用（ADAPT_REUSE，31 行）

| 组 | 行 | 提供方 | 动作 |
|---|---|---|---|
| 已安装 Agent/Harness 上的薄 adapter | AR-114 `AgentRoundAdapter`、AR-143 `JiuWenSwarmAgentAdapter`、AR-144 `JiuWenSwarmRoundHarness`、AR-192 `ProjectExecutionBinding`、AR-217 `FormalLiveVoiceAgentAdapter`、AR-218 `FormalAgentExecution`、AR-222 `process_formal_live_voice_stream`、AR-224 `get_live_voice_formal_task_agent` | openjiuwen Agent/Tool/Runner/DeepAgent/Harness（installed） | 保留为薄映射；B1 合并 `AgentBridgeRuntime` 与 round harness |
| 未来 AgentCore Task/durability authority 的 consumer adapter | AR-019、040、063、067（前端 Task datasource/RPC）、AR-128/129/131/133/134/135（durability 值/codec 映射）、AR-160/165/168/172/185/199/200/201/203/214（后端 Task 读、投影、游标、命令映射） | 现在 future-only（0.1.16 无对应 public 合同） | C1 后改为 F1–F6 的薄 consumer；在此之前不改 authority |
| 既有 Jiuwen 宿主 seam | AR-097 `web_connect.py` 的 media 路由/脱敏扩展 | Jiuwen WebChannel | 保留，B2a 收窄 |
| 观测 rail 候选 | AR-150 `AsyncLiveVoiceExporter`、AR-156 trace-fact 投影 | 已安装 openjiuwen logging/OTel rail | B4 适配 tracer，一个 exporter |

### 4.3 基础能力新增（AGENTCORE_FOUNDATION_ADD，原子表 `AGENTCORE_PR` 13 行）

13 行是缺口定位，不是实现单元；它们收敛为四个事务能力族、六个最小 public seam。规划中心
约 5,300 行，区间约 3,600–8,100（校准前的分解：约 1,490 适配/扩展 + 约 3,810 真正新增）；这是成本归因线，
不是 Gate。按官方 Hermes core 的后台工作 substrate（约 3,300 行）逐 seam 校准后，建议中心下调到
约 4,100（区间 3,150–5,700），并在 A2 decision record 中评估 F5 并入 F6；见
[官方对比](../reviews/OPENJIUWEN_LIVEVOICE_OFFICIAL_HERMES_VOICE_COMPARISON_2026-09-06.md) §8。

| Seam | 覆盖的 locator | 复用什么 | 只新增什么 | 明确不新增 | 本分支增量补充的 invariant |
|---|---|---|---|---|---|
| F1 Scoped Task/Attempt/Command/Result | AR-089、AR-139、AR-167、AR-206、AR-209，AR-204 的 Task 侧 | `TaskDao`、`TeamTaskManager`、`TeamTaskBase`、Task 状态/依赖图、`DbSessions.write` | `(scope, task)` 约束、Task–Attempt 关系、generation/revision CAS、幂等 command ledger、不可变 result、retry lineage、recover admission | 第二套 Task model/store、Voice envelope、Project spec、纯转发 Manager | selected-but-unbound Attempt 是队列工作（`settle_unbound_queued_attempt`）；派发前先结算取消（`_settle_cancel_before_dispatch`）；同项目未结算 Attempt 拒绝新派发（`project_has_unsettled_attempt`） |
| F2 Transactional Event/Outbox | AR-204、AR-207 的 event 侧，AR-089/139 的 envelope | Task 事务、Scheduler delivery、EventBus/mailbox | per-Task 单调 sequence/head、canonical event、同事务 outbox、claim lease、complete/release/reclaim、dispatch receipt | Voice progress event、Web delivery truth、第二个 Scheduler | claim 续约必须校验完整 binding 与 claimed_at 单调（`renew_outbox_claim`）；busy/capacity defer 是 claim 结果之一 |
| F3 Consumer Cursor | AR-207 | F2 event identity | consumer/channel/scope/stream identity、一行 cursor、expected sequence/version CAS | 重做 prefix verifier、DOM/audio truth | 无变化 |
| F4 Execution Ownership/Cancel/Settlement | AR-127、AR-189、AR-190，AR-167/209 的 recovery | `AsyncToolRuntime`、Runner、`TaskScheduler`、`TaskDao` 事务 | ExecutionRecord、owner lease/heartbeat/epoch、CAS、原子 admission、重复 identity 拒绝、单调 cancel settlement、terminal no-revival、restart reconcile、幂等 terminal callback | `_DirectProjectAttemptJournal` 的 tree/Git/patch/symlink/cleanup 状态；tool hold（§3.1 第 7 项，JIUWEN_KEEP） | settlement fence 独立于不合作 delivery；Executor close 之后、释放 binding 之前 drain，未 settle 即 RESULT_UNKNOWN |
| F5 Checkpoint Publication | AR-127、AR-132、AR-205 | Core `Checkpointer`/`PersistenceCheckpointer`、GraphStore | publication reference、Task/Attempt/execution/source-event 绑定、digest/size/codec 元数据、publish/read verify 事务 | 第二个 payload store、Jiuwen D1 codec、Voice 快照 | 无变化 |
| F6 External-effect Journal | AR-130、AR-132、AR-205 | `ToolCard.idempotent`、Workflow Journal 的 prefix 思路、`AsyncToolRuntime`、统一事务 | provider key/replay policy、one-use authorization、append-only facts、claim lease/version、一个 canonical reducer、unresolved-effect terminal fence、reconcile port | provider credential/request body、真实 Tool 调用、项目 probe/补偿策略 | 读端口：某 scope/resource 最近一次 RESOLVED settlement 及 evidence digest（`latest_completed_project_effect` 的通用形态） |

- **A2 的交付顺序**：每个 seam 先按 AgentCore 零基线审计 §9 提交一份 zero-baseline decision
  record（最近 public owner、被扩展的事务 owner、最小 invariant 与 oracle、Adapter 只映射什么、
  拒绝的历史 candidate symbol、public export 最小性、唯一 codec/digest/reducer、adopter、防双写的
  迁移/canary/rollback、同口径 LOC）；再写代码。工作在 agent-core 仓库进行，LiveVoice 在 installed
  前不改 authority。
- **adoption oracle**：`tests/unit_tests/live_voice/test_persistent_task_core.py`（10,906 行）、
  `test_p3_4_durability_store.py`/`test_p3_4_durability_runtime.py`、`test_project_code_executor.py`
  （5,762 行）中的 race/restart/corruption 用例，加本分支新增的两条 invariant 的用例。
- **拒绝的历史候选**（AgentCore 审计 §7）：God DAO（`task_dao.py` 1.2K→5.3K）、DAO/Authority
  双 reducer/verifier、33 个纯转发 Manager 方法、public export 47→95、无生产 consumer 的
  dispatch drain / checkpoint & effect coordinator / cursor handle、1.6K 行只有两个 public 操作的
  `cursor_dao.py`。[PR 准备材料](../reviews/agentcore-pr-preparation/README.md) 只作 oracle 与
  风险线索。
- **切换顺序**：C1 薄 consumer adapter → C2 single-writer cutover（含 `_DirectProjectAttemptJournal`
  两张表）→ C3 checkpoint/effect 与 executor 拆分。每步 canary 与 rollback 演练通过才推进。

### 4.4 明确不下沉（JIUWEN_KEEP）

原子表 `LIVEVOICE_CORE_KEEP` 16 行（L1）、`CHANNEL_ADAPTER_KEEP` 29 行（L2）、
`JIUWENSWARM_HOST_KEEP` 42 行（L3）全部保留在 jiuwenswarm，见 §9.3 之外的原子表原文。本分支
新增代码里同样全部 `JIUWEN_KEEP`：模型语义（`task_semantics`、`semantic_continuity`、pending
context）、speculative dialogue 与 tool hold、生成期打断、被动 profiling 与音频诊断、口语
finalize、前端 Task 呈现与 home start；理由见当前分支重分析 §3。

## 5. 实施包

每包落地前按 root `TESTING.md` 定级；表中 tier 是提案。所有包不含 Native。

| 包 | capability / 模块 | tier | 依赖 | 范围 | 排除 | 验收 | 回滚 |
|---|---|---|---|---|---|---|---|
| **A0 冻结与文档前置** | Configuration/code/document cleanup | 0 | 用户接受 §7.1/§7.2 | 选定冻结 tag；新增 Decision（触发条件、tool hold 归属）；为 §9.2 的新路径与 segment 定正式 key，拆 AR-212、迁 AR-013；按 symbol 重算 L1–L5 | 任何源码改动 | `git diff --check`、链接解析、authority map 一致、清单覆盖全部专属路径 | 单提交 revert |
| **A1 零 caller 退休** | Test/reference in production；Observability support | 1 | A0 的 key；oracle 已迁 | §2.1 的 9,281 行 | legacy 链（G2）、`liveVoiceContractV2.ts`（G4）、AR-065、L0 面板（待 §7.6） | import 扫描为零、`package.json`/`scripts/`/runbook 引用核对、受影响测试通过、前端 build 通过、demo 路径零改动 | 按文件 revert |
| **A2 AgentCore F1–F6** | Task Control Core / Executor & Durability 的通用 truth（agent-core 仓库） | 3 | AgentCore owner；六份 decision record | §4.3 | 复制 Jiuwen Store/Core/Journal；replay 历史候选；无 adopter 的 export；Voice/Project schema | 非 Voice conformance、race/crash/corruption oracle、public API 最小、独立 review、版本锁定 | agent-core 侧独立版本 |
| **A3 canonical schema 设计** | Schema/protocol | 0→1 | A0 | Python contract v2、semantic pending context、`task_semantic_output_schema`、TS contract v2、method catalog、allowlist 归一为 canonical source 与生成器；等价性测试 | 运行时切换 | 三套 Python 家族与 TS 副本字节/语义等价 | 生成器不接入即无影响 |
| **B1 直接复用与 round owner 合并** | Agent bridge | 2 | A0、A1；demo 物理 PASS | 合并 `AgentBridgeRuntime` 与 round harness；tool hold 收敛为一个 rail element；删除与已安装 seam 竞争的 facade（`AgentBridgePort`、`ScriptedCascade` 已在 A1 删除） | Runner 直调改造 | Agent/Tool 正负场景、生成期打断、speculation 回归；零 Task/history 副作用 | 按包 revert |
| **B2a media registration 拆分** | Web/Gateway media transport | 3 | B1；demo journey + 合成语音脚本 | `dedicated_media_registration.py` → registration / product authority / diagnostics；三条 route lifecycle 合一 | Native 段（只保留原位） | 合成语音 journey、物理 demo journey、reconnect/backpressure/ACK 回归 | 独立提交 revert |
| **B2b registry 与授权 owner 抽取** | Composition；Committed input/product authority | 3 | B1 | registry 抽出 semantic dispatch 与 handler 工厂；四套 CAS ledger 合成一个 authorization owner；`p3_authenticated_composition` 拆三 | Native handler | 正负授权场景、multi-Task、feature-off、refresh/reconnect、零副作用 | 独立提交 revert |
| **B2c 一个 response fence** | Conversation Runtime | 3 | B1 | 播放期插话与生成期打断合并 | Native fence | 两类打断既有用例全过；零 Task/history 副作用 | 独立提交 revert |
| **B2d Panel 与 P1 route 拆分** | Formal Web/UI；Browser Audio Edge | 3 | B1 | Panel → 仲裁纯函数模块 + P1/P2/P3 owner；三个 Task UI owner 合一；`productP1VoiceRoute.ts` 拆 capture/playout/diagnostics | Native activation 段 | 前端单测/mounted 测试等价、journey | 独立提交 revert |
| **B2e Speech provider 与 executor seam** | Speech provider；Project executor | 3 | B1；C3 在其后 | `batch_speech`/`openai_streaming_speech`/`streaming_speech` 各拆 contract/传输/orchestration；executor 的 project seam 与 generic attempt 记录分离 | authority 变化 | Provider fallback、D-113 admission、D0/D2 用例 | 独立提交 revert |
| **B3 协议单源切换** | Schema/protocol | 3 | A3、B2b | caller 切到生成 client/types；删除手写副本（含 `liveVoiceContractV2.ts` 除活 parser 外部分） | 状态值语义变化 | 跨语言 contract 测试、feature-off、multi-Task、refresh/reconnect | 旧 schema 保留一个包周期作 rollback reader |
| **B4 观测收敛** | Observability | 2 | A1 | 三通道 → 一个 exporter；被动 span 适配已安装 tracer；隐私投影单源；L0 工具按 §7.6 处置 | — | 隐私零泄露断言、export 等价、profiling 报告脚本仍可解析 | 独立提交 revert |
| **C1 薄 consumer adapter** | Task Control Core；Executor & Durability | 3 | A0；A2 accepted+installed（uv.lock） | §4.2 第二组改为 F1–F6 consumer；Jiuwen 只留 envelope 投影、Agent 选择、worktree/Git、DOM/audio/history | 双写；第二 reducer | 每项证明最近 public owner、唯一事务、真实 adopter | Adapter 不接入即无影响 |
| **C2 single-writer cutover** | Task Store/outbox/result | 3 | C1；importer；canary | 新 owner 先过共同 oracle，quiesced cutover；旧 Store 与 Direct journal 表停止分配；old-version read | 永久双写；历史候选 replay | migration、old-version read、race/restart/corruption、canary/rollback、零副作用 | 旧 Store 只读保留 + rollback 演练 |
| **C3 checkpoint/effect 与 executor 拆分** | Checkpoint/effect；Project executor | 3 | C2；B2e；F5/F6 installed | 通用 publication/journal/reconcile 下沉；Jiuwen 留 codec/probe/compensation/cleanup；`durability_*` helper 合一 | D1 host-crash 新承诺 | D1/D2 truth、ambiguous effect、crash window、compensation | 同 C2 |
| **D1 legacy 退休** | Legacy/compatibility | 2 | B2d、B3；feature-on/off 证据 | §2.2 全部；先关闭 AgentServer `schedule` 的 `project_code_pipeline` 分支 | 与 formal 共用的 `LiveVoiceDemoBar` 渲染器 | replacement、caller scan、feature-on/off、测试发现率 Gate | 按包 revert |
| **D2 累计验收与计量** | 全部 | 3 | 全部前置 | 完整产品 journey、独立跨模块 review、最终 L1–L5 与多仓口径报告 | — | exact clean source 上自动化、集成、人测、回滚演练 | — |

推荐的校准探针：B 期第一个包（B2c 或 B2a）落地后，用其实际削减比例修正 §3 各模块目标。

## 6. Gate 与验收规则

- 预算文档 §9 八条最低 Gate：replacement 已安装（非本地 worktree）、所有生产 caller 已迁移、
  正向成功且负向失败关闭、Agent/Tool/Task/audio/history/project/受保护状态零副作用、持久化迁移
  与 old-version read、oracle 已迁、root `TESTING.md` 要求的回归与独立审查、STATUS/Decision/
  source/tests/evidence 一致。
- 回归 oracle 集：后端 `tests/unit_tests/live_voice` 98 个文件约 125.6K 行、前端 `tests/*.test.mjs`、`scripts/live_voice/
  semantic_audio_*` 合成语音 journey、物理 demo journey（`demo/PRODUCT_READINESS_SHOWCASE.md`）。
- 结构收敛包只做行为保持的合并与搬迁；一旦需要改语义，按 root `TESTING.md` 重新定界定级，
  不在瘦身包内做。
- 每个包独立提交、独立 revert；远端更新逐次批准。

## 7. 待用户决定

1. 触发条件 Decision（§1.3），建议编号 D-116（D-115 已被“Agent-owned answers and faithful voice delivery”占用）。
2. 冻结 tag：建议取 A0 启动时的 w3 tip。
3. tool hold 归属：建议 JIUWEN_KEEP（一个 rail element），不向 AgentCore 提 F4 扩展。
4. 瘦身先于 `develop` 集成落地。
5. 观测三通道收敛并适配已安装 tracer（会改变离线 profiling 报告的数据源，需同步运行手册）。
6. L0 批量面板与离线 L0 工具（AR-010/050/145 约 1,260 行，另 AR-049 在 `l0Measurement.ts` 内未量测）：随 A1 re-home 到 `scripts/`
   还是保留为批量入口。
7. 部署观测与 preflight（AR-086/087，1,494 行）：删除还是 re-home。
8. 是否允许在 D1 前先关闭 AgentServer `schedule` 的 `project_code_pipeline` 分支。
9. Native 单独 commit 的时间点与范围（本计划不含）。

## 8. 分支前进后的重基线步骤

1. `git fetch` 后把 `hx/0905_livevoice_refactor` rebase 到 w3 tip；只有 docs/launcher 提交时
   不需要下面的步骤。
2. 运行 `scripts/live_voice/slimming/symbol_delta.py <上次 tip> HEAD`；有生产 symbol 变化才继续。
3. 运行 `inventory_loc.py --base 59998e2c5 --head HEAD`、
   `retire_rows.py --rev HEAD --base 59998e2c5`、`module_buckets.py --rev HEAD`。
4. 在激活预检文档末尾追加一段带 commit 范围的 delta；只有判断翻转时才修改本文（§2 清单、
   §3 数字、§4.3 invariant、§9.2 key）。
5. A0 冻结时做一次完整重判（重 key、LOC 重算、目标校准）。

## 9. 附录

### 9.1 文档地图

- 本分支产出：[激活预检](../reviews/OPENJIUWEN_LIVEVOICE_SLIMMING_ACTIVATION_PRECHECK_2026-09-05.md)
  → [计划重适配](../reviews/OPENJIUWEN_LIVEVOICE_SLIMMING_PLAN_REFIT_2026-09-05.md)
  → [当前分支重分析](../reviews/OPENJIUWEN_LIVEVOICE_CURRENT_BRANCH_ANALYSIS_AND_PLAN_2026-09-05.md)
  → [可去掉性验证](../reviews/OPENJIUWEN_LIVEVOICE_REMOVABILITY_VERIFICATION_2026-09-05.md)
  → [逐模块验证](../reviews/OPENJIUWEN_LIVEVOICE_SLIMMING_THESIS_VERIFICATION_2026-09-05.md)
  → 本文 → [官方 Hermes Voice 对比](../reviews/OPENJIUWEN_LIVEVOICE_OFFICIAL_HERMES_VOICE_COMPARISON_2026-09-06.md)
  （2026-09-06；§3 的 Hermes 列与 §4.3 的 AgentCore 校准来自它）。
- 移植的准备审计：[预算](../reviews/OPENJIUWEN_LIVEVOICE_HERMES_ALIGNED_SLIMMING_BUDGET_2026-08-31.md)、
  [AgentCore 零基线审计](../reviews/OPENJIUWEN_AGENTCORE_FOUNDATION_ZERO_BASE_AUDIT_2026-09-01.md)、
  [原子归属表](../reviews/OPENJIUWEN_LIVEVOICE_ATOMIC_DISPOSITION_2026-08-31.md)、
  [零基线模块审计](../reviews/OPENJIUWEN_LIVEVOICE_ZERO_BASE_MODULE_AUDIT_2026-08-31.md)、
  [中文架构指南](../reviews/OPENJIUWEN_LIVEVOICE_HERMES_MODULE_ARCHITECTURE_ZH_2026-08-31.md)、
  [152 路径处置表](../reviews/OPENJIUWEN_LIVEVOICE_MODULE_DISPOSITION_AND_HERMES_COMPARISON_2026-08-25.md)、
  [symbol 迁移映射](../reviews/OPENJIUWEN_LIVEVOICE_SYMBOL_MIGRATION_MAP_2026-08-24.md)、
  [审计计划](../reviews/OPENJIUWEN_LIVEVOICE_ZERO_BASE_MODULE_AUDIT_PLAN_2026-08-31.md)、
  [审计范围](../reviews/OPENJIUWEN_AGENTCORE_HERMES_SLIMMING_SCOPE_2026-08-25.md)、
  [历史执行计划](../reviews/OPENJIUWEN_AGENTCORE_HERMES_SLIMMING_EXECUTION_PLAN_2026-08-25.md)、
  [PR 准备复核](../reviews/OPENJIUWEN_AGENTCORE_PR_PREPARATION_REVIEW_2026-08-25.md)、
  [原型裁定](../reviews/OPENJIUWEN_LIVEVOICE_PROTOTYPE_ADJUDICATION_2026-08-25.md)、
  [历史终审](../reviews/OPENJIUWEN_LIVEVOICE_SLIMMING_FINAL_REVIEW_2026-08-25.md)、
  [PR 准备材料](../reviews/agentcore-pr-preparation/README.md)、
  [准备分支决定摘录](../reviews/PREP_BRANCH_DECISIONS_D096_D097_2026-09-01.md)。
- 产品权威：[STATUS](../STATUS.md)、[DECISIONS](../decisions/DECISIONS.md)（D-084 完成边界、
  D-107 语义退役、D-113 speech lifetime、D-114 生成期打断默认、D-115 Agent 原答与忠实语音投递）、root `TESTING.md`。

### 9.2 新增责任的临时 key（冻结时转正式）

| 临时 key | 路径 | 层 | 处置 | 包 |
|---|---|---|---|---|
| AR-229 | `server/live_voice/task_semantics.py` | L3 | JIUWEN_KEEP | B2b |
| AR-230 | `server/live_voice/semantic_continuity.py` | L3 | JIUWEN_KEEP | B2b |
| AR-231 | `server/live_voice/task_control_presentation.py` | L1/L3 | JIUWEN_KEEP | — |
| AR-232 | `server/live_voice/speculative_dialogue.py` | L1 | JIUWEN_KEEP | B1 |
| AR-233 | `server/runtime/agent_adapter/formal_tool_gate.py` | L3 | JIUWEN_KEEP，与 rail 收敛 | B1 |
| AR-234 | `common/live_voice_profiling.py` | L3 | JIUWEN_KEEP，适配 tracer | B4 |
| AR-235 | `common/live_voice_audio_diagnostics.py` | L3 | JIUWEN_KEEP | B4 |
| AR-236 | `server/live_voice/speech_http_diagnostics.py` | L1 | JIUWEN_KEEP | B4 |
| AR-237 | `server/live_voice/speech_socket_diagnostics.py` | L1 | JIUWEN_KEEP | B4 |
| AR-238 | `server/runtime/agent_adapter/formal_model_diagnostics.py` | L3 | JIUWEN_KEEP | B4 |
| AR-239 | `common/live_voice_capture_limits.py` | schema | JIUWEN_KEEP | A3 |
| AR-240 | `common/live_voice_operation_budgets.py` | schema | JIUWEN_KEEP | A3 |
| AR-241 | 前端 `formal/audioDiagnostics.ts` | L2 | JIUWEN_KEEP | B4 |
| AR-242 | 前端 `formal/audioDiagnosticJournal.ts` | L2 | JIUWEN_KEEP | B4 |
| AR-243 | 前端 `ChatPanel/useProductVoiceSessionStart.ts` | L3 | JIUWEN_KEEP | — |
| AR-244 | 前端 `multi-session/state/createLiveVoiceConversation.ts` | L3 | JIUWEN_KEEP | — |
| AR-245 | 前端 `ToolPanel/RecentTasksPanel.tsx` | L3 | JIUWEN_KEEP | B2d |
| AR-246 | 前端 `stores/liveVoiceTaskStore.ts` | L3 | JIUWEN_KEEP（读路径依赖 ADAPT_REUSE） | B2d/C1 |
| AR-247 | 前端 `features/live-voice/taskPresentationView.ts` | L3 | JIUWEN_KEEP | — |
| AR-248 | 前端 `utils/ttsPlaybackQueue.ts` | L2 | JIUWEN_KEEP | — |
| AR-249 | 前端 `services/messageTtsPlayback.ts` | L2 | JIUWEN_KEEP | — |
| AR-250 | `stream_event_rail.py` 的 `pause_tools`/`resume_tools` 段 | L3 harness | JIUWEN_KEEP（§7.3） | B1 |
| AR-251 | `response_prompt_rail.py` 的 formal section 守卫 | L3 | JIUWEN_KEEP | — |
| AR-252 | `interface_code.py` 的 background project rails 段 | L3 | JIUWEN_KEEP | — |
| AR-253 | `gateway/routing/agent_client.py` 的 profiling 段 | L2/L3 | JIUWEN_KEEP | B4 |
| AR-254 | `common/reasoning_injector.py` 的 `bounded_semantic_request_options` | L3 | JIUWEN_KEEP | — |
| AR-255 | 前端 `ToolPanel/index.tsx`、`buildTurnTimeline.ts`、`webClient.ts`、`newConversationLifecycle.ts` 段 | L3 | JIUWEN_KEEP | — |
| AR-256–263 | Native 8 个文件 | — | **本计划排除** | 单独 commit |

### 9.3 52 条 `CONSOLIDATE_RETIRE` 行的当前状态

| 状态 | 行 |
|---|---|
| 已自然退休 | AR-075、076、077、078、126、213 |
| G1 现在可删 | AR-038、039、044、058、070、086、087、092、119、120、136、137、152、183、194、195、210、228、198、145、142、115；AR-049、056（拆分后） |
| G2 legacy 单 owner 后 | AR-032、033、046、072、073、074、079、080、015、010、050、001–004、065 |
| G3 AgentCore cutover 后 | AR-169、208 |
| G4 schema 单源后 | AR-051、052、053、054 |

### 9.4 31 条 `SPLIT_REQUIRED` 行到包的映射

| 包 | 行 |
|---|---|
| B2a | AR-028、102、157（route/transport/registration 拆分） |
| B2b | AR-159、175、096、110、095、090（构造根、registry、AgentServer/Gateway/Web handler 段、schema 单体） |
| B2c | AR-141（端口与 fake 分离） |
| B2d | AR-007、009、011、016、042、047、059、068、081（Web 挂载、Panel、P1 route、Task control leaf、WebSocket hook 段） |
| B2e | AR-121、193、197、220（batch/streaming speech、executor `_run_attempt`、formal stream facade） |
| B4 | AR-048、055、146、149、151、154、180、181（L0 与观测的 runtime/offline 分离、OTel 组合） |
