# LiveVoice 中文模块化架构：给熟悉 Hermes Live Voice 的读者

> 本文是阅读视图。完整 LOC、152-path coverage、8 条链路和处置证据以
> [零基线模块审计](OPENJIUWEN_LIVEVOICE_ZERO_BASE_MODULE_AUDIT_2026-08-31.md)
> 为准。本文不授予迁移、删除、AgentCore PR 或产品验收信用。

## 1. 先建立正确的 Hermes 心智模型

这里的主要对标对象是独立仓库
`bielcarpi/hermes-live-voice@3dd8af386b845a1486b05b088bbc2b5a642a5b28`，
不是 NousResearch Hermes 仓库里若干 Voice/STT/TTS 文件的集合。

```text
Hermes Dashboard / browser / terminal
  -> Client SDK / audio / same-origin plugin relay
  -> authenticated HTTP/WebSocket inbound adapter
  -> LiveGatewaySession
       ├─ realtime Provider adapters
       ├─ Hermes Sessions Chat（前台 conversation）
       └─ TaskSupervisor（后台 Task）
            ├─ FileTaskStore
            └─ Hermes /v1/runs adapter
```

所以 Hermes Live Voice 并非“本地麦克风 → Agent → 扬声器”的单进程 loop。
它有真实 Browser/Channel、Gateway、Task、Store、Agent adapter 和 host plugin
边界。它没有名为 `ChannelAdapter` 的单个类，不等于没有 Channel Adapter 责任。

## 2. OpenJiuwen LiveVoice 的五层位置

```text
外部客户端 / JiuwenSwarm UI
  └─ L2 Channel Adapter
       Browser audio + existing WebChannel/Gateway media leaf
       └─ L1 Channel-neutral LiveVoice Core
            commit + turn/response/generation + speech + barge-in + presentation
            └─ L3 JiuwenSwarm Host/Product
                 auth/project/session + AgentManager + history + product policy + UI
                 └─ L4 AgentCore shared foundation
                      Agent/Tool/Runner/DeepAgent + future shared Task authorities

L5 Legacy/transition/support 横跨各层，但不属于目标 runtime。
```

### L1 — Channel-neutral LiveVoice Core

它回答“这段 speech 是否已经 committed”“当前 response/generation 是谁”“插话
取消哪个 response”“何时允许 text/audio presentation 与 history”。它不应该
知道 React、WebSocket、project path、SQLite schema 或 AgentCore DAO。

### L2 — Channel Adapter

它回答浏览器权限、capture/playout、AudioContext、媒体 frame/backpressure、
playout receipt 和 reconnect projection。JiuwenSwarm 已有 `BaseChannel`、
`BaseWebChannel`、`WebChannel`、TUI、ACP、A2A 和 IM adapters；LiveVoice 应在
既有注册/连接 seam 上增加窄 realtime-media capability，而不是新建 Channel
框架。

### L3 — JiuwenSwarm Host/Product

它拥有 principal/project/session、AgentManager binding、Session History、
Gateway/AgentServer 注册、intent/confirmation/model policy、project/worktree/
patch 安全和产品 UI。这些是 Jiuwen 产品责任，不应因为 AgentCore 有相似名词
就上移。

### L4 — AgentCore shared foundation

锁定 `openjiuwen 0.1.16@94e10cb6` 可直接调用 Agent、Tool、Runner 和
DeepAgent/Harness；真实前台路径主要复用 `create_deep_agent` 加
`attach_output`/`send_input`。Checkpointer 和 Session VCS 当前只能作为存储
foundation 复用，不能按 `DIRECT_REUSE` 冒充 Task checkpoint 发布或恢复 authority。

AgentTeams 中虽然存在 Task board/DAO，但它不是导出的最小权限公共 LiveVoice
facade，也不满足完整 scoped command/result/execution/outbox/event/checkpoint/
effect/cursor authority。SCOPE/A1/A2、ADD-01..05 仍是本地 PR 候选；历史
PR09/PR10 facade 必须重实现，不能按现状接入。

### L5 — Legacy / transition / support

包括 `useLiveVoiceDemo`、旧 Task client/bridge/monitor、AutoHarness compatibility、
test replicas/fakes、benchmark/probe 和旧 contract。它们可能仍携带 oracle 或
rollback 价值，但不是目标架构模块。

## 3. 当前调用链怎么走

### 3.1 前台语音 conversation

```text
ChatPanel / Browser ownership
  -> ProductP1VoiceRoute + BrowserAudioIO
  -> existing WebChannel 的 dedicated media route
  -> streaming/batch recognition（必要时 TEXT fallback）
  -> unified/P2 committed submit
  -> AgentServer registry + TurnCommit
  -> AgentConversationRuntime
  -> AgentManager formal DeepAgent/Harness seam
  -> presentation
  -> Gateway synthesis/media
  -> browser playout
  -> exact presentation ACK/failure
```

`AgentConversationRuntime` 是当前前台 response/presentation authority；Agent
执行委托给 Jiuwen 已有 facade。Browser、Gateway、Runtime 各自只拥有自己层的
lease/generation，不能互相伪造成功。

### 3.2 后台 Task

```text
formal P3 UI
  -> AgentServer registry / authenticated P3 composition
  -> VoiceTaskBridge（只接收 verified committed origin）
  -> PersistentTaskCore
  -> SqliteTaskStore（当前 canonical Task truth）
  -> DirectProjectCodeExecutorAdapter
  -> Jiuwen project-bound Agent/Tool
  -> TaskEventSubscription / progress projection
  -> text or voice presentation + exact ACK
```

当前 Task truth 仍在 LiveVoice，不能在 AgentCore 候选未接受/安装/迁移前删除。
目标是用一个公共 AgentCore authority 替代 generic Task truth，再保留 product
scope、project adapter 和 voice/text presentation。

### 3.3 插话不是 Task cancel

```text
browser speech-start
  -> exact response_id + response_generation
  -> AgentConversationRuntime cancel/fence
  -> Gateway synthesis cancel
  -> browser local stop
```

`stop speaking` 与 `stop task <id>` 是不同 operation。Hermes Live Voice 也明确
分开这两个控制面；OpenJiuwen 额外要求跨 Runtime/Gateway/Browser 的 generation
和 presentation fence。

## 4. 模块对照

| Hermes Live Voice 边界 | OpenJiuwen 当前对应 | 目标位置 | 关键差异 |
|---|---|---|---|
| Browser SDK/audio | formal browser adapters、P1 route、Panel | L2 | Jiuwen 多 device/page ownership 与 playout proof，但目前 UI 绑定过深 |
| HTTP/WS inbound | existing WebChannel + dedicated media | L2/L3 | 已复用 Channel；注册/服务/cleanup 仍需抽成单一 leaf |
| Realtime Provider adapters | speech ports、batch/streaming/OpenAI routes | L1/L2 | 收敛 capability/fallback/cancel 与重复 contract |
| `LiveGatewaySession` | ConversationRuntime + AgentConversationRuntime + registry | L1/L3 | Jiuwen committed input、history/presentation authority 更严格；registry 过大 |
| Hermes Sessions Chat adapter | Jiuwen AgentManager/formal DeepAgent seam | L3/L4 | 直接复用已有 Agent/Harness；只保留 product provenance translation |
| `TaskSupervisor` | PersistentTaskCore + P3 composition | L4 target + L3 adapter | 两边都有 durable Task 责任；Jiuwen 当前 generic truth 放错层 |
| `FileTaskStore` | 14,951-line `SqliteTaskStore` | L4 target | Jiuwen contract 更宽，但不能整文件上移或双写 |
| Hermes Runs adapter | DirectProjectCodeExecutorAdapter | L4 + L3 split | generic attempt/result/effect 上移；project/worktree/patch policy 留 Jiuwen |
| Task snapshots/notifications | event subscription/progress/presentation | L4 input + L1/L3 policy | generic event/cursor 与 spoken/DOM/audio policy 必须拆开 |
| Dashboard/Web demo/terminal | Integrated Panel + legacy Demo | L2/L3/L5 | pinned UI 分布在 Dashboard、Web demo、Browser SDK、terminal；Jiuwen 当前 formal/legacy owner 同时存在 |
| config/doctor/setup | registry/config/observability/deployment assets | L3/support | runtime diagnostics 保留；benchmark/fault/probe re-home |
| protocol/domain | Python v2 + TS/local contracts + allowlists | L1/L2/L3 split | 需要 schema，但应生成窄 client types 并去掉重复统一合同 |

## 5. 为什么 LiveVoice 代码比 Hermes 多

当前 OpenJiuwen 可归因生产 footprint 是 163,264 physical LOC（159,210 行
专属路径 + 4,054 行共享宿主 LiveVoice symbol/segment）；pinned Hermes Live
Voice 是 25,254 行 shipped production，去除插件内两个完全相同的 SDK/worklet
拷贝后为 22,530 行。对应约 6.5 倍 shipped、7.2 倍去重实现；这两个比率都不能
直接当作删除目标，但能定位结构问题。

合理增加：Jiuwen 多 Channel/宿主、产品 principal/project/session、committed
input/confirmation、DOM 与 audio 分 surface proof、project/worktree/patch policy、
更强 scope/generation/negative-side-effect contract。

不合理增加：

- 在 LiveVoice 内重建 generic Task/Attempt/Command/Event/Outbox/Result/Cursor/
  Checkpoint/Effect authority；
- formal 和 legacy capture/Task/TTS 路径并存；
- Python/TypeScript schema、method allowlist 和状态值重复；
- `task_store.py`、registry、Panel、executor 四个多职责巨型文件共 42,985 行；
- 至少 7,837 行 test/reference/validation-facing code 放在生产路径；
- WebChannel、AgentServer、Deep adapter 中的 LiveVoice segment 未形成窄插件边界。

## 6. 当前必须避免的错误结论

- 不能说 Hermes 没有 Browser/Channel 或 durable Task。
- 不能说 JiuwenSwarm 没有 Channel/Web/Agent/History/Project 基础。
- 不能把 raw `TeamTaskManager`/`TaskDao` 当成已经可供 LiveVoice 使用的公共 API。
- 不能把本地 Scope/A1/A2/ADD/Facade candidate 当成 installed 或 submission-ready。
- 不能把 feature gate 等同于单一 runtime owner：`ChatPanel` 仍构造
  `useLiveVoiceDemo`。
- 不能把 streaming path 写成无条件语音：recognition 和 Task progress 都允许
  TEXT fallback。
- 不能把共享宿主 57,588 行整块归给 LiveVoice；当前只归因 4,054 行，53,534
  行宿主余量明确排除。

## 7. 目标收敛形态

目标不是一个“更小但职责仍混在一起”的目录，而是：

```text
LiveVoice Core
  = speech + commit + conversation/generation + barge-in + presentation policy

Channel adapters
  = browser/Web realtime-media leaf，可由其他 Jiuwen UI/Channel 实现

JiuwenSwarm product adapter
  = auth/project/session + Agent binding + history + UI + project effects

AgentCore
  = existing Agent/Harness + accepted shared Task/execution/event/effect/cursor owners

Retired after Gates
  = legacy Demo/Task lane + duplicate schema/state + production-tree test support
```

迁移前只完成映射、PR 准备、single-writer/canary/rollback 和 retirement Gate
设计。当前特性分支继续开发期间不移动 authority，也不把本准备分支的分析代码
合入产品分支。

## 8. 证据入口

- [零基线完整审计](OPENJIUWEN_LIVEVOICE_ZERO_BASE_MODULE_AUDIT_2026-08-31.md)
- [152-path inventory 与历史逐模块说明](OPENJIUWEN_LIVEVOICE_MODULE_DISPOSITION_AND_HERMES_COMPARISON_2026-08-25.md)
- [AgentCore symbol 迁移映射](OPENJIUWEN_LIVEVOICE_SYMBOL_MIGRATION_MAP_2026-08-24.md)
- [审计范围](OPENJIUWEN_AGENTCORE_HERMES_SLIMMING_SCOPE_2026-08-25.md)

详细文件行数、测试/support 分组、每条流程的 unresolved runtime evidence 和
Hermes 源码 baseline 不在本文重复维护，统一由零基线完整审计负责。
