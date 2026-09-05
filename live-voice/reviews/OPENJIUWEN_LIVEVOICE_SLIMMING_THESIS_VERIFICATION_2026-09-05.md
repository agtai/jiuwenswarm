# OpenJiuwen LiveVoice 瘦身命题的逐模块验证 — 2026-09-05

> 状态：Integration Owner 的粗粒度验证记录（文档-only；root `TESTING.md` Live Voice risk
> tiers 与 D-046 的 Tier 0 口径）。基线 `hx/0812_live_voice_w3@076065f1b`（生产代码与
> `ebd2b4575` 相同）。要回答的问题只有一个：为什么这些代码能从十几万行压到几万行而
> LiveVoice 仍然正确。按用户要求只到模块粒度，Native engine 排除。本文数字来自脚本在
> HEAD 上的实测，模块归桶是本文按文件名规则做的粗分，不是原子表的逐 symbol 归属；本文
> 未经独立冷复核，只做了求和自检。

## 1. 结论先行

1. **规模不是注释和小重复造成的。** 149 个专属生产文件 181,498 行里空行、注释、文档串
   只占 8%；在 ≥3 个文件里重复定义的私有 helper 只多出约 600 行。所以“压到几万行”
   不能靠删注释或合并小函数，只能靠结构。
2. **规模来自五种结构性重复，每种都在 HEAD 上有可指认的证据：**
   (a) 没有生产 caller 的死代码与并行的 legacy lane，约 16K；
   (b) 在语音目录里重建的通用 Task/Event/Execution/Effect truth，约 30K，其中约 25K 应
   由 AgentCore 拥有；
   (c) 三条观测通道加已闭环的 L0 工具与 Alpha 支持代码，17.3K 里约 14K 是重复或已无 caller；
   (d) 三套 Python schema 加 TS 手写副本，7.5K 里约 5K 是同一 wire contract 的多份实现；
   (e) 产品/运行时/UI/组合层里同一个 truth 有多个 owner：58 个 `*Owner/*Lease/*Authority/
   *Ledger/*Fence/*Journal/*Store/*Registry` 类、三套 response fence、至少四个同模式的
   一次性授权 CAS ledger、三条 route lifecycle、三个 Task UI owner，以及每一层对同一闭合值
   的重复校验（Python 每 27 行一个 `raise`，TS 每 45 行一个 `throw`）。
3. **按机制分账，v1（不含 Native）从约 173.7K 到约 50.4K 的 123K 削减里，前四种机制
   约 54K 是本文能确认的；第五种约 69K 只能确认方向，确认不了幅度。** 因此 v1 更可能
   落在 60K 到 65K，而不是 50K；这仍在计划区间（43K 到 68K）内，但靠近上沿。
4. **正确性靠三层保证：** 死代码与 legacy 删除不改变任何生产路径（caller 扫描为零）；
   AgentCore 下沉保留同一组 invariant（F1–F6），以现有 10.9K 行的 Task Core 测试与
   durability 测试作为 adoption oracle，single-writer cutover 加 canary/rollback；结构收敛
   只做行为保持的合并与搬迁，以现有约 105K 行后端单元测试、前端测试、合成语音 journey
   和物理 demo journey 作为回归 oracle。删除得到的从来不是“功能”，而是重复的实现。

## 2. 实测口径

- 生产集合：`jiuwenswarm/` 下路径或文件名含 live_voice/live-voice/LiveVoice 的 py/ts/tsx/js，
  加 6 个不含该关键字的专属文件；排除测试与 24 个共享宿主整文件。共 149 个文件
  181,498 行，与激活预检的 182,741 行专属口径差 0.7%。
- 非行为行：空行 10,429、注释 2,582、文档串 2,180，合计 15,191（8%）。
- 重复指标：私有 helper 在 ≥3 个文件重复的 16 个名字（`_scope`、`_text`、`_identity`、
  `_required_text`、`_parse_utc`、`_digest` 等）多出 595 行；`raise` 4,978 处，`Violation/
  Error` 类 71 个，`MAX_` 常量 134 个；authority 类 58 个（Owner 20、Lease 13、Authority
  11、Ledger 5、Registry 4、Fence 2、Journal 2、Store 1）。
- Hermes 列沿用预算文档的 shipped LOC；目标列沿用当前计划（重适配加当前分支分析），
  Native 行剔除后 v1 目标约 50,400。

## 3. 逐模块对比与确认

| 模块 | HEAD 实测 | Hermes | v1 目标 | 削减靠什么（证据） | 确认程度 | 正确性守护 |
|---|---:|---:|---:|---|---|---|
| 1 Browser Audio Edge | 8,429 | 5,763 | 5,500 | `productP1VoiceRoute.ts` 4,099 行混装 capture/recognition/playout/diagnostics（债务 #7）；音频诊断 414 行归观测；近端插话候选保留 | 确认方向，幅度合理 | 前端单测、物理 journey |
| 2 Web/Gateway media transport | 17,409（含 Native 段约 2.3K） | 937 | 5,500 | `dedicated_media_registration.py` 7,276 行混装 registration/product authority/diagnostics/Native（#8）；三条 route 文件各自实现 lifecycle 与 fallback 投影（#3/#4/#5，约 5.6K）；TS/Python 两端镜像 transport 是固有的 | 方向确认，幅度存疑：剔除 Native 后 15.1K→5.5K 需去掉约 9.6K，可指认的重复约 6K | reconnect/backpressure/ACK 回归、合成语音 journey |
| 3 Speech provider | 9,909 | 1,803 | 6,000 | 三个约 2.5K 行的文件各自同时装 provider contract、传输与 orchestration（#1/#2）；HTTP/socket 诊断归观测 | 确认 | Provider fallback、D-113 admission 用例 |
| 4 Committed input / product authority | 16,840 | 763 | 3,800 | 一次性授权 CAS ledger 至少四套（`p3_confirmation` 979、`product_authority` 1,302、`production_task_intent` 内确认消费、`unified_committed_input` 的 request binding 与 semantic pending context）；`p3_authenticated_composition` 5,361 行同时是认证、产品请求翻译与重复的 Store/Core/executor 构造根（AR-159） | 方向确认，3,800 偏激进：一个 authorization owner + 一个 journal 后 5K 到 7K 更可信 | 正负授权场景、零副作用断言、语义模型探针 |
| 5 Conversation Runtime | 8,172（含 Native 段约 0.8K） | 1,942 | 4,500 | 三套 fence（播放期插话、生成期打断、Native）合一；`ScriptedCascade` fake 286 行死 | 确认 | 生成期打断、插话既有用例 |
| 6 Agent bridge | 3,168 | 1,140 | 1,500 | `AgentBridgeRuntime` 1,238 与 `JiuWenSwarmRoundHarness` 1,149 是同一 round 的两层；fixture seam 65 行死 | 确认 | Agent/Tool 正负场景 |
| 7 Task domain/control | 5,342 | 2,075 | 1,000 | `formal_task_models` 2,628 行的通用 Task/Attempt/event/cursor/outbox 值类型归 F1–F3；`TaskCore` 581 行死；`PersistentTaskCore` 在 C1 后成薄 facade | 确认，前提是 AgentCore installed | Task Core 测试作为 adoption oracle |
| 8 Task Store | 15,109 | 1,075 | 600 | 整个通用 Store 由 F1–F6 替代；迁移 581 行在 cutover 后退休；只留 importer/rollback reader | 确认为“转移”而非删除：约 5.3K 在 AgentCore 重写，多仓净减约 9K | single-writer cutover、canary、rollback、race/crash/corruption oracle |
| 9 Project executor | 6,694 | 0 | 3,200 | legacy carrier 504 行死；attempt journal 的 generic owner/lease/settlement 归 F4/F6；Direct journal 作为第二 writer 收缩为 Git/worktree 事实 | 确认 | D0/D2 用例、crash window |
| 10 Checkpoint/effect | 2,953 | 0 | 800 | 六个 `durability_*` 文件复制同一组 `_scope/_text/_digest/_profile/_reject_duplicate_keys` helper；prefix verifier 归 F5/F6；只留 codec/identity 映射 | 确认 | durability 测试 |
| 11 Task event/progress | 8,078 | 312 | 1,500 | `task_event_subscription` 1,568 行的游标订阅归 F2/F3；`progress_notification_arbiter` 2,212 与 `task_progress_return` 2,222 各自带 queue/ACK/lease 机制（#9）；`product_p3_text_adapter` 1,206 是呈现 | 方向确认，1,500 偏激进：2K 到 3K 更可信 | 通知/ACK/replay 用例 |
| 12 Presentation/history | 2,045 | 0 | 2,500 | 不需要削减；计划允许略增 | 确认 | 呈现/历史用例 |
| 13 Formal Web/UI | 16,908 | 4,701 | 5,600 | Panel 9,346 行装 P1/P2/P3 owner、recovery、diagnostics、通知仲裁；三个 Task UI owner（`formalTaskIntentRoute` 995、`formalTaskControlLeaf` 941、`formalP3TaskExperience` 952）；三本同模式 bounded journal | 方向确认，5,600 偏激进：6K 到 8K 更可信 | 前端单测、mounted 测试、journey |
| 14 Composition/config | 19,743（含 Native 段约 1.5K） | 1,172 | 2,700 | registry 15,742 行是 P1/P2/P3 handler 工厂加策略，每个 handler 重复做 scope/session/principal 校验，而 `p3_authenticated_composition`、`product_authority`、`product_p2_interaction_adapter` 也各做一遍 | 削减里约 10K 是搬到 4/5/11/13 的“移动”，真正删除的是重复校验；幅度取决于目标模块能否吸收 | feature-off、multi-Task、refresh/reconnect |
| 15 Observability | 17,322 | 2,668 | 3,500 | 无 caller 支持代码 4,150；L0 工具 3.1K 已由 D-095–D-097 闭环可 re-home；OTel 六文件 6.5K、被动 profiling、音频诊断三通道合一 | 确认，是 Task Store 之外最大且最实的削减 | 隐私零泄露断言、export 等价 |
| 16 Schema/protocol | 7,474 | 742 | 2,000 | Python v2 4,000 与 TS 副本 2,785 有 52 个同名类型；v1 235 与 `productCompositionContract` 289 已死；单源生成替代手写副本 | 确认 | 字节/语义等价测试 |
| 17 Legacy/compat | 5,484 | 0 | 0 | legacy 链 3,209 仍被 ChatPanel 构造、旧 Task lane 2,426 已死 | 确认（旧 lane 现在可删，链等单 owner） | feature-on/off |
| 18 Test/reference in prod | 2,661 | 161 | 200 | 全部零生产 caller | 确认 | oracle 先迁后删 |
| **合计（不含 Native 文件）** | **173,740** | **25,254** | **≈50,400** | | | |

### 3.1 按机制分账

| 机制 | 涉及模块 | 削减量 | 确认程度 |
|---|---|---:|---|
| 死代码、legacy、生产树内测试代码 | 17、18 及各模块内死 symbol | ≈14K（另有共享宿主 AutoHarness 段 0.5K） | 已逐项验证（见同日可去掉性验证） |
| 通用 Task truth 转移到 AgentCore | 7、8、9、10、11 的通用部分 | ≈25K 离开 LiveVoice（约 5.3K 在 AgentCore 重写） | 通用性已由 AgentCore 零基线审计逐 symbol 确认；替换 gate 未过 |
| 观测三通道收敛与支持代码退休 | 15 | ≈10K | 确认 |
| schema 单源生成 | 16 | ≈5K（另可减少各模块手写校验，未量测） | 确认 |
| 并行 owner 与逐层重复校验的收敛 | 1–6、11–14 | ≈70K | 只确认方向：证据是 58 个 authority 类、三套 fence、四套 CAS ledger、三条 route lifecycle、三个 Task UI owner、每 27 行一个 `raise`；没有量测证明合并后恰好剩 37K |

第五项占削减的 57%，是计划里最没有实测支撑的部分。它成立的前提是两件事同时做：
一个 truth 一个 owner（合并 fence/ledger/journal/route lifecycle），以及闭合值的校验由
schema 生成而不是每层手写。只做第一件事，v1 更可能落在 60K 到 65K。

## 4. 为什么删掉这些不会伤 LiveVoice

- **死代码与 legacy**：删除对象没有生产 importer 或只被同样死亡的文件引用；仍有效的
  测试 oracle 先迁到 `tests/`、`scripts/`；legacy 链只有在 ChatPanel 只构造一套 owner
  并通过 feature-on/off 后才删。行为集合不变。
- **AgentCore 转移**：不是“删掉 Task 能力”，而是把 scope、Attempt/CAS、事务 outbox、
  cursor、execution lease/settlement、checkpoint publication、effect journal 这些 invariant
  搬到一个 owner；LiveVoice 现有 `test_persistent_task_core.py`（10,906 行）、
  `test_p3_4_durability_*`、`test_project_code_executor.py`（5,762 行）中的 race/restart/
  corruption 用例成为新 owner 的 adoption oracle；旧 Store 保留只读直到 canary 与
  rollback 演练通过。
- **观测与 schema**：观测收敛以隐私零泄露断言与 export 等价为 Gate；schema 单源以三套
  Python 家族与 TS 副本的字节/语义等价测试为 Gate；两者都不改变业务路径。
- **结构收敛**：只做行为保持的合并与搬迁，每个包前后测试集等价，加合成语音 journey
  （`scripts/live_voice/semantic_audio_*`）与物理 demo journey；一旦某个合并要改语义，
  按 root `TESTING.md` 重新定界定级，不在瘦身包里做。
- **与 Hermes 的差距是解释而不是目标**：v1 约 50K 到 65K 仍是 Hermes 25K 的 2 到 2.5 倍，
  差在 Batch+Streaming 双路径与 TEXT 降级、WebChannel 多宿主媒体协议、committed
  input 与确认/项目 scope 的产品策略、D1/D2 durability、DOM/audio/history 分面呈现证明。
  这些是 OpenJiuwen 要保留的合同，不是可删的重复。

## 5. 本文确认不了的

1. 第五种机制的幅度（约 70K）；只有在 B 期第一个合并包（例如三套 fence 合一或
   media registration 拆分）落地后才有第一份实测比例。
2. 各层手写校验有多少能由 schema 生成替代；本文只测了 `raise`/`throw` 密度，没有分类。
3. 模块归桶是文件名规则的粗分，与原子表的 symbol 级归属有出入；例如 `p3_authenticated_composition`
   整体记在模块 4，而原子表把它拆成三行。

## 6. 本文不授予什么

本文不改变任何计划数字，不宣告任何包开始或完成，不删除代码，不授予 AgentCore
接受或安装信用，不授权远端操作。它只把“为什么能瘦”落到每个模块的可指认证据上，
并诚实标出哪一部分仍是假设。

## 7. 增量（`7c7aad7b8`，2026-09-05 第二次 rebase）

用收进仓库的 `scripts/live_voice/slimming/module_buckets.py` 在新 tip 重跑，不含 Native 的
合计从 173,740 变为 **171,431**：模块 17 Legacy 5,484→3,058（旧 Task lane 2,426 行被分支自身
删除）、06 Agent bridge 3,168→3,015（口语修订策略撤除）、14 Composition 19,743→19,826、
05 Conversation Runtime 8,172→8,224、08 Task Store 15,109→15,175、09 Project executor
6,694→6,755、04 Committed input 16,840→16,850；其余模块不变。§3 表与 §3.1 分账的结论
不受影响：G1 削减量从约 14K 降到约 12K（已被分支自行完成 2.4K），第五种机制的约 69K
不变。
