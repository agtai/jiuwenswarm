# OpenJiuwen LiveVoice 零基线模块审计 — 2026-08-31

> 状态（D-096，2026-09-01）：准备分支上的源码事实与冻结后激活 handoff 已完成；
> 不执行迁移、不改产品代码、不激活 composition、不实现或包装 AgentCore PR、
> 不更新远端。

## 1. 结论先行

旧结论需要纠正，而且不是只改一个名词：

1. 当前 LiveVoice 可归因生产 footprint 不是可证实的“30 万行”，而是
   **163,264 physical LOC**：128 个专属生产路径 159,210 行，加 24 个共享
   宿主中按稳定 symbol/segment 归因的 4,054 行。共享宿主其余 53,534 行不是
   LiveVoice 代码，不能整文件相加。
2. “30 万”只有把测试、fixture、脚本和支持资产混入后才成立：本轮可复算的
   可归因生产 + 直接支持文本集合为 338,602 行。它解释仓库规模，不代表要进入特性
   分支的产品实现。
3. 对标对象应是独立仓库
   `bielcarpi/hermes-live-voice@3dd8af386b845a1486b05b088bbc2b5a642a5b28`，
   不是只抽取 NousResearch Hermes 的 16 个 Voice/STT/TTS 文件。
4. Hermes Live Voice **有**浏览器 SDK、Web demo、Dashboard 插件/relay、
   HTTP/WebSocket inbound adapters、`LiveGatewaySession`、`TaskSupervisor`、
   Task Store、Hermes Runs adapter 和 terminal。旧文档中的“没有浏览器/Channel
   接入”及“没有 durable Task analogue”结论均撤回。
5. JiuwenSwarm 也已经有 `BaseChannel`/`BaseWebChannel`/`WebChannel`、TUI、
   ACP、A2A、多个 IM Channel、Web JSON/WS、E2A 和 browser Speech hooks。
   LiveVoice 需要的是 WebChannel 上的**薄实时音频扩展**，不是第二套 Channel
   或 Gateway 框架。当前代码虽然复用了 WebChannel，但把媒体注册、服务实例、
   清理和方法清单直接嵌入了共享宿主，仍需收敛成 plugin/registration seam。
6. 当前最大问题不是“功能比 Hermes 多，所以代码多”，而是通用 Task/
   durability/execution authority 在 LiveVoice 内重建、多代 formal/legacy 路径
   并存、schema 与 composition 重复，以及巨型多职责文件。最大的 4 个专属
   文件共 42,985 行，占专属生产代码 27.0%。

因此目标不是把 LiveVoice 做成 Hermes，而是把责任重新放回正确层：

- 调用 JiuwenSwarm/AgentCore 已有公共能力；
- 用薄 Adapter 连接已有能力；
- 只把确属通用缺口的合同记录为未来 AgentCore 下沉要求；
- 保留 channel-neutral 的语音语义、Web 媒体叶子和 Jiuwen 产品策略；
- Gate 后退休 legacy、测试替身和重复 authority。

## 2. 基线与证据强度

| 对象 | 固定事实 | 用途 |
|---|---|---|
| LiveVoice/JiuwenSwarm 产品事实 | 冻结 commit object：`hx/0812_live_voice_w3@59998e2c5724257bd410885b35e59e1b37027030`；相对 upstream ahead 4；后续并发工作区改动不计入本快照 | 当前路径、调用、LOC 和 authority |
| 准备分支 | `codex/livevoice-agentcore-hermes-prep` | 只保存审计、映射、历史候选证据和未来激活 handoff |
| Hermes Live Voice | `bielcarpi/hermes-live-voice@3dd8af386b845a1486b05b088bbc2b5a642a5b28` | 主要架构对标；不复制源码 |
| NousResearch Hermes | `fc9cbc872d8050c22f1192b16bc5ff4aed471e10` | 说明 Hermes Agent/Session/官方 Voice seam；不是上述集成仓库 |
| LiveVoice 锁定 AgentCore | `openjiuwen 0.1.16@94e10cb6102c36fe78a64547957c0def97299273` | 只有该版本的公共能力可称“当前可直接调用” |
| AgentCore 本地候选 worktrees | Scope、A1、A2、ADD/Facade 等本地分支 | 只能称“已准备候选”，不能冒充锁定依赖能力 |

本文的“当前调用”是源码调用链事实，不是物理设备、真实 Provider、真实 Tool
副作用或产品验收。`KEEP`/`REUSE`/`PR` 是目标责任判定，不表示迁移已发生。

## 3. 代码到底有多少

### 3.1 当前生产路径全集

| 物理分组 | 路径数 | physical LOC | 解释 |
|---|---:|---:|---|
| backend `server/live_voice` | 66 | 101,053 | 语音、Conversation、Task、durability、policy、composition、observability |
| formal Agent carrier | 1 | 163 | Jiuwen Agent 调用的窄合同 |
| frontend dedicated carrier | 7 | 9,500 | Panel、Demo bar、ownership hook 等 |
| frontend `features/live-voice` | 42 | 31,389 | Browser Audio、formal Web、legacy Task/voice |
| gateway `live_voice` | 8 | 11,376 | speech/media transport 与注册 |
| shared schema | 2 | 4,235 | Python v1/v2 wire/value schema |
| Web deployment | 2 | 1,494 | default-off deployment/readiness support |
| **专属/非共享合计** | **128** | **159,210** | 可防御的当前专属生产物理行数 |
| 共享宿主 LiveVoice symbol/segment | 24 | 4,054 | 当前快照可归因；以稳定 symbol/segment 命名 |
| **当前可归因生产 footprint** | — | **163,264** | 159,210 + 4,054；不是未来保留量 |
| 共享宿主非 LiveVoice 余量 | 24 | 53,534 | 明确排除 |
| **152 个 manifest 文件整文件和** | **152** | **216,798** | 163,264 + 53,534；不是 LiveVoice headline |

计数包含空行和注释，只计算 Git 跟踪的当前文本文件。152 个路径已独立做集合
相等检查：0 missing、0 duplicate、0 extra。旧 `158,729` 是 `c019da18`
快照；`7bf704d7` 的 Panel 净增 125 行，`39f4efa3` 又在四个已有 Channel
路径增加 357 行 successor-capture ACK/first-frame diagnostics；随后
`39f4efa3..5b4d3e69` 只修改 `live-voice/STATUS.md`；随后
`5b4d3e69..59998e2c` 在已纳入清单的 product composition registry 净减 1
行，并增加测试、状态和计划文档。路径、稳定 symbol 与责任类均未变。

### 3.2 当前生产责任 LOC

| 当前独占责任桶 | physical LOC |
|---|---:|
| LiveVoice Core | 10,651 |
| Channel Adapter | 41,837 |
| JiuwenSwarm host/product | 30,870 |
| AgentCore duplicate/PR candidate | 26,568 |
| Legacy/support（仍在生产树） | 15,123 |
| Truly mixed symbol groups | 38,215 |
| **当前可归因生产合计** | **163,264** |

这些是当前代码责任，不是未来去留数字。`AgentCore duplicate/PR candidate`
不表示 API 已安装或代码可删；`Truly mixed` 明确保留尚未完成 symbol 内部分账的
巨型文件，避免把它们虚假地全归给某一层。

24 个共享宿主只计下列稳定 symbol/segment；不保存易漂移的源代码行号：

| 共享宿主 | LiveVoice symbol/segment | 责任桶 | 归因 LOC | 宿主余量 |
|---|---|---|---:|---:|
| `auto_harness/project_execution.py` | `resolve_project_execution_contract`、project-code compatibility policy | Legacy/support | 47 | 150 |
| `auto_harness/scheduler.py` | LiveVoice origin skip、project-code branches | Legacy/support | 72 | 771 |
| `auto_harness/service.py` | LiveVoice reconciliation/scheduling/RPC branches | Legacy/support | 331 | 3,878 |
| `auto_harness/task_store.py` | orphaned-running reconciliation branch | Legacy/support | 43 | 730 |
| `channels/web/app_web.py` | media/transcript/claim redaction | JiuwenSwarm host/product | 65 | 1,390 |
| frontend `App.tsx` | route selection/product-panel composition | JiuwenSwarm host/product | 65 | 2,668 |
| `ChatPanel/index.tsx` | formal mount、legacy hook construction、browser ownership | Truly mixed | 268 | 1,412 |
| `ChatPanel/MessageItem.tsx` | manual-message TTS output fence | Channel Adapter | 34 | 891 |
| frontend `featureFlags.ts` | `FEATURE_LIVE_VOICE_*` | JiuwenSwarm host/product | 19 | 12 |
| frontend `useWebSocket.ts` | final marker、supplement quarantine integration | Channel Adapter | 210 | 4,043 |
| `supplementOutputQuarantine.ts` | quarantine factory/decision | Channel Adapter | 100 | 0 |
| frontend `utils/tts.ts` | shared TTS routing/output control | Channel Adapter | 104 | 0 |
| `ttsOutputOwnership.ts` | output ownership fence | Channel Adapter | 40 | 0 |
| `ttsText.ts` | text normalization/chunking | Channel Adapter | 78 | 176 |
| `common/schema/message.py` | LiveVoice request/event enum members | JiuwenSwarm host/product | 18 | 359 |
| `gateway/app_gateway.py` | voice claim、forward allowlist | JiuwenSwarm host/product | 118 | 2,977 |
| `app_web_handlers.py` | speech/media/product handler registrations | Channel Adapter | 391 | 6,241 |
| `web_connect.py` | dedicated-media dispatch、close/event forwarding | Channel Adapter | 204 | 1,531 |
| `server/agent_ws_server.py` | composition lifecycle、request/text/diagnostics | JiuwenSwarm host/product | 746 | 9,106 |
| `agent_adapter/agent_adapters.py` | formal adapter selection | JiuwenSwarm host/product | 50 | 118 |
| `agent_adapter/interface_deep.py` | formal stream/committed-context facade | Truly mixed | 620 | 11,822 |
| `agent_adapter/interface.py` | formal capability/stream facade | Truly mixed | 231 | 3,192 |
| `runtime/agent_manager.py` | formal acquire/pin/release/cleanup | JiuwenSwarm host/product | 150 | 1,309 |
| `session/session_history.py` | committed/presented history | JiuwenSwarm host/product | 50 | 758 |
| **合计** | — | — | **4,054** | **53,534** |

快照 LOC 由可复现脚本校验，但 symbol/segment 端点仍是 medium-confidence 的
源码/调用者归因；未来特性分支变化后必须重算，不能把这些数当迁移 locator。

### 3.3 为什么会被口头称为“30 万”

| 非生产/支持集合 | 路径数 | physical LOC |
|---|---:|---:|
| backend unit tests | 71 | 105,534 |
| integration tests | 4 | 2,166 |
| test/support | 2 | 1,188 |
| fixtures | 13 | 2,642 |
| `scripts/live_voice` 文本 | 27 | 15,932 |
| `scripts/live_voice` 二进制音频 fixture | 1 | 不计 physical LOC |
| frontend 文本匹配的测试/harness 诊断集合 | 49 | 47,876 |
| `live-voice/evidence/**` 文档 | 28 | 3,798 |
| 其他 `live-voice/**` 文档 | 99 | 24,404 |

前六个支持文本集合合计 175,338 行；与 163,264 行可归因生产相加是
**338,602** 行。文档/证据另有 127 个文本文件、28,202 行，不混入生产或上述
直接支持分母。该数可
解释工作量和仓库体量，但这些集合不能混成“LiveVoice 运行时代码”。
旧 register 曾列出 `10` 个 named-backend、`35` 个 frontend test 和 `7` 个
frontend asset 搜索分组；这些分组存在重叠，现已撤出加法口径。上表是本轮唯一
可相加的去重支持集合。
被排除的二进制文件是
`scripts/live_voice/w2_rehearsal/assets/voice-command-48k-mono-pcm16.wav`；此前把
其字节中的换行分隔误计为 1,050 行，已经撤回。

### 3.4 规模集中点

| 文件 | LOC | 当前多职责 |
|---|---:|---|
| `task_store.py` | 14,951 | Task/Attempt/Command/Event/Outbox/Result/Cursor/Checkpoint/Effect + schema/migration |
| `product_composition_registry.py` | 14,015 | P1/P2/P3 入口、配置、生命周期、route/replay/presentation 编排 |
| `LiveVoiceIntegratedRoutePanel.tsx` | 7,527 | Browser voice、P2、P3、recovery、presentation、diagnostics UI |
| `project_code_executor.py` | 6,491 | Agent worker、attempt journal、worktree/patch、result、D1/D2、cleanup |

这 4 个文件共 42,985 行；前 10 个文件共 65,555 行。瘦身首先应拆清 owner
并移除重复 truth，而不是平均压缩每个文件。

### 3.5 pinned Hermes 的同口径分层

| 责任层 | shipped 生产文件/LOC | 去重实现 LOC | 测试/fixture 文件/LOC |
|---|---:|---:|---:|
| client/channel | 10 / 6,344 | 6,344 | 6 / 4,311 |
| core/runtime | 22 / 6,178 | 6,178 | 13 / 7,247 |
| Hermes host/plugin | 10 / 6,133 | 3,409 | 1 / 320 |
| task/durability | 8 / 3,297 | 3,297 | 4 / 2,678 |
| support/fixtures | 12 / 3,302 | 3,302 | 14 / 1,344 |
| **合计** | **62 / 25,254** | **22,530** | **38 / 15,900** |

去重只扣除 Dashboard distribution 中与 Browser SDK 完全相同的
`hermes-live-client.js`（2,688 行）和 `mic-worklet.js`（36 行）；Dashboard
`dist/index.js`/CSS 仍是 shipped UI，不能按“generated”猜测删除。Pinned 仓库
另有 scripts/examples 15 路径/3,521 行、documentation 18/2,566、其他配置/
资产/lock 21/3,862；tracked repository 总计 154 路径/51,103 行。这些数字与
OpenJiuwen 的相同责任层比较，不把测试或文档混进生产分母。

## 4. 正确的五层架构

```text
外部客户端 / JiuwenSwarm UI
  └─ L2 Channel Adapter：Web capture/playout + WebChannel 媒体叶子
       └─ L1 Channel-neutral LiveVoice Core：commit、turn/response/generation、
          barge-in、speech policy、presentation
            └─ L3 JiuwenSwarm Host/Product：认证 scope、Agent/project binding、
               history、Web/Gateway/AgentServer composition
                 └─ L4 AgentCore shared foundation：Agent/Runner/Tool、Task、
                    execution、event、checkpoint/effect/cursor（已有或 PR 后）

L5 Legacy / transition / support 横跨各层，但不是目标运行时层。
```

这五层解决了旧 M1–M12 的一个根本问题：UI、Web transport、产品 policy、
AgentCore 通用 authority 和测试/部署支持不再被并列成“LiveVoice Core 模块”。

### L1 — Channel-neutral LiveVoice Core

保留 committed voice input、interaction/turn/response/generation、barge-in、
speech provider port/fallback、语音进度仲裁、presentation/history eligibility。
它不拥有 Browser 权限、WebSocket、project path 或通用 Task Store。

### L2 — Channel Adapters

Web 适配器拥有浏览器设备、capture/playout、本地 AudioContext、媒体帧、
backpressure、playout receipt 和 Web reconnect 投影。未来其他 UI/Channel
应实现同一窄端口，而不是复制 Core。JiuwenSwarm 已有 Channel 框架；这里只
扩展实时音频能力。

### L3 — JiuwenSwarm Host/Product

拥有真实 principal/project/session、AgentManager binding、Chat history、
Gateway/AgentServer 注册、产品 intent/confirmation/model/policy、Web UI 和
project/worktree/patch 安全。这些不能因为 AgentCore 有同名对象就上移。

### L4 — AgentCore shared foundation

已有 `BaseAgent`、Tool、Runner、DeepAgent/Harness、Checkpointer 和 Session
VCS。Jiuwen 真实前台路径主要通过 `create_deep_agent` 与
`attach_output`/`send_input`，不能把“直接复用”误写成只允许
`Runner.run_agent_streaming`。AgentTeams Task board/DAO 可达但不是导出的
最小权限公共 facade，且不具备完整 scoped command/result/execution/outbox/
event/effect/cursor authority。Checkpointer/VCS 也只是存储基础，不是 Task
checkpoint 发布 authority。直接复用、Adapter 和 PR 候选必须逐 API 证明，
禁止整体复制 `SqliteTaskStore`，也禁止直接组合 raw DAO/manager。

### L5 — Legacy / transition / support

包括 `useLiveVoiceDemo`、旧 browser Task client/bridge/monitor、AutoHarness
兼容片段、test-only replicas/fakes、probe/conformance helpers、未被产品调用的
旧 schema/realtime reference。它们在 Gate 前可能仍有 oracle/rollback 价值，
但不能被解释成目标模块。

## 5. 当前 8 条真实链路

| 链路 | 当前入口与 owner | 必须诚实披露的事实 |
|---|---|---|
| 1. capture → committed final | Panel/Browser ownership → dedicated media → streaming/batch result → unified/P2 submit | Browser/Gateway 分别拥有设备与媒体 lease；streaming unavailable 时允许 TEXT |
| 2. committed input → Agent/Tool | AgentServer → registry/TurnCommit → P2 activation → `AgentConversationRuntime` → AgentManager formal facade | 当前复用 Jiuwen Agent facade；正式链路未直接调用 AgentCore Runner |
| 3. Agent output → synthesis/playout | runtime presentation → registry → Gateway streaming synthesis → BrowserAudioIO → exact ACK/failure | 网络发送、synthesis success 和 audible/DOM adoption 不是同一个事实 |
| 4. barge-in/cancel | browser speech-start → exact P2 response/generation → runtime cancel → media/browser stop | speech interrupt 不等于 Task cancel；各层都要 fence late output |
| 5. Task create/execute/cancel/query | formal P3 UI → registry/P3 composition → `PersistentTaskCore`/`SqliteTaskStore` → direct project executor | 当前 Task truth 仍在 LiveVoice；AgentCore 替换尚未 composition |
| 6. event/progress/cursor/ACK | Store/event subscription → registry progress generation → text/voice projection → browser adoption/ACK | voice delivery不可用会回退 TEXT；browser cache 不是 durable truth |
| 7. reconnect/recovery | browser journals + Store/outbox/recovery + runtime presentation + media cleanup | 多个 recovery plane，不得把其中一个成功说成全链成功 |
| 8. feature-off/legacy | AgentServer master gate 阻止 formal registry allocation | `ChatPanel` 仍先构造 `useLiveVoiceDemo`；不能宣称只有一套 runtime owner |

## 6. 模块责任、Hermes 对照与目标处置

以下是逻辑责任模块，不把 UI、host 或 support 误叫成 Core。每个物理路径仍由
152-path manifest 逐项覆盖。处置只使用 scope 锁定的八个代码：
`DIRECT_REUSE`、`ADAPT_REUSE`、`AGENTCORE_PR`、`LIVEVOICE_CORE_KEEP`、
`CHANNEL_ADAPTER_KEEP`、`JIUWENSWARM_HOST_KEEP`、`SPLIT_REQUIRED`、
`CONSOLIDATE_RETIRE`。表中一行列出多个代码时，表示该行聚合了必须先按 symbol/
责任拆开的不同原子项；同一个原子责任仍只有一个当前处置，不是双重归属。

| 责任模块 | 当前 OpenJiuwen 位置/owner | pinned Hermes analogue | 目标处置 | 为什么 |
|---|---|---|---|---|
| Browser Audio Edge | frontend formal adapters、Audio Port、device/ownership、P1 route | `clients/browser` 的 `HermesLiveAudio`、mic worklet；Dashboard/Web demo | `CHANNEL_ADAPTER_KEEP` + split | 设备权限、capture/playout 和 receipt 属于客户端；Panel 不应独占实现细节 |
| Web/Gateway media transport | existing `WebChannel` + `gateway/live_voice` dedicated media/speech routes | inbound HTTP/WebSocket adapter + Dashboard relay | `CHANNEL_ADAPTER_KEEP` + `SPLIT_REQUIRED` | 复用现有 Channel；把注册/服务/cleanup 从共享 WebChannel 抽成单一扩展 owner |
| Speech provider layer | speech ports、batch/streaming/OpenAI provider、Gateway routes | realtime provider ports/adapters | `LIVEVOICE_CORE_KEEP` + consolidate | STT/TTS 是语音域；收敛 capability、fallback、cancel 和重复 contract |
| Committed input / product authority | unified input、product authority、intent/confirmation/model policy | `LiveGatewaySession` 的 authenticated session/tool boundary（partial） | `JIUWENSWARM_HOST_KEEP` | principal/project/confirmation 是 Jiuwen 产品策略，不是 AgentCore 通用 truth |
| Conversation Runtime | conversation state/loop、AgentConversationRuntime | `LiveGatewaySession`（analogue） | `LIVEVOICE_CORE_KEEP` + split | 保留一套 turn/response/generation authority，拆 subordinate coordinator |
| Agent bridge | formal carrier、Jiuwen facade、round harness/adapter | Hermes Sessions Chat / Agent Runs adapter | `DIRECT_REUSE`/`ADAPT_REUSE` | Agent/Tool/Runner/DeepAgent 已存在；正式路径复用 committed Harness handle。仅 fake 调用的 `AgentBridgePort` 应在迁移 oracle 后退休，不是主生产替换对象 |
| Task domain/control | models、PersistentTaskCore、P3 composition | Task domain + `TaskSupervisor` | `AGENTCORE_PR`/`ADAPT_REUSE` | Hermes 证明责任存在；锁定 AgentCore raw board/DAO 不是安全公共 facade，需接受并安装 corrected shared authority 后才可替换 |
| Task Store/outbox/result | 14,951-line `SqliteTaskStore` | `FileTaskStore` + TaskSupervisor persist-before-publish | `AGENTCORE_PR` then `CONSOLIDATE_RETIRE` | 当前是 sole truth，但不应永久属于 LiveVoice；禁止 whole-file 上移或双写 |
| Project executor | direct executor + Jiuwen AgentManager/worktree/patch | Hermes Runs adapter（partial） | `SPLIT_REQUIRED` | 通用 attempt/result/cancel 归 AgentCore；project/Git/Tool policy 留 Jiuwen |
| Checkpoint/effect recovery | `durability_*` + Store tables | TaskSupervisor reconciliation/unknown fence（partial） | `AGENTCORE_PR` + thin project adapter | 已有 Checkpointer/VCS 可作 payload 基础，但没有 Task-bound publication/effect authority；具体 probe/compensation 仍是 Jiuwen policy |
| Task event/progress | event subscription、progress return | Task snapshot/progress/notification | `ADAPT_REUSE` + `LIVEVOICE_CORE_KEEP` | event/source/cursor 通用；spoken/text arbitration 是语音产品语义 |
| Presentation/history | presentation ledger、generation store、formal history、browser ACK | Browser task cache/notification ACK + audio interrupt（partial） | `LIVEVOICE_CORE_KEEP`/`JIUWENSWARM_HOST_KEEP` | DOM、audio 和 history adoption 必须由真实 surface/产品规则证明 |
| Formal Web product UI | 7,527-line Panel、P1/P2/P3 owners/journals | Dashboard UI + browser SDK + terminal | `SPLIT_REQUIRED` | Hermes 也有 UI/SDK；当前 Panel 聚合过多 state machine 和 diagnostics |
| Composition/config | 14,015-line registry、root、declaration、host registrations | server composition/config/setup | `SPLIT_REQUIRED` | 能力声明与生命周期必要，但不应由一个 registry 实现所有 handler/policy |
| Observability/deployment/privacy | OTel adapter、diagnostics、preflight、probe/conformance | logger/readiness/doctor/setup/security support（partial） | runtime leaf `JIUWENSWARM_HOST_KEEP`；support `CONSOLIDATE_RETIRE` | 运行诊断必要；benchmark/fault harness/alpha probe 应迁到支持树或在 oracle 搬迁后删除 |
| Schema/protocol | Python v2 + frontend local schemas + method allowlists | protocol domain + browser validation | `SPLIT_REQUIRED`/generate | 需要 wire contract，但当前跨语言复制和超大统一 schema 扩大维护面 |
| Legacy/compatibility | `useLiveVoiceDemo`、old Task bridge/client/monitor、AutoHarness segments | 无需对应 | `CONSOLIDATE_RETIRE` after Gate | 与 formal lane 并存形成重复 capture/Task/poll/history authority |
| Test/reference code in production tree | TS replica/fake/result/contract、Python benchmark/fake/fault/reference | Hermes `test/**`（放在测试树） | `CONSOLIDATE_RETIRE` after oracle port | 已验证最少 7,837 行不在产品 runtime 调用链；迁到支持树或删除，不再伪装成运行时模块 |

## 7. 与 Hermes 真正的同、异、多、少

### 7.1 同类责任

两者都有 Browser client/audio、WebSocket inbound、session/gateway、realtime
Provider adapter、Agent adapter、durable Task supervisor/store、Task state/progress/
notification、speech interruption、exact Task stop、reconnect/reconciliation、
UI/CLI/support。speech interruption 的精确性取决于 Provider：OpenAI 支持
correlated cancel/truncate，Gemini 是 Provider-managed barge-in，没有同等的 exact
cancel channel。区别主要是 owner 位置和 failure model，不是“有/无”。

### 7.2 LiveVoice 合理多出的部分

- JiuwenSwarm 多 Channel/多宿主集成和 Web 产品 trust boundary；
- committed voice/text 统一输入、product intent/confirmation/model policy；
- DOM 与 audio 分 surface presentation/history eligibility；
- project/worktree/patch/Tool effect policy；
- 更严格的多 generation、scope 和跨组件 negative-side-effect contract。

这些差异解释“为什么不能直接复制 Hermes”，但不证明现有实现规模合理。

### 7.3 LiveVoice 不合理多出的部分

- 在语音目录内重建通用 Task/Attempt/Command/Event/Outbox/Result/Cursor/
  Checkpoint/Effect authority；
- formal 与 legacy Web/Task lane 同时构造；
- Python/TypeScript contract、method allowlist 和局部状态值重复；
- product registry、Panel、Task Store、executor 多职责膨胀；
- test/probe/reference module 放在生产路径；
- shared WebChannel/AgentServer/Deep adapter 内嵌大量 LiveVoice segment，缺少
  窄 registration/facade 边界。

### 7.4 LiveVoice 当前少或未收敛的部分

- 没有像 Hermes `clients/browser` 那样清晰、可供任意 Jiuwen UI 使用的窄 SDK
  边界；现有能力主要绑定 Jiuwen Web frontend；
- Channel 扩展点没有形成统一 realtime-media capability port；
- provider-neutral sentence/text chunk owner 尚未成为所有 TTS 路径的唯一入口；
- formal/legacy single-owner cutover 未完成；
- AgentCore-backed Task facade 尚未真实 composition。

## 8. 处置优先级与迁移前准备

当前阶段只准备，不迁移。建议顺序：

1. 冻结本文的 152-path/8-flow/五层责任基线；
2. 纠正所有 Hermes 列和 LOC 结论；
3. 锁定 AgentCore 公共 API 证据，区分 installed、local candidate 和 absent；
   PR09/PR10 历史 facade 有严重审查问题，只保留需求/oracle，未来公共
   grant/facade 如仍需要必须重新实现，但不在本准备分支实现或包装；
4. 先形成薄 Channel registration、Agent invocation 和 Task facade 设计；
5. 形成 AgentCore 下沉 handoff：记录通用 contract、非 Voice conformance、最小
   owner、依赖、风险和 LiveVoice consumer seam，不复制 LiveVoice Store/schema，
   也不把 PR replay/包装列为本分支完成条件；
6. 在特性开发稳定后，另开迁移包做 single-writer cutover、canary、rollback 和
   legacy retirement；
7. 将 LOC 只保留为激活时重算的规划区间。现在给出一个“必然瘦到多少行”的
   精确数字会把尚未决定的 shared-symbol allocation 和 Gate-retirement 当成
   既成事实。

### 8.1 本轮完成边界

| 工作产品 | 当前状态 | 明确没有声称完成的事项 |
|---|---|---|
| 零基线生产/支持 LOC、五层责任与八条当前流程 | 本轮审计已形成；原子归属独立复核为 `Critical 0 / Important 0 / Minor 10` | 不等于运行时迁移、内部重构或产品验收；10 项同 owner 结构债务仍未实现 |
| Hermes 模块逐项比较 | pinned snapshot 审查已关闭，独立复核为 `Critical 0 / Important 0 / Minor 0` | 不把 Hermes 当目标架构或源码复用来源 |
| AgentCore/JiuwenSwarm 复用、适配、下沉候选 | installed/local-candidate/absent 已分开；设计与 replay 证据已准备 | 不表示候选 API 已安装、已 composition 或已被 AgentCore 接受 |
| AgentCore 下沉 handoff | **完成**：13 个 `AGENTCORE_PR` 原子责任、公共缺口、依赖、历史缺陷/oracle 和未来 Gate 已记录 | 本分支不要求 PR 实现、replay、issue metadata、包装或提交；历史 packet 只作可选证据 |
| LiveVoice 迁移、single-writer cutover、canary、旧实现退休 | **未开始**，按用户范围刻意排除 | 没有迁移产品代码、删除 Store/schema、运行 canary 或提交远端 PR |

### 8.2 已披露但不阻断归属决策的 10 项结构债务

这些项的 canonical owner 已经明确，所以不再阻断“直接复用 / 适配复用 /
AgentCore PR / 保留 / 退休”的准备结论；但它们仍是实际的收敛工作，不能说成
已经重构，也不能预先计入删除 LOC：

1. `batch_speech.py` 的 Provider contract、环境选择和 service orchestration；
2. `openai_streaming_speech.py` 的 vendor transport 与 degradation selection；
3. `browser_gateway_media_transport.py` 的 wire codec 与 queue/lifecycle；
4. `streaming_speech_route.py` 的 route lifecycle 与 fallback/outcome projection；
5. `streaming_synthesis_route.py` 的 route lifecycle 与 buffer/pull mechanics；
6. `gatewayBatchSpeechClient.ts` 的纯音频转换与 request-local client state；
7. `productP1VoiceRoute.ts` 的 capture/recognition、playout 和 diagnostics；
8. `dedicated_media_registration.py` 的 registration、registry、diagnostics 和 product/media authority；
9. `progress_notification_arbiter.py` 的纯 policy 与 queue/ACK mechanics；
10. `product_observability_adapter.py` 的 activation/route facts 与 consumer/lease mechanics。

因此，“零基线审计与迁移前 handoff”可以关闭；真正的 LiveVoice/AgentCore
瘦身实现尚未开始，也不能因为文档齐全就宣称代码已经瘦身。正式开发冻结后只
增量重基线受影响责任，再形成绑定当时源码和测试的实施包。

## 9. 覆盖与限制

- [152-path 详细处置 register](OPENJIUWEN_LIVEVOICE_MODULE_DISPOSITION_AND_HERMES_COMPARISON_2026-08-25.md)
  保留完整物理 inventory、当前 caller/authority 证据和已校正的 pinned Hermes
  责任关系。
- [228-row 原子责任处置清单](OPENJIUWEN_LIVEVOICE_ATOMIC_DISPOSITION_2026-08-31.md)
  是多责任路径的唯一处置口径：覆盖 152/152 路径、48 个多责任路径，每个
  atomic key 只有一个 canonical code，不使用源码行号定位。
- [逐 symbol AgentCore 迁移映射](OPENJIUWEN_LIVEVOICE_SYMBOL_MIGRATION_MAP_2026-08-24.md)
  记录通用 owner、Adapter 与 retirement Gate。
- [审计计划](OPENJIUWEN_LIVEVOICE_ZERO_BASE_MODULE_AUDIT_PLAN_2026-08-31.md)
  记录方法、验收和排除项。

本轮没有运行真实麦克风、扬声器、浏览器权限、Provider、真实 Agent/Tool
副作用、重启/reconnect 或 canary；这些仍是未来实现/验收 Gate。本文也不把
Hermes 的实现、LOC 或 failure model当作 OpenJiuwen 的产品标准。
