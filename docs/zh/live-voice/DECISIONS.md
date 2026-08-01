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
- 状态：Superseded（final 路由部分由 D-019 取代；显式重新开麦和立即本地停播仍保留）
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

- 日期：2026-07-31；2026-08-01 补充真实 E2E 后的边界
- 状态：Accepted
- 背景：当前前端收到的 `chat.delta` / `chat.final` 没有可可靠关联到生成代次的 response ID；supplement 发出后，旧生成的迟到输出可能继续进入消息和 TTS。
- 决策：普通 Agent supplement 发出时，前端清除待刷新的旧 delta、封口旧流，并临时丢弃同 session 的 `chat.delta`、`chat.final`、`chat.reasoning`、`chat.media`、`chat.tool_call` 和 `chat.tool_update`；旧流关闭产生的 `processing=false` 在 barrier 内暂存。收到有序的 `chat.interrupt_result(intent=supplement)` ACK 后解除 quarantine。Team、evolution 和 pending question 特殊路径不套用该规则；请求失败、连接关闭或重连时清理本地 barrier，并在需要时恢复被暂存的停止边缘。
- 原因：WebSocket writer 的帧顺序使 ACK 可以作为“旧前端输出隔离结束”的 Demo 边界，但 2026-08-01 代码复核确认 Gateway 会在 AgentServer cancel 和 replacement 完成前发送 ACK。ACK 只开放客户端可见输出，不证明旧 Agent、工具或副作用已停止。
- 影响：该机制能降低演示路径中的旧文字、工具 UI 和错误 processing 边缘复活，但不能安全丢弃所有 `chat.tool_result`，也不能处理真实工具副作用、ACK 丢失、断线重放、多端并发或服务端跨生成乱序。不得据此宣称获得端到端一致性。
- 重新评估条件：服务端提供 response/generation ID，并实现客户端与服务端共同执行的 fence、ACK 和恢复协议。

## D-014 固定受控 Demo 环境，并区分 Demo 与生产阻塞项

- 日期：2026-07-31
- 状态：Accepted
- 背景：Live Voice 同时依赖浏览器语音服务、权限、硬件、网络、模型 Provider 和多套前后端依赖；只固定源码不足以保证现场可复现。同时，生产级 response ID、全双工媒体等长期能力不应阻塞两周纵向验证。
- 决策：Demo 固定 Windows/Chrome、`zh-CN`、默认麦克风、耳机、单用户、Agent 模式和稳定网络；Python 与 Node 依赖分别由 `uv.lock` 和 `package-lock.json` 恢复。真实麦克风 final、真实 `chat.tool_call/tool_result/final`、实际 TTS、10 Turn、10 次打断、20 分钟和连续 3 次脚本是 Demo 放行闸门。服务端 generation ID、全双工/AEC、Team、多语言、WebView2 和流式 TTS 是后续生产化工作，不是本轮阻塞项。
- 原因：受控环境足以验证“语音驱动真实 Agent 并可打断”的核心产品命题；把兼容矩阵和正式一致性协议塞入两周会稀释验证目标，但跳过真实端到端又会让 Demo 失去证明力。
- 影响：另一台机器必须按 `E2E_RUNBOOK.md` 重建依赖并重新验证机器私有状态。API key、Slack token、用户配置、浏览器 profile、`.venv` 和 `node_modules` 不进入 Git。
- 重新评估条件：纵向 Demo 放行，开始 Alpha/生产化规划时。

## D-015 浏览器识别实例边界不等于用户语音 Turn 边界

- 日期：2026-08-01
- 状态：Accepted
- 背景：Chrome 可能在用户已经说出部分内容后约 4 秒自然结束 SpeechRecognition，也可能在初始静默期提前报告 `no-speech`。直接把每次 `onend` 当成 Turn 结束会截断尾段或迫使用户抢话；无条件重启又会让 manual stop 复活。
- 决策：Live Voice 维护独立的逻辑 capture。浏览器实例自然结束且已有结果时，可在相同 capture 内续启并合并 final/interim 尾段；初始静默窗口固定 8 秒，有结果后的结束语音窗口为 2.2 秒；manual stop、自动 stop 和终止错误禁止 retry。最终仍由 core 保证一个 capture 最多提交一次。
- 原因：受控真机中该路径成功完整识别“调用终端查看当前分支”，同时精确静默测试在 8 秒阈值前保持 Listening。
- 影响：这是 Browser Speech 的 Demo 适配，不是 Provider-neutral VAD/EOT。技术词识别准确率仍由浏览器 Speech 服务决定，`git` 已出现“地图/史记”误识别。
- 重新评估条件：切换正式 Speech Provider，或建立统一 Streaming STT/VAD/EOT 协议。

## D-016 Live Voice 启用期间取得唯一可听输出所有权

- 日期：2026-08-01
- 状态：Accepted
- 背景：Live Voice 使用浏览器 SpeechSynthesis，旧聊天路径仍可能异步调用服务端 `tts.synthesize`，历史消息也有独立的手动朗读入口。仅在服务端请求开始时检查模式不足以阻止较早请求返回后双重播放；React 重渲染也可能产生交叠 owner。
- 决策：Live Voice 启用时取得进程内 TTS owner token，并通过全局 stop 终止已有浏览器或生成音频；服务端 TTS 在请求前取得 revision ticket，并在音频返回后再次验证；历史消息手动朗读在开始播放前检查同一 owner。任一 Live Voice owner 存在时不启动其他已知 TTS 路径；owner 获取前已在途的旧响应即使之后释放 owner 也永久失效。多个 token 必须全部释放后才能恢复服务端路径。
- 原因：该机制以很小范围保证当前单浏览器 Demo 只有一个可听输出源，并能纯逻辑验证旧异步响应不会复活。
- 影响：Live Voice 激活时点击历史消息朗读不会启动播放。owner/revision 只存在当前前端进程，不提供跨 tab、跨设备、断线或服务端播放一致性，不能替代正式 response/generation ownership。
- 重新评估条件：建设正式 Conversation Runtime、统一 TTS 播放器和 presented-history 协议。

## D-017 显示文本保持原样，Live Voice 使用完整且可朗读化的副本

- 日期：2026-08-01
- 状态：Accepted
- 背景：普通 TTS 的历史默认会在 500 字截断并省略路径/行内代码；`zh-CN` 系统音色又可能跳过 `hx/0731_live_voice_ux` 一类斜杠、下划线和连续字母数字。直接改 chatStore 内容会破坏用户看到的真实 Agent 回答。
- 决策：普通 `sanitizeTtsText` 的 500 字默认和既有行为保持不变。Live Voice 从完整 assistant 消息生成独立朗读副本：保留需要听到的路径和行内代码，去除显示用 Markdown，把技术分隔符转成可听词并拼读短缩写/数字；随后以约 220–300 字按句末优先分片，key 为 `${message.id}:${chunkIndex}`，全部进入同一 `responseEpoch` FIFO。
- 原因：2026-08-01 真机中用户确认完整听到分支名中的斜杠、数字和下划线；纯逻辑测试同时保证普通中英文不被无差别改写、长回答不丢失且片段可无损拼接。
- 影响：当前仍是完整消息到达后的浏览器分片朗读，不是 token/audio streaming TTS；朗读副本为了可听性可以与页面标点形式不同，但语义和显示事实不能被改写。
- 重新评估条件：引入正式 TTS Provider、SSML/发音词典、流式音频和播放确认。

## D-018 只保留一条累计演进路线，不另建全功能模拟 UX 原型

- 日期：2026-08-01
- 状态：Accepted
- 背景：V0 可以用临时实现快速打通主流程，但若再建立一套覆盖全部功能、主要依赖 hardcode 或模拟状态的独立 UX/Vision 原型，会形成第二套事实来源，消耗两周时间，并可能展示正式工程无法继承的效果。
- 决策：两周产出定义为 V0 Vertical Slice Demo——核心体验旅程完整，但不要求所有最终功能完整。之后在同一条真实工程路径上累计演进为 V1/P1 Product Alpha、V2/P2 Realtime Alpha、V3α/P3α Task Alpha、V3 Full Capability Beta，最后进入 RC/Production hardening；不单独建设“覆盖所有功能但都不正式”的模拟 UX 版本。每个新版本包含前一版本已验证的能力，并用正式模块逐步替换 Demo shortcut。
- 原因：纵向切片更早暴露真实 Agent、工具、取消、音频和状态耦合；累计替换避免 Demo 与生产效果来自两套机制。V2 引入实时媒体、流式语音和自然插话，是最明显的实时语音感知跃迁。
- 影响：共享事件契约、response ownership 和状态边界冻结后，P1/P2/P3 的部分工程可以并行，但版本放行仍按依赖顺序累计。P3α 只包含 create/get/list/status/cancel/events 与 D0；正在运行的后台任务从 A 改为 B，需要完整 P3 的 update/provide-input，或显式 cancel/create，不能用状态查询冒充更新。V3 只有在 P1/P2/完整 P3 都是真实实现时才接近正式版，并仍需 RC 的可靠性、安全、兼容性和运营加固。
- 重新评估条件：真实验证证明某个阶段边界无法独立验收，或正式实现必须改变共享协议顺序。

## D-019 V0 按 final 时的 processing 状态区分 supplement 与朗读中止

- 日期：2026-08-01
- 状态：Accepted
- 背景：当前 TTS 只朗读已经完成的 assistant 消息；此时 Agent 通常已经不再 processing。旧文档把 thinking、tool 和 speaking 中的“打断”都称为 supplement，会把本地停声后的普通下一轮误报成 Agent 中断成功。
- 决策：重新开麦始终先停止本地 TTS。新 final 到达时若 `processing=true`，通过 `chat.interrupt(intent=supplement)` 提交；若 `processing=false`，通过普通 `chat.send` 提交。V0 验收保留 10 次用户可感知打断，固定为 3 次 thinking、4 次 tool 和 3 次 speaking：前 7 次必须有真实 supplement 路由证据，后 3 次必须验证本地停声后恰好一次普通 `chat.send`。分别报告 `true_supplement_pass_count` 和 `speaking_playback_stop_pass_count`，不得写成“10 次 supplement”。
- 原因：这与当前代码和用户实际感知一致，也能分别验证处理中纠正与朗读中止，而不夸大服务端 cancel 能力。
- 影响：thinking/tool 时开麦但 final 前 processing 已结束的样本必须重分类，不能计入 supplement；Gateway ACK 仍不代表旧 Agent/工具已确定停止，V0 只使用可核对的只读工具并记录迟到 result、warning 和副作用。
- 重新评估条件：P1/P2 建立统一 response/generation lifecycle、流式 TTS 和显式的 stop-speaking / cancel-response / cancel-work 语义。
