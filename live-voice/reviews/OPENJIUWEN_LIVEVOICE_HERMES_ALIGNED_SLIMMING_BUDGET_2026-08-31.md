# OpenJiuwen LiveVoice 冻结后瘦身激活 handoff 与 Hermes 规划区间 — 2026-08-31

状态（D-096，2026-09-01 修订）：**准备分支收尾入口，尚未实施。** 本文件不改变
`STATUS.md` 的当前优先级，不授予迁移、删除、AgentCore 实现、产品验收或远端
提交信用。只有当 `STATUS.md` 记录 feature-complete 边界在一个 exact clean source
上通过并显式激活瘦身包时，未来执行者才使用本文件启动增量重基线。

本准备分支不实现 AgentCore 基础能力。历史候选和 preflight 只保留
为缺口、风险和测试 oracle 证据。实际 LiveVoice 与 AgentCore 代码调整必须在冻结
后的产品源码和届时的 AgentCore 权威源码上分别建立新的实施分支/worktree。

风险：本文档本身为 root `TESTING.md` 下的 Tier 0 文档；未来每个代码改动仍按其
实际 authority、协议、安全、状态、并发、恢复和副作用边界独立定级，不继承
Tier 0。

## 1. 本文件拥有什么

本文件是未来瘦身工作的单一入口，负责：

1. 固定当前可复现的总量、Hermes 对标事实和规划口径；
2. 给出 18 个责任模块的非约束规划区间；
3. 规定特性冻结后的增量重基线输入、输出和失败条件；
4. 将 LiveVoice 直接复用、薄 Adapter、AgentCore 下沉、内部收敛和退休组织成
   依赖有序的实施包；
5. 固定迁移、single-writer、canary、rollback 和删除 Gate；
6. 说明最终如何报告真实 LiveVoice、JiuwenSwarm Host、AgentCore 和 support 成本。

本文件是唯一入口，不是唯一事实来源：

- 当前产品状态、完成边界和激活包由 [`STATUS.md`](../STATUS.md) 管理；
- 228 项 stable-symbol 责任和当前去留由
  [原子责任表](OPENJIUWEN_LIVEVOICE_ATOMIC_DISPOSITION_2026-08-31.md) 管理；
- 152 路径、caller 和 Hermes 证据由
  [完整模块处置表](OPENJIUWEN_LIVEVOICE_MODULE_DISPOSITION_AND_HERMES_COMPARISON_2026-08-25.md)
  支持；
- 当前物理 LOC、五层架构和八条调用链由
  [零基线审计](OPENJIUWEN_LIVEVOICE_ZERO_BASE_MODULE_AUDIT_2026-08-31.md)
  管理；
- 复用、适配和下沉的 symbol/capability 证据由
  [迁移映射](OPENJIUWEN_LIVEVOICE_SYMBOL_MIGRATION_MAP_2026-08-24.md) 管理；
- 风险、正负场景、零禁止副作用和独立审查由 root `TESTING.md` 管理。

## 2. 固定事实与禁止推断

| 对象 | 固定 source | 可复现事实 |
|---|---|---|
| LiveVoice 产品审计基线 | `hx/0812_live_voice_w3@59998e2c5724257bd410885b35e59e1b37027030` | 128 个专属生产路径 159,210 physical LOC，加 24 个共享宿主中可归因的 4,054 symbol/segment LOC，共 163,264；共享宿主其余 53,534 行排除 |
| 原子归属基线 | `codex/livevoice-agentcore-hermes-prep@cfb7f030d0e7ceb08d1a15c94c0ba631334e8bf3` | 152/152 路径、228 项责任、48 个多责任路径；13 项 `AGENTCORE_PR` 只表示未来下沉要求 |
| AgentCore 零基线 | [D-097 审计](OPENJIUWEN_AGENTCORE_FOUNDATION_ZERO_BASE_AUDIT_2026-09-01.md) | 13 个 locator 收敛为四个事务能力族/六个最小 public seam；历史 15,128 行不是预算或迁移单元 |
| Hermes Live Voice | `bielcarpi/hermes-live-voice@3dd8af386b845a1486b05b088bbc2b5a642a5b28` | 62 个 shipped 文件 25,254 physical LOC；去除插件内完全重复 Browser SDK/worklet 后为 22,530 |

`physical LOC` 包含空行和注释，只用于复现 footprint，不代表复杂度、质量或可删除
量。冻结审计仍保留 38,215 行 truly mixed symbol group，以避免虚假分层归属。
因此当前只有 **163,264 总量**可作为生产责任事实；不存在已经证实的 18 模块当前
LOC、最终层级 owner 精确 LOC 或“必然删除 118,164 行”的事实。

任何未来执行不得：

- 按旧文件路径或整文件主责任直接删除；
- 把 local candidate、preflight 或内部 AgentCore API 当成 installed replacement；
- 把移动到 AgentCore/test/support 的代码都报告为 OpenJiuwen 多仓库净删除；
- 为达到 LOC 数字损害正向行为、fail-closed、恢复、隐私、安全或零副作用。

## 3. 18 个责任模块的规划区间

下表是 activation-time planning hypothesis，不是当前模块 LOC、accepted architecture
或完成 Gate。中心值之和为 45,100，区间之和为 36,600–56,900；最终实施可低于
低端，也可在责任有证据且经重新定界后高于高端。冻结后必须先按 stable symbol
重算，才能将任何数字用于排包。

| 责任模块 | Hermes shipped LOC | 规划中心 | 规划区间 | 冻结后应保留或收敛的责任 |
|---|---:|---:|---:|---|
| Browser Audio Edge | 5,763 | 5,000 | 4,500–5,500 | 设备、capture/playout、浏览器全局 owner、真实播放 ACK；合并重复 queue/fence/兼容输出 |
| Web/Gateway media transport | 937 | 4,200 | 3,500–5,000 | 既有 Channel/Gateway 窄插件、identity、sequence、ACK、backpressure、reconnect、cleanup；合并 codec 和资源 owner |
| Speech provider layer | 1,803 | 5,800 | 5,000–6,500 | Batch/Streaming STT/TTS、Provider-neutral port、fallback/TEXT 降级；合并 contract/provider/route/capability |
| Committed input/product authority | 763 | 3,600 | 3,000–4,500 | voice/text commit、principal/project scope、确认、模型和 intent policy；不下沉 Jiuwen 产品策略 |
| Conversation Runtime | 1,942 | 3,500 | 3,000–4,500 | 一套 turn/response/generation/presentation authority 与 late-output fence；退休平行 runtime/replica |
| Agent Bridge | 1,140 | 1,000 | 700–1,300 | 复用 Agent/Tool/Runner/DeepAgent/Harness；只留 committed context、Jiuwen Agent 选择和薄投影 |
| Task domain/control | 2,075 | 1,000 | 700–1,300 | 通用 Task/Attempt/Command/Result 目标为 AgentCore；LiveVoice 留产品 intent/control 映射 |
| Task Store/outbox/result | 1,075 | 600 | 300–800 | AgentCore 成为唯一通用 truth 后，只保留有版本校验的 importer/rollback reader；禁止永久双写 Store |
| Project executor | 0 | 3,000 | 2,500–4,000 | Jiuwen Host 留 project/worktree/Git patch/file Tool/symlink/cleanup；通用 lifecycle/result/effect 外移 |
| Checkpoint/effect recovery | 0 | 800 | 500–1,200 | 若最终 D1/D2 仍要求跨 crash window，留 project codec/probe/compensation；通用 publication/journal 下沉 |
| Task event/progress | 312 | 1,500 | 1,000–2,000 | 通用 event/head/cursor 下沉；留可说进度、TEXT fallback 和前台语音/后台 Task 仲裁 |
| Presentation/history | 0（嵌入其他模块） | 2,200 | 1,800–3,000 | 区分 DOM、audio、Chat history、Task notification adoption；网络发送、合成与真实呈现不互相冒充 |
| Formal Web/UI | 4,701 | 5,200 | 4,500–6,500 | 正式 P1/P2/P3 表面、设备选择、恢复和 Task presentation；拆除 Panel 多状态机与 legacy allocation |
| Composition/configuration | 1,172 | 2,500 | 1,800–3,500 | 一处薄 composition root、能力声明、feature gate、host registration；14,015 行 registry 不再承载具体 policy/state machine |
| Observability/deployment/privacy | 2,668 | 3,500 | 2,800–4,500 | runtime correlation、privacy projection、bounded exporter、readiness/preflight；harness/recorder 迁 support |
| Schema/protocol | 742 | 1,500 | 1,000–2,000 | 按 authority 分域的一份 canonical schema；Python/TypeScript client、method catalog、allowlist 从单一源生成 |
| Legacy/compatibility | 0 | 0 | 0–300（cutover 过渡） | replacement Gate 后停止分配并退休；过渡代码不得成为永久 owner |
| Test/reference in production | 161 | 200 | 0–500 | 只留极小 runtime smoke/readiness leaf；fake/benchmark/fault/L0 recorder 迁 test/validation/support |
| **规划合计** | **25,254** | **45,100** | **36,600–56,900** | 与当前 163,264 总量只作规模级比较，不构成删除承诺 |

## 4. 五层最终归属的重算规则

最终不能先按整模块分配给一个 owner。冻结后按每个 stable responsibility 重新
归入下列层，层级 LOC 由原子分账求和：

| 层 | 最终责任 | 计量规则 |
|---|---|---|
| L1 LiveVoice Core | channel-neutral turn/speech/presentation policy | 只计真正由 LiveVoice 独占的 symbol/segment |
| L2 Channel Adapter | Browser、WebChannel、Gateway、Audio Device、宿主 envelope | 共享宿主只计 LiveVoice segment，不把整个 Web/Channel 算入语音核心 |
| L3 JiuwenSwarm Host/Product | project、principal、confirmation、UI、composition、project executor、诊断 | 单独报告，不与 L1/L2 合称 Core |
| L4 AgentCore shared foundation | Agent、Tool、Task、execution、event、cursor、checkpoint/effect 的通用 owner | AgentCore 公共实现不计入 LiveVoice；薄 consumer Adapter 计入其实际 L1/L2/L3 owner |
| L5 Transition/Support | legacy、compat、test/reference/benchmark/validation | 分别报告迁移、暂留和最终退休量，不冒充生产 Core |

若需要 OpenJiuwen 多仓库总成本，必须另做 AgentCore + JiuwenSwarm 同口径审计；
LiveVoice footprint 减少不等于多仓库净删除相同数量。

## 5. 为什么规划中心仍比 Hermes 多

下面只是 `45,100 - 25,254 = 19,846` 的可核算解释，不是完成门槛：

| 差异来源 | 规划中心相对 Hermes | 必要性条件 |
|---|---:|---|
| Browser Audio Edge 去重 | -763 | Hermes shipped 含重复打包的 Browser SDK/worklet；Jiuwen 保留一份真实 Browser owner |
| WebChannel/Gateway 独立媒体协议 | +3,263 | 多宿主 Channel 的 identity/ACK/backpressure/reconnect/cleanup 仍是验收合同 |
| Batch + Streaming STT/TTS 和降级 | +3,997 | 双路径、Provider-neutral 和 TEXT fallback 仍为正式功能 |
| Jiuwen commit/auth/confirmation/model policy | +2,837 | unified commit、project scope 和高风险操作确认仍属于产品合同 |
| 更严格的 turn/response/generation fence | +1,558 | late output、barge-in 和跨 surface 零禁止副作用仍需证明 |
| project/worktree/Git patch Executor | +3,000 | Jiuwen 产品仍承载项目级 Code Agent 结果和安全清理 |
| D1/D2 project recovery Adapter | +800 | 最终产品仍要求跨 crash window checkpoint/effect |
| Task spoken progress 与独立 presentation truth | +3,388 | TEXT/voice 仲裁、DOM/audio/history adoption 和 ACK 仍是独立事实 |
| Formal Web、composition、隐私观测和跨语言协议 | +3,417 | 只含薄 host/UI、诊断和 generated contract，不含 validation harness |
| Agent/Task/Store 下沉规划节省 | -1,690 | AgentCore 公共能力被接受、安装并成为唯一通用 authority |
| 最小 runtime smoke | +39 | 不得扩张成生产树测试框架 |
| **净差额** | **+19,846** | 任一前提取消时同步调整相应规划，不保留无责任代码 |

## 6. 激活时需要接受的默认方向

以下是本次审计支持的默认方向。除 single-writer 和 fail-closed 等既有安全约束外，
它们不是由本 Tier 0 文档新设的产品/架构决定；激活时由对应实施包引用既有
Decision，或在缺失时新增并接受 Decision：

1. 通用 Agent/Task/Execution/Event/Cursor/Checkpoint/Effect truth 优先由已安装
   AgentCore 公共能力拥有，LiveVoice 不永久保留第二 authority。
2. 一个事实一个 writer；迁移期间不得无事务/回滚合同双写，cutover 后旧 owner
   不再分配新记录。
3. formal 与 legacy capture/Task/TTS owner 最终只构造一套；隐藏 UI 不等于停止
   runtime allocation。
4. WebChannel、Gateway、AgentServer、Deep Adapter、ChatPanel 只留窄
   registration/facade/leaf，不内嵌新的通用 LiveVoice state machine。
5. Python/TypeScript schema、method catalog、allowlist 和状态值从一份 canonical
   source 生成。
6. test/reference/benchmark/fault/physical-validation 迁到明确的
   test/validation/support owner，仍有效 oracle 先迁后删。
7. LOC 是解释工具，不是删除 KPI；低于规划区间不失败，高于规划区间也不自动
   失败，但必须说明新增责任、owner、风险和验收。

## 7. 特性冻结后的增量重基线

未来执行者必须完成一次有界增量重基线；不重做全部历史审计，也不能跳过：

1. 从 Git 固定通过 feature-complete 边界的 exact clean LiveVoice commit，记录
   branch、HEAD、upstream 和验收来源；机器私有运行状态不由 Git 恢复。
2. 新建基于该产品 commit 的 slimming execution branch/worktree；不得在本准备
   分支上实施 100K 级代码调整，也不得 wholesale merge 本准备分支。
3. 对 `59998e2c..冻结 commit` 枚举新增、删除、重命名和拆分的生产 symbol，逐项
   映射到现有 228 项责任；只为真实新增责任创建新的 stable key。
4. 重新验证受影响 caller、authority、provider、positive/negative oracle 和
   disposition；未受影响的原子责任继承，不做全量重新解释。
5. 重算完整 attributable production LOC：专属文件计整文件；共享宿主只计稳定
   symbol/segment；共享余量继续排除。分别报告 L1–L5，不预设 owner 总量。
6. 读取届时实际安装的 AgentCore 版本和 public exports，将每项需求标为
   `installed`、`adaptable` 或 `absent`；local branch、internal API 和 preflight
   仍不能作为 replacement。
7. 为受影响责任生成依赖有序的实施包；每包声明 capability/module、risk tier、
   dependencies、source/test surfaces、scope、exclusions、acceptance 和 rollback。
8. 若冻结代码已自然删除某项责任，只记录事实与证据，不重建兼容层来匹配旧清单。

增量重基线的必需输出是一张 changed-responsibility delta：`stable key`、冻结后的
symbol、当前 caller/owner、复用/适配/下沉/保留/退休处置、replacement 状态、
实施包、风险和 Gate。缺少任一列时不得开始对应删除。

## 8. 依赖有序的未来实施包

具体文件/API 由增量重基线填写；包边界现在按稳定责任固定：

| 顺序 | 包 | 主要结果 | 启动/关闭条件 |
|---:|---|---|---|
| S0 | 冻结、原子 delta 与 canonical schema | 冻结 source、changed-responsibility delta、单一 schema/method catalog 计划 | feature-complete PASS；差异和跨语言 contract 可复现 |
| S1 | 现有公共能力直接复用 | Agent/Tool/Runner/DeepAgent/Harness 及 Jiuwen shared host 改为直接调用；删除竞争 facade/fixture lane | installed public API 和真实 caller 证明；正负 Agent/Tool 场景通过 |
| S2 | AgentCore 缺口与薄 consumer Adapter | 按 D-097 的 F1–F6 对仍 absent 的 invariant 逐项扩展现有 owner；只在能力 accepted/installed 后组合薄 Task/Event/Cursor Adapter | 每项证明最近 public owner、唯一 transaction/reducer 和真实 adopter；不 wholesale 复用历史候选源码；generic non-Voice tests、public API、版本锁定和独立 review 通过 |
| S3 | Task/Store/Event/Result single-writer cutover | 新 owner 先通过共同 oracle，再 quiesced cutover；旧 Store/outbox/result 停止分配 | migration/importer、old-version read、race/restart/corruption、canary/rollback 和零副作用通过 |
| S4 | Checkpoint/effect 与 Project Executor 拆分 | 通用 publication/journal/reconcile 下沉；Jiuwen 留 project/worktree/Git/Tool/probe/cleanup | AgentCore replacement installed；D1/D2 truth、ambiguous effect、crash window 和 compensation 通过 |
| S5 | LiveVoice Core 与 Channel 收敛 | 合并 Speech/Media/Conversation/Progress/Presentation 重复 owner，拆十项 same-owner 结构债务 | 行为保持、Provider fallback、barge-in、ACK、reconnect 和完整音频链回归通过 |
| S6 | Host/Web/Composition/Protocol 收敛 | registry/Panel/shared host 只留窄 registration/facade/leaf；协议单源生成 | formal Web P1/P2/P3、feature-off、multi-Task、refresh/reconnect 与跨语言 contract 通过 |
| S7 | Legacy 与 production-test 退休 | legacy allocation 为零；oracle 迁 test/validation/support；删除无 caller/重复 schema | replacement、caller scan、feature-on/off、rollback 和测试发现率 Gate 通过 |
| S8 | 累积 canary、验收与计量 | 全产品 Journey、独立跨模块 review、最终 L1–L5 与多仓口径报告 | 所有前置包关闭；exact clean source 上自动化、集成、人测和回滚演练通过 |

S2 若需要 AgentCore 代码，必须先按
[D-097 零基线审计](OPENJIUWEN_AGENTCORE_FOUNDATION_ZERO_BASE_AUDIT_2026-09-01.md)
重新验证 F1–F6。13 个 locator、按既有 physical-LOC 口径计算的 31,325 行 Jiuwen
混合容器和历史 15,128 行 AgentCore 增量都不是实施预算；十个历史 packet 只能提供
风险/oracle 线索，不能作为复用或完成信用。

## 9. 任一迁移或删除的最低 Gate

- replacement public API 已在锁定依赖中安装，而不是只存在本地 worktree；
- 所有生产 caller 已迁移，静态扫描和实际 composition 均证明旧 owner 不再分配；
- 正向业务场景成功，错误 scope、stale generation、重复 command、cancel race、
  reconnect、crash window、corruption 和 feature-off 等适用负向场景失败关闭；
- Agent、Tool、Task、audio/history、project/file 和受保护状态的禁止副作用显式为零；
- 持久化迁移、旧版本读取、single-writer、canary 和 rollback 通过；
- 仍有效测试 oracle 已迁到新 owner，删除不是通过丢失覆盖获得；
- root `TESTING.md` 要求的 focused/affected regression、风险相称独立审查和真实
  产品路径证据完成；
- `STATUS.md`、Decision、source、tests、evidence 和实测计量一致。

未满足 Gate 时只能标记 `PARTIAL` 或 `BLOCKED`；“计划下沉”“已有候选”“LOC 已
分配”均不等于已经替换或可以删除。

## 10. 最终完成与报告

一次 Hermes 对标瘦身只有同时满足以下条件才算完成：

1. 冻结产品行为保持，受影响安全、恢复和零副作用合同重新通过；
2. 已选择的 AgentCore 通用责任由 accepted/installed public capability 唯一拥有，
   LiveVoice/JiuwenSwarm 只保留允许的薄 consumer Adapter；
3. legacy 最终 allocation 为零，test/reference 不再伪装成生产模块；
4. shared host 只含窄 registration/facade/leaf，schema/method catalog 单源生成；
5. 最终报告给出实际 L1 Core、L2 Channel、L3 Host、薄 Adapter、L5 transition/
   support 以及 AgentCore 新增/复用成本，不再把它们统称为“语音核心”；
6. 最终实际 LOC 与 36,600–56,900 规划区间比较并解释差异，但区间本身不决定
   PASS/FAIL，也不存在为了不低于低端而保留代码的要求；
7. 累积 canary、rollback、完整产品 Journey 和独立跨模块审查绑定同一个 exact
   clean source。

本准备分支在上述信息、路由和 Tier 0 一致性检查关闭后即可封存。真正的代码瘦身
从未来冻结产品源的新分支开始；执行者只做增量重基线，不重新发明本次已经关闭的
模块、Hermes 和 AgentCore 归属分析。
