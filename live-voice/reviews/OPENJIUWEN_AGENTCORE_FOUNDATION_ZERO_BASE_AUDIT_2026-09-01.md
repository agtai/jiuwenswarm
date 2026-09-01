# OpenJiuwen AgentCore 基础能力零基线审计 — 2026-09-01

> 状态：D-097 接受的冻结后瘦身准备事实。本文只回答 AgentCore 已有什么、
> 可以怎样复用、真正缺什么、LiveVoice 当前实现中哪些只是候选证据以及历史
> 15,128 行为什么不能整体采用。本文不实施产品改动，也不把任何本地候选称为
> 已安装能力。

## 1. 结论先行

此前“13 个 `AGENTCORE_PR` 原子责任”只完成了**归属方向识别**，没有完成
AgentCore 最小实现拆分。若据此理解为“AgentCore 需要接收约 15K 生产代码”，
这个理解是错误的。零基线复审得到以下结论：

1. 当前 LiveVoice 锁定的 AgentCore 已有 Agent、Tool、Runner、DeepAgent/Harness、
   Task DAO/Manager、Scheduler、AsyncToolRuntime、Checkpointer 和 Workflow Journal
   等基础 primitive；必须优先复用，不能在 LiveVoice 或 AgentCore 候选中另搭一套。
2. 锁定版本和刷新后的 `origin/develop` 都没有满足当前 LiveVoice 所需的 scoped
   durable Task、事务事件/游标、durable execution ownership、checkpoint publication
   和 external-effect truth 的完整公开合同。这些是**基础能力缺口**，不是 Voice
   特性，也不是把 LiveVoice 文件整体移动过去的理由。
3. 13 个原子 locator 应收敛成 **4 个事务能力族、6 个最小公共 seam**。13 是
   Jiuwen 当前代码中的定位数量，不是 AgentCore 模块数、提交数或未来文件数。
4. 历史 AgentCore 候选相对干净基线新增 **15,128 行生产代码**，只能证明一种
   实现尝试。它包含必要安全语义，也包含 God DAO、重复 reducer/校验、纯转发
   Manager、过厚 Authority、扩大 48 个公共导出以及尚无生产 consumer 的接口。
   因此 15,128 不是需求、预算、最小值或可整体复用资产。
5. 未来只能按能力重新实现或选取最小可证部分；不得 wholesale port LiveVoice 的
   `SqliteTaskStore`、`_DirectProjectAttemptJournal`，也不得 wholesale replay 历史
   AgentCore 候选。
6. AgentCore 最终应只有一个 generic transaction/reducer owner。JiuwenSwarm 只留
   principal/project/session 映射、Voice/产品 envelope、Project/Git/Tool 行为、
   presentation ACK、checkpoint payload codec 和 effect provider/compensation policy。

所以，对“为什么一定要合入几万行”的直接回答是：**没有理由，也没有这个结论。**
可以证明的是六项通用语义中有缺口；不能证明的是缺口必须用 15K 行实现。

## 2. 审计基线与证据等级

| 对象 | 固定事实 | 本文如何使用 |
|---|---|---|
| Jiuwen/LiveVoice 产品事实 | `hx/0812_live_voice_w3@59998e2c5724257bd410885b35e59e1b37027030` | 13 个 locator、真实 caller、物理容器和 Host/Product 边界 |
| LiveVoice 锁定依赖 | `openjiuwen 0.1.16@94e10cb6102c36fe78a64547957c0def97299273` | 只有这里已公开的能力可称“当前直接复用” |
| AgentCore 干净历史基线 | `4f2c29c34899a45cec56a7d765fcc95e4002f60a` | 历史候选增量对账基线 |
| AgentCore 刷新上游 | `origin/develop@6390bbf230f4ea2dd7446bc01ee882e6a4413d4c` | 验证缺口是否已被上游自然补齐 |
| AgentCore 历史候选 | `50c065dc7fb5e0c21903128d1a033c52968be97e` | 仅作可行性、复杂度、重复和风险证据 |
| 原子处置 | [228 项责任 manifest](OPENJIUWEN_LIVEVOICE_ATOMIC_DISPOSITION_2026-08-31.md) | 稳定 locator；本审计纠正其中 13 项的实现粒度 |

证据强度依次为：已安装公开 API > 刷新上游源码 > 当前 Jiuwen 真实 caller > 历史
候选源码与测试。历史候选即使局部测试通过，也不能覆盖其已有 Critical/Important
源码审查结论，不能升级为已接受架构。

本文使用路径和 stable symbol 说明边界，不把易漂移的源码行号当迁移合同。

## 3. 判定方法：直接复用、适配复用、基础能力新增、Jiuwen 保留

| 判定 | 必须同时满足 | 结果 |
|---|---|---|
| `DIRECT_REUSE` | 已安装 public API 已拥有所需生命周期和 truth；Jiuwen 不再解释同一状态 | 直接调用，只做参数/结果传递 |
| `ADAPT_REUSE` | 已有 primitive 拥有主体机制，但缺少 Jiuwen 类型映射或窄 Port | Adapter 只能映射，不能成为第二 writer/reducer |
| `AGENTCORE_FOUNDATION_ADD` | 语义不依赖 Voice、Project 或 UI；多个 Agent/Tool/Task 使用方需要；当前 public API 缺失；放在 Jiuwen 会产生重复通用 authority | 在现有 AgentCore owner 上补最小合同，不复制现有系统 |
| `JIUWEN_KEEP` | 语义解释 principal/project/session、Voice turn、presentation、Git/worktree、provider 或产品 policy | 留在 Jiuwen；只通过 opaque extension/Port 接入基础能力 |
| `REJECT/RETIRE` | 与已有 owner 重复、没有生产 adopter、只为历史候选层级服务，或让两个 writer 同时成立 | 不迁移；满足 replacement Gate 后删除 |

`AGENTCORE_PR` 是旧 manifest 的稳定处置码。自 D-097 起，它在当前权威链中只读作
`AGENTCORE_FOUNDATION_ADD`，不是交付方式，也不代表其 locator 的全部源码应进入
AgentCore。

## 4. AgentCore 当前已经有什么

### 4.1 可以直接复用

| 已有 owner / public surface | 当前可复用责任 | LiveVoice/Jiuwen 不应再做 |
|---|---|---|
| `Runner.run_agent` / `Runner.run_agent_streaming`、Base Agent、Tool | Agent 与 Tool 调用、streaming 执行 | 再造通用 Agent/Tool runtime |
| DeepAgent/Harness interaction handle | 长运行交互、`attach_output` / `send_input` 等既有 carrier | 用 Voice facade 假装拥有 Agent lifecycle |
| `TeamAgentSpec` / Team build lifecycle | Team/Agent 组合与生命周期 | 另建 Voice 专属 Team registry |
| Session VCS / Session public boundary | 会话状态与既有持久化能力 | 把 Task authority 塞回 Voice Session store |

### 4.2 只能作为 primitive 适配复用

| 已有 primitive | 能复用的部分 | 当前缺口 / Adapter 上限 |
|---|---|---|
| AgentTeams `TaskDao`、`TeamTaskManager`、`TeamTaskBase` | Task CRUD、状态、claim、依赖图和数据库事务底座 | 需要 scoped Task/Attempt/CAS/ledger；Adapter 不得另建 Task store |
| `TaskScheduler`、mailbox/EventBus | 调度与非权威投递 | 不能替代与 Task 状态同事务提交的 event/outbox truth |
| `AsyncToolRuntime.launch/cancel/wait` | 内存 worker 与实际 Tool runtime | 需要 monotonic cancel、terminal callback fence、durable owner/restart reconcile |
| Core `Checkpointer` / `PersistenceCheckpointer` | opaque checkpoint payload 存取 | 需要 Task/Attempt/source-event 绑定的 publication reference；Jiuwen 留 codec/内容 |
| Workflow `Journal` | 已完成调用的 cache/WAL、prefix 思路 | 不能证明外部副作用未发生/已发生/结果不确定；不能冒充 effect ledger |
| `SessionFileStore` / GraphStore | payload/file 存储 | 不是 Task、checkpoint publication 或 effect truth |

### 4.3 当前明确不存在完整公开合同

在锁定依赖 `94e10cb` 和刷新上游 `6390bbf` 中，没有找到能够完整替代以下六项
Jiuwen authority 的公开能力：

- scoped durable Task/Attempt/command/result；
- transactional Task event/outbox；
- event consumer cursor；
- durable execution ownership 与 monotonic settlement；
- execution-bound checkpoint publication；
- external-effect intent/evidence/reconcile。

这说明需要补基础能力；不说明历史候选的文件、类型数量或实现层级正确。

## 5. 13 个 locator 应怎样收敛

### 5.1 四个事务能力族、六个公共 seam

| 事务能力族 | 最小公共 seam | 原子 locator | 共同 transaction owner |
|---|---|---|---|
| K1 Scoped Durable Task | F1 Task/Attempt/command/result | AR-089、AR-139、AR-167、AR-206、AR-209，及 AR-204 的 Task 侧 | AgentTeams Task transaction service |
| K2 Ordered Event Consumption | F2 event/outbox；F3 consumer cursor | AR-204、AR-207，及 AR-089/AR-139 的 event/envelope 部分 | 同一 Task transaction service；cursor 是窄子存储，不重验 event truth |
| K3 Durable Execution Ownership | F4 execution lease/cancel/settlement | AR-127、AR-189、AR-190，及 AR-167/AR-209 的 recovery 部分 | execution service 与 Task transaction composition seam |
| K4 Checkpoint / External Effect Durability | F5 checkpoint publication；F6 effect journal | AR-127、AR-130、AR-132、AR-205 | 同一 execution/durability transaction owner；payload/provider 为 Port |

“四个”表示**每个 family 内相关 truth 必须通过同一原子事务协作**，不是要求
K1–K4 四族一次性交付；“六个”是可以独立定界、实现和审查的最小公开 seam。
它们不是四套数据库或六套 DAO。K1–K4 的元数据和权威引用应由一个 AgentTeams
持久化 transaction owner 承载。

### 5.2 13 项逐项纠正

| 原子项 | 当前 stable symbol 的真实性质 | 未来处理 | 明确不整体下沉的部分 |
|---|---|---|---|
| AR-089 | Scope/command/query/result/event 与 Voice/Host schema 混合 | 只抽 F1/F2 canonical core，Jiuwen 做 schema Adapter | Turn、response generation、origin、presentation、session-history |
| AR-127 | 一次操作、精确绑定、一次消费的 mutation capability | F4/F5/F6 共用的窄授权 contract | Jiuwen 授权/确认 policy、密钥和 principal/project 解释 |
| AR-130 | effect lifecycle 的部分 locator；真实能力还含 continuation、dispatch、observation、settlement、codec | F6 单一 journal/reducer | Tool/provider 调用、项目补偿和业务副作用 policy |
| AR-132 | checkpoint/effect prefix verifier；直接 caller 主要是 Task store | F5/F6 共用 record codec identifier、canonical metadata encoding/digest；只验证一次 | Jiuwen D1 payload codec/validation、Voice/Product checkpoint 内容 |
| AR-139 | 38 个 Task/Attempt/event/cursor/outbox 与产品类型混合 | 按 F1/F2/F3/F4 只补缺失 value；不整体搬模型文件 | project instructions、路径、权限、redaction、display/artifact vocabulary |
| AR-167 | recover、outbox drain、reconcile orchestration | K1/K2/K3 facade；不复制 PersistentTaskCore | product projection、project executor 选择和 operator event |
| AR-189 | `_DirectProjectAttemptJournal` 是 generic execution 与 Project/Git 状态的混合接缝 | 仅抽 F4 ExecutionRecord/lease/generation/terminal disposition | worktree、Git、patch、symlink、protected support、cleanup/governance |
| AR-190 | release-once、heartbeat、settlement 与 checkout critical section 混合 | F4 承接 generic worker ownership | “worker 是否仍会触碰 checkout”的项目安全语义 |
| AR-204 | event read/outbox 方法只是更大 truth 的入口 | F2 与 F1 同事务承接，禁止复制另一 Store | Voice event mapping、presentation/history side effects |
| AR-205 | 授权后追加 checkpoint/effect fact | F5/F6 append/publication contract | payload/operation 的项目解释 |
| AR-206 | mutation replay/result 与 adjustment 产品行为混合 | F1 scoped CAS command/result | confirmation、adjustment policy、presentation ACK |
| AR-207 | generic cursor 与 text/voice/DOM/audio adoption 混合 | F3 只保留 consumer/channel/sequence/version CAS | audible/DOM truth、presentation class、history adoption |
| AR-209 | scoped create/read/retry/recovery 与 FormalTaskSpec 混合 | F1/F4 承接 Task/Attempt/recovery fence | project spec、business retry policy、Git readiness |

AR-189 是最重要的纠错：整个 `_DirectProjectAttemptJournal` 不是 AgentCore 基础能力。
AR-139 和 AR-207 也必须先拆产品类型。AR-204–AR-209 不能按方法复制到另一 Store，
否则得到永久双 writer，而不是下沉。

### 5.3 当前真实调用链与切割点

```text
create_p3_composition_from_environment
  ├─ SqliteTaskStore
  ├─ DirectProjectCodeExecutorAdapter
  │    └─ _DirectProjectAttemptJournal
  └─ PersistentTaskCore
       └─ P3AuthenticatedComposition

产品 Command / Query
  → voice_task_policy 构造 product envelope
  → P3AuthenticatedComposition
  → PersistentTaskCore.execute / query
  → SqliteTaskStore create/update/adjust/cancel/retry/ack/result/unread

start / reconcile / stop
  → PersistentTaskCore.reconcile
  → recover_durable_attempt / claim_outbox
  → DirectProjectCodeExecutorAdapter dispatch/cancel/adjust
  → complete_outbox / reconcile_status

DirectProjectCodeExecutorAdapter._dispatch
  → execution identity + attempt journal + OS lock
  → Agent stream + worktree/Git/patch/protected-support
  → checkpoint/effect append + settlement + cleanup

Event / progress
  → TaskEventSubscription + consumer cursor
  → event-to-product progress projection
  → DOM/audio presentation + Session History
```

切割点不是“把一个类搬走”，而是把调用链中的 generic truth 换成 F1–F6 public
seam：Store/Core 的 Task/Event truth 对应 F1–F3，executor journal 的 owner/settlement
对应 F4，D1/D2 权威引用对应 F5/F6。envelope projection、Agent 选择、worktree/Git、
DOM/audio/history 仍留在 Jiuwen 两侧，因此 `_run_attempt`、`SqliteTaskStore` 和
`PersistentTaskCore` 都不能整类进入 AgentCore。

## 6. 六个最小基础能力为什么需要、怎样最小化

### F1. Scoped Durable Task / Attempt / Command / Result

- **为什么是基础能力：** 长运行 Agent/Tool Task 需要在 crash/retry 后仍能证明 Task、
  Attempt、scope、generation、command replay 和 terminal result 的唯一 truth；这不依赖
  Voice、浏览器或 Project。
- **复用什么：** `TaskDao`、`TeamTaskManager`、`TeamTaskBase`、Task 状态/依赖图、
  `DbSessions.write`。
- **只新增什么：** `(scope, task)` 强制谓词/约束，Task–Attempt 关系，generation/
  revision CAS，idempotent command ledger，immutable result，retry lineage 和 recover
  admission。
- **不新增什么：** 第二套 Task model/store、Voice envelope、Project spec、Manager 纯转发
  facade、另一套 canonical projection。
- **为什么旧能力不够：** 旧 point operation 主要按 `task_id`，没有完整 Attempt generation、
  command replay 和 restart recovery fence。

### F2. Transactional Task Event / Outbox

- **为什么是基础能力：** Task 状态改变和对外可见事件必须同事务提交；否则 crash window
  会出现“状态已变但事件丢失”或“重复 launch”。
- **复用什么：** Task transaction、Scheduler delivery adapter、EventBus/mailbox 传输。
- **只新增什么：** per-Task monotonic sequence/head、canonical event、同事务 outbox、claim
  lease、complete/release/reclaim 和 dispatch receipt。
- **不新增什么：** Voice progress event、Web delivery truth、第二个 Scheduler、独立于 Task
  writer 的 event database。
- **历史候选问题：** producer/outbox 已实现，但 `drain_dispatch_once` 在仓库内没有生产
  consumer；不能称完整 composition。

### F3. Generic Event Consumer Cursor

- **为什么是基础能力：** 多 consumer/channel 在 reconnect/replay 时需要隔离、单调、CAS
  的已消费位置；timestamp/read-status 不能稳定表达 stream incarnation 和 sequence。
- **复用什么：** F2 canonical event identity/head；必要时统一 command/receipt primitive。
- **只新增什么：** consumer/channel/scope/event-stream identity、一张 cursor row、expected
  sequence/version CAS；只有正式 threat model 要求时才增加防篡改 receipt chain。
- **不新增什么：** 重做 event prefix verifier、DOM/audio heard/displayed truth、Voice
  presentation class。
- **历史候选问题：** `cursor_dao.py` 约 1.6K 行却只有 `read_unread` / `advance` 两个
  public operation，并重复验证 event prefix，是最明确的过度实现候选。

### F4. Durable Execution Ownership / Cancel / Settlement

- **为什么是基础能力：** process crash、duplicate launch、lease expiry、cancel/complete race
  和 late callback 会影响任何长运行 Agent/Tool execution；只靠内存 Task handle 无法证明
  restart 后的 owner 和 terminal outcome。
- **复用什么：** `AsyncToolRuntime`、Runner、TaskScheduler、TaskDao transaction。
- **只新增什么：** ExecutionRecord、owner lease/heartbeat、owner epoch、generation/version
  CAS、atomic admission、duplicate identity rejection、monotonic cancel settlement、terminal
  no-revival、restart reconcile、idempotent terminal callback。
- **不新增什么：** `_DirectProjectAttemptJournal` 的 before/after tree、Git head、patch/apply、
  symlink、governance、cleanup 状态。
- **收敛原则：** cancellation fence 留在 `AsyncToolRuntime`；durable record/reducer 由一个
  Execution service 拥有；跨 Task/Attempt 原子动作通过窄 composition transaction。

### F5. Execution-bound Checkpoint Publication

- **为什么是基础能力：** 存下 bytes 不等于证明哪个 Task/Attempt/owner/source event 发布了
  checkpoint；resume 前必须验证 locator、digest、codec 和 execution fence。
- **复用什么：** Core Checkpointer/PersistenceCheckpointer、GraphStore 或其他 opaque payload
  store。
- **只新增什么：** publication reference、Task/Attempt/execution/source-event binding、
  digest/size/codec identifier metadata、publish/read verify transaction。AgentCore 只解释
  metadata，不解释 Jiuwen payload bytes 的编码规则。
- **不新增什么：** 第二个 payload store、Jiuwen D1 codec、Voice turn snapshot、Project
  recovery policy。
- **历史候选问题：** coordinator、DAO、bound Authority 三处重复校验，且 coordinator
  没有仓库内生产 consumer。

### F6. External-effect Intent / Evidence / Reconcile

- **为什么是基础能力：** 非幂等 Tool/provider 调用在 timeout/crash 后可能“已发生但未收到
  响应”；盲重试会产生重复副作用。Agent runtime 需要跨重启保留 intent、dispatch、
  receipt、observation、settlement 和 ambiguous outcome。
- **复用什么：** `ToolCard.idempotent`/retry metadata、Workflow Journal 的 prefix 思路、
  `AsyncToolRuntime` 和统一 database transaction。
- **只新增什么：** stable provider key/replay policy、one-use authorization、append-only
  facts、claim lease/version、一个 canonical reducer、unresolved-effect terminal fence 和
  reconcile port。
- **不新增什么：** provider credential/request body、真实 Tool 调用、Project/file probe、
  compensation/business policy。
- **为什么 Workflow Journal 不够：** 它是 completed-call cache/WAL，不能证明外部副作用
  的未发生、已发生或不确定状态。
- **历史候选问题：** DAO 和 Authority 各自重演 facts→state reducer，形成双重状态解释；
  public coordinator 也没有仓库内生产 adopter。

## 7. 历史 15,128 行到底是什么

固定比较 `4f2c29c..50c065dc`：

| 类别 | 文件数 | 新增 | 删除 | 判读 |
|---|---:|---:|---:|---|
| 生产 | 24 | 15,128 | 428 | 本节分析对象，不是目标规模 |
| 测试 | 22 | 14,003 | 190 | 大量 race/replay/corruption oracle；不能用数量代替架构正确性 |
| 文档/AGENTS | 27 | 2,697 | 28 | 历史设计说明 |
| 合计 | 73 | 31,828 | 646 | 不能作为一个整体变更单元 |

生产增量按实现结构分解：

| 结构 | 新增 | 主要问题 |
|---|---:|---|
| DAO/持久化模型 | 8,637 | `task_dao.py` 同时拥有 Task、Execution、Command、Event、Dispatch、Checkpoint |
| facade/authority | 4,561 | Manager 大量纯转发；Task/Effect Authority 再做完整投影和验证 |
| public schema/protocol/coordinator | 1,497 | DTO/SQL row/Canonical projection 多套并存，公共兼容面扩大 |
| runtime/composition | 433 | 少量合理 cancel/scheduler seam，也包含未完成 composition |
| **合计** | **15,128** | 只能说明历史实现形状 |

按最终存活新增行的来源能力对账：

| 历史能力来源 | 行数 | 零基线判断 |
|---|---:|---|
| scope | 201 | 必要，收敛进 Task store predicate/constraint |
| cancel | 116 | 必要且边界较小，留在 AsyncToolRuntime |
| execution owner | 2,160 | 语义必要，实现需拆 God DAO/转发 facade |
| command/result | 728 | 有价值，但必须成为唯一 mutation 入口；否则延期 |
| event/dispatch | 2,202 | event/outbox 必要；生产 drain 未组成，不能宣称闭环 |
| checkpoint | 999 | publication 必要；校验层重复、coordinator 无生产 adopter |
| effect journal | 2,819 | 安全语义必要；DAO/Authority 双 reducer 必须重写 |
| cursor | 1,822 | 语义需要；实现明显过厚，应按一行 cursor + CAS 起步 |
| bound Task access | 2,029 | least privilege 方向正确；实现未关闭 raw Manager 旁路 |
| bound effect access | 2,005 | 同上，且重复存储层完整验证 |
| diff 重排伪增量 | 47 | 不是新增责任 |
| **合计** | **15,128** | 不等于最小实现 |

### 7.1 重点文件为什么会膨胀

| 历史候选文件 | 基线/候选规模或增量 | 零基线结论 |
|---|---:|---|
| `tools/database/task_dao.py` | 约 1,219 → 5,335 行；`+4,299/-183` | Task graph/status、Execution、Command、Event、Dispatch、Checkpoint 和 effect settlement guard 共居；必须拆 owner，只保留跨表原子 composition seam |
| `tools/database/effect_dao.py` | 新增 1,818 行 | effect facts/lease/reconcile 有必要；与 Effect Authority 的双 reducer/验证无必要 |
| `tools/database/cursor_dao.py` | 新增 1,595 行 | 两个 public operation 前堆叠大量 helper，并重验 event prefix；应按单 cursor row + CAS 重写 |
| `agent_teams/task_authority.py` | 新增 1,432 行 | least-privilege handle 有价值；canonical DTO、snapshot retry、event/cursor/checkpoint 全量重验过厚 |
| `agent_teams/effect_authority.py` | 新增 1,782 行 | public capability intent 有价值；再次解释完整 effect facts 状态机无必要 |
| `tools/task_manager.py` | 约 1,850 → 3,108 行；`+1,347/-89` | 大量单次纯转发没有增加 owner，Authority 应依赖窄 service Port |
| `schema/task.py` | 约 248 → 682 行 | 可保留最小 public value；不能与 SQL row、Canonical projection、Jiuwen Product model 三套并存 |
| `schema/effect.py` | 新增 396 行 | 只保留 F6 provider-neutral intent/evidence/reconcile contract |
| `checkpoint.py` / `effect.py` | 新增 250 / 281 行 | Port/coordinator 形状可借鉴；没有 adopter 的预造 public surface 不进入首批实现 |

### 7.2 可直接证明的重复与未组成边界

- `task_dao.py` 从约 1.2K 行增长到约 5.3K 行，成为多子系统 God DAO。
- `TeamTaskManager` 新增段至少 33 个方法是单次纯转发，未增加 transaction owner。
- Task/Effect Authority 在同进程 typed service 之上再次验证 DAO 的 record、prefix 和
  state projection。
- effect、cursor、authority/DAO 重复实现 identity、positive/nonnegative validation、
  canonical JSON、digest 和 prefix verification。
- cursor 再次验证 F2 event prefix，而不是依赖唯一 EventStore。
- `TeamAgent.task_manager` 仍公开 raw Manager；新增 bounded handle 并未成为唯一入口。
- AgentTeams public export 从 47 增至 95，净增 48 个符号，产生很大的兼容成本。
- dispatch drain、checkpoint/effect coordinator、cursor handle 等多项只在定义/导出/
  测试出现，仓库内部没有生产 consumer。

这些证据说明“没有拆清楚就搭轮子”的风险确实存在。需要保留的是安全 invariant，
不是这些重复层级。

### 7.3 当前不能诚实给出精确最小 LOC

静态审计能证明重复 owner 和可缩小边界，不能证明“最少必须 N 行”，因为：

- 正式 threat model 若要求防数据库篡改、跨进程恶意 replay，多次校验中的一部分可能
  必须保留；若只要求 crash/concurrency，cursor/effect 可以更小；
- 新增公共导出是否已有仓库外 adopter 尚需在实施时查询；
- SQLite/PostgreSQL/MySQL 的锁和 CAS 差异需要运行证据；
- 跨 capability 共用的 transaction/codec/reducer 无法按 LOC 精确切割。

因此未来应先定合同、owner 和 threat model，再计量实现；禁止先拿“15K”当预算去填。

## 8. Jiuwen/LiveVoice 当前物理代码不能怎样计算

13 个原子项位于 8 个物理容器；按本仓库既有口径（包含空行和注释）在
`59998e2c` 上合计 31,325 physical LOC。只有
`durability_authority.py` 与 `durability_effects.py` 是 whole-file downshift 候选容器，
合计 1,149 physical LOC；其余文件都混有 Jiuwen/Voice/Product 责任。即使只计算
13 个 stable locator 的历史物理片段，也会遗漏共享 helper 并混入不能下沉的产品语义，
所以该片段数不作为未来合同或预算保留。

所以三种数字都不能互换：

- 31,325 = 混合容器上限，不是可迁移代码；
- stable locator 片段 = 冻结快照的辅助审计口径，不是未来 AgentCore 实现；
- 15,128 = 历史 AgentCore 候选生产增量，不是必要成本。

真正的净瘦身必须在冻结后分别报告：Jiuwen 删除、Jiuwen 保留 Adapter、AgentCore
复用、AgentCore 新增、迁移/测试/support 成本。跨仓移动不是 OpenJiuwen 净删除。

## 9. 防止继续搭轮子的实施 Gate

每个 F1–F6 能力在写代码前必须提交一张 zero-baseline decision record，至少回答：

1. 当前锁定 AgentCore 的最近 public owner 和 stable symbol 是什么；为何不能直接用；
2. 哪个现有 transaction/reducer/storage owner 被扩展；为何不新建平行 Store；
3. 缺失 invariant 的最小集合是什么；每个 invariant 对应哪个正向、负向、race、
   crash 或 corruption oracle；
4. Jiuwen Adapter 只映射哪些 opaque extension/Port；它明确不能写什么 truth；
5. 哪些历史 candidate symbol 被拒绝，以及拒绝原因；
6. public exports 是否最小，是否关闭 raw Manager/DAO 绕过路径；
7. 是否只有一个 canonical codec/digest/reducer/event verifier；
8. 仓库内与仓库外 adopter 是谁；没有 adopter 的 public surface 应延期而不是预造；
9. 如何保证旧 Jiuwen Store 与新 owner 不长期双写；迁移、canary、rollback 怎样验证；
10. 同口径报告 production LOC、tests、docs、Jiuwen retired LOC 和多仓库净变化。

以下任一情况出现即停止该能力实施并重新定界：

- 新建第二套 Task/event/effect truth，而不是扩展现有 owner；
- DAO、Manager、Authority 三层都解释同一状态机；
- 为 Voice/DOM/Git/provider policy 扩大 AgentCore schema；
- 仅因历史候选已有代码就保留没有 adopter 的 public API；
- 用测试数量、candidate 局部 PASS 或 LOC 规模替代独立源码审查；
- replacement 尚未 accepted/installed 就删除 Jiuwen 当前唯一 authority。

## 10. 冻结后直接执行的顺序

1. 对 `59998e2c..feature-complete frozen source` 做 stable-symbol delta，只复审受影响的
   13 项 locator 和新增责任。
2. 对届时安装的 AgentCore public exports 重跑 `DIRECT_REUSE / ADAPT_REUSE /
   FOUNDATION_ADD / JIUWEN_KEEP` 判断。
3. 先组合已存在的 Agent/Tool/Runner/Harness、TaskDao、Scheduler、AsyncToolRuntime、
   Checkpointer 等 primitive；删除重复 facade 的前提是调用链证据，而不是目标 LOC。
4. 对仍缺失的 F1–F6 逐项建立最小合同；优先关闭 single writer、raw Manager bypass、
   duplicate reducer 和未组成 consumer。
5. 只有新 public capability accepted、installed、正负/race/crash/corruption oracle 通过
   后，Jiuwen 才切换薄 Adapter；随后 quiesced migration、canary、rollback、旧 owner
   retirement。
6. 最终报告 LiveVoice、Jiuwen Host、AgentCore、tests/support 四个口径，解释每个模块
   为什么存在，而不是用一个总行数掩盖跨仓移动。

## 11. 最终回答

需要进入 AgentCore 的不是“LiveVoice 的 15K 行”，而是仍不存在的六组最小 generic
invariant。它们有充分的基础归属理由：scope、durable Task、事务事件、跨重启执行、
checkpoint publication 和外部副作用歧义都适用于通用 Agent/Tool runtime，放在
LiveVoice 会让每个产品重复实现。

但历史 15K 实现本身没有获得采用结论。当前证据反而要求它大幅收敛：复用现有
TaskDao/Manager、Scheduler、AsyncToolRuntime、Checkpointer/Journal primitive，删除
重复 facade/reducer/verifier，关闭 raw bypass，只留下一个 transaction owner 和六个
窄 public seam。未来实现多少行，必须由这些合同和 threat model决定，不能倒过来由
历史代码量决定。
