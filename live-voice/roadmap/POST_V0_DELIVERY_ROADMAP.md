# Live Voice：W2 90% Demo 与 Integrated Web Alpha 交付路线

> 更新日期：2026-08-12
> 当前产品和交付决策：[D-046、D-055、D-056、D-058、D-059、D-060、D-061、D-062、D-071、D-072、D-074–D-076](../decisions/DECISIONS.md)
> 当前实现事实、track 状态和产品验收清单：[STATUS.md](../STATUS.md)
> 当前 S5–S8 任务、依赖、风险、module-close oracle 和退出条件：[ALPHA_S5_S8_EXECUTION_PLAN_2026-08-12.md](ALPHA_S5_S8_EXECUTION_PLAN_2026-08-12.md)
> 已完成 Week 1 的历史 priority/dependency/boundary 与 package contracts：[WEEK_1_EXECUTION_PACKAGES_2026-08-03.md](WEEK_1_EXECUTION_PACKAGES_2026-08-03.md)
> Web Alpha 稳定工作包、Demo 替换关系、依赖和目标窗口：[WEB_ALPHA_DELIVERY_MATRIX_2026-08-05.md](WEB_ALPHA_DELIVERY_MATRIX_2026-08-05.md)
> 当前执行方式：[D-074–D-076](../decisions/DECISIONS.md) 定义 coherent 本地提交、模块/阶段 review、S5→S8 关键节点和 verify-first 当前任务合同；D-060/D-062 的非重叠 worker 图只在当前 packet 明确启用并行时生效，D-061 保留完整 reviewed 集成批次后的一次累计 smoke，远端更新继续单独批准。
> 完整目标架构仍由不可变 [FULL_SOLUTION_2026-07-30.md](../architecture/FULL_SOLUTION_2026-07-30.md) 定义；本文负责当前范围、顺序窗口和验收，不把 Alpha 写成 Production，也不把原并行估算继续写成单线日历承诺。

## 1. 交付目标

项目只维护一条累计工程路线。D-075 将顺序交付状态、长期能力结构和实现工作包分开：

1. **V0 — 已完成且冻结**：第一时间证明真实麦克风输入、committed transcript、真实 JiuwenSwarm Agent/Tool、真实结果和语音输出能端到端运行。
2. **Week 2 — Integrated Demo**：P1、P2、P3alpha、Context、Progress、Failure/Degradation 和 Observability 在同一 Demo 中累计运行；正式模块按 Port/Adapter/flag 逐段替换 V0 shortcut，适用自动验证通过，并完成一次完整人工产品验收。
3. **Historical Week 3–4 window — Integrated Web Alpha**：对应当前 S5–S8；P1 + P2 + P3alpha 三个真实纵向切片、桌面 Web 产品路径以及 P2/P3alpha 联合自动与人工验收通过。完整 P3 是 stretch goal。
4. **Later — Beta/RC/Production**：完整 P3、D1/D2、生产鉴权、跨平台、运营 SLO、隐私/retention、兼容矩阵和发布加固继续累计，不倒灌为当前 Web Alpha 的隐含阻塞项。

V0、W2 Integrated Demo 和 Integrated Web Alpha 使用不同的验收合同。一次 V0/W2 PASS 不能证明 Alpha，一次模块 conformance 也不能证明累计产品或真实设备路径。

本文只在回溯旧计划或 package target window 时沿用 `W1/W2/W3/W4`。它们不是当前阶段、当前日历周或默认队列。D-060/D-062 可在明确 packet 中恢复非重叠 leaf/package 并发，但没有恢复原“两周/四周”日历承诺；只有新的资源与工期决定才能重新冻结日期。

### 1.1 四层结构

| 层 | 标识 | 用途 | 当前事实由谁维护 |
|---|---|---|---|
| 项目阶段 | `S0`–`S9` | 表示顺序交付状态，只能前后推进 | [STATUS.md](../STATUS.md) |
| Alpha 关键节点 | `A0`–`A3` | 定义 S5–S8 的进入/退出条件 | 本文；当前结果在 STATUS |
| 能力轨与模块 | `Shared/X`、`P1/P2/P3alpha`；AIO/SR/SS、RM/CR/II/AB、TC/ED/VB | 表示长期架构所有权，可跨多个阶段演进 | 完整方案/ACG；当前覆盖在 STATUS |
| 工作包 | `*-A/*-B/*-C` | 表示模块内 contract、first-real、closure/hardening 批次 | [Web Alpha delivery matrix](WEB_ALPHA_DELIVERY_MATRIX_2026-08-05.md) |

完整方案中 `P1/P2/P3` 的 Phase 用法按 D-075 解释为架构能力分组，不再作为当前项目阶段。一个模块“W2 已证明”只说明其 W2 覆盖通过；没有满足本文件和 Alpha acceptance 的部分仍为 `Alpha PARTIAL`。

### 1.2 顺序阶段与 Alpha 关键节点

| Stage | 名称 | 稳定退出条件 |
|---|---|---|
| S0 | V0 Proof | 真实麦克风→committed text→真实 Agent/Tool→真实结果→语音输出的冻结证据通过 |
| S1 | Shared Foundations | ACG critical kernel、A-package foundations、fixtures/fakes/conformance 的既定范围关闭 |
| S2 | D-031 Bounded Compatibility | 项目绑定的有界单任务兼容 Adapter 按自身合同关闭，不取得正式 TC/ED/VB authority |
| S3 | W2 Integrated Demo | 适用自动验证加一次完整 W2 人工产品旅程；结果可为 `PRODUCT-ACCEPTED` |
| S4 | Develop Rebaseline | 已迁移实现与 develop 删除/替代意图一致，受影响及累计验证通过 |
| S5 / A0 | Alpha Baseline & Gap Freeze | 固定 tested baseline、范围/非目标、acceptance→module gap、risk/owner/dependency、机器条件和待用户选择项 |
| S6 / A1 | Alpha Module Closure | P1、P2、P3alpha、Shared/X 的必需 gap 分别完成实现、自动验证和 D-074 模块收口 review |
| S7 / A2 | Alpha Integrated Candidate | 全部必需 module closure 组合进同一干净 tested source；累计 review、自动矩阵、构建/静态和关键真实路径通过 |
| S8 / A3 | Alpha Product Acceptance | 用户在 A2 exact source 上按 Alpha 专用 showcase 完成一次完整人工旅程并作最终决定 |
| S9 | Later/Beta/Production | 完整 P3、D1/D2、生产鉴权、广泛兼容、发布/运营/隐私加固；不属于当前 Alpha |

S5/A0 是当前 Alpha 的唯一入口；A0 未关闭前可以做只读调查和有界缺陷修复，但不得把历史 W3/W4 package rows直接当作当前大规模实现队列。D-076 的 [S5–S8 execution plan](ALPHA_S5_S8_EXECUTION_PLAN_2026-08-12.md) 将这些稳定出口落实为当前 task IDs、依赖、风险、oracles 和 exclusions；mutable result 仍只看 STATUS。A1 可按独立所有权并行，A2/A3 必须串行并绑定同一 tested source。

## 2. Web Alpha 范围与非目标

### 2.1 Alpha 范围

Integrated Web Alpha 至少包括：

- **P1 Speech I/O**：浏览器 Audio I/O、Speech Recognition/Synthesis Port、一个真实可用 Adapter、Browser fallback、提交/编辑或安全澄清边界、文字降级；
- **P2 Realtime Conversation**：Realtime Media、Conversation Runtime、Interaction Engine、Agent Bridge、response/generation fence、自然或受控 barge-in、真实 presentation facts、后台工作不冻结前台；
- **P3alpha Task Control**：稳定 task/command/attempt identity、`create/get/list/status/cancel/events`、TaskEvent/Core reducer、一个 D0 Executor、committed Voice–Task Bridge、progress/result 回流、restart reconciliation 的诚实状态；
- **横切能力**：Context、WorkProgress、Capability/Error、route telemetry、fault injection、feature-off/text regression、Web 集成、安全上下文、浏览器权限/设备/页面生命周期和受控真实设备证据。

### 2.2 Alpha 非目标

- 完整 P3 的 `update/provide_input/pause/resume/reprioritize`、跨设备 unread/replay 和 D1/D2；
- 外部工具副作用 exactly-once、通用补偿或回滚；
- 生产多租户鉴权、对象存在性隐藏、完整审批体系；
- 移动 Web、PWA、Firefox、Safari 和公开跨浏览器/跨操作系统兼容矩阵；
- Windows `.exe`、WebView2、原生安装升级和 Windows 原生设备生命周期；
- RC/Production 的长期 SLO、安装升级全矩阵、正式运维和隐私保留系统。

这些内容只能在明确改变 milestone 后进入 Alpha 范围，不得因“完整方案”四个字静默扩张。

## 3. 资源与可行性假设

完整方案列出 28 个模块包和 3 个横切包，顺序时间盒约 47–78 人日，且不包含完整 P3 扩展。原四周目标依赖：

- 至少三条能够持续产出的并行实现轨；
- 一个共享契约/集成 owner，避免各轨创造第二套 authority；
- 从 Day 1 开始持续接回同一个 Demo；
- 当前没有固定 lane、worker 数量或跨模型分工；只有 active packet 才能按可用执行环境声明并行所有权和独立 review 入口；
- Provider、桌面 Chromium 浏览器、音频设备、Web 部署/代理、Executor 和私有配置在相应真实产品验收前可用。

D-060/D-062 只在当前任务包明确启用时提供按实际依赖和容量生成的非重叠 worker 图和一个单写集成 owner；没有 active parallel packet 时不保留历史 lane、worker 或模型分工。它们不改变外部 Provider、浏览器/设备、部署、Executor 或真实产品验收的依赖，也不把原并行 timebox 恢复为日历承诺。

## 4. Architecture Contract Gate 的渐进实现

这里的 Architecture Contract Gate 是共享协议/authority 合同，不是 D-071/D-072 已退役并删除的签名证据 Gate。ACG 的完整语义保持有效，但实现 checkpoint 分两层。

### 4.1 ACG critical kernel：Day 1–2 的公共阻断项

以下 primitive 必须先由 Sol 冻结，并以共享 types/fixtures/fakes/conformance 落地：

- opaque identity、parent、scope 和 authority map；
- committed input / TurnCommit 的零副作用边界；
- interaction/turn/response/task/attempt 的核心状态与 terminal outcome；
- `playback.stop`、`response.cancel`、`round.cancel`、`task.cancel` 四种不升级的 scope；
- response generation fence 和迟到事件零应用；
- Command/Query/Result/Event 的最小 version/correlation/sequence；
- Capability、Error、unknown/unsupported/unavailable/fallback；
- feature-off 保持当前文字 Chat/E2A/Task 行为且零新增 effect。

Kernel 通过 grouped Tier 3 review 后，P1/P2/P3alpha A 包可以并行。

### 4.2 Consumer gates：在对应 B/C 接线前完成

- P1 Provider/Audio 接线前：hypothesis/audio chunk、provider provenance、session cancel、隐私/retention；
- P2 播放/history 接线前：surface ACK/cursor、presented ledger、Context/WorkProgress 仲裁；
- P3alpha Store/Executor 接线前：AuthorizationContext、atomic command/event/snapshot/outbox、attempt dedup、restart reconciliation；
- Web/Release acceptance 前：route telemetry、benchmark schema、安全上下文、权限/设备/页面生命周期、部署/代理以及真实 Provider/Executor verification。

无关模块不等待未消费的扩展 contract。完整 Alpha-consumed ACG conformance 必须在 A2 Integrated Candidate 前闭环。

## 5. 并行 delivery tracks

| Track | A 包：contract/fake | B/C 包：真实接线 | 纵向退出条件 |
|---|---|---|---|
| Shared/X | ACG kernel、trace/metric schema、route labels | X-OBS、X-E2E、Web integration | 每个 Demo 段可证明 formal/fallback/substitute；Web 故障和 flag-off 可复现 |
| P1 | AIO-A、SR-A、SS-A | AIO-B/C、SR-B/C、SS-B/C | browser microphone → AIO → STT → current Agent → TTS → browser playout，含 fallback/设备/权限 |
| P2 | CR-A、RM-A、II-A、AB-A | CR-B/C、RM-B/C、II-B/C、AB-B | 持续输入、非阻塞 Agent、barge-in、fence、presented history 和后台负载成立 |
| P3alpha | TC-A、ED-A、VB-A | TC-B/C、ED-B、VB-B/C | structured/text/voice command → Core → D0 Executor → TaskEvent/Progress → origin surface |

各轨可以在共享 kernel 后并行；同一轨内部仍按消费者依赖推进。每次真实接线都必须立即进入累计 Integrated Demo 的可选 route，而不是等待 Week 2 前统一合并。

## 6. W2 顺序窗口（原并行资源下的十日模型）

本节保留原并行资源假设下的依赖顺序和里程碑间距，不表示 D-060 执行窗口或任何当前日历日期。已完成 Week 1 的精确历史 owner、依赖条件、目标文件、scenario oracle 和验证命令可查 dated [Week 1 execution plan](WEEK_1_EXECUTION_PACKAGES_2026-08-03.md)；当前状态和下一动作只写入 STATUS。

| 原并行时间模型 | 顺序目标 | 退出判据 |
|---|---|---|
| Day 1–2 | ACG critical kernel；route telemetry schema；各轨 A 包可编译骨架 | shared fixtures/fakes 在 Python/TypeScript 一致；现有 flag-off 回归不变 |
| Day 3–5 | P1/P2/P3alpha A 包并行；首批 Browser/Agent/AutoHarness compatibility Adapter 接入 | 三轨各有 fake vertical；至少一个真实累计路径开始替换 V0 shortcut |
| Day 5 | D-031 go/no-go | TC-B/Event projection 可在 Day 7 入 Demo则跳过/缩减；否则批准 1–2 天最小 poll Adapter |
| Day 6–8 | 真实 B 包、Continuous Integration、Web/Provider/Executor 后验启动 | formal route 有 trace；fallback/substitute 可切换；错误不污染文字路径 |
| Day 9 | Week 2 automated closure | 适用自动正向/负向/flag-off/回归/build/static 检查通过，未达项明确 |
| Day 10 | Integrated Demo product acceptance | 用户按 [INTEGRATED_DEMO_ACCEPTANCE.md](../validation/INTEGRATED_DEMO_ACCEPTANCE.md) 和 [INTEGRATED_SHOWCASE.md](../demo/INTEGRATED_SHOWCASE.md) 完成一次完整人工旅程 |

遇到风险时，优先保住共享 authority、committed-only、真实状态、fence、文字降级和累计可运行 Demo；降低非关键 UI 精度、扩展 Context adapter 或完整 P3 stretch，而不是用 hardcode 伪造结果。

## 7. 历史 W3/W4 顺序窗口到当前 S5–S8 的映射

本节保留原目标窗口以解释 dated package matrix，不是当前阶段表或日历计划。当前执行按 §1.2 的 A0→A1→A2→A3 进入和退出。

### Week 3（映射到当前 A0 freeze 与 A1 module closure）

- 完成主要 B/C 包和 consumer-specific ACG 扩展；
- 用真实 Media/Speech/Agent/Executor 替换剩余关键 substitute；
- 完成桌面 Web 安全上下文、浏览器权限/设备/页面生命周期、媒体路由、故障注入和 benchmark 基线；
- 连续运行 P1/P2/P3alpha 三个纵向切片；
- 开始 P2/P3alpha 联合 non-blocking interaction/progress 场景。

### Week 4（映射到当前 A1 closure、A2 candidate、A3 acceptance）

- 关闭所有 Tier 2/3 必需 gap；
- 按 D-074 完成必需 module closure review，并在 A2 审查累计 diff 与跨模块 integration seams；
- 在同一被识别的测试源码上运行受影响 unit/contract/integration/build 与真实 Web/Provider/Executor 自动检查；
- 完成一次覆盖纵向与联合场景的人工产品验收，并形成简短的 sanitized acceptance record；
- 只有在 P1 + P2 + P3alpha 和 Web 平台的适用自动与人工要求全部通过时标记 Integrated Web Alpha。

完整 P3 stretch 不得阻塞 P3alpha Alpha。如果 stretch 改变 canonical operation/state/durability，必须单独设计和验收。

## 8. Week 2 产品验收闭环

D-071 退役 Demo Replacement Ledger、签名证据 Gate、固定 artifact 槽位和重复三次完整展示。W2 只有两个完成条件：

1. 最终测试源码上的适用自动正向、负向、flag-off、回归、构建和静态检查通过；
2. 用户在一个完整产品会话中人工通过 P1、P2、P3alpha、非阻塞/打断、恢复与可见降级旅程。

D-072 进一步从当前源码删除已退役 Gate 的 evaluator/CLI、签名与 manifest 编排、runtime evidence owner、rehearsal/fault runner 和产品内 Gate 专属故障注入。保留的 P1/P2/P3、Task/Tool/Agent、安全确认、架构合同 Gate、风险分级与产品观测不属于该删除范围。

`formal`、`fallback`、`demo_substitute`、`unsupported` 和 `unknown` 继续用于如实描述实际 route，不再换算分数。任何必需产品行为或安全不变量失败时保持 `PARTIAL` 或 `FAIL`；缺少旧签名、manifest 或 Ledger 分数不影响产品状态。

## 9. D-031 最小边界

D-031 仅在 Day 5 go/no-go 选择后执行。若需要，范围固定为：

- 一个 current task，最多保留一个真实 predecessor/successor 关系；
- `schedule.status` 正常读取，exact-key `schedule.list` 只用于同页已知 command reconciliation；
- 一个 in-flight read、可取消 timer、connection pause、generation/context fence；
- backend `unknown/error/missing/scope mismatch` 不更新为 success、不播报成功、不触发 mutation；
- terminal notification 必须经过当前音频/交互 owner 仲裁；
- flag-off、unmount、target/session/Bridge 变化停止全部 timer/effect；
- 不写 Chat message/processing，不创建/取消任务，不构造 TaskEvent，不实现多任务、durable replay 或跨进程恢复。

原始完整 pre-review 在 [SOL_MODULE_PRE_REVIEWS_2026-08-03.md](../SOL_MODULE_PRE_REVIEWS_2026-08-03.md) 中保留，用于选取必要风险和审阅实际 diff，不再强制逐行实现其全部 legacy 设计。

## 10. 风险分级验证与分层 review

| Tier | 适用范围 | Required evidence | Review boundary |
|---|---|---|---|
| 0 | docs、机械修改、纯重构 | affected checks、链接/格式/characterization | 按需；不建立完整矩阵 |
| 1 | 普通功能、Port/Adapter/UI | positive journey、关键 negative/flag-off、affected integration/regression | 模块收口时做完整 scoped diff review |
| 2 | 状态、并发、mutation、cancel/fence | 所有适用 P/N/B/S/T/C/R/I/F/K/X 风险；零禁止副作用 | 新增/改变高风险契约时先做设计 checkpoint；模块收口做冷审和一次独立 review |
| 3 | shared protocol/authority/security/durability、production release | 完整适用 D-032、fault/recovery、真实 E2E；里程碑另按 D-071 完成人工产品验收 | 模块边界独立 review，阶段 candidate 再审累计 diff 和集成 seam |

### D-074 分层 review 节奏

- 开发中：检查实际受影响 diff 并运行 focused tests；每次小修改、保存或中间 commit 不触发独立 review 仪式。
- 模块/相关 package group 收口：对模块起点到当前结果的完整 scoped diff 做冷审；Tier 2/3 changed boundary 在这里运行一次独立 `/review` 或等价入口。
- 集成批次收口：冲突处理和 integration glue 先做 affected review/tests，完整 reviewed batch 组装后按 D-061 运行一次累计 smoke。
- 阶段/里程碑收口：审查阶段基线到 tested source 的累计 diff、跨模块 seam 和实际验证，再按 D-071 完成一次完整人工产品验收。
- finding 修复后重跑受影响检查；只有修复实质改变相应模块、共享契约或阶段语义时才重复对应层级 review。独立入口不可用时记录替代方式和限制，不得声称 `/review` 已运行。

### D-032 保留的不变量

- tests 从预期合同产生，不能只证明当前实现；
- 正例成功，反例明确拒绝/fail closed；
- Agent/Tool/Task/audio/history/store/other-scope 的禁止副作用为 0；
- ACK、timeout、unknown、queued/enqueued 不冒充 terminal/presented/success；
- test count/coverage 不替代 scenario oracle；
- 真实 Provider、设备、Executor 和用户感知不能由 fake 单测替代。

### D-046 调整的流程

- STATUS 不保存巨型矩阵；详细设计保存在 review record；
- coherent package group 可以共享设计 checkpoint、implementation batch、模块收口 review 和 commit；
- Tier 0/1 不制造完整 11 维 N/A 表；
- 不要求每个小包独立 checkpoint commit/push；
- W2/A3 在被识别且干净的测试源码上运行适用自动验证与各自一次完整人工产品验收；
- 普通本地 commit 按根 `AGENTS.md` 和 D-074 在已授权范围内自主形成 coherent scope，避免为 commit 而 commit；所有远端 ref 更新仍须单独精确批准。

## 11. 集成与兼容规则

1. 新模块通过明确 capability/feature flag 接入同一产品路径；关闭后原 Chat JSON/E2A、Session History、Agent/Tool、TTS 和 task 行为不变。
2. route telemetry 必须记录每段实际 owner 和 implementation class：`formal`、`fallback`、`demo_substitute`、`unsupported`、`unknown`。
3. Provider、Bridge、UI、Executor 不得成为第二生命周期 authority；Compatibility Adapter 保留 provenance，不能把 legacy v1 重新标为完整 v2。
4. 模块 fake 用于自动化和 fault injection，不作为现场真实成功证据。
5. 每个 landed module 立即进入 Integrated route 的可选组合，先通过 fake upstream/downstream，再连接真实 Adapter。
6. V0 candidate 保持冻结；累计 Demo 和 Alpha 使用新的被识别测试源码与验收记录，不修改 V0 事实。
7. 按 D-047，`useLiveVoiceDemo`、稳定句 preview、前端 TaskBridge 和旧 `schedule.*`/JSON foundation 只作为冻结 Compatibility/fallback/substitute；除有界回归修复、timeboxed D-031 或正式 route 薄接线外不得继续扩建，CR/TC/ED 等正式 owner 随实际替换接管，避免先做独立大重构或形成第二 authority。

## 12. 交付状态语义

- `NOT STARTED`：没有实现和测试事实；设计接受不改变该状态。
- `IN PROGRESS`：实现或自动验证尚未完成。
- `PARTIAL`：存在可运行 foundation/substitute，或自动/人工验收尚有未完成项。
- `CLOSED`：明确命名的工程阶段或模块边界已经满足其适用 Tier、真实接线和自动验证；必须同时写清关闭到哪个 milestone，不能把 `W2 CLOSED` 外推为 `Alpha CLOSED`。
- `PRODUCT-ACCEPTED`：一个 milestone 已完成 D-071 自动验证加一次完整人工产品验收；当前只适用于 W2。
- `BLOCKED`：缺少外部条件或必要决策，当前无法诚实完成。
- `OUT OF CURRENT SCOPE`：属于 S9 或明确非目标，不进入当前 Alpha 队列，也不是 blocker。

设计文档的 accepted/sign-off 不等于实现 `CLOSED`。W2 产品验收也不自动关闭任何 Alpha 模块或 A1–A3 节点。
