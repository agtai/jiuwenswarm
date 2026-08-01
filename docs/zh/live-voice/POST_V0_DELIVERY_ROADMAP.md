# Live Voice：V0 之后的两周全能力 Demo 与正式交付路线

> 更新日期：2026-08-01
> V0 不可变基线：`2c700934aa0024a7ab229644bf15934e9e8170e7`（Candidate，未放行）
> 状态：Task Foundation 已完成 review 与统一验证，并由后端 `3da101cf`、前端 `42e76d30` 落地；代码与文档已纳入本批 Git 交付

## 1. 两个目标同时成立

1. **两周最大能力 Demo**：P1 Speech I/O、P2 Realtime Conversation、P3 Agent Task Control，以及 Context、Progress、Failure/Degradation、Observability 等能力类别都要有可演示的纵向路径。
2. **最终正式交付版**：Demo 只走一条可累计替换的真实工程路径；后续用正式模块逐步替换 shortcut，最终经过 RC hardening 才能生产放行。

“展示所有功能”在两周范围内指 **覆盖所有能力类别和关键用户旅程**，不指完整实现目标方案的每个子能力、可靠性等级和兼容矩阵。未完成的难点必须满足三条：

- 替代流程的输入、Agent/Tool 调用、任务 ID、状态和结果都是真实的；
- UI 和文档明确标出 `Demo substitute`、`unsupported` 或 `unknown`，不模拟成功；
- shortcut 位于可替换接口后面，有明确的正式模块接替者。

## 2. V0 不可变基线与正常交付边界

- V0 Candidate 恢复点永久固定为 `2c700934aa0024a7ab229644bf15934e9e8170e7`。它尚未通过 [V0_ACCEPTANCE.md](V0_ACCEPTANCE.md)，所以只能称 Candidate，不能称 Released/frozen。
- D-022 的临时隔离已完成：stash `7f4cfd2eedfb3a177b94f69417143fba441f3671` 已 apply，原 stash 只作为额外备份保留。当前分支已有这些改动时，不得再次 apply/pop/drop。
- D-030 恢复常规 Git 流程：Post-V0 按逻辑切片 review、统一验证、commit、push；Foundation 代码已由后端 `3da101cf`、前端 `42e76d30` 落地，相关文档已纳入本批 Git 交付。跨机器只依赖共享分支和本目录文档，不依赖单机 stash。
- 用户稍后验收 V0 时，从精确 SHA 创建独立 checkout/worktree，清除 `VITE_FEATURE_LIVE_VOICE_STREAMING_SPEECH` 和 `VITE_FEATURE_LIVE_VOICE_TASK_DEMO` 后执行完整 Gate。不要为了回到旧基线反复 stash、reset 或改写当前开发分支。
- Gate 失败不得写 Released；Gate 通过后只把验收证据合回累计分支，Post-V0 foundation 不得混入 V0 能力证据。

## 3. 排序方法

优先级按四个因素共同决定：

1. 能否显著提升两周展示效果；
2. 是否直接成为正式版基础，而不是一次性假 UX；
3. 当前能否无需麦克风、耳机和人工判断，用纯逻辑、fake adapter 或故障注入自动验证；
4. 是否先消除错误取消、假进度、任务副作用或旧输出复活等安全风险。

## 4. 剩余工作优先级

| 优先级 | 工作项 | 两周 Demo 的真实表现或替代 | 正式版接替方向 | 当前可自动推进 |
|---|---|---|---|---|
| P0-1 | 最小 Contract Gate 与可重放测试脊柱 | 冻结 identity、四种 cancel scope、capability、committed intent、WorkProgress 和 terminal outcome 约束 | P1/P2/P3 共用版本化契约与 conformance suite | 是 |
| P0-2 | response/generation lifecycle 骨架 | 继续使用文字 WebSocket 和显式“打断并说话”，但用 ID、scope、reducer 和 fence 处理迟到/重复事件 | P2 Conversation Runtime 与 presented history | 是 |
| P0-3 | 保守稳定句预读 | 从已进入 chatStore 的单一稳定 assistant stream 提前朗读完整句；rewrite 时降级文字，不冒充音频流式传输 | streaming TTS、Realtime Media、播放 ACK | 是；听感后验 |
| P0-4 | 真实 P3α 任务纵向切片 | final committed 固定口令 → 真 `task_id` → status/events/cancel；只显示来源真实的状态 | Task Control Core、Executor Port、D0 durability | 大部分是 |
| P0-5 | Voice–Task Bridge 与任务卡 | 仅解析显式 create/status/cancel；破坏性操作确认；A→B 首版显示为 cancel A + create successor B | 完整 intent resolution、update/provide-input、多任务消歧 | 是；语音后验 |
| P0-6 | WorkProgress 时间线与能力披露 | 显示真实 accepted/running/blocked/decision_required/terminal；缺失信息写 `unknown`，不猜百分比 | Agent Bridge、Task events、observability | 是 |
| P1-1 | Speech Recognition/Synthesis Port + Browser Adapter | 当前 Browser Speech 是真实 fallback，固定 `zh-CN`、Chrome 和耳机 | Provider-neutral batch/streaming STT/TTS | 大部分是；设备后验 |
| P1-2 | InteractionEngine Port + Cascade 策略 | 固定 EOT、自动回听、显式点击插话；working notice 只来自真实状态 | VAD/EOT、自然 barge-in、Native Engine adapter | 逻辑是；体验后验 |
| P1-3 | Realtime Media contract + loopback/fault injection | 现场仍诚实使用 Browser Speech；开发实验室验证 ACK、背压、乱序和有界队列 | 正式双向音频 transport | 是；真媒体后验 |
| P1-4 | 最小 ContextRef | 真正传递当前仓库、分支、版本和权限范围；不声称已连接 IDE/浏览器 | 跨 IDE/文件/浏览器/通信 Context adapters | 是 |
| P2-1 | Windows AIO、设备选择、AEC/NS/AGC | 两周以固定 Chrome + 耳机 + 默认设备替代 | Windows 正式音频设备层 | 否，必须真机 |
| P2-2 | 真 streaming STT/TTS、二进制媒体、自然免手插话 | 两周用 Browser Speech + 稳定句预读 + 显式打断替代 | P2 Realtime Alpha 的核心体验 | 部分 |
| P2-3 | 完整 P3 | 未实现的 update/provide-input/pause/resume/reprioritize 明示 unsupported；A→B 用 successor 流程 | Full Task Control + D1/D2 + reconciliation | 核心逻辑可；执行器需集成 |
| P2-4 | RC/Production hardening | 两周只提供受控环境、预检、文字降级和真实录屏 | 安全、权限、隐私、兼容矩阵、SLO、运维与发布 Gate | 混合 |

## 5. 十个工作日的最大能力路径

| 日程 | 主产出 | 自动验收退出条件 |
|---|---|---|
| D1 | 最小合同、reducers、conformance、trace schema | 重复、乱序、错误 scope、terminal 缺 outcome、partial 副作用均被拒绝 |
| D2 | Web 请求路由真实性修复；任务 Executor 风险隔离 | request 只有一个响应所有者；未知/迟到响应可重放测试通过 |
| D3-D4 | P3α create/get/list/status/cancel/events、真实 store/adapter | ID、状态、cancel isolation、D0 断开边界自动测试通过 |
| D5 | committed Voice–Task Bridge、确认和 last-visible-task 选择 | partial=0 dispatch；歧义/破坏性操作不误发 |
| D6 | 任务卡、WorkProgress、cancel + successor | 只显示带 provenance 的真实状态；A/B 两个 ID 和关系可追踪 |
| D7 | response/generation ID、cancel scope 与迟到事件 fence | 乱序、重复、cancel race、旧 output 均不复活 |
| D8 | 稳定句预读接线、保守 final 对账和 feature flag | 无重复/丢字；rewrite 明确降级；V0 flag-off 回归不变 |
| D9 | ContextRef、capability/unsupported 展示、完整演示脚本 | P1/P2/P3/Context/Failure 各有真实路径或明确替代 |
| D10 | 全量回归、故障注入、构建、文档与录屏准备 | 自动 Gate 全绿；剩余项明确分为“需真人验收”或“正式版后续” |

这是一份滚动优先级，不是承诺每项必然在对应日期完成。出现风险时，先保住 Contract、真实状态、安全边界和文字路径，再降级媒体自然度或 UI 完整度。

## 6. 两周 Demo 如何覆盖完整方案

| 能力类别 | 两周可展示路径 | 尚未正式实现的部分 | 为什么仍可验证方案 |
|---|---|---|---|
| P1 听与说 | 真麦克风、真 STT、真 Agent 文本、Browser TTS；Provider capability 可见 | 统一设备层、多 Provider、一致性指标 | 验证语音入口/出口是否值得产品化，以及错误/降级 UX |
| P2 持续会话 | 自动回听、thinking/speaking 状态、稳定句预读 | 真媒体双工、streaming audio、AEC | 验证“一边工作一边尽早反馈”的节奏；不宣称模型/媒体全双工 |
| P2 插话与修订 | 本地立即停声；processing 时走真实 supplement；否则新 Turn | 自然免手 barge-in、服务端精确 cancel ACK、presented history | 验证用户能否纠正 Agent，以及取消 scope/旧输出问题 |
| P3 后台任务 | committed 固定口令创建、查询、取消真实 D0 任务 | 通用 Task Core、D1/D2、完整 update/provide-input | 验证语音会话与独立 task_id/lifecycle 组合是否有价值 |
| A→B 更新 | 明确显示 cancel A + create successor B | 原地更新 A、checkpoint/reconciliation | 验证用户控制意图和继任关系，不伪装已经更新同一任务 |
| Context | 当前仓库/分支/SHA 作为真实 ContextRef | IDE、浏览器、通信等广泛连接器 | 验证稳定引用、权限和版本是否能随命令传递 |
| Progress/通知 | 真实事件投影；缺失细节显示 unknown | 丰富进度、跨设备 unread/replay | 验证状态回流、语音播报仲裁和“前台不被后台冻结” |
| Failure/降级 | fault injection、能力披露、文字路径和 final-only fallback | 跨平台/跨 Provider/SLO | 验证失败不会污染原文字聊天，且不会伪造成功 |

## 7. 第一批切片实现 checkpoint

1. **Contract/Conformance 最小骨架已实现**：覆盖 identity、四种 cancel scope、capability、committed intent、WorkProgress provenance 和 terminal outcome 等约束；它仍只是正式版本化协议的地基。
2. **Web schedule 单一响应所有权和单进程竞态修复已实现**：Gateway 转发后不再由本地 handler 抢先返回 `unknown method`；run 只有在执行被调度器接管或真实进入 terminal 时才返回相应事实，cancel/delete 与同 task 操作按 store 真值串行收敛。
3. **稳定句预读已实现并默认关闭**：`VITE_FEATURE_LIVE_VOICE_STREAMING_SPEECH=true` 才启用。planner 覆盖 lookahead、幂等、rewrite、final suffix reconciliation、未闭合 Markdown、stale epoch、消息 collapse 和 `processing=false` 先于权威 final；缺 final 时只在 processing 停止且队列 drain 后启动 10 秒 grace period，到期废弃 epoch 并显示 Retry，不把 provisional 当 final；feature-off 不写 final marker、不启动 timer、不改变 V0。
4. **受限 Task Bridge/client/UI 已实现并默认关闭**：`VITE_FEATURE_LIVE_VOICE_TASK_DEMO=true` 才启用。面板在任何任务口令前常驻显示 AutoHarness、固定 `extended_evolve_pipeline`、代码副作用、取消边界和内存丢失警告。该 pipeline 本身是有副作用的，不存在可称为“安全只读”的当前 pipeline。
5. **任务派发边界已自动化**：只消费 committed final；启动、取消和替换需要明确确认；创建/替换目标只允许 `：`、`:`、`，`、`,`、空格或口述“冒号”等受控分隔符；capture 期间 session 改变、空 session 或 `new` session 均拒绝派发。
6. **任务事实、稳定 command identity 与未知结果保护已实现**：只显示真实 `task_id`、后端原始状态和来源；A→B 先取消 A 再创建不同 ID 的 successor B。每次 committed mutation 固定一个 command ID；run 结果不明时先做 owner/namespace/exact-key list，对不上就 fail closed，必要重放只使用同 key，不会生成第二个 key 盲目创建。
7. **每任务执行上下文和目标 provenance 已实现**：Scheduler 不再在执行时读取 singleton 可变 `_agent`，而是为每任务固定独立的进程内 Agent/context；并发 Session 隔离，周期任务保留 context，终态/取消/删除/service stop 释放。持久状态和 UI 返回 `project_dir`、`project_id`、来源 Session/Channel；前端没有可信绝对当前项目路径时 fail closed，capture 中 session/target/bridge identity 改变时零请求失效。重启后缺少旧 context 的任务诚实失败，不借新 Agent。
8. **后端 per-path single-process 创建幂等已实现**：服务端派生 owner scope，`origin_namespace` + `idempotency_key` 配合同一进程、同一 JSON store 路径共享锁、`create_commands` ledger 和 intent fingerprint 做 get-or-create。同意图重放同 ID、只触发一次；冲突返回 `IDEMPOTENCY_CONFLICT`；删除保留 tombstone，reload 后可恢复。该保证不跨进程，也不是 exactly-once。
9. **服务端读取与控制 scope 已实现**：`schedule.list/status/cancel/logs/delete` 均从可信 request 派生 owner + project execution target；外部缺失、无效或不匹配 scope fail closed，并在日志读取、scheduler cancel、store mutation、context release 前拒绝越权。
10. **严格 reconciliation 和真实任务卡已实现**：exact-key list 必须唯一，并逐项核对 task ID、query、pipeline、namespace、key 与 target。任务在网络往返期间从 pending 漂移到 running/terminal 时保留后端真值；task card 显示 command ID、恢复来源、冲突和 provenance，不合成假状态。
11. **foundation 已完成审阅和最终验证**：后端 `3da101cf`、前端 `42e76d30` 已落地；Live Voice 前端精确测试 **155/155**，chatStore marker 与相关回归 **24/24**，全前端 TypeScript 通过，Vite build **4494 modules transformed**；Python contract + TaskStore/service + AgentServer request + Web handler 统一 **226/226 passed**。这些自动化结果不能替代稳定句听感和真实有副作用任务 E2E；代码与文档已纳入本批 Git 交付，跨机器从共享分支恢复；下一实现切片为 D-031。

### 7.1 第一批切片仍未解决的正式版风险

- 稳定句预读仍用本地 response epoch 和 chatStore final marker，没有服务端 response/generation provenance。并发 cron/proactive/迟到 final 可能误归属；10 秒 recovery 只能避免永久 thinking，不能恢复或认证 provisional 文本。
- planner/FIFO 只能证明 planned/enqueued，不能证明声音已经播放或用户已经听到；缺少 playback ACK/cursor 和 presented history。
- 前端 stable command ID 只覆盖同一次 Bridge mutation/retry/reconcile；`lastVisibleTask`、未决 mutation 与 task card projection 仍是当前页面/Session 内存。刷新后尚无持久 command journal、连续 monitor、多任务消歧或通用 Executor。
- schedule 的锁、真值和幂等 ledger 都是单进程边界。JSON task store 没有跨进程 CAS/事务、唯一执行所有权、生产级 crash recovery 或外部副作用 reconciliation；多个进程共享 store 和 D1/D2 durability 仍需正式 Task Control Core 解决。
- Live Voice 的打断、退出和 session fence 只影响语音反馈或新的派发，不能取消已经发出的 `schedule.run`；`schedule.cancel` 也不能撤销已发生的代码修改。
- task-scoped Agent/context 和 project/origin provenance 已消除执行时借用最后一个 Agent 与目标猜测，但 context 仍只在进程内，持久 target 尚不含完整 model/provider/config/permission 快照；重启恢复仍需正式执行上下文存储。
- 前端已经接入同-key retry 与 scoped exact-key reconciliation，服务端也已经对 list/status/cancel/logs/delete 强制 owner + project scope；剩余 `mutation-unknown` 只在记录不唯一、identity/target 冲突或仍无法证明结果时 fail closed。没有跨刷新 command journal、持续轮询/事件回流、跨进程唯一约束、exactly-once 或 D1/D2，因此仍不能宣称完整幂等 Task Control。

### 7.2 下一实现切片：前台持续在线 + 后台非阻塞 + 结果异步回流

foundation 在本轮到此为止。下一切片按 D-031 使用 `schedule.status` 为主、scoped exact-key `schedule.list` 为恢复入口的 poll-backed monitor：任务一经真实派发，Live Voice 前台立即恢复监听；独立 task projection 持续更新真实 task card；terminal 结果始终显示，并只在麦克风关闭、Agent/TTS 空闲且未播报过时朗读一次简短通知。

该切片本轮**只记录，不继续实现**。它不修改 chatStore 的消息或 processing，不抢占麦克风/Agent TTS，也不扩成完整 TaskEvent push/replay、通用多任务 NLU、跨进程 exactly-once、D1/D2 或完整 P3。

## 8. 版本命名纠正

版本号与架构 Phase 不应混为一谈。完整方案定义：P1 是 Speech I/O，Conversation Runtime 属于 P2。建议累计版本为：

| 版本 | 能力里程碑 |
|---|---|
| V0 | Vertical Slice Candidate / Released（仅 Gate 通过后） |
| V1 Foundation Alpha | P1 Speech Port + P2 最小 response/generation lifecycle 基础 |
| V2 Realtime Alpha | P2 Conversation Runtime、Realtime Media、Interaction/Agent Bridge 和 streaming Speech extension |
| V3α Task Alpha | P3α create/get/list/status/cancel/events + D0 + Voice–Task Bridge |
| V3 Full Capability Beta | P1 + P2 + 完整 P3；仍未生产放行 |
| RC / Production | 可靠性、安全、兼容、可观测、运维和发布 Gate |

共享契约稳定后，V1/V2/V3α 的部分实现可以并行；版本放行仍按依赖累计，不能因为 Demo 有替代入口就跳过正式 Gate。
