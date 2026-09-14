# Live Voice / Host / SDK 生产代码量与实际复用

> 2026-09-14 当前工作树：配套 SDK `.7`。Work 编排由 `AgentRuntime → Runner.get_root_task_group → root.start_soon` 管理；WorkStore 的耐久事实仍为业务权威。独立 producer/cleanup 未结算时保留容量且不发布成功。TaskManager 注册管理及完整 Task/Work 融合仍未完成。
> 最新相同口径：Voice **112334**、Host **48028**、SDK **34056**，合计净增 **194418**；本批 **+70**（Host 适配 +13、SDK 所有权/结算增强 +57），累计较初始 **−1262**。后文各阶段数字为历史快照。[逐文件统计](../evidence/DEEP_WORK_NATIVE_OWNER_COUNTS_20260914.json)、[合并模块统计](../evidence/DEEP_WORK_NATIVE_OWNER_MODULES_20260914.json)。
> AgentServer 是宿主运行容器，持有应用服务并装配 Runner；不是另一个执行引擎。M4+M5、M7+M9 保持合并展示。外部 Hermes/多模态版本未重新核验，原静态证据边界不变；本批不证明性能优势。配套 wheel 安装后 12 项真实 Runner/SQLite 场景通过；1016 个 Host、2409 个 SDK Python 文件与当前源码逐字节一致。

> 2026-09-13。统计源码，不统计测试、文档、配置、二进制、依赖或构建产物。物理行包括注释和空行；这不是可执行语句数。

## 1. 历史提取阶段与本轮相同口径

官方兼容基线：JiuwenSwarm `8c7bfecdf0cc7607b07763fe687e08bf24f6ab83`；AgentCore `b5f189ba1054a338d8fa3e009b13053776340e44`。
“新增文件行数”只统计本分支引入文件的当前行数；“净增量”也包含原有文件的增加和删除。改过的整个上游文件不能算成新增代码。

| 阶段 | 分类 | 新增文件中的当前行数 | 相对官方基线净增量 | 所有受影响文件当前总行数 |
|---|---|---:|---:|---:|
| Task 统一后 | Voice 专属路径 | 113,424 | 113,424 | 113,424 |
| Task 统一后 | JiuwenSwarm 应用/共享 | 41,499 | 49,741 | 152,256 |
| Task 统一后 | AgentCore 新增 | 32,504 | 32,504 | 32,504 |
| Work 统一后 | Voice 专属路径 | 113,422 | 113,422 | 113,422 |
| Work 统一后 | JiuwenSwarm 应用/共享 | 40,235 | 48,477 | 150,992 |
| Work 统一后 | AgentCore 新增 | 33,781 | 33,781 | 33,781 |
| 本轮审计前 | Voice 专属路径 | 113,422 | 113,422 | 113,422 |
| 本轮审计前 | JiuwenSwarm 应用/共享 | 40,235 | 48,477 | 150,992 |
| 本轮审计前 | AgentCore 新增 | 33,781 | 33,781 | 33,781 |
| 本轮实施后 | Voice 专属路径 | 113,323 | 113,323 | 113,323 |
| 本轮实施后 | JiuwenSwarm 应用/共享 | 39,894 | 48,100 | 150,615 |
| 本轮实施后 | AgentCore 新增 | 33,812 | 33,872 | 34,017 |
| Work 宿主执行收敛 09-14 | Voice 专属路径 | 113,237 | 113,237 | 113,237 |
| Work 宿主执行收敛 09-14 | JiuwenSwarm 应用/共享 | 40,006 | 48,212 | 150,727 |
| Work 宿主执行收敛 09-14 | AgentCore 新增 | 33,812 | 33,872 | 34,017 |
| Registry 旧受理消重 09-14 | Voice 专属路径 | 113,111 | 113,111 | 113,111 |
| Registry 旧受理消重 09-14 | JiuwenSwarm 应用/共享 | 40,006 | 48,212 | 150,727 |
| Registry 旧受理消重 09-14 | AgentCore 新增 | 33,812 | 33,872 | 34,017 |
| 输入恢复修复 09-14 | Voice 专属路径 | 113,158 | 113,158 | 113,158 |
| 输入恢复修复 09-14 | JiuwenSwarm 应用/共享 | 40,116 | 48,322 | 150,837 |
| 输入恢复修复 09-14 | AgentCore 新增 | 33,812 | 33,872 | 34,017 |
| Host 模型目录消重 09-14 | Voice 专属路径 | 113,158 | 113,158 | 113,158 |
| Host 模型目录消重 09-14 | JiuwenSwarm 应用/共享 | 40,116 | 48,296 | 150,811 |
| Host 模型目录消重 09-14 | AgentCore 新增 | 33,812 | 33,872 | 34,017 |
| 前端宿主生命周期收敛 09-14 | Voice 专属路径 | 113,084 | 113,084 | 113,084 |
| 前端宿主生命周期收敛 09-14 | JiuwenSwarm 应用/共享 | 40,257 | 48,440 | 150,955 |
| 前端宿主生命周期收敛 09-14 | AgentCore 新增 | 33,812 | 33,872 | 34,017 |
| 项目受理历史消重 09-14 | Voice 专属路径 | 113,084 | 113,084 | 113,084 |
| 项目受理历史消重 09-14 | JiuwenSwarm 应用/共享 | 40,187 | 48,370 | 150,885 |
| 项目受理历史消重 09-14 | AgentCore 新增 | 33,812 | 33,872 | 34,017 |

本轮三部分净增量合计从 **195,680** 降至 **195,295**，减少 **385** 行：
Voice −99、Host −377、SDK +91。SDK 的 34,017 行受影响文件中包含既有
`agent_callback_manager.py` 的 145 行基线，不能把整个文件算成新增；该原生文件
本轮净增 60 行。新增文件行数和净增量因此不再相等。


Work 阶段相对 Task 阶段：Voice −2，JiuwenSwarm −1,264，AgentCore +1,277 行；三者合计净增 11 行。迁移、协议复用与应用依赖注入改变所有权，不意味着删除等量功能或总行数显著下降。

Voice 分类按专属目录/文件命名；公共 schema 和 `server/runtime` 归 JiuwenSwarm。它包含保留的 Native、Cascade、批量语音与诊断，不是只计算当前 Native 热路径。Host 适配中也有语音集成逻辑，因此该分法是可复现的文件所有权口径，不能解释成每行语义都完全通用。`live-voice/` 目录只有架构、验证与支持资料，没有该口径下的生产模块。

09-14 后续使用同一口径：合计 **195,321**，较首批增加26行，较审计前减少359行。
Voice净−86、Host净+112、SDK不变；这是删除Work对Voice协调运行时的依赖、
增加宿主薄适配和既有Harness结果收集的实际变化，不是等量搬迁或代码减量承诺。
Work状态/存储未复制；普通Voice委托的限时与播放行为未改。

随后 Registry 删除无生产写入的旧 P2 ledger、无调用的容量预留/预检及恒假分支，
生产净−126行（全部Voice）。该阶段合计 **195,195**，较审计前减少 **485** 行。
这是实际删除旧受理管理，没有搬迁或新增替代框架；统一journal仍负责当前输入。

随后恢复故障验证发现内存代次导致冻结输入无法跨 Registry 重建。现有 Host journal
新增独立服务端身份冻结和 P3/统一入口共用的持久序列，Voice 保留当前入口验证与
Agent 上下文投影适配。最新净增量合计 **195,352**，较审计前减少 **328** 行；
相对上一阶段 Voice +47、Host +110、SDK 不变。这157行是必要恢复增强与适配，
没有搬迁或删除重复生产实现的减量贡献，也不代表整套输入/会话能力已统一完成。
见[逐文件统计](../evidence/DEEP_INPUT_RECOVERY_20260914.json)与
[合并模块统计](../evidence/DEEP_INPUT_RECOVERY_MODULES_20260914.json)。

Host 模型目录消重后最新合计 **195,326**，较审计前减少 **354** 行：删除
AgentServer 中26行不可达的重复回退，由原有 `get_default_models()` 继续处理
格式兼容、环境变量和 AgentOS 条目。没有取消宿主回退或变更正式模型选择政策。
见[逐文件统计](../evidence/DEEP_HOST_CONFIG_20260914.json)和
[模块统计](../evidence/DEEP_HOST_CONFIG_MODULES_20260914.json)。

## 2. 最新实施后的合并模块统计

每个受影响生产文件按主要职责只归一组。AgentServer 是运行容器，不重复计数；云端模型代码不在仓库，不计数。横向公共层单列，避免把巨大共享文件硬塞给某个语音模块。

| 展示模块/归属组 | 新增文件当前行数 | 相对基线净增量 | 受影响文件当前总行数 |
|---|---:|---:|---:|
| 浏览器 M1+M2 | 45,137 | 45,995 | 70,839 |
| Gateway G | 18,155 | 19,538 | 38,373 |
| Realtime/语音适配 M3 | 14,427 | 14,427 | 14,427 |
| 会话与业务协调 M4+M5 | 38,320 | 38,320 | 38,320 |
| 工作管理 M6+M8 | 37,745 | 37,805 | 37,950 |
| Agent 与项目执行 M7+M9 | 12,829 | 16,917 | 50,937 |
| 公共契约、授权、配置、观测与 Host 装配 | 19,492 | 21,346 | 46,162 |

这些是文件粒度的职责分桶，不是逐函数测量。例如前端 Task UI 归浏览器，SDK file-effect/durability 归执行，SDK 状态和存储归工作管理；M3 同时包含保留的非 Native 语音适配。大型 Registry 主要归会话协调，实际同时承担装配。需要精确定位时查看逐文件清单，而不是把展示框大小理解为独立部署包大小。

## 3. 可复现证据

最新订阅管理收敛：Voice **112,334**、Host **48,015**、SDK **33,999**，
合计 **194,348**，较审计前 **195,680** 净减少 **1,332** 行。
本批 Host −356、SDK +228、Voice不变，合计净−128。Host 删除333行独立
消费者订阅类及分支装配；其中页校验、ACK水位与边界判断是保留后接入SDK的
模式算法，不能把333行都算作消除。SDK复用已有queue、状态快照、授权、
关闭意图和事件读取入口，补齐消费者分页模式及两处关闭竞争保护；没有新框架、
执行器或存储。应用ACK/投影适配继续保留。版本为SDK `.6` 与Host配套依赖。
[逐文件清单](../evidence/DEEP_CONSUMER_SUBSCRIPTION_20260914.json)与
[模块分桶](../evidence/DEEP_CONSUMER_SUBSCRIPTION_MODULES_20260914.json)为当前口径。

此前恢复订阅修复：Voice **112,334**、Host **48,371**、SDK **33,771**，
合计 **194,476**，较审计前 **195,680** 净减少 **1,204** 行。
本批 SDK 净增2行，按已有恢复事件契约选择前序 attempt 字段；未删除生产实现，
不算管理能力收敛。真实 SQLite 恢复/重开后订阅和旧 attempt 隔离验证通过。
[逐文件清单](../evidence/DEEP_RECOVERY_SUBSCRIPTION_20260914.json)与
[模块分桶](../evidence/DEEP_RECOVERY_SUBSCRIPTION_MODULES_20260914.json)记录该阶段。

此前共享校验收敛：Voice **112,334**、Host **48,371**、SDK **33,769**，
合计 **194,474**，较审计前 **195,680** 净减少 **1,206** 行。
本批 Voice−32、SDK−106、Host不变，合计−138。SDK删除四处文本/scope/profile
校验副本，由已有durability_identity的同一实现处理，保留领域错误适配；Voice
删除两份身份校验算法，直接调用已有Native契约，只保留错误转换。没有新模型、
状态或存储。新增共享参数/调用适配已计入净额，不能把删除行毛额当净减少。
这是实际消重，不是单纯迁移，也不代表Controller/Team任务机制已经全面统一。
[逐文件清单](../evidence/DEEP_VALIDATION_REUSE_20260914.json)及
[模块分桶](../evidence/DEEP_VALIDATION_REUSE_MODULES_20260914.json)记录该阶段。


此前 Work producer 管理收敛：Voice **112,366**、Host **48,371**、SDK **33,875**，
合计 **194,612**，较审计前 **195,680** 净减少 **1,068** 行。
本批 Voice−72、Host+70、SDK不变，合计仅−2。主体是将保留的分配算法交给
已有Host服务，并删除Voice持有的pool/lock别名；不能把Voice的72行减少算作
消除72行实现。实际新增责任是Host服务独立完成分配、代际检查和失败清理，
不新增存储、执行器或状态机。既有Task/Work全部管理能力的统一仍未完成。
[逐文件清单](../evidence/DEEP_WORK_OWNER_20260914.json)及
[模块分桶](../evidence/DEEP_WORK_OWNER_MODULES_20260914.json)记录该阶段。


此前 `.5` Task 原子读取收敛：Voice **112,438**、Host **48,301**、SDK **33,875**，
合计 **194,614**，较审计前 **195,680** 净减少 **1,066** 行。
本批 Host−69、SDK+3：删除宿主双读/三次收敛重试，增强现有 Store 快照读取并
共用其分页查询。没有新存储或任务状态；应用权限/能力投影保留。这个净增3行
不是新增功能仅3行，而是必要增强与删除重复分页实现后的差额；未把整个修改文件
计为新增。测试、文档及版本配置不计入。
[逐文件清单](../evidence/DEEP_TASK_SNAPSHOT_20260914.json)与
[模块分桶](../evidence/DEEP_TASK_SNAPSHOT_MODULES_20260914.json)记录该阶段。


此前效果交付消重后：Voice **112,438**、Host **48,370**、SDK **33,872**，
合计 **194,680**，较审计前 **195,680** 净减少 **1,000** 行。
本阶段−387行，全部为删除无人消费的上层effect领取/ACK管理；底层CR、通知、
实际播放确认及取消能力保留。不是迁移，没有新增替代框架，测试删除不计入。
[逐文件清单](../evidence/DEEP_EFFECT_CONVERGENCE_20260914.json)与
[模块分桶](../evidence/DEEP_EFFECT_CONVERGENCE_MODULES_20260914.json)记录该历史阶段。


此前准入账本收敛后合计 **195,067**，较审计前 **195,680** 减少 **613** 行。
Voice **112,825**、Host **48,370**、SDK **33,872**。本批生产净−259行：
删除旧独立调度/接管路径与重复准入账本−216行；Gateway直接调用BatchSpeech
已有授权摘要实现−43行。没有搬迁或新增替代框架；同一Future、协调任务与容量
边界由一份准入记录持有。测试及文档不计入。Task/Work管理层的全面原生复用
仍未证明，不因本次删除而变为完成。
见[逐文件清单](../evidence/DEEP_ADMISSION_CONVERGENCE_20260914.json)和
[模块分桶](../evidence/DEEP_ADMISSION_CONVERGENCE_MODULES_20260914.json)。
以下为历史阶段记录，不代表当前总量。


项目受理历史消重后最新合计 **195,326**，较审计前减少 **354** 行。本阶段仅Host
净−70行：删除D-120已停止调用的清洁度/受管基线检查及工厂分配，没有迁移或新增
执行框架。项目内容保护继续由现有Executor快照、冲突检查与写回负责。SDK公开的
旧只读基线证明API保留兼容能力，未从统计中扣除；它不再参与Host授权。见
[逐文件清单](../evidence/DEEP_PROJECT_AUTHORITY_20260914.json)与
[模块清单](../evidence/DEEP_PROJECT_AUTHORITY_MODULES_20260914.json)。

前端宿主生命周期收敛后最新合计 **195,396**，较审计前减少 **284** 行；相对模型
目录阶段 Voice −74、Host +144、SDK 不变，净增加70行。Host新增141行会话读取器
装配及原有ChatPanel净3行接入；Voice保留同步通知适配。读取、断线和轮询算法主体
移交宿主，不计为已消灭的重复算法；真正移除的是Voice独立生命周期入口和第二份
React任务快照。宿主store复用原有实现，没有新Task状态机/持久化/执行器。
验收证明无Voice消费者仍可读取、轮询及保留原RPC，而非以目录变化证明融合。
见[当前逐文件清单](../evidence/DEEP_FRONTEND_HOST_20260914.json)和
[当前模块分桶](../evidence/DEEP_FRONTEND_HOST_MODULES_20260914.json)。

- [Task 阶段逐文件清单](../evidence/TASK_UNIFIED_CODE_COUNTS_20260913.json)：Task 阶段已冻结。
- [Work 阶段逐文件清单](../evidence/WORK_UNIFIED_CODE_COUNTS_20260913.json)：包含每文件基线/当前、增删与 SHA-256。
- [Work 阶段模块分桶](../evidence/WORK_UNIFIED_MODULE_COUNTS_20260913.json)：每个文件唯一归属，可汇总回同一个总数。
- [所有权统计脚本](../../scripts/live_voice/code_ownership_counts.py)与[模块分桶脚本](../../scripts/live_voice/module_code_counts.py)。

```powershell
python scripts/live_voice/code_ownership_counts.py --stage work-unified --output live-voice/evidence/WORK_UNIFIED_CODE_COUNTS_20260913.json
python scripts/live_voice/module_code_counts.py live-voice/evidence/WORK_UNIFIED_CODE_COUNTS_20260913.json live-voice/evidence/WORK_UNIFIED_MODULE_COUNTS_20260913.json
```

## 4. 减量分类，不能把所有权变化当作消重

| 本轮边界 | 生产净变化 | 分类与保留内容 |
|---|---:|---|
| 旧 TaskCore/TaskIntent/map 和 AgentBridgePort 线程执行器 | −373 | 无生产消费者的历史实现退出生产；测试夹具迁至 tests/support，不能声称整个代码库删除了全部这些逻辑。AgentEvent 和正式 resolver 保留。 |
| 旧 SDK service carrier 与 Host 启停分支 | −47 | 删除不被生产读取的 service 协议/字段和冗余 scheduler lifecycle；历史载体仅用于测试。 |
| Voice Work fallback | −16 | 删除无宿主模式、无generation直接调用及独立close；唯一运行寿命为HostWorkService/AgentRuntime。 |
| 文字/语音会话配置复制 | −6 | 删除两处重复复制、复用既有newConversationLifecycle中的25行公共函数；非搬迁整个模块。 |
| Task原生checkpoint接口 | +57 | Host删除动态通道等净−46；SDK TaskRail适配+43、既有原生CallbackManager净+60。真正增强既有能力，保留Host实例/session身份读取。 |
| 合计 | **−385** | 以上为本轮相对起始提交变化，不是相对官方基线总量。 |

大量下沉代码仍然保留。[迁移来源逐项对照](../evidence/DEEP_INTEGRATION_ORIGINS_20260913.json)
按原始提交文件与当前SDK文件逐行精确匹配（`SequenceMatcher(autojunk=False)`）：
project_executor 当前6,209行中5,789行匹配原Host来源；Task Store当前13,898行中
13,140行匹配；PersistentTaskCore当前1,562行中1,497行匹配；WorkRuntime当前860行中
686行匹配。这是文本沿袭证据，不能解释为整份文件新增或逐行语义等价。

Controller/Team管理未被机械合入：它们缺少本应用要求的outbox/attempt/effect事务、
Work revision/CAS/UNKNOWN及取消实际结算保证。保留这些扩展的依据是具体语义，
不是名称或目录；实际复用、删除和未完成项见[代码级决策表](../reviews/DEEP_INTEGRATION_20260913.md)。

## 5. 本轮冻结证据

- [实施前](../evidence/DEEP_INTEGRATION_BEFORE_20260913.json)
- [实施后](../evidence/DEEP_INTEGRATION_AFTER_20260913.json)
- [当前模块分桶](../evidence/DEEP_INTEGRATION_MODULES_20260913.json)
- [09-14 Work宿主执行逐文件清单](../evidence/DEEP_WORK_HOST_20260914.json)
- [09-14 最新模块分桶](../evidence/DEEP_WORK_HOST_MODULES_20260914.json)
- [Registry消重后的逐文件清单](../evidence/DEEP_REGISTRY_20260914.json)
- [Registry消重后的最新模块分桶](../evidence/DEEP_REGISTRY_MODULES_20260914.json)

```powershell
.venv/Scripts/python.exe scripts/live_voice/code_ownership_counts.py --stage deep-integration-after --output live-voice/evidence/DEEP_INTEGRATION_AFTER_20260913.json
.venv/Scripts/python.exe scripts/live_voice/module_code_counts.py live-voice/evidence/DEEP_INTEGRATION_AFTER_20260913.json live-voice/evidence/DEEP_INTEGRATION_MODULES_20260913.json
```
