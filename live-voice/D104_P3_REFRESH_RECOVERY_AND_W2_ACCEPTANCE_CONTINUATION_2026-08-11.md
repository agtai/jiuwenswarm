# D104 P3 refresh recovery and W2 acceptance continuation — 2026-08-11

> Status: frozen source/review/runtime-boundary record for product commit
> `a6c0571ea8d1056d5e9cc7f5558e691e97075075`. Current milestone, branch and next
> action remain owned only by [STATUS](STATUS.md).

## 1. Outcome

The assisted W2 product journey exposed one real P3 refresh defect after a
correctly cancelled attempt A: the backend retained the exact terminal task, but
a full page refresh removed the P3 task id and retry controls from the stock
Integrated Web panel. Product commit `a6c0571e` closes that boundary without
changing formal Task authority, retry policy or mutation semantics.

The corrected source is automatically verified. Final W2 human acceptance is
still open and will continue on a different server in a new Codex Session. That
run is ordinary unsigned product acceptance under D-071; it must not create or
repair a trust policy, key, signature, evidence owner, 38-slot manifest,
Replacement Ledger or formal Gate result.

## 2. Observed product boundary

The pre-fix task was:

- task `task-140e78cae69141efb5579737394fa56b`;
- attempt A `attempt-ad20c58800cc479b986b45337302236f`;
- authoritative terminal outcome `cancelled`;
- zero fixture mutation, with its expected events and outbox work settled.

After refresh, P2 returned as `idle`, but the P3 panel no longer displayed the
task id. The cause was local to the product UI: `createdProgressTaskId` and the
task-control leaf existed only in React memory. Server state was neither lost nor
duplicated. The old task remains safe diagnostic history only and cannot satisfy
the post-fix A→B→C acceptance journey.

## 3. Repair contract

Commit `a6c0571e` adds a credential-free, same-tab P3 task-target journal and
binds its recovery to exact Session and correlation identity:

- `task.create` stores the exact task id and closed task-control binding in
  `sessionStorage`;
- a refreshed panel treats that record only as a hint and revalidates status and
  complete task events against backend authority before publishing the task id,
  terminal state or retry controls;
- malformed, oversized, cross-Session, cross-correlation, extra-authority and
  storage-unavailable cases fail closed;
- recovery performs no task mutation and cannot issue a duplicate `task.create`;
- unmount/remount restores the same cancelled task and its retry eligibility.

The journal contains no Provider key, bearer, model secret or other credential.
Formal Task Core/Store, authenticated mutation, three-attempt/two-retry budget,
outbox ownership and Agent/checkout lifecycle remain unchanged.

## 4. Verification and review

The exact repaired tree passed:

- Integrated Web suite: `250/250`;
- frontend production build: PASS;
- `git diff --check`: PASS.

The build retained only the pre-existing duplicate locale key, Browserslist and
chunk-size warnings. Implementation self-review and a cold complete-diff review
found no further actionable defect. A literal independent `/review` was not
available, and a substitute subagent review was prohibited by the active
execution instruction; this is the exact D-053 third-pass limitation and is not
reported as an independent PASS.

## 5. Runtime and handoff boundary

A fresh local unsigned environment was started on `a6c0571e` and then stopped at
the user's direction before any P3 task was created, because final acceptance
will run on another server. Its task, attempt, command, event and outbox counts
were zero; the disposable fixture was clean; Chrome and all dedicated service
ports were closed. No runtime from that abandoned start may be resumed or
counted.

Machine-private configuration is not restored by Git. The new server needs its
own protected Provider configuration, persistent Session, registered disposable
project, clean P3 database, browser profile, microphone selection and browser
permission. The source branch must contain `a6c0571e`, but the accepting Session
must record the actual full tested HEAD rather than assume this document is the
branch tip.

## 6. Copy/paste prompt for the new Codex Session

The following prompt is an operational bootstrap, not a second status authority.
It deliberately sends the next Session back to `STATUS.md` for live facts.

```text
继续完成 JiuwenSwarm Live Voice W2 的最终人工产品验收。使用极高思考强度和最小干预模式推进；优先完成一次真实、完整的产品旅程，不做 Gate、签名或 fault-runner 工作。

Repository:
<替换为新服务器实际 clone 绝对路径>

Remote / branch:
origin / hx/0803_live_voice

必须包含的产品修复：
a6c0571ea8d1056d5e9cc7f5558e691e97075075

一、先恢复并核对 Git

1. 完整阅读根 AGENTS.md，再依次完整阅读：
   - live-voice/README.md
   - live-voice/STATUS.md
   - live-voice/DOCUMENTATION_RULES.md
   - live-voice/D104_P3_REFRESH_RECOVERY_AND_W2_ACCEPTANCE_CONTINUATION_2026-08-11.md
   - live-voice/validation/INTEGRATED_DEMO_ACCEPTANCE.md
   - live-voice/demo/INTEGRATED_SHOWCASE.md
   - live-voice/runbooks/E2E_RUNBOOK.md 的 §7.1
   - live-voice/D95_P3_D0_ATTEMPT_BINDING_REPAIR_2026-08-08.md 的 §7
2. 执行 git status --short --branch、git remote -v、git rev-parse HEAD、git rev-parse @{upstream}、git log --oneline --decorate -12。
3. 若 worktree 有任何不明改动，停止并报告；不得覆盖、删除、stash 或 reset 用户内容。若干净，则 fetch origin 并仅以 fast-forward 方式更新 hx/0803_live_voice。
4. 确认 HEAD 是 a6c0571e 的后代，记录实际完整 HEAD、upstream 和 divergence。Git 是实现事实；STATUS 是唯一可变当前状态。

二、严格范围

- D-071 已把 W2 收口定义为“适用自动验证通过 + 一次完整人工产品验收”。
- 不创建、不签发、不修复、不执行 trust policy、root/leaf key、artifact signature、evidence owner、38-slot manifest、Replacement Ledger、w2_gate_cli evaluate 或旧 rehearsal fault runner。
- 暂不移除 Gate 代码；Gate 代码移除是 W2 人工验收完成后的独立任务。
- 不把路由事实面板当作产品入口。用户操作的是实际“Live Voice / 实验功能”控制区。
- 不委派其他 agent。只在必须由用户完成的私密输入、设备选择、实听和不可逆选择上打断用户。

三、新服务器机器准备

1. 核对仓库要求的 Python、Node、uv、前端依赖、Chrome 和服务端依赖。仅在最终产品源码发生变化时重跑受影响自动套件；当前已知 a6c0571e 边界为 Integrated Web 250/250、frontend build PASS、git diff --check PASS。
2. 创建全新的隔离 JIUWENSWARM_DATA_DIR、Chrome profile 和 P3 SQLite；不得复用旧服务器的 Session、数据库、profile、runtime root 或 task。
3. 创建并注册一个可丢弃 Git fixture，仓库本地设置 core.autocrlf=false，建立干净 baseline。fixture 至少有 README.md，最终只允许验收任务修改它。
4. 创建一个精确持久 Session，注册上述 project，选择真实 Agent/model。连续启动不会把模型配置替换成模板占位值。
5. 配置真实 OpenAI-compatible STT/TTS。API key 若缺失，只让用户在受保护的可见终端私密输入；不得在聊天、命令参数、PowerShell history、日志、文档或 Git 中回显/保存 key。
6. 使用一个 Chrome page 打开精确 /chat/<session_id>；选择实际可用的输入设备并取得麦克风权限。只要求设备正常，不要求与旧服务器型号相同。
7. 启动正式产品 flags：
   VITE_FEATURE_LIVE_VOICE_INTEGRATED_WEB=true
   VITE_FEATURE_LIVE_VOICE_INTEGRATED_P1=true
   VITE_FEATURE_LIVE_VOICE_PRODUCT_P3_MUTATION=true
   保持 VITE_FEATURE_LIVE_VOICE_STREAMING_SPEECH 和 VITE_FEATURE_LIVE_VOICE_TASK_DEMO 关闭。
8. 后端启用正式 product composition、P2、P3 text/mutation、P3 auth 和真实 Speech/Media 所需配置，但保持 W2 evidence/Gate 相关开关关闭。用同一受保护 bearer、同一 Session/project/model 启动 Gateway 与 AgentServer。
9. 先做只读 readiness：页面只有一个目标、Session/project/model 正确、fixture clean、P3 DB 无 task/attempt/outbox、服务端口无旧 owner。不要运行旧 signed rehearsal。

四、引导用户完成一条连续人工旅程

每一步先给用户一条短操作指令，然后等待用户报告肉眼/实听结果；同时用只读后端状态核对精确 Session、correlation、task、attempt、outbox、lease 和 fixture。不得用自动化假冒用户的麦克风、听觉或 UI receipt。

1. P1：用户点击 Start，以物理麦克风说一句短问题。确认 status=recognized，可编辑/确认，正式提交到真实 Agent；听到完整回答朗读；自动 successor capture 出现后由用户停止。确认没有重复 Agent/Tool 提交，空 successor 不被确认提交。
2. P2 Tool：文本输入“请调用终端工具只读执行 git branch --show-current，只回答实际输出，不要修改任何文件。”确认 waiting→presented→acknowledged、真实 Terminal Tool call/result、回答与 fixture 当前分支一致，并听到完整朗读。
3. correction/barge-in：先提交一个会产生可听朗读的短问题；朗读开始后让用户点击 Stop playback，确认声音立即停止且旧语音不恢复。若 P1 正在 capturing，先让用户停止并等到不再 capturing，不确认空转写。然后 P2 输入“修正：只回答‘分支用于隔离开发工作’。”确认 acknowledged、显示精确修正文本，并听到修正回答的完整朗读。修正不得取消或污染 P3。
4. 可见降级：提交一个正常但较长的朗读请求，观察真实 Provider/media 结果。若触发 REQUEST_TIMEOUT 或其他产品降级，UI 必须显示真实 reason，文本回答仍可用，控制仍可恢复；不得破坏 key、网络或权限来强造故障。若本环境没有自然触发安全降级，使用 acceptance/runbook 已有的非破坏性产品路径，不能运行已退役 Gate fault runner。
5. P3 未确认零副作用：填写一个会修改 fixture 的任务，但不签发/不执行确认。只读核对 task/attempt/outbox 仍为零且 fixture clean。
6. 创建正式新 task，名称“W2人工验收 A→B→C”，指令：
   “在修改任何文件前，请只读检查此夹具中所有已跟踪文本文件并先制定详细计划；完成后仅在 README.md 末尾追加一行：W2 manual acceptance 2026-08-11。不要修改其他文件。”
   签发确认并执行。记录唯一 task_id 和 attempt A id；一看到 A active 就立即进入下一步的并发 P2，不要等待任务完成。
7. A active 期间用 P2 提交“只回答‘P2与任务并行正常’。”P2 进入 waiting/presented 后立即取消 A；确认 P2 仍继续到 acknowledged 并完整朗读，P3 独立到 authoritative cancelled，没有互相遮蔽或误取消。等待 retry eligible、outbox/owner/lease settled 和 fixture zero mutation。若 A 在取消前已经 completed，必须如实记录并用全新隔离 P3 DB/task 从 A 重新开始，不能把 completed A 冒充 cancelled A。
8. A cancelled 且并行 P2 acknowledged 后，在同一个 /chat/<session_id> 页面按 F5。确认 P2 恢复/idle，P3 自动恢复完全相同的 task_id、cancelled 状态和 retry 控件；后端 task 总数仍精确为 1，没有重复 task.create。这是 a6c0571e 的必要人工回归。
9. 对同一个 task 执行第一次 retry，得到 attempt B（attempt_number=2）。等待 B completed。核对只有 README.md 多出精确一行，没有其他 tracked/untracked/ignored 副作用；task events、outbox、worker、owner、lease 和 checkout cleanup 正确。
10. 由当前 Codex Session 在可丢弃 fixture 内创建一个本地 checkpoint commit（不得 push fixture，不能要求用户手工提交），记录 SHA并确认 clean。产品源码仓库不得被任务修改。
11. 对同一个 task 执行第二次也是最后一次 retry，得到 attempt C（attempt_number=3）。C 一进入 nonterminal/active 就优雅停止 predecessor AgentServer，然后用相同数据目录、P3 DB、Session、project、model、bearer 和源码启动 successor AgentServer。核对 successor 只重建/对账精确 C，UI 显示真实 terminal/restart outcome（预期 interrupted/restart_interrupted，若实现返回其他合法结果则记录并按合同判断），无旧 predecessor 卡片回填、无 attempt D、无重复 mutation、所有 owner/lease/outbox 最终清理。若 C 在重启前已 terminal，必须如实记录并用全新 DB/task 重跑完整 A→B→C，不能伪造 restart。
12. 避免在等待 P2 notification 时人为闲置超过 10 分钟；若实际出现 stale poll/timeout，要记录真实状态，先判断产品影响，不要立即转去修 Gate。

五、闭环判定与文档

1. 完整检查：P1 麦克风关闭、TTS/定时器停止、页面和服务优雅关闭、专用端口关闭、source worktree clean；P3 无 nonterminal task/attempt/project-attempt、pending outbox、owner/lease；fixture 位于预期 checkpoint 且 clean。
2. 向用户索取并记录必要人工观察：识别正确、完整初始 TTS、Stop playback 立即停止、完整修正 TTS、P2/P3 并发可用、F5 后同一 P3 task id 恢复、可见降级/文本 fallback、restart UI 真实。
3. 若只是操作失误，重做受影响步骤；若发现产品缺陷，只修该产品边界，跑受影响自动检查，再重做受影响人工步骤。不要修 Gate。
4. 全部通过后，新增一份简洁脱敏的日期验收记录，更新 STATUS 一次，把 W2 标记为 PRODUCT-ACCEPTED，并把下一优先级切到 Integrated Web Alpha。更新 README 路由，不改写 D103/D104 冻结历史。
5. 本地文档/修复 commit 可按当前 D-063 最小干预授权完成。任何 push 前仍须按 AGENTS.md 单独列明 exact remote、branch、commits、普通或改写方式，并取得明确授权。

开工后先简短报告 Git/HEAD/upstream/worktree、机器私有缺口和准备顺序，然后立即推进。不要因为没有 Chrome 插件而停止；可用现有单页、CDP 或用户手动操作继续，但自动化不能替代人工观察。
```

## 7. Acceptance decision boundary

The new Session closes W2 only if the complete product journey passes and final
cleanup is correct. A safe operator mistake permits repeating only the affected
step. A product defect requires a product-boundary fix plus affected automated
and human reruns. Gate-era failures, missing signatures and Replacement Ledger
scores have no effect under D-071.

On success, create a new concise sanitized acceptance record and update
`STATUS.md` once to `PRODUCT-ACCEPTED`; do not rewrite D103 or this frozen record.
