# OpenJiuwen LiveVoice 瘦身激活预检与 `59998e2c..ebd2b4575` 增量重基线 — 2026-09-05

> 状态：Integration Owner 预检记录（文档-only 批次；风险按 root `TESTING.md` 的 Live Voice
> risk tiers 与 D-046 的 Tier 0 文档/机械口径）。本文只回答
> 三件事：当前 LiveVoice 特性分支是否已在一个 exact clean commit 上通过
> feature-complete 边界；若未通过，阻塞条件是什么；相对准备基线所用的产品事实
> `59998e2c`，当前 HEAD 的生产 stable symbol 发生了什么变化。本文不实施迁移、
> 不删除代码、不实现 AgentCore 基础能力、不更新任何远端，也不授予任何验收信用。

## 1. 结论先行

1. **当前特性分支没有达到 feature-complete PASS。** `hx/0812_live_voice_w3@ebd2b4575`
   是干净 commit，但 `STATUS.md`（2026-09-04）的项目判断是 `PARTIAL`，五个当前
   acceptance gate 无一为 PASS，`HUMAN_PHYSICAL_ACCEPTANCE` 为 `FAIL / INCOMPLETE`；
   记录该 STATUS 的提交 `408d7304f` 本身就带生产代码，其后又有两次生产代码提交
   （`be0ea0b27`、`ebd2b4575`），且没有任何验收记录绑定 `ebd2b4575`。
2. 因此按用户约束，**本次不启动 S0 增量重基线，不实施 DIRECT_REUSE / ADAPT_REUSE /
   AGENTCORE_FOUNDATION_ADD / JIUWEN_KEEP / CONSOLIDATE_RETIRE 的任何迁移或删除，
   F1–F6 不开工。** 本文只记录阻塞条件与 stable-symbol delta。
3. 执行分支 `hx/0905_livevoice_refactor` 已从 `ebd2b4575` 建立在独立 worktree 上，
   没有 upstream，没有推送；除本文和一条 `REFERENCE_INDEX.md` 路由外没有其他改动。
4. 准备基线 `codex/livevoice-agentcore-hermes-prep@b9dc8a5c` 只存在于远端 `agtai`
   （GitHub），`origin`（AtomGit）上没有该 ref。它未被 merge/cherry-pick，五份
   审计文档也不存在于产品分支；本文按 commit 限定路径引用它们，不复制内容。
5. 相对 `59998e2c`，生产 stable symbol 的增量是**扩张而不是收敛**：专属生产路径
   physical LOC 从 159,210 增至 182,741（+14.8%），新增 27 个专属生产路径、
   至少 8 个 24 宿主清单之外的共享宿主 LiveVoice segment；228 项原子责任中
   117 项所在路径被修改、1 项所在文件被删除，5 个 stable symbol 已不存在（2 项是
   清单本就标记 `CONSOLIDATE_RETIRE` 的自然退休，1 项是 feature flag 退休，2 项是
   `JIUWENSWARM_HOST_KEEP` 责任的迁移/收缩，需要在冻结后重新定 key）。
6. 一个必须先解决的文档冲突：准备分支新增的 `D-096`/`D-097` 与产品分支上已存在的
   `D-096`/`D-097`（L0 普通 Chrome 决定）编号相撞。产品分支从 `59998e2c` 起就有后者。
   在冻结后移植准备分支决定时必须重新编号；在此之前不能在产品分支按编号引用它们。

## 2. Git 事实

按 root `AGENTS.md` 的 resume 检查，在本 worktree 读取：

| 对象 | 事实 |
|---|---|
| 执行 worktree | `.claude/worktrees/lucid-khorana-2dde65`，`git status --short --branch` 干净 |
| 执行分支 | `hx/0905_livevoice_refactor` = `ebd2b457525b58e90380603f1ee6ce560ee77db9`，`@{upstream}` 不存在（按要求报告缺失，不虚构） |
| 特性分支 | `hx/0812_live_voice_w3`，本会话开始时 tip 为 `ebd2b4575`（2026-09-05 00:24 +0200，`perf(live-voice): speculate the dialogue candidate at submit`）；upstream `agtai/hx/0812_live_voice_w3` = `ebd2b4575`（2026-09-05 00:51 push） |
| 主检出（用户工作区） | 本会话期间 `hx/0812_live_voice_w3` 从 `ebd2b4575` 前进到 `e517bcac3`（`8db0a7036`、`3e34c6453`、`e517bcac3` 三个 docs 提交：75 个文件全是 Markdown/YAML，含包内 agent workspace skill 资源与 STATUS/README/AGENTS.md 改写，无 Python/TypeScript 生产代码），相对 `agtai` 为 `ahead 3`，主检出另有过未提交编辑。这些是用户的并发工作，未被本 worktree 纳入；本文的事实只绑定 `ebd2b4575`，执行分支不随之移动 |
| 产品审计基线 | `59998e2c5724257bd410885b35e59e1b37027030`（2026-08-31 17:53 +0200），是 `ebd2b4575` 的祖先，中间 77 个提交 |
| 准备基线 | `b9dc8a5c3a2033d177d6949154be051700fa5a71`（2026-09-01 11:46 +0200）；仅 `agtai/codex/livevoice-agentcore-hermes-prep` 含该提交；本地同名分支停在 `802efcce4`（落后 3 个提交）。与 `hx/0812_live_voice_w3` 的 merge-base 为 `362403cd6`，准备分支独有 33 个提交；`59998e2c` 不是准备分支的祖先，准备审计以 commit object 方式引用它 |
| AgentCore 锁定 | `pyproject.toml` 指向 `agent-core@develop`，`uv.lock` 在 `59998e2c` 与 `ebd2b4575` 同为 `openjiuwen 0.1.16@94e10cb6102c36fe78a64547957c0def97299273`；主仓库 `.venv` 安装的是同一版本。准备审计的 installed/absent 判断没有因锁定变化而失效，但冻结时仍须按届时安装的 public exports 重跑 |

## 3. feature-complete 判定与阻塞条件

D-084 定义 feature complete 为完整 P1/P2/P3、完整 Task 操作/泛化边界、延迟目标、
配置、legacy/Demo authority 退休、广泛验证、竞品缺口决定与跨模块独立 review；
只有它触发 `develop` 集成。`STATUS.md` 当前 gate：

| Gate | STATUS 当前结论 |
|---|---|
| HARDCODE_RETIREMENT | PARTIAL：cutover/removals 存在；完整可达性与 unique-oracle 迁移 review 未闭 |
| SEMANTIC_AND_EXECUTION | PARTIAL：scoped creation/continuity/execution 通过；结果质量与更广业务行为未闭 |
| AUDIO_E2E_DIGITAL | PARTIAL：一条真实 Cascade 分析/委托/文件路径；完整 A/B/A2、离线、非旅行 journey 与 Native 语义业务音频未证 |
| HUMAN_PHYSICAL_ACCEPTANCE | FAIL / INCOMPLETE：后续排练暴露缺陷；当前源码完整麦克风/扬声器 journey 未通过 |
| REGRESSION_AND_REVIEW | PARTIAL：scoped 检查通过；继承的 Registry/Web 失败、受影响迁移与累计独立 review 未闭 |

特性分支在本会话结束时的最新 tip `e517bcac3` 的 STATUS（Updated 2026-09-05，仅指令/文档
同步）仍为 PARTIAL，上述五个 gate 结论逐字不变。

阻塞条件（任一成立即不得启动 S0）：

1. 没有 exact clean commit 绑定 feature-complete PASS。`ebd2b4575` 之后的物理耳机
   验收、A/B/A2 journey、Native 语义业务路径、结果正确性、legacy retirement 审计和
   累计跨模块 review 都在 STATUS 中标记 open。
2. 分支仍在活跃移动。`59998e2c..ebd2b4575` 的 77 个提交中 09-03 至 09-05 占 41 个
   （09-04/05 占 29 个），含 5 次 perf、多次 fix 与 feat；本会话期间特性分支又前进了
   三个 docs 提交。冻结要求一个静止的 commit。
3. 准备分支的 `D-096`/`D-097` 与产品分支的 `D-096`/`D-097` 编号冲突（见 §1.6）。
4. 五份准备审计不在产品分支；用户禁止整体 merge/cherry-pick。冻结后需要单独的、
   经批准的文档移植包（只移植审计/归属/计划，且重新编号决定）。
5. 228 项原子责任需要按 §6 的 delta 重新定 key 后才能作为迁移 locator；当前
   清单对 `ebd2b4575` 已经不完整（27 个新增专属路径、≥8 个新增共享 segment、
   2 项责任迁移/收缩）。
6. F1–F6 的 installed / adaptable / absent 状态必须在冻结时对届时安装的 AgentCore
   public exports 重跑；本文只能确认锁定版本未变。
7. 任何远端更新（包括把本分支或本文推到任何 remote）都需要用户对精确
   remote/ref/commit 的单独确认；本文不请求也不假定该授权。

## 4. `59998e2c..ebd2b4575` 的范围与规模

`physical LOC` 与准备审计同口径：包含空行和注释，只计 Git 跟踪的文本文件。

| 集合 | 文件 | 新增 | 删除 |
|---|---:|---:|---:|
| 全部 | 286 | 86,276 | 11,408 |
| 生产（`jiuwenswarm/`，含前端 `src/`，不含前端 `tests/`） | 107 | 32,206 | 7,605 |
| `scripts/live_voice` 支持脚本 | 14 | 2,645 | 40 |
| 顶层 `tests/` | 78（新增 41、修改 37） | 30,525 | 2,310 |
| 前端 `jiuwenswarm/channels/web/frontend/tests/` | 21（新增 7、修改 14） | 8,623 | 297 |
| 文档（`live-voice/`、`docs/`、`AGENTS.md`） | 66 | 12,277 | 1,156 |

其中 `DECISIONS.md` 新增 729 行（D-098 至 D-113），新增 Native Interaction Engine
架构文档与四份 `docs/superpowers` 计划，`PRODUCT_READINESS_ACCEPTANCE.md`、
`E2E_RUNBOOK.md`、`ARCHITECTURE_CONTRACT_GATE_V1.md` 各有增量。

### 4.1 可归因生产 LOC 重算

| 口径 | `59998e2c` | `ebd2b4575` | 说明 |
|---|---:|---:|---|
| 128 个专属路径整文件 | 159,210 | 171,286 | 127 个仍存在；`demo_fixture_contract.py` 已删除 |
| 新增专属生产路径（27） | 0 | 11,455 | 见 §6.4 |
| **专属生产合计** | **159,210** | **182,741** | +23,531，+14.8% |
| 24 个共享宿主 LiveVoice segment | 4,054 | 未重算（沿用 4,054） | 24 个宿主整文件 57,588 → 58,293（+705），segment 归因需冻结后按 symbol 重做 |
| 24 宿主之外新增 LiveVoice segment | 0 | 未归因 | ≥8 个文件，整文件增量合计约 290 行（上限） |
| **可归因生产 footprint** | **163,264** | **≈186,795（182,741 + 沿用的 4,054）+ ≤~1,000 未归因** | 与规划区间 36,600–56,900 的距离扩大，不是缩小 |
| 新增 `scripts/live_voice` 支持文件（9：8 个 `.py` 共 2,341 行，另 1 个 `.ps1`） | — | 2,341 | L5 support，不计入生产 |

本口径复算得到的 `59998e2c` 专属合计恰为准备审计记录的 159,210，证明专属/共享
集合划分与审计一致。

### 4.2 规模集中点的变化

| 文件 | `59998e2c` | `ebd2b4575` | 变化 |
|---|---:|---:|---:|
| `product_composition_registry.py` | 14,015 | 15,742 | +1,727 |
| `task_store.py` | 14,951 | 15,109 | +158 |
| `LiveVoiceIntegratedRoutePanel.tsx` | 7,527 | 9,346 | +1,819 |
| `dedicated_media_registration.py` | 4,311 | 7,276 | +2,965 |
| `project_code_executor.py` | 6,491 | 6,694 | +203 |
| `p3_authenticated_composition.py` | 4,896 | 5,361 | +465 |
| `agent_conversation_runtime.py` | 3,791 | 4,937 | +1,146 |
| `productP1VoiceRoute.ts` | 2,787 | 4,099 | +1,312 |

准备审计记录的四个最大专属文件（registry、`task_store.py`、Panel、`project_code_executor.py`）
合计 42,984（审计原文写 42,985）→ 46,891；按 `ebd2b4575` 重排，`dedicated_media_registration.py`
已超过 `project_code_executor.py`，当前四个最大文件合计 47,473。准备审计披露的第 8 项结构债务
（`dedicated_media_registration.py` 的 registration/registry/diagnostics/product
authority 混合）在 Native 集成后加重了约 69%。

## 5. 方法与局限

- 责任清单来自 `b9dc8a5c3:live-voice/reviews/OPENJIUWEN_LIVEVOICE_ATOMIC_DISPOSITION_2026-08-31.md`
  的 152-path coverage index 与 228-row register（解析得到 152 路径、228 行、
  八个 canonical code 计数与原文一致）。
- 共享宿主 24 路径按 `OPENJIUWEN_LIVEVOICE_ZERO_BASE_MODULE_AUDIT_2026-08-31.md` §3.2
  的表识别；其余 128 路径按整文件计。
- symbol delta 用 Python `ast` 取顶层 class/def、类方法（`Class.method`）和大写
  常量；TypeScript 取 `export` 声明。这是生产 symbol 的粗粒度变化面，不是
  caller 级归因。
- stable-symbol 复验只检查 register 中每个名字是否仍以词形出现在 `ebd2b4575`
  的同一路径文本中（`Class.method` 两段都需出现）。它能发现删除和迁移，不能
  证明语义未变；语义复验属于冻结后的 S0。

## 6. Stable-symbol delta

### 6.1 已清单路径

| 状态 | 路径数 | 原子行 |
|---|---:|---:|
| 修改 | 62（专属 51、共享 11） | 117 |
| 删除 | 1（`server/live_voice/demo_fixture_contract.py`） | 1（AR-126） |
| 未变 | 89 | 110 |

被修改与被删除路径上的 118 行共 317 个 stable symbol token（范围写法 `a..b` 拆成两端计数）
中 312 个仍在原路径；5 个不存在：

| 原子行 | code | 缺失 symbol | 判读 |
|---|---|---|---|
| AR-126 | `CONSOLIDATE_RETIRE` | `DEMO_ITINERARY_TASK_NAME` | 文件已删除；责任自然退休，按 §7 规则只记事实，不重建 |
| AR-213 | `CONSOLIDATE_RETIRE` | `BoundedAlphaTaskIntentResolver` | D-107 生产语义退役已删除 Alpha 启发式；自然退休 |
| AR-024 | `JIUWENSWARM_HOST_KEEP` | `FEATURE_LIVE_VOICE_TASK_DEMO` | 该 flag 退休，新增 `FEATURE_LIVE_VOICE_GENERATION_INTERRUPTION`；2 个前端测试文件与 `scripts/live_voice` 的 2 个脚本仍引用旧 env 名，属清理候选 |
| AR-013 | `JIUWENSWARM_HOST_KEEP` | `FormalP3TaskExperiencePanel` | 底部手工 Registry 表单移除；“最近任务”改由 `ToolPanel/RecentTasksPanel.tsx` 读取 scoped owner。责任迁移，需冻结后重 key |
| AR-212 | `JIUWENSWARM_HOST_KEEP` | `ResolvedUnifiedCommittedInput` | `voice_task_bridge.py` 由 1,447 行收缩到 197 行，`resolve`/`resolve_unified`/Port 全部移除，只剩 `VoiceTaskBridge.map`（AR-214）。“committed-input 语义路由与 Task 目标解析”责任已迁到 `task_semantics.TaskSemanticResolver`、registry `_resolve_semantic_input` 与 `unified_committed_input` 的 semantic context。AR-212 必须拆分/重 key |

被修改的 62 个路径中，生产 symbol 变化最大的（数字为 physical LOC 与顶层/类成员 symbol 增减）：

| 路径 | 原子行 | LOC | symbol |
|---|---|---:|---|
| `dedicated_media_registration.py` | AR-101、AR-102 | 4,311 → 7,276 | +55（Native downlink/barge fence/replay/transcript） |
| `product_composition_registry.py` | AR-175、AR-176 | 14,015 → 15,742 | +39 / −14（语义分派、speculation、native delegate；移除 `_PendingTaskIntent`、frozen one-current-task 与 `PRODUCT_DEMO_POLICY_BYPASS_ENV`） |
| `agent_conversation_runtime.py` | AR-117、AR-118 | 3,791 → 4,937 | +24（generation interruption、native delegate/history、speculation） |
| `conversation_runtime_loop.py` | AR-122、AR-123 | 1,238 → 1,540 | +14（`interrupt_generation`、`commit_native_turn`、`seal_presentation`） |
| `streaming_speech.py` | AR-197 | 2,110 → 2,230 | +17 / −2（D-113 `SpeechStreamAuthority`/`SpeechResponseAuthority`，删除累计 identity 配额） |
| `unified_committed_input.py` | AR-211 | 1,095 → 1,694 | +15（D-107 semantic context journal） |
| `p3_authenticated_composition.py` | AR-159–161 | 4,896 → 5,361 | +16 / −2（Native P3 activation authority、语义解析入口；删除 demo bypass/checkpoint env） |
| `formal_live_voice.py` | AR-218 | 163 → 495 | +12（spoken answer finalize/revision） |
| `interface.py` | AR-221、AR-222 | 3,423 → 3,487 | +5（`pause/resume/abort_formal_tools`、`supports_speculative_dialogue`） |
| `LiveVoiceIntegratedRoutePanel.tsx` | AR-017–020 | 7,527 → 9,346 | +13 / −2（Task notification playout/arbitration） |
| `productP1VoiceRoute.ts` | AR-059 | 2,787 → 4,099 | +7（Native activation/audio input/chat projection） |
| `browserAudioIOAdapter.ts` | AR-025–027 | 2,183 → 2,860 | +11（verified-headset local barge-in profile） |
| `voice_task_bridge.py` | AR-212–214 | 1,447 → 197 | −22 |
| `production_task_classifier.py` | AR-186 | 578 → 162 | −13（`classify_natural` 与正则目标提取移除，只剩 `parse_structured`） |
| `useLiveVoiceDemo.ts` | AR-080 | 1,337 → 873 | 收缩但仍被 `ChatPanel/index.tsx` 构造；legacy owner 未退休 |
| `openai_streaming_speech.py` | AR-157 | 2,738 → 2,921 | +2 / −6：`RealtimeSocket` 与 socket factory 迁入新文件 `openai_realtime_session.py`，属 AR-157 拆分的一步 |

### 6.2 13 个 `AGENTCORE_PR` locator

D-097 把这些行读作 `AGENTCORE_FOUNDATION_ADD` 的缺口定位，不是实现单元。8 个物理
容器中 4 个未变，4 个有增量；13 行的 stable symbol 全部仍在：

| 容器 | 原子行 | 变化 | 对 F1–F6 的含义 |
|---|---|---|---|
| `common/schema/live_voice_contract_v2.py` | AR-089 | 未变 | — |
| `durability_authority.py` / `durability_effects.py` / `durability_readers.py` | AR-127 / AR-130 / AR-132 | 未变 | — |
| `formal_task_models.py` | AR-139 | 10 行改动，无 symbol 增减 | — |
| `task_store.py` | AR-204、AR-205、AR-206、AR-207、AR-209 | +`SqliteTaskStore.renew_outbox_claim`、+`settle_unbound_queued_attempt` | 确认 F2 需要 claim lease 续约、F1/F4 需要 unbound queued attempt 的恢复结算；只是缺口更具体，不新增能力族 |
| `persistent_task_core.py` | AR-167 | +11：`_AdjustmentDeliveryOwner`、`_deliver_outbox`、`_fence_adjustment_delivery`、`_own_adjustment_settlement`、`_reap_adjustment_deliveries`、`drain_inflight_adjustments` 等 | D-100/D-112 的有界调整投递落在 K2/K3（F2 outbox claim + F4 settlement）；AR-167 的 locator 范围扩大，仍禁止复制 `PersistentTaskCore` |
| `project_code_executor.py` | AR-189 / AR-190 | +`_DirectProjectAttemptJournal.latest_completed_project_effect`、+`DirectProjectManagedBaselineReader`、+`_relocate_result_artifact_paths`、+`_LEGACY_DIRECT_D0/D2_CAPABILITY_PROFILE` | D-098 的“精确受管前序效果”是 F6 的 Jiuwen 侧 consumer，不下沉；legacy capability profile 是 v1 记录不得授权 v2 dispatch 的过渡物，`CONSOLIDATE_RETIRE` 候选 |

结论：F1–F6 四个能力族、六个 seam 的划分没有被增量推翻；增量只把 F2 claim-lease
续约和 F4 queued-attempt 结算写得更明确。约 5,300 / 3,600–8,100 的规划中心与区间
不需要因本 delta 调整。

### 6.3 24 宿主之外新增的共享宿主 LiveVoice segment

这些文件不在 152-path 清单中，但增量带有 LiveVoice 专属 symbol/segment，冻结后
需要新的 stable key 与 segment 归因：

| 共享宿主 | 新增 segment | 整文件增量 | 临时归类 |
|---|---|---:|---|
| `agents/harness/common/rails/stream_event_rail.py` | `JiuSwarmStreamEventRail.pause_tools` / `resume_tools` / `_get_tool_pause_event`（speculative candidate 的 tools-only pause） | +28 | 待定：若 AgentCore owner 认为通用 tool-pause 属于 `AsyncToolRuntime` cancel/pause seam（AgentCore 零基线审计 §6 F4 的“cancellation fence 留在 AsyncToolRuntime”），则为 `ADAPT_REUSE`；否则 `JIUWEN_KEEP`。这是冻结时需要 AgentCore owner 决定的边界 |
| `agents/harness/common/rails/response_prompt_rail.py` | `formal_live_voice_presentation` section 存在性守卫 | +4 | `JIUWEN_KEEP` |
| `server/runtime/agent_adapter/interface_code.py` | `BACKGROUND_PROJECT_RESULT_INSTRUCTIONS`、`_disable_background_project_non_file_rails`、`_configure_background_project_result_prompt`、`_cleanup_failed_background_project_session` | +171 | `JIUWEN_KEEP`（Project executor 的 Jiuwen Agent 选择/rails 策略） |
| `gateway/routing/agent_client.py` | `@profiled('gateway.agent_rpc')` 与 unary 隔离修正 | +8 | `JIUWEN_KEEP`（Observability leaf） |
| `common/reasoning_injector.py` | `bounded_semantic_request_options` | +28 | `JIUWEN_KEEP`（model policy） |
| 前端 `components/ToolPanel/index.tsx` | `RecentTasksPanel` 挂载与 scoped Task 选择 | +15 | `JIUWEN_KEEP` |
| 前端 `features/chatTimeline/buildTurnTimeline.ts` | `isTaskNotification`（按 Task presentation owner 铸造的 id 命名空间识别） | +23 | `JIUWEN_KEEP`（Presentation/history） |
| 前端 `services/webClient.ts` | `live_voice.*` RPC 的 audio diagnostics profiling | +12 | `JIUWEN_KEEP`（Observability） |
| 前端 `multi-session/state/newConversationLifecycle.ts` | `processing` 参数 | +1 | `JIUWEN_KEEP` |

不归因给 LiveVoice 的同批宿主改动：`common/utils.py`、`dotenv_early.py`、
`start_services.py` 的 `JIUWENSWARM_CONFIG_DIR` 显式配置目录（受控启动器隔离，
属 Jiuwen host 通用配置）；`agents/harness/agent_observability.py` 的 import 路径修正。

### 6.4 新增专属生产路径（27，11,455 LOC）与临时归类

临时归类只用用户指定的五个执行码，作用是冻结后 S0 的起点，不是处置决定。
责任模块名沿用准备预算的 18 模块表。

| 新路径 | LOC | 来源决定 | 责任模块 / 层 | 临时归类 |
|---|---:|---|---|---|
| `server/live_voice/native_interaction_runtime.py` | 1,485 | D-101–D-103 | Conversation Runtime / L1 | `JIUWEN_KEEP` |
| `server/live_voice/native_interaction_contract.py` | 852 | D-101–D-103 | Schema/protocol / L1 | `JIUWEN_KEEP`；S6 单源 schema 合并对象 |
| `server/live_voice/native_interaction_carrier.py` | 507 | D-102 | Schema/protocol 跨进程 carrier / L2–L3 | `JIUWEN_KEEP` |
| `server/live_voice/native_interaction_config.py` | 111 | D-101 | Composition/configuration / L3 | `JIUWEN_KEEP` |
| `server/live_voice/openai_realtime_native_engine.py` | 2,350 | D-101–D-103 | Speech provider layer / L1 | `JIUWEN_KEEP`；单文件 2,350 行，S5 拆分观察对象 |
| `server/live_voice/openai_realtime_session.py` | 1,073 | D-101 | Speech provider transport / L1–L2 | `JIUWEN_KEEP`；吸收了 AR-157 的 `RealtimeSocket` |
| `gateway/live_voice/native_interaction_runtime_client.py` | 1,089 | D-102 | Web/Gateway media transport / L2 | `JIUWEN_KEEP` |
| `gateway/live_voice/native_response_downlink.py` | 291 | D-103 | Web/Gateway media transport / L2 | `JIUWEN_KEEP` |
| `server/live_voice/task_semantics.py` | 1,207 | D-107、D-111 | Committed input/product authority / L3 | `JIUWEN_KEEP`（model-only，无 Task/Tool/history writer） |
| `server/live_voice/semantic_continuity.py` | 255 | D-107、D-109、D-110 | Committed input/product authority / L3 | `JIUWEN_KEEP` |
| `server/live_voice/task_control_presentation.py` | 47 | D-112 | Presentation / L1–L3 | `JIUWEN_KEEP` |
| `server/live_voice/speculative_dialogue.py` | 407 | `ebd2b4575` | Conversation Runtime + Agent bridge / L1–L3 | `JIUWEN_KEEP`；依赖 §6.3 的 tool-pause seam 决定 |
| `server/runtime/agent_adapter/formal_tool_gate.py` | 75 | `ebd2b4575` | Agent bridge / L3（进程本地） | `JIUWEN_KEEP`，同上待 AgentCore owner 决定是否改为 `ADAPT_REUSE` |
| `common/live_voice_profiling.py` | 221 | 2026-09-04 profiling 包 | Observability runtime leaf / L3（被 15 个生产模块引用） | `JIUWEN_KEEP` |
| `common/live_voice_audio_diagnostics.py` | 168 | 同上 | Observability / L3 | `JIUWEN_KEEP` |
| `server/live_voice/speech_http_diagnostics.py` | 63 | 同上 | Speech provider diagnostics / L1 | `JIUWEN_KEEP` |
| `server/live_voice/speech_socket_diagnostics.py` | 210 | 同上 | Speech provider diagnostics / L1 | `JIUWEN_KEEP` |
| `server/runtime/agent_adapter/formal_model_diagnostics.py` | 320 | 同上 | Agent bridge diagnostics / L3 | `JIUWEN_KEEP` |
| `common/live_voice_capture_limits.py` | 10 | D-105/D-113 | Schema/protocol 常量 | `JIUWEN_KEEP` |
| `common/live_voice_operation_budgets.py` | 13 | D-107 | Schema/protocol 常量 | `JIUWEN_KEEP` |
| 前端 `features/live-voice/formal/audioDiagnostics.ts` | 326 | profiling 包 | Browser Audio Edge diagnostics / L2 | `JIUWEN_KEEP` |
| 前端 `features/live-voice/formal/audioDiagnosticJournal.ts` | 88 | 同上 | Browser Audio Edge / L2 | `JIUWEN_KEEP` |
| 前端 `components/ChatPanel/useProductVoiceSessionStart.ts` | 99 | 2026-09-03 home start | Formal Web/UI / L3 | `JIUWEN_KEEP` |
| 前端 `multi-session/state/createLiveVoiceConversation.ts` | 55 | 同上 | Formal Web/UI / L3 | `JIUWEN_KEEP` |
| 前端 `components/ToolPanel/RecentTasksPanel.tsx` | 62 | 2026-09-03 recent tasks | Formal Web/UI / L3 | `JIUWEN_KEEP`；承接 AR-013 迁移 |
| 前端 `stores/liveVoiceTaskStore.ts` | 42 | 同上 | Task presentation datasource / L3 | `JIUWEN_KEEP`，读取路径与 AR-019/AR-040 同为 `ADAPT_REUSE` 依赖 |
| 前端 `features/live-voice/taskPresentationView.ts` | 29 | 同上 | Presentation / L3 | `JIUWEN_KEEP` |

新增 9 个 `scripts/live_voice` 文件（8 个 `.py`：`analyze_demo_profile.py`、`artifact_quality_probe.py`、
`semantic_audio_{assertions,browser,journey,runtime}.py`、`semantic_model_probe.py`、
`task_control_model_probe.py`，共 2,341 行；另有 `prepare_semantic_audio.ps1`）已在支持树内，是 L5 support；S7 时按
“仍有效 oracle 先迁后删”的规则处理，不计入生产 footprint。

没有任何新增路径被临时归为 `DIRECT_REUSE` 或 `AGENTCORE_FOUNDATION_ADD`：增量全部
是 Voice/Provider/Product/Web/诊断责任，没有新增通用 Task/Event/Execution truth。

### 6.5 自然退休与收敛事实

以下事实按准备 handoff §7.8 只记录，不重建兼容层：

- `demo_fixture_contract.py`（AR-126）删除；`BoundedAlphaTaskIntentResolver`（AR-213）
  删除；`PRODUCT_DEMO_POLICY_BYPASS_ENV` 与 `_DEMO_ADJUSTMENT_CHECKPOINT_ENV` 从
  registry、`batch_speech.py`、`p3_authenticated_composition.py` 全部移除，生产树内
  已无 demo bypass 环境开关。
- `FEATURE_LIVE_VOICE_TASK_DEMO` 退休；`production_task_classifier.py` 的自然语言分类
  与正则目标提取移除（D-107）。
- `useLiveVoiceDemo.ts` 收缩 464 行但仍由 `ChatPanel/index.tsx` 第 1240 行构造；
  AR-080 的 legacy owner 退休 gate 未关闭，feature gate 仍不等于单一 runtime owner。
- 前端测试 `liveVoiceBuildProfiles.test.mjs`、`liveVoiceIntegratedRoutePanelMounted.test.mjs`
  仍引用 `VITE_FEATURE_LIVE_VOICE_TASK_DEMO`，`scripts/live_voice/s7_alpha_verification.py` 与
  `start_hands_free_demo.ps1` 也仍引用该 env 名，属 S7 清理候选。

## 7. 冻结后 S0 必须补齐的事项

1. 在冻结 commit 上重跑本文 §5 的复验与 §4.1 的 LOC 重算，并把 24 宿主 segment
   与 §6.3 的新 segment 按 symbol 重新归因。
2. 为 27 个新增专属路径与 ≥8 个新增 segment 创建新的 stable key；拆分 AR-212、
   迁移 AR-013；关闭 AR-126、AR-213 与 AR-024 的退休 symbol。
3. 移植准备分支的审计/归属/计划文档时重新编号 `D-096`/`D-097`，并修复所有
   跨文档引用；不整体 merge/cherry-pick。
4. 对届时安装的 AgentCore public exports 重跑 F1–F6 的 installed / adaptable /
   absent 判断，并向 AgentCore owner 提交 §6.3 的 tool-pause seam 归属问题。
5. 只有上述完成、且 feature-complete PASS 绑定同一 exact clean commit 后，才能
   生成依赖有序的 S1–S8 实施包。

## 8. 本文不授予什么

本文不是 feature-complete 判定的替代，不是产品验收，不是迁移/删除许可，不是
AgentCore 能力接受，不是 LOC 目标，也不是远端更新授权。它只固定 2026-09-05 对
`ebd2b4575` 的预检事实与 delta；准备基线的五份审计（Hermes 对齐预算、AgentCore
零基线审计、原子归属表、零基线模块审计、中文架构指南）继续作为
`agtai/codex/livevoice-agentcore-hermes-prep@b9dc8a5c` 上的唯一入口与事实来源。
