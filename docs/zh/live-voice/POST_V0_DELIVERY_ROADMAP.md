# Live Voice：V0 之后的两周全能力 Demo 与正式交付路线

> 更新日期：2026-08-02
> V0 不可变基线：`2c700934aa0024a7ab229644bf15934e9e8170e7`（Candidate，未放行）
> 状态：Task Foundation 已由后端 `3da101cf`、前端 `42e76d30` 落地；D-031 尚未编码，必须先通过 D-032 开发前 checkpoint
> 模块闭环：从 D-031 起强制执行 D-032 的开发前/开发后双回顾与完整场景测试 Gate

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

## 3.1 每个模块的强制测试闭环（D-032）

本节是所有 Live Voice 模块和逻辑切片的唯一详细测试闭环规范。“模块”按一个可独立说明契约、状态、ownership 和副作用边界的逻辑单元划分，不按文件数量划分。规则从 D-031 起强制执行；Foundation 的既有 `226/155/24/4494` 仍是有效历史回归结果，但不能倒写成已经完成本规则要求的双回顾。

“覆盖所有场景”指：基于完整方案、当前版本阶段、当前模块定义、已接受决策、上下游契约和实际 diff，可以识别出的全部必需行为与风险均进入矩阵。它不等于无限组合穷举，也不等于行覆盖率 100%。无法自动化、当前明确不支持或确实不适用的场景仍必须列出，分别绑定人工/E2E 证据、后续替代计划或有依据的 `N/A`；不得静默遗漏后宣称闭环。

### 3.1.1 开发前回顾：先理解，再设计 tests

任何语义实现开始前，必须完成并在 [STATUS.md](STATUS.md) 留下前置记录：

1. 重读本目录的方案入口、当前 `HANDOFF/STATUS`、当前阶段路线、相关 Accepted decisions；涉及长期架构、P1/P2/P3、协议、ownership、取消、持久化或生产边界时，完整重读 `FULL_SOLUTION_2026-07-30.md`。
2. 阅读当前模块代码、所有相关现有 tests 和上下游接线，不能只根据计划标题或当前实现猜模块定义。
3. 写清模块定义：阶段/版本、目标、非目标、输入与输出、状态与允许/禁止转换、事实源、identity/ownership/scope、外部副作用、时序/重试/取消/恢复、feature flag/fallback、上下游依赖、Demo shortcut 与正式接替者。
4. 建立 test inventory：列出已有和计划新增的具体 suite/test case、测试层级、每项为什么存在、它证明哪条行为或风险、覆盖哪些 scenario ID，以及当前缺口。不能只记录测试总数。
5. 先完成场景矩阵和 oracle，再写语义代码。Bug 修复应先有能在旧行为上失败的回归测试；纯重构应先建立 characterization。无法做到时必须记录原因和替代证据。
6. 前置记录必须在任何语义实现开始前作为独立文档 checkpoint commit/push，使机器故障、新会话或跨机器恢复也不会丢失模块理解和测试设计；不能只留在对话、本机草稿或尚未提交的 worktree。

### 3.1.2 强制场景矩阵

| 维度 | 必须回答的问题 |
|---|---|
| `P` 正向正确 | 每个合法输入、状态和用户旅程是否得到正确输出、状态、provenance 与预期副作用；需要 exactly-once/at-most-once 时次数是否准确 |
| `N` 反向拒绝 | 缺失、非法、歧义、未授权、冲突、过期或当前状态不允许的动作是否明确失败、拒绝或 no-op，并且所有禁止副作用为 0 |
| `B` 边界与数据形态 | 空值、临界值、超长、Unicode/标点、畸形类型、缺字段、旧格式、损坏或部分数据如何处理 |
| `S` 状态与生命周期 | 所有允许和禁止的状态转换、terminal 不可逆、退出/卸载、错误恢复、事实源优先级是否正确 |
| `T` 时序与事件顺序 | 重复、乱序、迟到、超时、ACK/final/processing 顺序互换、旧 callback/promise 是否被 fence |
| `C` 并发、重试与幂等 | 并发 create/retry/cancel/delete/claim、同 key 重放、竞态收敛、调用次数和身份是否正确 |
| `R` 恢复与持久化 | reload/reconnect/restart、响应丢失、部分失败、未知结果 reconciliation、旧 context 缺失时是否诚实恢复或失败 |
| `I` 隔离与权限 | session/channel/project/task/target/response/generation/owner 跨域时是否 fail closed，且不读取或修改他域数据；声明生产授权或机密隔离的模块还必须隐藏对象存在性。D-033 Demo scope 当前未提供存在性隐藏，必须把它明确记为 Production gap，并证明不返回跨 scope 内容、不执行跨 scope 控制或修改 |
| `F` flag、能力与降级 | feature flag on/off、capability 缺失、fallback、unsupported/unknown 和文字降级是否真实，关闭时是否零新增副作用 |
| `K` 协议与持久格式兼容 | client/server 版本组合、schema/envelope、correlation 与单一响应所有权、未知/新增字段、序列化 round-trip、旧持久数据迁移/默认值、升级/降级策略是否明确且可验证 |
| `X` 跨模块与真实路径 | Adapter、WebSocket、hook/UI、Agent/Tool、存储、设备或 Provider 每个新增接线不变量是否都有对应 integration 证据，包括适用的正例、反例、stale 和 flag-off；一个 happy-path E2E 不能替代这些证据，且必要人工证据不能被单测替代 |

`P` 与 `N` 对每个新增或改变的不变量都是必填项；其他维度只可在确实不适用时填写有理由的 `N/A`。每个场景必须写清前置状态、输入/事件、期望输出和状态、允许的副作用、明确禁止的结果，以及对应自动化 test 或人工证据。

“错误场景必须错误”描述的是**业务行为**：系统应被拒绝、进入明确 error/conflict/unknown/unsupported，或安全 no-op；相应 pytest/npm test 本身仍应 PASS。反向测试不能只断言抛异常，还要按模块断言敏感操作没有发生，例如没有 Agent/Task/TTS/timer 调用，没有第二个任务，没有 store/history/ledger 修改，没有 progress/log 越权读取，也没有旧声音/旧消息/旧任务卡复活。对于声明生产授权或机密隔离的模块，还必须证明没有泄露其他 scope 下对象是否存在；D-033 Demo scope 不具备该安全属性时必须显式记为 gap，不能伪称已覆盖。
后端/协议/持久化场景至少用 spy/counter 和 store before/after snapshot 证明拒绝路径零调用、零写入；用同路径多实例、reload、tombstone、损坏/截断数据和写入失败验证恢复边界；协议 test 断言精确 error code、response envelope、correlation/identity 和只响应一次，不能只断言“有 error”。

并发和时序测试优先使用 fake clock、deferred promise、barrier/event 或 fault injection，避免依靠 `sleep` 和偶然调度得到假绿。

### 3.1.3 Test inventory 最小字段

| Test / suite | 层级 | Why：对应行为或风险 | Scenario IDs | Oracle 与禁止结果 | 当前状态 |
|---|---|---|---|---|---|
| 具体测试标题或参数化组 | pure/unit、contract/conformance、adapter/integration、E2E/manual | 为什么这样设计；防哪个 bug/风险 | `P-...`、`N-...` 等 | 成功/拒绝、状态、副作用次数 | existing/new/changed/gap |

同一场景不要求在所有层级重复，但必须在能证明该风险的最低层和必要的真实接线层留下证据。纯函数全绿不能替代 React hook/UI/WebSocket、协议、存储或真实副作用路径；真机录屏也不能替代可重复的状态机、错误和竞态自动化。

### 3.1.4 开发后回顾：按实际 diff 重新证明

实现完成后、宣称模块闭环前，必须再次阅读相关方案、阶段定义、模块代码和全部相关 tests，并完成：

1. 逐项检查实际 diff 新增或改变的分支、状态、调用顺序和副作用，把开发中发现的新风险补回模块定义、inventory 和矩阵。
2. 逐项回答“有哪些 tests、为什么这样设计、覆盖哪些场景、什么错误实现会让它失败”；删除、放宽断言或更新 snapshot 必须有模块定义变化作为理由，不能为了变绿。
3. 确认每个场景都有 `scenario → test/evidence` 映射；必要场景没有证据时保留 gap，不得用总测试数或行覆盖率代替。
4. 先跑目标模块，再跑相邻回归、跨层 contract/integration、类型检查、lint 和 build；对最终 candidate 执行 `git diff --check <baseline_sha>..<candidate_sha>`。涉及真实设备、Agent/Tool、外部 Provider 或副作用时执行相应 E2E/人工 Gate。
5. tested evidence 的固定顺序是：前置回顾文档 checkpoint → 提交全部 code/tests/fixtures/config/schema/migration/lockfile 等行为输入形成 candidate commit → 确认这些路径相对 HEAD 无未提交差异并记录 `git rev-parse HEAD`、`git status --short` → 在该 commit 上统一复跑 → 用后续 evidence-only 文档 commit 在 `STATUS.md` 记录精确命令、环境、exit code、结果和 `tested_sha`。任何 amend、新的代码/test commit 或行为输入变化都会使受影响闭环失效并必须重审/重测。
6. 反向场景必须验证 fail-closed 与禁止副作用为 0；重试、重复、迟到和并发场景必须验证 identity、次数与最终状态，不以“没有崩溃”冒充正确。
7. 记录 flaky、未自动化场景、人工观察、当前阶段明确不支持项和正式版替换计划。需要反复重跑才能偶然通过的测试视为未闭环。
8. `HANDOFF.md` 只摘要当前模块状态、tested SHA 和 `STATUS.md` 证据位置；规则本身不在多个文件重复定义。

### 3.1.5 闭环状态

- `CLOSED`：开发前与开发后两次回顾均有记录；当前模块定义中的全部必需行为/风险都有场景映射；正例成功，反例 fail-closed 且零禁止副作用；必要的跨模块和真实路径证据已完成；最终测试在包含全部行为输入且相关路径干净的 immutable candidate SHA 上执行，本切片的目标模块、相邻回归与 required commands 全部 exit 0，且没有未解释 flaky 或必需 gap。额外的更宽仓检查若存在既有 baseline failure，必须在修改前以相同命令记录，并以前后相同命令对比证明本 diff 没有新增，不能靠重跑偶然绿或静默忽略。
- `PARTIAL`：实现可以继续集成或演示，但场景、接线、E2E/人工证据或恢复/兼容矩阵仍有缺口。不得对外写“模块已闭环/已完成”，也不得仅凭它通过版本 Gate。
- `BLOCKED`：必需行为或证据因已确认的外部条件无法继续；记录阻塞条件、已完成证据和恢复入口，不能用 unsupported 或 mock success 隐藏。

已有模块不会因为新规则而被写成“从未实现”，但既有测试数量只能作为历史回归证据。已有模块下一次被修改、被依赖来关闭新切片，或进入 V1/V2/V3/RC Gate 前，必须补齐其受影响范围的闭环记录。

### 3.1.6 `STATUS.md` 记录模板

```markdown
### Module test closure: <module / slice>
- stage / decision / requirement sources:
- code scope and upstream/downstream:
- baseline SHA / candidate tested SHA / environment / clean-status evidence:
- pre-review: DONE | MISSING
- post-review: DONE | MISSING
- closure: CLOSED | PARTIAL | BLOCKED

#### Module definition and non-goals
...

#### Test inventory
| Test / suite | Level | Why | Scenario IDs | Oracle / forbidden outcome | Actual result / evidence | Status |

#### Scenario matrix
| ID | P/N/B/S/T/C/R/I/F/K/X | Preconditions and action | Expected/forbidden outcome | Test or evidence | Result/N/A reason |

#### Commands and exact results
...

#### Remaining gaps, manual evidence and replacement plan
...
```

### 3.1.7 D-031 的首次强制应用

D-031 编码前必须先在 `STATUS.md` 建立上述前置记录，至少覆盖：派发后前台立即恢复；同一任务最多一个 in-flight poll；fake-time 轮询与 1/2/5/10 秒退避；断线暂停和重连 reconcile；task/session/target/monitor generation 改变后的迟到 promise；terminal/deleted/flag-off/unmount 停止；任务卡保留真实终态；只在安全空档最多播报一次；始终不写 chatStore message、不修改 chat processing、不抢占麦克风或 Agent TTS；scope/业务/transport 错误和零/多条 reconciliation 必须 fail closed；当前/旧 schedule response、缺失/新增字段、非法 envelope 与 adapter 兼容策略必须有测试或有理由的 `N/A`。还必须包含 hook/UI/WebSocket 接线层的正例、反例、stale 和 flag-off 证据，不能只靠 monitor 纯函数单测；A→B successor 已按 D-034 锁定为监控 B、保留 A 的 cancelled/terminal 卡与 successor 关系；矩阵必须验证该语义，且不得无意扩成任意多任务 monitor。

## 4. 总体优先级与当前状态

状态含义：`LANDED` 表示当前定义已落地，`PARTIAL` 表示只有 foundation/substitute 或仍缺 Gate，`NOT STARTED` 表示尚未进入实现；这些状态不能替代 D-032 的 `CLOSED` 判定。`STATUS.md` 是当前下一任务的事实源。

| 优先级 | 当前状态 | 工作项 | 两周 Demo 的真实表现或替代 | 正式版接替方向 | 当前可自动推进 |
|---|---|---|---|---|---|
| P0-1 | PARTIAL | 最小 Contract Gate 与可重放测试脊柱 | 冻结 identity、四种 cancel scope、capability、committed intent、WorkProgress 和 terminal outcome 约束 | P1/P2/P3 共用版本化契约与 conformance suite | 是 |
| P0-2 | PARTIAL | response/generation lifecycle 骨架 | 继续使用文字 WebSocket 和显式“打断并说话”，但用 ID、scope、reducer 和 fence 处理迟到/重复事件 | P2 Conversation Runtime 与 presented history | 是 |
| P0-3 | PARTIAL | 保守稳定句预读 | 从已进入 chatStore 的单一稳定 assistant stream 提前朗读完整句；rewrite 时降级文字，不冒充音频流式传输 | streaming TTS、Realtime Media、播放 ACK | 是；听感后验 |
| P0-4 | PARTIAL | 真实 P3α 任务纵向切片 | final committed 固定口令 → 真 `task_id` → status/events/cancel；只显示来源真实的状态 | Task Control Core、Executor Port、D0 durability | 大部分是 |
| P0-5 | PARTIAL | Voice–Task Bridge 与任务卡 | 仅解析显式 create/status/cancel；破坏性操作确认；A→B 首版显示为 cancel A + create successor B | 完整 intent resolution、update/provide-input、多任务消歧 | 是；语音后验 |
| P0-6 | PARTIAL | WorkProgress 时间线与能力披露 | 显示真实 accepted/running/blocked/decision_required/terminal；缺失信息写 `unknown`，不猜百分比 | Agent Bridge、Task events、observability | 是 |
| P1-1 | PARTIAL | Speech Recognition/Synthesis Port + Browser Adapter | 当前 Browser Speech 是真实 fallback，固定 `zh-CN`、Chrome 和耳机 | Provider-neutral batch/streaming STT/TTS | 大部分是；设备后验 |
| P1-2 | PARTIAL | InteractionEngine Port + Cascade 策略 | 固定 EOT、自动回听、显式点击插话；working notice 只来自真实状态 | VAD/EOT、自然 barge-in、Native Engine adapter | 逻辑是；体验后验 |
| P1-3 | NOT STARTED | Realtime Media contract + loopback/fault injection | 现场仍诚实使用 Browser Speech；开发实验室验证 ACK、背压、乱序和有界队列 | 正式双向音频 transport | 是；真媒体后验 |
| P1-4 | PARTIAL | 最小 ContextRef | 真正传递当前仓库、分支、版本和权限范围；不声称已连接 IDE/浏览器 | 跨 IDE/文件/浏览器/通信 Context adapters | 是 |
| P2-1 | NOT STARTED | Windows AIO、设备选择、AEC/NS/AGC | 两周以固定 Chrome + 耳机 + 默认设备替代 | Windows 正式音频设备层 | 否，必须真机 |
| P2-2 | PARTIAL | 真 streaming STT/TTS、二进制媒体、自然免手插话 | 两周用 Browser Speech + 稳定句预读 + 显式打断替代 | P2 Realtime Alpha 的核心体验 | 部分 |
| P2-3 | NOT STARTED | 完整 P3 | 未实现的 update/provide-input/pause/resume/reprioritize 明示 unsupported；A→B 用 successor 流程 | Full Task Control + D1/D2 + reconciliation | 核心逻辑可；执行器需集成 |
| P2-4 | NOT STARTED | RC/Production hardening | 两周只提供受控环境、预检、文字降级和真实录屏 | 安全、权限、隐私、兼容矩阵、SLO、运维与发布 Gate | 混合 |

## 5. 历史滚动十个工作日最大能力路径

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

这是 2026-08-01 形成的滚动路径快照，不是从当前日期重新开始的日历或当前任务清单。出现风险时，先保住 Contract、真实状态、安全边界和文字路径，再降级媒体自然度或 UI 完整度。

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
7. **每任务执行上下文和目标 provenance 已实现**：Scheduler 不再在执行时读取 singleton 可变 `_agent`，而是为每任务固定独立的进程内 Agent/context；并发 Session 隔离，周期任务保留 context，终态/取消/删除/service stop 释放。持久状态和 UI 返回 `project_dir`、`project_id`、来源 Session/Channel；前端无法从 persisted Session 与精确注册项目解析绝对当前项目路径时 fail closed，capture 中 session/target/bridge identity 改变时零请求失效；这只约束正常客户端一致性，不证明 Web 请求身份不可伪造。重启后缺少旧 context 的任务诚实失败，不借新 Agent。
8. **后端 per-path single-process 创建幂等已实现**：服务端派生 owner scope，`origin_namespace` + `idempotency_key` 配合同一进程、同一 JSON store 路径共享锁、`create_commands` ledger 和 intent fingerprint 做 get-or-create。同意图重放同 ID、只触发一次；冲突返回 `IDEMPOTENCY_CONFLICT`；删除保留 tombstone，reload 后可恢复。该保证不跨进程，也不是 exactly-once。
9. **服务端读取与控制的一致性 scope 已实现**：`schedule.list/status/cancel/logs/delete` 从 Web request 字段派生 owner + project execution target；必需的 `channel_id/session_id` 缺失或非法、完整 owner scope 不一致，或请求 target 与 stored target 中已知的 `project_dir/project_id` 不一致时 fail closed，并在读取、取消、变更或释放前阻止正常客户端串线。`app_id` 当前可空，遗留 unknown project 字段不猜测。Web 身份仍由请求提供，因此这不是认证、租户隔离或抵御恶意伪造的生产鉴权。
10. **严格 reconciliation 和真实任务卡已实现**：exact-key list 必须唯一，并逐项核对 task ID、query、pipeline、namespace、key 与 target。任务在网络往返期间从 pending 漂移到 running/terminal 时保留后端真值；task card 显示 command ID、恢复来源、冲突和 provenance，不合成假状态。
11. **foundation 已完成历史审阅和验证**：后端 `3da101cf`、前端 `42e76d30` 已落地；当时命令记录为 Live Voice 前端 **155/155**、chatStore marker 与相关回归 **24/24**、全前端 TypeScript 通过、Vite build **4494 modules transformed**，Python **226/226 passed**。155 与 24 两组有 9 项重叠，不能相加；Git 保存测试代码、命令和结果记录，但未保存 JUnit 产物，不能把历史记录当作新 clone 已复跑。它们也不能替代稳定句听感和真实有副作用任务 E2E。

### 7.1 第一批切片仍未解决的正式版风险

- 稳定句预读仍用本地 response epoch 和 chatStore final marker，没有服务端 response/generation provenance。并发 cron/proactive/迟到 final 可能误归属；10 秒 recovery 只能避免永久 thinking，不能恢复或认证 provisional 文本。
- planner/FIFO 只能证明 planned/enqueued，不能证明声音已经播放或用户已经听到；缺少 playback ACK/cursor 和 presented history。
- 前端 stable command ID 只覆盖同一次 Bridge mutation/retry/reconcile；`lastVisibleTask`、未决 mutation 与 task card projection 仍是当前页面/Session 内存。刷新后尚无持久 command journal、连续 monitor、多任务消歧或通用 Executor。
- schedule 的锁、真值和幂等 ledger 都是单进程边界。JSON task store 没有跨进程 CAS/事务、唯一执行所有权、生产级 crash recovery 或外部副作用 reconciliation；多个进程共享 store 和 D1/D2 durability 仍需正式 Task Control Core 解决。
- Live Voice 的打断、退出和 session fence 只影响语音反馈或新的派发，不能取消已经发出的 `schedule.run`；`schedule.cancel` 也不能撤销已发生的代码修改。
- task-scoped Agent/context 和 project/origin provenance 已消除执行时借用最后一个 Agent 与目标猜测，但 context 仍只在进程内，持久 target 尚不含完整 model/provider/config/permission 快照；重启恢复仍需正式执行上下文存储。
- 前端已经接入同-key retry 与 scoped exact-key reconciliation，服务端也已经对 list/status/cancel/logs/delete 强制单用户请求一致性 scope（非生产鉴权）；剩余 `mutation-unknown` 只在记录不唯一、identity/target 冲突或仍无法证明结果时 fail closed。没有跨刷新 command journal、持续轮询/事件回流、跨进程唯一约束、exactly-once 或 D1/D2，因此仍不能宣称完整幂等 Task Control。

### 7.2 下一实现切片：前台持续在线 + 后台非阻塞 + 结果异步回流

Foundation 的范围已经冻结。当前下一切片按 D-031 使用 `schedule.status` 为主、scoped exact-key `schedule.list` 为恢复入口的 poll-backed monitor：任务一经真实派发，Live Voice 前台立即恢复监听；独立 task projection 持续更新真实 task card；terminal 状态与后端现有事实字段始终显示，并只在麦克风关闭、Agent/TTS 空闲且未播报过时朗读一次简短通知。

D-031 尚未编码；开始前必须先提交 D-032 开发前 checkpoint。该切片不修改 chatStore 的消息或 processing，不抢占麦克风/Agent TTS，也不扩成完整 TaskEvent push/replay、通用多任务 NLU、跨进程 exactly-once、D1/D2 或完整 P3。

### 7.3 D-031 编码前必须锁定的边界

以下不是实现后的补作文档，而是 D-032 开发前 checkpoint 的阻断项：

1. **页面生命周期**：D-031 只承诺同一页面内的断线重连与 poll reconciliation；当前随机 command ID 不能在整页刷新后恢复。整页刷新明确显示 unsupported，直到后续引入最小持久 command journal，不能把 `schedule.list` 写成无 identity 的猜测恢复。
2. **A→B successor**：B 是当前活动任务并进入 monitor；A 保留独立的 cancelled/terminal 卡和 successor 关系。首版不同时轮询任意多个活动任务，也不把 B 伪装成 A 的原地更新。
3. **终态真值**：当前接口只有 `status/progress/last_error` 等字段，没有版本化 `terminal_outcome` 或自然语言结果。D-031 将合法 envelope、匹配的 `task_id`、可识别或可保留 raw value 的 `status`、target/provenance 作为必需事实；缺失、非法或不匹配时 adapter 必须失败并保留旧投影。只有可选的 `progress`、`last_error` 缺失时显示 `unknown`。在正式 WorkProgress 闭环前必须新增版本化 outcome 合同，不能由前端猜测“成功结果”。
4. **错误 envelope**：transport error、`ok=false`、`ok=true` 但 payload 含业务 error、缺失任务和非法/新增字段必须在 adapter 层归一化为稳定的成功/失败结果；失败用例要断言无播报、无假终态、无错误 task mutation。
5. **持久范围**：后端 Task JSON store/日志依赖本机 `JIUWENSWARM_DATA_DIR`；前端 task card/projection/command state 只在页面内存，刷新即丢。二者都不会通过 Git 或换机恢复。开发、V0 验收和真实副作用 E2E 必须使用彼此隔离的数据目录。
6. **安全范围**：现有 owner/project 校验只用于单用户 Demo 的请求一致性；Web 身份来自客户端字段，不是生产授权。D-031 不扩大此边界，生产版需认证会话和服务端派生身份/项目 registry。

以上六项及对应正反 tests 未写入 `STATUS.md` 的 scenario matrix 并提交前，不进入 D-031 代码实现。

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
