# Live Voice 当前状态

- 最后更新：2026-08-01
- 工作分支：`hx/0731_live_voice_ux`
- 远端跟踪：`agtai/hx/0731_live_voice_ux`
- 建立方案时的代码基线：`7b69fdeb`
- V0 核心实现提交：`346f802a`；当前已推送 V0 Candidate 恢复点：`2c700934aa0024a7ab229644bf15934e9e8170e7`
- 当前里程碑：不可变 V0 Vertical Slice Candidate + Post-V0 Task Foundation 收尾
- 实现状态：真实“麦克风 → Agent → Terminal Tool → 完整回答 → 浏览器 TTS → 自动回听”主链已在固定 Windows/Chrome 环境成功跑通一次；[V0_ACCEPTANCE.md](V0_ACCEPTANCE.md) 已定义完整 Gate，但稳定性、分阶段打断和跨环境放行尚未执行完

跨机器恢复先读 [HANDOFF.md](HANDOFF.md)；启动和固定环境按 [E2E_RUNBOOK.md](E2E_RUNBOOK.md) 执行；V0 是否放行以 [V0_ACCEPTANCE.md](V0_ACCEPTANCE.md) 为准。

当前开发遵循 D-030 与 [POST_V0_DELIVERY_ROADMAP.md](POST_V0_DELIVERY_ROADMAP.md)：`2c700934aa0024a7ab229644bf15934e9e8170e7` 固定为未放行 V0 Candidate；stash `7f4cfd2eedfb3a177b94f69417143fba441f3671` 已 apply 且只保留为备份。Post-V0 foundation 恢复正常的 review → commit → push 流程；稍后从 `2c700934` 的独立 checkout/worktree 执行 V0 Gate，不再反复 stash 当前开发分支。

对 **`2c700934` V0 Candidate baseline** 的量化判断仍是：代码实现约 **97%**，整体 Demo 约 **90%**，上台成熟度约 **78%**。这些数字来自 V0 的真实麦克风/Agent/Tool/TTS 首次贯通和当时的 47 项 Live Voice 自动化，不包含后续 Post-V0 foundation。连续 10 Turn、分阶段 10 次打断、soak 和连续 3 次主演示尚未完成，因此 V0 仍不能称为已放行；Post-V0 的完成度也不能用 V0 的百分比替代。

## 当前结论

核心产品命题已从“代码路径推断可行”推进到“固定真机上实际成立”：用户说出“调用终端查看当前分支”，Chrome 产生完整 final，新会话 promotion 没有让 Live Voice 退出，Agent 真实调用 `git branch --show-current`，工具返回 `hx/0731_live_voice_ux`，完整回答从 Jabra 耳机朗读，随后自动回到 Listening。用户确认斜杠、数字和下划线组成的分支名也完整听到。

这次成功证明了受控 Demo 的主链和感知效果，但只是一次主链证据，不等于稳定性放行。之后又成功进入两轮回听，说明循环可以继续；同时 Web Speech 把 `git` 识别为“地图”或“史记”，暴露出中文技术词准确率风险。真实 supplement 打断、speaking 本地停声、工具副作用隔离和长时运行仍需专项验证。

已接受新的累计路线：不另建覆盖全部功能的模拟 UX 原型；Post-V0 两周让 P1/P2/P3、Context、Progress、Failure/Degradation、Observability 等能力类别都有真实纵向路径或明确标注的替代。版本命名修正为 V1 Foundation Alpha、V2 Realtime Alpha、V3α Task Alpha、V3 Full Capability Beta，最后进入 RC/Production hardening。详细见 `DECISIONS.md` 的 D-018、D-020 和 D-021。

## 本轮实现与修复

### 语音识别和 Turn 生命周期

- 修复 `new` session promotion 分两次 React 渲染到达时，promotion signal 被提前消费并导致 Live Voice 退出的问题。
- 用户消息本地 echo 早于 `processing=true` 时，不再误判为“无可朗读回答”并提前重新开麦。
- 将一个用户 capture 与单个浏览器 SpeechRecognition 实例解耦：Chrome 约 4 秒自然结束时可在同一逻辑 capture 内续启，final/interim 尾段合并后只提交一次。
- 区分 8 秒初始静默窗口和有结果后的 2.2 秒结束语音窗口；浏览器初始 `no-speech` 可在阈值内重试，手动停止或终止错误不会被错误重启。
- 修复 manual stop 与自动 retry 的竞态，旧识别实例和迟到回调继续受 generation 隔离。

### 回答朗读

- 完整 assistant 消息不再被普通 TTS 的 500 字默认上限静默截断；Live Voice 先完整清洗，再以约 220–300 字按中英文句末优先分片，超长句硬切并保持 FIFO。
- 显示文本保持不变，只修改朗读副本：路径、分支、下划线、斜杠、缩写和连续字母数字转换成 `zh-CN` 系统音色可稳定读出的形式。
- 分片 key 使用 `${message.id}:${chunkIndex}`，继续复用现有 `responseEpoch`；打断、退出或新 Turn 会使整条旧队列和迟到回调失效。
- Live Voice 启用时取得进程内 TTS 所有权；旧的服务端 `tts.synthesize` 路径在请求前和音频返回后都检查 ownership revision，历史消息手动朗读也在播放前检查 owner；启用瞬间的全局 stop 会终止已有浏览器或生成音频。

### supplement 隔离

- ACK 前 quarantine 现在除旧 delta/final/reasoning/media 外，也隔离旧 `chat.tool_call` 和 `chat.tool_update`。
- 旧流关闭产生的短暂 `processing=false` 会在 barrier 内暂存，避免替代回答尚未开始时 Live Voice 提前结束 Turn；请求失败时会恢复被暂存的停止边缘。
- Gateway 不再静默吞掉 Agent cancel 异常，会记录可诊断 warning 后继续 replacement。

这些仍是 Demo 级本地防线。Gateway 的 supplement ACK 目前早于 AgentServer cancel 和 replacement 入队完成，真实工具副作用也没有 generation fence；前端隔离不能证明旧副作用已取消。

### 当前 Post-V0 foundation

- 新增最小 Live Voice contract/conformance schema，自动拒绝非法 identity、cancel scope、未 committed 的副作用意图、无来源进度和缺少 terminal outcome 的事件；它是后续 P1/P2/P3 共用测试地基，不代表正式协议已经全部接线。
- WebChannel 对全部 schedule/issue 方法采用单一 AgentServer 转发所有权，不再由本地 handler 抢先返回 `unknown method`；AutoHarness 的 run/cancel/delete 状态和同任务竞态也按真实 store 状态收敛。
- 新增保守稳定句预读：只消费 chatStore 中唯一、追加式的 assistant stream，以权威 `chat.final` 标记做 final suffix 对账。`VITE_FEATURE_LIVE_VOICE_STREAMING_SPEECH` 只有精确设置为 `true` 才启用，默认关闭，因而 Post-V0 代码存在时也不会静默改变 V0 默认行为。
- processing 已停止、临时朗读已 drain、同 epoch 权威 final 仍缺失时，稳定句路径只启动一次 10 秒 grace period；到期废弃该 epoch 并显示 Retry，不把 provisional 当 final、不补造或重播文本。final/mismatch、processing 恢复、capture/Session/退出生命周期都会隔离旧 timer。
- 新增受限 Voice–Task Bridge、Web request client 和真实任务卡。`VITE_FEATURE_LIVE_VOICE_TASK_DEMO` 默认关闭；开启后，面板会在用户说任何任务口令前常驻披露 AutoHarness、固定 `extended_evolve_pipeline`、代码副作用和取消边界，并显示真实 task ID、command ID、状态、恢复来源、target/provenance 和冲突信息。
- 任务只接受 committed final 的受控中文语法；启动、取消和替换必须显式确认。启动/替换目标允许 `：`、`:`、`，`、`,`、空格或口述“冒号”作为分隔符，并容忍句末标点。普通语音不被拦截，继续进入真实 Chat/Agent。
- 任务 capture 记录开始时的 session；final 到达前若 session 已切换，本次副作用命令被拒绝。`new` 或空 session 也不发任务请求。界面只展示真实 `task_id`、后端原始状态和来源，不生成假状态。
- 每次 committed create/replace mutation 只生成一个稳定 command ID；首次 `schedule.run` 结果不明时先按 owner/namespace/exact key 执行严格 `schedule.list` 对账，必要时只用**同一个 key**重放。只有 task ID、query、pipeline、namespace、key 和 execution target 全部一致且结果唯一时才恢复真实任务；冲突、多个结果或仍不可证明时继续 fail closed，不会用新 key 盲目创建。
- exact-key 对账不假设任务仍停在 `pending`：请求往返期间即使后端已进入 `running/success/failed/cancelled`，前端仍保留并显示该真实状态；这解决 pending drift，不把旧 pending 快照覆盖后端真值。
- 当前 command ID 只保证同一次 Bridge mutation 及其同-key retry/reconciliation 稳定，不是跨刷新持久 command journal。`lastVisibleTask`、未决 mutation 和任务卡投影仍是当前页面/Session 内存；刷新、切 Session 后还没有持续 monitor 或通用多任务恢复。
- schedule 执行已经改为每任务固定独立的进程内 Agent/context，不再在执行时借用 singleton 可变 `_agent`；并发 Session 分离，周期任务保留自己的 context，一次性终态、取消、删除和 service stop 会释放。进程重启后缺少旧 context 的任务会诚实失败，不借用新 Agent。
- 任务持久化并返回 `execution_target`：`project_dir`、`project_id`、`origin_session_id`、`origin_channel_id`。前端只接受当前 persisted Session 对应的可信绝对项目路径；capture 期间 session/target/bridge 任一变化都会零请求失效，UI 显示真实 target/provenance，遗留字段显示 unknown。
- 后端 `schedule.run` 已支持由服务端派生 owner scope 约束的 `origin_namespace` + `idempotency_key`。同一进程内、同一 JSON store 路径的 TaskStore 实例共享锁与持久 `create_commands` ledger/intent fingerprint：同意图重放返回同一 ID 且只触发一次，冲突返回 `IDEMPOTENCY_CONFLICT`，删除保留 tombstone，JSON reload 后仍可恢复。这是 **per-path single-process** 保证，不是跨进程事务或 exactly-once。
- `schedule.list/status/cancel/logs/delete` 均由服务端从可信 request 派生 owner scope 和 project execution target 后校验；外部请求缺失、无效或不匹配时 fail closed，不能靠客户端伪造 scope 读取、取消或删除另一来源任务。显式内部兼容路径不等于对外放宽授权。

## 验证记录

### `2c700934` V0 baseline 自动化

| 日期 | 验证 | 结果 |
|---|---|---|
| 2026-08-01 | Live Voice 纯逻辑 | **47/47 通过**：core 9、turn lifecycle 6、TTS text/chunking 10、message gate 7、supplement quarantine 6、speech lifecycle 7、TTS ownership 2 |
| 2026-08-01 | 相关既有回归 | **22/22 通过**：stream delta 7、session creation 8、chat store/settle 7 |
| 2026-08-01 | 全前端 TypeScript | `tsc --noEmit` 通过 |
| 2026-08-01 | Vite production build | 通过，**4490 modules** |
| 2026-08-01 | Python 与工作树检查 | `ruff`、`git diff --check` 通过 |

上表是稍后从独立 checkout/worktree 验收的 V0 baseline 历史结果，不能冒充当前 Post-V0 foundation 的验证结果。

### 当前 Post-V0 foundation 自动化和构建

| 验证 | 本轮最终实跑结果 |
|---|---|
| Live Voice 前端精确测试 | **155/155 通过**：覆盖 V0 core/lifecycle/TTS/gate/quarantine、streaming speech、task bridge/client/adapter 与 foundation reconciliation |
| chatStore marker 与相关前端回归 | **24/24 通过**：authoritative-final marker 3、historical settle 6、stream delta 7、session creation 8 |
| 全前端 TypeScript | `tsc --noEmit` 通过 |
| Vite production build | 通过，**4494 modules transformed**；仅有 caniuse 数据过期和大 chunk 警告 |
| Python 统一精确回归 | **226/226 通过**：contract、schedule TaskStore/service、AgentServer request、Web handler |
| 工作树检查 | foundation 合并点的 `git diff --check` 已通过；精确历史与基线 lint 说明见 stash 交接单 |

以上 **226/226、155/155、24/24、TypeScript 和 4494 modules** 是 foundation review 修复合入后的最终统一结果，不是子任务数字相加。后端 `3da101cf`、前端 `42e76d30` 已落地；精确历史和边界见 [POST_V0_STASH_HANDOFF.md](POST_V0_STASH_HANDOFF.md)。自动化结果仍不能替代稳定句听感和真实有副作用任务 E2E。

### 固定环境真实 E2E

- 环境：Windows、Chrome `150.0.7871.187`、Jabra EVOLVE 30 II、`zh-CN`、Node.js `24.14.0`、Python `3.12.9`、模型标签 `deepseek-v4-flash`。
- 本轮 Python 临时复用主仓现有 `.venv`；这是本机便利措施，不是跨机器恢复方案。新机器仍必须按 `uv.lock` 创建自己的 `.venv`。
- 文字强制工具 smoke 成功，证明模型、项目注册、Agent 和 Terminal Tool 可用。
- 真实麦克风完整识别“调用终端查看当前分支”，final 只进入一个逻辑 Turn；`new` session promotion 后 Live Voice 保持激活。
- 本轮计时证据：`T+1.050s` 进入 Agent working；真实工具执行 `git branch --show-current` 并返回 `hx/0731_live_voice_ux`；`T+7.420s` Agent 完成；`T+8.922s` 进入 TTS；`T+17.215s` 完整朗读结束并回到 Listening。
- 用户确认完整听到技术标识符中的斜杠、数字和下划线。
- 初始静默测试的 UI 轮询从点击 Retry 后计时，而不是从 Recognition `onstart` 精确计时；`T+7.293s` 仍为 Listening，`T+7.816s` 进入可见 `no-speech`，与约 8 秒的配置窗口一致，也没有被 Chrome 更早的自然结束误伤。
- 自动回听又接收了 2 个 follow-up，证明循环继续；但 Web Speech 把 `git` 误识别为“地图”或“史记”，尚不能据此记为 3 个准确语音 Turn。

## 尚未完成与不能宣称的内容

- 尚未完成连续 10 个准确语音 Turn、分阶段 10 次用户可感知打断、20 分钟或 20 Turn 稳定性，以及主演示脚本连续成功 3 次。
- 10 次打断必须拆分：thinking 3 次和 tool 4 次验证真实 `supplement`；speaking 3 次验证立即停声后普通 `chat.send`。当前没有任何一组可以写成已通过，也不能把 speaking 样本计入 supplement。
- 尚未测量并通过 speaking 本地静音目标 `<300ms` 和全部样本旧声音恢复 0 次；本轮主链没有证明真实 supplement 的 cancel/replacement 顺序可靠。
- supplement P1 协议风险仍在：ACK 早于 AgentServer cancel/replacement 完成；`chat.tool_result` 和真实工具副作用缺少 generation ID，前端不能可靠 fence。
- Web Speech 对中文句子中的英文技术词准确率不稳定，需要继续真机测试口令、说法和必要的 Provider fallback。
- Desktop/WebView2、Team、多语言、全双工/AEC、断线恢复和服务端 streaming TTS 未验证，也不属于本轮已经完成的能力。
- 当前固定演示环境可用不等于跨环境兼容；模型、Chrome Speech 服务、麦克风权限和网络仍是机器私有条件。
- 稳定句预读还没有服务端 response/generation ID；并发 cron/proactive 响应或迟到旧 `chat.final` 仍可能被归到错误 Turn。10 秒 timeout 只避免永久 thinking，不能证明响应归属或恢复 provisional 文本。
- 当前 FIFO 只能证明文本已规划或已入队，不能证明用户实际听到；正式版仍需 playback ACK/cursor 和 presented history。
- schedule 的本轮修复解决了同一进程、同一 JSON store 路径内的主要 run/cancel/delete 竞态与幂等创建，但没有跨进程事务、唯一执行所有权、exactly-once 或生产级 crash recovery。多个进程共享同一 store、D1/D2 durability 和外部副作用 reconciliation 仍是正式版风险。
- Task Demo 使用真实且有副作用的 AutoHarness。Live Voice 的打断、退出或 session 切换不会自动取消已经发出的 `schedule.run`，确认取消也不能撤销已经产生的代码修改。
- task-scoped Agent/context 和 project/origin provenance 已解决“并发任务借用最后一个 `_agent`”及目标猜测问题，但 context 仍只在进程内；重启不能恢复旧 Agent，持久 target 也不包含完整 model/provider/config/permission 快照。
- owner + project scope、稳定 command ID、同-key retry 与严格 exact-key reconciliation 已经补齐 foundation 门槛，但它们不构成跨进程 CAS、唯一执行 owner、crash transaction、exactly-once、D1/D2 或外部副作用 reconciliation。
- 前台目前仍会把任务反馈作为当前语音交互的一次结果处理；还没有“派发后立即继续监听、后台独立轮询、终态异步回流”的 task monitor。刷新恢复、多个任务、主动事件推送、重放/unread 和通用 Task Control 也未完成。

## 下一步

1. 下一实现切片按 D-031 建立 **poll-backed 异步任务监控**：任务派发后前台立即恢复 Live Voice，任务状态在独立投影中轮询更新，终态结果异步回流到真实 task card；安全空档最多播报一次简短终态，绝不抢占麦克风或 Agent TTS。
2. 该切片保持窄范围：不把 task 状态写进 chatStore，不伪造 chat processing，不做完整 TaskEvent push/replay、通用多任务 NLU、跨进程 exactly-once 或 D1/D2。
3. 用户稍后验收 V0 时，从 `2c700934` 新建独立 checkout/worktree，清除 Post-V0 flags 并执行 [V0_ACCEPTANCE.md](V0_ACCEPTANCE.md)；当前开发分支和 stash 备份不参与这次隔离。
4. 随后按 [POST_V0_DELIVERY_ROADMAP.md](POST_V0_DELIVERY_ROADMAP.md) 推进 response/generation lifecycle、P1 Speech Port、P2 Realtime、P3α/完整 P3，最后进入 RC。

## 接手者注意事项

- 开始工作前执行 `git status --short --branch`，确认位于 `hx/0731_live_voice_ux`，并区分本轮已知修改与意外文件。
- 真实环境、服务拓扑、无密钥配置和时序证据见 [E2E_RUNBOOK.md](E2E_RUNBOOK.md)。
- partial/interim transcript 绝不能触发 Agent、Tool 或 Task；浏览器重启只能延续同一个逻辑 capture。
- 插话或退出必须先本地停播；不要把 ACK quarantine、TTS ownership 或本地 epoch 描述成生产一致性协议。
- processing 中 final 才是 supplement；只剩 TTS 时是停声后的普通下一 Turn，不得混用验收计数。
- 真实主链已通过一次，但完整放行闸门未通过；只能称为 V0 Candidate，不得写成“Live Voice Demo 已完成/已冻结”。
