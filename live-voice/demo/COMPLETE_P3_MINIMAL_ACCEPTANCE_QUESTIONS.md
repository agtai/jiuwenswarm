# Complete P3 最小验收问题集

> 当前实现状态与候选边界：[STATUS](../STATUS.md)
> 完整 P3 合同与最终判定：[complete P3 execution plan](../roadmap/FULL_P3_EXECUTION_PLAN.md)
> 风险、场景与评审规则：根 [TESTING](../../TESTING.md)
> 环境、启动与清理：[E2E runbook](../runbooks/E2E_RUNBOOK.md)
> 较小的受控候选 Journey：[product-readiness showcase](PRODUCT_READINESS_SHOWCASE.md)

本文准备一次尚未执行的完整 P3 人工验收，并把不能由人工观感证明的
自动化、故障、配置和隐私前置问题列在同一 Gate 中。它覆盖 `P3-1` 至
`P3-8`，但不改变已有 exact-source 验收事实；只有下列证据问题和 19 个
人工问题在同一个精确、干净候选上全部通过，才可以形成完整 P3 结论。

## 1. 判定方法

每题只记录 `PASS`、`FAIL`、`BLOCKED` 或 `N/A`。必答题不得用 `N/A`
跳过。`BLOCKED` 只用于缺少真实 Provider、设备、项目、凭据或受控故障条件；
产品正向路径失败、权威真值错误或出现禁止副作用时记为 `FAIL`。测试数量、
对话承诺、文件存在或 UI 外观均不能单独替代权威 Task/Attempt/Event/Result
事实。

这是两个缺一不可的 Gate：

1. **E Gate — exact-source 证据问题：** 自动化、故障/恢复、配置、隐私、
   feature-off 和独立评审已经在候选上闭合。
2. **H Gate — 19 个最小人工问题：** 一个真实 Chrome、麦克风、TTS、
   Agent/Tool、Store、Executor 和正式 P3 Panel Journey 通过。

正常运行中，terminal 语音在 presentation ACK 后应只播报一次；但产品仍是
at-least-once presentation。若恰好在播放后、ACK 提交前崩溃，允许重放，
不得把本文写成任意崩溃下的 exactly-once speech 承诺。

## 2. E Gate — 人工 Journey 前必须回答的证据问题

以下问题不应通过临时点击或肉眼猜测回答。引用的自动化、受控故障结果和
独立评审必须绑定本次 exact source；任何行为代码变化都要求重跑受影响证据。

### E1 — 候选与环境是否唯一

- 是否记录完整 commit、comparison base、branch/upstream、clean status，且
  自动化、评审和人工运行使用同一行为源码？
- 是否记录脱敏的 Chrome/OS/origin/设备/网络、Provider/model、隔离数据目录
  和无 remote 的一次性项目标签？
- 启动后源码是否保持不变，凭据、私有配置、运行数据库、音频与原始结果是否
  均留在 Git 外？

### E2 — 是否只使用正式产品权威

- `formal-web-validation` 预检和启动合同是否通过，且明确记录正式 Speech、
  Media、Agent/Tool、Task Core/Store、Direct Executor 和 Runtime/TTS route？
- `executor_profile` 是否精确为 `live-voice.direct-project-code.d2.v1`，所有
  必需 P3/Live Voice 开关是否为 `true`？
- 是否没有把 Demo、legacy、fake、测试注入或项目文件推断当成 Task/Result/
  presentation 权威？

### E3 — P3-1～P3-3 的权威、命令与 admission 是否闭合

- D-032 的适用 `P/N/B/S/T/C/R/I/F/K/X` 证据是否覆盖 migration/reopen、
  duplicate/conflicting command、wrong task/scope、并发 terminal、capacity、
  project serialization、lease/outbox fence、deadline 和 exact cancel？
- 受控 dispatcher fixture 是否证明 `task.update` 只在 dispatch outbox 从未
  claim/deliver 时同步更新 canonical spec 与 payload；一旦 claim/deliver，是否
  稳定 conflict 且零业务副作用？该正向路径不交给人工抢时间窗口。
- `EXECUTOR_PROJECT_BUSY` 的 closed pre-effect defer 是否证明同一 Attempt 回到
  `PENDING` 后保留 `task.reprioritize`、移除 `task.update`；claimed 窗口是否两者
  都不展示，fresh status 后不保留过期 capability？
- accepted/queued、running、command accepted/applied 和 terminal outcome 是否
  始终分离，所有拒绝/冲突/超时/未知路径是否断言禁止副作用为零？
- `task.retry` 的 cancelled recovery 与非法状态是否已有 exact-source 证据？
  它不并入下面的主 Journey，以免主动复活 B 并破坏取消隔离 oracle。

### E4 — P3-4 durability 是否按声明而非接口名证明

- D0 是否证明 Session/语音断开不取消仍由存活应用和 Executor 执行的 Task，
  且重启时不能证明 continuation 的状态如实成为 `interrupted/unknown`？
- 本次 D2 profile 是否用真实 Direct Adapter 在危险的
  intent/effect/receipt 边界完成 process-failure、checkpoint、linked recovery
  Attempt、stable effect identity、reconciliation 与 repeated-start 证据？
- unresolved effect 是否进入有界 `manual_required/pending/unknown`，而不是
  自动重试或伪装 completed？
- 当前没有可声明的 D1 candidate 时，缺失/D1/未知 profile 是否在 Store 或
  Executor 副作用前 fail closed？不得把 D2 或接口存在改称 D1 PASS。

### E5 — P3-5 result、unread 与 ACK 是否耐久

- legal immutable TaskResult、Task-wide bounded/paged cursor、跨 Attempt replay、
  fresh Session/process nonzero watermark、terminal append race 和超过 256 个
  non-presentable/presentable event 是否通过 Store 证据？
- text/voice consumer watermark 是否隔离，wrong/stale/foreign generation、Task、
  Attempt、consumer 或 presentation class 是否零消费、零错播报？
- voice consumption 是否经过真实 Runtime presentation ACK 和 durable Core ACK，
  而非 synthetic Arbiter 单测冒充产品证据？

### E6 — P3-6 自然语言与结构化入口是否同权威

- 当前 68-case bilingual corpus、14 个 text/voice/structured parity group 和
  actual production Resolver/Bridge 是否全部通过？
- partial、低置信度、否定、引用、零/多候选、重复名称、changed Task set、
  stale/foreign target 及 confirmation 改 operation/target/arguments 是否全部
  fail closed，且禁止副作用为零？
- 语音、自然文本和 Panel 对同一 operation 是否得到相同 canonical command/
  query truth，而不是从对话文本、current/recent hint 或文件推断状态？

### E7 — P3-7/P3-8 组合、配置、隐私与退役是否闭合

- 初次连接、refresh 和 reconnect 是否按顺序 fresh reread bounded list、exact
  status、完整 bounded events 和 result，失败时不激活、不 ACK、不 mutation？
- content-free diagnostics 是否能关联 Task/Attempt/Command/Event/outbox/
  Executor/checkpoint/effect/recovery/reconciliation/generation/ACK，同时不包含
  prompt、answer、TaskResult/artifact 内容、raw identity、凭据或 raw audio？
- exporter 饱和、拒绝、异常和关闭是否不改写业务结果，也不回退到第二个 legacy
  collector/authority？
- configuration 缺失、伪造、过期、D1 或未知 profile 是否 fail closed；
  ordinary production flag-off 是否保留支持的 text path 且零 formal Task owner/
  allocation？
- 正式产品能力是否不依赖受控杭州 itinerary、固定 Task 名称/口令、trusted Demo
  bypass 或 `.env.production` 的隐式启用；非杭州的 P3-6 corpus 与本文的新文件名/
  adjustment 是否共同证明没有把 fixture 命中冒充 generalization？
- D-092 已批准的三项是否保持 retired，其余 18 项和仍有消费者的 compatibility
  path 是否保持明确 retained/inventory，没有扩大删除或伪报 external OTel、SLO、
  retention、Production 能力？

E1～E7 任一必答问题未通过时，不开始或不通过 H Gate。

## 3. 固定项目与 Task 输入

使用已注册、可丢弃、无 remote 的隔离 Git 项目。开始前确认项目中不存在
`food-b.md`、`itinerary-a.md`、`itinerary-a2.md`，并记录初始 Git 指纹。
不得在本源码仓库或用户真实项目中执行。

### Task B

- Name：`杭州美食乙`
- Instruction：

  > 创建 food-b.md，整理三十项杭州美食与街区信息。每项包含名称、所在区域、特色和注意事项，并按区域汇总；完成前检查文件已经保存。

### Task A 初始版本

- Name：`杭州行程甲`
- Instruction：

  > 创建 itinerary-a.md，制定一份三天杭州行程。每天包含上午、下午和晚上，每个时段至少三项候选活动，每项给出交通方式、开放时间、费用和注意事项；初始安排中第二天下午去灵隐寺，第二天晚上逛河坊街；完成前检查文件已经保存。

### Task A pre-dispatch update oracle（仅用于 E3 受控证据）

> 创建 itinerary-a.md，制定一份三天杭州行程。每天包含上午、下午和晚上，每个时段至少三项候选活动，每项给出交通方式、开放时间、费用和注意事项；第二天下午改为西湖，第二天晚上留作自由活动；完成前检查文件已经保存。

### Task A running adjustment

> 把 itinerary-a.md 中第二天下午改为西湖，第二天晚上改为自由活动；并在文件末尾增加“雨天备选”小节，列出三个室内备选并说明分别替换哪个时段；不要改变其余安排。

### Task A successor

- Name：`杭州行程甲修订版`
- Instruction：

  > 创建 itinerary-a2.md，以杭州行程甲的最终结果为前版依据，将第三天上午改为中国丝绸博物馆，其余已确认安排和雨天备选保持不变；不要改写 itinerary-a.md。

若 B 在取消前自然完成或将 patch 应用到目标项目，或 A 在 unsupported 检查、
running adjustment/Exit 前已终结，本次相应正向场景是**夹具时序无效**，不是
自动 PASS。清理隔离项目与数据后，用更长的安全任务重新开始；不得修改真实
状态或把非法状态 conflict 当成通过。`task.update` 的人工竞速不属于 H Gate，
其正向和 claimed-conflict 均由 E3 回答。

## 4. H Gate — 19 个最小人工验收问题

### 第一部分：语音与两个独立 Task

1. **普通语音链是否完整？** 启用 Live Voice，说：

   > 请用一句话介绍杭州。

   是否只提交 authoritative committed final，看到并听到真实 Agent 回答，
   播放后自动恢复监听？

2. **B 是否成为真实 running Task？** 在正式 P3 Panel 用固定输入创建并确认
   `杭州美食乙`。是否先区分 command accepted/applied，再看到 B 的唯一
   `task_id`、`attempt_id` 和 authoritative `running`？不要等待 B 完成。

3. **A 是否成为同项目中独立 queued Task？** 立即用固定输入创建并确认
   `杭州行程甲`。是否生成与 B 不同的 `task_id` 和 `attempt_id`，A 显示
   canonical `accepted` 加 derived `queued`，且没有伪报 running？

4. **多 Task 投影是否隔离？** 点击一次 Panel“刷新”。是否仍只有 A、B 两个
   Task，B=`running`，A=`accepted/queued`；切换选择只改变 selection，两个
   Task 的 identity、instruction、state、event head 和 result truth 均不互改？

### 第二部分：busy queue 控制与无目标副作用取消

5. **busy defer 后 reprioritize 是否可实际操作？** 精确选择 A，点击 Panel
   “刷新”，直到 fresh status 同时显示 A=`accepted/queued`、admission reason=
   `EXECUTOR_PROJECT_BUSY`，且操作列表启用 `task.reprioritize`。若后端已证明
   outbox=`PENDING`，但 fresh Panel 仍禁用该操作，立即记为 **FAIL** 并停止本轮；
   这是 P3-7 capability freshness 缺陷，不能用反复点击绕过。

   执行 `task.reprioritize`，Priority=`urgent` 并确认。若确认时恰逢下一次 claim，
   state conflict 是合法竞态；等待下一次 closed defer、fresh refresh 后用新命令
   重试。最终是否至少有一次先 accepted 后 applied，A 的 admission priority
   精确成为 `urgent`，但没有声称 running/completed，且 B 完全不变？

6. **busy 后 update 边界是否诚实？** A 已有 closed busy delivery 后，Panel
   是否不再展示 `task.update` 为可用？不要绕过禁用状态。本题只验证 D-087
   的 claimed/delivered conflict；“Task A pre-dispatch update oracle”的正向
   applied 结果必须来自 E3 的受控、从未 claim 的 dispatch fixture。

7. **取消 B 是否发生在目标 patch 之前？** 完成 H5～H6 后立即精确选择 B，
   执行 `task.cancel` 并确认。是否区分 cancel accepted 与 authoritative terminal，
   最终 B=`terminal/cancelled`；A 未取消、未回滚、未重建；B 的取消通知在正常
   ACK 路径至多播报一次并恢复监听？同时重新读取隔离项目：其 Git 指纹是否仍
   等于初始 clean 指纹，且 `food-b.md` 不存在？若 B 已 completed 或目标项目
   出现 B 的 patch，本轮时序无效，不能继续用该项目验收 A。

### 第三部分：running 控制与前台对话隔离

8. **running adjustment 是否在非固定 Demo 输入上真实应用？** B terminal 后等
   A 明确 `running`，立即执行 `task.adjust`，填入固定 running adjustment 并
   确认。是否先 accepted 后 applied，绑定 A 当前 Attempt/checkpoint，且最终
   项目/Result 能验证“雨天备选”；若只是对话确认、返回
   `ADJUSTMENT_CHECKPOINT_CLOSED` 或 A 已 terminal，均不能记为 PASS？

9. **当前 Direct profile 的不支持能力是否诚实且零副作用？** A 仍未终结时，
   Panel 是否将 `task.provide_input`、`task.pause`、`task.resume` 显示为
   unavailable/unsupported 且不可执行？不要绕过禁用状态。前后 authoritative
   snapshot 与项目指纹是否证明除允许的 sanitized decision/command ledger 外，
   Agent、Tool、Task、Attempt、Event、outbox、Executor、文件、音频、history
   和其他 scope 副作用均为零？

10. **精确语音查询是否只读取 A？** 在 A 未终结且 A/B 都可见时说：

    > 请查看名为“杭州行程甲”的任务状态。

    是否只返回 A 的 canonical status，并与 Panel fresh status 一致；B 的
    identity、terminal outcome 和项目指纹不变？目标澄清的零/多候选、重复名称
    与 changed-set 证据由 E6 的固定 corpus 回答，不在本题临时制造歧义。

11. **前台交互与 barge-in 是否只作用于当前 response？** A 仍未终结时说：

    > 杭州哪个季节最适合旅行？

    必须等回答开始播放后再插话：

    > 请介绍一下西湖最有代表性的景点。

    是否只停止旧前台朗读并产生一个新前台回答；A 未取消、未修改、未重建，
    B 仍保持原 cancelled truth，新回答后恢复监听？这不声称
    generation-time interruption。

### 第四部分：刷新、D0 断开、unread 与重放

12. **刷新重连是否 fresh 恢复同一真值？** A running 后刷新浏览器一次并重新
    启用 Live Voice，再点击 Panel“刷新”。A/B 原 `task_id`、`attempt_id` 是否
    不变，B 仍 cancelled，A 仍是原 Task，列表无第三个重复 Task；旧 route 在
    fresh list/status/events/result 完成前没有 activation/ACK，已消费的 B 通知
    没有重播？

13. **Exit 是否只关闭语音而不取消 A？** A 尚未终结时 Exit Live Voice。
    麦克风、播放和该 route 的轮询/重连是否停止；后端 authoritative status 是否
    证明 A 仍为同一 Task/Attempt 且继续由存活应用/Executor 执行，没有隐式
    `task.cancel`？本题只取得 D0 Session-disconnect 人工信用；E4 单独决定
    process-restart/D2 信用。

14. **离线期间终结的 A 是否只形成一个真实 unread 结果？** 等后端确认 A
    terminal 后重新启用 Live Voice。是否只恢复同一 A，并将一个 retained/unread
    terminal event/result 绑定到新的 response/generation；正常 presentation ACK
    后只显示并播报一次，随后恢复监听，B 的取消通知不重播？

15. **消费后的刷新是否不重复？** 再刷新一次。A 的 terminal 通知是否不再
    显示或播报，A/B 不重复创建，Task list、event replay、voice watermark 与
    result availability 一致？text adoption 不应错误消费 voice watermark，
    fallback-to-text 也不能冒充 voice ACK。

### 第五部分：A 的 Result 与语音/Panel 同权威

16. **A 的最终结果是否正确且可由两个入口一致读取？** 精确选择 A，并说：

    > 请读取名为“杭州行程甲”的任务结果。

    Panel 与语音是否都从同一 immutable TaskResult 得到
    `terminal/completed`、result=`available`，并满足：

    - `itinerary-a.md` 存在且属于 A 的真实 Tool effect；
    - 第二天下午安排为西湖，第二天晚上明确为自由活动；
    - 不再把第二天下午安排为灵隐寺，也不保留第二天晚上逛河坊街的旧版本；
    - 存在“雨天备选”及三个带替换时段的室内选项；
    - B 的 `food-b.md` 不存在，也没有被当作 A 的 Result；
    - 语音摘要不虚构缺失或截断内容。

    记录 `itinerary-a.md` 的内容 hash，供 successor 后验证不可变性。

### 第六部分：successor revision 与最终清理

17. **clean checkpoint 后 successor 是否创建新身份且不改写 predecessor？**
    保持选中 completed A，先记录 A 的 Task/Attempt/Event/TaskResult、
    `itinerary-a.md` hash 与当前项目指纹。然后只能由外部验收夹具检查预期 patch，
    将 `itinerary-a.md` 建立为新的本地 Git checkpoint，记录新 HEAD 并确认项目
    clean；不得由 Agent/Task 隐式执行 commit/reset/stash/clean/checkout，也不得
    push。checkpoint 前后 A 的 canonical truth 与 Result hash 是否完全不变？

    重新解析同一稳定项目的新 clean revision 后，执行 `task.create_successor`，
    填入固定 successor Name/Instruction 并确认。是否新建
    `杭州行程甲修订版` 及新 Attempt，新旧 `task_id`、`attempt_id` 不同；原 A
    的 `successor_task_id` 指向新 Task，新 Task 的 `predecessor_task_id` 指向
    原 A，revision 关系与 command accepted/applied 分离且一致？本题不声明
    Direct profile 支持在 dirty worktree 上无缝创建 successor。

18. **修订结果是否只写新 artifact？** 等 successor terminal 并完成一次通知。
    `itinerary-a2.md` 是否存在，第三天上午为中国丝绸博物馆，其余已确认安排和
    雨天备选保持不变；原 A 的 Task/Attempt/Event/TaskResult 与
    `itinerary-a.md` hash 是否完全不变；B 是否仍 cancelled 且未复活、未修改；
    再次选择原 A 时 `task.create_successor` 是否已经 unavailable，且刷新没有
    创建额外 Task？不要绕过禁用状态尝试第二个 successor。

19. **Exit 与系统清理是否完整且不改写结果？** Exit 后麦克风、capture、playout、
    Task notification polling、timer、reconnect、presentation owner 和 exporter
    worker 是否停止或有界 settle；所有 Task/Attempt/outbox/lease/reconciliation
    状态是否终结或如实记录 pending/manual/unknown；隔离项目只有预期 artifact，
    源码仍 clean，端口按 runbook 释放？

## 5. 覆盖与最终结论

| Package | 最小直接问题 | 必须同时引用的 E Gate |
|---|---|---|
| `P3-1` | H2–H4、H7、H10、H12、H17–H18 | E3 |
| `P3-2` | H6–H9、H17–H18 | E3 |
| `P3-3` | H2–H5、H7–H9 | E3 |
| `P3-4` | H12–H14、H19 | E4 |
| `P3-5A/B` | H10、H12–H16、H18 | E5 |
| `P3-6` | H10、H16–H17 的语音/结构化同权威 | E6 |
| `P3-7` | H2–H19 的正式 Panel、刷新与 presentation | E2、E5 |
| `P3-8A/B` | H12、H19 的可观察组合与关闭 | E1、E2、E7 |

最终记录必须包含：exact source、comparison/upstream、clean status、E1～E7、
H1～H19、三个 Task 和各 Attempt identity、命令 disposition、terminal/result/
lineage、预期 artifact hash、自动化/故障/评审引用、脱敏环境标签、所有失败和
接受偏差。原始 prompt/result、用户目录、凭据、设备私有标识和运行数据库不进入
Git。

只有 E Gate 与 H Gate 均通过，且没有未解释的必答失败，才可记录
`PASS — COMPLETE P3 ACCEPTANCE`。这仍不证明完整 P1/P2、feature-complete、
competitor-gap closure、Production authentication/tenancy、公开部署、外部 OTel、
SLO/retention、广泛浏览器/设备兼容、RC/Production 或 `develop` 集成资格。
