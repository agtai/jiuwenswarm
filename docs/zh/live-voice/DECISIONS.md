# Live Voice 决策记录

本文件记录已经明确接受的产品和工程取舍。后续 Codex 不应仅因为当前代码更容易而静默改变这些决策；如需改变，应新增决策并把旧决策标记为 `Superseded`。

## D-001 方案知识保存在 Git 跟踪的普通文档中

- 日期：2026-07-31
- 状态：Accepted
- 背景：需要在多台机器上通过 GitHub 同步代码并让新的 Codex 会话快速接续。
- 决策：完整方案和 Demo 方案保存在 `docs/zh/live-voice/`；根目录 `AGENTS.md` 只保存阅读入口和维护规则；不把完整知识仅存入 `.codex`、`.agent`、本地数据库或聊天记录。
- 原因：普通 Markdown 可审查、可 diff、可提交、可跨工具阅读；隐藏工具目录容易与某一运行环境绑定。
- 影响：每次实质性工作结束前必须更新 `STATUS.md`，作出新取舍时更新本文件，并 commit/push。
- 重新评估条件：仓库建立了统一且跨工具的项目知识系统。

## D-002 先交付纵向 Demo，不把它称为 Alpha

- 日期：2026-07-31
- 状态：Accepted
- 背景：完整方案包含 P1、P2、P3 和大量生产化模块，一个人两周无法全部可靠交付。
- 决策：两周交付命名为 `Live Voice UX / Vertical Slice Demo`，先完整走通用户旅程。
- 原因：验证产品价值需要真实的端到端链路，不需要提前完成所有基础设施。
- 影响：Demo 验收与完整 Alpha 验收分开，不能用固定环境的短测替代生产指标。
- 重新评估条件：核心链路已经稳定，需要定义正式 Alpha 范围。

## D-003 Demo 必须通过语音调用真实 Agent 和工具

- 日期：2026-07-31
- 状态：Accepted
- 背景：只有听写和朗读无法验证 Live Voice 驱动 Agent 工作的价值。
- 决策：final transcript 必须进入现有 `chat.send` 或 `supplement`；Agent 回答、工具调用和结果必须真实，不能预设。
- 原因：核心产品假设是“用户通过语音持续协调 Agent”，不是“聊天框多了一个麦克风”。
- 影响：Demo 主验收必须包含仓库检查或其他真实工具调用。
- 重新评估条件：无；这是产品定义的一部分。

## D-004 保留现有文字 Agent，将语音作为外层交互

- 日期：2026-07-31
- 状态：Accepted
- 背景：现有 Agent 已有 Session、工具、审批和中断语义。
- 决策：Demo 使用 `Speech → existing Chat/Agent → Speech` 的薄级联，不在两周内替换为新的实时模型大脑。
- 原因：能够最大限度复用仓库能力，并真实验证现有 Agent 的语音体验。
- 影响：本轮不迁移工具到 provider-native Realtime，不引入 LiveKit 主链。
- 重新评估条件：Demo 证明链路成立，但级联延迟或交互自然度达不到产品目标。

## D-005 Day 1 锁定 Web Speech，失败则快速切换

- 日期：2026-07-31
- 状态：Accepted
- 背景：仓库已有 Browser Speech 代码，但 WebView2 权限和中文连续识别存在环境风险。
- 决策：Day 1 在演示机器完成 Spike；稳定则使用 Browser Speech，不稳定则 Day 2 切到单一 Provider 的薄级联，中文场景优先评估 Azure Speech。
- 原因：设置明确止损点，避免在桌面兼容问题上耗完整个周期。
- 影响：Demo 可先在 Chrome/Edge 展示，Desktop 不是阻塞项。
- 重新评估条件：Provider 账号、预算、网络或隐私约束变化。

## D-006 Demo 的插话采用确定性路径

- 日期：2026-07-31
- 状态：Accepted
- 背景：免手插话需要持续采集、回声消除、误触发恢复和更完整的状态管理。
- 决策：必做路径是“重新开麦或点击 → 立即本地停播 → final transcript → supplement”；耳机环境的自然开口插话为增强项。
- 原因：确定性路径已能验证用户是否需要打断和修改 Agent，同时显著降低两周风险。
- 影响：不能把 Demo 描述为生产级全双工。
- 重新评估条件：D1/D6 实测显示持续监听在目标环境中足够稳定。

## D-007 本地 epoch 是 Demo 防线，不是最终一致性协议

- 日期：2026-07-31
- 状态：Accepted
- 背景：被打断回答的迟到文字和音频可能在新回答中重新出现。
- 决策：Demo 使用本地递增 `responseEpoch` 让旧播放队列失效；完整版仍需 response ID、generation fence、播放确认和 presented history。
- 原因：能以很小改动保护核心演示路径，又不掩盖完整方案的缺口。
- 影响：断线、多端和服务端乱序一致性不属于本轮证明范围。
- 重新评估条件：开始实现正式 Conversation Runtime。

## D-008 通用后台任务不是两周主线

- 日期：2026-07-31
- 状态：Accepted
- 背景：完整 P3 需要稳定任务 ID、状态权威、恢复、审批、多任务消歧和副作用协调。
- 决策：核心 Demo 只要求语音驱动当前 Agent；D7 稳定后，才可复用 `schedule.run/status/cancel` 演示一个明确标注的受限后台任务。
- 原因：当前 Agent 调用和通用持久任务是两个不同的问题，不能让 P3 阻塞 Live Voice 主链。
- 影响：任务演示只能证明产品体验，不能声称完成 Task Control Core 或 Durability。
- 重新评估条件：核心 Live Voice 在 D7 前完成且稳定。

## D-009 可以写死选择，不能写死结果

- 日期：2026-07-31
- 状态：Accepted
- 背景：Demo 需要大幅缩小范围，但过度造假会让验证结论失真。
- 决策：允许固定平台、语言、设备、静音时间、音色、任务口令和最近任务；禁止预设 Agent 答案、伪造工具结果、伪造成功状态或用隐藏的预录内容冒充实时链路。
- 原因：环境限制不会破坏核心产品验证，伪造业务结果会。
- 影响：所有 shortcut 必须记录在 `TWO_WEEK_DEMO.md`。
- 重新评估条件：无；这是 Demo 可信度底线。

## D-010 D7 未稳定则砍掉任务增强

- 日期：2026-07-31
- 状态：Accepted
- 背景：两周周期只有一个人，后两天必须保留稳定和演示缓冲。
- 决策：如果 D7 语音调用 Agent、朗读、打断、错误降级和文字回归尚未全部通过，D8/D9 不做后台任务或新的架构抽象。
- 原因：一个稳定的核心闭环比多个不可靠功能更能验证方向。
- 影响：任务能力是明确可砍的 stretch。
- 重新评估条件：核心验收提前通过。

## D-011 当前 Live Voice Demo 只开放 Agent 模式

- 日期：2026-07-31
- 状态：Accepted
- 背景：Team 模式同时存在 Team Leader、成员执行输出和不同的 interrupt 语义，不能安全地把“最新 assistant 消息”直接解释为唯一应该朗读的 Agent 回答。
- 决策：本轮 UI 和控制器只在 `mode === 'agent'` 时允许启用 Live Voice；进入 Team 模式时显示不可用并退出、清理当前语音状态。
- 原因：单 Agent 模式已经足以验证“语音驱动真实 Agent/Tool、朗读和 supplement”的核心假设；未经建模就开放 Team 会造成串读、重复朗读或错误打断。
- 影响：Demo 通过不能证明 Team Live Voice 已完成。后续必须先定义 Team response ownership、成员输出的呈现/朗读规则和 Team 插话语义。
- 重新评估条件：Team 事件模型与唯一可朗读 response 边界已明确，并有对应一致性测试。

## D-012 Demo 只朗读 chatStore 中已经完成且属于当前语音 Turn 的消息

- 日期：2026-07-31
- 状态：Accepted
- 背景：直接消费原始 `chat.delta` 或在 React 消息组件挂载时触发 TTS，容易因批处理、重写、重复渲染和迟到事件造成重复或串音。
- 决策：Live Voice 以当前 final transcript 对应的用户消息为起点，只从 `chatStore` 选择其后的完整 assistant 消息；`isStreaming === true`、空消息、历史消息、已朗读消息都不进入 TTS。遇到下一条 user 消息即截止，后续文字 Turn 不归属于旧语音 Turn。
- 原因：`chatStore` 是用户实际看到的消息事实，等待其完成再入 FIFO 可以用稳定消息 ID 去重，并让文字和语音共享同一条真实 Agent 路径。
- 影响：本轮是“完整消息后朗读”，不能声称达到 token/audio 流式首音延迟；如果用户在语音 Turn 后发文字消息，其回答不会被误读成旧语音回答。
- 重新评估条件：引入带 response ID 的正式 streaming TTS 与 presented-history 协议。

## D-013 supplement ACK quarantine 是 Demo 隔离，不是生产 fence

- 日期：2026-07-31
- 状态：Accepted
- 背景：当前前端收到的 `chat.delta` / `chat.final` 没有可可靠关联到生成代次的 response ID；supplement 发出后，旧生成的迟到输出可能继续进入消息和 TTS。
- 决策：普通 Agent supplement 发出时，前端清除待刷新的旧 delta、封口旧流，并临时丢弃同 session 的 `chat.delta`、`chat.final`、`chat.reasoning` 和 `chat.media`；收到有序的 `chat.interrupt_result(intent=supplement)` ACK 后解除 quarantine。Team、evolution 和 pending question 特殊路径不套用该规则；连接关闭或重连时清空本地 barrier，避免丢失 ACK 后永久锁死。
- 原因：当前 Gateway 会先取消并等待旧流，再发送 supplement ACK，WebSocket writer 又保持帧顺序，因此 ACK 可作为这一条 Demo 路径的短期边界。
- 影响：该机制能保护当前演示路径，但不能处理 ACK 丢失、断线重放、多端并发或服务端跨生成乱序；失败和断开时只能清理本地隔离，不能据此宣称获得端到端一致性。
- 重新评估条件：服务端提供 response/generation ID，并实现客户端与服务端共同执行的 fence、ACK 和恢复协议。
