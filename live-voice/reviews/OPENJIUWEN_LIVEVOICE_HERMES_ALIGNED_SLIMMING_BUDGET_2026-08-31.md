# OpenJiuwen LiveVoice Hermes 对标瘦身预算与执行合同 — 2026-08-31

状态：**未来执行约束，尚未实施。** 本文件不改变 `STATUS.md` 的当前优先级，
不授予迁移、删除、AgentCore PR、产品验收或远端提交信用。只有当正式 LiveVoice
开发完成、产品验收通过，并且 `STATUS.md` 明确激活瘦身包时，才可把本文件作为
该包的目标预算和大方向约束。

风险：本文档本身为 root `TESTING.md` 下的 Tier 0 文档；未来每个代码改动仍按其
实际 authority、协议、安全、状态、并发、恢复和副作用边界独立定级，不继承
Tier 0。

## 1. 本文件拥有什么

本文件是以下内容的唯一未来预算记录：

1. Hermes 对标后的 18 个责任模块 LOC 预算；
2. 正确收敛后的层级规模和总规模上限；
3. 正式开发完成后的重新基线方法；
4. 小方向允许调整、大方向必须保持的边界；
5. AgentCore 下沉、single-writer cutover、legacy 退休和删除 Gate。

本文件不取代其他 authority：

- 当前产品状态、完成边界和激活包仍由 [`STATUS.md`](../STATUS.md) 管理；
- 当前 228 项 symbol 责任的唯一去留由
  [原子责任表](OPENJIUWEN_LIVEVOICE_ATOMIC_DISPOSITION_2026-08-31.md) 管理；
- 当前 152 路径、caller 和 Hermes 证据由
  [完整模块处置表](OPENJIUWEN_LIVEVOICE_MODULE_DISPOSITION_AND_HERMES_COMPARISON_2026-08-25.md)
  支持；
- 当前物理 LOC、五层架构和八条调用链由
  [零基线审计](OPENJIUWEN_LIVEVOICE_ZERO_BASE_MODULE_AUDIT_2026-08-31.md)
  管理；
- 风险、正负场景、零禁止副作用和独立审查要求由 root `TESTING.md` 管理。

如果路径、文件或 API 在正式开发中改变，先重新映射到原子责任和本文件的 18 个
模块，不得把路径变化解释为 owner、Gate 或预算已经失效。

## 2. 固定比较事实与 LOC 口径

| 对象 | 固定 source | 口径 |
|---|---|---|
| LiveVoice 当前产品事实 | `hx/0812_live_voice_w3@59998e2c5724257bd410885b35e59e1b37027030` | 128 个专属生产路径 159,210 physical LOC，加 24 个共享宿主中可归因的 4,054 symbol/segment LOC，共 163,264 |
| 归属判断 | `codex/livevoice-agentcore-hermes-prep@cfb7f030d0e7ceb08d1a15c94c0ba631334e8bf3` | 零基线、Hermes 比较、228 项原子责任；该 commit 只修改文档，未实施瘦身 |
| Hermes Live Voice | `bielcarpi/hermes-live-voice@3dd8af386b845a1486b05b088bbc2b5a642a5b28` | 62 个 shipped 文件 25,254 physical LOC；去除插件内完全重复的 Browser SDK/worklet 后为 22,530 |

`physical LOC` 包含空行和注释，目的是复现仓库物理 footprint，不代表复杂度、质量
或可删除量。当前多职责文件为了闭合 163,264 总数，整文件只记入一个主责任模块；
真实迁移和删除仍必须按原子 symbol 处置，不能按整文件主责任粗暴删除。

## 3. 18 个模块的当前值与目标预算

“中心目标”是正式瘦身的工程预算；“允许区间”用于适配最终验收代码。低端不是
强制删减指标，高端不是自动许可。模块超过高端、总量超过 56,900，或者出现新的
authority、共享协议、迁移或产品策略时，必须重新记录范围、理由、owner、风险和
验收，不能以实现细节变化默许扩张。

| 责任模块 | 当前 LiveVoice LOC | Hermes shipped LOC | 中心目标 LOC | 允许区间 | 目标处置与合理差异 |
|---|---:|---:|---:|---:|---|
| Browser Audio Edge | 6,941 | 5,763 | 5,000 | 4,500–5,500 | 保留设备、capture/playout、浏览器全局 owner 和真实播放 ACK；合并重复 queue、fence 和兼容输出。Hermes shipped 含重复打包的 Browser SDK/worklet，去重浏览器实现约 3,039 行。 |
| Web/Gateway media transport | 10,834 | 937 | 4,200 | 3,500–5,000 | 保留已有 WebChannel/Gateway 的窄 LiveVoice 插件、identity、sequence、ACK、backpressure、reconnect 和 cleanup；合并前后端重复 codec，注册和资源关闭只有一个 owner。 |
| Speech provider layer | 13,195 | 1,803 | 5,800 | 5,000–6,500 | 保留 batch/streaming STT/TTS、Provider-neutral port、fallback 和 TEXT 降级；合并 contract、provider、route 和 capability。若最终不再要求 batch fallback，本模块预算应再下降而非保留。 |
| Committed input/product authority | 10,182 | 763 | 3,600 | 3,000–4,500 | 保留 voice/text unified commit、principal/project scope、确认、模型和 intent policy；这些属于 Jiuwen 产品边界，不进入 AgentCore，也不得分散成第二套 P2/P3 authority。 |
| Conversation Runtime | 8,453 | 1,942 | 3,500 | 3,000–4,500 | 保留一套 turn/response/generation/presentation authority 和 late-output fence；删除平行 Runtime、无生产 caller 的 replica 和 subordinate coordinator 重复状态。 |
| Agent Bridge | 3,568 | 1,140 | 1,000 | 700–1,300 | 直接复用 Agent/Tool/Runner/DeepAgent/Harness；只保留 committed context、Jiuwen Agent 选择、输出投影和生命周期薄适配，退休 thread-pool/fake Agent lane。 |
| Task domain/control | 4,759 | 2,075 | 1,000 | 700–1,300 | 通用 Task/Attempt/Command/Result authority 下沉 AgentCore；LiveVoice 只保留产品 intent/control 映射。Hermes 的 TaskSupervisor 证明该责任存在，不证明 LiveVoice 应重建它。 |
| Task Store/outbox/result | 14,951 | 1,075 | 600 | 300–800 | AgentCore 成为唯一 Task/Event/Outbox/Result/Cursor truth；LiveVoice 最多保留只读、版本校验的 importer/rollback reader，不允许双写或永久兼容 Store。 |
| Project executor | 7,131 | 0 | 3,000 | 2,500–4,000 | Hermes Voice 把实际执行交给外部 Hermes Agent；Jiuwen 仍需 project/worktree/Git patch/file Tool/symlink/cleanup Adapter。通用 Attempt、Result、worker 和 Effect journal 必须移出。该模块属于 Jiuwen Host，不属于语音核心。 |
| Checkpoint/effect recovery | 2,953 | 0 | 800 | 500–1,200 | 仅在最终 D1/D2 产品合同仍要求跨 crash window 的安全恢复时保留 project codec、probe、compensation；通用 checkpoint publication、effect journal 和 continuation token 归 AgentCore。 |
| Task event/progress | 6,000 | 312 | 1,500 | 1,000–2,000 | AgentCore 提供 event/head/cursor；LiveVoice 保留 cancellation-aware subscription、可说进度投影、TEXT fallback 和前台语音/后台 Task 仲裁。 |
| Presentation/history | 5,413 | 0（嵌入其他模块） | 2,200 | 1,800–3,000 | Jiuwen 的 DOM、audio、Chat history 和 Task notification 是不同 adoption fact，保留一个明确 owner；网络发送、synthesis 成功和真实呈现不得互相冒充。 |
| Formal Web/UI | 12,788 | 4,701 | 5,200 | 4,500–6,500 | 保留正式 P1/P2/P3 产品表面、设备选择、恢复和 Task presentation；拆除 7,527 行 Panel 的多状态机，停止构造并退休 legacy 产品。 |
| Composition/configuration | 23,907 | 1,172 | 2,500 | 1,800–3,500 | 保留一个薄 composition root、能力声明、feature gate 和 host registration；14,016 行 registry 不得继续拥有 handler、policy、replay、presentation 和 lifecycle 的实现。 |
| Observability/deployment/privacy | 12,186 | 2,668 | 3,500 | 2,800–4,500 | 保留 runtime correlation、privacy projection、bounded exporter、readiness 和必要 preflight；benchmark、fault harness、Alpha conformance、离线报表和物理验收 recorder 迁 validation/support。 |
| Schema/protocol | 4,731 | 742 | 1,500 | 1,000–2,000 | 保留按 authority 分域的一份 canonical schema 和 Jiuwen Web envelope；Python/TypeScript client、method catalog、allowlist 和状态值从单一源生成，v1 和无 caller contract 退休。 |
| Legacy/compatibility | 5,914 | 0 | 0 | 0–300（仅 cutover 过渡） | `useLiveVoiceDemo`、旧 P1、旧 Task bridge/client/monitor 和 AutoHarness LiveVoice 分支在 Gate 后停止分配并退休；过渡代码不得成为永久预算。 |
| Test/reference in production | 9,358 | 161 | 200 | 0–500 | 只允许极小 runtime smoke/readiness leaf；replica、fake、benchmark、fault harness、L0 UI/recorder 和未调用 contract/result route 迁 test/validation/support 或删除。 |
| **合计** | **163,264** | **25,254** | **45,100** | **36,600–56,900** | 相对当前中心目标减少 118,164 行（72.4%）；相对 Hermes shipped 为 1.79 倍，相对 Hermes 去重实现为 2.00 倍。 |

## 4. 正确收敛后的层级预算

| 最终 owner | 中心预算 | 包含的上表模块 |
|---|---:|---|
| LiveVoice Core + Channel | 23,700 | Browser Audio、Web/Gateway media、Speech、Conversation、Task 语音进度、Presentation、语音/媒体协议 |
| JiuwenSwarm Host/Product/UI | 18,000 | committed/product policy、Project Executor、Formal Web/UI、composition、runtime observability 和最小 support |
| AgentCore thin bridges | 3,400 | Agent、Task、Store、checkpoint/effect Adapter/importer；不包含 AgentCore 自身公共实现 LOC |
| Legacy | 0 | cutover 结束后无永久 owner |
| **完整可归因集成** | **45,100** | 不是全部放在 `server/live_voice`；真正 Core + Channel 约 23,700 |

AgentCore 公共实现不计入 LiveVoice 模块预算，正如 Hermes Voice 不把 Hermes Agent
自身实现计入 25,254 行。未来若评估整个 OpenJiuwen 多仓库总成本，应另建同口径
跨仓审计，不能把共享 AgentCore LOC重新记回每个消费者。

## 5. 为什么目标仍比 Hermes 多

45,100 相比 Hermes shipped 多 19,846 行。允许存在的主要差额必须由下列已命名
责任解释，不允许再用笼统的“Jiuwen 更复杂”解释：

| 差异来源 | 目标相对 Hermes 的主要净差额 | 必要性条件 |
|---|---:|---|
| WebChannel/Gateway 独立媒体协议 | +3,263 | 继续使用既有多宿主 Channel，且 identity/ACK/backpressure/reconnect/cleanup 合同仍是验收要求 |
| Batch + Streaming STT/TTS 和降级 | +3,997 | 双路径、Provider-neutral 和 TEXT fallback 仍是正式功能；否则降低预算 |
| Jiuwen commit/auth/confirmation/model policy | +2,837 | voice/text unified commit、project scope 和高风险操作确认仍属于产品合同 |
| 更严格的 turn/response/generation fence | +1,558 | late output、barge-in 和跨 surface 零禁止副作用仍需证明 |
| project/worktree/Git patch Executor | +3,000 | LiveVoice 产品仍直接承载项目级 Code Agent 结果和安全清理 |
| D1/D2 project recovery Adapter | +800 | 跨 crash window checkpoint/effect 要求仍存在；通用 authority 已在 AgentCore |
| Task spoken progress 和独立 presentation truth | +3,388 | TEXT/voice 仲裁、DOM/audio/history adoption 和 ACK 仍是独立事实 |
| 多宿主 composition、隐私观测和跨语言协议 | +3,417 | 只包括薄 host leaf、运行诊断和 generated contract，不包括 validation harness |
| Agent/Task/Store 下沉节省 | -1,690 | AgentCore 已被接受、安装并成为唯一 authority |
| 最小 runtime smoke 差额 | +39 | 不得扩张成生产树测试框架 |
| **净差额** | **+19,846** | 任一前提取消时，同步降低对应模块预算 |

## 6. 不可通过“小调整”改变的大方向

正式开发完成后的路径、symbol 名称、Adapter API 和模块内 LOC 可以重新映射，
但以下方向不可作为普通适配调整：

1. **AgentCore owns generic truth。** LiveVoice 不得永久拥有第二套 Task、Attempt、
   Command、Event、Outbox、Result、Cursor、Checkpoint 或 Effect authority。
2. **一个事实一个 writer。** 迁移期间禁止无明确事务和回滚合同的双写；cutover
   后旧 Store/Core 不再分配新记录。
3. **正式路线唯一。** formal 与 legacy capture/Task/TTS owner 不得在最终产品同时
   构造；隐藏 UI 不等于停止 runtime allocation。
4. **Host 只有窄插件。** WebChannel、Gateway、AgentServer、Deep adapter 和
   ChatPanel 只保留 registration/facade/leaf，不再内嵌新的 LiveVoice policy。
5. **协议单源生成。** Python/TypeScript schema、method catalog、allowlist 和状态值
   不得继续手工多份维护。
6. **测试退出生产路径。** test/reference/benchmark/fault/physical-validation 代码迁到
   test、validation 或 support；测试价值不能成为生产 owner。
7. **预算是警戒线，不是删除 KPI。** 不得为达到 LOC 破坏正向行为、失败关闭、
   恢复、隐私、安全或零禁止副作用；确有新产品责任时必须正式重新定界，而不是
   隐藏超支。

改变上述任一方向需要一个新的架构/authority 决策、更新的 Hermes/AgentCore
证据、独立风险定级和明确用户接受；普通文件移动、API 适配或新代码合入不能自动
改变它们。

## 7. 正式开发完成后的重新基线流程

未来执行者不得直接拿 `59998e2c` 的旧路径做删除列表。必须按以下顺序启动：

1. 从 Git 固定正式开发和产品验收通过的精确 clean commit，记录 branch、HEAD 和
   upstream；运行时凭据、设备、数据库和项目状态不由 Git 恢复。
2. 读取当前 `README.md`、`STATUS.md`、本文件、228 项原子责任表和 root
   `TESTING.md` 的适用风险部分；旧计划不得覆盖当前激活包。
3. 对 `59998e2c..验收 commit` 做增量清单，将每个新增、删除、重命名和拆分的
   stable symbol 映射到 18 个模块及一个原子 disposition。
4. 重新计算 physical LOC：专属文件计整文件；共享宿主只计稳定
   symbol/segment；共享宿主余量继续排除。
5. 记录每个模块的新当前值、中心目标、允许区间和差额。路径/API/最终 Provider
   适配属于小方向；新的 authority、协议、产品策略或超过高端属于重新定界。
6. 形成依赖有序的实际瘦身包；每包声明 capability、owner、风险、依赖、范围、
   排除和验收，不把 18 个模块一次性作为一个巨大改动。

如果最终验收代码已经自然删除某项责任，只记录事实和证据，不重新制造兼容层来
匹配旧清单。

## 8. 迁移和删除顺序

推荐依赖顺序如下；具体并行度由当时的 disjoint owner 和活动包决定：

1. 冻结 canonical schema 和 AgentCore public capability/API；本地候选、preflight
   或未安装 PR 不能作为替换事实。
2. 先建立薄 Agent、Task、event/cursor、checkpoint/effect 和 project Adapter，并
   让新旧实现通过同一正向/负向/恢复 oracle。
3. 对 Task/Store/Result/Event/Checkpoint/Effect 执行 quiesced single-writer
   cutover；保留版本校验 importer/rollback reader，不保留第二 writer。
4. 拆 Project Executor，只把 project/worktree/Git/Tool/probe/cleanup 留在 Jiuwen
   Host；通用 lifecycle/journal/result 进入 AgentCore。
5. 收敛 Conversation、Presentation 和 Channel owner，再拆 registry、Panel 和
   shared-host segment；行为保持由测试证明，不以文件拆分本身记完成。
6. formal P1/P2/P3 全链验收后停止 legacy allocation，证明 feature-off、隐藏 UI、
   reconnect 和 rollback 均无旧 owner 副作用，再删除旧 lane。
7. 将 validation/reference 代码迁出生产路径，迁移仍有效的 oracle 后删除无 caller
   模块和重复 schema。
8. 运行逐模块 canary、回滚演练、完整产品 Journey 和最终独立跨模块审查，再记录
   实测最终 LOC；预算本身不授予完成信用。

## 9. 每个删除 Gate 的最低证据

任一旧实现、表、schema、compatibility branch 或文件删除前，至少必须满足：

- replacement public API 已在锁定依赖中安装，而不是只存在本地 worktree；
- 所有生产 caller 已迁移，静态扫描和运行 composition 均证明旧 owner 不再分配；
- 正向业务场景成功，错误 scope、stale generation、重复 command、cancel race、
  reconnect、crash window、corruption 和 feature-off 等适用负向场景失败关闭；
- Agent、Tool、Task、audio/history、project/file 和受保护状态的禁止副作用显式为零；
- 持久化迁移、旧版本读取、single-writer、canary 和 rollback 通过；
- 仍有效的测试 oracle 已迁到新 owner，删除不是通过丢失覆盖获得；
- 受影响模块按 root `TESTING.md` 完成风险相称的 focused/affected regression 和
  独立审查；
- 当前 `STATUS.md`、本文件的实测预算表和相关 source/evidence 一致。

未满足 Gate 时只能标记 `PARTIAL` 或 `BLOCKED`；不得将“计划删除”“已下沉设计”或
“LOC 已分配给目标模块”报告为已删除、已迁移或已验收。

## 10. 完成判定

一次 Hermes 对标瘦身只有同时满足以下条件才算完成：

1. 产品验收通过的行为保持，所有受影响安全/恢复/零副作用合同重新通过；
2. AgentCore 是通用 authority 的已安装唯一 owner，LiveVoice 只持有允许的薄桥接；
3. legacy 最终分配为零，测试/reference 不再伪装成生产模块；
4. shared host 只含窄 registration/facade/leaf；schema 和 method catalog 单源生成；
5. 实测完整可归因 LOC 位于 36,600–56,900，中心目标约 45,100；任何高端超支已
   经新的正式责任决策，而不是未解释的实现膨胀；
6. 最终报告同时给出完整集成 LOC 和真正 Core + Channel LOC，不再把 Jiuwen
   Host、AgentCore 或 validation 责任统称为“语音核心”。

本合同允许未来实现适配代码事实，但不允许通过重新命名、移动目录、复制生成物或
改变统计口径规避已经接受的收敛方向。
