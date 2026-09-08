# LiveVoice 目标架构：从能力出发的重写设计 — 2026-09-07

> 目的：回答"在保证功能正确的前提下，LiveVoice 应该怎样重写、怎样设计、怎样分层，才能把代码量降到最低"。
> 不以 Hermes 的形态为准绳（Hermes 没有 LiveVoice 的大部分产品责任，它的形态也未必对），只以 LiveVoice 自己
> 的能力清单与已接受的产品决定为准绳。本文是设计分析，不改代码，不改变
> [设计简化计划](LIVEVOICE_DESIGN_SIMPLIFICATION_PLAN_2026-09-07.md) 的承诺；它给出第二条路线（重写）与第一条
> 路线（分包重构到 60–65K）的关系，以及选择依据。基线 `hx/0907_livevoice_slimming@e20e7b19c`，170,706 行不含 Native。

## 0. 结论先行

1. LiveVoice 的产品能力可以用**一套身份、一份会话事件日志、三个进程各一个 owner、三张小库**表达完整。按这个
   架构自底向上估算，生产代码约 **23–24K 行**（浏览器 5.5–6.5K、Gateway 4K、AgentServer 13.5K），计入 20% 未知后
   **26–29K**；Native 13.2K 另计。这不是"Hermes 密度"的类比，而是按 LiveVoice 自己的操作数乘以合理密度得出的数。
2. 现在 170K 的体量来自五个结构性原因（§2），每一个都对应一个可替换的原语（§3）；替换之后消失的不是能力，是
   每个阶段各自重造的机制：13 个 Lease 类、10 个 Cleanup 类、44 个 Authority 类、28 个 Snapshot 类、36 个 Violation 类、
   642 个不同的 id 字段名。
3. 正确性不靠"每层都校验"，靠三个 chokepoint（会话事件日志的 append、任务台账的事务、授权 owner 的 consume）
   加两道 seam 上的录放差分测试（E2A 方法、浏览器 WS 协议）。§6 把每条已接受的产品决定映射到强制它的组件与
   证明它的测试。
4. 两条路线曾并存：路线 A 是分包重构到 60–65K（现有计划 S0–S8）；路线 B 是在两道 seam 之后重写核心到 26–29K。
   **2026-09-08 用户选择路线 B（D-121）**；两条路线共享的 S0、S1 与录放差分 harness 先做，B3 探针给出第一份实测后
   再继续 B4–B9（§10）。

## 1. 必须保留的能力（从产品决定倒推）

| 能力 | 来源决定 | 不变量（新架构必须强制） |
|---|---|---|
| C1 免提对话：采集 → 已提交的识别 final → 一次语义决定 → 对话/本地任务/澄清 → 播放与文本呈现 → 历史 | D-107、D-108、D-109、D-111、D-115 | 一个 final 只提交一次；一个已提交输入只做一次语义决定；Agent 原答不被改写；历史只记录被确认呈现的内容 |
| C2 打断：播放期插话取消 exact response；生成期打断关闭 exact response 的两个呈现面并只取消对话 round | D-104、D-106、D-114 | 取消对象是 exact response（按序号），不能扩大为 task.cancel；一个 interaction 不同时存在两个未围栏 response |
| C3 流式语音：identification/synthesis 资源的生命周期绑定到一次本地 grant；provider 不可用时 TEXT 降级 | D-113、D-105 | 新的采集/合成分配必须持有本次 turn 的 grant；grant 随 turn 结束回收；降级是显式结果不是异常 |
| C4 本地任务：创建/状态/调整/取消/结果；同项目串行且只接受精确的受管前序效果；确认绑定精确目标；权威读取有界；调整状态真实 | D-098、D-099、D-100、D-109、D-112 | 一个项目同时至多一个未结算 attempt；确认与 (task, attempt, args) 摘要绑定，一次性消费；状态由台账推导，不由内存猜测；UNKNOWN 是终态 |
| C5 多面交付与重连：浏览器/Gateway/AgentServer 三进程；重连不重复提交、不丢通知、不重复播放 | D-084 及 W2/W3 修复决定 | 每条通知有序号与 ACK；重连从序号续；已播放的不再播放 |
| C6 隐私与观测 | Alpha 隐私合同 | 音频、凭据、URL 不进日志与观测；观测记录只含闭合枚举与摘要 |

C1–C6 之外的东西都不是能力：例如"P1/P2/P3 三个激活阶段各有 journal"是实现，"四套确认 CAS"是实现，"三条 route
各自的 lifecycle"是实现，"每个 owner 一套 snapshot/reason/violation"是实现。§2 逐条说明它们为什么存在、为什么可以消失。

## 2. 现在为什么是 170K：五个结构性原因

| 原因 | 证据 | 后果 |
|---|---|---|
| R1 身份靠握手而不是靠序号 | 线上 642 个不同的 id 类字段名（`session_id`、`interaction_id`、`correlation_id`、`request_id`、`response_generation`、`activation_generation`、`turn_id`、`commit_id`、`lease_id`、`activation_lease`、`through_seq`…）；`Binding` 类 22 个、`Receipt` 类 7 个 | 每一对进程、每一个阶段都要发一次 ticket/lease/generation 并双向校验；每个校验一个守卫，每个失败一个 reason |
| R2 所有权靠 lease 对象而不是靠结构化并发 | `Lease` 类 13 个、`Cleanup` 类 10 个（`_TransportCleanupOwner`、`DedicatedMediaLeafCleanupOwner`、`_RetainedAttemptCleanup`、`P2FailedActivationCleanup`、`ProductObservabilityLease`…） | 每个异步资源自己实现 retained cleanup / close_with_result / reentrant close，重复十次 |
| R3 真相放在 owner 里而不是放在日志里 | `Owner` 17 个、`Authority` 44 个、`Snapshot` 28 个；浏览器三本 journal、AgentServer 的 activation/notification/presentation 三套 lease | 每个 owner 要自己做恢复、重放、去重、快照；重连逻辑在每个阶段各写一遍 |
| R4 校验在每一层重复 | 守卫行 25.9K（15%）、`Violation` 类 36 个、`Reason` 枚举 17 个约 200 个值；registry 每个 handler 各做一遍 scope/session/principal 校验 | 同一个不变量被检查五次，每次的失败类型不同 |
| R5 阶段被建成 owner | P1/P2/P3 各有 activation、journal、lease、cleanup、UI owner；三套 response fence | 一次对话被切成三个生命周期，交接处需要 binding/receipt 互相证明 |

这五条不是代码质量问题，是架构选择。同样的选择也能写出正确的系统（现在就是），只是每条不变量要用五倍的代码来守。

## 3. 设计原则（每条对应一个原因）

- **P1 序号身份**（对 R1）：一个会话只有 `session_id`；会话内一切可寻址的事物由同一计数器分配 `seq`（turn、response、
  notification、presentation unit、confirmation 都是某个 seq）；任务用 `task_id + attempt_no`；命令用 `command_id` 幂等。
  过期判断是 `seq < current`，不需要 generation/epoch/lease/ticket。线上的 id 类字段从 642 个降到 8 个。
- **P2 事件日志是会话真相**（对 R3）：AgentServer 为每个会话维护一份 append-only 事件日志（SQLite，一张表），
  约 15 种事件（§5.2）。运行时状态、浏览器视图、历史、通知投递都是日志的投影；重连 = `resume(after_seq)`；
  ACK = 一条事件。浏览器不再需要 journal，AgentServer 不再需要 notification lease 与 activation lease。
- **P3 每个进程每个关注点一个 owner**（对 R5）：浏览器 `Session` + `AudioEdge`；Gateway `MediaSession`；AgentServer
  `SessionRuntime` + `Authorization` + `TaskCore`。没有 P1/P2/P3 owner，阶段是 runtime 状态机里的状态。
- **P4 只在边界校验**（对 R4）：wire 入口用 schema 生成的 parser 校验一次；进程内调用只靠类型；一个
  `LiveVoiceError(code)`，18 个码；内部不变量用 `assert`，不是异常家族。
- **P5 结构化并发**（对 R2）：每个 turn/route/attempt 是一个 task group；取消传播到子任务；资源在 `finally` 关闭；
  超时用 `asyncio.timeout`。不存在"retained cleanup"——要么关闭成功，要么记一条 `unknown` 事件由 owner 决定。
- **P6 三张小库**：会话事件日志、授权 journal（已提交输入 + 确认 + 语义 pending）、任务台账（四张表）。每张库一个
  writer，事务边界就是不变量边界。
- **P7 用状态表和录放测试证明正确**：每个状态机有一张转移表测试；两道 seam 上录放真实流量做差分（§6.2）；物理
  demo journey 是最终验收。

与 Hermes 的差别是有意的：Hermes 没有会话日志（transcript 即状态）、没有 committed-input journal、没有显式确认、
没有流式识别、没有带持久效果的项目执行器。这些是 LiveVoice 的产品责任，本设计保留它们，只是用日志和序号而不是
用 lease 和握手来实现。

## 4. 目标架构

### 4.1 三进程与两道 seam

```text
浏览器                          Gateway                          AgentServer
AudioEdge ──LVM1 帧/控制──▶ MediaSession ──E2A: input.commit────▶ SessionRuntime ──▶ JiuwenSwarm Agent/Harness
Session   ◀──事件流(seq)────────────────────────────────────────  SessionLog       │
          ──命令(submit/barge/interrupt/ack/task.*)─────────────▶ rpc/handlers     ├─ Authorization(journal)
          ◀──合成音频帧──── MediaSession ◀── E2A: present.unit ── └─ TaskCore(四张台账) ─▶ ProjectExecutor(worktree)
```

seam 1：AgentServer 的 E2A 方法（§4.4 的 16 个）；seam 2：浏览器与 Gateway 的媒体 WebSocket（LVM1 帧 + 6 个控制
对象）。两道 seam 是录放差分测试的挂点，也是路线 B 的替换边界。

### 4.2 浏览器（TypeScript，5.5–6.5K）

| 模块 | 责任 | 行 |
|---|---|---:|
| `contract/generated.ts` | 由 schema 生成的类型与 parser | 0（生成） |
| `audio/edge.ts` | 采集（含 worklet 装载）、播放（含 playout receipt）、设备选择、跨页 ownership；事件 6 种；失败映射到 5 类 | 1,200 |
| `audio/worklet.js` | 采集 worklet | 200 |
| `audio/nearEnd.ts` | verified-headset 近端插话候选（RMS/峰值/回声相似度） | 300 |
| `session/session.ts` | 事件流客户端：`open/resume(after_seq)/close`，把事件折叠成视图状态；命令 `submit/barge/interrupt/ack/task.*`；未配置或运行条件不满足时进入明确的不可用状态并给出配置入口（D-122）；这就是全部"owner" | 900 |
| `session/media.ts` | LVM1 socket leaf：上行帧、下行帧、playout receipt；一个 lifecycle | 700 |
| `session/speech.ts` | 流式不可用时的批处理 STT/TTS RPC | 300 |
| `ui/Panel.tsx`、`ui/TaskPanel.tsx`、`ui/hooks.ts` | 视图；hook 只从 `Session` 状态派生 | 1,700 |
| `errors.ts` | `LiveVoiceError` 与 18 个码的文案表 | 100 |

消失的东西：`productWebActivation`（durable operation 客户端，2.2K）、三本 journal（1.7K）、`formalTaskIntentRoute/
ControlLeaf/P3TaskExperience` 三个 owner（2.9K）、`integratedWebRouteShell`（0.6K）、Panel 里的 recovery/diagnostics
（约 5K）、`liveVoiceContractV2.ts` 手写副本（2.8K）、legacy 链（3.1K）。它们的功能由"事件流 + resume"覆盖：重连后
浏览器不需要证明自己在哪个阶段，只需要从最后收到的 seq 继续。

D-122：正式语音入口进入标准构建，是否启用由产品配置与运行条件决定；`build:live-voice` 与普通构建的 profile 区分收敛为
运行时配置，机制在 B6 定。legacy 链在入口迁移完成后删除；runbook §7 的三种旧演示模式归档，仍需展示的能力迁到新
journey。第一版只交付 Gateway 路径的语音，浏览器识别与朗读路径随 legacy 退出，这是明确的取舍。

### 4.3 Gateway（Python，约 4K）

| 模块 | 责任 | 行 |
|---|---|---:|
| `media/session.py` | 一次激活一个 `MediaSession`：ticket 校验、attach/frames/ack/detach、playout receipt 转发、通知音频准备；grant 绑定到 `(session_id, turn_seq)`（D-113） | 1,000 |
| `media/route.py` | 上行识别 route 与下行合成 route 共用的 lifecycle：`begin/offer/finish/abort/next_chunk/cancel`，一个 task group | 500 |
| `media/codec.py` | LVM1 帧与 6 个控制对象的编解码 | 350 |
| `media/rpc.py` | WS 路由注册与 E2A 转发 | 250 |
| `speech/provider.py` | `SpeechProvider` ABC、`Capability`、`Fallback`（≤8 值）、注册表 | 250 |
| `speech/openai_batch.py`、`speech/openai_streaming.py` | 两个实现；传输对象自带 `aclose()` | 1,300 |
| `speech/fallback.py` | TEXT 降级与原因映射 | 100 |

消失的东西：`dedicated_media_registration.py` 8.4K 里的 registration/authority/diagnostics 三层、三条 route 各自的
lifecycle（5.9K）、conformance validator（2.2K）、两个 cleanup owner、`browser_gateway_media_transport.py` 里 24 个值类型
中的 18 个。Native 段（约 2.5K）不在本设计内，以 mixin 形式挂在 `MediaSession` 上，待 Native 单独 commit 采用新合同。

### 4.4 AgentServer（Python，约 13.5K）

| 模块 | 责任 | 行 |
|---|---|---:|
| `schema/` | refs、envelopes、task records、errors、codec；TS 生成器 | 1,000 |
| `session/log.py` | 会话事件日志：`append(session, kind, payload) -> seq`、`read_after(session, seq)`、`ack(session, seq)`；一张表 | 500 |
| `session/runtime.py` | `SessionRuntime` 状态机：interaction → turn → response → generation；fence；presentation spans；effect 队列；驱动 Jiuwen Agent/Harness 的 round；speculation | 1,800 |
| `session/history.py` | 从 `presentation.acked` 事件写 Session History | 200 |
| `session/progress.py` | 前台感知的通知策略：task 事件 → 出声/文本/静默 | 600 |
| `authorization/journal.py` | 已提交输入（digest）、确认、语义 pending；三张表 | 600 |
| `authorization/owner.py` | principal 认证、项目 scope、确认签发/消费（`UPDATE … WHERE consumed_seq IS NULL`）、critical token 澄清 | 700 |
| `authorization/semantics.py` | 唯一语义模型调用（闭合 schema）与有界连续性 | 700 |
| `authorization/intent.py` | 语义结果 → task 命令（D-109/D-111/D-112 的显式委托规则） | 500 |
| `task/executions.py`、`delivery.py`、`events.py`、`facts.py` | 四张台账（见设计简化计划 S2） | 2,100 |
| `task/core.py`、`admission.py` | facade 与 admission | 850 |
| `task/project_executor.py`、`worktree.py` | Code Agent 派发、流观察、结算；Git/worktree/patch/tree 指纹 | 1,700 |
| `task/importer.py` | 旧库一次性导入 | 300 |
| `rpc/handlers.py` | 16 个 E2A 方法：`session.open/resume/close`、`input.commit`、`response.barge/interrupt`、`presentation.ack`、`events.read`、`task.create/adjust/cancel/status/list/result`、`confirmation.issue/consume` | 900 |
| `composition/root.py` | 构造三个 owner、三张库、provider，注册 16 个方法；feature-off 时不分配 | 300 |
| `observability/observation.py`、`sink.py` | 闭合记录 + 隐私投影 + 一个 sink | 750 |

现在的 37 个 E2A 方法（`composition.p2.*` 8 个、`composition.p3.*` 7 个、`unified.submit`、`media.*` 4 个、`speech.*` 5 个、
`task_preparation.*` 4 个、`task.*` 8 个）收成 16 个：p2/p3/unified 的"激活、提交、通知拉取、呈现 ACK"合并为
`session.*`、`input.commit`、`events.read`、`presentation.ack`；`p3.progress.activate/ack/close` 消失（进度是事件）；
`p3.intent/intent.status` 消失（语义决定在 `input.commit` 内完成，结果是事件）。

消失的东西：`product_composition_registry.py` 16K（handler 工厂与逐 handler 校验）、`p3_authenticated_composition.py`
5.4K（第二个构造根）、四套确认 CAS（3.5K）、`agent_conversation_runtime` 与 `conversation_runtime_loop` 的双层
（6.6K → 1.8K）、`agent_bridge_runtime` 与 round harness 的双层（2.4K → runtime 内约 400 行）、`task_store.py` 15K
（→ 2.1K）、`formal_task_models` 2.6K（→ schema 内约 600）、durability 六文件 3K（→ `facts.py` 400）、
`task_progress_return` + `progress_notification_arbiter` 4.5K（→ 600）、`presentation_ledger` 1.3K（→ runtime 内
spans 约 200）、观测链 6.5K（→ 750）。

## 5. 关键机制

### 5.1 身份

| 事物 | 标识 | 分配者 | 过期判断 |
|---|---|---|---|
| 会话 | `session_id` | AgentServer `session.open` | 不过期，close 后拒绝 |
| 会话内一切（turn、response、notification、presentation unit、confirmation、事件） | `seq`（会话内单调） | `SessionLog.append` | `seq < runtime.current[kind]` 即过期 |
| 已提交输入 | `input_digest`（音频/文本摘要 + session） | 浏览器计算，journal 唯一约束 | 重复 digest → 返回原 seq，不重做 |
| 任务 | `task_id`、`attempt_no` | `executions` 台账 | 终态不可改写 |
| 命令 | `command_id` | 调用方生成 | `delivery` 台账幂等 |
| 媒体 grant | `(session_id, turn_seq)` | `MediaSession` | turn 结束即回收（D-113） |

现在的 `activation_id/activation_generation/response_generation/lease_id/activation_lease/commit_id/record_id/
correlation_id/subject_id/…` 全部由 `session_id + seq` 覆盖。`request_id` 保留在 wire 层做去重，不进入状态。

### 5.2 会话事件日志

一张表 `events(session_id, seq, kind, payload_json, acked_seq NULL, ts)`，`(session_id, seq)` 主键。事件种类约 15 个：
`session.opened/closed`、`input.committed`、`semantic.decided`、`response.started`、`response.presented`（一个 unit）、
`response.cancelled`（含 phase = playback|generation）、`response.done`、`clarification.requested`、`confirmation.issued/
consumed`、`task.created/updated/terminal`（从任务台账投影进来）、`notification.queued`、`presentation.acked`。

- 浏览器：`events.read(after_seq)` 长轮询或流；本地状态是事件的折叠；重连从 `after_seq` 续。
- 通知投递：`notification.queued` 是事件；浏览器播放后 `presentation.ack(seq)` 写回 `acked_seq`；未 ACK 的在重连后重放。
  取代现在的 notification lease、arbiter 的 queue/ACK/lease 机制、浏览器的三本 journal 与 Panel 的 recovery 段。
- 历史：`history.py` 只消费 `presentation.acked`，所以历史永远只含被确认呈现的内容（D-115）。

### 5.3 响应围栏

`SessionRuntime` 对每个 response 维护 `{generating, presenting, cancelled, done}` 四态；`barge(phase=playback)` 与
`interrupt(phase=generation)` 是同一个转移 `-> cancelled`，写一条 `response.cancelled` 事件，随后：关闭该 response 的
文本与音频呈现面（丢弃未 ACK 的 unit）、向 Gateway 发 `playback.stop`、只取消对应的 Agent round（D-104）。提交替换
turn 时先完成围栏再写 `input.committed`，所以一个 interaction 不会同时有两个未围栏 response。三套 fence 变成一个
四态机 + 一张转移表测试。

### 5.4 授权

`authorization/journal.py` 三张表：`committed_inputs(session_id, input_digest, seq)`、`confirmations(seq, scope, target_digest,
expires_at, consumed_seq NULL)`、`semantic_pending(session_id, seq, payload, expires_at)`。
`owner.consume_confirmation(seq, target_digest)` 就是一条 `UPDATE … SET consumed_seq=? WHERE seq=? AND target_digest=?
AND consumed_seq IS NULL AND expires_at > now`，受影响行数为 1 即成功。四套 CAS 变成一条语句；D-099 的"确认绑定
精确目标"由 `target_digest` 保证；D-108 的"语音证据不是授权"由 owner 只认 confirmation 行不认转写文本保证。

输入适配边界（D-122）：交互核心不把 Gateway 当成唯一合法身份来源。用户／服务身份、提交来源、输入证明是三个概念，
schema 与 journal 分别表达：身份回答谁有执行权限；来源回答请求经浏览器还是 Gateway；证明回答这是认证文本输入还是
绑定媒体 grant 的语音提交。第一版只实现 Gateway 语音提交与认证文本输入两种证明；不为未来的浏览器模式加入含义未定的
`principal` 占位字段，若审计已需要记录真实提交身份，则在 B1 定义其结构、认证依据与重放语义。

### 5.5 任务

四张台账（设计简化计划 S2 的定义），加两条关系：任务事件投影进会话事件日志（`task.*` 事件带 `task_id`），进度策略
（`session/progress.py`）读前台状态（是否在生成/播放）决定出声还是文本；D-098 的串行由 `executions.has_unsettled(project)`
一句查询保证；D-100 的"权威读取有界"天然成立，因为读取就是一次台账快照，没有内存副本可漂移。

### 5.6 媒体与 provider

`MediaSession` 一次激活一个；grant 与 turn 同生命周期；上行识别与下行合成共用 `route.py` 的 lifecycle；provider 只有
ABC + 两个实现；conformance 校验取消（provider 自报能力），错误映射到 `Fallback`。LVM1 帧格式不变，控制对象 24 → 6。

### 5.7 错误与校验

错误是三部分（D-123）：`code` 表达类别；受控诊断字段是白名单结构，至少含模块、阶段、闭合子原因、结果确定性
（none/applied/unknown）；用户文案按界面语言展示。`detail` 自由文本只进日志，观测记录只含 `code` 与白名单字段。
行为由 `code`、结果确定性与阶段共同决定：超时且结果未知按 `command_id` 或 `task_id + attempt_no` 对账，不重建。
wire 入口：生成的 parser 校验一次，失败 → `invalid_input`；授权失败 → `unauthorized/forbidden`；过期序号 → `stale`；
同一命令身份携带不同内容 → `conflict`；资源 → `capacity/unavailable`；provider 失败记在 provider 事件，文字降级记在
响应事件的交付状态 `degraded`；不确定 → `result_unknown`。类别码的数量是 B0 映射表的结果，不是指标。进程内不再抛
类型化违规；不变量用 `assert`。守卫从 25.9K 行降到约 2K。

### 5.8 并发

每个 turn 是一个 task group（识别 → 语义 → round → 呈现），取消传播；每个 route、每个 attempt 也是 task group；关闭在
`finally`；超时用 `asyncio.timeout`。没有 retained cleanup、reentrant close、close_with_result：关不掉就写 `unknown` 事件，
由 owner 决定。

## 6. 正确性如何保证

### 6.1 不变量 → 组件 → 测试

| 不变量（来源） | 强制它的组件 | 证明它的测试 |
|---|---|---|
| 一个 final 只提交一次（C5） | `committed_inputs` 唯一约束 | 同一 digest 提交两次 → 同一 seq，日志只有一条 `input.committed` |
| 一次语义决定（D-107/D-111） | `input.commit` 内唯一调用 `semantics.decide` | 每个 turn 恰好一条 `semantic.decided` |
| 语音证据不是授权（D-108） | owner 只认 `confirmations` 行 | 只有转写、无确认行 → mutation 被拒 |
| 显式委托免二次确认（D-109/D-112） | `intent.py` 的规则表 | 规则表驱动测试 |
| exact response 取消、两面关闭、只取消 round（D-104） | 四态机 + `response.cancelled` | 转移表测试；打断后日志无第二个未围栏 response；task 台账无变化 |
| 历史只含被确认呈现的内容（D-115） | `history.py` 只消费 `presentation.acked` | 中途打断 → 历史等于已 ACK 的 unit 集合 |
| 资源生命周期绑定 grant（D-113） | `MediaSession` 的 grant 表 + task group | N 个 turn 后 provider 客户端与 route 数量为零 |
| 同项目串行、只接受精确前序效果（D-098） | `executions.has_unsettled` + `facts.latest_settled_effect` | 并发创建 → 第二个进入 queued；dirty tree → 拒绝 |
| 确认绑定精确目标、一次性（D-099） | `consume_confirmation` 的 UPDATE | 两线程同时消费 → 恰好一个成功；目标摘要不同 → 失败 |
| 状态由台账推导（D-100/D-112） | 无内存副本 | 崩溃重启后 `task.status` 与台账一致 |
| UNKNOWN 终态、不重放 | `delivery.recover_abandoned` | 杀死 owner 进程 → 行变 unknown，不重投 |
| 通知恰好一次、重连不丢（C5） | 事件日志 + `acked_seq` | 断线重连 → 未 ACK 的重放，已 ACK 的不重放 |
| 隐私零泄露（C6） | `observation.py` 投影 + sink | 合成秘密与音频字节 canary |

### 6.2 录放差分测试

在两道 seam 各放一个录放器：E2A 方法的请求/响应/事件序列，媒体 WS 的控制对象与帧摘要（不存音频）。用
`scripts/live_voice/semantic_audio_*` 的合成语音 journey 驱动旧实现录一遍，再驱动新实现，比对：已提交 final、语义
决定、呈现 unit 顺序、ACK 后的历史、任务台账终态。差异只允许出现在设计简化计划 §4 声明的 SC 项上。这套 harness
在路线 A 与路线 B 都需要，是最先要建的东西。

harness 常驻一条隐私断言：合成秘密与音频字节 canary 不得出现在任何记录、日志、事件与观测表面（沿用
`alpha_privacy_conformance` 的 canary 技术）。harness 不自动覆盖安全部署、隐私与故障验证；S7 五项检查的后继位置：

| S7 检查 | 后继 | 包 |
|---|---|---|
| speech-media | 媒体 seam 录放差分 + D-113 资源计数测试 + 帧 ACK 完整性断言 | B2、B5 |
| agent-executor | 任务台账状态表测试 + 项目执行 journey（真实 worktree） | B4 |
| benchmark-fault | 耗时测量脚本（出生产树的 `l0/latency_measurement.py`）+ provider 故障 journey | B7、B9 |
| secure-deployment | B9 的部署检查（凭据不在树内、私有输入路径、TLS/来源限制），独立于 harness | B9 |
| privacy | harness 常驻 canary 断言 + `observation.py` 隐私投影测试 | B2、B7 |

### 6.3 最终验收

物理 demo journey（`start_hands_free_demo.ps1`）、formal web 验证、合成语音 journey 三者 PASS；`anatomy_modules.py`
的预算（值类型 ≤150、异常类型 ≤12、守卫 ≤4K、owner ≤30、`throw` ≤150）全部达标；错误类别码的数量不设指标（D-123）。

证据绑定（D-122）：保留轻量、自动的候选与运行证据绑定。绑定项三类：测的是什么（源码提交、构建标识、实际运行的服务
与前端资源版本）、哪种运行方式（关键配置、feature flag、运行编号）、验证了什么（检查结果、失败原因、证据引用）；
分支、领先落后数、工具版本只记录，不作拒绝条件。运行时标识从实际运行的制品取得（服务自报构建标识，前端 bundle
携带构建标识），不由启动脚本重写 HEAD。开发与诊断运行允许脏树但必须记录；正式候选验收用冻结源码与可识别构建产物，
校验一致。轻量驱动只做身份与配置采集、一致性检查、运行编号与结果汇总，业务验证由 harness 与 journey 承担。

## 7. 规模估算（自底向上）

| 进程 | 操作数与密度假设 | 估算 |
|---|---|---:|
| 浏览器 | 事件 15 种 × 折叠 20 行 + 命令 8 个 × 30 行 + AudioEdge（采集/播放/设备/ownership 4 个子系统 × 300）+ 媒体 leaf 700 + UI 1,700 | 5.5–6.5K |
| Gateway | MediaSession 8 个操作 × 80 + route lifecycle 6 个操作 × 60 + codec 350 + provider 2 × 650 + fallback/rpc 350 | 4K |
| AgentServer | 16 个 E2A 方法 × 55 + 状态机 4 态 × 转移 ≈ 600 + round 驱动 400 + 台账 45 个操作 × 45 + 授权 3 表 × 200 + 语义 700 + intent 500 + 项目执行器 1,700 + schema 1,000 + 观测 750 | 13.5K |
| 合计 | | 23–24K |
| 含 20% 未知 | | 26–29K |
| 测试（按 1.2 倍） | 状态表、台账并发/重启、录放差分、canary、前端 mounted、journey | 28–35K |

与设计简化计划的 48–62K 相比，差额来自 §2 的五个原因被原语替换：不再有 P1/P2/P3 三套 owner（约 12K）、四套 CAS 与
逐 handler 校验（约 10K）、三条 route lifecycle 与 conformance（约 8K）、Store 的通用层与 durability 六文件（约 12K）、
通知 lease/journal/recovery（约 6K）、观测三通道（约 5K）。

## 8. 两条路线与选择

| | 路线 A：分包重构（现有计划 S0–S8） | 路线 B：seam 之后重写（本文） |
|---|---|---|
| 目标 | 60–65K | 26–29K |
| 方法 | 在现有 owner 上换合同、合并、删守卫；每包独立回滚 | 在 E2A 与媒体 WS 两道 seam 之后新建 `session/`、`authorization/`、`task/`、`media/`，feature flag 切换，旧实现作 oracle |
| 风险 | 低：每包可比对旧套件失败集 | 中高：一次性替换核心；靠录放差分与 journey 兜底 |
| 工期 | 长（每包都要处理旧 owner 的耦合） | 短于 A 的总和（不需要与旧结构妥协），但前期 harness 与 schema 是硬前置 |
| 测试 | 旧套件按包退役，新测试逐包写 | 旧套件只作 oracle，新测试从状态表与录放出发重写 |
| 共享前置 | S0（授权、基线、错误码表）、S1（schema 与生成器）、录放 harness | 同左 |
| 分岔点 | S2 开始在旧 Store 上做台账 | S2 开始在新包里做 `session/log.py` + `task/` |

决定（D-121，2026-09-08）：选择路线 B。先做 S0、S1 和录放 harness；harness 跑通后用它给 AgentServer 的 `session/` 与
`authorization/` 做 B3 探针（约 4K 行新代码替换约 40K 行旧代码），探针的行数比例与差分结果决定是否继续 B4–B9。
任务台账（S2）在两条路线里是同一份设计。包序列见 §10。

## 9. 风险与未知

- 估算未经实测：本文的密度假设（每个 E2A 方法 55 行、每个台账操作 45 行）来自 Hermes 与本仓库 exporter 探针的数量级，
  不是 LiveVoice 上的测量；探针（§8）之前不要把 26–29K 写成承诺。
- 事件日志的体量：每会话事件数上限、保留期、压缩策略要定，否则日志会成为新的膨胀点；建议每会话 ≤10K 事件、
  close 后 7 天归档。
- 语义模型与 Agent 的耦合：`semantics.py` 与 round 驱动是不可压缩的产品逻辑，估算里已按现状保留。
- Native：13.2K 不在本设计内；它依赖现在的 runtime/registry/media 内部接口，路线 B 落地后 Native 必须按新合同重做，
  否则要维持一套兼容层，那会把总量抬回 40K 以上。
- 协议变更：16 个方法取代 37 个，浏览器与 AgentServer 必须同步切换；用 feature flag 双跑一个包周期。
- 构建标识：D-122 的制品绑定要求服务与前端 bundle 自报构建标识；字段在 B1 定，B6/B7 落地，否则 B9 只能绑定声明。

## 10. 路线 B 的包序列（D-121）

每包独立提交、不推送；新实现在 `live_voice.v2.*` 方法名与 feature flag 之下上线，旧实现保留到 B8 之后一个包周期。
"复用"列指设计简化计划里可以原样执行的卡片；没有复用的包按本文 §4–§5 的模块表与 §6 的不变量表执行。

| 包 | 交付 | 验证 | 回滚 | 复用 |
|---|---|---|---|---|
| B0 授权与基线 | D-121/D-122/D-123 已记录；基线失败集、18 模块行数、D-123 七列映射表（原触发条件、操作、结果确定性、处理动作、目标 code、诊断字段、文案键）、`semantic_audio_*` 回收；开始记录 D-122 退休前检查 1–2 的结果 | S0 卡的完成判据；映射表覆盖 27 个 reason 枚举的 311 个值 | revert | S0 卡 |
| B1 schema 与记录 | `common/schema/live_voice/`（refs、envelopes、task records、errors、codec）；新增 §5.2 的 15 种事件与 16 个命令的 envelope；TS 生成器 | S1 卡的完成判据 + 事件/命令 schema 生成幂等 | 不接入即无影响 | S1 卡 |
| B2 录放 harness | E2A 方法录放器、媒体 WS 控制对象/帧摘要录放器、差分比对器；常驻 canary 隐私断言；用合成语音 journey 录制旧实现的基线 traces。harness 不覆盖安全部署、隐私投影与故障验证，见 §6.2 表 | 旧实现两次录制自比对零差异；每条 journey 有一份基线 trace；canary 断言在旧实现上通过 | 无 | 新（`scripts/live_voice/replay/`） |
| B3 会话核心探针 | `session/log.py`、`session/runtime.py`、`session/history.py`、`session/progress.py`、`authorization/*`、`rpc/handlers.py` 的会话与授权部分（`session.open/resume/close`、`input.commit`、`response.barge/interrupt`、`presentation.ack`、`events.read`、`confirmation.issue/consume`）、`composition/root.py`；flag 关闭 | §6.1 表中前 7 条不变量的测试全过；对旧实现的差分只含 SC 项；新代码 ≤ 估算 × 1.3（session ≤ 4.0K、authorization ≤ 3.3K） | 关 flag，删包 | 本文 §4.4、§5.2–5.4、§5.7–5.8；S3 卡的 symbol 处置表用于确认没有漏掉的责任 |
| 门 | B3 的行数比例与差分结果由用户审阅后决定是否继续 | — | — | — |
| B4 任务台账与执行器 | 四张台账、`core.py`、`admission.py`、`project_executor.py`、`worktree.py`、`importer.py`；任务事件投影进会话日志 | S2 卡的完成判据 + §6.1 表中 D-098/D-099/D-100/D-112/UNKNOWN 五条 | 旧 Store 只读 + importer 反向演练 | S2 卡（`task/events.py` 改为向会话日志投影） |
| B5 Gateway 媒体与 provider | `media/session.py`、`route.py`、`codec.py`、`rpc.py`、`speech/*`；grant 绑定 `(session_id, turn_seq)`；Native 段以 mixin 挂载 | S5 卡的完成判据 + 媒体 seam 差分 + D-113 资源计数 | 关 flag | S5 卡 |
| B6 浏览器 | `audio/*`、`session/session.ts`（事件流客户端，含未配置的不可用状态）、`session/media.ts`、`session/speech.ts`、`ui/*`、`errors.ts`；正式入口进入标准构建，启用由配置与运行条件决定；旧演示模式归档、仍需展示的能力迁到新 journey；入口迁移完成后删除 legacy 链（D-122） | 前端 mounted 测试、三条 journey；标准 `build` 通过，未配置时显示不可用状态；`throw` ≤150 | 关 flag | S6 卡的 AudioEdge 与 legacy 退休部分 |
| B7 观测 | `observability/observation.py`、`sink.py`、前端 `observability.ts`/`diagnosticsSink.ts`；退休旧 OTel 实现与 S7 工具，第一版不提供外部导出（D-122） | S7 卡的完成判据；D-122 退休前检查 1–4 全部有记录；四类性质各有指名测试 | revert | S7 卡 |
| B8 cutover | flag 默认 v2；删除旧 `server/live_voice`、`gateway/live_voice`、前端 `features/live-voice/formal` 中被替代的文件与其测试；E2A 37 → 16 | 旧 symbol grep 为零；三条 journey PASS；旧套件只剩已迁移的用例 | 一个包周期内切回 flag | — |
| B9 验收与计量 | 轻量证据绑定驱动（身份与配置采集、实际制品标识一致性、运行编号、结果汇总）、部署检查、物理 journey、独立评审、`anatomy_modules.py` 预算、多仓口径报告、STATUS/README 更新 | S8 卡；正式验收证据绑定冻结源码与构建产物，开发运行如实记录脏树（D-122） | — | S8 卡 |
