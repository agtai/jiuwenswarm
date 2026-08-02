# Post-V0 stash 历史与恢复保险交接单

> **仅供历史取证/灾难恢复。** 第 3–7 节记录的是 2026-08-01 foundation 收尾快照，不是当前执行计划；普通新机器和新 Codex 只读取共享 Git，并以 [STATUS.md](STATUS.md) 的当前下一步为准。

- 快照日期：2026-08-01
- 工作分支：`hx/0731_live_voice_ux`
- V0 Candidate 不可变基线：`2c700934aa0024a7ab229644bf15934e9e8170e7`（未放行）
- 远端跟踪：`agtai/hx/0731_live_voice_ux`
- stash 名称：`post-v0-live-voice-wip-before-v0-validation-2026-08-01`
- stash commit：`7f4cfd2eedfb3a177b94f69417143fba441f3671`
- 状态：**已经 apply，原 stash 保留为额外备份**；D-030 已结束 D-022 的临时“不 commit、不 push”窗口

共享累计分支已包含这份 stash 的内容以及其后的 foundation 收尾；后端 `3da101cf`、前端 `42e76d30` 已落地，相关文档已纳入本批 Git 交付。正常开发、新机器恢复和 V0 验收都**不要重复 apply/pop/drop**。跨机器事实来自正常 commit/push 后的共享分支；本机 stash 只是远端可重建前后的额外保险。

## 1. 正常继续开发与灾难恢复边界

正常继续开发只需核对 Git，不操作 stash：

```powershell
git status --short --branch
git rev-parse HEAD
git rev-list --left-right --count HEAD...agtai/hx/0731_live_voice_ux
```

只有在本机发生明确的数据丢失、共享分支又尚未包含 foundation，并且已确认当前目标工作区不含这些改动时，才把 `7f4c...` 当灾难恢复候选。恢复前先比较 stash stat/patch 与目标 HEAD，避免重复应用；本文件不授权自动 pop/drop 或覆盖现有修改。

stash 只存在于创建它的本机 `.git` 中，不能通过 `git pull` 在另一台机器恢复。Foundation review、统一复跑、代码提交和交接文档已经纳入本批 Git 交付；另一台机器只通过 fetch/pull 接续，不查找这份 stash。

## 2. 两个默认关闭的入口

```text
VITE_FEATURE_LIVE_VOICE_STREAMING_SPEECH=true
VITE_FEATURE_LIVE_VOICE_TASK_DEMO=true
```

只有精确设置为 `true` 才开启。V0 验收必须不设置这两个变量，或显式清除它们，并重启前端与后端进程；热更新或旧进程可能仍保留 Post-V0 代码/状态，不能只凭工作区已经干净就开始记 V0 证据。

## 3. 已完成的 Post-V0 能力

### 3.1 协议与 schedule 真值

- 增加最小 Live Voice contract/conformance schema：校验 identity、cancel scope、committed input、WorkProgress 来源和 terminal outcome。
- Web schedule/issue 请求只有 AgentServer 一个响应 owner，避免本地 handler 抢先返回 `unknown method`。
- AutoHarness 的 run/cancel/delete、快速终态和同任务竞态按持久 TaskStore 真值收敛。

### 3.2 稳定句预读

- 只消费 chatStore 中当前 Turn 唯一且追加式的 assistant stream；有完整句和下一句 lookahead 时才提前朗读。
- 只把权威 `chat.final` 当最终对账边界；suffix 一致才补读，rewrite/mismatch 会停止该 epoch，不把 provisional 冒充 final。
- processing 停止、临时朗读 drain、权威 final 仍缺失时启动一次 10 秒 grace period；到期显示 Retry，不补造或重播文本。
- 修复 planner 尚无 message ID 时先看到 processing、以及 Session A→B/timeout 的迟到回调竞态。Voice Turn 保存 capture 起点 Session，只有合法 `new`→persisted promotion 才重绑定。

### 3.3 受限 Voice–Task Demo

- committed final 的固定中文口令可真实调用 AutoHarness，取得真实 task ID/status/cancel，并以 cancel A + create successor B 表示替换。
- 固定使用有代码副作用的 `extended_evolve_pipeline`；界面常驻披露执行器、副作用和取消不能撤销既有修改。
- session、target 和 bridge identity 全链 fence；capture 期间任一身份改变都拒绝副作用命令。
- 无法从当前 persisted Session 与精确注册项目解析绝对项目路径时 fail closed，零 gateway 请求；run/status/cancel 都携带冻结的 `project_dir`/`project_id`。这只证明正常客户端的一致性约束，不证明请求身份不可伪造。
- UI 显示项目路径、项目 ID、来源 Session、来源 Channel 和来源方法；遗留任务缺字段时显示 unknown，不猜测。

### 3.4 每任务执行上下文与 provenance

- Scheduler 为每个任务注册独立、不可变的进程内 Agent 上下文，不再在执行时借用 singleton 可变 `_agent`。
- 两个并发 Session 使用各自 Agent/context；周期任务沿用其上下文；一次性完成、取消、删除和 service stop 会释放注册。
- 任务持久化并返回 `execution_target`：`project_dir`、`project_id`、`origin_session_id`、`origin_channel_id`。Agent 创建与 target 快照使用同一个已解析项目目录。
- 进程重启后若只有 JSON 任务、没有对应进程内 Agent 上下文，任务会诚实失败，不会借用后来创建的 Agent。

### 3.5 后端创建幂等

- `schedule.run` 可接收 `origin_namespace` 与 `idempotency_key`；owner scope 由服务端根据 Web request 的 channel/session/可用 app identity 字段派生；它只提供单用户请求一致性，不证明字段已认证。
- 同一进程、同一 JSON store 路径的 TaskStore 实例共享锁，原子执行 get-or-create，并在 JSON 中保存 `create_commands` ledger、标准化 intent fingerprint 和删除 tombstone。
- 同 scope、同 key、同 intent 重放返回同一个 task ID，且只触发一次；同 key 不同 intent 返回 `IDEMPOTENCY_CONFLICT` 和 `existing_task_id`，不返回新的 `task_id`。
- JSON reload 后仍可重放；冲突或 replay 时释放本次候选 Agent pin/context。`schedule.list` 支持 scope/namespace/key 的精确筛选；不带幂等字段的旧调用保持原行为。

### 3.6 apply 后完成的 Task Foundation

- `schedule.list/status/cancel/logs/delete` 由 AgentServer 从 Web request 字段派生 owner scope 与 project execution target；必需 `channel_id/session_id` 缺失或非法、完整 owner scope 不一致，或请求 target 与 stored target 中已知的 `project_dir/project_id` 不一致时 fail closed；`app_id` 可空，遗留 unknown project 字段不猜测。拒绝发生在日志读取、scheduler cancel、store mutation、context release 前。由于 Web 身份仍由请求提供，这不是抵御恶意伪造的鉴权边界；显式内部兼容 sentinel 也不应对外暴露。
- Live Voice 每次 committed create/replace 生成一个稳定 command ID；首次 run、同-key retry 和 scoped exact-key list 始终复用这个 ID，绝不以新 key 盲目重试。
- exact-key list 只接受唯一且 task ID、query、pipeline、namespace、key、target 全部一致的记录。任务在请求期间从 pending 进入 running/terminal 是合法真实状态，不因 pending drift 被错误拒绝或覆盖。
- 页面显示真实 task card：task ID、command ID、后端原始状态、recovery/result source、execution target/provenance、predecessor 与冲突信息。它仍是当前页面/Session 投影，不是跨刷新 durable journal。

## 4. 验证结果

### 4.1 隔离前历史快照

#### Python

从本 worktree 执行：

```powershell
..\..\..\.venv\Scripts\python.exe -m pytest -q tests/unit_tests/common/test_live_voice_contract.py tests/unit_tests/auto_harness/test_schedule_task_service.py tests/unit_tests/agentserver/test_schedule_request.py tests/unit_tests/test_app_web_handlers.py
```

结果：**195/195 passed**，exit 0，57.50 秒。该统一数字替代早期有重叠的 46/51/76 分项记账。

#### 前端

- Live Voice 精确测试：**140/140 passed**。
  - core 9
  - turn lifecycle 16
  - TTS text/chunking 10
  - message gate 14
  - supplement quarantine 6
  - speech lifecycle 7
  - TTS ownership 2
  - streaming speech 18
  - task bridge 32
  - task client 15
  - task adapter 11
- chatStore authoritative-final marker 与相关回归合计：**24/24 passed**（marker 3、historical settle 6、stream delta 7、session creation 8）。
- 全前端 `tsc --noEmit`：通过。
- Vite production build：通过，**4494 modules transformed**；只有 caniuse 数据过期和大 chunk 警告。

Python 与前端测试是在最终三项实现汇合后统一执行，不是把子任务的重复数字相加。文档收尾后 `git diff --check` 通过（仅输出 Git 的 LF→CRLF 工作副本提示）。对全部本轮 Python 文件执行完整 `ruff` 时只报告基线已存在且不在本 diff 新增行中的两项：`service.py:293` 的 E712（HEAD blame `756e464e1`）和 `agent_ws_server.py:190` 的 E402（HEAD blame `c6d6cf070`）；以 `--ignore E402,E712` 复查本轮文件后 **All checks passed**。没有为了让收尾数字变绿而顺手修改这两处无关基线代码。

### 4.2 apply + foundation 最终确认

- Python contract、TaskStore/service、AgentServer schedule request、Web handler 统一精确回归：**226/226 passed**。
- Live Voice 前端精确测试：**155/155 passed**。
- chatStore authoritative-final marker 与相关回归：**24/24 passed**。`155` 与 `24` 两组有 9 项测试重叠，不能相加；这些是历史命令结果记录，Git 未保存 JUnit 产物。
- 全前端 `tsc --noEmit`：通过。
- Vite production build：通过，**4494 modules transformed**。

以上是 review 修复合入后的最终统一结果；后端 `3da101cf`、前端 `42e76d30` 已落地，相关文档已纳入本批 Git 交付。它们仍不能替代稳定句听感和真实有副作用任务 E2E。

## 5. 明确没有完成的内容

- 后端幂等仅保证同一进程、同一 JSON store 路径的共享锁 + ledger；没有跨进程 CAS、唯一执行 owner、crash transaction、exactly-once 或外部副作用 reconciliation。
- Live Voice 已有 mutation 内稳定 command ID、同-key retry 和严格 exact-key reconciliation，但没有跨刷新持久 command journal。记录不唯一、identity/target 冲突或 list 仍不可证明时继续 `mutation-unknown`，不能宣称完整恢复。
- owner + project scope 已覆盖 list/status/cancel/logs/delete 的单用户请求一致性，但 Web 身份仍可由客户端声明；它不等于身份认证、租户隔离、审批或生产权限模型。
- Agent 执行上下文只在进程内；重启后不能恢复旧 Agent。`execution_target` 尚未持久化完整 model/provider/config/permission 快照。
- response/generation ID、服务端 cancel/replacement 顺序、工具副作用 fence、playback ACK/cursor、presented history 仍未实现。
- 稳定句预读不是 token/audio streaming TTS，也尚未真机验收；Task Demo 尚未做真实有副作用 E2E。
- 还没有 poll-backed 持续 task monitor：任务派发后前台持续在线、后台非阻塞执行和 terminal 结果异步回流尚未接线；也没有完整 TaskEvent push/replay。
- V0 本身仍待用户完成 10 个准确 Turn、分阶段 10 次打断、20 分钟或 20 Turn soak、主演示连续 3 次和冷环境恢复。

## 6. 后续顺序

1. 2026-08-01 快照选择的下一实现切片是 D-031 poll-backed task monitor；当前仍是该切片，但必须先完成 D-032 开发前回顾、test inventory 与场景矩阵，具体执行权威见 [STATUS.md](STATUS.md)。
2. 保持两个 feature flag 默认关闭；单独开启稳定句预读做 final/rewrite/timeout/Session E2E，在可丢弃或已备份的独立项目开启 Task Demo 做真实 create/status/cancel/replace E2E。
3. V0 验收始终从 `2c700934` 的独立 checkout/worktree 执行，不操作累计分支或 `7f4c...` stash；Post-V0 开发可按 D-030 在隔离轨并行推进。

## 7. 审阅提示

`App.tsx`、`ChatPanel/index.tsx`、`useWebSocket.ts`、`chatStore.ts` 等大文件混有此前 Prettier/换行格式噪声，diff 行数明显大于真实语义变更。不要用总行数判断功能量；恢复后提交前应按逻辑切片审阅和整理，但不要为了减小 diff 丢掉本 stash 中已经验证的语义修改。
