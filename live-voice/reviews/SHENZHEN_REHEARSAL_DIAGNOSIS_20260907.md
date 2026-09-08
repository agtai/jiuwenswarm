# 深圳出差语音预演：诊断与调整建议

日期：2026-09-07。范围：定位用户指定的两次故障，调整展示脚本，给出可执行的体验修复顺序。
本次只改文档（TESTING Tier 0），未修复或重新部署产品代码，未改私人 USER.md、模型配置、Task 或项目成果。
当前状态由 [STATUS](../STATUS.md) 维护；人类操作由 [showcase §4](../demo/PRODUCT_READINESS_SHOWCASE.md#4-current-shenzhen-business-trip-showcase) 维护。

## 1. 样本与证据边界

- 部署代码：`d8ee9e6d39ea6cc73994b5dd86d3d3662bc43ae1`；Native `gpt-realtime-2`，Agent `gpt-5.6`，Native output `inf`，VAD `auto`。
- 原 Session：`web_1a07d4a90d8_59d084d62838`，原 Chrome 页面，未刷新、重开或发送测试对话。
- 用户报告的时间为 Europe/Paris；日志诊断 ISO 时间为 UTC，相差两小时。
- 服务日志：`logs/swarm-20260907-194710.log`。原页面通过公开“导出诊断”按钮导出；离线副本、窗口与分析脚本在忽略目录 `logs/shenzhen-20260907/`。
- 浏览器原始诊断存在历史覆盖计数；本报告使用保留的指定回答事件与服务日志交叉核对，不声称整个历史记录完整。
- 未录制/收听原始扬声器音频。播放空隙来自浏览器调度时钟和用户听感报告；未将首帧到达或排队 ACK 当成实际播放完成。

## 2. 21:15:02 门票回答：存在真实供给不足，半句结束另有打断

该回答为 `response_generation=4`，Provider response `resp_ELZ5z10h8w3hwRFkbTmnv`。

| 时间（Paris） | 事实 |
|---|---|
| 21:15:02.193 / .238 | 端点观察 / 用户输入提交。 |
| 21:15:02.260 | 请求发给实时模型。 |
| 21:15:04.310 | 浏览器首次出现文字。 |
| 21:15:05.517 | 服务端观察到 Provider 首段音频。 |
| 21:15:06.794 | 下行音频源首帧就绪。 |
| 21:15:07.370 | 浏览器播放时钟到达首段开始点，距端点约 5.18 秒。 |
| 21:15:11.462–25.114 | 16 次 `playout_rebuffered`，调度空隙合计约 4.979 秒，最长 0.920 秒。 |
| 21:15:26.174 / .278 | Provider 检测到新语音；浏览器以 `formal_product_barge_in` 停止旧声。 |

服务端对应 seq 280/380/620 的取源等待分别约 914/1352/1052 ms；对应浏览器空隙约 600/920/789 ms。
38 个被记录的下行帧样本中，源就绪后排队等待中位数 0.817 ms、最大 70.198 ms，socket 发送中位数 11.107 ms、最大 33.597 ms。
队列通常只有 1 帧，最大 3 帧。这将主要瓶颈定位到**下行源就绪之前的音频供给链路**，没有证据把主要原因归为本地 WebSocket 带宽或 ACK 堵塞。

当前 [播放器](../../jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/adapters/browserAudioIOAdapter.ts) 的 `#flushPlayout` 在启动/饥饿后等待 250 ms 实际 PCM，再继续安排播放。
实际 0.4–1.35 秒级供给间隔仍会耗尽储备，故 R6 通过自动化也不等于本样本连续性通过。
`playout_rebuffered.reserve_ms` 目前写死为 0，不应将这个字段误读为缓冲功能关闭。
不能用无限加大启动等待掩盖持续供给慢，也不能重新播放已启动 PCM 来补空隙。

证据还不能进一步区分 Provider 生成、Provider 网络与本地 Provider 事件消费各自贡献：现有 transport 诊断没有保留逐段 audio delta 的完整到达序列。
下一步应在同一响应上测量 Provider socket 收到 PCM → engine 入队/出队 → source_ready → 浏览器接受/调度，并用相同输入复现；不要直接断言“模型太慢”或“网不好”。

文字停在“现场按提示来就”对应新语音打断链路，本次没有证据指向旧的 1024-token 截断。
在 21:15:11–25 的卡顿区间，没有本地候选打断暂停/恢复事件；因此这 16 次空隙也不是本地误触发暂停造成的。

## 3. 21:16:41 后台行程：工具路由错误与回执丢失叠加

| 时间（Paris） | 事实 |
|---|---|
| 21:16:41.285 | “后台制定周日深圳一日行程”输入提交。 |
| 21:16:48.123–50.698 | 模型开始/完成工具参数生成，选中 **work.start**。 |
| 21:16:50.902–51.138 | 服务受理只读分析，准备并发送回执；51.139 后继回复排队。 |
| 21:16:52.090–56.291 | 真实 Agent 执行约 4.20 秒，0 次工具调用，返回 36 字结果。 |
| 21:16:56.790–21:17:41.792 | 20 次 `NATIVE_RESPONSE_PRESENTATION_BUSY`。每次 Provider 已创建通知回复，随后本地拒绝并取消，未形成可听通知。 |
| 21:17:43–50 | 用户再次追问“卡住了吗 / 喂喂喂”，才出现后续解释。 |

只读 checkpoint 的原始结果是：“当前无法创建后台任务，因为本轮没有可用的任务委派工具；行程尚未开始制定。”
记录的 analysis state 为 completed，表示分析执行结束，不表示行程 Task 完成。
Task 总数仍为部署前的 112；本请求没有 `task.create` 受理记录。

第一层原因是**选择了没有 Task 创建权限的只读分析入口**：
[工具定义](../../jiuwenswarm/server/live_voice/native_business_tools.py) 明确区分 `work.start` 与 `task.create`，
[router](../../jiuwenswarm/server/live_voice/native_business_router.py) 将前者交给 `execute_native_work(... allow_tools=True)`，
其 formal 入口仍按只读分析限制工具。不能通过给只读 Agent 增加任意写权限来绕过错误路由。
“无法创建”是这条只读分析返回的能力说明，不是 Task 创建 API 已尝试后报错，也不是本次 dirty workspace 拒绝。

第二层原因是**后继回执丢失后前台占用没有释放**。离线对照复现脚本
`logs/shenzhen-20260907/reproduce_successor_refresh.py` 使用仓库 fake socket，无网络/数据库/业务副作用：

- 无并发观察：产生两次 response.create（原调用 + 回执后继）。
- 相同上下文的观察更新与回执刷新重叠：仅产生原来一次 response.create，后继队列为空，inflight 为空，`business_successor_requested=True`，source 未被取消；多次调度也不再补发。

代码路径位于 [Native engine](../../jiuwenswarm/server/live_voice/openai_realtime_native_engine.py)：
`_queue_business_successors` 先标记已安排；刷新期间 `_business_context is not refresh_context` 会调用 `_retire_unsent_request` 丢弃它；该函数没有让同一合法回执重新排队。
这不需要用户 STOP、Task 修订或实际上下文变化，普通观察器返回等价上下文即可触发。
[Runtime](../../jiuwenswarm/server/live_voice/native_interaction_runtime.py) 的 delegate hold 要到后继受理才释放；
[通知入口](../../jiuwenswarm/server/live_voice/native_business_router.py) 因 foreground busy 拒绝 work 播报，而 Gateway 的准备判断没有同一完整前台状态，于是形成创建、拒绝、取消、重试循环。

这个确定性复现与现场“successor_queued 后无发送、随后连续 busy”的序列一致。现场未记录 unsent retirement 的具体分支事件，故不能把离线复现冒充当时的完整调用栈。
修复应保留真实回执并重新仲裁发送，同时保持 STOP/新轮次/旧修订不能复活；不能通过忽略 busy、提前 ACK 或宣称完成解除占用。

## 4. USER.md、回答长度与事实准确性

实际私人 USER.md 已要求先给结论、简短准确、不重述背景、不主动完整报告、委派只作简短确认、只在必要时追问。
**无需为深圳重写这份通用偏好**。本次未修改它。

Native 会话启用 business context 后使用 `_BUSINESS_INSTRUCTIONS`，其中只有“自然对话”和“回执简洁”，没有对所有直接回答施加明确的简短回合规则，也没有在该入口加载私人 USER.md。
P4 的结论优先规则在 [formal Agent 入口](../../jiuwenswarm/server/runtime/agent_adapter/interface_deep.py) 的 Native 只读分析中生效，覆盖不了本样本这些直接由实时模型生成的问答。
现场21:15的天气问题没有 Agent 请求或工具调用，却给出了“下周多半温暖到热、有阵雨”的泛化描述。这不能作为实际预报，也未展示真实 Agent 查询。
启动时还记录了 `web_paid_search` 未知/失败的警告；查询能力需要检查真实注册和工具结果，不能承诺仅改话术即恢复天气查询。

建议把以下表达约定一致应用到 Native 直接回答和 Agent 口头交付（待实施，不是本次已部署行为）：

> 默认第一句给答案，再补一条影响选择的依据；通常一到两句。用户问几个，就给几个。追问只答新问题。省去客套、复述、重复总结和习惯性邀请。日期天气、开放时间等动态事实先查工具；无可靠结果时明确缺少哪项信息。任务回执只讲真实状态和必要约束。详细方案写进成果，用户明确要求展开时再充分回答。

例如，门票问题在实际核验支持后可答：“免费，不需要门票。”本句是期望表达示例，不是本报告对当日开放政策的查证。
不要降低 `max_output_tokens` 来强制短句；这可能重新引入半句截断。也不要要求模型输出后机械删字，以免删掉否定、金额或限制条件。

## 5. 实施顺序与验证边界（建议，尚未执行）

1. **先修回执和委派。** 保留合法回执跨观察更新的发送机会；在创建通知前用一致的前台事实仲裁。明确“后台交付成果”走 Task，“查询/分析”走真实只读 Agent。验证自然表达、追问、运行中调整、已完成另存、无重复 Task；STOP/旧轮次/跨 scope 保持零错误副作用。状态与并发边界按 Tier 2，涉及新权限/协议则先重新定级。
2. **统一简洁回答与真实查询。** 把口语规则送到实际生成声音的模型；检查可用天气/检索工具，补日期消歧和必要来源。信息核验可异步完成，但不能虚构查询中或已完成。短确认跟随真实受理，完整成果留文件。提示与普通路由边界先按 Tier 1；不得暗增分类器或写权限。
3. **修音频供给。** 补齐逐段供给时序并复现；根据实际瓶颈调整读取/转发或有界缓冲。必须同时测首声延迟和中途空隙，不能用更久启动换一条表面连续的录音。播放器/取消/队列变更按 Tier 2，复测开头、数字、转折、句尾、打断、停止重开。
4. **按深圳主脚本真实验收。** 前台对话与后台执行并行；短回执快速返回，不等待整个行程完成。保留用户给出的六类验收项，测量而非承诺绝对零等待。工具/网络有延迟时，应能继续听用户说话并准确交代状态。

文档验证：核对来源、事件关联与算术，复现上述上下文刷新竞态，检查变更链接与 scoped diff。未跑全套产品测试，也未将离线复现或文档修改计为物理体验修复。
