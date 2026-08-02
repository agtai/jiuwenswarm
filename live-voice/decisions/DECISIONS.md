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
- 状态：Accepted（仅适用于 V0；Post-V0 范围由 D-020/D-024 扩展）
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
- 状态：Accepted（仅适用于 V0 原始排期；Post-V0 范围由 D-020/D-024 扩展）
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
- 状态：Accepted（单一累计路线保留；两周范围由 D-020 扩展，版本命名由 D-021 取代）
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

## D-020 Post-V0 两周目标覆盖全部能力类别，但不建立第二套假 UX

- 日期：2026-08-01
- 状态：Accepted（两周范围部分取代 D-018；“单一累计工程路线”继续保留）
- 背景：V0 已形成可恢复 Candidate，新的目标是在不等待人工麦克风验收的开发窗口内，尽量提高两周 Demo 的能力覆盖，同时继续以最终正式交付为终点。只做 V0 稳定性会错过 P2/P3 方案级验证；另建一套全功能模拟 UX 又会产生与正式工程脱节的第二事实来源。
- 决策：Post-V0 两周 Demo 必须让 P1、P2、P3、Context、Progress、Failure/Degradation 和 Observability 等能力类别均有可演示的纵向路径。难点可以采用固定口令、固定环境、Browser Speech、显式打断、单任务、loopback/fault injection 或 cancel+successor 等替代，但真实输入以外的 Agent/Tool/任务 ID/状态/结果不得 hardcode；未实现能力必须明确显示 `Demo substitute`、`unsupported` 或 `unknown`。所有切片仍进入同一产品代码和可替换接口，不单建假 UX。
- 原因：这既能在两周内验证整体产品方案、模块边界和用户效果，又让 Contract、Bridge、Reducer、Adapter、状态投影和测试继续成为正式版资产。替代实现暴露在接口边界和 Shortcut Ledger 中，可以逐个被正式模块替换。
- 影响：D-018 中“V0 两周只回答核心体验”的范围不再是 Post-V0 两周上限；V0 自身的 Released Gate 和证据口径不变。测试 fake 只用于自动化和故障注入，不能作为展示成功证据。A→B 在完整 P3 前只能真实执行 cancel A + create successor B，并显示两个 task ID，不能称为原地更新。
- 重新评估条件：某个替代无法提供真实可核对结果、会引入不可接受副作用，或阻碍正式模块接替。

## D-021 版本号与 P1/P2/P3 架构 Phase 解耦

- 日期：2026-08-01
- 状态：Accepted（更正 D-018 的版本命名，不改变完整方案中的 Phase 定义）
- 背景：完整方案定义 P1 为 Speech I/O，P2 才包含 Conversation Runtime、Realtime Media、Interaction Intelligence 和 Agent Bridge；旧路线把 `V1/P1` 写成 Conversation Runtime，造成版本里程碑与架构 Phase 错位。
- 决策：后续命名为 V1 Foundation Alpha（P1 Speech Port + P2 最小 response/generation lifecycle 基础）、V2 Realtime Alpha（正式 P2）、V3α Task Alpha（P3α）、V3 Full Capability Beta（P1 + P2 + 完整 P3），最后进入 RC/Production。版本用于累计交付，P1/P2/P3 用于架构能力面，两者不再用斜杠强行一一对应。
- 原因：response identity 和 cancel/fence 是继续开发流式语音、插话和任务通知的共同前置，但其权威属于 P2；同时 P1 Speech Port 可以与这部分基础并行。解耦后既符合完整方案，也不会人为串行所有工作。
- 影响：旧文档中的 `V1/P1 Conversation Runtime`、`V2/P2 正式 Speech Port` 均应按新表修正；共享 Contract Gate 通过后，多个 Phase 的工作包仍可并行，版本放行仍累计验收。
- 重新评估条件：完整方案正式修订 P1/P2/P3 边界。

## D-022 V0 验收前的 Post-V0 开发保持可整体 stash

- 日期：2026-08-01
- 状态：Superseded by D-030（历史临时工作流；V0 未放行和禁止破坏性 reset 的约束仍有效）
- 背景：用户计划在稍后介入时先 stash 新开发，再验证和冻结 `2c700934` 的 V0 Candidate，之后恢复并验证新开发。commit 无法被 stash 隐藏，直接提交到当前分支会改变待验收基线。
- 决策：在用户发出“停止并准备验收 V0”前，Post-V0 代码、测试和文档保持未提交、不 push，并持续保证 `git diff --check`、相关自动化和精确 dirty-file 清单可用。停止时用包含 untracked 文件的命名 stash 隔离，确认 HEAD 仍为 `2c700934` 后验收 V0；冻结 V0 后再 apply 新开发。不得用破坏性 reset 代替该流程。
- 原因：这严格保留用户指定的验收顺序，并使 V0 Candidate 随时可恢复。自动测试和文件清单降低较大未提交工作集的风险。
- 影响：此窗口内 Git 远端不能恢复尚未提交的 Post-V0 进度；跨机器接续必须等用户完成 stash/冻结/恢复并允许提交。该例外结束后恢复常规“小步提交并推送”规则。
- 重新评估条件：用户改变验收工作流，或明确授权使用独立 Post-V0 分支/checkout 提交。

## D-023 Post-V0 稳定句预读只消费 chatStore，并默认关闭

- 日期：2026-08-01
- 状态：Accepted（仅在独立 feature flag 开启时扩展 D-012/D-019；V0 默认口径不变）
- 背景：完整消息后朗读可靠但首音较晚。直接订阅 `chat.delta` 会绕过 chatStore、supplement quarantine 和可见消息事实；即使 chat delta 通常追加，`chat.final` 仍可能重写文本，已经播放的内容无法撤回。
- 决策：新增纯逻辑稳定句 planner，仍只观察 chatStore 中当前语音 Turn 的唯一 streaming assistant 消息。只有完整句末后已出现下一句非空 lookahead、内容追加式、message ID/responseEpoch 稳定且没有未闭合代码围栏时才提前释放；final 的可朗读副本必须以已播前缀开头，只补 suffix。提前朗读前发生 rewrite 时退回 final-only；提前朗读后发生 mismatch 时立即失效 FIFO、停止预读并提示以页面文字为准，绝不整段重播。功能由 `VITE_FEATURE_LIVE_VOICE_STREAMING_SPEECH=true` 开启，默认关闭。
- 原因：该路径能显著提前 Demo 首音，同时保留现有 chatStore 事实、quarantine 和 core epoch 防线；保守 lookahead 与 final 对账把重复朗读风险放在实时性之前。独立开关保证 apply Post-V0 工作后不会静默改变 V0 的验收行为。
- 影响：这只能称为 sentence preview，不是 token/audio streaming TTS，也不能证明用户确实听到（尚无 playback cursor/ACK）。开关开启后 speaking 可能与 `processing=true` 重叠，因此 speaking 时新 final 可能是真实 supplement；D-019 的“3 次 speaking 均普通 chat.send”只适用于 flag-off 的 V0 验收，Post-V0 必须按 final 时实际 processing 状态重新分类。
- 重新评估条件：正式 P2 提供 response/generation ID、streaming TTS、播放 ACK 和 presented history，或真实 chatStore 流表现证明 lookahead 仍不稳定。

## D-024 Post-V0 任务演示只开放受限 AutoHarness，并默认关闭

- 日期：2026-08-01
- 状态：Accepted（Demo substitute；不是完整 P3）
- 背景：现有 `schedule.run/status/cancel` 可以最快验证“语音会话控制独立后台任务”，但它连接的是 AutoHarness 演进任务，会生成或修改本地 Harness package；把它包装成“只读检查仓库”会隐藏真实副作用，也无法验证通用 Task Control。
- 决策：任务路径由独立 `VITE_FEATURE_LIVE_VOICE_TASK_DEMO=true` 开关启用，默认关闭。只拦截 committed final 的高特异中文口令；普通语音继续进入真实 Chat/Agent，interim/uncommitted 不得发请求。create、cancel 和 replace 必须包含显式“确认”；启动/替换允许受控的 `：/:/，/,/空格/口述冒号` 分隔符和固定命令句末标点，以适配真实 ASR，但不接受通用“检查进度”。固定使用 `extended_evolve_pipeline`，并在用户可能执行任何口令前常驻显示 executor、pipeline、代码副作用、Live Voice 打断/退出不取消任务、刷新/切 Session 丢失语音任务记忆等边界。页面显示真实 `task_id` 和后端原始状态。查询只针对桥内最后一个真实可见任务；A→B 必须先确认取消 A，再创建带新 ID 的 successor B，任一步失败都如实显示，不能宣称原地更新。
- 原因：固定执行器和口令能在两周内验证任务 ID、生命周期、状态回流、取消、继任关系和语音反馈，同时不伪造结果。独立开关与确认口令避免 apply Post-V0 工作后静默触发有副作用的后台执行。
- 影响：这一切片不提供任务持久恢复、多任务消歧、通用只读 Executor、list/get/events、D1/D2 durability、update/provide-input/pause/resume/reprioritize，也不能证明完整 P3。capture 期间切换 Session 会以零请求失效；在 `new` Session 只给出 requires-session 反馈。刷新页面或切换 Session 后内存中的 `lastVisibleTask` 和未知变更 latch 不再可用。最初的 project/context 缺口已由 D-028 的 task-scoped context 和 execution target 缩小，但持久 Task Control Core、跨重启执行上下文和完整 model/permission provenance 仍未完成。
- 重新评估条件：通用 P3α Executor/Task Store 可用，或 AutoHarness 的副作用范围不再适合受控演示。

## D-025 稳定句预读只把权威 chat.final 当作最终对账边界

- 日期：2026-08-01
- 状态：Accepted（仅在稳定句预读开关开启时生效）
- 背景：`chat.processing_status(false)` 可能先停止消息的 visual streaming，真正 `chat.final` 稍后才到。只检查 `isStreaming=false` 会把 provisional delta 误当 final，提前回听或重复播放；`chat.final` 还可能 collapse 为新 message ID、同 ID 修订或形成多个工具分段。
- 决策：feature-on 时，WebSocket `chat.final` 完成同步的 content update/add/collapse 后，通过一个微任务对当前 user Turn 的所有 assistant 消息一次性写入 `isResponseFinal`；message gate 只有看到该标记才做 final 对账。planner-owned final 即使已入队、同 ID 修订或内容为空也持续可观察；collapse 后 ID 变化、多段 final topology、final suffix、pending/active speech 和 `processing=false` 先到均由纯逻辑 fence 处理。若 processing 已停止、临时朗读队列完全 drain、同 epoch planner 仍等待权威 final，则启动一次 10 秒 grace period；到期后废弃该 epoch并显示可 Retry 错误，绝不把 provisional 当 final、补造文本或重播。final、mismatch、processing 恢复、新 capture、Session 切换、退出和卸载都会取消或隔离旧 timer。feature-off 不写标记、不启动 timer、不增加 store 更新，V0 D-012/D-019 行为不变。
- 原因：这把“停止流式显示”和“收到权威最终响应”拆成两个事实，并避免 React 在 provisional content 与最终 topology 之间启动下一次 capture。
- 影响：标记和 10 秒 recovery 仍是当前单 session/单 response Demo 关联，不包含服务端 response/generation ID。并发 cron/proactive/迟到旧 final 可能误盖当前 Turn；timer 只能避免永久 thinking，不能证明响应归属或恢复未确认文本。正式版必须用 generation provenance、协议级 final deadline、播放 ACK 和 presented history 替换。
- 重新评估条件：P2 Conversation Runtime 提供正式 response lifecycle，或后端保证每条可见 message 自带不可歧义的 generation/final metadata。

## D-026 schedule API 在单进程内以持久状态为真值并串行同任务取消

- 日期：2026-08-01
- 状态：Accepted（Post-V0 Demo 安全切片；不是正式 Task Control Store）
- 背景：`schedule.run` 的 immediate trigger、调度循环 claim、任务快速终态、cancel/delete 和 execution history 存在竞态；旧实现还可能在启动失败时返回 running、重复取消并追加重复 history，或让删除后的 claim 继续启动。
- 决策：create/run 共用非空 query、有限正 interval 和 pipeline allowlist；run 根据持久任务状态区分 claimed/running、快速 success、failed、cancelled 和真正启动失败，不能用无 error 响应冒充成功。cancel 后重读状态，已成功任务不覆盖为 cancelled；同一 task 的并发 cancel/cancel 和 cancel/delete 合并到共享 cancellation operation；delete 必须 fence pending/running claim，execution history 按 execution ID 幂等 upsert；cancel/delete 不获取 Agent。旧空 query claim 清理并标 failed。
- 原因：受限 Task Demo 至少必须显示来源真值，不能因单进程竞态伪造“已启动/已取消”，也不能让相同取消生成冲突 history。
- 影响：这些保证仅覆盖当前单进程 Scheduler/JSON TaskStore。没有跨进程 CAS、原子 claim、版本化条件更新；`to_thread` 持久写在 shutdown/二次 cancellation 下仍可能迟到覆盖。正式版必须采用持久事件存储、幂等 command、条件更新和 reconciliation。
- 重新评估条件：迁移到 P3 Task Control event store，或 Scheduler 支持多实例执行。

## D-027 前端未接入可恢复幂等创建时，结果不明必须阻止重试

- 日期：2026-08-01
- 状态：Accepted as fallback（foundation 已用稳定 command ID、同-key retry 和 exact-key reconciliation 缩小触发范围）
- 背景：`schedule.run` 有真实副作用。该决策形成时，后端已经增加可选 idempotency key，但 Live Voice 前端尚未生成/持久化 key 或接入 list reconciliation；请求可能已经创建任务，但前端在 response 前超时/断线，或收到无效 payload、缺失/冲突 task ID。把它显示为普通失败并允许重试仍会制造不可见 orphan/duplicate。
- 决策：上述结果进入内存 `mutation-unknown` latch，明确提示“任务可能已创建，勿重试；当前没有可跨刷新的 Web 任务列表恢复入口，保留页面与后端证据并由受控运维核对真值”，并阻止当前桥后续 create/replace。没有可见 task ID 时，status/cancel 也保持 `mutation-unknown`，不能降级成“没有任务”。cancel response 即使带业务 error，只要 task ID 匹配，也先保存其真实终态。任务反馈朗读可以在无关 Agent 仍 processing 时独立恢复监听，但不能把本地打断解释为 task cancel。
- 原因：在没有幂等创建和 list/reconciliation 前，宁可停止语音侧任务 mutation，也不能把网络不确定性转成重复真实副作用。
- 影响：latch 只在当前页面/Session 内存中，刷新后仍会丢失；它是两周 Demo 的保守防线，不是 durability。D-029 已提供单进程服务端幂等地基，但正式路径仍需要持久 client command ID、task list/get/events 和 orphan reconciliation。
- 重新评估条件：Live Voice client 接入 D-029 的幂等 key 与 scoped reconciliation，并能按 command ID 恢复真实结果。

## D-028 schedule 执行上下文与目标必须按任务冻结

- 日期：2026-08-01
- 状态：Accepted（Post-V0 P3α 地基）
- 背景：singleton Scheduler service 在每次 run 覆盖共享 `_agent`，会让并发 Session 的后台任务借用最后一个 Agent；仅保存 query/task ID 也无法证明任务实际作用于哪个聊天项目。前端若从临时 cwd 或不匹配的注册项目猜路径，会把副作用发往错误目标。
- 决策：AgentServer 使用同一个解析后的 `project_dir` 创建 Agent 并构造 `execution_target`。Scheduler 为每个 task ID 注册独立、不可变的进程内 Agent/context；周期任务沿用，单次终态、取消、删除和 service stop 释放。两个 Session 并发不得共享 context；进程重启后没有旧 context 的 pending 任务必须明确失败，禁止借用新 Agent。任务持久化并返回 `project_dir`、`project_id`、`origin_session_id`、`origin_channel_id`；遗留字段显示 unknown，不猜测。前端只从当前 persisted Session 与精确匹配的已注册项目解析绝对 target，无法从 persisted Session 与精确注册项目解析 target 时 fail closed；capture 中 session、target 或 bridge identity 改变时零请求失效，run/status/cancel 均携带冻结 target 并在 UI 显示 provenance。
- 原因：真实副作用任务首先必须回答“由谁、从哪个会话、作用于哪个项目”，而且排队后不能随全局 Agent 变化。诚实失败比重启后静默借错 Agent 安全。
- 影响：解决当前进程内多 Session 串 context 和 project target 猜测，但 Agent/context 仍不可跨重启恢复；`execution_target` 还不是完整 model/provider/config/permission 快照，也不等于授权决策。正式版仍需可持久恢复的执行上下文和权限 provenance。
- 重新评估条件：P3 Executor 能从版本化、加密的持久上下文安全重建 Agent，或任务迁移到独立 worker/queue。

## D-029 D0 创建使用服务端 owner scope 下的持久幂等 ledger

- 日期：2026-08-01
- 状态：Accepted（单进程/JSON 边界；不是 exactly-once）
- 背景：有副作用的 `schedule.run` 在 response 丢失后无法区分“未创建”和“已创建但响应丢失”。只靠前端内存 latch 能防止立即重复，但刷新后丢失，也不能为未来 reconciliation 提供稳定 command identity；同时不能信任客户端自己声明跨用户 owner scope。
- 决策：`schedule.run` 接受可选 `origin_namespace` 与 `idempotency_key`，owner scope 由 AgentServer 根据 Web request 的 channel/session/可用 app identity 字段派生；按 D-033，它不是已认证身份。TaskStore 在单进程锁内以 scope + namespace + key 原子 get-or-create，并把标准化 intent fingerprint、task ID 和删除 tombstone写入 JSON `create_commands` ledger。同 scope/key/intent 重放返回原 task ID 且只触发一次；同 key 不同 intent 返回 `IDEMPOTENCY_CONFLICT` 和 `existing_task_id`，不得返回新 `task_id`。JSON reload 后保持语义，删除不释放 key；`schedule.list` 可按 scope/namespace/exact key 筛选。replay/conflict 路径释放本次候选 Agent pin/context；无幂等字段的旧客户端保持原行为。
- 原因：这提供 D0 可测试的稳定 command identity，并避免把客户端可伪造 namespace 当作租户边界；tombstone 防止删除后相同 key 意外生成第二个副作用任务。
- 影响：只保证同一进程、同一 JSON store 路径内的原子性和 JSON reload 重放，不保证多进程 CAS、crash transaction、exactly-once、唯一执行 owner 或外部副作用 reconciliation。后续 foundation 已把稳定 command ID、同-key retry、严格 exact-key reconciliation 和 list/status/cancel/logs/delete 的单用户请求一致性 scope 接线；D-027 只在记录不唯一、identity/target 冲突或结果仍不可证明时继续 fail closed。
- 重新评估条件：迁移到支持唯一约束/条件写的正式 Task Control store，或 Live Voice client 完成持久 command journal 与 reconciliation。

## D-030 结束临时 stash 窗口，固定 V0 Candidate 后正常提交 Post-V0 增量

- 日期：2026-08-01
- 状态：Accepted（取代 D-022 的临时工作流；不改变 V0 Released Gate）
- 背景：D-022 已完成其隔离目的：全部 Post-V0 增量保存为命名 stash，工作区回到 `2c700934`。用户随后明确调整顺序，要求暂缓 V0 人工验收，先保留 stash、恢复增量，只收尾任务身份、幂等、执行目标和前端任务卡等基础门槛并提交，再推进“前台持续在线 + 后台非阻塞工作 + 结果异步回流”。继续把大量已验证代码只放在单机 stash 会妨碍跨机器恢复。对应 stash commit 为 `7f4cfd2eedfb3a177b94f69417143fba441f3671`。
- 决策：`2c700934aa0024a7ab229644bf15934e9e8170e7` 永久作为 V0 精确恢复点；当前状态是未放行 Candidate，完整 Gate 通过后可以把同一 SHA 标记 Released；`7f4c...` 已 `apply` 且原 stash 作为额外备份保留，不 `pop/drop`。完成自动化和审阅后按逻辑切片正常 commit 并推送。后续提交全部属于 Post-V0，不得并入 V0 验收证据，也不得仅凭 Post-V0 提交把 Candidate 改称 Released。稍后验收 V0 时，从 `2c700934` 的独立 checkout/worktree 启动固定环境，不再要求把当前开发分支反复 stash 回旧基线。
- 原因：不可变 commit 已足以精确复现 V0；把后续工作提交到同一累计分支既保留 Git 可追溯性，又让其他机器仅靠 fetch/pull 和仓库交接文档无损续作。保留原 stash 直到恢复增量已提交、推送并能从远端重建，仍提供一次额外回滚保险。
- 影响：D-022 中“Post-V0 不 commit、不 push”的限制结束；D-022 对 V0 未放行、禁止破坏性 reset、验收必须使用精确基线和完整 Gate 的要求继续有效。当前收尾范围不扩成完整 P3：不实现跨进程 CAS、exactly-once、D1/D2、重启后 Agent context 恢复、update/provide-input/pause/resume/reprioritize 或通用多任务控制。
- 重新评估条件：远端分支无法安全保存累计开发，或 V0 验收发现 `2c700934` 本身不可复现，需要重新建立 Candidate。

## D-031 下一切片用轮询实现前台持续在线、后台非阻塞与结果异步回流

- 日期：2026-08-01
- 状态：Accepted（当前下一实现切片；恢复、终态和安全边界由 D-033/D-034 补充）
- 背景：Task Foundation 已具备真实 task ID/target/provenance、单用户请求一致性 scope（非生产鉴权）、per-path single-process JSON 幂等、前端稳定 command ID、同-key retry、严格 exact-key reconciliation 和真实任务卡。但 `schedule.run` 返回“已持久/已接管”不等于任务完成；当前语音路径仍以一轮反馈为中心，不能展示“用户继续交谈，后台任务独立运行，完成后结果回来”的核心 P3α 感知效果。直接建设完整 TaskEvent store/push/replay 会扩大成本并混入完整 P3。
- 决策：新增独立于 chatStore 的 task projection/monitor。真实派发并取得或对账出 task ID 后，Live Voice 前台立即恢复可监听状态；monitor 以 `schedule.status` 轮询真实任务状态，同一页面内的断线重连/不确定恢复只使用 owner/namespace/exact-key 的 `schedule.list`；整页刷新在持久 command journal 完成前明确 unsupported。同一任务最多一个 in-flight poll，所有迟到 promise 必须受 task/session/target/monitor generation fence；断线暂停，连接恢复立即 reconcile；terminal、删除、feature flag 关闭、provenance 不匹配或卸载后停止。
- 决策：任务卡始终显示后端实际提供的 terminal 状态与现有事实字段，不得虚构自然语言结果或版本化 outcome。合法 envelope、匹配的 `task_id`、`status`、target/provenance 是必需事实；缺失、非法或不匹配时 adapter 必须失败并保留旧投影。只有可选的 `progress`、`last_error` 缺失时显示 `unknown`。终态语音通知最多一次，且只在来源 Session/target 仍匹配、Live Voice 启用、麦克风关闭、chat 不在 processing/thinking、core/TTS 空闲时播报；它不得抢占麦克风、用户插话或 Agent TTS。若一直没有安全空档，只保留可见结果，不为播报阻塞前台。task monitor 不写 chatStore message，不修改 chat `isProcessing`，不把后台任务状态伪装成 Agent Turn。
- 轮询基线：派发/重连后立即查询；pending 约 1 秒，running 前 30 秒约 2 秒、之后约 5 秒；瞬时错误按 1/2/5/10 秒退避并封顶。状态间隔是 Demo 运维参数，不是生产 SLO，最终实现可在不改变上述安全语义的前提下微调。
- 原因：这一窄切片最大化两周展示价值，同时复用已经完成的 identity、scope、reconciliation 和 task card；它能真实验证“前台不被后台冻结”和“结果异步回流”，又不会把聊天消息、TTS 或假进度作为任务真值。
- 影响：本切片仍不是服务端 TaskEvent push/replay、跨设备 unread、多任务自然语言消歧、update/provide-input/pause/resume/reprioritize、跨进程 exactly-once、D1/D2 或完整 P3。后续正式 Task Control 可以用事件订阅与持久 projection 替换轮询，而不改变 task identity、scope、UI 投影和播报仲裁边界。
- 重新评估条件：`schedule.status/list` 无法在受控负载下提供可靠真值，或正式 TaskEvent 订阅在同一时间窗口内可直接复用而不扩大完整 P3 范围。

## D-032 每个模块必须以开发前/开发后双回顾和完整场景 tests 闭环

- 日期：2026-08-02
- 状态：Accepted（从 D-031 起强制执行；不改变 V0 Candidate 的独立放行 Gate）
- 背景：现有 Foundation 的 Python `226/226`、Live Voice `155/155`、相关回归 `24/24` 能证明对应 suites 在当时最终代码上通过；155 与 24 两组有 9 项重叠且 Git 未保存 JUnit 产物。测试数量、行覆盖率或纯函数测试无法单独证明模块定义中的所有行为、拒绝路径、竞态、恢复和真实接线均已覆盖。若 tests 只是跟随当前实现编写，还可能把错误行为固化成“预期”。
- 决策：每个模块或逻辑切片在语义开发前、实现完成后各做一次正式回顾。两次都必须重新理解完整方案、当前阶段、模块契约/非目标、上下游、现有 tests 和实际风险，并维护 test inventory、每项 test 的设计原因以及 `scenario → test/evidence` 矩阵。每个改变的不变量必须同时有正向正确场景和反向拒绝场景；反向业务动作必须明确失败、拒绝或安全 no-op，并断言所有禁止副作用为 0，而测试进程本身应 PASS。边界、状态、时序、重复/乱序、并发/重试、恢复、scope/权限、feature flag/降级、协议/持久格式兼容和真实跨模块路径按适用性覆盖；`N/A` 必须说明理由。详细执行规范和记录模板以 [POST_V0_DELIVERY_ROADMAP.md](../roadmap/POST_V0_DELIVERY_ROADMAP.md) §3.1 为唯一权威。
- 决策：只有双回顾齐全、全部必需场景有证据、最终命令在包含全部 code/test 行为输入且相关路径干净的 immutable candidate SHA 上通过、必要 E2E/人工观察完成且无未解释 flaky/必需 gap 时，模块才可标记 `CLOSED`；否则只能是 `PARTIAL` 或 `BLOCKED`。任何后续 code/test/input 变化都会使受影响闭环失效。现有 Foundation 结果保留为历史回归证据，但不能倒写成已经走过 D-032；已有模块在再次修改、作为新切片闭环依赖或进入版本 Gate 前补齐受影响范围。
- 原因：这迫使测试从项目方案和模块定义出发，既证明“应该成功的确实成功”，也证明“不应发生的确实被阻止且没有副作用”，并让新机器或新 Codex 会话能够从 Git 恢复每项测试为何存在、覆盖了什么和还缺什么。
- 影响：D-031 是第一个强制应用切片，编码前先在 `STATUS.md` 固定 monitor 的状态/时序/错误/竞态/flag-off/接线矩阵；编码后在 exact tested SHA 上重审并统一验证。`STATUS.md` 保存详细证据，`HANDOFF.md` 只摘要状态和入口。`V0_ACCEPTANCE.md` 继续独立负责 `2c700934` 的真机 Release Gate，不将 Post-V0 流程倒灌进 V0 证据。
- 重新评估条件：模块边界或交付流程发生重大变化时可以调整模板字段，但不得取消正反例成对证明、反向零副作用、两次回顾、场景可追溯和 immutable tested evidence 这些原则。

## D-033 当前 Web owner/project scope 是单用户请求一致性，不是生产鉴权

- 日期：2026-08-02
- 状态：Accepted（澄清 D-028/D-029 和 Foundation 文档口径）
- 背景：当前 WebSocket 的 session/app/project 等身份值来自浏览器请求。服务端会拒绝必需 owner 字段（`channel_id`、`session_id`）缺失或非法，并比较完整 owner scope；`app_id` 当前允许为空。对已有任务，只校验 stored target 中已知的 `project_dir/project_id`，遗留 unknown 字段不会被猜测。它能阻止正常客户端串任务/串项目，但没有经过认证的服务端主体可以证明这些字段不可由恶意客户端伪造。
- 决策：现阶段一律称为“单用户 Demo 的 request owner + project 一致性 scope”或“防串线边界”，不得写成可信身份、租户授权或生产权限。当前错误 owner 与不存在 task 的错误可区分，因此也不承诺隐藏对象是否存在；但拒绝路径仍不得返回跨 scope 内容或执行控制/修改。它可以继续作为 fail-closed 工程地基；生产放行前必须由认证会话、服务端派生 user/app/session identity、受控 project registry、正式授权/审批策略和存在性隐藏策略接替。
- 原因：防止正常客户端错误与抵御恶意请求是两个安全等级。夸大当前边界会让后续 Task Control、日志读取、取消和删除错误依赖客户端自报身份。
- 影响：当前正反测试仍应覆盖必需 owner 字段缺失/非法、完整 owner scope 不匹配、已知 stored project 字段不匹配、遗留 unknown project 字段和零副作用；这些测试只证明一致性约束。对象存在性隐藏、鉴权、租户隔离、权限升级和攻击面测试另列为 RC/Production Gate。
- 重新评估条件：Web/Gateway 已接入可验证身份并由服务端权威映射项目和权限。

## D-034 D-031 首版限定同页恢复并固定 successor、终态和错误语义

- 日期：2026-08-02
- 状态：Accepted（D-031 编码前约束）
- 背景：当前 Live Voice command ID、未决 mutation 和 task card 都在页面内存中；整页刷新会丢失 identity。`schedule.status` 只提供现有状态/progress/last_error 等字段，尚无版本化 terminal outcome；部分业务错误可能位于 `ok=true` payload。若不先固定这些边界，monitor 会把猜测恢复或业务错误展示成成功。
- 决策：D-031 只承诺同一页面内断线重连和精确 key reconciliation；整页刷新明确 unsupported，直到最小持久 command journal 落地。A→B 中 B 是当前被监控任务，A 保留 cancelled/terminal 卡和 successor 关系。合法 envelope、匹配的 `task_id`、`status`、target/provenance 是必需事实；缺失、非法或不匹配时 adapter 必须失败、保留旧投影且不得播报或触发 task mutation。只有可选的 `progress`、`last_error` 缺失时显示 `unknown`。未识别的新状态保留 raw value、按非终态 `unknown` 处理，不能触发终态通知。
- 决策：后端明确返回 `deleted` 时将其保留为 terminal、非成功的 raw 状态并停止轮询；missing-task/不存在业务错误显示为独立 error/missing 结果、保留最后已知事实并停止自动 mutation/轮询。二者都不能混成“成功终态 unknown”，也不得触发成功播报。后端 TaskStore JSON 与 AutoHarness 运行日志属于 `JIUWENSWARM_DATA_DIR` 下的机器私有运行态；前端 task projection/card、command ID 与 mutation latch 当前只在浏览器页面内存，整页刷新即丢。二者都不随 Git 或换机恢复；V0、累计开发和副作用 E2E 使用隔离目录。正式 WorkProgress 闭环仍需版本化 terminal outcome、持久 projection/journal 与生产鉴权。
- 原因：这是不扩大为完整 P3 的最窄诚实边界，同时让 D-031 的正向、反向、竞态和恢复测试有确定预期。
- 影响：D-031 代码开始前，以上语义必须进入 `STATUS.md` 的 D-032 pre-review inventory/matrix 并形成 checkpoint commit；当前文档决策不表示实现已完成。
- 重新评估条件：持久 command journal、TaskEvent store/subscription 或版本化 WorkProgress contract 提前落地。

> D-035 was intentionally left unused; historical decision IDs are not renumbered.

## D-036 用干净运行时边界的新提交取代旧 V0 Candidate

- 日期：2026-08-02
- 状态：Accepted（取代 D-022/D-030/D-032 中仅把 `2c700934` 作为当前 V0 Candidate/放行目标的部分；这些决策的历史正文、stash 历史、独立验收轨、测试闭环和 Post-V0 正常提交边界保留原文）
- 背景：Gate 1 Attempt 1 在 detached `2c700934aa0024a7ab229644bf15934e9e8170e7` 上真实完成 `chat.send → chat.tool_call → chat.tool_result → chat.final`，但 Agent/Terminal Tool 返回 `2c700934,1`。JiuwenSwarm runtime 在仓库根生成旧候选未忽略的 `.agent_history/`，使工作区从 clean 变为 dirty；该 attempt 必须判定 FAIL，不能因 Agent/Tool 链真实完成而计作 PASS。
- 决策：新 V0 Candidate 固定为 `d4c3e32aa34a4d26b346cdf0396788d39930cd6b`。它的父提交是 `2c700934...`，唯一 diff 是 `.gitignore` 新增三行以忽略 JiuwenSwarm runtime file operation logs 的 `.agent_history/`；不包含 Post-V0 foundation 或功能变化。所有当前 Gate、展示、冷 clone 和新会话期望统一使用短 SHA `d4c3e32a` 与 dirty count `0`。旧 attempt 的 `2c700934,1` 作为失败证据永久保留，不得改写成通过。
- 验证：新候选 checkout 已恢复 clean；Gate 0 已 PASS；Gate 1 固定自动化、TypeScript、Vite build、Ruff、`git diff --check` 与真实文字 Agent/Terminal Tool smoke 已全部 PASS，真实链路返回 `d4c3e32a,0` 且结束后仍 clean。Gate 2–6 尚未因此自动通过。
- 原因：V0 的工具 smoke 本身会运行 JiuwenSwarm；如果正常运行必然污染 Git 工作区，则“真实 Agent/Tool + 工作区 count 0”的验收 oracle 无法在同一候选上成立。将机器运行日志显式排除在源码工作树之外，是最小且可审查的修复，不改变 Live Voice 行为。
- 影响：`2c700934` 仍是新候选的直接父提交和 Attempt 1 历史身份，但不再是当前放行候选。V0 继续在独立 detached `d4c3e32a` checkout、独立 `JIUWENSWARM_DATA_DIR` 和清除 Post-V0 flags 的环境中执行；只有 Gate 0–6 全部 PASS 后才可标记 Released / 已冻结。累计 Post-V0 分支、Foundation、stash 与 V0 证据继续隔离。
- 重新评估条件：新候选再次因仓库内运行时产物或其他可复现缺陷无法保持干净，或完整 Gate 发现必须改变 V0 行为而不仅是运行边界。

## D-037 Gate 3 重复确定性失败必须先建立新 Candidate

- 日期：2026-08-02
- 状态：Accepted（V0 blocker 的最小安全修复；不扩成完整 P3）
- 背景：Gate 3 Attempt 1 的 Turn 3 触发 Git for Windows 非 ASCII 日期格式 OOM；同一用户 Turn 只有一次 `chat.send`，但模型在每个错误结果后重新选择同一 bash 命令，形成 11 次 tool call / 10 次相同失败。现有 CircuitBreaker 默认关闭且阈值过晚。
- 决策：`d4c3e32a` 保留为 Gate 0–2 PASS、Gate 3 Attempt 1 FAIL 的历史 Candidate，不能 Released。必须从该 SHA 建立新 Candidate：在同一 invoke 内，对同 tool name、去 metadata 后同参数、同完整失败签名且 `has_error=true` 的**顺序**重试，第 3 次完成后只 force-finish 一次；默认启用并支持显式关闭/阈值配置。失败签名必须覆盖结构化 nested data 与异常路径，不能复用会丢字段的普通结果哈希。
- 决策：Gate 3 日期语料同时改成明确 `YYYY-MM-DD` 的跨平台安全 oracle，但改题不是 guard 的替代品。代码/tests/config 形成新 immutable SHA 后重跑 Gate 0/1；真人 Gate 3 前按用户要求停止，让用户先调整模型配置。
- 非目标与缺口：本切片不修 Git、不提供任意子进程硬内存/CPU/超时沙箱、不追溯取消同一模型响应中已经并行发出的工具调用，也不降低全局 `max_iterations`。这些是正式交付前继续闭环的资源治理项。
- 原因：重复执行已知高资源失败不增加 Live Voice 证据；低阈值精确熔断能解决本次被证明的放大器，同时把更宽的生产安全缺口如实保留。
- 影响：实现前必须按 D-032 提交并推送 `STATUS.md` 的模块定义、test inventory 和 P/N/B/S/T/C/R/I/F/K/X 矩阵；实现后再做完整回顾、immutable candidate 复跑和证据提交。Gate 3–6 不得由本决策自动通过。
- 重新评估条件：项目提供经过验证的进程级资源硬限制和并行批次取消，或上游 Agent/Tool contract 改变顺序回调与 force-finish 语义。

## D-038 放行 `ee2896a4`，并保留 ASR/模型偏差为非阻塞证据

- 日期：2026-08-02
- 状态：Accepted（V0 Release 验收决策；不改变生产边界）
- 背景：detached `ee2896a4afb186e693c720476b6de10797e66f72` 已在从零建立的隔离环境中完成 Gate 0–6。严格的首次 transcript/格式样本仍暴露“未/为”、技术词、目录名和只回答格式偏差；同时，真实工具事实、打断路由、唯一 TTS、自动回听、降级、soak 和连续主演示均满足受控 V0 核心旅程。
- 决策：将 `ee2896a4` 标记为 `V0 Released / 已冻结`。Gate 3 本次按 owner 明确接受的任务级口径判定：10 个固定只读目标必须最终 10/10 来自真实工具，每个目标最多允许两次语音重试；首次 transcript、错误结果和重试次数必须保留，不能改写成首轮准确率 100%。“只回答 X”的多余措辞和 `YYYYMMDD`/`YYYY-MM-DD` 差异单列为模型遵循问题，只要受控复核的核心工具事实和最终目标正确，不阻塞本次 V0。
- 决策：Gate 4 tool-stage 的等待由 8 秒延长为 60 秒，以稳定命中真实工具执行窗口；动作保持只读，打断仍必须有 `chat.interrupt(intent=supplement)`、Gateway 取消/替代时间线、零旧 UI/TTS 污染和零副作用。Gate 6 接受本次 Codex task 自身的从零环境、全新 detached worktree、lockfile 依赖、全新数据目录和完整实链作为等效恢复证据，不再机械复制到第二个 task；该等效关系必须在证据中显式写出。
- 影响：早期 `2c700934` Gate 1 FAIL 与 `d4c3e32a` Gate 3 FAIL 永久保留；它们不被最终 PASS 覆盖。V0 Released 只冻结 `ee2896a4` 的受控纵向 Demo，不宣称 ASR 准确率、模型格式遵循、生产 cancellation fence、带副作用工具取消、跨环境兼容、全双工或完整 P3 已解决。后续累计分支继续 V1 Foundation Alpha / D-031，不把 Post-V0 代码算进 V0。
- 证据：[evidence/V0_20260802_ee2896a4.md](../evidence/V0_20260802_ee2896a4.md)。
- 重新评估条件：发现证据与 candidate 身份不一致、真实工具结果被伪造、候选无法从 Git 恢复，或任何 Gate 的零污染/零副作用结论被新的可复现证据推翻。

## D-039 Speech Port 负责可替换识别，Native Audio Engine 不成为第二控制平面

- 日期：2026-08-02
- 状态：Accepted（Post-V0 P1 架构与验收方向；实现未开始，不改变 D-031 当前优先级）
- 背景：V0 的真实语音验收稳定打通 Browser Speech、文字 Agent、Terminal Tool、最终回答、TTS 和自动回听，同时反复出现 `未/为`、中文同音字、英文技术词、目录名和数字格式偏差。当前 Web Adapter 固定 `zh-CN`、只采用第一候选并把合并后的 final 自动提交；它证明了纵向价值，但不能代表正式 ASR fidelity。一个否定词错误对工具意图的风险远高于普通字符错误。
- 比较事实：OpenAI 当前公开的原生实时音频模型名为 [`gpt-realtime`](https://developers.openai.com/api/docs/models/gpt-realtime)，可直接消费/生成音频；其可选 input transcription 仍是独立异步 ASR，只应视为输入内容指引，并不保证精确等于原生模型实际听到的内容，见 [Realtime API](https://platform.openai.com/docs/api-reference/realtime)。因此 Native Engine 能提升语气、时延和自然轮转，却不自动提供 JiuwenSwarm 工具链需要的可审计文字契约。
- 决策：继续坚持 D-004 的文字 Agent/Tool 主链。P1 建立 provider-neutral Speech Recognition/Synthesis Port；Browser Speech 是 fallback，专用本地或云端 ASR 是可替换 Adapter，未来 Native Audio Engine 也只能作为声明 capability 的可选 Adapter。任何 Adapter 都不得绕过 committed final、权限/确认、Runtime identity、cancel/fence、工具 schema 和真实结果。
- 决策：Recognition Port 的正式结果至少携带 final transcript、alternatives/confidence（Provider 支持时）、provider、locale、timing、capability 与 fallback provenance。项目领域解析器可以用仓库/分支/路径/工具 schema/当前上下文动态词表和确定性混淆规则重排候选；不能把低置信度纠错静默伪装成原始 transcript。
- 决策：否定词、数字、日期、SHA、路径、分支以及删除/提交/推送/覆盖/重置等有副作用动词是 critical tokens。高置信度只读 Turn 可以直交；关键候选不一致或低置信度时必须澄清；副作用动作继续显式确认并 fail closed。partial、interim、未确认候选对 Agent、Tool 和 Task 的副作用必须为 0。
- 决策：正式对比以任务结果而非“模仿某个竞品”放行。除 CER/WER 外，必须记录 critical semantic error rate、first-pass task success、clarification rate、错误工具派发数、speech-end→commit p95、重复提交和 fallback 一致性。V0 的真实错词类型形成固定回归语料；原始音频只在明确同意的隐私边界内保存和回放。
- 原因：模块化方案不应宣称在情绪、韵律、重叠语音和开放式自然对话上普遍超过原生音频模型；它的可胜维度是代码/任务领域的精确实体、工具安全、可审计性、Provider 可替换和本地化。把 Native Engine 也收进同一 Port，可保留未来体验升级而不分裂 Agent/Tool 权威。
- 影响：D-031 仍是当前下一切片。共享 Contract Gate 后，P1 Speech Port 可按 D-032 独立建立 pre-review、provider fake/conformance、固定语料、正反/降级/隐私场景和 exact-SHA 后置闭环；D-039 不表示任何新 Provider 已选择或质量目标已经达成。
- 重新评估条件：固定语料 A/B 证明单一 Native Engine 在关键语义、工具安全、延迟、隐私和成本的综合指标上持续占优，或 Speech/Runtime contract 改变到可安全合并控制平面；即使重新评估，真实工具权限和副作用确认也不能由音频模型隐式替代。

## D-040 Live Voice 文档采用根目录知识库、单一状态源和按任务渐进阅读

- 日期：2026-08-03
- 状态：Accepted（取代 D-001 的旧 `docs/zh/live-voice/` 位置，并取代 D-032 中继续维护独立 `HANDOFF.md` 的操作方式；历史正文保留）
- 背景：完整文档保证信息不丢失，但把 README、STATUS、HANDOFF、决策、路线和完整方案同时列为每次必读会显著增加恢复成本，并让当前 SHA、里程碑和下一任务在多处重复后发生矛盾。
- 决策：Live Voice 知识库统一放在仓库根 `live-voice/`。根 `AGENTS.md` 只保存 Git 审批、最小 bootstrap 和模块测试闭环等跨任务不变量；`README.md` 是轻量路由；`STATUS.md` 是当前分支、里程碑、已验证事实、缺口和下一切片的唯一可变权威；完整方案、决策、路线、验收、runbook、展示、证据和 archive 按目录保留。
- 决策：文档深度（简要/完整）与读取策略（必读/涉及才读）是正交分类。每个 Live Voice 任务只强制读取根 AGENTS、README、STATUS；普通模块再读相关源码/tests/路线/决策，架构或协议任务才完整读取方案，验收任务才读取验收/runbook/showcase/evidence，文档任务必须读取 `DOCUMENTATION_RULES.md`。
- 决策：删除重复的 `HANDOFF.md`。可变事实只在 STATUS 更新；README 不复制状态；决策只记录选择与理由；不可变 evidence/方案不被事后改写；archive 明确不能覆盖当前状态。移动文档时必须统一修复链接并验证 `docs/zh/live-voice/` 无 tracked 副本。
- 原因：新机器和新 Codex 可以用很小的必读集恢复正确方向，需要细节时仍能进入完整记录；单一权威避免简要版与完整版各自维护同一状态而漂移。
- 影响：旧决策中的历史路径、旧分支和当时状态仍作为历史事实保留，但当前操作必须以根 AGENTS、`live-voice/README.md`、`live-voice/STATUS.md` 和 `DOCUMENTATION_RULES.md` 为准。文档同步不构成自动 commit/push 授权。
- 重新评估条件：仓库出现可自动生成并可靠校验的文档索引/状态投影，或根知识库影响上游文档发布流程。
