# Live Voice 跨机器交接快照

- 快照日期：2026-08-02
- 开发分支：`hx/0731_live_voice_ux`
- 共享远端：`agtai`（`https://github.com/agtai/jiuwenswarm.git`）
- V0 核心实现提交：`346f802a`；当前已推送 V0 Candidate 恢复点：`2c700934aa0024a7ab229644bf15934e9e8170e7`
- 权威 V0 恢复点：`2c700934`；它永久保持未放行 Candidate，不随 Post-V0 累计提交移动
- 当前阶段：V0 Candidate 已提交并推送，但完整真机 Gate 尚未通过，因此还不是 V0 Released / 已冻结
- stash 状态：`7f4cfd2eedfb3a177b94f69417143fba441f3671` 已 apply，原 stash 只作为额外备份保留；当前分支不要重复 apply/pop/drop
- 当前状态：Task Foundation 代码和历史回归已落地（后端 `3da101cf`、前端 `42e76d30`）；D-032 模块测试闭环 Gate 已接受，D-031 必须先完成开发前场景/test 回顾再编码。V0 继续从 `2c700934` 的独立 detached checkout/worktree 验收

## 接手后先做什么

1. `git fetch agtai`，切换并更新 `hx/0731_live_voice_ux`。
2. 依次阅读 [README.md](README.md)、本文件、[STATUS.md](STATUS.md)、[TWO_WEEK_DEMO.md](TWO_WEEK_DEMO.md)、[POST_V0_DELIVERY_ROADMAP.md](POST_V0_DELIVERY_ROADMAP.md)、[POST_V0_STASH_HANDOFF.md](POST_V0_STASH_HANDOFF.md)、[V0_ACCEPTANCE.md](V0_ACCEPTANCE.md) 和 [DECISIONS.md](DECISIONS.md)；开发模块前必须执行 D-032 与路线 §3.1。
3. 准备演示机时严格执行 [E2E_RUNBOOK.md](E2E_RUNBOOK.md)，新机器必须从 lockfile 重建依赖，不复制 `.venv` 或 `node_modules`。
4. 核对 `git status --short --branch`、HEAD 和 upstream。D-030 已恢复正常 commit/push：不要为了验收 V0 把当前开发分支重新 stash，也不要重复 apply `7f4c...`。需要 V0 Gate 时，从精确 SHA `2c700934...` 创建独立 checkout/worktree，避免把 V0 证据与 Post-V0 混在同一运行目录。

本目录是 Git 中的接续入口。不要依赖旧对话、未提交文件、某台机器的 `.codex` / `.agent` 目录或本机 stash 恢复项目事实。Task Foundation 已随代码正常 commit，并由本批 push 进入共享分支；新机器只需 fetch/pull 分支并按本文阅读顺序接续。

## `2c700934` V0 baseline 已经能做什么

- Live Voice 只在 Agent 模式开放；final transcript 在 Agent processing 时复用真实 `supplement`，空闲或只剩 TTS 时复用普通 `chat.send`，interim 只有显示副作用。
- Web Speech 的浏览器实例自然结束不会直接结束用户 Turn；约 4 秒早退可以在同一逻辑 capture 中续启并合并尾段，手动停止不会被 retry 复活。
- 初始静默窗口固定 8 秒，有识别结果后的结束语音窗口为 2.2 秒。
- `new` session promotion 分两次渲染时会保留 Live Voice；普通 session 切换仍退出并清理。
- 用户 echo 先于 `processing=true` 到达时，不会提前重新开麦。
- 完整 assistant 回答经过无 500 字截断的 Live Voice 清洗后，以约 220–300 字分片进入 TTS FIFO。
- 朗读副本会把路径、分支、斜杠、下划线、缩写和字母数字转换为可听形式，聊天页面显示文本不变。
- 每个分片用 `${message.id}:${chunkIndex}` 去重，并受同一 `responseEpoch` 控制；打断、退出和新 Turn 会让旧队列失效。
- Live Voice 拥有浏览器 TTS 时，进程内 owner/revision 会阻止旧服务端音频与之双播；历史消息手动朗读也会在播放前检查 owner。
- supplement ACK 前隔离旧 delta/final/reasoning/media/tool_call/tool_update，并暂存旧流的 `processing=false` 停止边缘。

以上是已经推送、稍后从独立 checkout/worktree 验收的 V0 Candidate 能力，不包含 Post-V0 foundation。

## 当前 Post-V0 Task Foundation

- 最小 contract/conformance schema 已落地；Web schedule/issue 请求已改为单一 AgentServer 响应所有权，AutoHarness run/cancel/delete 的单进程竞态和状态真实性已加强。
- `VITE_FEATURE_LIVE_VOICE_STREAMING_SPEECH` 默认关闭。开启后，稳定句预读只消费 chatStore 的唯一追加式 assistant stream，并等待权威 `chat.final` 做 suffix 对账；processing 停止、队列 drain 后仍缺 final 会在 10 秒 grace period 到期时废弃 epoch 并显示 Retry，不把 provisional 当 final。它不是 token/audio streaming TTS。
- `VITE_FEATURE_LIVE_VOICE_TASK_DEMO` 默认关闭。开启后，Live Voice 面板会**常驻预披露**：执行器是 AutoHarness，固定 `extended_evolve_pipeline`，会生成或修改本地 Harness 代码包；Live Voice 打断/退出不等于取消任务，取消也不能撤销已产生修改。
- Task Bridge 只拦截 committed final 的受控语法。启动、取消和替换必须带“确认”；创建/替换目标支持 `：`、`:`、`，`、`,`、空格和口述“冒号”等有限分隔符，也容忍句末标点。普通语音继续走真实 Chat/Agent。
- 当前精确任务口令是：`确认启动后台演进任务<分隔符><目标>`、`检查后台任务进度` / `检查后台演进任务进度`、`确认取消后台演进任务`、`确认替换后台演进任务<分隔符><目标>`。省略“确认”的启动/取消/替换形式只返回确认提示，不发 mutation；`检查进度` 等宽泛说法不被任务桥拦截。
- task capture 从开始到 final 必须保持同一个 persisted session；session 切换、空 session 或 `new` session 都不会发副作用请求。
- UI 使用真实任务卡显示后端返回的 `task_id`、command ID、原始状态、恢复来源、target/provenance 和冲突信息。A→B 是先确认取消 A，再创建不同 ID 的 successor B，不伪装原地更新。
- 每次 committed create/replace 固定一个 command ID。首次 run 结果不明时，Bridge 先使用相同 owner/namespace/exact key 查询 `schedule.list`，必要时只以同一个 key 重放；只接受唯一且 task ID、query、pipeline、namespace、key、target 全部匹配的记录。
- exact-key reconciliation 接受请求期间发生的真实状态漂移；任务已从 pending 进入 running 或 terminal 时不会被旧 pending 假设覆盖。冲突、多条记录或无法证明时继续 fail closed。
- command ID 目前只在同一次 Bridge mutation/retry/reconcile 内稳定；`lastVisibleTask`、未决 mutation 和任务卡投影仍是页面/Session 内存。刷新后没有持久 command journal、连续 monitor 或通用多任务恢复。
- Scheduler 已改为每任务固定独立的进程内 Agent/context；并发 Session 不再借用最后写入的共享 `_agent`，周期任务保留自己的 context，终态/取消/删除/service stop 释放。进程重启后缺 context 的旧任务会诚实失败，不借用新 Agent。
- task request、持久状态和 UI 已携带/显示 `execution_target`：项目路径、项目 ID、来源 Session、来源 Channel。前端仅允许当前 persisted Session 对应的可信绝对项目路径；capture 期间 session/target/bridge identity 改变时零请求失效，遗留任务缺字段则显示 unknown。
- 后端创建支持服务端 owner scope 下的 `origin_namespace` + `idempotency_key`：同一进程、同一 JSON store 路径的 TaskStore 实例共享锁和 ledger；同意图返回同一 task ID 且只触发一次，冲突返回 `IDEMPOTENCY_CONFLICT`，删除保留 tombstone，reload 后可重放。这是 per-path single-process，不是跨进程或 exactly-once。
- `schedule.list/status/cancel/logs/delete` 都在服务端按可信 request 派生 owner + project execution target 并在读取、取消、删除或释放 context 前校验；外部缺失、无效或不匹配 scope fail closed。

## 2026-08-01 已完成的验证

### `2c700934` V0 baseline 自动化

- Live Voice 纯逻辑：**47/47**（core 9、turn lifecycle 6、TTS 10、message gate 7、quarantine 6、speech lifecycle 7、TTS owner 2）。
- 相关既有回归：**22/22**（stream delta 7、session creation 8、chat store/settle 7）。
- 全前端 TypeScript、Vite production build（4490 modules）、Python `ruff` 和 `git diff --check` 通过。

上述 47/47、22/22 和 4490 modules 是 V0 baseline 的历史验收前记录。

### 当前 Post-V0 foundation 自动化

- Live Voice 前端精确测试：**155/155**，覆盖 V0 core/lifecycle/TTS、稳定句与 Task Foundation。
- chatStore authoritative-final marker 与相关回归：**24/24**（marker 3、historical settle 6、stream delta 7、session creation 8）。
- 全前端 `tsc --noEmit` 通过；Vite production build 通过，**4494 modules transformed**，只有 caniuse 数据过期和大 chunk 警告。
- Python 最终统一精确回归：**226/226 passed**，覆盖 contract、TaskStore/service、AgentServer schedule request 和 Web handler。
- foundation 合并点的 `git diff --check` 已通过；历史 lint 说明见 [POST_V0_STASH_HANDOFF.md](POST_V0_STASH_HANDOFF.md)。

以上 **226/226、155/155、24/24、TypeScript 和 4494 modules** 是 review 修复合入后的最终统一结果，不是子任务数字相加；后端 `3da101cf`、前端 `42e76d30` 已落地。自动化结果仍不能替代稳定句听感和真实有副作用任务 E2E。

### D-032 模块测试闭环摘要

- Foundation 的上述数字是由交接提交 `01df6de0` 记录、对应包含后端 `3da101cf` 与前端 `42e76d30` 的最终代码树的历史回归证据；当时没有保存 D-032 要求的开发前/开发后双回顾和完整 `scenario → test/evidence` 映射，不能仅凭数量追认模块已经按 D-032 `CLOSED`。
- D-031 是首个强制应用切片：开发前在 [STATUS.md](STATUS.md) 建立 module definition、test inventory、每项 test 的 why 与完整场景矩阵；开发后绑定 exact tested SHA 复审、复跑并记录 gap。详细规则只见 [POST_V0_DELIVERY_ROADMAP.md](POST_V0_DELIVERY_ROADMAP.md) §3.1。
- HANDOFF 以后只保留 closure 状态、tested SHA 和 STATUS 证据入口，不复制详细 inventory。缺少正例、反例零副作用、竞态/恢复/隔离、flag-off 或必要真实接线证据时，只能写 `PARTIAL`/`BLOCKED`。

### 真实固定环境

- Windows；Chrome `150.0.7871.187`；Jabra EVOLVE 30 II；`zh-CN`；Node.js `24.14.0`；Python `3.12.9`；模型标签 `deepseek-v4-flash`。
- Python 本轮临时复用主仓现有 `.venv`；这是本机临时措施，不是恢复规范。
- 文字强制 Terminal Tool smoke 成功。
- 麦克风完整识别“调用终端查看当前分支”；新会话 promotion 保持 Live Voice。
- `T+1.050s` Agent working；真实调用 `git branch --show-current`，结果为 `hx/0731_live_voice_ux`；`T+7.420s` Agent 完成；`T+8.922s` 开始 TTS；`T+17.215s` 完整朗读结束并回 Listening。
- 用户确认完整听到分支名中的斜杠、数字和下划线。
- 静默测试的 UI 轮询从点击 Retry 后计时；`T+7.293s` 仍为 Listening，`T+7.816s` 显示 `no-speech`，与约 8 秒的配置窗口一致。
- 自动回听又接收了 2 个 follow-up，但 `git` 被识别成“地图”或“史记”，只能证明循环继续，不能计为准确率验收通过。

详细非敏感证据和启动方式见 [E2E_RUNBOOK.md](E2E_RUNBOOK.md)。

## 仍未完成：当前唯一主线

- 10 个准确语音 Turn，重复提交为 0。
- 10 次用户可感知打断：thinking 3 次、tool 4 次必须走真实 supplement；speaking 3 次必须立即停声并恰好走一次普通 `chat.send`。三类分别记数，旧声音恢复 0 次，并检查旧工具 UI、迟到 result、warning 和副作用。
- 连续 20 分钟或 20 Turn 无需刷新。
- 主演示脚本连续成功 3 次。
- 在独立环境从 `uv.lock` / `package-lock.json` 重建并复测，不依赖主仓 `.venv`。

任何一项未通过，都不能写成“Demo 已完成”。当前真实主链成功一次是关键进展，但不是放行替代品。

## 量化进度口径

| 维度 | 完成度 | 含义 |
|---|---:|---|
| 代码实现 | 约 97% | 主链、识别生命周期、分片朗读、TTS 单一所有权、Demo 隔离和自动化基本完成 |
| 整体 Demo | 约 90% | 真实 Speech → Agent → Tool → Speech 已成功一次，重复性与打断闸门未完成 |
| 上台成熟度 | 约 78% | 固定环境和首条时序证据已建立，仍缺 10 Turn、10 次打断、soak 和连续彩排 |

这些数字是项目判断，不是测试覆盖率；后续真实失败必须如实下调。

## 当前最重要的已知风险

### Web Speech 技术词准确率

中文句子中的 `git` 在连续回听中被误识别为“地图”或“史记”。主链没有断，但请求语义会偏移。先用固定口令和真机样本量化；若仍不稳定，再按既有 Day 1/Day 2 闸门评估单一 Speech Provider fallback。

### supplement 仍不是端到端 fence

前端现在可以隐藏更多旧 UI 事件并保持 processing 状态，但 Gateway 的 supplement ACK 仍早于 AgentServer cancel/replacement 完成。`chat.tool_result` 与真实工具副作用没有 generation ID，旧副作用无法由前端可靠撤销或归属。真实 10 次打断必须专项观察，不能把 ACK 解释成“旧 Agent 和工具已确定停止”。

### speaking 打断不是 supplement

当前回答只有在 Agent 完成后才进入浏览器 TTS。因此 speaking 时重新开麦会立即停止本地声音，但新 final 通常发生在 `processing=false`，实际是普通 `chat.send`。它能验证“停声并修改下一轮”，不能证明服务端 Agent cancel。验收必须按 [V0_ACCEPTANCE.md](V0_ACCEPTANCE.md) 分开记录。

### 固定环境仍有机器私有状态

模型配置、浏览器权限、Chrome Speech 服务、硬件和网络不会进入 Git。本轮复用主仓 `.venv` 也只是临时便利；跨机器必须按运行手册重建并重新验收。

### Post-V0 streaming 与任务风险

- 稳定句预读仍没有服务端 response/generation ID；并发 cron/proactive/迟到 final 可能误归属。10 秒 recovery 只避免永久 thinking，不能认证归属或恢复 provisional 文本。
- speech planner/FIFO 的 planned/enqueued 不能证明“已经听到”；正式版仍需 playback ACK/cursor 和 presented history。
- schedule 当前只加强了同一进程、同一 JSON store 路径内的一致性；没有跨进程事务、唯一执行所有权、exactly-once 或生产 crash recovery。多个进程共享 store、D1/D2 durability 和外部副作用 reconciliation 不在当前保证内。
- Task Demo 是真实有副作用的 AutoHarness，不是只读仓库工具。只有受控环境才能开启；Live Voice 退出或 session fence 只能阻止新的错误派发，不能停止已经创建的任务。
- task-scoped Agent/context、project/origin provenance、服务端 owner+project scope、per-path single-process JSON 幂等 create、前端稳定 command ID 与严格 exact-key reconciliation 已落地，但 Agent context 不能跨重启恢复，target 未包含完整 model/provider/config/permission 快照，也没有跨刷新 command journal、持续 task monitor、跨进程 exactly-once 或 D1/D2；这些仍是正式版缺口。

## 不要重复做或提前做的事情

- 不要另写语音专用 Agent 协议、发送 partial transcript、写死 Agent 答案或工具结果。
- 不要把本地 epoch、quarantine、TTS owner/revision 描述成生产 generation fence。
- V0 独立 checkout/worktree 验收时不要启用 Post-V0 task/streaming flag；受限后台任务开发只按 D-024 在默认关闭、常驻披露和受控环境边界内推进。Team、多语言、WebView2 和真全双工媒体仍不提前宣称完成。
- 不要另建一套覆盖全部功能、依赖模拟状态或 hardcode 结果的 UX 原型；V1/V2/V3 在同一真实工程路径上累计替换 V0 shortcut。
- 不要提交 API key、Slack token、用户配置、浏览器 profile、`.venv`、`node_modules` 或本机绝对路径。

## 每次继续工作后的交接要求

- 更新 [STATUS.md](STATUS.md) 的真实结果、失败、时序和下一步。
- 对每个受影响模块摘要 D-032 closure 状态、exact tested SHA、前后回顾是否完成及 [STATUS.md](STATUS.md) 证据入口；不能用测试数量替代场景闭环，存在必需 gap 时写 `PARTIAL` 或 `BLOCKED`。
- 技术选择变化时更新 [DECISIONS.md](DECISIONS.md)；新增临时简化时更新 [TWO_WEEK_DEMO.md](TWO_WEEK_DEMO.md) 的 Shortcut Ledger。
- 按 D-030 正常提交并推送到 `agtai/hx/0731_live_voice_ux`；不再保留“V0 验收前不 commit/push”的例外。未提交 worktree 和 stash 都是机器本地状态，不能作为跨机器交接方式。

## 用户介入后的 V0 独立验收流程

不要改写、stash 或 reset 当前 Post-V0 开发分支。先确认 foundation 已 commit/push，再从不可变 SHA 创建一个独立 checkout/worktree：

```powershell
git status --short --branch
git rev-parse HEAD
git rev-list --left-right --count HEAD...agtai/hx/0731_live_voice_ux
git worktree add --detach ..\live-voice-v0-acceptance 2c700934aa0024a7ab229644bf15934e9e8170e7
```

上例目录名可按机器调整；必须选择当前仓库外的独立空目录。只在新目录确认 `HEAD=2c700934...`、工作区干净，并清除两个 Post-V0 环境变量后执行 [V0_ACCEPTANCE.md](V0_ACCEPTANCE.md)。如果 Gate 失败，不得写 `Released` 或冻结；失败证据回写当前开发分支的文档，不在 detached 验收目录继续产品开发。

只有 V0 Gate 全部通过后，才在当前累计分支合并验收证据并明确标记 Released/freeze；不得把 Post-V0 foundation 代码算进 V0 证据。当前 foundation 已可从共享分支完整重建；原 stash `7f4cfd2eedfb3a177b94f69417143fba441f3671` 已经 apply，仅作为本机额外保险保留，正常开发和 V0 验收都不要重复 apply/pop/drop，是否删除由用户明确决定。

stash 不随 Git 远端同步。跨机器恢复只认已经 push 的分支提交和本目录文档；新机器执行 fetch、切换分支、`pull --ff-only`，不需要也不应尝试取得本机 stash。
