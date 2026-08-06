# Live Voice 决策记录

本文件记录已经明确接受的产品和工程取舍。后续 Codex 不应仅因为当前代码更容易而静默改变这些决策；如需改变，应新增决策并把旧决策标记为 `Superseded`。

旧决策的历史正文可以保留，但状态行必须指出被后续决定取代的当前含义；实现进度始终由 `STATUS.md` 提供。

## D-001 方案知识保存在 Git 跟踪的普通文档中

- 日期：2026-07-31
- 状态：Accepted（“知识进入 Git 跟踪文档”的原则保留；旧 `docs/zh/live-voice/` 路径由 D-040 取代，commit/push 操作由根 `AGENTS.md` 的逐次审批规则取代）
- 背景：需要在多台机器上通过 GitHub 同步代码并让新的 Codex 会话快速接续。
- 原决策：完整方案和 Demo 方案保存在 `docs/zh/live-voice/`；D-040 后续把权威位置调整为根 `live-voice/`。不把完整知识仅存入 `.codex`、`.agent`、本地数据库或聊天记录的原则不变。
- 原因：普通 Markdown 可审查、可 diff、可提交、可跨工具阅读；隐藏工具目录容易与某一运行环境绑定。
- 原影响：实质性工作更新 STATUS，新取舍更新本文件；其中自动 commit/push 要求已失效，当前每次 commit 与 push 都按根 `AGENTS.md` 分别取得精确批准。
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

## D-031 下一切片用轮询实现前台持续在线、后台非阻塞与结果异步回流（历史；当前由 D-046 条件化）

- 日期：2026-08-01
- 状态：Accepted（历史设计保留；当前仅为 D-046 的 Day 5/Day 7 条件性 legacy Adapter，恢复、终态和安全边界由 D-033/D-034 补充）
- 背景：Task Foundation 已具备真实 task ID/target/provenance、单用户请求一致性 scope（非生产鉴权）、per-path single-process JSON 幂等、前端稳定 command ID、同-key retry、严格 exact-key reconciliation 和真实任务卡。但 `schedule.run` 返回“已持久/已接管”不等于任务完成；当前语音路径仍以一轮反馈为中心，不能展示“用户继续交谈，后台任务独立运行，完成后结果回来”的核心 P3α 感知效果。直接建设完整 TaskEvent store/push/replay 会扩大成本并混入完整 P3。
- 决策：新增独立于 chatStore 的 task projection/monitor。真实派发并取得或对账出 task ID 后，Live Voice 前台立即恢复可监听状态；monitor 以 `schedule.status` 轮询真实任务状态，同一页面内的断线重连/不确定恢复只使用 owner/namespace/exact-key 的 `schedule.list`；整页刷新在持久 command journal 完成前明确 unsupported。同一任务最多一个 in-flight poll，所有迟到 promise 必须受 task/session/target/monitor generation fence；断线暂停，连接恢复立即 reconcile；terminal、删除、feature flag 关闭、provenance 不匹配或卸载后停止。
- 决策：任务卡始终显示后端实际提供的 terminal 状态与现有事实字段，不得虚构自然语言结果或版本化 outcome。合法 envelope、匹配的 `task_id`、`status`、target/provenance 是必需事实；缺失、非法或不匹配时 adapter 必须失败并保留旧投影。只有可选的 `progress`、`last_error` 缺失时显示 `unknown`。终态语音通知最多一次，且只在来源 Session/target 仍匹配、Live Voice 启用、麦克风关闭、chat 不在 processing/thinking、core/TTS 空闲时播报；它不得抢占麦克风、用户插话或 Agent TTS。若一直没有安全空档，只保留可见结果，不为播报阻塞前台。task monitor 不写 chatStore message，不修改 chat `isProcessing`，不把后台任务状态伪装成 Agent Turn。
- 轮询基线：派发/重连后立即查询；pending 约 1 秒，running 前 30 秒约 2 秒、之后约 5 秒；瞬时错误按 1/2/5/10 秒退避并封顶。状态间隔是 Demo 运维参数，不是生产 SLO，最终实现可在不改变上述安全语义的前提下微调。
- 原因：这一窄切片最大化两周展示价值，同时复用已经完成的 identity、scope、reconciliation 和 task card；它能真实验证“前台不被后台冻结”和“结果异步回流”，又不会把聊天消息、TTS 或假进度作为任务真值。
- 影响：本切片仍不是服务端 TaskEvent push/replay、跨设备 unread、多任务自然语言消歧、update/provide-input/pause/resume/reprioritize、跨进程 exactly-once、D1/D2 或完整 P3。后续正式 Task Control 可以用事件订阅与持久 projection 替换轮询，而不改变 task identity、scope、UI 投影和播报仲裁边界。
- 重新评估条件：`schedule.status/list` 无法在受控负载下提供可靠真值，或正式 TaskEvent 订阅在同一时间窗口内可直接复用而不扩大完整 P3 范围。

## D-032 每个模块必须以开发前/开发后双回顾和完整场景 tests 闭环（历史全量流程；当前由 D-046 风险分级）

- 日期：2026-08-02
- 状态：Accepted（测试从合同出发、正反例、零禁止副作用和 immutable evidence 原则保留；普遍双回顾/完整矩阵流程已由 D-046 的 Tier 0–3 风险分级取代）
- 背景：现有 Foundation 的 Python `226/226`、Live Voice `155/155`、相关回归 `24/24` 能证明对应 suites 在当时最终代码上通过；155 与 24 两组有 9 项重叠且 Git 未保存 JUnit 产物。测试数量、行覆盖率或纯函数测试无法单独证明模块定义中的所有行为、拒绝路径、竞态、恢复和真实接线均已覆盖。若 tests 只是跟随当前实现编写，还可能把错误行为固化成“预期”。
- 决策：每个模块或逻辑切片在语义开发前、实现完成后各做一次正式回顾。两次都必须重新理解完整方案、当前阶段、模块契约/非目标、上下游、现有 tests 和实际风险，并维护 test inventory、每项 test 的设计原因以及 `scenario → test/evidence` 矩阵。每个改变的不变量必须同时有正向正确场景和反向拒绝场景；反向业务动作必须明确失败、拒绝或安全 no-op，并断言所有禁止副作用为 0，而测试进程本身应 PASS。边界、状态、时序、重复/乱序、并发/重试、恢复、scope/权限、feature flag/降级、协议/持久格式兼容和真实跨模块路径按适用性覆盖；`N/A` 必须说明理由。详细执行规范和记录模板以 [POST_V0_DELIVERY_ROADMAP.md](../roadmap/POST_V0_DELIVERY_ROADMAP.md) §3.1 为唯一权威。
- 决策：只有双回顾齐全、全部必需场景有证据、最终命令在包含全部 code/test 行为输入且相关路径干净的 immutable candidate SHA 上通过、必要 E2E/人工观察完成且无未解释 flaky/必需 gap 时，模块才可标记 `CLOSED`；否则只能是 `PARTIAL` 或 `BLOCKED`。任何后续 code/test/input 变化都会使受影响闭环失效。现有 Foundation 结果保留为历史回归证据，但不能倒写成已经走过 D-032；已有模块在再次修改、作为新切片闭环依赖或进入版本 Gate 前补齐受影响范围。
- 原因：这迫使测试从项目方案和模块定义出发，既证明“应该成功的确实成功”，也证明“不应发生的确实被阻止且没有副作用”，并让新机器或新 Codex 会话能够从 Git 恢复每项测试为何存在、覆盖了什么和还缺什么。
- 影响：历史上 D-031 被指定为第一个完整应用切片；当前 D-046 只要求 Tier 2/3 保留适用或完整双回顾，Tier 0/1 使用最小充分证据。详细矩阵进入 dated/module review record，`STATUS.md` 只保存短 dashboard、当前状态和链接；独立 `HANDOFF.md` 已由 D-040 取消。V0 acceptance/evidence 继续独立，不将 Post-V0 流程倒灌进 V0 事实。
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
- 状态：Accepted（D-031 语义约束保留；只有 D-046 Day 5/Day 7 go 后适用，执行流程按当前风险分级）
- 背景：当前 Live Voice command ID、未决 mutation 和 task card 都在页面内存中；整页刷新会丢失 identity。`schedule.status` 只提供现有状态/progress/last_error 等字段，尚无版本化 terminal outcome；部分业务错误可能位于 `ok=true` payload。若不先固定这些边界，monitor 会把猜测恢复或业务错误展示成成功。
- 决策：D-031 只承诺同一页面内断线重连和精确 key reconciliation；整页刷新明确 unsupported，直到最小持久 command journal 落地。A→B 中 B 是当前被监控任务，A 保留 cancelled/terminal 卡和 successor 关系。合法 envelope、匹配的 `task_id`、`status`、target/provenance 是必需事实；缺失、非法或不匹配时 adapter 必须失败、保留旧投影且不得播报或触发 task mutation。只有可选的 `progress`、`last_error` 缺失时显示 `unknown`。未识别的新状态保留 raw value、按非终态 `unknown` 处理，不能触发终态通知。
- 决策：后端明确返回 `deleted` 时将其保留为 terminal、非成功的 raw 状态并停止轮询；missing-task/不存在业务错误显示为独立 error/missing 结果、保留最后已知事实并停止自动 mutation/轮询。二者都不能混成“成功终态 unknown”，也不得触发成功播报。后端 TaskStore JSON 与 AutoHarness 运行日志属于 `JIUWENSWARM_DATA_DIR` 下的机器私有运行态；前端 task projection/card、command ID 与 mutation latch 当前只在浏览器页面内存，整页刷新即丢。二者都不随 Git 或换机恢复；V0、累计开发和副作用 E2E 使用隔离目录。正式 WorkProgress 闭环仍需版本化 terminal outcome、持久 projection/journal 与生产鉴权。
- 原因：这是不扩大为完整 P3 的最窄诚实边界，同时让 D-031 的正向、反向、竞态和恢复测试有确定预期。
- 影响：若 D-046 的 go 决策授权 D-031，Sol 必须先把以上语义重新裁成 1–2 天最小包，并在 dated review/plan 中记录适用的 Tier 2 oracle；`STATUS.md` 只记录当前状态和链接，不要求独立 pre-review checkpoint commit/push。当前文档决策不表示实现已完成。
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
- 状态：Accepted（Post-V0 P1 架构与验收方向；实现未开始；原 D-031-first 排序已由 D-046 取代）
- 背景：V0 的真实语音验收稳定打通 Browser Speech、文字 Agent、Terminal Tool、最终回答、TTS 和自动回听，同时反复出现 `未/为`、中文同音字、英文技术词、目录名和数字格式偏差。当前 Web Adapter 固定 `zh-CN`、只采用第一候选并把合并后的 final 自动提交；它证明了纵向价值，但不能代表正式 ASR fidelity。一个否定词错误对工具意图的风险远高于普通字符错误。
- 比较事实：OpenAI 当前公开的原生实时音频模型名为 [`gpt-realtime`](https://developers.openai.com/api/docs/models/gpt-realtime)，可直接消费/生成音频；其可选 input transcription 仍是独立异步 ASR，只应视为输入内容指引，并不保证精确等于原生模型实际听到的内容，见 [Realtime API](https://platform.openai.com/docs/api-reference/realtime)。因此 Native Engine 能提升语气、时延和自然轮转，却不自动提供 JiuwenSwarm 工具链需要的可审计文字契约。
- 决策：继续坚持 D-004 的文字 Agent/Tool 主链。P1 建立 provider-neutral Speech Recognition/Synthesis Port；Browser Speech 是 fallback，专用本地或云端 ASR 是可替换 Adapter，未来 Native Audio Engine 也只能作为声明 capability 的可选 Adapter。任何 Adapter 都不得绕过 committed final、权限/确认、Runtime identity、cancel/fence、工具 schema 和真实结果。
- 决策：Recognition Port 的正式结果至少携带 final transcript、alternatives/confidence（Provider 支持时）、provider、locale、timing、capability 与 fallback provenance。项目领域解析器可以用仓库/分支/路径/工具 schema/当前上下文动态词表和确定性混淆规则重排候选；不能把低置信度纠错静默伪装成原始 transcript。
- 决策：否定词、数字、日期、SHA、路径、分支以及删除/提交/推送/覆盖/重置等有副作用动词是 critical tokens。高置信度只读 Turn 可以直交；关键候选不一致或低置信度时必须澄清；副作用动作继续显式确认并 fail closed。partial、interim、未确认候选对 Agent、Tool 和 Task 的副作用必须为 0。
- 决策：正式对比以任务结果而非“模仿某个竞品”放行。除 CER/WER 外，必须记录 critical semantic error rate、first-pass task success、clarification rate、错误工具派发数、speech-end→commit p95、重复提交和 fallback 一致性。V0 的真实错词类型形成固定回归语料；原始音频只在明确同意的隐私边界内保存和回放。
- 原因：模块化方案不应宣称在情绪、韵律、重叠语音和开放式自然对话上普遍超过原生音频模型；它的可胜维度是代码/任务领域的精确实体、工具安全、可审计性、Provider 可替换和本地化。把 Native Engine 也收进同一 Port，可保留未来体验升级而不分裂 Agent/Tool 权威。
- 影响：P1 Speech Port 在所消费的 ACG critical kernel 通过后可与 P2/P3alpha 并行；其 review/evidence 深度按 D-046 风险等级执行，并继续覆盖 provider fake/conformance、固定语料、正反/降级/隐私场景和 exact-SHA 后验。D-039 不表示任何新 Provider 已选择或质量目标已经达成；D-031 只在 Day 5/Day 7 go 决策后执行。
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

## D-041 以 Sol 冻结高风险语义并由非 Sol 模型执行有界工作包

- 日期：2026-08-03
- 状态：Partially superseded（风险判断和历史设计职责保留；面向未来任务的非 Sol 执行分工由 D-052 取代，原 D-031-first 排序和普遍 D-032 流程由 D-046 取代）
- 当前解释：以下非 Sol owner、交接和成本分配正文只记录接受本决定时的策略，不能用于分配当前或未来任务。
- 背景：Live Voice 后续同时包含契约、并发状态机、取消与副作用安全、持久化、真机媒体和大量可机械执行的 Adapter/tests 工作。高能力模型额度有限；若让同一模型承担全部编码，会把稀缺推理消耗在已经能够由明确规范驱动的实现上。反过来，若让执行模型自行决定状态权威、错误语义、恢复、权限或测试放行标准，则可能把错误实现固化为预期。
- 优先级决策：P1/P2/P3 是能力平面，不作为简单的串行开发顺序。当前排序以 D-046 为权威：先在 1–2 天内冻结并实现 ACG critical kernel，同时建立累计 Integrated Demo 的 route telemetry 与 Replacement Ledger；随后 P1、P2、P3alpha 和集成轨按已冻结依赖并行。D-031 只保留 Day 5/Day 7 决策点，若正式 `TC-B + TaskEvent/projection` 不能及时进入 Demo，再把最小单任务 monitor 限时为 1–2 个工作日；不再把完整 D-031 作为共享 Contract Gate 和全部能力轨的前置任务。
- 模型职责决策：GPT-5.6 Sol 是指定的设计与审查模型，负责 D-046 风险分级要求的开发前/开发后回顾、模块定义与非目标、适用的 P/N/B/S/T/C/R/I/F/K/X 场景及 test oracle、跨模块 schema/state authority/identity/ownership/cancel/commit/fence/compatibility、安全与 durability 边界、架构变更、证据解释以及 `CLOSED/PARTIAL/BLOCKED` 和版本放行判断。Sol 不承担已冻结规范下的常规执行和实现，除非用户以后明确改变该分工。
- 执行职责决策：代码实现交给非 Sol 模型，例如已配置环境中的 DeepSeek-V4-Flash 或其他执行模型。执行模型适合在所消费的契约、状态转换、scenario IDs、允许与禁止副作用、目标文件和验证命令齐全后，实现 types/ports/reducers/adapters/fakes/conformance、受限 UI/协议接线、测试、fault injection、instrumentation、benchmark runner、打包和机械文档整理。Tier 2/3 或共享契约 `*-A` 工作包由 Sol 冻结 contract/oracle，执行模型落实 types/fake/conformance；其余包按 D-046 的风险等级采用最小充分交接。`*-B`、`*-C` 由执行模型按其实际依赖 Gate 实现和验证，再由 Sol 审查高风险语义与累计证据。
- 停止条件：执行模型不得自行新增或放宽契约、把 `unknown/unsupported/error` 改成成功、改变状态权威或 cancel scope、删除或弱化失败断言、用 snapshot 更新掩盖差异，或把 Demo consistency scope 写成生产安全。发现规范歧义、上下游冲突、需要新状态/错误、测试与设计不一致或无法证明禁止副作用为零时，必须停止该语义分支并交回 Sol；不能凭当前代码更易实现而猜测产品行为。
- 交付约束：Sol 保持完整项目的模块级依赖图，但只详细冻结未来一周的滚动执行队列。每个工作包必须可独立说明和验证；共享同一契约与风险边界的相关包可以共用一次设计 checkpoint、实现批次、post-review 和 commit，依赖已冻结且文件范围不冲突的包可以并行。交接必须包含 authoritative sources、目标与非目标、输入输出、状态与 ownership、scenario→test/evidence、禁止副作用、目标文件、验证命令和明确 exclusions。执行结果保持未提交并报告 status、diff、测试与未决问题；commit 和 push 继续分别遵守根 `AGENTS.md` 的精确批准门。具体模型/provider、凭据、API base 和可用性属于机器私有条件，不写成 Git 可恢复能力。
- 原因：把 Sol 额度沉淀为可复用的契约、状态机、测试 oracle 和审查结论，可以让后续较低成本模型安全地持续实现；同时通过 Tier 2/3 的适用双回顾和 Week 2/Week 4 累计 Gate，阻止高风险执行偏差被测试自洽地掩盖。该策略按风险和依赖分配模型，而不是按文件类型或代码量分配，也不要求低风险机械工作承担完整矩阵成本。
- 影响：Sol 维护完整项目的模块级依赖图和未来一周滚动执行队列；当前 dated queue 由 `STATUS.md` 路由到 [WEEK_1_EXECUTION_PACKAGES_2026-08-03.md](../roadmap/WEEK_1_EXECUTION_PACKAGES_2026-08-03.md)。非 Sol 模型只执行明确标为 `READY` 或其依赖 Gate 已实际通过的有界包；共享 kernel 在被下游消费前由 Sol grouped post-review。D-031 的旧 `B1..B4` 表仅保留为历史设计输入，只有 Day 5/Day 7 go 决策通过后才由 Sol 重新裁成最小当前包。Observability/X-E2E/Windows 真机等证据仍需工具、环境或人工后验，不能由任一模型的文字判断代替。
- 重新评估条件：用户明确更改模型分工；受控对比证明某执行模型可在不降低适用风险等级证据质量的前提下可靠承担某类设计/审查；模型或工具可用性变化；或某切片的风险、合规、安全与生产责任要求升级到需要重新分类。

## D-042 Architecture Contract Gate 采用完整 v2 契约并允许 Sol 先行冻结后续设计

- 日期：2026-08-03
- 状态：Accepted design（“实现尚未开始”只描述接受本决定时的快照；当前实现和 closure 只看 STATUS，交付排序和 review 深度按 D-046/D-053）
- 背景：用户要求把 D-031 的非 Sol 实现内容登记后留空，并在切换执行模型前继续消耗 Sol 额度完成只有 Sol 应判断的工作。完整方案要求下一 Gate 冻结版本化 API/Event schema、interaction/response 与 task 状态机、cancel/fence/presented-history、WorkProgress、ContextRef、依赖 DAG、首个 Provider/Executor 基线和 conformance skeleton。仓库现有 `live-voice.contract.v1` 只是严格最小 Foundation 子集，会拒绝完整 WorkProgress 所需的新增字段；在相同版本名下扩展会改写既有序列化含义。
- 决策：接受 [ARCHITECTURE_CONTRACT_GATE_V1.md](../architecture/ARCHITECTURE_CONTRACT_GATE_V1.md) 为 `ACG-1` 的规范架构产物，完整目标 contract family 定为 `live-voice.contract.v2`。v1 保留为现有 Foundation 兼容输入；只有能够从权威来源补齐完整 identity、scope、sequence、source-event provenance 和 known/unknown facts 的 Adapter 才可升级为 v2，否则返回 `unsupported` 或保留明确标注的 Demo projection，禁止把 v1 重新贴标为完整 v2。
- 决策：冻结精确 authority map、opaque identity/parent/scope、Command/Query/Result/Event envelopes、按 authority stream 的 sequence/dedup/gap 规则、interaction/turn/response 与 task/attempt 状态机、四类不互相升级的 cancel、TurnCommit 零副作用边界、response generation fence、按 surface ACK 的 presented ledger、结构化 WorkProgress provenance/unknown、ContextRef expiry/permission/redaction、capability/error/compatibility 和 feature-off 规则。ACK 不等于 lifecycle terminal，queued output 不等于 presented，task cancel 不等于副作用回滚。
- 决策：首个测试基线使用 deterministic fake Provider/Executor；首个具体 Speech 兼容 Adapter 是现有 Browser Speech 的 P1 batch/fallback 接线，Windows Alpha Interaction 使用 Cascade；首个具体 D0 Executor Adapter 目标是隔离目录/项目中的现有 AutoHarness scheduler + 固定 `extended_evolve_pipeline`。本决策不选择新的云端/Native Provider、凭据、endpoint 或 model，也不把 Browser Speech/AutoHarness 写成正式 Provider/通用 Executor/生产闭环。
- 历史排序与当前解释：D-042 接受时，D-031 B1–B4 尚未执行、A2 post-review 尚缺；允许先冻结 ACG-1 不把 D-031 写成完成。D-046/D-048 现已取代“非 Sol 一次只执行一个包”和“每个包独立完整 D-032”的操作方式：依赖已冻结且文件边界不冲突的包可以并行，coherent group 可以共享 checkpoint/batch/post-review/commit，review 深度按 Tier 0–3；真实 B/C 接线仍必须等待它实际消费的 A-package/consumer Gate。
- 原因：用新 major 显式隔离已落地的最小 v1 与完整架构目标，避免兼容性伪装；先由 Sol 固定跨 P1/P2/P3 的高风险语义，使后续低成本执行模型可以按确定 contract/oracle 编码，而不能从当前 Demo 代码反推产品权威。
- 影响：ACG-1 的设计 Gate 是后续 shared v2 types/fixtures/fakes/conformance 和各消费包适用 review 的输入；它本身不表示任何 v2 code/tests 已实现或通过，不关闭 D-031，不提供生产授权、D1/D2、real-media/Provider SLO 或版本放行。当前 critical-kernel 与消费包边界由 D-046/D-048 和 Week 1 plan 冻结；执行结果、diff、tests/evidence 和未决问题必须等真实执行后记录并交回 Sol 审查。
- 重新评估条件：v2 实现发现无法保持既有 v1 兼容边界；真实 Provider/Executor 能力要求新的 authority/state/cancel/error 语义；安全、法规或多租户要求改变 ScopeRef/ContextRef；或用户改变模型分工与交付顺序。

## D-043 CR-A 用服务端 canonical Runtime 加前端验证 replica 建立 response/generation 基础

- 日期：2026-08-03
- 状态：Accepted design（“实现尚未开始”只描述接受本决定时的快照；当前实现和 closure 只看 STATUS，实际 review 按 D-046/D-053）
- 背景：当前 Web Demo 用前端 `responseEpoch`、message ID/文本边界、`isResponseFinal`、TTS owner 和 supplement ACK quarantine 保护主要 UI/播放路径；Gateway/Agent 事件没有统一的 interaction/turn/response/generation provenance，ACK 在取消完成前即可发出，也没有 playback cursor 或 presented-history ledger。把这些本地标记直接重命名为正式协议，会让迟到 Agent/Tool 副作用、跨连接乱序和历史修复继续没有权威边界。
- 决策：CR-A 的 canonical Conversation Runtime 位于 Gateway/服务端逻辑边界，唯一分配并拥有 `interaction_id/turn_id/response_id/response_generation`、canonical transition、output fence 和 cancel record；前端实现同 schema 的验证 replica、presentation ledger 和 effect router，但不能自行创造或推进服务端 lifecycle。客户端 capture ID、旧 `responseEpoch`、WebSocket `request_id/rid`、chat message ID 和 `isResponseFinal` 均为兼容关联，不得当作正式 identity。
- 决策：response lifecycle 与取消状态正交。`response.cancel` 在 Runtime 接受命令时立即把精确 response tuple 的未来 UI/audio/history output fence 掉并请求 Provider/Bridge cancel，但 response 只有在权威 terminal event 到达后才进入 terminal；ACK、超时或 `RESULT_UNKNOWN` 均不冒充 terminal。新 response 被接受时 generation 必须严格递增并原子 fence 同 interaction 的旧前台 response，但不隐式升级为 `round.cancel` 或 `task.cancel`。
- 决策：`playback.stop` 只关闭精确 response/surface 的 presentation epoch 并请求 Audio owner 返回 ACK/cursor，不改变 response/round/task lifecycle。presented ledger 按 text/audio surface 记录连续 ACK；produced/enqueued、`chat.final` 或 browser utterance `onstart` 均不等于 presented。已 ACK prefix 可保留，未 ACK/fenced suffix 失效；同一已 presented span 不允许被原地 rewrite。CR-A 只产生 history selector/effect，不直接写 `chatStore` 或 Session History。
- 交付边界：CR-A 只实现 v2 types、canonical reducer、前端 replica、纯 cancel/effect routing、presentation ledger、fakes 和 conformance；当前 Chat/Agent path 在新 capability/feature flag 关闭时完全不变。真实 Gateway↔Agent event tagging、Provider cancel、Web/Audio ACK、legacy adapter 和 history write 属于后续 CR-B/AB-A/B/AIO/SS 接线，各自执行 D-046 要求的适用 consumer Gate 和风险证据。
- 原因：一个服务端 canonical owner 才能让客户端重连、Provider callback、Agent stream、cancel ACK 和 Session History使用同一 generation fence；前端 replica 仍能在网络往返前立即静音和丢弃旧输出，同时不会把本地 UX 状态提升为业务真值。
- 影响：CR-A 可以在 ACG shared schema/fixture primitives 可用后交给非 Sol 执行；现有 Demo modules 保留为 feature-off compatibility baseline，不在 CR-A 中原地重构。CR-A conformance 通过也不证明真实 cancel、媒体 ACK、Agent side-effect fence 或 presented history 已接线，不能替代 CR-B/真实 E2E。
- 重新评估条件：部署拓扑无法提供服务端 canonical Runtime；现有 Agent/Harness 不能携带或回传 response/round provenance；跨设备 Runtime 需要新的 leader/lease authority；或真实 playback API 无法提供可验证 ACK/cursor。

## D-044 P1 Speech Port 保留原始假设与展示文本，并把语义决策和播放事实留给各自权威

- 日期：2026-08-03
- 状态：Accepted design（“实现尚未开始”只描述接受本决定时的快照；当前实现和真实 Provider 后验只看 STATUS，实际 review 按 D-046/D-053）
- 背景：现有 `useSpeech.ts` 直接绑定 Browser Speech，识别只读取第一候选并用本地化字符串报告错误；现有 TTS 能保留完整回答、转换技术 token 并有界分块，但 Browser `onstart/onend`、全局 audio owner 和 `tts.synthesize` 兼容函数都没有 response/generation、audio cursor 或 provider provenance。它们是重要兼容基线，不是正式 Speech Port。D-039 还要求对否定词、数字、日期、SHA、路径、分支和副作用动词实施可审计的 critical-token 安全门。
- 决策：P1 以共享 capability/provider/error/identity primitives 定义两个独立模块：Speech Recognition Port `SR-A` 与 Speech Synthesis Port `SS-A`。二者共享协议风格和 deterministic fake/conformance，但各自独立实施、后审与闭环；任何一个通过都不能替另一个或 Realtime Media/Audio 声称完成。Browser Speech 只作为明确标注 capability 缺口的 batch/fallback compatibility Adapter；本决策不选择云端、本地或 Native Provider。
- 决策：Recognition Provider 只能发出带 session/generation/sequence、partial/final/cancel、locale/timing/capability/fallback provenance 的原始 hypothesis；Provider 支持时携带 alternatives/confidence，不支持时显式 `unknown`，不得制造数值。原始候选不可修改。独立的 deterministic domain resolver 可以使用有权限且未过期的 ContextRef 对候选重排或生成 resolved copy，但必须记录选中候选、规则/上下文引用、修订原因和置信来源。critical-token gate 只输出 `eligible/clarification_required/blocked` 及理由；Recognition final 不是 TurnCommit，只有 Interaction/Conversation Runtime 能决定提交、澄清和 Agent/Tool/Task 副作用。
- 决策：Synthesis Port 只接受 canonical `response_id + response_generation`、presentation unit/text span、voice/locale 与可审计 `SpeechRenderPlan`。RenderPlan 保持原始展示文本/哈希不变，并单独记录 speakable copy、清洗/省略/发音转换和 span mapping；Provider 不得反写聊天文本。流式 Adapter 的 audio chunks 必须有严格 sequence、格式、时间和来源；Browser SpeechSynthesis 没有音频 bytes、可靠 chunk timing 或 cursor 时必须声明 unsupported 并只产生 compatibility control events。synthesized/enqueued/browser `onstart/onend` 都不等于 presented；只有 Audio/Presentation owner 的 ACK 能推进播放事实。
- 决策：recognition/synthesis session cancel 是 Port owner 对精确 Provider session 的内部 control，不新增第五种业务 CommandEnvelope cancel scope，也不能由外部调用者越权发出；它与 `playback.stop` 的 target/authority 不同。接受 session control 后立刻 fence 精确 session/generation 的迟到事件，但 ACK、超时和本地静音不伪造 final/terminal。Provider 失败、能力不匹配或降级只可选择满足请求策略的已声明 fallback；fallback 也必须保留原始错误与选择 provenance，不能把失败吞成空 transcript、成功音频或已播放。
- 隐私与放行：原始音频默认不持久化；固定语料优先使用合成/获同意样本，任何录音保存都需要目的、同意、retention、删除和 redaction 证据。SR 除 CER/WER 外必须度量 critical semantic error、first-pass task success、clarification、错误工具派发、speech-end→decision/commit、重复提交和 fallback 一致性；SS 必须度量首音频、stop、stale playback、可懂度、display→spoken 覆盖和关键 token 发音。没有固定环境、样本明细、真实设备/Provider 后验和零禁止副作用证据，SR-A/SS-A 只能保持 `PARTIAL`。
- 原因：把声学事实、领域解析、提交决策、文本呈现和实际播放拆到各自权威，既允许替换 Provider，也防止高置信度幻觉、静默改词和浏览器回调被误当作用户意图或听见的事实。
- 当时的执行影响：本决定接受时允许非 Sol 模型在 shared primitives 后实现 Port/fake/conformance；该模型分配由 D-052 取代。真实 Browser Adapter、专用 Provider、Audio ACK 与当前 Web 设备/权限闭环仍属于 SR-B/C、SS-B/C、AIO/RM/CR-B 的后续 consumer Gate。
- 重新评估条件：真实 Provider 无法表达当前 hypothesis/audio event 模型；critical-token policy 需要新的授权主体；某浏览器/Native API 可提供可验证 audio cursor；或隐私/多语言/无障碍要求改变保存、解析或呈现边界。

## D-045 P3α Task Core 采用 command/event/attempt/outbox 权威模型并把现有 scheduler 降为 Executor 兼容目标

- 日期：2026-08-03
- 状态：Accepted design（“接线尚未开始”只描述接受本决定时的快照；当前 Core/Store/Executor 状态只看 STATUS，实际 review 按 D-046/D-053）
- 背景：现有 AutoHarness `schedule.run/status/list/cancel` 已有稳定 task ID、服务端派生的单用户一致性 scope、执行 target、单进程/单 JSON 路径 create 幂等 ledger、进程内 task-bound Agent context、取消竞态防护和重启孤儿 `running→failed` 修复；但任务行、execution history 和 Harness log 不是版本化 append-only TaskEvent store，没有 durable attempt dispatch outbox、跨进程 CAS/唯一执行 owner、正式 terminal outcome 或通用 `events` API。它是强兼容基础和首个 D0 Executor 集成目标，不是 Task Control Core。
- 决策：`TC-A` 唯一拥有 canonical `task_id`、`command_id` ledger、TaskEvent stream、task reducer、attempt record 和 reconciliation record。P3α state/terminal outcome/operation 集严格沿用 ACG-1：状态为 `accepted/running/blocked/decision_required/terminal`，attempt 为 `accepted/running/terminal`，终态 outcome 为 `completed/failed/cancelled/interrupted/unknown`；命令只有 `create/cancel`，`get/list/status/events` 是零 mutation Query。`update/provide_input/pause/resume/reprioritize/delete/logs/recurrence/arbitrary recover` 不是正式 P3α Core operation，旧 schedule 能力只能保留在明确标注的兼容或 Executor Adapter 边界。
- 决策：同一 canonical `command_id + fingerprint` 重放原 Result，fingerprint 冲突零 mutation；`request_id` 每次 transport 尝试可变，不能成为幂等键。create 的 durable 单元必须原子包含 command ledger、task record、首个 accepted TaskEvent、result 和首次 attempt-dispatch intent；后续 event append 与 reducer snapshot 原子，Executor 投递通过 durable outbox 至少一次。Core 在持久化后分配 attempt ID，Executor 必须以 `(task_id, attempt_id)` 幂等接收并回报事实；这不承诺外部工具副作用 exactly-once。
- 决策：TaskEvent 是唯一 lifecycle 输入。Executor 只能发带自身 identity、attempt ID、sequence、causation/correlation、真实 outcome/facts 的 source event，不能直接改 task 行；Core 验证 scope、attempt、sequence、transition 后 append canonical event 并归约快照。WorkProgressEvent 是从已 append TaskEvent 派生的独立 projection，不反向改 task、不直接 TTS、不进入 Session History。`events` Query 返回可验证的有序持久 prefix、head/truncation/capability 事实；P3α 不承诺实时 subscription 或跨连接 cursor replay。
- 决策：`task.cancel` 先持久化精确 command、cancel-request record 和 attempt-control outbox，再返回 accepted/replayed/rejected/unknown；ACK 不等于 task terminal。未派发 task 可由 Core 权威终结为 cancelled；已有 attempt 时只有权威 Executor/Core reconciliation event 能终结，completed/failed 可赢取消竞态，已发生副作用不回滚。不同 task、response、round、playback owner 的调用必须为 0。
- 决策：启动时 Core 枚举所有非终态 task/attempt，fence 新 dispatch 并按原 attempt ID 查询 Executor。精确 active/terminal 事实继续或终结原记录；明确丢失且不可续跑的 D0 attempt 终结为 `interrupted` 并记录稳定原因；暂时不可查询保持原 lifecycle、标记独立 reconciliation pending 且禁止重派。只有显式、有 provenance 的 Core reconciliation decision 才可在事实永远不可知时终结为 `unknown`；重启绝不借用新 Agent/context 或自动创建新 attempt。
- 安全决策：Core invocation 除 envelope 外接收由可信入口提供的 `AuthorizationContext`，绑定 principal、scope、operation、target、command ID、能力与需要时的精确确认；它不是客户端可自报 payload，也不得由本地化错误或 ContextRef 自身推导。当前 D-033 Web scope 只能进入 legacy consistency Adapter，不能冒充正式 authentication/authorization。自然语言命令仍需 committed intent 和 Voice–Task Bridge；partial/uncommitted 的 command/event/store/outbox/Executor 副作用为 0。
- 原因：将 command、event、attempt 和 outbox 作为同一权威模型，才能在 ACK 丢失、重复投递、并发取消和进程重启后解释“接受了什么、实际执行了哪一次、依据哪个事件进入当前状态”；同时保留 at-least-once 的可实现性而不虚构 exactly-once 或回滚。
- 当时的执行影响：本决定接受时允许非 Sol 模型实现纯 types/reducer/fake/fixture conformance；该模型分配由 D-052 取代。真实 store/API/outbox/restart 仍属 `TC-B/C`，AutoHarness 适配属 `ED-A/B`，结构化 Command Adapter 与 Voice–Task Bridge 属各自后续 Gate；legacy 回归不能直接计为 TC-A conformance。
- 重新评估条件：目标 store 无法提供所需原子单元/outbox；Executor 不能按 attempt ID 幂等接收或查询；生产 identity/authorization 模型改变 ScopeRef 语义；D1/D2、recurrence、delete 或 input/pause/resume 被提升进 P3α；或真实副作用需要事务性 exactly-once/补偿契约。

## D-046 以两周 90% 累计 Demo 和四周 Integrated Alpha 驱动并行交付

- 日期：2026-08-03
- 状态：Partially superseded（累计路线、范围、评分和风险分级保留；Windows/X-WIN 载体由 D-055 取代，未来模型分工和原并行资源假设由 D-052 取代；`W2/W3/W4` 当前是顺序窗口，不是单线执行下的日历承诺）
- 背景：用户明确项目目标不是无限期平台建设，也不是只维护 V0 或只完成 D-031。V0 要第一时间打通真实端到端，随后正式模块沿同一工程路径持续替换 Demo 中的手工代码、固定限制和兼容实现；第 2 周 Demo 达到可审计的 90% 完成度，第 3–4 周完成 P1 + P2 + P3，若完整 P3 风险过高则 P3alpha 可作为承诺结果。完整方案现有 31 个 Alpha 工程包的顺序时间盒约为 47–78 人日，尚未包含完整 P3 扩展；若按每个小切片独立 D-032 checkpoint、单执行流和末期统一集成推进，四周目标在流程上即不可达。
- 接受时的目标定义：原四周并行范围写作 **Integrated Windows Alpha = P1 + P2 + P3alpha + Context/Progress/Failure/Observability + 三个真实纵向切片 + P2/P3alpha 联合 Gate**。D-055 已把 carrier 映射为 Web/X-WEB，D-052 已取消原并行日历承诺；能力范围仍不是 RC/Production，完整 P3 仍是 stretch，P3alpha 是当前 Alpha 的最低 Task 范围。
- 两周决策：Week 2 必须运行一个累计 Integrated Demo，而不是分别运行互斥的 V0、稳定句和 Task 样例。完成度按权威 Demo Replacement Ledger 的用户旅程权重计算，不按代码行数、测试数、文件数或模块名计数；总分至少 90/100，且 committed-only、副作用确认、精确 identity/scope、stale fence、unknown/error 不冒充成功、文字 flag-off 回归等 mandatory invariant 全部通过。`fallback`、`Demo substitute`、`unsupported` 和 `unknown` 必须可见；substitute 可以证明类别价值，但不能自动获得正式模块全部分值。
- 演进决策：V0 `ee2896a4` 保持不可变证据基线。新模块通过 Port/Adapter/capability/feature flag 逐段接管同一累计 Demo，必须由 route telemetry/trace 证明每段实际使用 formal、fallback 或 substitute；不另建第二套假 UX，也不等到所有模块完成后再进行首次集成。
- 并行决策：共享 ACG critical kernel 在最初 1–2 天冻结并实现，包含 identity/scope、authority、committed input、核心 lifecycle、四种 cancel、generation fence、Event/Error/Capability 和 feature-off primitives。随后 P1（AIO/SR/SS）、P2（CR/RM/II/AB）、P3alpha（TC/ED/VB）与 X-OBS/X-E2E/Windows 集成按依赖并行。ACG 的 ContextRef 全量策略、presentation ACK、完整 restart reconciliation 等扩展仍属于完整目标，但只在消费它们的 B/C 接线前成为局部门槛，不阻塞无关 A 包。
- D-031 决策：D-031 不再是整个项目无条件第一任务。它是 P3alpha 轨上的 legacy Demo Adapter 候选：若 `TC-B + TaskEvent/projection` 可在 Day 7 前进入累计 Demo，则跳过或缩减 D-031；否则把最小单任务 monitor 限时为 1–2 个工作日。必须保留 single in-flight、精确 identity/target、迟到结果 fence、错误不冒充终态、零 Chat mutation 和播报仲裁，但不得把临时 poll 路径扩成通用多任务、持久 replay、跨进程恢复或第二个 Task Core。
- D-032 决策：测试与 Sol 回顾按风险分级。Tier 0 文档/机械/纯重构执行受影响检查；Tier 1 普通功能/Adapter/UI 覆盖正向旅程、关键反例/flag-off、受影响集成和回归；Tier 2 状态/并发/副作用边界执行 scoped Sol pre/post review 和全部适用维度；Tier 3 共享协议、authority、安全、durability、Week 2/Week 4 Release Gate 执行完整 D-032、fault/recovery、immutable candidate 和真实路径证据。相关包可以共享一次设计 checkpoint、实现批次、post-review 和 commit；不再要求每个小包独立 pre-review commit/push。根 `AGENTS.md` 的每次 commit 与 push 分别精确批准仍保持不变。
- 历史模型分工：本决定接受时沿用 D-041；D-052 后续已把设计、实现、测试和审查统一为当前 GPT/Sol 单线。这里保留的跨轨契约、高风险判断和 Gate 责任仍有效，但不再授权非 Sol 模型执行未来包。
- 文档影响：`STATUS.md` 只保留短 dashboard、当前 replacement ledger、blocker 和 next actions；2026-08-03 已完成的详细 D-031/ACG/CR-A/SR-A/SS-A/TC-A 设计移入冻结 review record。Roadmap 以 Week 2/Week 4 Gate 和并行轨为权威；V0 acceptance/evidence/showcase 保持历史边界，并新增 Integrated Demo 与 Alpha acceptance/showcase。Runbook 在代码具备组合路由前必须诚实标注 Integrated mode 尚不可运行。
- 原因：架构规模与明确的 P1/P2/P3alpha 目标匹配，真正的风险是串行 Gate、临时 Adapter 过度建设和最后一刻集成。风险分级不降低 committed-only、精确对象、副作用、fence、truthfulness 和兼容性底线，而是把完整证明集中到真正高风险边界和累计 Gate，使三至四周并行交付具有可执行性。
- 重新评估条件：Week 1 结束仍只有一个有效执行轨；共享 kernel 超过两天仍不能支持并行；Week 2 route telemetry 无法证明 90% 分值；真实 Provider/Web/Executor 条件不可用；P3alpha 联合 Gate 暴露必须提前实现完整 P3 的依赖；或用户改变范围、资源并行度、日历目标或生产责任。D-052 已触发资源假设重新估算，当前没有接受新的四周日历承诺。

## D-047 保留必要安全并冻结临时 authority，正式模块只在替换时收缩兼容层

- 日期：2026-08-03
- 状态：Accepted（当前分支代码范围审查；本决策不授权立即删除、重构、commit 或 push）
- 背景：对当前分支相对 `develop` 的代码执行只读复核后，V0 的 committed-only、单次 final 提交、本地 response epoch、迟到回调失效、TTS owner、supplement quarantine 和错误降级属于合理的最小功能保护；任务路径中的稳定 command/task identity、精确 owner/project target、幂等冲突、mutation-unknown fail-closed、取消竞态与真实状态也保护会修改代码的副作用，不能仅因代码量大而删除。过重主要集中在临时组件承担了过多未来权威：`useLiveVoiceDemo.ts` 同时编排识别、会话迁移、响应选择、流式朗读、TTS、任务路由和恢复定时器；`liveVoiceTaskBridge.ts` 与后端 `schedule.*`/JSON store 已共同形成近似第二套 Task Core；最小 v1 contract、稳定句 planner 和任务详情 UI 也存在继续扩张为平行正式架构的风险。核心前端文件还混入了大范围无关格式变化，增加审查和合并成本。
- 决策：保留现有安全底线和已覆盖的负向/副作用回归，不通过删除 committed gate、identity/scope、stale fence、unknown/error、取消竞态、幂等或确定性失败断路器换取表面速度。测试数量和代码行数本身不作为过重或完成的判断；判断标准是该逻辑是否保护真实风险、是否成为第二 authority、是否帮助 Week 2/Week 4 的正式 route 替换。
- 决策：V0 `LiveVoiceCore`、Browser Speech/TTS、supplement quarantine、稳定句 preview、`useLiveVoiceDemo`，以及 task Bridge/Client/Adapter/task card 和后端 `schedule.*` foundation，统一视为冻结的 fallback、Demo substitute 或 Compatibility Adapter。除修复已证明的回归、完成 timeboxed D-031 最小监控或接入正式 route 所需的薄适配外，不再为它们增加通用状态、恢复、持久化、多任务、跨进程、展示或平台能力；任何新增 authority、identity、lifecycle、cancel、durability 或安全语义必须落入相应 ACG/CR/TC 等正式模块并经过对应 Gate。
- 决策：不先发起一次只为降低行数的全面重构。P2 接线时由 CR/RM/II/AB 逐段接管 lifecycle、fence、presentation 和 Agent mapping，`useLiveVoiceDemo` 随实际替换收缩为 route/compatibility shell；P3alpha 接线时由 TC 唯一拥有 command/event/task/attempt/reconciliation，旧 scheduler 只作为 ED/Executor Adapter，前端 TaskBridge 不再拥有 canonical mutation 状态。`live-voice.contract.v1` 不继续扩展成平行 v2；只能按 D-042 显式映射、保留兼容输入或退役。
- 决策：既有 legacy 测试继续作为回归门，不因正式模块启动而删除；但不再为临时别名、展示字段或第二套状态矩阵成倍扩张。正式实现优先使用共享 v2 fixtures/fakes/conformance 和按风险分级的场景证据。任务 UI 后续只保留用户需要的真实状态、错误与确认，详细 provenance 转入可选诊断/trace；不为未替换的 substitute 继续投入非关键视觉精度。正式合并前以 Tier 0 机械范围处理核心文件的无关格式 churn，保留语义改动并执行受影响回归。
- 原因：当前问题不是“保护太多”，而是“临时保护被组织成可能与正式模块竞争的架构”。冻结兼容层、让正式模块在同一累计 Demo 中逐段接管，可以保留真实副作用安全和已验证回归，同时避免为将在两周内被替换的路径重复建设平台能力或先做一次高风险大重写。
- 影响：执行模型不得继续向 `useLiveVoiceDemo`、TaskBridge 或旧 schedule store 推导正式产品语义，也不得把它们的现状直接计为 CR/TC/ED conformance。Sol 后续 review 重点检查 authority 是否迁移、legacy 是否保持薄适配、route telemetry 是否诚实，而不是追求统一行数上限。D-046 的 ACG kernel、P1/P2/P3alpha 并行顺序、Day 5 D-031 go/no-go、Week 2 90% 和 Week 4 Alpha Gate 不变。
- 重新评估条件：正式模块无法在里程碑前进入累计 Demo且某个有界兼容改动是唯一可验证路径；删除或冻结某项保护被真实故障数据证明会阻塞目标；上游 schedule/Chat 架构已成为正式共享平台并提供等价 authority/durability；或用户明确改变里程碑、风险容忍度与重构预算。任何重新开放都必须限定目标、时间盒和退出条件，不能默认恢复平台化扩张。

## D-048 采用模块级全局图与五工作日 execution-ready 滚动计划

- 日期：2026-08-03
- 状态：Completed historical plan（Week 1 包边界和 oracles 保留；当时的实现状态、环境、owner、模型和五日时序不再描述当前工作，未来模型分工由 D-052 取代）
- 背景：D-046 已冻结两周 90% Demo、四周 Integrated Alpha、ACG critical kernel 和并行轨，但 roadmap 的 Day 1–10 表仍不足以直接交给非 Sol 模型实现。执行模型还需要精确包状态、依赖、目标文件、场景 oracle、禁止副作用、验证命令和 return-to-Sol 条件；同时旧 D-042 仍残留“每次只执行一个包、每包完整 D-032”的历史操作措辞。若不补齐，执行模型要么自行决定架构，要么为低风险工作重复完整仪式。
- 决策：接受 [WEEK_1_EXECUTION_PACKAGES_2026-08-03.md](../roadmap/WEEK_1_EXECUTION_PACKAGES_2026-08-03.md) 为下一五个工作日的 dated Sol execution handoff。完整项目继续用模块级优先级、authority map 和依赖 DAG 管理；只把当前一周展开为 execution-ready 包。`STATUS.md` 唯一记录当前包状态、tested SHA、blocker 和下一动作；dated plan 冻结包合同，不复制进度。
- 优先级：Week 1 先完成 `W1-K1` ACG critical kernel 和 `W1-X1` route telemetry；kernel 通过 `W1-S1` grouped Tier 3 review 后，P1 `AIO/SR/SS`、P2 `CR/RM/II/AB`、P3alpha `TC/ED/VB` A 包按文件边界并行；随后 `W1-X2` 组合三个 fake vertical，并在条件具备时用 `W1-P1B` 让 Browser Speech 作为明确 fallback 进入正式 P1 Port route。Day 5 由 Sol 用实际 TC/Event 进展执行 D-031 `SKIP/REDUCE/TIMEBOX`，不自动运行历史 `D031-B1..B4`。
- 代码边界：shared v2 wire validation 新建在 `jiuwenswarm/common/schema/live_voice_contract_v2.py`，不改写 v1；正式服务端模块新建在 `jiuwenswarm/server/live_voice/`；正式前端 replica/Port/route 新建在 `src/features/live-voice/formal/`。除 plan 明确允许的 `W1-P1B` 薄 route selection/label 外，不修改或扩建 `useLiveVoiceDemo`、TaskBridge、旧 `schedule.*`/JSON authority。该布局是 Week 1 实现边界，不宣称已经落地，也不阻止后续在证据支持下经新决策调整。
- 执行门：第一项非 Sol 代码包是 `W1-K1`；独立 lane 可并行执行纯 `W1-X1`。其余包只有在依赖 Gate 实际 `CLOSED` 后才能执行。每包保持未提交，报告 start SHA、diff、命令/结果、scenario evidence、未决问题和 exclusions，再由 Sol 完成适用 review；package plan、Sol sign-off 和测试命令都不等于代码已通过。
- 环境与非目标：在本决定接受时，仓库尚未恢复 `.venv` 和 frontend `node_modules`，命令在依赖恢复前只是验证规范；该环境描述不是当前事实。Week 1 不选择真实 streaming Speech Provider、Realtime Media transport、历史 Windows 设备基线或生产 Store/Auth，也不承诺后续 Gate。
- 原因：一个短、精确、依赖可判定的滚动计划既能让 DeepSeek-V4-Flash 等执行模型在不重做架构推理的情况下编码，也避免 Sol 把整月计划过度细化成会快速失真的微任务。新的正式目录和单一薄接线例外让三条轨能够并行，又不会继续把临时 Demo 组织成第二套平台。
- 影响：文档 reconciliation 完成后先形成一个纯文档 commit 候选；取得精确 commit 批准并提交后，切换非 Sol 模型执行 `W1-K1`/`W1-X1`。Sol 随实际 diff 执行 W1-S1/S2/S3，不亲自承担已冻结合同下的常规编码。相关代码包可以按 coherent boundary 共用后审和 commit，但每个 commit/push 仍需根 `AGENTS.md` 要求的独立精确批准。
- 重新评估条件：W1-K1 超过两天仍不能关闭；正式目录与仓库部署边界不兼容；单 lane 无法在 Week 1 建立三轨 fake vertical；真实 Provider/Executor/Windows 条件改变 critical path；某包必须新增 authority/state/cancel/error/durability 语义；或用户改变模型分工、里程碑、并行资源与风险容忍度。

## D-049 W1-K1 改由 Sol 重新实现，非 Sol 转为参考实现后的有界执行

- 日期：2026-08-03
- 状态：Completed historical source decision（W1-K1 代码来源和五轮候选判断保留；面向未来任务的模型分工由 D-052 取代，当前实现状态只看 STATUS）
- 背景：DeepSeek 先后提交 `a5f91654`、`ca3836ba`、`1b9d3b83`、`a1c6d3d2` 和 `6ce74a4b` 五个从同一 `73448519` 基线产生的替换候选。连续五轮 Sol review 后，15 类修正中仅 Attempt 默认 lifecycle 一类基本完成，Event sequence/causation、TurnCommit、parent、rule immutability、response fence、cancel、JSON boundary、Result replay、scope/capability 和 event authority 等跨语言语义仍有阻断问题；focused tests 全绿仍未覆盖这些反例。详细记录见 [W1-K1 implementation review](../W1_K1_IMPLEMENTATION_REVIEWS_2026-08-03.md)。这已经满足 D-048 的 W1-K1 超时、语义分支返回 Sol 和用户改变模型分工的重新评估条件。
- 代码来源决策：保留 `agtai/hx/0803_live_voice_ds` 及其最新 `6ce74a4b` 候选作为审查历史和可选素材，不删除、不继续 force-update，也不把它标记为已接受实现；五轮候选 SHA 全部记录在 review record 中，但前四个被替换且没有独立 remote ref 的对象不作为长期集成来源。Sol 从干净的 `hx/0803_live_voice` 基线建立独立工作分支并重新实现 W1-K1；不在 `6ce74a4b` 上继续补丁，不整体 merge 或 cherry-pick DeepSeek 候选。只有逐项对照 ACG 和反例后确认正确的 fixture、测试思路、枚举/错误等机械片段可以选择性复用。
- 当时的模型分工决策：Sol 直接负责 W1-K1 和高风险参考实现，非 Sol 只处理参考实现后的有界工作；D-052 已取代这段面向未来任务的安排，后续不再据此分配工作。
- 流程决策：W1-S1 仍是 P1/P2/P3alpha 消费 shared kernel 前的依赖条件，但 W1-K1 不再采用“非 Sol 修改、Sol 重复后审”的第六轮流程。Sol 先以共同 scenario oracle 驱动 Python/TypeScript 实现，再运行完整 Tier 3 反例与受影响回归。非 Sol 后续工作不得用新增测试去合理化候选行为，也不得把旧候选 manifest 当成执行中的协议来源。
- 原因：五轮结果说明问题不在缺少局部修改清单，而在实现没有形成跨 identity、state、authority、replay、cancel 和 JSON 边界的一致模型。继续在同一结构上逐项补丁的预计成本和引入新问题的风险已经高于由设计 owner 直接建立参考实现；保留候选历史仍可避免丢失测试素材和已完成的机械工作。
- 影响：D-048 的 dated Week 1 plan 保留为历史执行合同，不静默改写原始 owner 字段。本决定接受时主分支尚未集成 W1-K1 候选；后续 Sol 实现、closure 和当前 Replacement Ledger 只看 STATUS，非 Sol 并行安排已失效。
- 重新评估条件：Sol 已建立稳定参考实现和共享场景，后续任务只剩无语义选择的等价转换；新的执行模型能在独立盲测中一次满足 Tier 3 oracle；或用户重新调整成本、速度和模型责任。

## D-050 v2 canonical JSON 的整数采用跨 Python/TypeScript 安全范围

- 日期：2026-08-04
- 状态：Accepted
- 背景：ACG 要求 Python 与 TypeScript 对同一 v2 JSON 产生相同 canonical UTF-8 bytes。JavaScript `number` 无法精确表示超出 `2^53-1` 的整数；若 Python 接受更大整数，两端可能在 fingerprint、幂等和事件冲突判断上得到不同事实。
- 决策：v2 critical kernel 只接受绝对值不超过 `9007199254740991` 的整数和整数值浮点数；超出范围返回 `INVALID_SAFE_INTEGER`。其余数字必须有限；canonical helper 不选择或内置新的 digest 算法。
- 影响：共享 fixture 同时验证安全范围、非有限数字和 canonical bytes。未来如需更大计数器或业务整数，必须使用明确的字符串/新类型编码并经过新合同决策，不能让 Python 单边扩大范围。
- 重新评估条件：v2 数字模型改为精确十进制/大整数编码，或所有消费端采用能够证明相同 canonical 数字语义的新表示。

## D-051 W1-K1 Sol 候选直接保留在当前开发分支的未提交工作区

- 日期：2026-08-04
- 状态：Completed historical operation（记录 W1-K1 当时直接保留在开发分支的操作授权；候选现已提交，当前 Git/实现状态只看 STATUS）
- 决策：W1-K1 从 `73448519be9ee7cb2bb384e8aa2c4914178f9291` 开始，直接在 `hx/0803_live_voice` 工作区开发并保持未提交，完成三轮 review 和验证后再按根 `AGENTS.md` 单独申请 commit 批准。不得因此合并或 cherry-pick DeepSeek 候选，也不得绕过单独的 push 批准。
- 当时影响：`STATUS.md` 记录未提交候选和验证事实，Git HEAD 在获得批准前保持基线 SHA；该操作已完成，不再表示当前候选仍未提交。
- 重新评估条件：用户要求拆分分支/提交范围，当前工作区出现无法安全区分的无关改动，或 commit 审批要求改变候选边界。

## D-052 后续开发固定由当前 GPT/Sol 单线完成

- 日期：2026-08-04
- 状态：Accepted（替代 D-041、D-048、D-049 中面向未来任务的模型分工；这些决策仍保留其历史背景、代码来源和风险判断）
- 决策：后续包固定由当前 GPT/Sol 设计、实现、测试和审查，不再提醒、委派或切换到 DeepSeek/其他外部执行模型。Tier 2/3 的 identity、authority、state、cancel、security、concurrency、durability 和 release 判断始终由 GPT/Sol 负责。
- 历史候选：已有外部候选只作为审查历史或可选择复用的素材；任何片段都要按当前合同、完整 diff 和实际测试重新验证，不得整体 merge/cherry-pick 来代替实现与审查。
- 影响：dated Week 1 plan 的包边界和风险 Gate 继续有效，但其中历史 owner/model 字段不再决定当前执行。原三到四周估算依赖多条并行实现轨；默认单线执行后必须按实际速度重新估算，不能继续沿用原资源假设。
- 重新评估条件：只有用户以后明确作出新的模型分工决策，或项目范围、时间和可用资源发生变化。

## D-053 高风险开发批次采用三轮 review

- 日期：2026-08-04
- 状态：Accepted（面向本决定之后开始的开发批次，不追溯改变已经接受的历史 Gate 结果）
- 背景：实现者自我检查、脱离实现理由的完整 diff 检查和独立 `/review` 能发现不同类型的问题。只依赖第一次检查容易遗漏实现者已经习惯的假设；只规定测试次数又不能证明需求、兼容性、并发、取消和禁止副作用正确。但对文档、格式和低风险机械修改一律执行三轮会增加时间而没有对应收益。
- 决策：一个完整开发批次按 D-046 风险分级 review。Tier 2/3 在接受前必须依次完成三轮：第一轮由实现者对需求、边界、代码和测试自我 review；第二轮不采信开发过程中的实现理由，只依据原始需求、仓库规则、既有行为/API、完整 Git diff 和真实测试结果进行冷态 diff review；第三轮使用独立 `/review`，或使用当前环境中等价的独立审查入口。每轮发现的问题先修改并重跑受影响测试；若修改明显改变语义，必须再执行一次最终完整 diff review，直到没有可操作缺陷。
- 低风险规则：Tier 0 只执行相关检查；Tier 1 默认执行自我 review 和完整 diff review，涉及取消、权限、跨范围副作用、并发或发布影响时升级为三轮。三轮以一个 coherent implementation batch 为单位，不要求每个文件、每次保存或每个小 commit 重复三次。
- 可用性规则：若当前环境不能调用字面意义上的 `/review`，必须记录实际替代的独立审查方式和剩余限制，不得声称 `/review` 已运行。缺少 Tier 2/3 所需的第三轮且没有等价独立审查时，该批次保持 `PARTIAL`。
- 影响：`W1-X2` 及后续 Tier 2/3 开发按三轮流程执行；`W1-P1B` 的普通 Adapter 部分按 Tier 1 执行，但其 commit/playback 边界按 Tier 2 升级为三轮。review 记录写明每轮发现、修正、测试和仍未覆盖的验证；`STATUS.md` 只记录当前批次是否满足规则。Git commit/push 批准规则不变。
- 重新评估条件：独立 review 工具长期不可用且替代流程无法提供不同视角；实际数据表明第三轮没有发现独立问题；风险分类发生变化；或用户调整质量、速度与发布要求。

## D-054 W1-S3 选择限时的 D-031 最小任务监控候选

- 日期：2026-08-04
- 状态：Completed scope decision（本条在接受时只决定 `TIMEBOX`、不自动授权开发；用户后来已单独授权并完成 D-031 最小监控，当前状态和下一缺口只看 STATUS）
- 背景：当前 P3alpha 只有内存 Task Core、确定性 Executor fake、Voice Task Bridge 和 fake WorkProgress 投影。真实 Store/outbox、Harness Adapter、restart reconciliation、生产 AuthorizationContext、公开 events API 和累计 Demo 接线都未完成；在当前单一 GPT/Sol 执行线上，`TC-B + TaskEvent/projection` 无法可信地在 Day 7 前进入累计 Demo。
- 决策：W1-S3 结果为 `TIMEBOX`，不选择 `SKIP` 或 `REDUCE`。若用户批准后续执行包，D-031 只实现 roadmap §9 的一个 current task、1–2 个工作日轮询 Adapter，并保留 single in-flight、精确 task/target、generation/context fence、真实 unknown/error、零 Chat mutation 和安全播报仲裁。
- 影响：本决定不把旧 schedule/JSON 路径称为正式 TC/TaskEvent，也不增加 Demo Replacement Ledger 分值。所需实现授权后来已经取得；这句话不再阻止当前 D-031 修正，但任何 commit/push 仍需新的精确批准。
- 重新评估条件：D-031 开始前正式 Store/Event/Harness 依赖已经具备并可在相同时间内进入累计 Demo；用户拒绝临时 polling 路径；或 Day 7/Week 2 范围发生变化。

## D-055 Live Voice Alpha 产品载体从 Windows Desktop/WebView2 调整为 Web

- 日期：2026-08-05
- 状态：Accepted（用户已明确将当前 Alpha 产品目标从 Windows Desktop/WebView2 调整为 Web；本条把此前对话中的产品决定同步为仓库权威记录）
- 背景：当前可运行 V0 和 Post-V0 Demo 已经通过 JiuwenSwarm Web 前端、浏览器麦克风和浏览器音频路径验证产品价值；继续把 Windows `.exe`、WebView2 权限、原生设备生命周期和安装包作为四周 Alpha Gate，会把平台产品化工作放在真实 Speech/Media/Conversation/Task 纵向链之前。用户已经决定当前交付载体改为 Web，但 D-046、roadmap、STATUS 和 Alpha acceptance 仍保留 Windows Alpha 表述，造成当前目标与文档权威不一致。
- 产品决定：当前范围目标为 **Integrated Web Alpha**。`W2/W3/W4` 表示累计交付顺序；D-052 固定单 GPT/Sol 轨后，原四周并行估算不再是当前日历承诺，必须根据实际速度重新估算。首期载体是 JiuwenSwarm 桌面 Web 前端；实际验收必须使用并记录明确声明的桌面浏览器、操作系统、设备和网络标签，但不把固定验收环境冒充公开兼容矩阵。D-055 不自行承诺 Chrome+Edge 双浏览器覆盖；X-WEB 真实 Gate 前必须明确冻结是单一 Chromium 基线还是 Chrome+Edge 双 Chromium 基线。移动 Web、PWA、Firefox、Safari 和全平台兼容不属于当前 Alpha 范围。
- 安全与部署边界：部署环境必须使用安全上下文；`localhost` 只作为本地开发和受控验收例外。Speech/模型 Provider 凭据只能保存在 Gateway/服务端，浏览器不得持有长期 Provider 密钥。麦克风权限、权限撤销、设备变化、autoplay/user-activation、页面隐藏/后台、CSP、CORS、反向代理、连接失败和文字降级必须在 Web Alpha Gate 中可见且无静默失败。原始音频默认不持久化。
- 架构保持：P1/P2/P3alpha、ACG v2 wire contract、identity/scope/authority、committed-only、四种取消作用域、generation fence、presented history、Task/Core/Executor 边界、Week 2 90% 评分和风险分级不变。Web 是产品载体变化，不授权 Browser、UI、Provider 或 Transport 成为新的生命周期权威。
- 工作包影响：`AIO-B/C` 保留稳定 ID，交付解释改为浏览器采集、播放、权限、设备和 exact-response stop；`RM-B` 保留稳定 ID，改为 Browser↔Gateway 实时媒体传输；`X-WEB` 取代 `X-WIN`，负责 Web UI、权限/隐私、部署、诊断和正式 P3alpha 控件接线。Browser Speech Recognition/Synthesis 继续作为显式 fallback，不获得正式 Provider 或 Realtime Media credit。不得为所有包机械增加 `-Web` 后缀。
- 待消费包决定：AudioWorklet/MediaRecorder 的组合、上行与下行编码/采样率/frame、WebSocket/WebTransport 及其 fallback、具体 Provider 和部署拓扑，不由本决策提前指定；它们必须在 AIO-B/C、RM-B/C、SR-C/SS-C 的设计与真实接线前形成有证据的消费决策。未决定或不可用时必须标记 `unknown/unsupported`，不得由实现默认值静默成为产品合同。
- 文档和历史：D-055 取代不可变 Full Solution、D-046、D-048 和历史 X-WIN 计划中的 Windows 产品载体与产品化安排，但不倒写带日期的 Full Solution、V0 evidence/showcase、Week 1 execution plan 或历史 review。V0 的 Windows/Chrome/Jabra 证据继续是不可变历史事实，不代表当前 Web Alpha 的兼容范围。当前目标、阶段和 blocker 只在 STATUS 维护；稳定工作包、替换关系和目标窗口记录在 dated Web Alpha delivery matrix。
- 非目标：Windows `.exe`、WebView2、Windows 原生设备生命周期和安装升级不再属于当前 Alpha Gate；完整 P3、D1/D2、生产多租户鉴权、未被后续范围决定纳入的浏览器/多端、公开兼容承诺、运营 SLO、完整隐私保留系统和 RC/Production hardening 仍属于 Later。
- 重新评估条件：用户重新选择 Desktop/native 作为产品载体；目标客户必须使用移动端、PWA 或非 Chromium 浏览器；浏览器权限、音频或后台限制无法达到 Alpha Gate；Gateway 代理或安全上下文无法满足部署要求；或真实测量证明 Web 平台无法达到已接受的 P1/P2/P3alpha 用户体验和安全边界。

## D-056 D-031 采用项目绑定 Code Agent，而不是把 AutoHarness runtime extension 伪装成项目代码任务

- 日期：2026-08-05
- 状态：Accepted implementation choice（用户要求完成 D-031；本条采用 D-031 评审和 STATUS 中已推荐的 project-bound code execution，取代 `d031-05` 暴露的混合合同）
- 背景：D-031 monitor、幂等对账、严格 scope/provenance 和零变化结果门槛已经完成，但 `extended_evolve_pipeline` 实际修改配置的 Agent Core/runtime-extension 存储，页面选择的项目只用于授权和结果检查。继续给 AutoHarness 增加一个 `repo_url` 字段不能改变 extension-only artifact 语义，也不能满足“后台代码优化任务”对当前项目的承诺。
- 决策：Live Voice Task Demo 固定使用 `project_code_pipeline` 和 JiuwenSwarm Code Agent。服务端必须在任务持久化、模型调用和执行副作用前证明：页面保存的绝对 `project_dir`、Code Agent 根目录和 `git rev-parse --show-toplevel` 完全一致；随后持久化 `effective_execution_root`、`artifact_kind=git_visible_project_change`、`executor=jiuwenswarm_code_agent` 和 pipeline。任何缺失、外部根、无效 Git 根或合同冲突都以稳定错误 fail closed，且不创建任务。
- 副作用决定：该兼容执行器把 task Session ability 收窄为 Code Agent 的项目 read/search/write/edit 文件工具，并移除 task/subagent、cron、send-file、search、skill、terminal 与其他配置能力；后台上下文同时禁用 JiuwenSwarm command tool 与 OpenJiuwen Bash/PowerShell 的全部 shell 命令，因此测试、脚本、Git 与远端命令均不可执行。明确 no-tests/no-commit/no-push 约束可被该边界满足；明确要求运行测试或执行 shell 的任务在执行前以 `UNSUPPORTED_PROJECT_TASK_CONSTRAINT` 拒绝，不能接受后再静默违反。该收窄来自 D-053 独立 review：仅按命令文本筛查 Git 无法阻止 Python 或生成脚本间接改变 ref。
- Authority：旧 `schedule.*`/JSON 仍只是 D-031 Demo carrier，TaskBridge/monitor 继续只负责一个页面内任务的命令、轮询和可见事实，不获得执行权、Chat 写入权或正式 Task Core/Event Store 权威。后台 Code Agent 使用独立 task Session、关闭 memory/A2UI/user interaction，并绕过 Chat history hooks。正式替换仍由 TC-B/ED-B/VB-B 及其后续包负责，D-031 不获得 Replacement Ledger credit。
- 初始成功口径：Executor 必须正常终止，且选定 Git 项目的 tracked 或未忽略 untracked 内容指纹发生变化；零变化、仅忽略文件变化、外部目录变化、不可读或无效目标均失败。该门槛只证明 Git-visible effect，不证明修改语义正确；真实验收还需检查精确产物、HEAD、同一 task 终态与安全播报。D-056 原本要求“意外文件为零”，D-057 根据真实样本把共享 Agent Runtime support paths 改为必须显式盘点的独立归属，禁止继续宣称绝对为零。
- 初始影响（D-056 接受时）：自动化候选可以解除“混合 target/runtime extension”这一代码阻断，但在新的项目绑定候选完成三轮 review 和一次隔离真实服务正向验证前，D-031 仍为 `PARTIAL`。凭据、Provider、项目注册、浏览器权限、设备和运行时数据仍是机器私有条件。后续真实验证和关闭归属由 D-057 记录。
- 重新评估条件：产品明确把口令改为 runtime-extension 创建；正式 ED/TC/VB 路径可在相同时间内替换兼容 carrier；产品要求后台任务运行测试；Code Agent 工具集合新增绕过统一安全钩子的命令/代码执行入口；或真实运行证明项目根绑定、禁用副作用、结果指纹或无 Chat history 隔离不成立。

## D-057 D-031 按逻辑单任务和项目绑定边界闭环，Speech 与 Agent Runtime 问题分别归属

- 日期：2026-08-05
- 状态：Accepted validation and ownership decision（用户在执行前已恢复基线的隔离项目正向验证后明确接受该边界）
- 背景：项目绑定候选的有效 committed-final 口令产生了两次同幂等键 `schedule.run` wire attempt，但持久层只有一个 create command、一个 task 和一个 execution；任务正确修改了选定项目的 `README.md`，HEAD 未变化并达到 `success/success`。同时，Agent/runtime 初始化在目标内留下 `.gitignore`、`coding_memory/`、`prompt_attachment/` 和被忽略的 `.agent_history/`，终态安全播报没有发生；更早样本还出现过 ASR 把 README 识别为 `radi.nd`。
- 输入权威：D-031 以提交后的 final transcript 为命令权威。Executor 忠实执行错误的 ASR final 不构成 D-031 project binding/monitor 缺陷；识别 fidelity 归 P1 Speech 跟进，但关键 token 不清楚时仍应由产品确认流程阻止误执行。
- 幂等口径：一次用户 committed-final 对应一个稳定 command/idempotency key。超时或未知 mutation 后允许 exact-key list 与同 key 重试；wire 上可以出现多个 `schedule.run`，验收要求是一个 durable create command、一个 task、一个 execution 和零重复副作用。该口径不是跨进程 exactly-once 承诺。
- 副作用归属：D-031 必须证明选定项目/Code Agent/Git root 一致、语义产物正确、shell/tests/Git/remote effect policy 生效、HEAD 不变、任务终态真实且监控停止。共享 Code Agent 初始化目录的落盘位置归 Agent Runtime/workspace isolation，不再作为 D-031 关闭阻断；这些路径必须被如实记录，不能写成“意外文件为零”，未来要求 clean workspace 的正式 ED Gate 仍需解决。
- 语音口径：终态播报合同保持 safe at-most-once，而不是 guaranteed delivery。安全窗口不存在时允许 0 次且不延迟补播；超过 1 次失败。若产品需要必达通知，必须由后续正式事件/通知 owner 增加可恢复投递与确认合同，不能把本次 0 次改写成已具备。
- 当前影响：2026-08-05 隔离且执行前已基线化的项目样本满足上述 D-031 Compatibility Adapter 边界，因此 D-031 可记为 `CLOSED`。该关闭不增加 Demo Replacement Ledger credit，不授予旧 `schedule.*`/TaskBridge 正式 Task Core/Event Store/Executor 权威，也不关闭 Speech fidelity、Agent Runtime workspace isolation 或正式终态通知任务。
- 证据：[D-031 project-bound real-service evidence](../evidence/D031_20260805_PROJECT_BOUND.md)。
- 重新评估条件：发现同 key 重试产生多个 durable task/execution 或重复项目写入；execution root 与选定项目不一致；shell/test/Git/remote 禁令可绕过；运行时支持文件影响用户项目语义、安全或正式 ED clean-workspace Gate；或产品把终态语音从 at-most-once 改为必达。

## D-058 Web Alpha 采用单一桌面 Google Chrome 基线，AIO-B 以 AudioWorklet 交付正式浏览器音频帧

- 日期：2026-08-05
- 状态：Accepted scope/design（用户已接受单一桌面 Chrome Alpha 基线；实现最初来自独立 `codex/aio-b-x-web` 候选，并在当前分支完成集成 review。候选使用的 D-057 顺延为 D-058，因为当前分支的 D-057 已记录 D-031 closure；该编号协调不改变决定语义。实际代码、review 和真机 evidence 只看 STATUS 与本批 review record）
- 背景：D-055 已把当前载体改为桌面 Web，但仍要求 X-WEB 在真实 Gate 前冻结单一 Chromium 或 Chrome+Edge 双 Chromium 基线，并把 AudioWorklet/MediaRecorder、音频 frame 和浏览器生命周期选择交给消费包。现有 Browser `SpeechRecognition`/`speechSynthesis` 能证明 V0 和 fallback 价值，却自行持有麦克风/播放且不提供正式 PCM frame、可靠 cursor 或设备生命周期，不能充当 AIO-B。现有 AIO-A 代码只建立了精确 response 的有界播放队列和 fake，尚未实现浏览器 capture、设备、权限或 Web Audio playout Adapter。
- 产品范围：Integrated Web Alpha 的首个浏览器范围冻结为 **单一桌面 Google Chrome**。候选必须在每次 Gate 记录精确 Chrome 版本、操作系统、origin、音频设备和网络；初始真实 evidence 使用当前 Windows 桌面环境，但不得由一次固定环境推导 macOS/Linux 或所有 Chrome 版本兼容。Chrome/Chromium 107 仍只是前端实现下限。Edge、其他 Chromium、Firefox、Safari、移动 Web、PWA、WebView2 和 native desktop/mobile 均不属于当前 Alpha 承诺；它们可能工作，但没有兼容保证或 release credit。
- capture 决策：AIO-B 通过安全上下文中的 `mediaDevices.getUserMedia` 取得一个显式选择或默认的 `audioinput`，以 `ideal` 请求 echo cancellation、noise suppression、auto gain control 和 mono，并把 `MediaStreamTrack.getSettings()` 的实际结果作为 provenance，绝不把请求值冒充已生效事实。正式帧由 `AudioWorklet` 在音频渲染线程采集、单声道 downmix，并聚合为 20ms `pcm_f32` frame；每帧携带 capture identity/generation、track identity、连续 sequence、sample cursor、AudioContext clock、实际 sample rate、channel count 和样本数。Adapter 不执行自定义重采样或选择 wire codec；Web Audio 输入图可能把 track rate 适配到 context rate，因此两者都必须显式记录，且无法形成整数 20ms frame 的 context rate 必须拒绝。RM-B/SR-C 再基于这些事实决定传输编码和必要转换。
- MediaRecorder 决策：`MediaRecorder` 的 `dataavailable/timeslice` 产物是浏览器选择或协商的 encoded Blob/container，不能提供本路径要求的确定 PCM sample cursor、20ms frame 和 AudioWorklet clock，因此不进入正式 realtime AIO route。它可在未来仅作为显式 `batch/fallback` Adapter 重新评估，并必须保留 mime/codec/timing capability provenance；不可因 API 存在而获得 realtime credit。
- playout 决策：AIO-B 的正式浏览器播放消费带精确 `response_id/response_generation`、unit/sequence、`pcm_f32` format 和 Provider provenance 的数据，通过 Web Audio 排队并只对当前 response 产生 render-completed ACK。该 ACK 表示浏览器音频图完成了对应连续单元，不证明人实际听见；queued/scheduled、AudioBufferSource `start` 或 Browser Speech callback 都不是 presented。新 response 或显式 local stop 只停止本地播放，不升级为 `response.cancel`、`round.cancel` 或 `task.cancel`；AIO-C 后续负责 exact-response hard-stop 的真机延迟和故障 closure。
- Web 生命周期与隐私：创建 AudioContext、请求麦克风和恢复 autoplay 必须来自显式启用/用户动作；flag/capability off 时不得创建 stream/context/listener/timer。权限拒绝/撤销、track ended、processor error、设备变化、页面隐藏和 AudioContext suspended 必须产生稳定可诊断失败，不自动切换设备或在页面恢复时自动重新采集。页面隐藏时 active capture fail closed、fence 迟到 frame 并释放设备；恢复后需要新的显式 start。原始 PCM 默认只在内存中流转，不写 storage、URL 或日志。
- 依据：[Media Capture and Streams](https://www.w3.org/TR/mediacapture-streams/) 定义 getUserMedia、设备、track settings 和 AEC/NS/AGC；[Web Audio API 1.1](https://www.w3.org/TR/webaudio-1.1/) 定义 AudioWorklet、安全上下文、render quantum 和 AudioContext clock；[MediaStream Recording](https://www.w3.org/TR/mediastream-recording/) 定义 MediaRecorder 的 encoded Blob/timeslice 边界；[Chrome Web Audio autoplay policy](https://developer.chrome.com/blog/web-audio-autoplay) 要求被 suspend 的 AudioContext 在用户交互后显式 resume。
- 本批非目标：不接入真实 SR/SS Provider、Browser↔Gateway RM-B、WebSocket/WebTransport、wire codec、CR/AB、Agent、Tool、Task、完整 X-WEB UI/部署/CSP/CORS、AIO-C 性能 closure 或 Web Alpha release Gate。Browser Speech 继续是明确 fallback；AIO-B 真机通过也不等于 P1/P2 纵向路径完成。
- 重新评估条件：目标客户要求另一个浏览器/OS 进入 Alpha；AudioWorklet 在声明基线上不能稳定取得 frame；真实 SR/RM 必须消费 MediaRecorder container 或不同 frame contract；20ms mono Float32 中间格式造成不可接受的质量/性能；页面后台连续采集成为明确产品需求并有可接受隐私策略；或浏览器无法提供足以支撑 ACG presentation truth 的播放事实。

## D-059 P2 真实 Agent 路径采用 Harness round 权威、精确取消、text presented history、两阶段 admission 与保留式关闭

- 日期：2026-08-05
- 状态：Accepted interface decision（用户明确接受 Integration Owner 推荐组合 `1A 2A 3A 4A 5A`；本决定解除接口设计 blocker，不代表实现、review、集成或 Gate 已通过）
- 背景：AB-B 只会投影已有权威 Harness round event，CR-B 只会从 surface PresentationAck 选择 presented history；现有 `JiuWenSwarm.process_message_stream()` 只返回 legacy chunks 并直接写 Session History，现有 `CHAT_CANCEL`/DeepAdapter cancel 又只能命中 session-current work。探索性 P2 Adapter 因伪造 round authority、把 session-current cancel 当成 exact cancel、在 Bridge admission 前修改 CR，以及让 caller cancellation/卡死 stream 消耗 teardown truth 而被撤回。真实 P2 Agent 路径因此需要相邻 Agent/Harness 接口决定，而不能由 compatibility Adapter 静默创造语义。
- Round authority 决策：实际 Agent/Harness Runtime 在 dispatch reservation 时分配 canonical opaque `round_id` 和可信内部 reservation binding，并以自身 authority 产生不可变 v2 `round.accepted/running/blocked/decision_required/terminal` EventEnvelope。只发真实观察到的状态；Agent chunk、Adapter completion 或 stream end 不得制造 lifecycle，缺 terminal 的 stream 保持 incomplete/error。Agent Bridge 只验证、传递和投影这些源事件。
- Cancel 决策：`round.cancel` 精确绑定 `command_id + ScopeRef + request_id + round_id + trusted round binding`，由同一 Harness owner 在产生效果前原子验证。错 scope、错 request/round、陈旧、重绑定或 terminal target 以零无关 Agent/Tool/Task effect 拒绝；exact replay 返回原结果，fingerprint 冲突零 mutation。ACK 不等于 terminal，completion 可在竞态中获胜；barge-in、`playback.stop` 和 `response.cancel` 永不隐式升级。
- History 决策：正式 P2 Agent seam 只消费 committed turn 和 CR 显式选择的 context，不调用 legacy user/assistant/tool/error/final history 写钩子，也不在首个 slice 隐式运行 legacy cloud/auto-memory history hooks。Alpha history surface 冻结为 `text`：committed user turn 可由正式 writer 写入，assistant 只有 UI text PresentationAck 确认的连续 prefix 可按精确 response/generation/surface/cursor 幂等持久化；audio ACK 仅是播放证据，unACKed/fenced suffix 永不入 history。Direct Chat/fallback 保持不变。
- Admission 决策：Bridge/Harness 在任何 CR response mutation 或 generation fence 前执行两阶段 `reserve -> CR accept_response -> commit/abort`。Reservation 原子占用有界 capacity、request ledger、scoped round binding 和 Harness reservation；concurrent exact replay 共用一份 reservation/completion，冲突、容量耗尽或 Harness 拒绝在 CR 零 mutation 前失败。owner cancellation/CR failure 必须 abort；reservation 有界过期且同 identity 不可被过期后重放成新 execution。
- Shutdown 决策：首次 close 创建唯一 retained coordinator，所有 caller 以 shielded、bounded wait 观察同一结果；caller cancellation/timeout 不取消 teardown或消费结果。关闭立即停止 admission，drain/settle 已接受 work/output，超时保持 `closing/cleanup_pending` 并返回明确 pending/timeout，只有 worker/subscription/queue/cleanup 全部 terminal 后才是 closed。Subscription detach 不等于业务取消；临时 WebSocket/media 断线在 interaction 仍 open 时不取消，显式 `interaction.closed` 另发一次精确幂等 `round.cancel`，基础设施 shutdown 本身不隐式取消 round/task。
- 实施与证据：稳定执行合同记录在 [P2 Real Agent + CR interface Task Packet](../roadmap/P2_REAL_AGENT_CR_INTERFACE_TASK_PACKET_2026-08-05.md)。该批涉及 shared authority/protocol 与并发关闭，按 Tier 3/2 的完整适用 D-032、D-053 三轮 review、真实 facade 正向/反向证据和 feature-off/legacy regressions 闭环。P3 authenticated composition、browser PresentationAck、real media/Speech 与 cumulative Gate 仍独立开放；实现通过也只能先记 formal foundation，不自动获得 Replacement Ledger credit。
- 重新评估条件：真实 Harness 无法拥有/分配 round identity 或产生 source event；无法在 Agent/Tool effect 前完成 exact reservation/cancel target check；正式 Agent 上下文无法脱离 legacy implicit history/memory hooks；跨进程/重连要求把 P2 round 提升为 durable replay authority；或产品要求 interaction close 后 round 独立继续而不是精确取消。任何变化都必须重新审查 authority、cancel、history、admission 和 shutdown 的组合语义。

## D-060 Live Voice Alpha 采用四实现 Session、单一集成所有权和有界本地 Git 例外

- 日期：2026-08-06
- 状态：Accepted execution decision（用户明确批准执行，并明确取消本任务中所有本地 Git 操作的逐次批准；任何远端 ref 更新仍需单独精确批准）
- 背景：剩余 Alpha 工作可分为 P1、P2、P3alpha 和横切四个长期非重叠实现 lane，但 Web auth/activation、共享 Authority/协议、产品 Composition、累计 Gate 和冲突裁决存在跨 lane 依赖。D-052 的单实现 lane 会把可并行的 leaf/package 工作串行化；完全分散合入又会让共享语义和 review 失去单一 owner。
- 决策：建立四个实现 Session：P1 Speech/Media、P2 Runtime/Interaction/Agent Bridge、P3alpha Task/Confirmation、X-OBS/X-WEB/X-E2E；当前 Main Session 是唯一 Integration Owner，同时推进共享依赖、执行完整 diff 冷审、分配 integration lease、合入已通过候选并运行累计验证。独立 review 按 D-046/D-053 风险在需要时启动，不占用某个实现 lane 的所有权。稳定范围、文件边界和 handoff 记录在 [Alpha parallel execution plan](../roadmap/ALPHA_PARALLEL_EXECUTION_2026-08-06.md)。
- 本地 Git 例外：在该执行计划范围内，Main 和 Task Sessions 无需再次取得用户批准即可 stage、commit、amend、squash、rebase、merge、cherry-pick、创建或更新本地 branch/ref/worktree，以及在单写 integration lease 下完成本地 task integration。Task Session 在 review 通过后可生成自己的最终 commit；Main 可拉取、整理、修正和本地合入这些 commit。语义修复必须回到 owning Session，或由 Main 明确记录为 integration glue 并重跑受影响 review/tests。
- 远端边界：上述例外不包含任何 push 或远端 ref 变更。普通 push、force/force-with-lease、远端 branch/tag 创建、更新和删除都必须在操作前取得对精确 remote/ref/commit/方式的单独批准；Task Session 不得 push。
- 不变量：共享 Authority/Composition/协议文件与最终 activation/Gate 归 Main；同一 integration worktree 同时只有一个 writer；formal/fallback/demo_substitute/unavailable/disabled 如实表达；缺少 Provider、凭据、部署、设备或真实 owner 时 fail closed，不以 mock、contract-only、测试数量或本地 Git 集成宣称 Alpha/production-ready；Replacement Ledger 仍只按真实产品验收更新。
- 重新评估条件：文件范围无法保持非重叠；两个 lane 必须同时修改同一共享语义；integration lease 不能防止交叉污染；review 往返成本持续高于并行收益；用户改变并发数、合入职责或 Git 授权；本地 immutable Alpha candidate 已关闭；或任何远端更新进入范围。

## D-061 Alpha integration smoke 在完整 reviewed cherry-pick 批次后统一执行

- 日期：2026-08-07
- 状态：Accepted execution amendment（用户明确要求调整 D-060 的集成验证节奏）
- 背景：D-060 原计划在每个 segment 合入后重复累计 smoke。当前四个 Task commit 均已在各自 branch 完成风险相称的 focused tests、冷审和独立 review，再逐个合入同一 integration branch；每次 cherry-pick 后重复全量 smoke 会消耗时间，但不会增加独立语义证据。
- 决策：Main 仍按真实依赖顺序逐个声明 source branch、exact commit、target branch 和 cherry-pick/merge 方式并保持单写 integration lease，但不在每个无冲突 cherry-pick 后运行累计 smoke。完整 reviewed commit 批次全部合入后，只运行一次累计 smoke，覆盖正常产品 route、authority denied/unavailable、correlation/binding mismatch、cleanup/retry、feature-off 零副作用及 fallback/Demo/legacy 回归。
- 例外：任何语义冲突、手工 conflict resolution 或 integration glue 都必须先完成受影响检查和必要 review；若它改变共享 authority/protocol/lifecycle 语义，不得等待最终 smoke 来代替缺失的 review closure。
- 不变量：该优化不改变 D-046/D-053 的 task-level 验证、D-060 的单写与远端批准边界、真实 E2E/Immutable Alpha Gate，也不允许以一次 aggregate smoke、mock 或测试数量授予 Replacement Ledger credit。
