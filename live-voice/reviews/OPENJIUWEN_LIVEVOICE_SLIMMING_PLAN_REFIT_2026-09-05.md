# OpenJiuwen LiveVoice 瘦身计划重适配（demo 冻结前提）— 2026-09-05

> 2026-09-05 更新：本文 §3 规划区间与 §4 实施包由同日
> [当前分支重分析与计划更新](OPENJIUWEN_LIVEVOICE_CURRENT_BRANCH_ANALYSIS_AND_PLAN_2026-09-05.md)
> 修订（只列变化的行与包，未列出的继续以本文为准）；§2 前提核对、§5 A1 清单、§6 约束与 §7 决定清单继续有效。
>
> 状态：Integration Owner 的计划重适配提案（文档-only 批次；root `TESTING.md` Live Voice
> risk tiers 与 D-046 的 Tier 0 口径）。前提由用户给出：`hx/0812_live_voice_w3` 已合入
> 全部特性，正在准备 demo，代码基本不会大改。本文回答“原瘦身计划是否仍然成立、哪些
> 要改、改完后的计划是什么”。它不实施迁移、不删代码、不实现 AgentCore 能力、不更新
> 远端；§7 列出的产品边界决定仍由用户作出。事实基线见同日的
> [激活预检](OPENJIUWEN_LIVEVOICE_SLIMMING_ACTIVATION_PRECHECK_2026-09-05.md)。

## 1. 结论先行

1. **计划骨架仍然成立。** 五层归属（L1 Core / L2 Channel / L3 Host / L4 AgentCore / L5
   transition）、228 项原子责任的处置码、AgentCore 的四个事务能力族与 F1–F6 六个最小
   seam、S0–S8 的包边界、single-writer / canary / rollback / 删除 Gate，都没有被
   `59998e2c..ebd2b4575` 的增量推翻。增量新增的 27 个专属路径没有一个引入新的通用
   Task/Event/Execution truth，所以 AgentCore 下沉范围不变。
2. **四件事必须改。** (a) 触发条件：原计划以 feature-complete PASS 触发 S0，现在改为
   “demo 源码冻结 tag”触发准备期工作、“demo 物理验收 PASS”触发行为保持型重构，
   `develop` 集成触发（D-084）不变；(b) 基线数字：可归因生产 footprint 从 163,264 增到
   约 187K，18 模块规划区间要按新增责任重推；(c) 顺序：demo 期只做不触碰 demo 热路径
   的包，巨型文件拆分和 authority cutover 排在 demo 验收之后；(d) 两项文档前置：准备
   分支 `D-096`/`D-097` 重编号、五份准备审计以独立文档包移植。
3. **现在就能开始的部分是明确的、demo-safe 的：** 约 9,450 行没有任何生产 importer 的
   代码退休（先迁 oracle 再删）、AgentCore F1–F6 在 agent-core 仓库内的零基线决定记录
   与实现、canonical schema 单源生成设计、以及冻结/重 key/文档移植。它们都不改 demo
   运行路径。
4. **现在不能开始的部分也明确：** 四个巨型文件的拆分需要 demo 物理 journey 作为行为
   oracle，而它目前是 FAIL；Task/Store/Event 的 single-writer cutover 需要 accepted 且
   installed 的 AgentCore public capability，而锁定仍是 `0.1.16@94e10cb6`。
5. 重推后的 18 模块规划中心约 **54,900**，区间约 **43,900–68,700**（原 45,100 /
   36,600–56,900）；相对当前约 187K 仍是约 −70% 的规模级目标。与原计划一样，这是
   偏差解释线，不是删除 KPI。

## 2. 前提核对：代码是否真的“基本不大改”

| 证据 | 事实 |
|---|---|
| w3 在 `ebd2b4575` 之后的移动 | 到 `e517bcac3` 共 3 个 docs 提交、75 个文件，全部 Markdown/YAML（含包内 agent workspace skill 资源），无 Python/TypeScript |
| 最近窗口（09-04/05，29 个提交）对巨型文件的触碰 | registry 2、Panel 1、`dedicated_media_registration.py` 2、executor 1、`agent_conversation_runtime.py` 1、`task_store.py` 0；相比整个 77 提交窗口的 18/24/7/6/4/2 明显降温 |
| STATUS 在 `e517bcac3` | 仍为 PARTIAL；五个 gate 逐字不变，HUMAN_PHYSICAL_ACCEPTANCE 为 FAIL / INCOMPLETE |
| 仍会变的地方 | demo 排练暴露的修复（耳机插话、结果正确性、通知呈现）会继续落在 registry、Panel、`dedicated_media_registration.py`、`agent_conversation_runtime.py` 这四个文件上 |

判断：源码可以作为“冻结候选”对待，但行为验收 oracle 还没有冻结。这决定了 §4 的
分期：先做与热路径无关的包，热路径重构等 demo PASS。

## 3. 计划逐模块符合性与规划区间重推

数字沿用准备预算的 physical LOC 口径，是激活时规划假设，不是当前模块 LOC，也不是
完成 Gate。“增量事实”来自预检 §6；“重推中心”只解释新增责任，不预设 owner 总量。

| 责任模块 | 原中心（区间） | `59998e2c..ebd2b4575` 增量事实 | 重推中心（区间） | 判断 |
|---|---:|---|---:|---|
| Browser Audio Edge | 5,000（4.5–5.5K） | verified-headset 本地插话候选/tentative pause（+11 symbol）、浏览器音频诊断 414 行 | 5,500（5.0–6.0K） | 符合；近端候选是 Hermes 没有的真实责任 |
| Web/Gateway media transport | 4,200（3.5–5K） | `dedicated_media_registration.py` 4,311→7,276（Native downlink/barge fence/replay）；Native gateway client 1,089 + downlink 291 | 5,500（4.5–6.5K） | 符合但债务加重；Native 下行必须复用 synthesis downlink leaf，否则再 +1.5K |
| Speech provider layer | 5,800（5–6.5K） | D-113 stream/response authority（+17 symbol）、HTTP/socket 诊断 273 行；`RealtimeSocket` 迁出到 realtime session | 6,000（5.2–7.0K） | 符合 |
| **Native interaction engine（新增行）** | — | engine 2,350 + session 1,073 + contract 852 + carrier 507 + runtime owner 1,485 + gateway client/downlink 1,380 = 7,758 | 4,500（3.0–5.5K） | Hermes 对应 realtime Provider adapter + `LiveGatewaySession` 局部；contract/carrier 并入 canonical schema，runtime owner 与 Conversation Runtime 共用 fence |
| Committed input / product authority | 3,600（3–4.5K） | D-107 单一模型语义路径（`task_semantics` 1,207、continuity 255、journal +599）；关键词/正则分类器退役（−1,660） | 3,800（3.2–4.8K） | 符合且方向正确：hardcode 退役已发生，产品策略仍在 Jiuwen |
| Conversation Runtime | 3,500（3–4.5K） | 生成期打断（+14 symbol）、speculative dialogue 407、Native admission | 4,500（3.8–5.5K） | 符合；三项都是真实 turn/response 责任 |
| Agent Bridge | 1,000（0.7–1.3K） | spoken finalize/revision 495、model diagnostics 320、tool gate 75、`interface_code.py` background rails +171 | 1,500（1.1–2.0K） | 符合；仍是 committed context + Jiuwen Agent 选择 + 薄投影 |
| Task domain/control | 1,000（0.7–1.3K） | 有界调整投递 owner（AR-167 +11） | 1,000 | 不变；通用部分归 F2/F4 |
| Task Store/outbox/result | 600（0.3–0.8K） | `renew_outbox_claim`、`settle_unbound_queued_attempt` | 600 | 不变；仍禁止双写 |
| Project executor | 3,000（2.5–4K） | D-098 managed baseline reader、artifact path relocation、legacy D0/D2 profile | 3,200（2.6–4.2K） | 符合 |
| Checkpoint/effect recovery | 800（0.5–1.2K） | 无变化 | 800 | 不变 |
| Task event/progress | 1,500（1–2K） | 无实质变化 | 1,500 | 不变 |
| Presentation/history | 2,200（1.8–3K） | Native history records、Task notification 仲裁（Panel +13 symbol）、timeline `isTaskNotification` | 2,500（2.0–3.3K） | 符合 |
| Formal Web/UI | 5,200（4.5–6.5K） | Panel 7,527→9,346、RecentTasks 133、home start 154 | 5,600（4.8–7.0K） | 符合但距离拉大 |
| Composition/configuration | 2,500（1.8–3.5K） | registry 14,015→15,742（语义分派、speculation、native delegate）；native config、budgets | 2,700（2.0–3.7K） | 符合但距离拉大；registry 是第二大结构债务 |
| Observability/deployment/privacy | 3,500（2.8–4.5K） | 被动 span/诊断约 1,400 行新增；deployment observer/preflight 1,494 行无生产 caller | 3,500 | 不变：新增诊断正是要保留的 runtime correlation，旧 observer 退休抵消 |
| Schema/protocol | 1,500（1–2K） | 第三套 schema（native contract/carrier 1,359）与 Python v2 4,235、TS contract v2 2,785 并存 | 2,000（1.4–2.6K） | 符合；单源生成价值更高 |
| Legacy/compatibility | 0（0–300） | `FEATURE_LIVE_VOICE_TASK_DEMO` 退休；`useLiveVoiceDemo` 仍被 ChatPanel 构造 | 0 | 不变 |
| Test/reference in production | 200（0–500） | 约 9,450 行零生产 importer 集群已定位 | 200 | 不变 |
| **合计** | **45,100（36,600–56,900）** | 可归因生产 ≈187K | **≈54,900（43,900–68,700）** | 相对 Hermes 25,254 仍是规模级比较 |

相对原中心多出的约 9,800 行可核算：Native engine +4,500，Runtime/Agent bridge/
Presentation +2,300，media/browser +1,800，schema/Web/composition +1,200。任一前提
取消时同步下调。

## 4. 重适配后的分期与实施包

分期原则：A 期与 demo 并行，只做不改变 demo 运行路径的包；B 期在 demo 物理 PASS 后，
用 demo journey 加现有合成语音脚本（`scripts/live_voice/semantic_audio_*`）作为行为
保持 oracle；C 期在 AgentCore capability accepted 且 installed 后；D 期收尾。每个包
落地时仍要按 root `TESTING.md` 单独定级、记录正负场景与零副作用断言。

| 包 | capability / 模块 | 风险 tier | 依赖 | 范围 | 排除 | 验收 | 回滚 |
|---|---|---|---|---|---|---|---|
| **A0 冻结与文档前置** | Configuration/code/document cleanup | Tier 0 | 用户接受 §7.1/§7.2 | 选定 demo 冻结 tag；新增 Decision 记录触发条件变化；重编号并移植五份准备审计；按预检 §7 为 27 新路径与 ≥8 新 segment 建 stable key，拆 AR-212、迁 AR-013；按 symbol 重算 L1–L5 | 任何源码改动；不 merge 准备分支 | `git diff --check`、链接解析、authority map 一致、228→N 行清单 152/+27 路径全覆盖 | 单提交 revert |
| **A1 零 caller 代码退休（S7-lite）** | Test/reference in production；Observability support | Tier 1（机械删除 + caller 扫描） | A0 的 key；仍有效 oracle 已迁 | 见 §5 清单约 9,450 行：先把仍有效的测试 oracle 迁到 `tests/`/`scripts`/support，再删生产树文件 | `useLiveVoiceDemo` 集群（仍被构造）；`liveVoiceContractV2.ts`（仍被 Panel 引用）；AutoHarness 共享宿主整文件 | 静态 import 扫描为零、`scripts/`/runbook 引用核对、受影响测试通过、前端 build 通过；demo 路径零改动 | 按文件 revert |
| **A2 AgentCore F1–F6 基础能力** | Task Control Core / Executor & Durability 的通用 truth（agent-core 仓库） | Tier 3（agent-core 自身口径） | AgentCore owner；D-097 审计 §9 的 zero-baseline decision record | 在 `TaskDao`/`TeamTaskManager`、Scheduler、`AsyncToolRuntime`、Checkpointer 上补 F1–F6 最小合同：scope/Attempt/CAS/command ledger、同事务 outbox+claim lease、单行 cursor CAS、ExecutionRecord/lease/monotonic settlement、checkpoint publication ref、effect journal 单 reducer | 复制 `SqliteTaskStore`/`PersistentTaskCore`/`_DirectProjectAttemptJournal`；replay 15,128 行候选；无 adopter 的 public export；Voice/Project schema | 非 Voice conformance、race/crash/corruption oracle、public API 最小、独立 review、版本锁定 | agent-core 侧独立版本，LiveVoice 不切换即无影响 |
| **A3 canonical schema 单源设计** | Schema/protocol | Tier 0→1 | A0 | 把 Python contract v2、native contract/carrier、TS contract v2、method catalog、allowlist 归一为一份 canonical source 与生成规则；产出生成器与等价性测试，不切换 caller | 运行时切换（放 B3） | 生成结果与现有三套 schema 字节/语义等价测试通过 | 生成器不接入即无影响 |
| **B1 直接复用与替身 lane 删除（S1）** | Agent Bridge | Tier 2 | demo 物理 PASS（oracle 冻结） | `AgentBridgePort` fixture seam、`ScriptedCascadeInteractionEngine`、`InteractionEnginePort` 替身路径退休；正式路径直接使用已安装 `create_deep_agent` + `attach_output`/`send_input` | Runner 直调改造（无收益） | 正负 Agent/Tool 场景、生成期打断、speculation 回归通过；零 Task/history 副作用 | 按包 revert |
| **B2 巨型文件行为保持拆分（S5/S6 结构部分）** | Web/Gateway media transport、Composition、Formal Web/UI、Project executor | Tier 3 | B1；demo journey + 合成语音脚本作为 oracle | 四个拆分：`dedicated_media_registration.py`→registration / product registry / native downlink / diagnostics；registry→薄 composition root + 各 handler factory；Panel→P1/P2/P3 owner + notification 仲裁；executor→project seam 与 generic attempt 记录分离（为 C3 铺路）。只移动，不改语义 | 任何 authority 变化、schema 变化、legacy 退休 | 拆分前后测试集等价、合成语音 journey 与物理 demo journey 通过、reconnect/barge-in/ACK 回归 | 每个拆分独立提交，可单独 revert |
| **B3 协议单源切换（S6）** | Schema/protocol | Tier 3 | A3、B2 | caller 切到生成 client/types；删除重复 TS/Python 合同（含 `liveVoiceContractV2.ts` 2,785 行） | 状态值语义变化 | 跨语言 contract 测试、feature-off、multi-Task、refresh/reconnect 通过 | 保留旧 schema 一个包周期作为 rollback reader |
| **C1 薄 consumer Adapter（S2）** | Task Control Core、Executor & Durability | Tier 3 | A2 accepted+installed（uv.lock 锁定） | 组合 Task/Event/Cursor/Execution/Checkpoint/Effect 的薄 Adapter；Jiuwen 只留 envelope 投影、Agent 选择、worktree/Git、DOM/audio/history | 双写；第二 reducer | 每项证明最近 public owner、唯一事务、真实 adopter | Adapter 不接入即无影响 |
| **C2 single-writer cutover（S3）** | Task Store/outbox/result | Tier 3 | C1；migration/importer；canary | 新 owner 先过共同 oracle，quiesced cutover；旧 Store 停止分配；importer/旧版本读取 | 永久双写；历史候选整体 replay | migration、old-version read、race/restart/corruption、canary/rollback、零副作用 | 保留旧 Store 只读 + rollback 演练通过 |
| **C3 checkpoint/effect 与 executor 拆分（S4）** | Checkpoint/effect recovery、Project executor | Tier 3 | C2；F5/F6 installed | 通用 publication/journal/reconcile 下沉；Jiuwen 留 codec/probe/compensation/cleanup | D1 host-crash 新承诺 | D1/D2 truth、ambiguous effect、crash window、compensation 通过 | 同 C2 |
| **D1 legacy 退休（S7 正式）** | Legacy/compatibility | Tier 2 | B2、B3；feature-on/off 证据 | `useLiveVoiceDemo` 集群 3,209 行、`CommandCenter`、AutoHarness 的 LiveVoice segment 493 行；ChatPanel 只构造一套 owner | 与 formal 共用的 `LiveVoiceDemoBar` 渲染器 | replacement、caller scan、feature-on/off、测试发现率 Gate | 按包 revert |
| **D2 累计 canary/验收/计量（S8）** | 全部 | Tier 3 | 全部前置 | 完整产品 journey、独立跨模块 review、最终 L1–L5 与多仓口径报告 | — | exact clean source 上自动化、集成、人测、回滚演练通过 | — |

## 5. A1 的零生产 importer 集群（`ebd2b4575` 实测）

静态 import 扫描（排除 `tests/` 与 `scripts/`）为零的整文件 `CONSOLIDATE_RETIRE` 路径。
删除前仍须核对 `scripts/`、runbook 与动态引用，并把仍有效的 oracle 迁走。

| 集群 | 路径（LOC） | 小计 |
|---|---|---:|
| 后端 support/probe | `live_voice_deployment_observer.py`（1,045）+ 仅被它引用的 `live_voice_deployment_preflight.py`（449）、`alpha_privacy_conformance.py`（1,025）、`realtime_media.py`（822）、`alpha_benchmark.py`（633）、`fake_verticals.py`（404）+ 仅被它引用的 `executor_port.py`（117）、`observability_fault_harness.py`（391）、`sli_window_contract.py`（386）、`product_p2_readiness.py`（262）、`common/schema/live_voice_contract.py`（235，v1）、`telemetry_privacy_contract.py`（221） | 5,990 |
| 前端旧 Task lane 与替身 | `liveVoiceTaskBridge.ts`（1,486）、`liveVoiceTaskMonitor.ts`（499）、`liveVoiceTaskAdapter.ts`（279）、`liveVoiceTaskClient.ts`（162）（四者只互相引用）、`webLifecycleObservationRecorder.ts`（383）、`productCompositionContract.ts`（289）、`conversationRuntimeReplica.ts`（258）、`fakeP1Vertical.ts`（104） | 3,460 |
| **合计** | | **≈9,450** |

仍有生产 caller、因此不属于 A1 的 `CONSOLIDATE_RETIRE` 整文件：`useLiveVoiceDemo.ts`
集群（3,209 行，D1）、`liveVoiceContractV2.ts`（2,785 行，B3）、`formalTaskResultRoute.ts`
（311 行，被 `package.json` 引用，需核对）、AutoHarness 四个共享宿主（只退休 493 行
segment，D1）。

## 6. 不变的约束

- 一个事实一个 writer；迁移期不得无事务/回滚合同双写；cutover 后旧 owner 不再分配。
- 禁止复制 `SqliteTaskStore`、`PersistentTaskCore`、`_DirectProjectAttemptJournal`；禁止
  重复 reducer/verifier；禁止整体 replay 历史 AgentCore 候选。
- AgentCore 规划中心约 5,300、区间约 3,600–8,100 不因本次 delta 调整；超出即说明新增
  threat model / backend / adopter。
- LOC 是偏差解释线，不是删除目标；不为达到数字损害正向行为、fail-closed、恢复、隐私、
  安全或零副作用。
- 任何远端更新继续按 root `AGENTS.md` 逐次精确确认。

## 7. 需要用户决定的产品边界

1. **触发条件变更。** 把“feature-complete PASS 触发 S0”改为“demo 源码冻结 tag 触发
   A 期、demo 物理 PASS 触发 B 期、AgentCore installed 触发 C 期”，`develop` 集成触发
   仍按 D-084。这需要一条新 Decision；建议编号顺延当前 `D-113`。
2. **冻结 tag 选点。** 推荐现在就以 `e517bcac3`（代码与 `ebd2b4575` 相同）作为 A 期
   源码冻结点；B 期 oracle 冻结点等 demo 物理 PASS 的 exact commit。
3. **Native engine 是否纳入本轮瘦身。** 它是最大的新增块（7,758 行）；纳入则 A3/B2/B3
   都要覆盖 Native contract/runtime，不纳入则规划中心回落约 4,500。
4. **tool-pause seam 归属。** `stream_event_rail.pause_tools` + `formal_tool_gate` 属
   AgentCore `AsyncToolRuntime` 还是 Jiuwen harness；影响 F4 范围与 B1 的 Agent Bridge 包。
5. **瘦身与 `develop` 集成的先后。** 建议瘦身在 w3 上落地后再做 `develop` 集成，避免
   先合入约 187K 再删除；这与 D-084 不冲突，但需要明确写入触发 Decision。

## 8. 本文不授予什么

本文不改变 STATUS 判断，不宣告任何包已开始或完成，不把临时归类当处置决定，不授予
AgentCore 能力接受或安装信用，也不授权任何远端操作。A 期各包在用户接受 §7.1 与
§7.2 后才进入实施。
