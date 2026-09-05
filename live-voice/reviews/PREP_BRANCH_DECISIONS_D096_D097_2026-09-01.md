# 准备分支决定摘录：D-096 / D-097（2026-09-01，codex/livevoice-agentcore-hermes-prep）

> 这两条决定只存在于准备分支 `codex/livevoice-agentcore-hermes-prep@b9dc8a5c3`，其编号与本分支
> `decisions/DECISIONS.md` 中的 D-096/D-097（L0 普通 Chrome）相撞。本文按原文摘录以便移植后的审计
> 文档可引用；它们不是本分支已接受的产品决定。若未来接受，须按本分支当前编号顺延后写入
> `DECISIONS.md`，并修正移植文档中的引用。

## D-096 关闭准备分支为冻结后瘦身 handoff，不要求准备 AgentCore PR

- 日期：2026-09-01。
- 状态：Accepted preparation-closure decision（用户明确要求完成当前独立准备分支的收尾，不继续准备 AgentCore PR；本分支的唯一目的，是在 LiveVoice 特性分支开发完成后，为 LiveVoice 自身瘦身以及通用责任下沉 AgentCore 提供足够、可追溯且不绑定源码行号的信息）。
- 准备输出：保留 152 路径/228 项 stable-symbol 责任、八条真实流程、五层架构、Hermes 解释、直接复用、薄 Adapter、AgentCore 下沉要求、LiveVoice/JiuwenSwarm 保留责任、结构债务、retirement Gate 和规划区间。`AGENTCORE_PR` 继续作为原子处置代码，但只表示未来通用 owner/public-contract gap，不要求本分支实现、replay、包装、提交或推送 PR。
- 历史候选边界：既有 AgentCore candidate、PR01–PR10 packet 和 preflight 只保留为 dated gap/risk/oracle evidence；它们不是 installed capability、当前执行队列、cherry-pick 输入或本分支完成条件。未来若同一缺口仍存在，由届时的 AgentCore owner 在 current source 和 accepted dependency 上重新定界、实现、测试和审查。
- 激活边界：只有 `STATUS.md` 记录 feature-complete 边界在一个 exact clean LiveVoice source 上通过并显式激活 slimming packet 后，才开始代码调整。实际修改从该冻结产品源新建 execution branch/worktree；不得在准备分支实施迁移，也不得 wholesale merge 准备分支或实验候选。
- 增量重基线：激活时必须对 `59998e2c..冻结 source` 枚举新增、删除、重命名和拆分的 stable symbols，映射到现有原子责任，只复审受影响 owner/caller/disposition，重新计算 attributable L1–L5 LOC，并验证届时安装的 AgentCore public API。该步骤是有界 delta，不重做完整 Hermes/模块审计，也不能跳过后直接按旧路径删除。
- LOC 判读：`45,100` 中心和 `36,600–56,900` 只作工程规划区间，不是 accepted architecture、删除承诺或完成 Gate。最终 PASS 由行为、安全、single-writer、migration/canary/rollback、oracle 保留和独立审查决定；实际 LOC 必须如实分层报告并解释偏差，低于区间不失败，高于区间须对新增责任重新定界但不自动失败。
- 重新评估条件：用户要求在特性冻结前迁移；要求本分支交付可提交 PR；feature-complete 激活边界改变；原子责任无法表达冻结后的新 authority/协议；AgentCore installed API 使下沉处置根本变化；或瘦身必须引入新的产品政策、shared schema/migration、第二 writer 或更宽平台承诺。

## D-097 AgentCore 下沉以零基线基础能力为单位，不以 13 个 locator 或历史 15K 为实现单位

- 日期：2026-09-01。
- 状态：Accepted preparation-clarification decision（用户要求像前两次 LiveVoice/Hermes 审计一样深度拆解 AgentCore：逐项说明直接复用、薄适配复用、真正需要新增的通用基础能力、Jiuwen 保留责任，并证明历史几万行是否必要）。
- 事实基线：锁定依赖 `openjiuwen 0.1.16@94e10cb6102c36fe78a64547957c0def97299273` 和刷新上游 `origin/develop@6390bbf230f4ea2dd7446bc01ee882e6a4413d4c` 已有 Runner/Agent/Tool、Task DAO/Manager、Scheduler、AsyncToolRuntime、Checkpointer/Journal 等 primitive，但没有覆盖 scoped durable Task、事务 event/cursor、durable execution ownership、checkpoint publication 和 external-effect truth 的完整公开合同。
- 粒度纠正：228 项 manifest 中 13 个 `AGENTCORE_PR` locator 自本决定起只表示 `AGENTCORE_FOUNDATION_ADD` 方向，应收敛为四个 transaction capability family 和六个最小 public seam：Task/Attempt/command/result、event/outbox、consumer cursor、execution ownership/cancel/settlement、checkpoint publication、external-effect intent/evidence/reconcile。13 不是模块数、实施包数或提交数。
- 15K 判读：历史候选 `4f2c29c..50c065dc` 的 15,128 行生产增量是一个实现尝试，不是需求、目标、预算或可整体采用资产。其必要 invariant 与 God DAO、Manager 纯转发、Authority 重复 reducer/验证、重复 codec/digest、raw Manager bypass、扩大 public exports 和无生产 consumer 的 surface 必须分开判读；未来不得 wholesale replay。
- 单一 owner：六个 seam 必须扩展现有 AgentCore primitive，并由一个 AgentTeams transaction/reducer owner 组合；不得复制 Jiuwen `SqliteTaskStore`、`PersistentTaskCore` 或 `_DirectProjectAttemptJournal`，不得形成永久双 writer。Jiuwen 保留 principal/project/session、Voice turn/presentation、Project/Git/Tool/provider、checkpoint codec 和 compensation policy，只通过 opaque extension/Port 和薄 Adapter 接入。
- 计量和 Gate：按包含空行/注释的既有 physical-LOC 口径，当前 31,325 行混合容器与历史 15,128 行候选互不等价；stable locator 片段也不作为实现预算。冻结后按 production/tests/docs、Jiuwen 删除/保留 Adapter、AgentCore 复用/新增和多仓净变化分别计量。每个 seam 在实现前必须证明最近 public owner、缺失 invariant、唯一 transaction/reducer、adopter、threat model、正负/race/crash/corruption oracle、single-writer migration/canary/rollback；不能给出证据时延期，而不是预造能力。
- 权威记录：[AgentCore 基础能力零基线审计](../reviews/OPENJIUWEN_AGENTCORE_FOUNDATION_ZERO_BASE_AUDIT_2026-09-01.md) 是 13 项 locator 的当前实现粒度与历史候选判读权威；原子 manifest 仍是 stable-symbol 定位权威。
- 重新评估条件：届时 AgentCore installed public API 已补齐某 seam；正式 threat model 要求数据库恶意篡改或跨后端更强保证；发现仓库外 adopter 依赖历史公共 surface；或 frozen LiveVoice 新增无法由六个 seam 和 Jiuwen opaque extension 表达的通用责任。
