# Live Voice：两周 90% Demo 与四周 Integrated Alpha 路线

> 更新日期：2026-08-03
> 当前产品和交付决策：[D-046](../decisions/DECISIONS.md)
> 当前实现事实、track 状态和 Demo Replacement Ledger：[STATUS.md](../STATUS.md)
> 当前五工作日的 Sol priority/dependency/boundary 与 execution-ready 包：[WEEK_1_EXECUTION_PACKAGES_2026-08-03.md](WEEK_1_EXECUTION_PACKAGES_2026-08-03.md)
> 完整目标架构仍由不可变 [FULL_SOLUTION_2026-07-30.md](../architecture/FULL_SOLUTION_2026-07-30.md) 定义；本文负责当前四周执行解释，不把 Alpha 写成 Production。

## 1. 交付目标

项目只维护一条累计工程路线：

1. **V0 — 已完成且冻结**：第一时间证明真实麦克风输入、committed transcript、真实 JiuwenSwarm Agent/Tool、真实结果和语音输出能端到端运行。
2. **Week 2 — Integrated Demo 90%**：P1、P2、P3alpha、Context、Progress、Failure/Degradation 和 Observability 在同一 Demo 中累计运行；正式模块按 Port/Adapter/flag 逐段替换 V0 shortcut，Replacement Ledger 至少 90/100 且 mandatory invariants 全部通过。
3. **Week 3–4 — Integrated Windows Alpha**：P1 + P2 + P3alpha 三个真实纵向切片以及 P2/P3alpha 联合 Gate 通过。完整 P3 是 stretch goal。
4. **Later — Beta/RC/Production**：完整 P3、D1/D2、生产鉴权、跨平台、运营 SLO、隐私/retention、兼容矩阵和发布加固继续累计，不倒灌为四周 Alpha 的隐含阻塞项。

V0、Week 2 和 Week 4 使用不同的验收合同。一次 V0 PASS 不能证明 Alpha，一次模块 conformance 也不能证明累计 Demo 或真实设备路径。

## 2. 四周承诺与非目标

### 2.1 承诺范围

Integrated Windows Alpha 至少包括：

- **P1 Speech I/O**：Audio I/O、Speech Recognition/Synthesis Port、一个真实可用 Adapter、Browser fallback、提交/编辑或安全澄清边界、文字降级；
- **P2 Realtime Conversation**：Realtime Media、Conversation Runtime、Interaction Engine、Agent Bridge、response/generation fence、自然或受控 barge-in、真实 presentation facts、后台工作不冻结前台；
- **P3alpha Task Control**：稳定 task/command/attempt identity、`create/get/list/status/cancel/events`、TaskEvent/Core reducer、一个 D0 Executor、committed Voice–Task Bridge、progress/result 回流、restart reconciliation 的诚实状态；
- **横切能力**：Context、WorkProgress、Capability/Error、route telemetry、fault injection、feature-off/text regression、Windows 集成和受控真实设备证据。

### 2.2 四周非目标

- 完整 P3 的 `update/provide_input/pause/resume/reprioritize`、跨设备 unread/replay 和 D1/D2；
- 外部工具副作用 exactly-once、通用补偿或回滚；
- 生产多租户鉴权、对象存在性隐藏、完整审批体系；
- macOS/HarmonyOS/移动端兼容矩阵；
- RC/Production 的长期 SLO、安装升级全矩阵、正式运维和隐私保留系统。

这些内容只能在明确改变 milestone 后进入四周承诺，不得因“完整方案”四个字静默扩张。

## 3. 资源与可行性假设

完整方案列出 28 个模块包和 3 个横切包，顺序时间盒约 47–78 人日，且不包含完整 P3 扩展。因此四周目标依赖：

- 至少三条能够持续产出的并行实现轨；
- 一个共享契约/集成 owner，避免各轨创造第二套 authority；
- 从 Day 1 开始持续接回同一个 Demo；
- Sol 对跨轨和高风险边界集中评审，非 Sol 模型并行执行已冻结的有界包；
- Provider、Windows 设备、Executor 和私有配置在相应真实 Gate 前可用。

若 Week 1 结束仍只有一个有效执行轨，必须重新估算范围或时间；不得继续用顺序 timebox 宣称四周可达。

## 4. Architecture Contract Gate 的渐进实现

ACG 的完整语义保持有效，但实现 Gate 分两层。

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
- Windows/Release Gate 前：route telemetry、benchmark schema、真实设备/Provider/Executor evidence。

无关模块不等待未消费的扩展 contract。完整 ACG conformance 仍在 Week 4 Alpha Gate 前闭环。

## 5. 并行 delivery tracks

| Track | A 包：contract/fake | B/C 包：真实接线 | 纵向退出条件 |
|---|---|---|---|
| Shared/X | ACG kernel、trace/metric schema、route labels | X-OBS、X-E2E、Windows integration | 每个 Demo 段可证明 formal/fallback/substitute；故障和 flag-off 可复现 |
| P1 | AIO-A、SR-A、SS-A | AIO-B/C、SR-B/C、SS-B/C | microphone → AIO → STT → current Agent → TTS → playout，含 fallback/设备/权限 |
| P2 | CR-A、RM-A、II-A、AB-A | CR-B/C、RM-B/C、II-B/C、AB-B | 持续输入、非阻塞 Agent、barge-in、fence、presented history 和后台负载成立 |
| P3alpha | TC-A、ED-A、VB-A | TC-B/C、ED-B、VB-B/C | structured/text/voice command → Core → D0 Executor → TaskEvent/Progress → origin surface |

各轨可以在共享 kernel 后并行；同一轨内部仍按消费者依赖推进。每次真实接线都必须立即进入累计 Integrated Demo 的可选 route，而不是等待 Week 2 前统一合并。

## 6. 两周 critical path

本节冻结里程碑时序；当前 Week 1 的精确 owner、依赖 Gate、目标文件、scenario oracle、验证命令和 return-to-Sol 条件以 dated [Week 1 execution plan](WEEK_1_EXECUTION_PACKAGES_2026-08-03.md) 为准。包的实际状态和 tested SHA 仍只写入 STATUS。

| 时间 | 必达产出 | 退出判据 |
|---|---|---|
| Day 1–2 | ACG critical kernel；route telemetry schema；各轨 A 包可编译骨架 | shared fixtures/fakes 在 Python/TypeScript 一致；现有 flag-off 回归不变 |
| Day 3–5 | P1/P2/P3alpha A 包并行；首批 Browser/Agent/AutoHarness compatibility Adapter 接入 | 三轨各有 fake vertical；至少一个真实累计路径开始替换 V0 shortcut |
| Day 5 | D-031 go/no-go | TC-B/Event projection 可在 Day 7 入 Demo则跳过/缩减；否则批准 1–2 天最小 poll Adapter |
| Day 6–8 | 真实 B 包、Continuous Integration、Windows/Provider/Executor 后验启动 | formal route 有 trace；fallback/substitute 可切换；错误不污染文字路径 |
| Day 9 | Week 2 candidate freeze | Replacement Ledger 有证据、mandatory invariants 全绿、未达项明确 |
| Day 10 | Integrated Demo Gate | [INTEGRATED_DEMO_ACCEPTANCE.md](../validation/INTEGRATED_DEMO_ACCEPTANCE.md) 至少 90/100，并按 [INTEGRATED_SHOWCASE.md](../demo/INTEGRATED_SHOWCASE.md) 连续运行 |

遇到风险时，优先保住共享 authority、committed-only、真实状态、fence、文字降级和累计可运行 Demo；降低非关键 UI 精度、扩展 Context adapter 或完整 P3 stretch，而不是用 hardcode 伪造结果。

## 7. Week 3–4 critical path

### Week 3

- 完成主要 B/C 包和 consumer-specific ACG 扩展；
- 用真实 Media/Speech/Agent/Executor 替换剩余关键 substitute；
- 完成 Windows 设备/权限/路由、故障注入和 benchmark 基线；
- 连续运行 P1/P2/P3alpha 三个纵向切片；
- 开始 P2/P3alpha 联合 non-blocking interaction/progress 场景。

### Week 4

- 关闭所有 Tier 2/3 必需 gap；
- 对共享 ACG 和各真实 Adapter 执行 grouped Sol post-review；
- 在同一 immutable candidate 运行受影响 unit/contract/integration/build、真实 Windows/Provider/Executor、纵向和联合 Gates；
- 形成 sanitized Alpha evidence；
- 只有在 P1 + P2 + P3alpha 必需 Gate 全部通过时标记 Integrated Windows Alpha。

完整 P3 stretch 不得阻塞 P3alpha Alpha。如果 stretch 改变 canonical operation/state/durability，必须单独设计和验收。

## 8. Week 2 Demo Replacement Ledger

权威当前分数保存在 STATUS；验收算法和 mandatory invariants 保存在 Week 2 acceptance。固定权重为：

| Journey | Weight | Full credit requires |
|---|---:|---|
| P1 Speech I/O | 20 | formal AIO/SR/SS Port 路由、真实 Adapter/fallback、提交与权限/设备降级证据 |
| P2 Realtime Conversation | 40 | CR/RM/II/AB 实际拥有 lifecycle、媒体/交互、Agent mapping、fence 和 presentation facts |
| P3alpha Task Control | 25 | TC/ED/VB 实际拥有真实 command/event/task/attempt、D0、progress/result；legacy poll 只可获部分分 |
| Cross-cutting | 15 | Context facts、Failure/Degradation、route telemetry、Observability、fault injection 和 flag-off/text regression |
| **Total** | **100** | **至少 90，且 mandatory invariant 全部通过** |

评分规则：

- `formal`：目标模块及真实 Adapter 通过本 Journey 所需证据，可获得该子项全分；
- `formal + fallback`：正常路径正式、fallback 诚实且可验证，可获得全分；
- `Demo substitute`：只能按 acceptance 中预先分配的部分分计入，不能因为“可展示”就当作正式完成；
- `unsupported/unknown`：可以保持诚实，但对应目标能力不得计满；
- 没有 route telemetry 或证据无法确定实际实现时记 0；
- 任一 mandatory invariant 失败时，Demo Gate FAIL，即使算术达到 90。

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

## 10. 风险分级验证与 Sol 签字

| Tier | 适用范围 | Required evidence | Sol involvement |
|---|---|---|---|
| 0 | docs、机械修改、纯重构 | affected checks、链接/格式/characterization | 按需；不建立完整矩阵 |
| 1 | 普通功能、Port/Adapter/UI | positive journey、关键 negative/flag-off、affected integration/regression | grouped contract/diff review 按需 |
| 2 | 状态、并发、mutation、cancel/fence | scoped pre/post review；所有适用 P/N/B/S/T/C/R/I/F/K/X 风险；零禁止副作用 | Sol 必须签署边界和实际 diff |
| 3 | shared protocol/authority/security/durability、Week 2/4 Gate | 完整 D-032、fault/recovery、immutable candidate、真实 E2E/manual evidence | Sol 最终判断和 Gate 签字 |

### D-032 保留的不变量

- tests 从预期合同产生，不能只证明当前实现；
- 正例成功，反例明确拒绝/fail closed；
- Agent/Tool/Task/audio/history/store/other-scope 的禁止副作用为 0；
- ACK、timeout、unknown、queued/enqueued 不冒充 terminal/presented/success；
- test count/coverage 不替代 scenario oracle；
- 真实 Provider、设备、Executor 和用户感知不能由 fake 单测替代。

### D-046 调整的流程

- STATUS 不保存巨型矩阵；详细设计保存在 review record；
- coherent package group 可以共享 pre-review、implementation batch、post-review 和 commit；
- Tier 0/1 不制造完整 11 维 N/A 表；
- 不要求每个小包独立 checkpoint commit/push；
- Week 2/Week 4 使用 immutable candidate 统一证明累计结果；
- Git commit 和 push 仍分别遵守根 `AGENTS.md` 的精确批准门。

## 11. 集成与兼容规则

1. 新模块通过明确 capability/feature flag 接入同一产品路径；关闭后原 Chat JSON/E2A、Session History、Agent/Tool、TTS 和 task 行为不变。
2. route telemetry 必须记录每段实际 owner 和 implementation class：`formal`、`fallback`、`demo_substitute`、`unsupported`、`unknown`。
3. Provider、Bridge、UI、Executor 不得成为第二生命周期 authority；Compatibility Adapter 保留 provenance，不能把 legacy v1 重新标为完整 v2。
4. 模块 fake 用于自动化和 fault injection，不作为现场真实成功证据。
5. 每个 landed module 立即进入 Integrated route 的可选组合，先通过 fake upstream/downstream，再连接真实 Adapter。
6. V0 candidate 保持冻结；累计 Demo 和 Alpha 使用新的 candidate/evidence，不修改 V0 事实。
7. 按 D-047，`useLiveVoiceDemo`、稳定句 preview、前端 TaskBridge 和旧 `schedule.*`/JSON foundation 只作为冻结 Compatibility/fallback/substitute；除有界回归修复、timeboxed D-031 或正式 route 薄接线外不得继续扩建，CR/TC/ED 等正式 owner 随实际替换接管，避免先做独立大重构或形成第二 authority。

## 12. Gate 状态语义

- `NOT STARTED`：没有实现和测试事实；设计接受不改变该状态。
- `IN PROGRESS`：有未完成实现或 evidence，不能计满 Replacement Ledger。
- `PARTIAL`：存在可运行 foundation/substitute 或部分证据，但目标 route/Gate 未完成。
- `CLOSED`：相应 Tier 的必需行为、风险、真实接线和证据全部满足。
- `BLOCKED`：缺少外部条件或必要决策，当前无法诚实完成。

设计文档的 accepted/sign-off 不等于实现 `CLOSED`。Week 2 90% 也不自动关闭 Week 4 Alpha 模块。
