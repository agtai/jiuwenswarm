# Live Voice 决策记录

本文件记录已经明确接受的产品和工程取舍。后续 Codex 不应仅因为当前代码更容易而静默改变这些决策；如需改变，应新增决策并把旧决策标记为 `Superseded`。

旧决策的历史正文可以保留，但状态行必须指出被后续决定取代的当前含义；实现进度始终由 `STATUS.md` 提供。

## D-001 方案知识保存在 Git 跟踪的普通文档中

- 日期：2026-07-31
- 状态：Accepted（“知识进入 Git 跟踪文档”的原则保留；旧 `docs/zh/live-voice/` 路径由 D-040 取代，本地 commit/远端 push 操作由根 `AGENTS.md` 和 D-074 的当前规则控制）
- 背景：需要在多台机器上通过 GitHub 同步代码并让新的 Codex 会话快速接续。
- 原决策：完整方案和 Demo 方案保存在 `docs/zh/live-voice/`；D-040 后续把权威位置调整为根 `live-voice/`。不把完整知识仅存入 `.codex`、`.agent`、本地数据库或聊天记录的原则不变。
- 原因：普通 Markdown 可审查、可 diff、可提交、可跨工具阅读；隐藏工具目录容易与某一运行环境绑定。
- 原影响：实质性工作更新 STATUS，新取舍更新本文件。D-074 当前允许已授权任务形成 coherent local commit；所有远端 ref 更新仍按根 `AGENTS.md` 单独精确批准。
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
- 决策：每个模块或逻辑切片在语义开发前、实现完成后各做一次正式回顾。两次都必须重新理解完整方案、当前阶段、模块契约/非目标、上下游、现有 tests 和实际风险，并维护 test inventory、每项 test 的设计原因以及 `scenario → test/evidence` 矩阵。每个改变的不变量必须同时有正向正确场景和反向拒绝场景；反向业务动作必须明确失败、拒绝或安全 no-op，并断言所有禁止副作用为 0，而测试进程本身应 PASS。边界、状态、时序、重复/乱序、并发/重试、恢复、scope/权限、feature flag/降级、协议/持久格式兼容和真实跨模块路径按适用性覆盖；`N/A` 必须说明理由。当前风险分级、场景维度和 review cadence 的稳定执行权威为根 [TESTING.md](../../TESTING.md)；本段历史的通用双回顾要求继续受 D-046/D-074 限定。
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
- 影响：旧决策中的历史路径、旧分支和当时状态仍作为历史事实保留，但当前操作必须以根 AGENTS、`live-voice/README.md`、`live-voice/STATUS.md` 和 `DOCUMENTATION_RULES.md` 为准。D-074 当前允许已授权文档任务形成 coherent local commit，但不自动授权任何 push。
- 重新评估条件：仓库出现可自动生成并可靠校验的文档索引/状态投影，或根知识库影响上游文档发布流程。

## D-041 以 Sol 冻结高风险语义并由非 Sol 模型执行有界工作包

- 日期：2026-08-03
- 状态：Partially superseded（风险判断和历史设计职责保留；面向未来任务的非 Sol 执行分工由 D-052 取代，原 D-031-first 排序和普遍 D-032 流程由 D-046 取代，交付/review/commit 节奏由 D-074 取代）
- 当前解释：以下非 Sol owner、交接和成本分配正文只记录接受本决定时的策略，不能用于分配当前或未来任务。
- 背景：Live Voice 后续同时包含契约、并发状态机、取消与副作用安全、持久化、真机媒体和大量可机械执行的 Adapter/tests 工作。高能力模型额度有限；若让同一模型承担全部编码，会把稀缺推理消耗在已经能够由明确规范驱动的实现上。反过来，若让执行模型自行决定状态权威、错误语义、恢复、权限或测试放行标准，则可能把错误实现固化为预期。
- 优先级决策：P1/P2/P3 是能力平面，不作为简单的串行开发顺序。当前排序以 D-046 为权威：先在 1–2 天内冻结并实现 ACG critical kernel，同时建立累计 Integrated Demo 的 route telemetry 与 Replacement Ledger；随后 P1、P2、P3alpha 和集成轨按已冻结依赖并行。D-031 只保留 Day 5/Day 7 决策点，若正式 `TC-B + TaskEvent/projection` 不能及时进入 Demo，再把最小单任务 monitor 限时为 1–2 个工作日；不再把完整 D-031 作为共享 Contract Gate 和全部能力轨的前置任务。
- 模型职责决策：GPT-5.6 Sol 是指定的设计与审查模型，负责 D-046 风险分级要求的开发前/开发后回顾、模块定义与非目标、适用的 P/N/B/S/T/C/R/I/F/K/X 场景及 test oracle、跨模块 schema/state authority/identity/ownership/cancel/commit/fence/compatibility、安全与 durability 边界、架构变更、证据解释以及 `CLOSED/PARTIAL/BLOCKED` 和版本放行判断。Sol 不承担已冻结规范下的常规执行和实现，除非用户以后明确改变该分工。
- 执行职责决策：代码实现交给非 Sol 模型，例如已配置环境中的 DeepSeek-V4-Flash 或其他执行模型。执行模型适合在所消费的契约、状态转换、scenario IDs、允许与禁止副作用、目标文件和验证命令齐全后，实现 types/ports/reducers/adapters/fakes/conformance、受限 UI/协议接线、测试、fault injection、instrumentation、benchmark runner、打包和机械文档整理。Tier 2/3 或共享契约 `*-A` 工作包由 Sol 冻结 contract/oracle，执行模型落实 types/fake/conformance；其余包按 D-046 的风险等级采用最小充分交接。`*-B`、`*-C` 由执行模型按其实际依赖 Gate 实现和验证，再由 Sol 审查高风险语义与累计证据。
- 停止条件：执行模型不得自行新增或放宽契约、把 `unknown/unsupported/error` 改成成功、改变状态权威或 cancel scope、删除或弱化失败断言、用 snapshot 更新掩盖差异，或把 Demo consistency scope 写成生产安全。发现规范歧义、上下游冲突、需要新状态/错误、测试与设计不一致或无法证明禁止副作用为零时，必须停止该语义分支并交回 Sol；不能凭当前代码更易实现而猜测产品行为。
- 历史交付约束：接受本决定时，工作包要求完整交接并保持未提交等待逐次批准。当前由 D-074 取代为：开发中做 affected review，模块收口审完整 scoped diff，阶段收口审累计 diff；已授权任务可形成 coherent local commit，所有 push 仍须单独批准。具体模型/provider、凭据、API base 和可用性属于机器私有条件，不写成 Git 可恢复能力。
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
- 状态：Partially superseded（累计路线、范围和风险分级保留；Windows/X-WIN 载体由 D-055 取代，签名 Gate/评分由 D-071 取代，固定三轮/逐次 commit 审批节奏由 D-074 取代，D-060/D-062 的并行模型只在 active packet 中按需启用；D-075 将 `W1/W2/W3/W4` 进一步限定为历史交付窗口，并以 S0–S9/A0–A3 表示当前顺序状态）
- 背景：用户明确项目目标不是无限期平台建设，也不是只维护 V0 或只完成 D-031。V0 要第一时间打通真实端到端，随后正式模块沿同一工程路径持续替换 Demo 中的手工代码、固定限制和兼容实现；第 2 周 Demo 达到可审计的 90% 完成度，第 3–4 周完成 P1 + P2 + P3，若完整 P3 风险过高则 P3alpha 可作为承诺结果。完整方案现有 31 个 Alpha 工程包的顺序时间盒约为 47–78 人日，尚未包含完整 P3 扩展；若按每个小切片独立 D-032 checkpoint、单执行流和末期统一集成推进，四周目标在流程上即不可达。
- 接受时的目标定义：原四周并行范围写作 **Integrated Windows Alpha = P1 + P2 + P3alpha + Context/Progress/Failure/Observability + 三个真实纵向切片 + P2/P3alpha 联合 Gate**。D-055 已把 carrier 映射为 Web/X-WEB，D-052 已取消原并行日历承诺；D-060 的有界并行只改变执行分配，不恢复该日历承诺。能力范围仍不是 RC/Production，完整 P3 仍是 stretch，P3alpha 是当前 Alpha 的最低 Task 范围。
- 两周决策：Week 2 必须运行一个累计 Integrated Demo，而不是分别运行互斥的 V0、稳定句和 Task 样例。完成度按权威 Demo Replacement Ledger 的用户旅程权重计算，不按代码行数、测试数、文件数或模块名计数；总分至少 90/100，且 committed-only、副作用确认、精确 identity/scope、stale fence、unknown/error 不冒充成功、文字 flag-off 回归等 mandatory invariant 全部通过。`fallback`、`Demo substitute`、`unsupported` 和 `unknown` 必须可见；substitute 可以证明类别价值，但不能自动获得正式模块全部分值。
- 演进决策：V0 `ee2896a4` 保持不可变证据基线。新模块通过 Port/Adapter/capability/feature flag 逐段接管同一累计 Demo，必须由 route telemetry/trace 证明每段实际使用 formal、fallback 或 substitute；不另建第二套假 UX，也不等到所有模块完成后再进行首次集成。
- 并行决策：共享 ACG critical kernel 在最初 1–2 天冻结并实现，包含 identity/scope、authority、committed input、核心 lifecycle、四种 cancel、generation fence、Event/Error/Capability 和 feature-off primitives。随后 P1（AIO/SR/SS）、P2（CR/RM/II/AB）、P3alpha（TC/ED/VB）与 X-OBS/X-E2E/Windows 集成按依赖并行。ACG 的 ContextRef 全量策略、presentation ACK、完整 restart reconciliation 等扩展仍属于完整目标，但只在消费它们的 B/C 接线前成为局部门槛，不阻塞无关 A 包。
- D-031 决策：D-031 不再是整个项目无条件第一任务。它是 P3alpha 轨上的 legacy Demo Adapter 候选：若 `TC-B + TaskEvent/projection` 可在 Day 7 前进入累计 Demo，则跳过或缩减 D-031；否则把最小单任务 monitor 限时为 1–2 个工作日。必须保留 single in-flight、精确 identity/target、迟到结果 fence、错误不冒充终态、零 Chat mutation 和播报仲裁，但不得把临时 poll 路径扩成通用多任务、持久 replay、跨进程恢复或第二个 Task Core。
- D-032 决策：测试按风险分级。Tier 0 文档/机械/纯重构执行受影响检查；Tier 1 普通功能/Adapter/UI 覆盖正向旅程、关键反例/flag-off、受影响集成和回归；Tier 2 状态/并发/副作用边界覆盖全部适用维度与零禁止副作用；Tier 3 共享协议、authority、安全、durability 与阶段放行执行完整适用 D-032、fault/recovery 和真实路径证据。D-074 当前要求仅在新增/改变高风险契约时先做设计 checkpoint，并把 review 聚合到模块/阶段收口；普通 local commit 无需逐次批准，所有 push 仍须单独精确批准。
- 历史模型分工：本决定接受时沿用 D-041；D-052 后续把设计、实现、测试和审查统一为当前 GPT/Sol 默认单线，D-060 再为有界 Alpha 范围建立四个 GPT/Sol 实现 Session 和单一集成所有权。这里保留的跨轨契约、高风险判断和 Gate 责任仍有效，但不授权切换到外部模型。
- 历史文档影响：本决定接受时要求 STATUS 保存 replacement ledger 并以 Week 2/Week 4 Gate 表达路线；D-071/D-072 已退役该 ledger/evidence Gate，D-075 现以 S0–S9/A0–A3 和 milestone-specific showcase 取代其当前执行解释。详细设计继续保留在冻结 review record，Runbook 必须诚实标注实际可运行路线。
- 原因：架构规模与明确的 P1/P2/P3alpha 目标匹配，真正的风险是串行 Gate、临时 Adapter 过度建设和最后一刻集成。风险分级不降低 committed-only、精确对象、副作用、fence、truthfulness 和兼容性底线，而是把完整证明集中到真正高风险边界和累计 Gate，使三至四周并行交付具有可执行性。
- 重新评估条件：Week 1 结束仍只有一个有效执行轨；共享 kernel 超过两天仍不能支持并行；Week 2 route telemetry 无法证明 90% 分值；真实 Provider/Web/Executor 条件不可用；P3alpha 联合 Gate 暴露必须提前实现完整 P3 的依赖；或用户改变范围、资源并行度、日历目标或生产责任。D-052 已触发资源假设重新估算，D-060 已改变有界 Alpha 的资源并行度，但当前仍没有接受新的四周日历承诺。

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

## D-052 后续开发默认由当前 GPT/Sol 单线完成

- 日期：2026-08-04
- 状态：Partially superseded（替代 D-041、D-048、D-049 中面向未来任务的模型分工；D-060/D-062 后来在接受的 W2→Alpha 范围内建立按批次自适应的 GPT/Sol worker 图和单一集成 owner，D-052 在该例外外继续作为默认分配）
- 决策：后续包固定由当前 GPT/Sol 设计、实现、测试和审查，不再提醒、委派或切换到 DeepSeek/其他外部执行模型。Tier 2/3 的 identity、authority、state、cancel、security、concurrency、durability 和 release 判断始终由 GPT/Sol 负责。
- 历史候选：已有外部候选只作为审查历史或可选择复用的素材；任何片段都要按当前合同、完整 diff 和实际测试重新验证，不得整体 merge/cherry-pick 来代替实现与审查。
- 影响：dated Week 1 plan 的包边界和风险 Gate 继续有效，但其中历史 owner/model 字段不再决定当前执行。原三到四周估算依赖多条并行实现轨；D-060 的有界并行不自动恢复原日历承诺，仍须按真实依赖和速度重新估算。
- 重新评估条件：用户明确作出新的模型分工决策，或项目范围、时间和可用资源发生变化。D-060 已触发一次有界重新评估，其文件所有权、集成 lease 和远端边界只在该决定范围内有效。

## D-053 高风险开发批次采用三轮 review

- 日期：2026-08-04
- 状态：Partially superseded by D-074（历史批次的三轮 review 事实保留；当前改为开发中 affected review、模块收口完整 scoped review、Tier 2/3 独立 review 与阶段累计 review）
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
- 影响：本决定不把旧 schedule/JSON 路径称为正式 TC/TaskEvent，也不增加 Demo Replacement Ledger 分值。所需实现授权后来已经取得；D-031 当前已关闭。这里的逐次 commit/push 审批是历史规则，当前 local commit/remote push 边界分别由 D-074 与根 `AGENTS.md` 决定。
- 重新评估条件：D-031 开始前正式 Store/Event/Harness 依赖已经具备并可在相同时间内进入累计 Demo；用户拒绝临时 polling 路径；或 Day 7/Week 2 范围发生变化。

## D-055 Live Voice Alpha 产品载体从 Windows Desktop/WebView2 调整为 Web

- 日期：2026-08-05
- 状态：Accepted product-carrier decision（Web 载体继续有效；D-058 后续冻结单 Chrome 基线，D-071 取代评分 Gate，D-075 取代 W3/W4 的当前阶段用法）
- 背景：当前可运行 V0 和 Post-V0 Demo 已经通过 JiuwenSwarm Web 前端、浏览器麦克风和浏览器音频路径验证产品价值；继续把 Windows `.exe`、WebView2 权限、原生设备生命周期和安装包作为四周 Alpha Gate，会把平台产品化工作放在真实 Speech/Media/Conversation/Task 纵向链之前。用户已经决定当前交付载体改为 Web，但 D-046、roadmap、STATUS 和 Alpha acceptance 仍保留 Windows Alpha 表述，造成当前目标与文档权威不一致。
- 产品决定：当前范围目标为 **Integrated Web Alpha**。本决定接受时用 `W2/W3/W4` 表示累计交付顺序；D-075 现将其限定为历史窗口，当前 Alpha 使用 S5–S8/A0–A3。D-052 取消了原四周并行估算的日历承诺，后续有界并行也不自动恢复该承诺。首期载体是 JiuwenSwarm 桌面 Web 前端；实际验收必须记录明确的浏览器、操作系统、设备和网络标签，但不把固定验收环境冒充公开兼容矩阵。D-058 已选择单一桌面 Google Chrome Alpha 基线；移动 Web、PWA、Firefox、Safari 和全平台兼容不属于当前 Alpha 范围。
- 安全与部署边界：部署环境必须使用安全上下文；`localhost` 只作为本地开发和受控验收例外。Speech/模型 Provider 凭据只能保存在 Gateway/服务端，浏览器不得持有长期 Provider 密钥。麦克风权限、权限撤销、设备变化、autoplay/user-activation、页面隐藏/后台、CSP、CORS、反向代理、连接失败和文字降级必须在 Web Alpha Gate 中可见且无静默失败。原始音频默认不持久化。
- 架构保持：P1/P2/P3alpha、ACG v2 wire contract、identity/scope/authority、committed-only、四种取消作用域、generation fence、presented history、Task/Core/Executor 边界和风险分级不变。Week 2 90% 评分在本决定接受时未改变，但后来由 D-071 退役。Web 是产品载体变化，不授权 Browser、UI、Provider 或 Transport 成为新的生命周期权威。
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
- 状态：Partially superseded by D-062/D-074/D-075（四个历史 lane 仅保留分解参考；固定 Session 数和 Session-only 形式已被取代，ownership/single-writer/Main-only integration 只在 active parallel packet 中启用；普通本地 commit 由 D-074 管理，任何远端 ref 更新仍需单独精确批准）
- 背景：剩余 Alpha 工作可分为 P1、P2、P3alpha 和横切四个长期非重叠实现 lane，但 Web auth/activation、共享 Authority/协议、产品 Composition、累计 Gate 和冲突裁决存在跨 lane 依赖。D-052 的单实现 lane 会把可并行的 leaf/package 工作串行化；完全分散合入又会让共享语义和 review 失去单一 owner。
- 决策：建立四个实现 Session：P1 Speech/Media、P2 Runtime/Interaction/Agent Bridge、P3alpha Task/Confirmation、X-OBS/X-WEB/X-E2E；当前 Main Session 是唯一 Integration Owner，同时推进共享依赖、执行完整 diff 冷审、分配 integration lease、合入已通过候选并运行累计验证。独立 review 按 D-046/D-053 风险在需要时启动，不占用某个实现 lane 的所有权。稳定范围、文件边界和 handoff 记录在 [Alpha parallel execution plan](../roadmap/ALPHA_PARALLEL_EXECUTION_2026-08-06.md)。
- 本地 Git 例外：在该执行计划范围内，Main 和 Task Sessions 无需再次取得用户批准即可 stage、commit、amend、squash、rebase、merge、cherry-pick、创建或更新本地 branch/ref/worktree，以及在单写 integration lease 下完成本地 task integration。Task Session 在 review 通过后可生成自己的最终 commit；Main 可拉取、整理、修正和本地合入这些 commit。语义修复必须回到 owning Session，或由 Main 明确记录为 integration glue 并重跑受影响 review/tests。
- 远端边界：上述例外不包含任何 push 或远端 ref 变更。普通 push、force/force-with-lease、远端 branch/tag 创建、更新和删除都必须在操作前取得对精确 remote/ref/commit/方式的单独批准；Task Session 不得 push。
- 不变量：active parallel packet 中共享 Authority/Composition/协议与最终集成归 Main；同一 integration worktree 同时只有一个 writer；formal/fallback/demo_substitute/unavailable/disabled 如实表达；缺少 Provider、凭据、部署、设备或真实 owner 时 fail closed，不以 mock、contract-only、测试数量或本地 Git 集成宣称 Alpha/production-ready。Replacement Ledger 已由 D-071 退役。
- 重新评估条件：文件范围无法保持非重叠；两个 lane 必须同时修改同一共享语义；integration lease 不能防止交叉污染；review 往返成本持续高于并行收益；用户改变并发数、合入职责或 Git 授权；本地 immutable Alpha candidate 已关闭；或任何远端更新进入范围。

## D-061 Alpha integration smoke 在完整 reviewed cherry-pick 批次后统一执行

- 日期：2026-08-07
- 状态：Accepted reusable integration rule（完整 reviewed integration batch 后一次累计 smoke 继续有效；D-071 退役 Gate/Ledger，D-074 取代 D-053 review cadence，D-075 把该规则放在 A2 candidate closure）
- 背景：D-060 原计划在每个 segment 合入后重复累计 smoke。当前四个 Task commit 均已在各自 branch 完成风险相称的 focused tests、冷审和独立 review，再逐个合入同一 integration branch；每次 cherry-pick 后重复全量 smoke 会消耗时间，但不会增加独立语义证据。
- 决策：Main 仍按真实依赖顺序逐个声明 source branch、exact commit、target branch 和 cherry-pick/merge 方式并保持单写 integration lease，但不在每个无冲突 cherry-pick 后运行累计 smoke。完整 reviewed commit 批次全部合入后，只运行一次累计 smoke，覆盖正常产品 route、authority denied/unavailable、correlation/binding mismatch、cleanup/retry、feature-off 零副作用及 fallback/Demo/legacy 回归。
- 例外：任何语义冲突、手工 conflict resolution 或 integration glue 都必须先完成受影响检查和必要 review；若它改变共享 authority/protocol/lifecycle 语义，不得等待最终 smoke 来代替缺失的 review closure。
- 当前不变量：该优化不改变 D-046 风险验证、active packet 的单写/集成所有权或远端批准边界；一次 aggregate smoke、mock 或测试数量不能替代 D-032 场景、真实路径或 A3 人工验收。D-053 固定 cadence 与 Replacement Ledger/Immutable evidence Gate 已分别由 D-074 和 D-071 取代。

## D-062 W2 优先并采用按批次自适应的并行执行图

- 日期：2026-08-07
- 状态：Accepted reusable execution model（W2 优先级和历史 packet 已完成；当前仅在新批次声明独立 lane/ownership 时启用，不构成永久并行任务分配）
- 历史里程碑优先级：W2 当时的关键路径只服务累计 Integrated Demo；D-071 已关闭其 Gate/Ledger 解释，W2 现为 `PRODUCT-ACCEPTED`。D-075 把当前优先级固定为 S5/A0 Alpha baseline freeze，Alpha PASS 后才进入 S9 完整 P3、D1/D2 和生产化。
- 自适应执行图：D-060 的 P1、P2、P3alpha、X 四项是一次历史上有效的逻辑分解，不是永久 worker 数量。Main 在每个 coherent batch 开始时按依赖独立性、文件和语义所有权、关键路径、外部阻塞、review/integration 吞吐与实际工具容量，选择最小的有用 lane 图；可以拆分、合并、暂停或结束 lane，不设固定数量，也不得为占满并发而创建无独立产出的任务。Main 自身计入可用并发容量。
- Worker 形式：一个 lane 可以由独立 Session/worktree、bounded subagent 或 Main 承担。独立 Session/worktree 按包边界持有自己的 branch 和 reviewed final commit。与 Main 共享 worktree 的 subagent 只编辑明确授权且不重叠的文件，不切换 branch、不 stage/commit、不修改历史；Main 在完整 diff review 后统一执行 Git 操作。只读调查、测试和独立 review 优先使用 bounded subagent；执行实现的 worker 不同时充当该批的独立 reviewer。
- 集成和 Git：Main 继续是共享 Authority/协议/Composition、集成分支、stage/commit、分支历史、累计证据和 Gate 的唯一 owner。共享 integration worktree 任一时刻只有一个持明确 lease 的 filesystem editor；若由 shared-worktree subagent 编辑，Main 和其他 agent 在 lease 返回前不同时编辑。D-060 的有界本地 Git 例外扩展到当前 W2/Alpha execution packet 内的上述 worker 形式，但不扩展任何远端权限。每次 normal/force push 或其他远端 ref 更新仍需用户对精确 remote/ref/commit/方式单独批准，Task worker 永不 push。
- 当前验证：D-046 风险分级和 D-061 的批次后累计 smoke 保持；review cadence 由 D-074 控制。Tier 0/1 不制造 Tier 2/3 仪式；缺少真实 Provider、设备、Executor 或用户感知时保持 `PARTIAL/BLOCKED`，不用更多 worker、mock、测试数量或文档完成度换取 Alpha closure。
- 历史执行合同：W2 范围、依赖和防漂移规则保留在 [90% Demo execution packet](../roadmap/DEMO_90_EXECUTION_2026-08-07.md)，不得作为当前队列。当前任务选择由 D-075/STATUS 与新的 bounded packet 决定；只有 packet 激活时才继承适用的 single-writer/ownership 规则。
- 重新评估条件：当前 A0/A1 batch 范围变化；实际 lane 冲突/协调成本持续高于并行收益；工具并发容量改变；共享 worktree 无法保证隔离；用户改变里程碑、并发、Git 或远端授权；或工作没有 active parallel packet。

## D-063 用户明确要求最少介入时启用任务级本地自主推进

- 日期：2026-08-07
- 状态：Partially superseded by D-074（普通本地 stage/commit 已成为已授权任务的默认权限；本决定继续控制更广的最少介入、历史组合/改写和用户介入边界）
- 触发和期限：只有用户明确要求“最少介入”“自主推进、只在必须时找我”或等价的 reduced-approval handling 时才启用；普通“继续”不自动启用。授权只覆盖已经接受的目标和 active routed packet，跨 Session、context compaction 和 task resume 保持有效，直到该任务/候选关闭、工作离开授权范围或用户撤销。STATUS 只记录当前是否 active。
- 本地自主权：在适用检查和 review 完成后，Main 自行选择 coherent commit 边界和消息，可无需逐操作批准地 stage、commit、amend、squash、rebase、merge、cherry-pick，以及创建或更新 local branch/ref/worktree。独立 worktree worker 和 shared-worktree subagent 仍受 active packet 的所有权、review、single-writer、Main-only integration 与 Git 限制；任何 worker 都不因本决定获得自行集成或 push 权限。
- 不扩张边界：最少介入只减少审批往返，不扩大产品/任务范围，不降低测试、D-074 review、acceptance、truthfulness 或 fail-closed 要求，不允许覆盖无关用户修改，也不授权 destructive/hard-to-recover 操作、凭据披露或迁移、外部 account/provider/billing 变更、公开部署、安全策略选择或未经接受的重大产品语义变更。遇到这些边界时继续所有不受阻工作，并向用户说明精确问题、为何需要介入、需要执行的动作和推荐方案。
- 远端边界：默认不包含任何 remote ref 更新。只有用户另行授予包含精确 remote、branch/tag、允许的 update mode 和有效窗口的窄授权时，Main 才可在该窗口内执行相应远端操作；否则每次 normal/force push 及远端 branch/tag/ref 创建、更新或删除仍须单独精确批准。Task worker 永不 push。
- 当前影响：原 W2 minimum-intervention activation 随候选关闭成为历史。普通已授权任务的本地 stage/commit 现在由 D-074 直接允许；只有用户再次明确要求更广的最少介入或历史组合/改写时才重新激活本决定。完整 P3/production 或其他新 scope 进入时仍须由 STATUS/用户确认边界。
- 重新评估条件：用户撤销或收窄授权；任务或 immutable candidate 关闭；进入未接受范围；需要远端、破坏性、凭据/账户、部署/安全或重大产品选择；发现自动 commit 边界持续混杂无关修改；或 required review/test 无法在不请求用户输入的情况下诚实完成。

## D-064 W2 真实 Speech 验证采用 Gateway 托管的 OpenAI-compatible Batch Speech

- 日期：2026-08-08
- 状态：Accepted W2 runtime selection（用户选择采购 OpenAI API credit，并指定 `gpt-4o-mini-transcribe` + `gpt-4o-mini-tts` 完成当前真实验证；这是 W2 候选的 Provider 选择，不是长期独家供应商或 production 授权）
- 候选配置：Gateway 使用 `LIVE_VOICE_SPEECH_PROVIDER=openai-compatible`、`LIVE_VOICE_SPEECH_API_BASE=https://api.openai.com/v1`、STT `gpt-4o-mini-transcribe`、TTS `gpt-4o-mini-tts`，初始 voice 使用 `marin`。真实启动前先执行最短 STT/TTS 探针；若 Provider 拒绝 alias、voice 或实际响应合同，停止本 attempt，记录精确非敏感错误，再冻结 Provider 实际接受的 snapshot/voice，不得在一次 evidence attempt 内静默换模型。
- 凭据和计费边界：API key 只进入 Gateway 启动进程的机器私有环境，不进入浏览器、AgentServer、Git、日志、证据或聊天。购买 credit、账户、billing 和 key 创建仍由用户控制；本决定不授权自动充值、外部账户变更或凭据迁移。正式产品浏览器只向 Gateway 的受控 Speech RPC 提交已绑定音频/文本，不直接调用 Provider。
- 音频和 HTTP 边界：所选 OpenAI Adapter 对所有请求声明 `Accept-Encoding: identity`，只接受无 `Content-Encoding` 或规范化后精确为 `identity` 的响应，并通过 raw stream 按实际字节限流；其他编码在读取 body 前以不可重试协议错误 fail closed，不使用 HTTPX 隐式解压。`/audio/speech` 明确请求 `response_format=pcm`，并按 Provider 文档只接受 24 kHz、mono、signed PCM16 little-endian、无容器头的有界原始字节；Gateway 先生成固定 44-byte canonical WAV，再在浏览器 AIO-B playout rate 不同时用显式 capability `server_linear_pcm16_mono` 执行确定性的 server-owned 线性重采样。同采样率保持 PCM 样本并输出 canonical WAV。空响应、奇数字节、超限、未知 capability 或不一致结果全部 fail closed；其他 Provider 必须由各自受审 Adapter 声明真实格式，不能继承 OpenAI 假设。真实 Gate 记录 Provider、模型、voice、输入/输出 rate、转换 capability、延迟和人工实听，不从配置标签推导成功。
- 可替换性：JiuwenSwarm 保留统一 Speech Provider seam；后续可以接入本地 Qwen3-ASR/TTS、JiuwenSwarm 内建实现或其他兼容服务，但必须作为新的受审 Provider Adapter 完成能力、质量、延迟、资源、隐私、失败模式和真实设备 evidence，不能把本次 OpenAI W2 结果自动转移为本地模型 credit。
- 重新评估条件：模型/alias/voice 不再可用；API 不再满足已验证的 raw PCM 合同；延迟、成本、区域、隐私或网络不满足当前 Gate；本地 Qwen 路线准备好受审；或进入 production provider/SLO/retention/HA 选择。

## D-065 AIO-B 对 Chrome 瞬态空输入采用受限静音时间轴，持续异常仍 fail closed

- 日期：2026-08-08
- 状态：Accepted implementation correction（用户要求解决真实 Formal P1 在 Agent 文本已确认、TTS 开始后因并发 capture 停止而中断的问题；该选择只修正 D-058 在声明桌面 Chrome/Windows 基线上的 AudioWorklet 输入语义，不扩大浏览器或 release 范围）
- 观察事实：真实日志证明 P2 Agent 输出和 exact presentation ACK 已完成；下一个 capture uplink 与 TTS downlink 随后几乎同时关闭，UI 只显示被聚合的 `AUDIO_CAPTURE_STOPPED`。代码审查确认旧 processor 把 Web Audio 允许的 empty input quantum 或短 `currentFrame` 前跳立即视为 fatal，P1 的正式双工清理又会同步停止当前 playout，因此形成“开始朗读后立即中断”。该根因仍需修正后的物理复测确认；不能从自动化推导人已听见。
- 输入缺口决策：capture processor 只在真实非空输入恢复后，把一次最多 `15ms` 的前向缺口补为 PCM silence，以保持 20ms frame、sequence、sample cursor 和 AudioContext clock 连续；任何单次缺口不得覆盖完整 20ms frame。一个 `1000ms` 滚动窗口内累计补偿最多 `60ms`，因此重复亚阈值异常不能无限取得正式 duplex credit。初始 empty input 本身不发布 frame，也不能满足 capture readiness。
- 失败和诊断：单次或滚动预算超限以 `AUDIO_INPUT_GAP_EXCEEDED` fail closed；render clock 回退以 `AUDIO_RENDER_FRAME_REGRESSED` fail closed；未知 Worklet error、非法 message、sequence/sample-rate 变化保留各自稳定或 generic 原因，不再全部折叠成 `AUDIO_CAPTURE_STOPPED`。持续错误仍停止 exact response、撤销 capture/downlink authority，且不得产生 playout receipt、Agent/Tool/Task/history 或 widened cancel 副作用。
- 不扩张边界：静音只表达浏览器输入时间轴中的短暂不可用区间，不是降噪、丢包隐藏、重采样、设备切换、ASR 质量保证、physical-heard proof 或 production dropout recovery。权限/track/context/page/processor 持续故障继续 fail closed；正式 ACK 仍只能来自实际浏览器 render completion。
- 重新评估条件：修正后的真实 Chrome 仍发生中断；底层稳定原因不是输入 gap；15ms/60ms 界限不能覆盖声明基线的合法瞬态或造成可感知 ASR 质量下降；Web Audio/Chrome 行为改变；需要跨浏览器/OS 保证；或需要把合成 silence provenance 提升到 wire/Gate 合同。

## D-066 AIO-B 分离 render clock 与已物化输入边界，单调重叠仅作异常兼容去重

- 日期：2026-08-08
- 状态：Accepted implementation correction（D-065 后的第二次真实 Formal P1 复测已经识别文字、完成 Agent 回复并开始 TTS，但用户只听到“语音联调”即中断，UI 给出精确 `AUDIO_RENDER_FRAME_REGRESSED`；本决定修正该谓词和诊断，不扩大 Chrome Alpha 或 Gate 范围）
- 根因：旧实现把新回调的 `currentFrame` 与上一块已物化的结束位置 `expectedRenderFrame` 比较，并把 `currentFrame < expectedRenderFrame` 一律定义为时钟回退。这个条件只能证明输入区间重叠，不能证明 `currentFrame` 相对上一回调向后移动；旧测试甚至用严格递增的 `0 → 64` 作为“回退”例，固化了错误判据。规范连续 AudioWorklet 仍应按同一固定 render quantum 前进；真实机器缺少数值帧诊断，因此这次观察只证明稳定失败原因与错误谓词一致，不把异常重叠宣称为标准浏览器行为。
- 时钟与输入决策：processor 分别保留上一回调起点 `lastRenderFrame` 和已物化输入边界 `expectedRenderFrame`。只有 `currentFrame < lastRenderFrame` 是 `AUDIO_RENDER_FRAME_REGRESSED`；D-066 当时将相等作为独立的 `AUDIO_RENDER_FRAME_NOT_ADVANCED` 并立即 fail closed，该单回调边界现由 D-067 取代。严格递增但与已物化区间重叠的回调只作为已观察 UA/device 异常的确定性兼容：采用 first-writer-wins，丢弃重复前缀且只追加未见 suffix，不补 silence、不重复麦克风样本。重复前缀或完全物化的重复区间不推进 readiness；未见 suffix 是唯一的新真实 PCM，可正常推进 sequence/cursor/readiness。该路径不按 overlap 次数预算，因为它不合成数据且以 `currentFrame` 的唯一时间区间去重；向前缺口仍继续受 D-065 的单次与滚动预算约束。
- 传播和副作用：Worklet → Browser Adapter → Product P1 必须保留上述精确稳定原因；播放期间失败时，同一原因同时拒绝 pending playout Promise 和驱动 UI，不能再被资源释放覆盖。任一终止异常都关闭 exact capture/downlink/playout authority，产生零 playout receipt、零 widened cancel 和零额外 Agent/Tool/Task/history mutation。
- 验证边界：自动化必须分别覆盖规范连续序列（包括非零首次 `currentFrame`、固定非 128 quantum 和 suspend/resume 无回调区间）、empty input、异常 full/partial overlap 去重、真实回退、停滞、非法 frame 值及失败后的零副作用。第二次物理失败不获得 Gate/Replacement Ledger credit；只有刷新到本修正后完整听完、render ACK 完成并回到下一轮 capture 的真实运行才能关闭当前 P1 blocker。
- 重新评估条件：修正后的声明基线仍中断；出现新的精确 Worklet/Adapter 原因；UA 异常兼容造成样本丢失、重复、错误 readiness 或时间轴漂移；浏览器提供可稳定复现的不同 quantum/currentFrame 合同；或需要把数值诊断提升为受限观测事件。

## D-067 AIO-B 对同一 render frame 的短重复回调执行有界去重，持续停滞仍 fail closed

- 日期：2026-08-08
- 状态：Accepted implementation correction（D-066 后的第三次真实 Formal P1 运行已经完整识别、提交 Agent、合成并让用户听到完整“语音联调成功”，但自动下一轮 capture 最终以 `AUDIO_RENDER_FRAME_NOT_ADVANCED` 失败；该运行证明完整物理声音可达，不证明下一 capture、render receipt 或累计 Gate 完成）
- 观察与规范边界：Web Audio 的正常 `currentFrame` 应按 render quantum 单调前进；当前机器仍给出了代码唯一可能由相邻回调 frame 相等触发的稳定原因。缺少数值诊断使本记录不能把该现象推广成标准 Chrome 行为，但真实失败证明“一次相等立即终止”对声明机器过严。该异常与 D-066 的单调 overlap 一样只进入受限兼容路径，不改变规范正向模型。
- 重复回调决策：相同 `currentFrame` 继续使用已物化时间区间的 first-writer-wins 去重。若前一回调为空且尚未物化输入，同 frame 的首次真实输入可以填入该区间；若区间已完整物化，重复样本全部丢弃，不重复麦克风内容、不插入 silence、不推进 sequence/cursor/readiness。`currentFrame` 一旦前进，连续重复计数归零。
- 卡死边界：最多接受 `8` 次连续同 frame 回调；第 `9` 次仍未前进以 `AUDIO_RENDER_FRAME_NOT_ADVANCED` fail closed。真实 `currentFrame < lastRenderFrame` 仍立即 `AUDIO_RENDER_FRAME_REGRESSED`；D-065 的向前缺口预算不变。该小边界允许一次或短 burst 的实机异常，同时避免永久无进度 processor 隐藏为健康 capture。
- 活性边界：该计数只检测“回调仍发生但 render frame 不前进”，不检测完全停止产生回调的稳态冻结，也不替代既有首帧、route attach/ACK 与 downlink drain deadline；不得把它表述为通用 AudioWorklet stall detector。
- 传播和副作用：播放期间触发终止异常时，downlink admission/queue refill 同步要求 exact `playing` owner 且无 failure cleanup；故障后不得新增 audio source、receipt、cancel 或 Agent/Tool/Task/history effect。成功兼容路径必须完整 TTS、render-driven ACK 并保持下一 capture；自动化或完整实听本身都不能替代该最终状态。
- 自动化证据：processor 覆盖 8→advance/reset→8→第 9 次失败、重复后立即 regression、same-frame empty 与不同 quantum 的 unseen suffix；真实 processor→Adapter→P1 组合覆盖三帧 TTS 的最终 source teardown 重复、唯一 receipt、下一 capture 的连续 uplink PCM，以及 receipt 后持续停滞只关闭保留 capture 且无第二 receipt/late source/frame/cancel。真实 Chrome 复验仍是关闭当前 P1 blocker 的必要条件。
- 重新评估条件：修正后的真实 Chrome 仍报同一原因；实际重复 burst 超过 8 且可证明仍是可恢复输入；出现样本遗漏、重复、错误 readiness、长时间无进度或 CPU 异常；取得数值 frame 诊断并证明另一个根因；或浏览器/规范改变 render quantum/currentFrame 合同。

## D-068 Product P1 保留 30 秒完整 Batch STT 边界，并以精确原因终止超时采集

- 日期：2026-08-08
- 状态：Accepted product boundary and reviewed implementation correction（D-067 后的真实 Formal P1 运行已完成 ASR、提交真实 JiuwenSwarm Agent、完整 TTS 实听并自动进入下一轮 capture；之后未提供第二次 utterance，连续采集约 30 秒后 UI 以通用 `AUDIO_FRAME_CONSUMER_FAILED` 失败。主链与 D-067 的实机阻塞因此关闭，但该运行仍是冻结前可变源码上的辅助诊断，不是 immutable Gate evidence 或 Replacement Ledger credit；D-053 修复后复审已完成，修复实现冻结为 `e821fea84`，正式证据仍是后续 Gate 动作）
- 根因与采集边界：Product P1 为 Batch STT 保留完整的 `1500 × 20ms = 30s` 已采集 PCM frame 副本。media ACK 只证明 uplink 接收，不能释放 Batch STT 仍需要的帧；静音也会由 AudioWorklet 产生 PCM，因为当前 W2 路径没有 VAD/EOT。该限制是已物化音频容量而不是从 capture start 计算的墙钟 timer；连续采集时约 30 秒，启动等待、suspend 或无 callback 可使墙钟更长。并发下一轮 capture 在 TTS 播放前启动，因此重叠播报期间实际采集的音频计入同一容量。第 1501 帧的 Product callback 异常此前被 Browser Adapter 正确按未知 observer 异常折叠成通用 consumer failure，但丢失了 Product 已知容量边界的诊断语义。
- 边界决策：保留 30 秒硬上限，不改成无限监听、不简单增大 retention、不滚动丢弃已 ACK frame，也不把超时静音自动提交 STT。无限 retention 会扩大内存、麦克风隐私与生命周期风险；滚动丢弃会截断 Batch STT 输入；静音自动识别会产生 Provider 费用、幻觉文本及潜在 Agent/Tool 副作用。正式 VAD/EOT 或 Gateway-owned streaming recognition 属于后续 Alpha/生产设计，不在本修复中临时实现。
- 精确终止：第 1501 帧由 Product P1 同步锁定 failure cleanup，以 `AUDIO_CAPTURE_DURATION_EXCEEDED` 进入受限清理；当前 capture PCM 被丢弃，不发起新 STT、Agent、Tool、Task、history、receipt 或 cancel，晚到 frame 为零效果。此前已接受的唯一 playout receipt 保持不变。达到恰好 1500 帧时仍允许用户执行 `Stop and recognize`，并提交完整 30 秒 WAV。
- UI 与并发：Formal P1 UI 明示“最多保留 30 秒已采集音频；连续采集时约 30 秒；重叠播报期间采到的音频计入上限”，要求在上限内说话并点击 `Stop and recognize`；超限后明确说明未产生新 Speech/Agent submission，失败 owner 必须刷新/关闭后重建。Start 使用单次共享 Promise；旧 owner 精确 close 未完成时，两次连续 Start 不得分配两个麦克风或 media authority，close 持续失败则终态按钮禁用并保留原 authority 供有界清理重试。
- ASR 质量边界：本次 `联调` 被识别为同音词 `连调` 是当前模型/音频条件下的识别质量问题，不是路由、commit 或 TTS 失败。W2 通过“识别后可编辑、确认后提交”保持文本权威；受保护 token 继续使用既有关键 token Gate。不得把一次同音词误识别升级为自动提交或生产级 ASR 准确率证明。
- 重新评估条件：30 秒不足以覆盖已接受的 Demo 交互；实际运行在 1500 帧之前触发相同原因；清理产生额外 Speech/Agent/Tool/Task/history/receipt/cancel；用户在精确边界 Stop 时被误拒；引入正式 VAD/EOT/streaming STT；或产品选择持续免按键监听模式。

## D-069 W2 P3 采用显式有界 task.retry 与 attempt-segment 权威

- 日期：2026-08-08
- 状态：Accepted P3alpha design and W2 evidence contract（用户明确接受同一任务的有界显式重试；本决定只冻结待实现/待验收合同，不表示源码、迁移、D-053 review、真实重启 Gate 或 Replacement Ledger 已完成）
- 背景：D-045 只允许 `task.create/task.cancel`，并正确禁止重启时自动创建新 attempt；但 W2 严格 Gate 要求同一 `task_id` 同时给出成功取消、完成真实 D0 mutation 和跨进程重启 reconciliation。单个 attempt 无法确定地同时提供这些互斥事实，把 Gate 放宽为拼接不同 task 又会破坏 identity truth，因此需要一个窄幅、显式、可重复且有总量上限的 same-task transition。
- 命令、预算与资格：新增协商后的正式 mutation `task.retry`。初始 attempt A 的 `attempt_number=1`；每次成功应用重试只创建一个新的 opaque `attempt_id` 并递增 attempt number，单个 task 最多 `3` 个 total attempts、最多 `2` 次 applied retries。只有当前 task 和当前 attempt 都为 `terminal`，且精确 outcome 为 `cancelled` 或 `completed` 时才有资格；`failed/interrupted/unknown`、非终态、非当前 predecessor 或已达上限全部 fail closed。计数、当前 attempt 和 outcome 只来自 Store 权威，客户端不能自报或跳号。
- 精确授权、确认与前置条件：`task.retry` 是结构化、destructive、显式用户确认的 mutation。可信入口必须提供与 `principal + authenticated ScopeRef + operation/capability=task.retry + command_id + target_task_id` 精确绑定且未过期的 `AuthorizationContext`；正式 P3 confirmation 必须再绑定 exact predecessor `attempt_id/outcome`、expected next `attempt_number`、原 task intent/executor/model/capability/side-effect facts，以及重新解析后的 clean `ResolvedTaskContext`。其稳定项目 identity `{source, stable_id, uri, scope}` 必须与原 task 相同，外部 checkpoint 后允许使用新的 clean `revision`；permission/expiry/redaction 等其余安全事实必须重新验证、进入 exact fingerprint 且不得被静默放宽。执行前还必须证明 predecessor 的 dispatch/cancel outbox 已 settled、reconciliation 不为 required/in-progress/pending、Executor worker/lease/retained cleanup 已 quiescent，并再次通过现有 exact-root、versioned-context、permission、expiry、redaction 与 clean-worktree guard。上述事实均为 server-derived precondition，不能由 payload 声明为真。
- 原子状态与事件：一次 applied retry 的 durable 原子单元必须包含一条 command-ledger result、更新后的 task current-attempt/spec/context pointer、一个新 attempt、一条 `task.retry_accepted`、一个 attempt-dispatch outbox 和返回结果；task/current attempt 进入 `accepted`、outcome 清空，旧 cancel/fence/reconciliation 状态不得泄漏到新 epoch。`task.retry_accepted` 由 `task_core` 产生，event 自身的 `task_id/attempt_id` 指向新 epoch，`state=accepted`、`outcome=null`，details 必须精确包含 `command_id`、`retry_of_attempt_id`、`previous_outcome` 和 `attempt_number`。初始 A 仍且只由 genesis `task.accepted` 建立；普通 lifecycle event 不得让 terminal attempt 回到 accepted。task aggregate 的 terminal→accepted 只可由通过上述原子校验的 `task.retry_accepted` 跨越，terminal 不可逆性按 attempt epoch 保持。
- 查询、订阅与兼容：`task.events` 是唯一返回同一 task 完整 A/B/C 有序历史的 API。正式 TaskEvent subscription/replay 只交付 current-attempt segment：A 从 genesis `task.accepted` 开始，B/C 从各自最新的 `task.retry_accepted` 原子边界开始；不得把旧 terminal prefix 当成当前 attempt lifecycle，也不得由消费者自选边界。识别新事件的消费者必须验证 exact lineage、attempt number、producer 和状态；尚未协商 `task.retry_accepted` 的旧消费者遇到该未知事件必须 fail closed，不能跳过、降格或伪装成普通 `task.accepted`。
- 幂等、并发与稳定错误：同一 authenticated scope、同一 `command_id` 和同一 canonical fingerprint 的 applied command 必须优先从 ledger 精确重放原结果，即使 task 已继续推进也只允许新的 transport `request_id`，并产生 `+0` attempt/event/outbox/Executor/Git effect；同 command ID 改变任一绑定事实返回 `CONFLICT/IDEMPOTENCY_CONFLICT`。对同一 predecessor 并发提交不同 command ID 时，只允许一个 CAS winner 创建下一 attempt；其余返回 `STALE/TASK_RETRY_PRECONDITION_STALE`，绝不跳过 attempt number。资格和预算分别稳定返回 `CONFLICT/TASK_RETRY_REQUIRES_TERMINAL`、`CONFLICT/TASK_RETRY_OUTCOME_NOT_ELIGIBLE`、`CONFLICT/TASK_RETRY_LIMIT_EXCEEDED`；未 settle 的 authority 分别返回 `UNAVAILABLE/TASK_RETRY_OUTBOX_PENDING`、`UNAVAILABLE/TASK_RETRY_RECONCILIATION_PENDING`、`UNAVAILABLE/TASK_RETRY_EXECUTOR_CLEANUP_PENDING`；dirty checkout 继续使用现有 `PERMISSION_DENIED/TASK_CONTEXT_WORKTREE_DIRTY`。认证、能力、context 和 confirmation 失败继续使用既有稳定原因，不折叠成 retry generic error。
- 零副作用 oracle：任何 authorization/confirmation/eligibility/limit/precondition/context/quiescence/idempotency rejection 都必须保持 `+0` task/spec/current-attempt mutation、`+0` new attempt/event/outbox/command row、`+0` outbox claim/state change、`+0` Executor dispatch/cancel、`+0` Agent/Tool/worker/lease/worktree/Git mutation 和 `+0` progress/D0/Gate evidence。已成功应用命令的 exact replay 只读原 ledger result。confirmation 的签发/消费继续服从既有独立 ledger，但必须在可能时先做确定性拒绝，并允许已 applied command 通过 command ledger 精确重放；它不能成为重复 attempt 的入口。
- Git/checkpoint 边界：`task.retry` 自身不执行 `commit/reset/stash/clean/checkout`，不改变 HEAD，不吞并工作区差异，也不放宽 `TASK_CONTEXT_WORKTREE_DIRTY`。A cancelled 后可在原 clean revision 创建 B；B 完成 D0 mutation 后，由外部 W2 fixture harness 单独验证目标 patch、建立并记录一个新的 clean Git checkpoint，再重新解析同一稳定项目 identity 的新 revision，签发 exact confirmation/precondition 后才能创建 C。checkpoint 是可审计 Gate 前置步骤，不是 retry 的隐藏副作用或生产自动恢复能力。
- W2 A/B/C 与重启 Gate：固定拓扑为 A=`created/queried/status/events/list → successfully cancelled`；retry #1 创建 B，B 在同一 `task_id` 上完成真实 D0 mutation；外部 fixture checkpoint 后 retry #2 创建 C，predecessor 必须已原子提交 C 为非终态并正常关闭，successor 只能查询和 reconciliation exact C，重启本身不得创建 attempt D。Gate 必须按同一 `task_id` 和三个精确且不同的 `attempt_id`/`attempt_number=1/2/3` 联结 A 的 Core/cancel、B 的 completed D0 fact 与 C 的 predecessor/successor restart fact，并在 C 内继续按 exact `task_id+attempt_id` 校验；不得拼接不同 task、接受额外 attempt、从 summary 推导 lineage，或把一次进程内重连冒充 restart。
- 与 D-045/ACG 的关系：本决定只对显式协商的 `task.retry` 窄幅取代 D-045/ACG 的 mutation whitelist、task aggregate terminal→accepted 和 current-segment subscription 边界；D-045 的 command/event/attempt/outbox 权威、at-least-once dispatch、精确 cancel/reconciliation、安全授权及“restart 不自动创建 attempt”全部保留。它不新增自动 retry、startup recovery、arbitrary recover/resume、失败副作用回滚、跨工具 exactly-once 或一般生产重试策略；未协商的新命令/事件继续 fail closed。
- 实施与验收：先完成 D95 的 attempt-Agent/checkout retained-ownership 修复，再以一个 Tier-3 coherent batch 同步实现 Store/Core/reducer/subscription、policy/auth/confirmation/composition/Gateway 和 Web TypeScript consumer/UI，避免生产者先发出旧消费者无法理解的新事件；随后覆盖 applied/exact replay/conflict、全部资格/前置条件错误、并发 CAS、migration/restart/current-segment subscription 和零副作用组合测试，完成 D-053 三轮 review。最后才由 W2 fixture harness 执行 A→B→clean checkpoint→C→successor 的诊断和 fresh immutable Gate；在这些步骤实际关闭前，本决定不产生实现或 Gate credit。
- 重新评估条件：三次总量不足以完成已接受的 W2 拓扑；真实 Executor 无法证明 worker/lease/outbox/reconciliation quiescence；同一稳定项目无法安全更新到 checkpoint revision；Store 不能原子创建 retry epoch；current-segment subscription 无法保持旧消费者 fail closed；restart 需要继续原 attempt 之外的新正式恢复语义；或产品要把 bounded manual retry 扩成自动/通用 retry policy。

## D-070 W2 D-069 采用 GPT/Sol 与 Claude Code + Opus 5 跨模型双线执行和互审

- 日期：2026-08-09
- 状态：Accepted bounded execution/review decision（用户明确批准当前 W2 双线方案、本地 branch/worktree/commit/rebase/integration 和互为跨模型第三轮；不授权任何远端更新）
- 范围：本决定只覆盖当前 W2 的 D-069 Core/Store retry 批次和 product-reachability 批次。它不把模型分工扩成所有未来 W2/Alpha/完整 P3 或生产工作的永久规则，也不改变 D-069 产品语义、D-046 风险等级、D-053 三轮要求或 Integrated Demo Gate。
- 分工：GPT/Sol 继续担任协议与产品语义权威、Integration Owner、冲突裁决者、最终 D-053 记录者以及 Gate/release owner。Core/Store 由 GPT/Sol 实现、修复并完成 self-review 与 cold complete-diff review，第三轮由 Claude Code + Opus 5 对冻结 exact SHA 作分离只读审查；product-reachability 由 Opus 在独立 worktree 实现、测试并完成 self-review 与 cold complete-diff review，第三轮由 GPT/Sol 对冻结完整 diff 审查。任一方不得以同模型的分离 agent 替代另一方的第三轮；指定模型不可用时对应批次保持 `PARTIAL`，等待用户重新决定。
- 并行和集成：Opus 可以在不可变 Core preview 上进行不产生正式结论的预读，并在 Core 公共 seam 足够稳定后基于未验收 Core candidate 实现产品批；正式 Core 第三轮只针对 rebase、测试并冻结后的 exact candidate SHA，审查期间 Core 不得变化。产品分支在接受前必须 rebase 到最终 D-053 PASS 的 Core SHA，并重新运行测试与 cold review。开工可以并行，集成顺序固定为 Core 后 product-reachability；Main 是唯一集成 worktree writer 和 Git integration owner。
- 所有权和禁止项：Claude/Opus、Core reviewer 和其他 worker 不得编辑集成 worktree、集成自己的返回、更新远端、处理或持久化凭据、授予 Gate/Replacement Ledger credit，或越过任务包修改共享 Core/协议语义。`project_code_executor.py` 与 `p3_authenticated_composition.py` 只允许新增 bounded retry 路径，不得重构或放宽 `7be485e8c` 已闭合的 exact-root、attempt lease、cross-process lock、retained cleanup、cleanup/release、pending truth 或 checkout 删除边界；确有需要时必须停止并提交接口缺口、原因和零副作用 oracle，由 GPT/Sol 裁决。
- Review 和 finding：两个实现批都保留实现者 self-review、实现者 cold complete-diff review和跨模型第三轮。预读不属于第三轮且不产生 PASS/NOT PASS。第三轮 findings 必须绑定 exact SHA，给出稳定 symbol/path、违反的不变量、确定性复现和影响；影响当前请求、兼容性或适用 D-032/D-069 维度的 actionable finding 必须修复。只有明确 scope-out 且不影响本批验收的事项可以记录后续 owner，而不能用 P2 标签自动延后。
- Git/环境边界：D-063 的本地自主 Git 例外继续适用，任何 remote ref 更新仍需用户对精确 remote/ref/commit/方式单独批准，Task worker 永不 push。本决定不要求 MCP；Codex PATH、`CODEX_HOME`、ripgrep、Claude 本机配置和 review scratchpad 是机器私有条件，不进入 Live Voice Git 状态或证据。scratchpad 只能作为恢复素材，确认后的 finding 才可按文档规则规范化进入 D95。
- 重新评估条件：跨模型第三轮不可用；Core seam 在产品实现期间持续变化；两个 lane 出现文件/语义重叠；Opus 无法在不改变 `7be485e8c` 安全边界的情况下实现 retry readiness；协调或 rebase 成本持续高于并行收益；用户改变模型、集成、Git 或远端授权；或当前两个 D-069 批次关闭。

## D-071 Live Voice 里程碑以自动验证加一次完整人工产品验收闭环

- 日期：2026-08-11
- 状态：Accepted product-acceptance policy（用户明确撤销 W2 及后续 Live Voice 里程碑的签名证据 Gate/Replacement Ledger 完成门槛）
- 范围：本决定适用于当前 W2 Integrated Demo、后续 Integrated Web Alpha 及之后的 Live Voice 产品里程碑，直到用户为明确的审计、合规或正式发布场景重新要求更高等级认证。它只取代 D-046、D-060、D-062 和相关执行包中的签名取证、固定槽位、重复展示、计分与 Gate 阻塞规则；产品范围、真实 Agent/Tool/Task 要求、架构权威、安全边界、D-046 风险分级、D-074 当前高风险 review（D-053 历史 cadence 保留）和负向零副作用要求继续有效。
- 完成标准：先在被识别的测试源码上完成适用的自动化验证，包括正向旅程、关键负向、flag-off、受影响回归、构建和静态检查；再由用户在一个完整产品会话中人工验收所有适用的用户可见能力。人工步骤可以复用同一源码和环境中已经通过且未被后续语义修改影响的结果，不得仅为仪式重复。修复若影响某个可见步骤，只重跑受影响自动检查和人工步骤。
- 退役内容：W2/Alpha 完成不再要求 root/leaf key、trust policy、artifact signature、evidence owner、七个 runtime artifact、31 个 non-runtime artifact、38-slot manifest、三次连续 showcase、`w2_gate_cli evaluate` 或 Replacement Ledger 分数。相关代码、脚本、旧 candidate 和历史文档保留为诊断/取证历史，不再进入关键路径，不得因其失败、缺失或 `0/100` 阻止产品验收或后续里程碑。
- 记录：STATUS 记录自动验证、人工验收的通过/未通过项目、测试源码和真实限制；必要时新增简短的脱敏验收记录。不得把自动测试称为人工体验，也不得把未实际观察的麦克风、完整朗读、打断、非阻塞、Task UI、刷新/重连或降级行为写成通过。
- W2 当前影响：P1/P2、真实 Terminal Tool、完整 TTS 和后继 capture 的人工结果继续有效；剩余人工范围是打断/纠正、P2/P3 非阻塞、P3 create/cancel/retry A→B→C，以及刷新/重连/重启和可见降级。完成这些适用步骤并确认无关键产品缺陷后，W2 可标记 `PRODUCT-ACCEPTED`，无需恢复签名 Gate。
- 原因：签名取证框架曾发现若干真实身份、重放、P3 UI、配置和音频问题，但后期成本主要消耗在证据编排、签名、页面计数、等待窗口和 artifact 完整性，已明显偏离 90% Demo 的产品价值。自动化验证与一次完整人工产品验收足以满足当前交付目标，同时保留真实功能、安全和回归保证。
- 重新评估条件：外部发布、审计、监管、客户合同或跨组织交付明确要求不可抵赖且可复现的签名证据；自动与人工结果发生无法解释的冲突；或用户明确重新启用某个有界认证 Gate。

## D-072 删除已退役的 W2 签名证据 Gate 实现

- 日期：2026-08-11
- 状态：Accepted implementation-removal decision（用户要求在 W2 人工验收继续按 D-071 推进的同时，深度分析并至少分三轮删除 Gate 代码；最终只保留一个提交）
- 删除范围：删除 W2 Gate evaluator/scoring/CLI、root/leaf key 与 trust-policy/signature/manifest/Replacement Ledger 处理、自动报告与 runtime evidence exporter/owner、38-slot rehearsal/choreography/controller/fault runner，以及只为该 Gate 服务的 P1/P2/P3 request-id 故障注入和专属测试。
- 保留范围：保留真实 P1/P2/P3 产品路由、Agent/Tool/Task 权威、P3 confirmation、replay/idempotency、fail-closed/零副作用、Task Core/Store/Executor/outbox/lease、普通产品观测、D-046 风险分级与 D-074 当前 review 节奏（D-053 历史记录保留）、Architecture Contract Gate、Product Composition Gate 0 和历史冻结记录。确定性 WAV Speech preflight 与真实 D-069 A→B→C/restart 诊断不签名、不计分，作为产品验证工具保留。
- 执行约束：删除分为纯 evaluator/编排、runtime evidence/故障 seam、残余入口/配置/文档三轮；每轮都必须完成依赖分析、实际删除和针对保留产品路径的无副作用确认。中间允许本地临时 commit，但最终历史只允许一个本任务 commit；任何 remote ref 更新仍需单独精确授权。
- 完成影响：当前 checkout 不再提供或接受旧签名 Gate 命令和环境变量，历史 D90–D102 只解释过去事实。W2 状态、人工验收范围和后续 Alpha 顺序不因删除而自动改变，仍由 D-071、验收合同与 STATUS 决定。
- 重新评估条件：用户为新的审计/合规/客户交付明确批准一个重新设计且有界的认证需求。不得直接复活被删除的 W2 实现；新认证必须重新定义威胁模型、所有者、成本和产品交付关系。

## D-073 W3 换基线必须保留 develop 的删除与替代意图

- 日期：2026-08-12
- 状态：Accepted migration-integration decision（用户要求审核既有 W3 migration，判断 develop 删除对象是彻底删除还是迁移，并在不重做迁移的前提下完成必要调整）
- 范围：`hx/0812_live_voice_w3` 的 develop 换基线收口；不改变 W2 产品验收，不自动扩大 Alpha 范围，也不统一现有 Task 子系统。
- 规则：换基线不得仅因特性旧代码仍引用某个符号就将 develop 删除内容补回。先用删除提交、当前调用面和替代 API 判定意图：有替代 API 时迁移调用方；明确退役时删除特性依赖；纯改名时采用新名称。只有特性仍有独立且被测试的产品需求、并且当前树没有等价能力时，才可设计一个显式兼容 Adapter，而不是静默复活旧实现。
- 本次适用：删除恢复的 `prompt_attachment_loader.py`、其测试和 `get_prompt_attachment_dir`；删除恢复的 `resolve_project_coding_memory_workspace_path` 并采用 `resolve_project_coding_memory_dir`；保持 `ReqMethod.SKILLS_GRAPH_*`；使用 agent-core 公共 `get_agent_history_root()`；继续服从 develop 已删除“自动改写项目 `.gitignore`”的决定；公共 Agent 启动继续遵守 develop 的失败传播契约。`ProjectCodeExecutorAdapter` 作为有测试覆盖的兼容 Adapter 暂时保留，但正式 P3 组合继续使用 `DirectProjectCodeExecutorAdapter`。
- 依赖规则：浮动的 agent-core develop 依赖必须由 `uv.lock` 的解析 commit 固定迁移验证边界；源码需适配该 commit 的公共 rail/history API，不得依赖已移除的私有属性。
- 重新评估条件：develop 重新引入官方文件热加载契约；Live Voice 出现经产品范围确认且当前 PromptAttachmentManager 无法满足的文件附件需求；agent-core 再次变更公共 API；或兼容 Adapter 的所有调用方和测试被一个独立移除批次明确关闭。


## D-074 本地提交与 review 改为按模块、风险和阶段分层

- 日期：2026-08-12
- 状态：Accepted repository execution/review policy（用户明确允许在已授权任务内自行创建本地 commit，要求避免为了 commit 而产生过小、过频的提交；所有 push 仍须单独审批，并要求评估旧 Gate、diff 和 review 流程是否阻碍交付）
- 本地 Git 决定：实现、修复、文档或集成任务已经获得范围授权时，Main 可在完成适用检查后自行 stage/commit，无需再申请逐次 commit 批准。commit 应对应一个可审阅、可解释的模块、缺陷批次、集成批次或文档决策；不得为了展示进度制造微小 checkpoint，不得把已知破损或语义未闭合状态当作普通完成提交。handoff 必须报告 commit、状态、验证和明确排除项。amend/squash/rebase/cherry-pick/merge 等现有历史组合或改写，仅在用户请求本身、accepted execution packet 或 D-063 最少介入授权明确涵盖时自主执行。
- 远端决定：任何 normal/force/force-with-lease push，以及远端 branch/tag/ref 创建、更新或删除，仍须在操作前取得对 exact remote、ref、commits 和 update mode 的单独明确批准。之前的 commit、push 或“继续”不自动授权下一次远端更新；worker 不得 push。
- 开发中节奏：模块推进期间只要求实现者自查实际受影响 diff、运行 focused tests，并在触及新风险时补充相应 scenario。中间小修改或每个 commit 不触发独立 `/review`，也不要求对未变化的全项目历史反复做 complete-diff review。
- 模块收口：一个 coherent module 或相关 package group 收口时，对从该模块起点到当前结果的完整 scoped diff 做冷审，核对原始请求、仓库规则、现有 API/行为和实际测试。Tier 2/3 的 changed boundary 在此时运行一次独立 `/review` 或等价独立入口；相关包改变同一契约时可共享一次收口 review。若独立入口不可用，记录实际替代方式和限制，不得声称 `/review` 已运行。
- 阶段收口：Integrated Web Alpha 等阶段 candidate 对阶段基线到 tested source 的累计 diff、跨模块集成 seam、配置/flag-off/回归和适用真实路径进行大范围 review 与自动验证，再按 D-071 完成一次完整人工产品验收。已在模块收口审过且后续未变化的内部细节无需机械重复逐行 review，但其集成关系必须进入阶段审查。
- 修复反馈：任何 review finding 先修复并重跑受影响测试；只有修复实质改变了某一模块、共享契约或阶段集成语义时，才重复对应层级的最终 review，不因无关文件或格式调整重跑整个未受影响阶段。
- 不变安全底线：D-032 的 contract-first tests、正例成功、负例拒绝/fail closed、Agent/Tool/Task/audio/history/store/other-scope 禁止副作用为 0，以及真实 Provider/设备/Executor/用户感知不能由 fake 代替的原则继续有效。Tier 3 的 shared protocol、authority、security、durability 与 release 仍需完整适用矩阵；本决定只调整 review 的聚合层级和时点，不降低产品或安全标准。
- 取代关系：本决定取代 D-053“每个 coherent implementation batch 固定三轮”的节奏，以及 D-046 中“每个 Tier 2 都固定 pre/post review”和“默认 commit 逐次精确审批”的操作性表述。D-063 不再是普通本地 commit 的必要前提，但继续控制更广的最少介入、历史组合/改写和用户介入边界。D-060/D-062 的 ownership、single-writer 与 Main-only integration 只在存在 active parallel packet 时启用；已完成 W2 的固定 lane 和 D-070 模型分工是历史，不是当前 Alpha 默认任务分配。D-061 的完整 reviewed integration batch 后一次累计 smoke、D-071 的自动加一次人工验收、D-072 的 Gate 删除和 D-073 的迁移原则继续有效。
- 重新评估条件：模块级 review 持续遗漏只在阶段 review 才发现的高风险问题；独立 review 在 Tier 2/3 收口长期无法运行且替代方式无效；coherent commit 长期混入无关修改或变得不可审阅；公共发布、监管、客户交付或安全审计需要更强的可追溯认证；或用户更改 local/remote Git 授权。

## D-075 用交付阶段、能力轨、工作包和关键节点四层模型管理后续 Alpha

- 日期：2026-08-12
- 状态：Accepted project-structure decision（用户要求整理项目阶段与模块、明确完成/未完成和后续关键节点，并同步全部当前文档以消除后续执行歧义）
- 术语边界：`P1/P2/P3alpha/Shared/X` 是长期能力轨，AIO/SR/SS、RM/CR/II/AB、TC/ED/VB 是模块，`*-A/*-B/*-C` 是模块内工作包；它们都不是当前项目的顺序阶段。`W1/W2/W3/W4` 只保留为历史交付窗口和文档索引，不再表示当前日历周、当前阶段或默认任务队列。完整方案中把 P1/P2/P3 称为 Phase 的表述保留为历史架构分组，当前执行统一解释为 capability track。
- 顺序阶段：`S0 V0 Proof`、`S1 Shared Foundations`、`S2 D-031 Bounded Compatibility`、`S3 W2 Integrated Demo`、`S4 Develop Rebaseline`、`S5 Alpha Baseline & Gap Freeze`、`S6 Alpha Module Closure`、`S7 Alpha Integrated Candidate`、`S8 Alpha Product Acceptance`、`S9 Later/Beta/Production`。阶段状态只由 `STATUS.md` 维护；截至本决定，S0/S1/S2/S4 为 `CLOSED`，S3 为 `PRODUCT-ACCEPTED`，S5 为当前进行阶段，S6–S8 尚未关闭，S9 不属于当前 Alpha 范围。
- Alpha 关键节点：`A0 Baseline Freeze` 固定测试源码、Alpha 范围/非目标、逐条 acceptance→module gap、risk tier、机器私有依赖和需要用户决定的产品输入；`A1 Module Closures` 分别关闭 P1、P2、P3alpha 与 Shared/X 的 Alpha gap，并完成 D-074 模块级 review；`A2 Integrated Candidate` 在干净且被识别的源码上完成累计 diff/integration review、适用自动验证、构建/静态检查和关键真实路径；`A3 Product Acceptance` 按 Alpha 专用 showcase 完成一次完整人工旅程后才能标记 `PASS — INTEGRATED WEB ALPHA`。
- 完成语义：历史 W2 能力已经通过并不等于对应模块满足 Alpha；当前实现存在也不等于模块 `CLOSED`。模块表必须同时写“已证明到哪个 milestone”和“Alpha 尚缺什么”。没有完成 Alpha 验收合同的模块统一保持 `PARTIAL`，但这不回退 W2 `PRODUCT-ACCEPTED` 或 W3 rebaseline `CLOSED`。
- 执行顺序：S5/A0 关闭前不建立大规模实现队列；A0 后只把依赖已满足、所有权不重叠的 module batch 并行化。A1 的模块 closure 可以并行，A2 必须在全部必需模块 closure 返回后由 Main 统一集成，A3 必须针对 A2 的 exact tested source。后续任务必须声明所属 stage、target node、track/module、risk tier、包含项和排除项，避免把历史 packet 当作当前授权。
- 验收入口：W2 保留 `INTEGRATED_DEMO_ACCEPTANCE.md + INTEGRATED_SHOWCASE.md`；Alpha 使用 `ALPHA_ACCEPTANCE.md + ALPHA_SHOWCASE.md`。两者不得共用一个含糊的人工脚本，也不得用 W2 观察自动换取 Alpha PASS。ACG 和 Product Composition Gate 0 的 `Gate` 继续表示合同/组合 checkpoint；D-071/D-072 退役的是签名证据 Gate，不能把二者混为一谈。
- 文档同步：README 只路由，STATUS 只保存当前阶段/模块/node，roadmap 定义稳定顺序和退出条件，acceptance 定义 pass/fail，showcase 定义人工操作，runbook 定义环境/启动步骤，D109 保存本次同步审计。冻结的完整方案、W1/W2 execution packets、D90–D108 和 evidence 不倒写；其中旧术语只通过本决定和当前路由解释。
- 重新评估条件：Alpha 产品范围改变；某个 module gap 被证明需要新增共享协议或第二 authority；A0 无法在不做产品选择的情况下冻结；模块 closure 长期无法组合成一个 candidate；或用户重新接受日历承诺、完整 P3/生产范围或审计级认证。

## D-076 S5–S8 使用一份 verify-first 的当前执行合同

- 日期：2026-08-12
- 状态：Accepted execution-planning decision（用户确认 S5–S8 的具体任务应当在 Markdown 中落实，避免只有阶段出口而没有可执行、可判定完成的工作）
- 当前合同：`roadmap/ALPHA_S5_S8_EXECUTION_PLAN_2026-08-12.md` 是 S5/A0 到 S8/A3 的 active task contract。它冻结任务 ID、依赖、风险、模块边界、必须验证的行为、退出条件和非目标；STATUS 仍是唯一 mutable progress/branch/gap/next-action source，acceptance 仍是 pass/fail authority，showcase 仍是 A3 人工操作脚本。
- Verify-first：当前源码已经包含大量正式 P1/P2/P3alpha/Shared-X 实现和测试。A1 不按历史 W3/W4 行重新开发；先检查真实源码和测试，将 requirement 分类为 satisfied/implementation/verification/environment/deviation/Later，只实现被源码审计或真实验证证明的缺口。旧 Wave packet、worker、owner、日期和 replacement queue 不自动恢复为当前授权。
- 冻结的主要缺口方向：AIO、RM、CR/AB、TC/ED 的多数工作先做 Alpha 级 real-path/fault/performance closure；当前明确需要实施或决定的边界包括选择正式 streaming Speech 路径或接受偏差、把 critical-token safety 接入受保护的 committed product path、补齐 committed natural-language `task.status` 正式查询路径、建立可复现 p50/p95/sample/failure benchmark 与 whole-stack raw-audio zero-persistence 回归，以及形成一个 slow conversational round + detached Task 的 joint X-E2E 场景。后续源码检查若推翻任一判断，以源码为事实并更新 STATUS/新决定，不静默改写本决定。
- 执行顺序：S5-01 source audit、S5-02 product/environment freeze、S5-03 batch/ownership freeze 完成后进入 A1；A1 的非重叠模块组可并行，X-E2E 消费所有必需 closure；A2 由 Main 形成一个 exact candidate 并完成累计自动验证和 review；A3 只在该 candidate 上运行一次完整 Alpha 人工旅程。自动音频语料或程序化声音检查可以支持 A2/A3，但不能替代用户对物理权限、设备、可听质量和产品可用性的人工观察。
- 用户介入边界：S5-02 的 Provider/streaming-or-deviation、浏览器/设备/网络/secure deployment、真实 Executor/可丢弃项目和任何重大 acceptance 偏差由用户或已有明确决定提供；其余只读审计、测试准备和不改变产品选择的工作继续推进。凭据、billing、公开部署、破坏性真实目标和远端 ref 更新不由本决定授权。
- 重新评估条件：Alpha acceptance 变更；已选 Speech/Media/Executor 无法满足声明能力；源码审计发现新的 shared authority/protocol gap；任务边界长期产生所有权冲突；A2 无法组合为一个 candidate；或用户收窄/扩展 Alpha 产品范围。

## D-077 Live Voice 文档按当前任务段渐进读取

- 日期：2026-08-12
- 状态：Accepted documentation-routing decision（用户要求文档瘦身，避免新 Session 读取与当前任务无关的完整计划、验收、历史和架构材料）
- 最小入口：每个 Live Voice task 只固定读取根 `AGENTS.md`、轻量 `live-voice/README.md` 和精简 `live-voice/STATUS.md`；文档结构/更新任务再读取 `DOCUMENTATION_RULES.md`。链接只表示 route，不表示整份读取。
- 当前执行：S5–S8 普通工作只读 execution plan §1–2 和 STATUS 命名的 task section、受影响源码/tests 与该任务消费的 acceptance bullets；A2 才读完整 Alpha acceptance，A3/runtime 才读 showcase 和相关 runbook。完整 plan 只用于 task-graph 审计/调整；ACG 只读实际涉及的 sections，完整方案只在长期边界本身变化或仍有歧义时读取。
- 历史隔离：模块旧 review、W1/W2/Wave packet、D90–D109、evidence、archive 和 fresh-clone 说明移至条件式 `REFERENCE_INDEX.md`；普通 bootstrap 禁止读取该索引。STATUS 不再保存历史证据目录，README 不再保存完整文档角色表。
- 不改变内容：本决定只缩小默认读取面，不改变 D-075 阶段、D-076 任务、Alpha acceptance、D-074 review、D-032 安全不变量或任何已冻结历史事实。
- 重新评估条件：新 Session 经常无法仅凭最小入口定位当前任务；sectional route 导致必需 contract 被遗漏；条件索引无法定位回归来源；或 README/STATUS 再次持续膨胀为完整 handoff/catalog。

## D-078 Alpha Speech、Provider、Executor 与私有环境采用完整 Streaming 隔离基线

- 日期：2026-08-12
- 状态：Accepted S5-02 product/environment decision（用户明确选择完整 Streaming，并接受 Gateway、JiuwenSwarm Agent、Direct Executor、disposable project、可用 OpenAI Speech API access 和 W2 Batch fallback 的推荐组合；独立 OpenAI Project 是费用/权限隔离建议，不是代码硬依赖；本决定冻结目标和隔离边界，不表示当前 Streaming Adapter、Provider 探针、凭据或候选环境已经完成）
- Speech 主路径：Alpha 使用 OpenAI 官方 API，但所有 Provider 连接和凭据只由 Gateway 持有。STT 采用 `Browser AudioWorklet → Gateway → OpenAI Realtime transcription session` 的服务端 WebSocket 路径，保留 partial/final、顺序、来源和精确 cancel；TTS 采用 `JiuwenSwarm Agent response text/delta → Gateway → OpenAI streaming speech → browser playout`，音频块必须绑定 response/generation 和精确 text span。浏览器不得接触 API key。当前代码只有正式 Batch Adapter、Browser fallback 和 Streaming seam，因此该选择给 S6-02 指定实现目标，不提前获得 `streaming=true` 或 Alpha closure credit。
- Agent 边界：committed final transcript 仍提交给当前已工作的 JiuwenSwarm Agent Provider/model 和真实 tools；Speech 与 Agent 是两套独立能力。本阶段不替换 Agent Provider，也不得让 OpenAI speech-to-speech 模型直接生成最终回答、绕过 JiuwenSwarm Agent/Tool authority。候选记录只保存去敏后的 Agent Provider/model label。
- Provider 与 fallback：Alpha Streaming 的初始探针/候选默认值为 STT `gpt-4o-mini-transcribe-2025-12-15`、TTS `gpt-4o-mini-tts-2025-12-15` 和 voice `marin`；它们仍必须在候选环境中经过官方 capability、区域/隐私、价格与最短真实探针后取得真实 credit。探针拒绝 snapshot/voice 或协议时停止并报告，再显式更新选择；不得在同一验收 attempt 中静默换模型、voice 或 route。保留 D-064 已验证的 OpenAI-compatible Batch 路径作为显式 fallback，Browser Speech 只能作为更低级的显式 fallback；两者均不得冒充 Streaming。
- 凭据与费用：运行硬前提是具备可用额度和所需 Realtime transcription/Audio Speech 权限的 OpenAI API access，以及只注入 Gateway 进程私有环境变量 `LIVE_VOICE_SPEECH_API_KEY` 的受限 key；key 不进入浏览器、Git、日志、证据或聊天。独立 OpenAI Project 建议用于隔离费用、权限和吊销范围，但已有 Project 中满足同等权限/费用边界的 restricted key 也可使用。建议设置约 `$5–10` 月度预算/告警，但该阈值只用于费用监测，不视为硬停机；自动验证另设有界 session、request、音频分钟和估算费用硬上限。创建 Project/key、设置 billing/预算或充值是用户控制的外部账户操作，本决定不授权自动执行。
- 浏览器、设备、网络与部署：Alpha 只声明一套在 candidate freeze 时记录精确版本的 desktop Google Chrome Stable + Windows 基线，不承诺广泛兼容；物理验收使用实际连接的耳机或输出设备加麦克风，不限制品牌、型号或 USB/内置形态。候选记录 Chrome/OS 和本次实际输入/输出标签只为复现，不形成设备 allowlist；device change/loss 可使用当时可用的第二 endpoint 或受控断开。网络采用一个稳定主 profile 和一个受控 degraded/fault profile。正式真实路径采用私有 same-origin HTTPS/WSS：`Chrome → reverse proxy → Gateway → AgentServer`；localhost 只用于开发 smoke。候选环境需验证浏览器 permission/profile、CSP/CORS/connect routing、设备标签和实际私有 origin，Git 不保存机器私有值。
- Executor 与隔离：正式 P3alpha 使用 `DirectProjectCodeExecutorAdapter`，不经过旧 `schedule.*`。所有 create/status/cancel/restart 与 mutation 验证只针对新建、可丢弃、无 remote、无 push 凭据、无用户数据的本地 Git fixture repo，并使用独立 `JIUWENSWARM_DATA_DIR`、Store/database 和有界 deterministic workload；不得把 JiuwenSwarm 源码仓库、当前工作区或用户项目作为测试目标。清理只作用于本次明确创建并核对过的隔离路径。
- 仍待实例化：S5-02 的产品选择和初始 model/voice 默认值已完成；可用 OpenAI Speech API access/受限 key、真实 Provider 探针、Chrome/Windows/实际设备/network 标签、私有 origin/证书和隔离目录仍需在候选机器上准备、记录并实测。完成这些环境事实和探针前，S5/A0 仍为 `IN PROGRESS`，任何模块不得声称真实 Provider、完整 Streaming、secure deployment 或 real Executor 已验收。
- 非目标与授权边界：本决定不扩大到公开部署、生产鉴权、跨浏览器/OS、真实用户项目 mutation、完整 P3/D1/D2，也不授权外部账户/billing/credential 变更或任何 remote ref 更新。
- 重新评估条件：OpenAI 官方 API 无法提供所需的 STT/TTS streaming、provenance 或 cancel contract；区域、隐私、成本或延迟不满足 Alpha；声明的 Chrome/Windows/设备/私有 HTTPS 基线无法稳定运行；当前 JiuwenSwarm Agent Provider 不再可用；或 Direct Executor 不能在 disposable fixture 和独立数据目录内证明零跨项目副作用。

## D-079 剩余 S7/S8 窗口采用快速收口模式：批量修复 + 单次契约级冻结 + 人工只做物理部分

- 日期：2026-08-15
- 状态：Accepted execution-mode decision（用户在复盘"每修复一个缺陷即完整重验再冻结"消耗约 25 小时、六轮冻结循环仍未进入人工旅程后明确要求：先自动跑 S7/S8 集中发现并修复明确问题，过程不逐修复冻结、不反复跑不受影响的全量测试；最后按契约执行一次冻结、累积评审与全量验证；人工只承担必须物理在场的部分）
- 适用窗口：自本决定起至 S8-03 记录 Alpha 结论为止；操作合同为 `roadmap/S8_FAST_CLOSEOUT_PACKET_2026-08-15.md`，当前进度仍只由 STATUS 维护。
- 快速阶段：修复以 affected diff 自查 + affected tests + 一行台账落地；不逐修复运行完整 runner、不逐修复重建候选冻结、不逐修复生成外部 report/handoff。
- 分诊门槛：本窗口只修阻塞级发现——不安全/部分/重复 mutation 或数据丢失；隐私/凭据/raw-audio 暴露；核心旅程无 reload/restart 即无法继续的死路 UX；必需 showcase 节完全无法执行。其余（措辞、诊断文案、打磨、罕见路径恢复）一律进偏差台账，不在本窗口修复。
- 收敛判据：扫描必须广度优先、先扫完再报告全部发现；一轮完整扫描零新增阻塞级即停止修复进入冻结。硬上限：三个修复批次后仍出现新阻塞级，停止迭代并连同台账升级用户决策。
- flaky 规则：孤立重复 ≥100 次通过、所属完整测试文件通过、产品源码未变、仅在全量负载下偶发失败的用例，记为 accepted test-evidence deviation，不阻塞最终 runner，本窗口内不再重写。
- 终态收口顺序：先在最终源码上一次性完成全部文档/台账提交，再对该精确干净 HEAD 运行唯一一次完整 runner + 五类真实探针，再产出外部 report 与 `live-voice.s7-a3-handoff.v1`（S7-03 `PASS`、S7-04 `FROZEN_FOR_A3`）；冻结后零 tracked 编辑。外部 fail-closed 绑定规则不变。
- 人机分工：可由机器执行并记录的点击、查询、刷新/重连、重启对账、降级、隐私/日志扫描、Store/Executor 结算按 showcase 分节记为 `machine-verified` 证据；用户只做物理麦克风说话、亲耳听感、语音打断、设备/权限物理行为、一次连贯联合旅程与最终 `PASS/PARTIAL/BLOCKED/FAIL` 判定。机器事件不得改标为人工观察。
- 主机边界：Phase C 入口向用户一次性确认最终验收主机（当前主机或既定目的地服务器）；确认后不再迁移。选择目的地时按包 §6 执行目的地重验，源主机的 report/runtime/fixture/Session/人工观察一概不迁移。
- 不降低底线：D-032 正例/负例/零禁止副作用矩阵、Tier-3 独立评审（聚合到批次收口与终态累积层级执行）、真实 Provider/设备/Executor 不得造假、D-074 审查语义全部保持；本决定只取消重复时点，与 D-074"修复只重跑受影响层级，不因无关调整重跑未受影响阶段"的既有效率条款一致。
- 取代关系：本窗口内取代 STATUS 旧 Next actions 中"任何新源码修复即重启精确候选评审与 S7 冻结"的操作性节奏，以及实践中形成的"每修复即全量 runner + 再冻结"惯例；不取代 Alpha acceptance 内容、外部冻结绑定规则或 S5–S8 计划 §7 排除项。
- 重新评估条件：阻塞级发现在三批次上限内无法收敛；最终 runner 因非 flaky 原因反复失败；机器证据与人工观察边界发生争议；或用户收回快速模式、恢复逐修复冻结节奏。

## D-080 Live Voice 运行中调整与终态主动通知复用现有 v3/P2 权威链路

- 日期：2026-08-16
- 状态：Accepted Tier-3 design checkpoint（实施与候选验收仍待 D119 闭环）
- 调整契约：第一版正式增加 `task.adjust`，只绑定认证主体、项目、Session 下的非终态 current background Task。它复用 Store v3 的 command、通用 outbox、TaskEvent 和 current pointer，不预设 v4 或独立 adjustments 表。原子 admission 写入 command、`task.adjust_requested` 和 adjustment outbox；运行中的 Direct Executor 必须在安全检查点按权威顺序真实消费，只有 Core 持久化 `task.adjust_applied` 后才可声称已应用，无法消费或已越过检查点则写入 `task.adjust_rejected`。状态只包含 pending/applied/rejected。
- 终态与修订：终态 Task、历史 TaskResult 和已应用结果不可修改。本批次只提示用户明确创建修订任务，不自动创建 successor revision，不增加撤回、合并、superseded 或 revision lineage。
- 通知契约：终态 TaskEvent 是稳定通知身份和恢复事实；继续使用 TaskEvent → task progress return → P2 notification/presentation/ACK/TTS，不增加完成通知表或第二套协议。主动播报由当前有效 P2 activation 取得新的 response generation，禁止复用 task-create 的旧/superseded response；没有有效 activation 时保留未消费的 TaskEvent，待下一次有效 activation 重放。completed 只有同时存在合法 immutable TaskResult 才能播报完成，failed/cancelled/interrupted 分别如实播报。
- 重放语义：presentation ACK 后同一稳定通知不再投递；播放后 ACK 前崩溃继续遵循现有 P2 replay，不宣称无条件 exactly-once。通知与 ASR final、Agent output、TTS 串行互斥，且通知、插话、Speech 错误对 Task cancel/mutation 的副作用必须为零。
- 语义与 UI：统一入口扩展为 dialogue、background.create/update/query/status/cancel 六路。create/update 分离并使用高置信度全句规则；普通非任务问句、歧义和低置信度保持 dialogue，current Task 的结果、进度和 adjustment 状态问句仍路由 query/status。UI 只增加转写/错误分离、重新监听、调整状态和终态通知，不恢复 Send、Agent/Task、operation 或 Task ID 控件。
- 重新评估条件：源码或并发测试证明 v3 无法原子表达上述 admission/排序/重放；现有 TaskEvent/P2 ledger 无法在进程恢复后重建未 ACK 通知；或 Direct Executor 无法在终态前提供确定性安全检查点。只允许针对被证明缺口的最小结构扩展。

## D-081 已验收 Alpha 不因 Post-Alpha Demo 扩展与修复回退

- 日期：2026-08-17
- 状态：Accepted project-status and validation decision（用户明确要求保留已经完成的 Alpha 验收，不因准备后续 Demo 时发现并修复缺陷而把 S7/S8 改回未完成）
- 里程碑语义：`PASS — INTEGRATED WEB ALPHA` 继续绑定 2026-08-15 已验收的精确源码 `d33b520e0d21ae0829d30814d77a01cc18256f09`，S8/A3 保持关闭。Alpha 之后加入的免手循环、运行中调整和终态通知能力，以及这些能力暴露的后续缺陷，不倒写该历史验收、不把 S7/A2 或 S8/A3 重新打开，也不把新源码冒充为原验收源码。
- 当前工作：当前阶段内工作定义为 `Post-Alpha Demo preparation / bug repair`。先修复 STATUS 中的 unified-create 完成通知与 completion-adjacent barge/P2 recovery 两个阻塞，再在最终 Demo 源码上验证；它们阻塞新的 Demo，不撤销 Alpha PASS。
- 验证方式：修复过程运行受影响正例、关键负例、flag-off、恢复/并发与零禁止副作用检查；最终源码运行 Demo 范围内风险相称的受影响/累计检查和 Tier-3 评审，随后完成一次完整真实麦克风/TTS Demo Journey。这是 Post-Alpha Demo 验证，不创建新的 Alpha freeze/handoff，不重走 S7/S8 流程，也不降低 D-032、D-071、D-074 的安全、真实路径和评审底线。
- S9 边界：S9 尚未开始。完整 P3、Beta/RC/Production、公开部署、生产鉴权/多租户、D1/D2 和稳定性/SLO 等仍属 Later；当前 Demo 修复本身不取得任何 S9 进度信用。
- 取代关系：本决定取代 D119 结尾“当前还需一次 S8/A3 physical acceptance”的当前状态解释；D119 对精确 `3bc7f934` 的设计、实现、测试与评审事实保持冻结有效，其 S7/A2、S8/A3 文案只作为当时候选记录。当前事实和下一步只看 STATUS。
- 重新评估条件：用户明确重新打开 Alpha 里程碑；发现原已验收源码本身的验收记录失实；当前范围扩展到 S9；或 Demo 修复改变已接受的核心安全/权威合同而需要新的阶段定义。

## D-082 当前项目状态改用产品准备度与能力/模块完成度

- 日期：2026-08-17
- 状态：Accepted project-governance decision（用户要求从项目角度重新审视真实实现，明确已完成、部分完成和未完成，并停止使用旧的编号阶段体系表达当前状态）
- 当前状态语义：`STATUS.md` 只按产品准备度、能力/模块完成度、真实阻塞和有序下一步表达当前项目。有效状态包括明确边界内的 `COMPLETE`、`PARTIAL`、`BLOCKED`、`NOT STARTED`/`NOT READY`；任何“完成”都必须同时写清适用源码和产品边界。
- 历史验收语义：已接受的 Integrated Web Alpha 继续绑定精确源码 `d33b520e0d21ae0829d30814d77a01cc18256f09`。改用能力口径既不撤销该历史验收，也不把后续源码、Demo 扩展或生产范围自动标记为完成。
- 执行包语义：新的实现或修复包必须声明产品能力/模块、风险等级、依赖、包含项、排除项和验收；不得再从旧计划编号推导当前队列、优先级、进度或验收要求。
- 历史保留：冻结的路线、执行计划、评审、证据及已有测试/文件名中的旧编号保持历史真实性，待代码与文档整理时按安全范围归档或重命名；它们不能覆盖 STATUS，也不构成当前工作授权。
- 取代关系：本决定取代 D-075/D-076/D-079/D-081 中关于“用编号阶段/节点描述当前工作”的解释。上述决定的能力边界、安全要求、精确源码验收事实、测试/评审证据和历史顺序继续有效。
- 重新评估条件：用户重新要求阶段式项目管理；能力依赖无法通过模块执行包表达；产品边界发生需要新里程碑合同的重大变化；或历史验收事实被证明不真实。

## D-083 先收敛当前文档权威，再按产品真实性优先完成实现

- 日期：2026-08-17
- 状态：Accepted cleanup/execution decision（用户批准立即执行稳定验证权威迁移与第一批文档删除，要求把产品缺陷记录为后续实现最高优先级，同意测试先迁移再删除旧入口，并把 develop 集成延后到全部功能完成）
- 文档执行：根 `TESTING.md` 接管 D-032/D-046/D-074 的当前风险分级、场景维度和 review cadence；带日期的 Post-V0 路线图从工作树删除。当前 pass/fail 与人工 Journey 分别改为 `validation/PRODUCT_READINESS_ACCEPTANCE.md` 和 `demo/PRODUCT_READINESS_SHOWCASE.md`，不再使用编号阶段作为当前验收入口。文档退休审计 Batch A 的 19 份历史/孤立/旧脚本文档已删除，精确内容由 Git 历史恢复。
- 实现优先级：下一项产品代码工作必须先关闭 STATUS 中 Executor application/terminal/result、Task truth、bounded update/status、result context 和 P2/TTS/presentation 生命周期缺陷；文档清理不得把这些缺陷挤到后面。
- 测试迁移：删除 S7/S8/W2 rehearsal 等旧脚本或测试入口前，必须先把仍适用的正例、负例、flag-off、恢复/并发和零禁止副作用 oracle 迁移到能力/模块 owner，并证明新 owner 可独立发现相应缺陷。入口删除与迁移后的 affected discovery/checks 属于同一清理批次。
- Hardcode 时机：`.env.production` 默认开启部分 Demo 能力及 launcher 对该文件的强依赖是当前应处理的产品真实性问题，必须在下一受控产品候选构建前改为显式 Demo profile/进程配置；精确 itinerary、trusted Demo bypass、adjustment checkpoint 和 launcher 的其余场景固定值保留到下一次干净真实 Journey，随后随泛化替换而删除。协议常量、安全边界、稳定事件/错误名和显式 bounds 不按 hardcode 债务删除。
- 重复代码时机：registry generation-index 遍历只在当前缺陷批实际触及该 owner 时做窄合并；前端 validator、`exactObject`、binding equality 和 task clone 在后续代码整理批统一。confirmation/mutation/close/ACK 等 authority handler 即使结构相似也不在当前抽象，除非先证明业务绑定、幂等、失败和零副作用语义完全一致。
- develop 集成：用户明确要求在全部产品功能完成前不 re-fetch/rebase/merge/cherry-pick `origin/develop`。现有分叉继续作为 STATUS 风险记录，但不进入当前执行队列；功能完成后再单独审计累计差异并选择历史策略。
- 单 commit 与分批 review：继续遵守“全部修改完成后只建立一个最终 commit”。分批 review 指在未提交工作树中按文档清理、测试迁移、缺陷修复、兼容/Hardcode 退休分别检查 scoped diff 和运行 affected checks；它们不是中间 commit。全部完成后再审累计 diff、运行最终验证并建立一次 commit。
- 重新评估条件：文档删除发现唯一当前合同/证据没有稳定 owner；测试无法在删除旧入口前迁移；产品缺陷修复必须改变已接受的高风险合同；或长期 develop 分叉使继续实现产生已证明的重复劳动/不可解决冲突。

## D-084 用四个完成边界和当前能力矩阵定义完整项目接续

- 日期：2026-08-17
- 状态：Accepted project-completion decision（用户要求新 Session 不仅能看到优先缺陷和待办类别，还能理解完整项目剩余能力、依赖、完成判据和 `develop` 集成触发点，并批准执行文档重构）
- 完成边界：当前项目依次区分 `controlled product-readiness candidate`、`feature complete`、`productized candidate` 和 `RC / Production ready`。四者是累计但不可互换的产品结论；历史 Integrated Web Alpha 继续绑定其原精确源码。
- 功能完整：`feature complete` 包含正式 P1/P2、完整 P3、Integrated Web 体验、多任务寻址与完整控制操作、结果/replay、按 Executor capability 如实提供的 D0–D2 语义、延迟指标、Provider/Executor/配置/语言/任务策略泛化、Demo/legacy authority 退休、广泛自动验证、竞品缺口审查和独立跨模块深度 review。
- 功能完整排除项：生产鉴权/多租户、公开部署、SLO/retention、发布/回滚运营、额外平台承诺和可选 Native model-level duplex 不阻塞 feature-complete；这些进入 productized 或 RC/Production 边界，除非后续决定显式提前。
- 集成触发：用户所说“全部功能完成后再集成 develop”绑定 `feature complete` 验收通过。通过前不 re-fetch/rebase/merge/cherry-pick `origin/develop`；通过后先审计实时 Git 分叉和累计冲突，再选择历史策略并完成受影响验证。历史 ahead/behind 数字不作为长期状态事实。
- 当前权威：`STATUS.md` 用一张能力矩阵同时表达已实现、剩余功能、依赖和验收，并用一个当前执行包和一条到 feature-complete 的依赖路线取代多份重复的 completed/remaining/next-work 摘要。实时 HEAD、branch、upstream、ahead/behind 和 dirty 状态只从 Git 读取；STATUS 仅记录最后完成产品代码审查的基线。
- 历史设计：`FULL_SOLUTION_2026-07-30.md` §§2、4–5 继续提供稳定 P1/P2/P3 能力、模块和共享合同边界；其旧载体、旧代码差距、编号 Work Package、日历 timebox 和交付顺序是历史输入，不得直接变成当前任务。
- 取代关系：本决定取代 D-075/D-076/D-081 中仍以编号阶段表达当前项目完成路线的解释，并扩展 D-082 的能力口径与 D-083 的“全部功能完成后集成”边界；这些决定保存的精确源码、已执行验收、安全合同、测试迁移和清理时机事实继续有效。
- 重新评估条件：用户改变 `develop` 集成触发边界；Production 能力被要求提前进入 feature-complete；某项完整 P3/D1/D2 能力被明确移出产品范围；或代码事实证明当前模块划分无法表达真实产品权威。

## D-085 逐模块代码事实审计是当前修复和功能完整路线的前置依赖

- 日期：2026-08-17
- 状态：Accepted execution-dependency decision（用户确认现有能力矩阵尚未经过一次全新的逐模块代码事实审计，并要求将该工作写入待办与 feature-complete 依赖顺序）
- 审计范围：在精确当前源码上逐一检查 STATUS 的 15 个能力域，记录实际 entrypoint/owner/call chain、formal/legacy/Demo/flag-off 路径、已实现行为、测试与缺失 oracle、hardcode、重复实现、退休条件、跨模块依赖和有代码证据的状态判断。
- 顺序与信用：审计是当前 Tier-3 产品真实性修复的只读前置步骤。STATUS 完成校准前不得基于现有矩阵授予新的模块完成信用；六个已知阻塞不因此降级，审计应先验证并补全它们，再进入同一确认后的修复包。
- 验证强度：只读审计本身不要求预先运行全量测试；先执行源码/测试发现与静态核对，只对有争议的代码事实运行 focused tests。实现修复、候选关闭和 feature-complete 仍执行各自风险相称的累计验证与真实 Journey。
- 交付物：一份可追溯的逐模块代码事实审计、每个能力域的代码—测试—缺口—依赖—状态映射，以及所有发现不一致后的 STATUS/执行包/优先级更新。
- 重新评估条件：审计期间产品代码改变；模块 owner/能力边界无法按当前 15 域表达；focused evidence 与既有 exact-source 记录冲突；或发现必须先改变高风险合同才能判断实现状态。

## D-086 P3-G0 按 P3 权威基础闭环并将持续监听修复转回 P1/P2 完成包

- 日期：2026-08-19
- 状态：Accepted scope-and-sequencing decision（用户要求记录问题、现象、原因和解决方向，在 P1/P2 从 `PARTIAL` 进入 `COMPLETE` 时处理，并立即闭环 P3-G0、推进 P3）。
- 不改写的事实：精确产品源码 `f24dd17d336c8266954f2d7299ca13bd0314d424` 的受影响自动化、构建、静态审查和 clean-SHA 部署有当前证据，但真实 hands-free Journey 两次进入 `AUDIO_CAPTURE_DURATION_EXCEEDED`，因此该源码仍是 `FAIL — NOT A CONTROLLED PRODUCT-READINESS CANDIDATE`；documentation-only 决定不能把它升级为 PASS。
- 问题归属：active Live Voice 在 TTS 后自动返回监听、采集租约轮换、回声/double-talk、speech-start/EOT 与 cancel cleanup 属于 P1 Audio/Speech 和 P2 Media/Conversation Runtime 完成边界，不由 P3 Task Control Core/Store 实现，也不再作为 P3-1 的排序 Gate。问题、机制、未决归因和修复方向记录在 [延期缺陷证据](../evidence/P1_P2_POST_TTS_CAPTURE_CONTINUATION_DEFERRED_20260819.md)。
- P3-G0 闭环口径：D-085 审计、六组 P3 产品真值源码修复、适用自动化/构建/静态证据和显式 Live Voice profile 构成允许 P3 扩展的 authoritative foundation。未完成的综合真实 Task Journey 转入 P3-9/累计产品验收；它不授予受控候选 PASS，也不授予 P1/P2 COMPLETE。
- 当前顺序：STATUS 立即激活 P3-1 canonical multi-Task model/Store/migration。P1/P2 延期缺陷保持显式 `PARTIAL`，可在不冲突的 owner lane 中后续修复，但必须在 D-084 feature-complete、`develop` 集成触发和任何新的受控产品候选 PASS 之前关闭并完成真实 Journey。
- 风险接受：在未完成综合物理 Task Journey 的情况下展开 multi-Task 会保留集成风险；后续 P3 包不得继承不存在的物理信用。若 P3-1 发现六组真值修复本身存在新的 P3 权威缺陷，应回到对应 P3 owner 修复，而不是归因给本次 P1/P2 延期。
- 重新评估条件：P3-1 需要改变 speech/media 权威才能正确实现；延期缺陷阻断 P3-owned text/structured acceptance；用户恢复“受控候选 PASS 先于任何 P3 扩展”的顺序；或准备 D-084 feature-complete/`develop` 集成。

## D-087 P3-2 冻结六项命令合同并以真实 capability 限定正向控制

- 日期：2026-08-19
- 状态：Accepted P3-2 shared-contract decision（用户要求完成六项合同冻结并立即推进 P3-2；冻结基于 accepted P3-1 `d40e0ee391fdf162faa9d9938eb9b9610020c1a7` 和 clean activation parent `9f2636bd33f1e267059ce4e05431374fb04ae572`）。
- Successor：新增命令名固定为 `task.create_successor`，目标是精确 terminal predecessor；payload 绑定 predecessor revision/event head/terminal event/outcome/result digest 和新 Task spec。`completed/failed/cancelled/interrupted` 可在精确确认后创建一个新 Task，`unknown` 不可创建；每个 predecessor 最多一个直接 successor。predecessor Task、Attempts、Events 和 Result 均不可修改。新命令的 same-Task `task.retry` 仅保留 `cancelled` execution recovery；历史已应用的 completed-retry 仍可读取和重放，但不得再创建新的 completed-retry。
- `provide_input`：只回答 exact current `task.decision_required` event，不把普通 `blocked` 当作 input-required。payload 固定绑定 current Attempt、event head、`responds_to_event_id` 和 bounded answer；answer 是需持久化的 untrusted Task data，不是 system instruction，不进入日志/telemetry。没有 P3-3 proven input/checkpoint capability 时返回 `unsupported`；除 sanitized Command decision ledger 外，Task/Attempt/Event/outbox/Executor effect 必须为零。
- Pause/resume：P3-2 不增加 `paused` canonical state，不把 `accepted/blocked/decision_required` 重命名为 paused，也不决定 same-versus-linked resume Attempt。两种命令可进入跨语言 closed parser，但当前所有非终态路径返回 `unsupported`；terminal 返回 `conflict`。只有 P3-3/P3-4 后续冻结真实 pause boundary、capability version 和 recovery identity 后才能增加正向行为。
- Update/adjust：`task.update` 只在 Task=`accepted`、current Attempt=`accepted` 且 dispatch outbox 从未 claim/deliver 时原子替换 instruction/constraints，并同步 canonical Task spec、dispatch payload、Command、requested/applied Events；其他当前状态或已 claim/deliver 的 dispatch 返回 `conflict`。运行中 checkpoint 继续使用现有 `task.adjust` exact `{adjustment}` compatibility command；它不等于 `provide_input`，不接受 pre-dispatch、blocked、decision-required 或 terminal target。未来若 P3-3 要增加 live `task.update`，必须另行扩展合同。
- Reprioritize：wire vocabulary 固定为 `low|normal|high|urgent`，但当前没有真实 scheduler/admission owner，因此所有非终态请求返回 `unsupported`、terminal 返回 `conflict`，且不得写 Task/Event/outbox 或展示成功。P3-3 只有在选择真实 owner 和 capability version 后才能组合正向行为。
- Disposition：Command-only disposition 固定为 `accepted/applied/rejected/unsupported/conflict/timeout/unknown`，放入现有 `ResultEnvelope.extensions["live_voice.command"]` 并保持 Python/TypeScript parity；query success 不伪装为 command `applied`。ErrorCode 继续分别表达 invalid/auth、unsupported/capability、conflict/stale、timeout 和 result-unknown。exact replay 在当前 precondition 前返回已存结果；同 command ID 不同 fingerprint 返回 conflict。canonical authenticated decision 可只持久化 fingerprint、sanitized result 和 authority binding；未认证/未解析 wire 不建 Store authority，accepted payload 不得进入日志或 telemetry。
- 持久化与 schema：P3-2 复用 schema v4 的 immutable Command fingerprint/result、TaskEvent、outbox、Task spec 和 P3-1 predecessor/revision fields；requested Event 是不可变 admission receipt，settlement Event/outbox/result 是 later disposition authority。P3-2 不独立 bump SQLite schema；P3-5A 仍未激活并拥有下一次 result/unread/consumer migration。若实现证明六项合同无法在 v4 上保持 admission/settlement immutable，应在写 DDL 前重新激活一个共享 Core/Store schema packet，而不是静默扩张。
- 顺序与竞态：所有可变命令绑定 exact scope/task/attempt/event head 或 predecessor facts；同 ID exact replay 优先，changed fingerprint、stale version、concurrent terminal/cancel/successor winner 均 fail closed。每个 rejected/unsupported/conflict/timeout/unknown 路径必须证明 zero forbidden Agent/Tool/Task-other-row/Executor/file/audio/history/presentation effect。
- 范围：该决定只冻结 P3-2 协议、Core/Store 事务和测试 oracle；不激活 P3-5A，不实现 P3-3 capability/admission、P3-4 recovery、P3-6 natural-language targeting、P3-7 UI、P1/P2 延期修复或任何 Production/remote work，也不授予实现或产品验收信用。
- 重新评估条件：P3-2 需要新增 canonical Task state 或 SQLite DDL；发现 current Executor 已有与本合同冲突的真实 pause/input/priority owner；successor 必须支持 `unknown` predecessor；same-Task completed retry 无法在不破坏 immutable TaskResult 的情况下停止；或 Python/TypeScript/Product consumers 无法以当前 ResultEnvelope extension 保持 closed parity。

## D-088 Wave 2 并行激活 P3-2、P3-3 与 P3-5A，并冻结 admission/consumer 合同

- 日期：2026-08-19
- 状态：Accepted Wave-2 multi-package decision（用户批准在当前 Main Session 下以隔离 worktree/subagent 并行完成 P3-2、P3-3、P3-5A，中途采用最少介入，由 Main 单独持有共享语义、schema、集成历史和最终验收包；远端仍等待最终精确批准）。
- 批次与所有权：Main 是唯一 Integration Owner。Core/Store lane 串行拥有 P3-2 与 P3-5A 的共同协议、records、transaction 和 migration；Executor lane 只拥有 P3-3 的 capability/selector/Direct Adapter 与 admission observation 实现。任何 `formal_task_models.py`、`task_store.py`、共同 Python/TypeScript contract 或迁移冲突均回到 Main/Core owner；两个 worker 不各自发明 schema 或 terminal truth。
- P3-2 顺序：D-087 仍是 schema-v4 command freeze。先证明 `task.update`、`task.adjust` compatibility、zero-effect unsupported controls、cancel disposition 和 `task.create_successor` 在 v4 上闭环；P3-2 不获得独立 DDL。P3-3/P3-5A 集成后，accepted/queued `task.reprioritize` 可由下面冻结的真实 admission queue owner 从 `unsupported` 升级为 `applied`，而 running/blocked/decision-required/terminal 或已被 Executor 接管的目标保持 `conflict`，不伪造运行时调度能力。
- Capability 与 requirement：P3-3 新增一个 canonical、immutable、可 canonical-hash 的 `ExecutorCapabilityProfile` v1，以及与 command authorization 分离的 `TaskExecutionRequirements` v1。profile 绑定 executor/Adapter identity、operation versions、D0 durability、observation/cancel/adjust support、project serialization、capacity/enforcement facts；Attempt 持久化选择时的完整 profile snapshot/digest 与 requirement。static mismatch 在 Task/Attempt/outbox 写入前返回 `unsupported`；Adapter 已接受或外部 outcome unknown 后禁止 fallback。
- Admission：Task/Attempt `accepted` 仍是 canonical truth，`queued` 只由 accepted lifecycle 加持久 admission facts 投影。capacity/project busy 保留同一 Attempt，记录 closed reason、attempt count、priority、next eligible time 和 absolute deadline；默认 admission deadline 为可配置的 60 分钟，retry backoff 有界且不移动 absolute deadline。deadline/budget 耗尽由 Core/Store 原子终止 Task/Attempt 为 `failed`，reason 精确为 `EXECUTOR_ADMISSION_TIMEOUT`，不创建 TaskResult、不调用 Executor、不声称曾 running。admission queue 真实使用 `low|normal|high|urgent` 排序，并保持同优先级稳定顺序。
- Orphan/fence：Store outbox claim、Direct Adapter journal lease/generation/runtime deadline 与 OS ownership lock 是三个不同证明。无法证明外部 ownership/outcome 时只暴露持久 `reconciliation_required` projection、reason 和 manual-action need；不伪造 terminal、不重分配 Attempt、不自动重试未知 effect。P3-4 继续单独拥有 D1 checkpoint、same-versus-linked recovery Attempt 和 D2 effect reconciliation/人工结算。
- Direct Adapter 正向边界：本批必须用 versioned profile 和真实 Direct Adapter/current factory 证明 dispatch/start semantic、status、exact cancel、当前 checkpoint `task.adjust`、跨项目并发、同项目 serialization、capacity queue、deadline/fence 与 D0 reconciliation。`provide_input`、pause、resume、generic running `task.update` 和 running reprioritize 在缺少真实进程/Agent/scheduler primitive 时继续如实 `unsupported` 或 state `conflict`；完整项目的 primary Integrated Web Direct Adapter 仍必须在后续 P3-4/P3-5B/P3-6/P3-7 组合中为五项控制建立其合法状态的真实正向路径，不能把本批 unsupported 当成 feature-complete。
- P3-5A consumer：stable consumer 由服务端认证的 `(subject_id, project_id)` 派生，不由 Session、response、generation、浏览器存储或 `current_background_tasks` 派生。presentation class 关闭为 `text|voice`，两类 watermark 完全独立。`task.events`、`task.result`、`task.unread_events` 和展示均为纯读；只有显式 authenticated `task.ack_events` 可推进消费。
- P3-5A ACK/replay：`task.unread_events` 读取 exact Task/presentation class 的 retained events above watermark；page limit 保留 `1..500`。`task.ack_events` payload 绑定 `presentation_class`、`acked_through_seq`、该 sequence 的 `acked_event_id` 和 observed `expected_event_head`；exact replay 返回原结果，lower/equal watermark 为 idempotent no-op，future/missing/wrong scope/task/class/consumer/changed fingerprint 为 rejected/conflict 且零 Task/Attempt/Event/Result/Executor/presentation-other-class effect。并发 ACK 只可线性推进到最大合法 contiguous prefix。
- P3-5A retention/schema：TaskEvent 和合法 immutable TaskResult 在本批中保留至 Task lifetime；不加入 Production retention/SLO/compaction policy。P3-5A 是下一次 SQLite schema v5 的唯一 owner；v5 同一迁移可容纳已冻结的 P3-3 Attempt capability/admission facts与 P3-5A consumption ledger，但不得预建 P3-4 checkpoint/effect tables。migration/backfill/failpoint/reopen、v1→v4→v5 和 v5 concurrent initializer 都归 Core/Store Tier-3 review。
- 证据和非声明：每个 child package 独立覆盖 root TESTING 的适用 P/N/B/S/T/C/R/I/F/K/X 与 zero forbidden effects；批次后才运行 shared seam/cumulative verification。positive P3-3 至少经过真实 Direct Adapter、真实 Agent 和真实 Tool 的 disposable no-remote project；fake 只可证明 negative/race。该批不包含 P1/P2 延期修复、P3-4 D1/D2、P3-5B Runtime/Web ACK composition、P3-6 NLU targeting、P3-7 UI、完整 P3/feature-complete、`develop` integration、Production 或 remote ref update。
- 重新评估条件：P3-2 无法保持 v4；v5 无法由单一 transaction owner 同时容纳冻结的 admission/consumer facts；真实 Direct Adapter 与 profile 声明冲突；queued priority 无法真正影响 admission；60 分钟 deadline 或 orphan projection需要新的产品政策；P3-3 必须预建 D1/D2；P3-5A 必须使用 Session/generation consumer；或并行文件/语义隔离失效。

## D-089 Wave 3 并行激活 P3-4、P3-5B 与 P3-6，并冻结 recovery/presentation/targeting 合同

- 日期：2026-08-20
- 状态：Accepted Wave-3 multi-package decision（用户明确要求在 `hx/0812_live_voice_w3` 上使用 Goal 模式，以 Main Integration Owner 和三个隔离 worker lane 正式完成 P3-4、P3-5B、P3-6；授权任务范围内的本地 branch/worktree/commit/cherry-pick、自动化、独立 Tier-3 review 和 ACL-private 有界真实验证，并要求除无法从现有合同、代码和 fail-closed 原则推导的重大产品选择外最少介入；所有 remote-ref update 仍未授权）。
- 精确基线与顺序：激活基线是 clean `cfff0c43aa599c009ab9517397566fec5c1bdd95`，其 upstream 为同 SHA。三个 lane 可并行开发，但 Main 只能按 P3-4 → P3-5B → P3-6 → shared composition 顺序集成。Main 是唯一 shared semantic/schema/composition owner、W3 history writer、证据 owner 和 remote gate owner；worker 只写各自隔离分支且不得 push。
- P3-4 recovery identity：当前 Direct 是唯一首选真实 D1/D2 候选，legacy 保持 D0-only。D1 保留同一 `task_id`，但恢复必须创建显式 linked/new `attempt_id`；producer Attempt、lease/source sequence、checkpoint、effect 和 result provenance 不可复活或重写。只有 immutable checkpoint、exact Task/project/context/profile/durability/effect prefix 和 producer quiescence 全部精确匹配才可恢复；缺失、stale、corrupt、unknown 或不兼容均 fail closed。
- P3-4 Store/effect authority：`SqliteTaskStore` 是唯一 canonical schema/migration/recovery transaction owner；如 P3-4 需要持久化记录，只允许从当前 v5 到一个 v6 migration，并保持 v1-v5 reopen/backfill/failpoint/concurrent-initializer compatibility。Adapter runtime journal、lease/generation 和 OS lock 保持 Adapter-owned 且彼此独立；外部调用不得发生在 Store transaction 内。D2 logical operation key 绑定 Task、origin Attempt、operation kind/ordinal、target、intended-effect fingerprint 和 selected profile；intent 先持久化，process death after call/before receipt 为 `unknown`，自动 retry 只在 stable-key contract 或权威 `no_effect` observation 下允许，否则进入 durable `manual_required`。任何 operator settlement seam 不注册到普通 voice/text/`provide_input`。
- P3-5B durable presentation：durable consumer identity 固定为 authenticated `(subject_id, project_id, task_id, presentation_class)`，其中 class 只允许 `text|voice`；Session、interaction、response、generation 和 delivery 只绑定一次 presentation attempt，不是 durable identity。refresh/new Session 必须取得新的完整 authorization grant。DOM adoption 只能授权 text ACK，Audio Device accepted `PresentationAck` 只能授权 voice ACK；fallback-to-text 不能消费 voice。`task.unread_events` 保持纯读，只有 exact presentation owner 接受 Task/Event/class/response/generation/delivery 后发出的 `task.ack_events` 可推进 durable consumption。presentation 后、commit 前 crash 可重放，因此产品承诺是 at-least-once。
- P3-6 targeting/clarification：支持范围冻结为当前 English/Chinese closed resolver/corpus boundary；activation Gate 要求现有 68 cases 和 14 parity groups 全部通过，并增加 actual production Resolver/Bridge evidence。显式 Core `task_id` 是当前 server-owned stable reference；唯一 authorized exact name 可解析，零/多候选、duplicate name、changed Task set 必须澄清或拒绝，current/recent 只可作 hint。clarification 是 bounded server-owned pre-command state，绑定 subject/project/source commit/operation/candidate-set fingerprint/generation/expiry，single-use CAS；本批选择 fail-closed restart policy，所有 pre-restart handle 失效并签发新 identity。confirmation 单次绑定 operation/target/arguments/Task-set fingerprint，并在 Core invocation 前重新读取 exact Task/Attempt/event/result/capability facts。
- Authority firewall：P3-6 Resolver/Bridge 只能消费 authenticated Core `list/status/get/events/result/unread` 和 exact visible Task/profile/confirmation facts；corpus、file、dialogue、UI、current/recent 都不是 authority。`task.create_successor` 只使用 Core exact predecessor outcome/result digest；没有真实能力的 `provide_input/pause/resume` 与 running update/reprioritize 继续返回 truthful `unsupported|conflict`。P3-5B/P3-6 不得新增 Store/schema、第二 consumer/resolver/command authority或直接调用 Agent/Tool/Executor/TTS/history。
- Acceptance 与非声明：三个 child package 分别覆盖 root TESTING 的适用 P/N/B/S/T/C/R/I/F/K/X、positive real seam、restart/race/failpoint 和 zero-forbidden-effect evidence；各自一次 cold self-review、一次 independent Tier-3 review 和一次 fix-only review，全部集成后只运行一次 fresh broad Python/Formal Web/strict contract/build/static Gate。真实运行只能使用 fresh ACL-private root；失败 root 保留 `CLEANUP_PENDING`。本决定不授予 P3-4/P3-5B/P3-6、完整 P3、feature-complete、controlled product-readiness、Production 或 remote credit。
- 重新评估条件：实现要求 same-Attempt D1、第二 Store/coordinator/resolver/consumer authority、新 canonical Task state、v6 之外的并行 migration、普通用户可触发 D2 settlement、新 Provider/account/billing/public deployment、扩大到 P3-7/P3-8B/P3-9/P1/P2、或改变上述用户可见 presentation/clarification/targeting 语义。

## D-090 P3-5B 重连消费重新激活 P3-5A/Core 的 Task-wide 只读游标协议

- 日期：2026-08-21
- 状态：Accepted shared-owner re-scope decision（D-089 Tier-3 review 证明，仅用当前 Attempt 的 live subscription 无法在 durable watermark、retry/recovery Attempt rollover、进程重启和大前缀下正确完成 P3-5B；用户已授权 Goal 模式下最少介入地正式完成并本地集成 P3-5B，Main 依 D-089 重新评估条件收回 shared semantic owner）。
- 所有权：这不是 P3-5B worker 的 Store 扩权。Main/Core 重新激活 P3-5A 的现有 `task.events`/`task.unread_events`/`task.ack_events` 真相，只拥有 `formal_task_models.py`、`task_store.py`、consumer source、Arbiter internal capability、shared composition 和相应 Tier-3 tests；DOM adoption、Runtime Audio `PresentationAck`、presentation reservation 与消费调用仍由 P3-5B owner 负责。
- 共享只读 Port：`SqliteTaskStore` 从既有 TaskEvent 与 class-isolated durable watermark 原子读取一个 Task-wide、跨 Attempt、bounded/paged suffix。每次初始读取冻结当前 head，并同时返回 watermark 时点的 exact latest projected Task lifecycle、latest accepted/retry/recovery Attempt boundary 和 current canonical terminal-head fact；后续页只能延续同一 frozen head。该 Port 不新增表、sidecar、consumer identity、watermark 或第二事件 ledger。
- 重启与 epoch：fresh Session/进程不得从浏览器、当前 UI、进程缓存或当前 Task state 猜测 Arbiter cursor。Bridge 只能从上述 Store-verified cursor baseline mint package-internal capability，恢复 exact `next_seq`、last lifecycle 和 Attempt epoch；canonical `task.retry_accepted` 与 `task.recovery_accepted` 都必须建立新的 verified Attempt epoch。generic/non-consumer Arbiter 的 sequence、capacity、duplicate 和 conflict 语义不变。
- 有界滚动：Store-verified consumer path可滚动丢弃早于 durable cursor/当前验证窗口的 per-event projection fingerprint，但必须保持 monotonic sequence、exact event bytes、Task/scope/Attempt binding、pending presentation 和 stale-generation fences。它必须同时覆盖 non-presentable gap 与 presentable lifecycle event；不能仅把固定 256 上限改成另一个固定上限，也不能放宽 generic Arbiter。
- 终结与竞态：frozen page 期间新 append 的 terminal 不得把旧 frozen head 当作 terminal。只有 frozen head 等于 current Task event head，且该 head 是 canonical `task.terminal` 时才可关闭；否则先完成冻结页，再重新读取并交付至真实 terminal。close/reconnect/ACK 与 append/retry/recovery races 均保持 zero forbidden Task/Attempt/Event/Result/Executor/Agent/history/other-class effect。
- Tier-3 acceptance：必须以真实 Store 证明 text/voice fresh Session 与 fresh process 从 nonzero watermark 恢复；cancelled/retry 与 interrupted/recovery 跨 Attempt 顺序；分页期间 terminal append；超过 256 个 non-presentable 及 presentable unread；bounded retained state；late/stale/foreign/changed facts fail closed。Registry AUDIO 路径还必须经过真实 Runtime presentation ACK 和 durable Core ACK，不得以 synthetic Arbiter 单测替代产品证据。
- 排除：不 bump schema v6，不改变 D-088 durable consumer key/ACK payload/retention，不增加 Session consumer identity，不创建第二 subscription/event truth，不授予 human-perceived exactly-once、P3-6、完整 P3、feature-complete、Production、physical 或 remote credit。
- 重新评估条件：正确恢复必须持久化 Arbiter/presentation state；TaskEvent 不能提供 canonical watermark baseline；consumer rolling 需要放宽 generic authority；跨 Attempt replay要求改变 Task lifecycle；或 v6 需要新增 DDL。

## D-091 P3-7 冻结正式多 Task Web 投影与重连新鲜度边界

- 日期：2026-08-21
- 状态：Accepted scoped P3-7 interface-freeze decision（A 线最终集成源 `98e063f084c140cb6eb0042de32f3695c89c7279` 通过受影响自动化、完整 Formal Web 判读和独立 Tier-3 review；该决定只向已排队的 P3-8B B2 开放冻结接口，不授予完整 P3、物理音频、controlled-product、feature-complete、Production、`develop` 或 remote credit）。
- 正式 Web owner：visible formal carrier 可列出并选择多个 authenticated Tasks；browser storage 只保存 selection hint。初始选择、refresh、切换和 reconnect 的正式 route 必须依次 fresh reread bounded list、exact status、完整 bounded events 和 result；Task/Attempt/Command/Event/Result、scope、correlation、revision/head、outcome 和 lineage 仍只来自既有 authenticated reader 与 Store/Core。
- Web-only control 投影：唯一新增 response field 冻结为 `live_voice.task.list|status -> result.supported_operations: string[]`，不新增 ReqMethod、common wire schema 或 Task state。status 值必须是既有 `AuthenticatedTaskFact.supported_operations` 与 current principal authorization 的 exact intersection；`task.retry` 仅由既有 permission-aware `retry_admission` 合并。预注入、错 scope/Task/Attempt/head/revision 或不一致投影 fail closed，且 Task/Store/Executor effects 为零。
- mutation 与结果：Web 继续使用现有 direct query、`live_voice.composition.p3.intent`、confirmation issue 和 mutate seams；command issuing、accepted/applied disposition 与 later terminal Task outcome 分离。`task.create_successor` 创建显式 successor，不重写 predecessor/TaskResult。`provide_input`、pause、resume 在没有真实 primitive 时继续稳定 unavailable/unsupported；Stop、barge-in 和 response/round cancel 永不映射为 Task cancel。
- durable presentation：P3-5B 的 authenticated `(subject, project, task, presentation_class)` consumption、Task-wide `task.unread_events`/`task.ack_events`、connected-DOM text adoption 与 Runtime AUDIO `PresentationAck` 继续是唯一 durable owner；Web 不建立 viewed-head/unread ledger，Task event 不直接调用 TTS，fallback-to-text 不消费 voice。
- reconnect/refresh fence：formal collection 第一次成功后，该 Session 的 progress route 是 connection-local。disconnect 必须同步失效 route；旧 effect closure、reconnect 和 later refresh 在 fresh list/status/events/result 完成前不得 activate 或 ACK。result/revalidation failure 保持 blocked 且零 additional activation/ACK/command/Task effect。第一次正式 collection 成功前，已接受 P3-5B generic durable progress 仍是独立 owner，P3-7 不反向接管。
- feature-off 与组合边界：ordinary production flag-off 保持零 formal Task transport/allocation 并保留旧 text path。P3-8B 只能以 content-free observation/diagnostic consumer 身份接入 Registry/AgentServer startup/shutdown/issuer、Runtime generation/response/PresentationAck 和上述 Task projection；不得改变它们的 authority、closed params/result、auth/durability/Store semantics 或 unsupported vocabulary。需要修改 A-owned file 时由 Main 重新签发 single-writer lease。
- 证据：backend authenticated composition/AgentServer `184 passed`，formal owner `14/14`，mounted affected `10/10`，build profiles `2/2`，production build PASS；完整 Formal Web `439/440`，唯一失败是已在 clean A baseline 复现的 P1/TTS Exit/immediate-re-enable late presentation ACK。最终独立 review 为 `0 Critical / 0 Important / 0 Minor`。详见 [P3-7 review](../reviews/P3_7_FORMAL_INTEGRATED_WEB_IMPLEMENTATION_REVIEW_2026-08-21.md) 与 [evidence](../evidence/P3_7_FORMAL_INTEGRATED_WEB_EVIDENCE_20260821.md)。
- 重新评估条件：实现要求新 common ReqMethod/schema/Task state、第二 Task/event/result/unread/confirmation authority、浏览器推断 principal capability/retry、跳过 fresh result 即恢复 formal route、Task event 直接触发 TTS、Stop/barge-in 扩为 Task cancel、改变 unsupported operation、P3-8B 需要修改 auth/Store/Core/durability semantics，或把 P3-7 自动化冒充物理/完整产品验收。

## D-092 P3-8B 接受有界诊断组合与三项替换门控退役

- 日期：2026-08-21
- 状态：Accepted scoped P3-8B decision（集成源 `c0de16b5eba7004381f314ee97cbc98b35fe4e87` 的配置、相关性、Registry producer、单一 exporter FIFO、内存 OTel callback backend 与 lifecycle 通过受影响自动化和独立 Tier-3 review；该决定不授予外部 OTLP、完整 Executor 物理调度、完整 observability、P3-9、feature-complete、controlled-product、Production、`develop` 或 remote credit）。
- 配置与身份真相：Mutation/D* 诊断只在 exact `DirectProjectCodeExecutorAdapter`、已 `prepare_startup` 的 exact `_DirectP3RuntimeOwner`、owner/Core 同一 executor 及 trusted confirmation verifier 全部成立时启用；query-only、过期、伪造或缺失配置 fail closed。公开 trace identity 只使用由 process-local owner 签发并由独立 trusted verifier 验证的 HMAC `lvpub:*` token；raw subject/project/session/correlation/Task/Attempt/Command 等 identity 不进入 backend，metric dimensions 保持闭集低基数。
- 生命周期与 authority：正式 `ProductObservabilityAdapter`/exporter 是唯一有界 FIFO/worker；runtime 只负责 validated configuration、correlation/causation、P3-8A codec、selected bounded in-process callback backend 与 health。达到 backend 容量即 non-ready，后续拒绝进入 failed；authority/diagnostic/delivery exact binding 不驱逐，容量或 cross-scope 冲突 fail closed/poison。诊断拒绝、异常、饱和和关闭不得改写业务 payload，也不得回落为 legacy collector 双投递。
- 正式 producer 边界：唯一 OPEN subject/project/session/correlation route 通过后，Registry 在权威成功或 Store read/ACK consumption 之后投影 confirmed mutation `Command` 与 initial outbox identity、status `Executor`、Store `Event/TASK_FAILURE`、available `Result`、terminal progress `Generation` 和 successful text/voice/P2 delivery `ACK`。这些投影不改变 common wire、Task/Core/Store/Executor/Runtime/PresentationAck authority。测试在同一 Registry/runtime/SQLite Store 中关联 create、真实 Store failed events、status/events/result、generation 与 ACK；Executor failure 是测试向真实 Store 注入的 synthetic `ExecutorObservation`，不是实际 Direct/Core dispatch。
- 明确非声明：checkpoint/effect 仅证明 codec/token map 可表达，没有正式 producer；recovery/reconcile/current outbox state、claim/lease 与独立 reconciliation truth 未组合；outbox 只表示 mutation accepted receipt 的 initial identity；backend 只是在进程内有界 callback，不是外部 OTel SDK/collector、持久 exporter、SLO/retention 或生产运维。
- 退役边界：本批仅删除已通过 replacement/oracle/flag-on/flag-off/rollback Gate 的 `scripts/live_voice_snapshot.ps1`、W2-only dotenv compatibility tuples/branches/exports 与两项孤立测试、ticket-in-path media compatibility symbols/branches。固定 media registry/handler/predicate/WebChannel、ordinary dotenv、正式 P3 Web carrier、Direct Adapter、Task/Core/Store、S7/S8、Wave-2/3 evidence tooling、launchers、validators、generic `schedule.*` consumers 与 manifest 其余 18 项全部 retained/inventory；禁止以本决定扩大删除。
- 证据与判读：B1/P3-8A 合并回归 `267 passed`，runtime/auth/AgentServer `204 passed`，dedicated media `27/27`，build profiles `2/2`，production build PASS；完整 Formal Web `439/440` 的唯一失败仍是既有 P1/TTS Exit/immediate-re-enable late ACK。完整 Registry 的六个失败与 `cc420981` baseline nodeid/function digest 精确相同且发生在新增 diagnostic projection 前。combined B2 独立 review 为 `0 Critical / 0 Important / 0 Minor`。
- 重新评估条件：需要 raw/private identity 或内容进入 backend、开放 metric labels、第二 queue/worker/collector authority、外部 OTLP/持久化/SLO/retention、新 wire/schema/auth/durability/Task state、修改 Store/Core/Executor/Runtime/ACK 真相、把 synthetic Executor observation 冒充 Direct dispatch、为 checkpoint/effect/recovery/reconcile/current outbox state 宣称正式 producer、删除任何未满足 manifest Gate 的 retained 项，或把 scoped automation 冒充 P3-9/物理/完整产品验收。

## D-093 在 P3-9 前冻结完整 P3 能力代码边界

- 日期：2026-08-22
- 状态：Accepted（实现源 `b4e70efebc1f1eb499c883566263af5275a3d48e` 通过受影响 Gate 和独立 Tier-3 follow-up review；本决定关闭计划内 pre-P3-9 P3 代码边界，不把 P3-9、完整 P3 产品验收或 feature-complete 判为 PASS）。
- 控制 primitive 决定：当前 Direct profile 不实现正向 `provide_input`、`pause` 或 `resume`。`provide_input` 只有在 exact current `decision_required` seam 才进入评估，随后以 sanitized durable decision 返回 stable unsupported；`pause`/`resume` 对 nonterminal Task 返回 stable unsupported，对 terminal Task 返回 conflict。除既有 sanitized command/decision ledger 外，Task、Attempt、Event、outbox、Executor 和项目副作用必须为零。未来正向能力需要新的 primitive/capability 决定，不能由 UI、Voice、Stop、barge-in 或兼容层推断。
- Executor/profile 配置决定：正式 P3 factory 必须消费 `JIUWENSWARM_LIVE_VOICE_P3_EXECUTOR_PROFILE` 指定的一个 exact available construction candidate。当前仅接受 Direct D0 和 Direct Store-backed D2；缺失、D1 和未知 profile 在 Store/database 构造前 fail closed。D0 只声明 dispatch/status/cancel，D2 声明完整 checkpoint/recovery/effect-reconciliation 集；没有真实 D1 candidate 就不得声明 D1。launch/evidence owner 显式选择 D2，ordinary production 和 Live Voice 总开关语义不变。
- durability diagnostic producer 决定：正式 authenticated status consumer 在业务 authority 成功后，从同一个 SQLite Store snapshot 读取 current Task/Attempt event head、每类 current outbox row、verified checkpoint/effect prefix、linked recovery 和 closed reconciliation state。每条 outbox 先校验 canonical Task/Attempt/scope/executor/command-or-recovery binding；公开 record revision 使用 row-owned delivery count。Recovery 继承的 checkpoint/effect 保留 producer Attempt identity；status event-head 不一致时放弃诊断而不改写业务结果。
- privacy/observability 决定：新增 `task.adjust_outbox_observed` 和 `task.reconciliation_observed` 为 Python/TypeScript/fixture 同步的闭集事件。reconcile 只公开 `required/in_progress/pending/resolved` 低基数状态；raw audio、prompt、blocking answer、TaskResult/artifact 内容、凭据、reconciliation reason 和 raw identity 不进入 backend，metric labels 不接受高基数身份。checkpoint/effect/recovery/reconcile/current outbox producer 不成为第二 Task、Store、Executor 或 recovery authority。
- 退役决定：D-092 retirement manifest 不因本决定扩大。已退役三项保持退役，其余 18 行与 generic `schedule.*`、正式 P3-7 Panel/routes、Direct Executor、fixed media owner 和仍有消费者的兼容路径保持 retained/inventory，直至各自 replacement/oracle/feature-on/feature-off/rollback/review Gate 完成。
- 证据与判读：backend/config/durability/observability/retirement `387 passed`，Registry affected `13 passed`，cross-language observability `19 passed`，build profiles `2 passed`，production build、Ruff、compileall 和 diff check PASS。首次独立 review 的 `C0/I2/M1` 全部修复；follow-up 为 `C0/I0/M0`。这使计划内 P3 模块开发和代码收尾在 P3-9 前完成，但完整 P3 仍必须通过 P3-9 cumulative human/product Journey。
- 重新评估条件：新增真实 control primitive 或 Executor/D1 candidate；改变 D0/D2 capability matrix；要求 Store/schema migration；允许 private content/raw identity/open metric label；引入外部 telemetry/第二 authority；删除 retained manifest row；或把自动化/审查证据冒充 P3-9、物理、feature-complete、product-readiness、Production、`develop` 或 remote credit。

## D-094 P2 有界通知拉取人工验收后默认开启并退役部署开关

- 日期：2026-08-23（继承 2026-08-21 validation-branch 人工验收）
- 状态：Accepted scoped default-and-compatibility decision（用户在 validation 分支的 `4b405fca1` 上完成 feature-on 人工验收后，明确决定不长期保留仅用于 A/B、验证和快速回滚的两个 P2 notification batch 部署开关；当前集成不改变该验收边界）。
- 验收依据：三个问题的可见任务用时分别为 `10.65s`、`7.05s`、`2.78s / 3.14s / 3.14s`；语音均可播放，修复前连续出现的 `SPEECH_OPERATION_NOT_AUTHORIZED` 未复现。该结果只接受默认路径与修复效果，不是冻结语料 p50/p95，也不改变 controlled-candidate/feature-complete 状态。
- 生产默认：Integrated Web 生产 owner 固定注入 `notification_batch_size: 16`。后端 `p2.notification.next` 始终接受显式 canonical `max_notifications=2..16`；未传该字段的旧客户端继续按单条 `notification` 拉取，不要求升级或伪造 batch response。
- 配置退役：删除前端 `VITE_FEATURE_LIVE_VOICE_P2_NOTIFICATION_BATCH` 与后端 `JIUWENSWARM_LIVE_VOICE_P2_NOTIFICATION_BATCH_ENABLED`，不再由部署环境选择 P2 通知 transport mode。A/B 自动化通过依赖注入只选择 `1` 或 `16`，从而保留可重复基线而不恢复生产开关。
- Authority 与非变化：Dedicated Media 在任何 Speech authority 写入前先完整校验 exact batch/item keys、activation binding、publish sequence 与 non-tail observer barrier；任一无效项使整批保持零 partial authorization。完整 batch 通过后，每个 final 仍复用既有 observer 校验/注册才可进入 TTS。batch 上限保持 `16`，replay、zero-forbidden-effect 和 fail-closed 语义不变。Successor-ACK/TTS 原本没有此类开关且已默认启用，本决定不为它新增或清理开关。
- 回滚：默认切换验收完成后，回滚窗口不再依赖长期部署开关；若当前实现发生已证实回归，使用有边界的代码回退/修复并保留旧客户端单条兼容。该决定不授权 remote ref update。
- 证据：[P2 default-on evidence](../evidence/P2_NOTIFICATION_BATCH_DEFAULT_ON_20260821.md)。
- 重新评估条件：显式 `2..16` 无法保持严格绑定/顺序/authoritative barrier；旧客户端缺省单条路径失败；生产 `16` 在真实负载下产生有证据的 backpressure、丢序或错误授权；或固定语料证明另一有界值需要成为新产品默认。重新评估不自动恢复环境开关。

## D-095 L0 以一次完整人工验收和独立自动化延迟序列闭环

- 日期：2026-08-24。
- 状态：Accepted L0 closure execution and evidence-boundary decision（用户明确要求把下列三项作为不可拆分的剩余闭环内容，使 Main 或后续 Session 都必须完成同一组交付；本决定不把尚未运行的验收或测量记为 PASS）。
- 一次完整人工验收：在一个记录了 exact clean source、环境和配置的普通 Chrome 会话中完成固定关键旅程，而不是只说一句话。人工必须观察真实麦克风拾音、短/长播报、停顿与空白拒绝、连续回合、Tool/Task 路径、播放中 barge-in 和实际停止，并记录整组通过或失败。该会话只给功能、真实可听性和主观质量的有界信用，不产生 p50/p95。
- 自动化测量：脚本以固定语料和自动完整性 oracle 分别生成 warm 与 cold 序列，不再把逐轮人工 pass 当作数字链路样本的必要条件。Warm 先做一次不计数预热；cold 的每个样本来自一个新的受控本地 launcher epoch。每个温度至少保留 `20` 个 time-to-first-audio 有效样本和 `20` 个专用 barge-in 有效样本；失败、fallback、cancel、丢弃和不完整样本单独计数，不得进入不适用的成功百分位。
- 结果合同：sanitized 报告至少给出 profile/temperature、attempt/eligible/failure/drop counts、p50/p95 `speech_end_to_webaudio_started_ms` 和 p50/p95 `stop_to_silence_ms`，并列出 cold/warm 差异及异常分类。前者的自动端点是 WebAudio actually-started，后者的自动端点是 Browser fence-cancel completion；两者必须称为 Browser 数字链路指标。
- 非声明：一次人工验收不能把后续自动样本升级为逐轮物理确认；自动 Browser 数值也不是声压传感器测得的 physical-first-audible 或 physical-silence。没有外部声学 oracle 时，严格物理声学 p95、AEC/double-talk、跨设备/房间泛化和 release 稳定性保持开放。本决定不改变 product-readiness、feature-complete、Production 或 remote-ref 状态。
- 完成门：上述人工记录、两个温度的两类最小样本序列、sanitized 聚合、runner 适用自动化和风险相称 review 必须绑定同一个接受 source 后，L0 才可按本决定记工程测量闭环。当前 runner 若仍要求受控端点或逐轮 operator verdict，先在独立实施包中收敛该差异；不得通过自动输入 `pass`、普通 Chrome 冒充受控 provenance 或更名指标绕过门槛。
- 重新评估条件：需要严格物理声学 p95；引入参考麦克风、可信硬件/OS loopback 或原始音频保留；改变 corpus、里程碑端点、样本最低数、成功资格或 cold epoch 定义；或把该 L0 工程测量闭环升级为产品/发布 Gate。

## D-096 D-095 自动序列使用普通 Chrome 单次解锁与本地协调器

- 日期：2026-08-24。
- 状态：Accepted scoped D-095 runner re-evaluation（用户要求减少人工介入并开始实施；本决定只收敛 D-095 自动序列，不把尚未完成的真实序列或聚合记为 PASS）。
- 普通 Chrome：runner 只在已安装的普通 Google Chrome profile 中打开一个带随机 nonce 的 localhost 页面，不创建、连接、停止或清理隔离 profile，也不启用 CDP/remote-debugging。用户只需首次点击一次以满足浏览器 user-activation；后续 warm/cold 样本、专用语音打断、失败重试、服务重启和聚合由本地控制器执行。固定预录语料同时送到扬声器和仅由该 nonce 页面安装的 WebAudio capture stream；后者进入不变的正式 Media/Realtime STT/Agent/TTS 链路，避免把耳机回放、默认麦克风和 AEC 的偶然声学耦合误当自动输入。
- 固定输入与端点：13 个 case、`speech_end_to_webaudio_started_ms`/`stop_to_silence_ms` 端点、每温度每指标 20 个 eligible 目标、warm 一次非计数预热和 cold 每个 launcher epoch 最多一个 attempt 均不变。闭集 corpus 仅新增 `ordinary-chrome-prerecorded-cold|warm` 两个非物理 profile，因此摘要变为 `a51a17289edf1dbcd83da66526d2175e2f84c516240d585e9a78b814551e99d6`；旧摘要的历史证据保持原样，不能混入新序列。
- 身份、安全与恢复：loopback 协调器只绑定 `127.0.0.1`、精确 `http://localhost:5173` Origin、随机 32-hex nonce、clean source、environment/configuration/corpus 和 fresh epoch。动态标签在每轮前原子启用、结算后关闭；错标签、跨 corpus、丢弃和不完整均 fail closed。单轮失败自动单独记账并继续；完成响应丢失保持 unknown，通过同一 active job 或后续 exact session 恢复，不伪造失败或成功。服务重启可复用的前端 bundle 必须同时匹配 source HEAD、前端 tree、lockfile 和 bundle SHA-256。
- 数据与非声明：固定语料的 Provider 合成音频只驻留协调器和浏览器内存，报告和仓库不保留音频、识别文本、prompt、凭据、设备 identity 或逐轮 correlation。结果只给 Browser 数字链路信用；预录 WebAudio 输入不等于逐轮 operator confirmation，WebAudio started/fence completion 不等于 physical-first-audible/physical-silence，也不关闭真实麦克风、AEC/double-talk、设备/房间泛化或 release 稳定性。
- 重新评估条件：需要后台绕过浏览器 user-activation/权限；普通 Chrome 无法在服务重启间保留控制页；需要保留原始音频/文本；改变 D-095 case、端点、资格、样本数或 cold epoch 定义；引入非 loopback 服务、CDP/隔离 profile、外部 telemetry 或发布 Gate。

## D-097 D-095 以普通 Chrome warm 稳态基线闭环，cold 转为后续性能工作

- 日期：2026-08-25。
- 状态：Accepted L0 warm steady-state closure（用户明确确认 cold 不属于本次 L0 收尾要求，并要求以 warm 稳态基线关闭 D-095）。本决定覆盖 D-095/D-096 中把 cold/warm 两温度作为本次 L0 合取完成门的部分；不改写它们在接受时的事实，也不把未运行的 cold 样本记为通过。
- 完成边界：一次普通安装 Chrome 的 8/8 基础人工旅程、修复后按钮/语音/Stop+Exit 的权威 P2 打断结算，以及同一接受行为源上的普通 Chrome warm 自动序列共同构成本次 L0 闭环。Warm 自动序列必须保留一次不计数预热、至少 `20` 个 eligible first-audio 样本和 `20` 个 eligible dedicated barge-in 样本、独立失败/丢弃分类、sanitized p50/p95 和 exact source/environment/configuration/corpus 绑定。
- 接受结果：行为源 `ba06d9825c92602066756118dd5cac9572c22827` 在普通安装 Chrome 上完成 warm first-audio `20/20`、barge-in `20/20`，失败和丢弃均为 `0`。`speech_end_to_webaudio_started_ms` 为 p50 `4834.362 ms`、p95 `5603.215 ms`；Browser fence `stop_to_silence_ms` 的报告值为 p50/p95 `0.0/0.0 ms`，原始同源单调时钟为 p50 约 `0.1 ms`、p95 约 `0.3 ms`。这些值建立 warm Browser 数字链路基线，不是预先设定 SLO 的性能 PASS。
- cold 处置：cold fresh-launcher、cold-minus-warm 和冷启动稳定性不再阻塞本次 L0；它们转入后续性能/泛化工作，只有在未来明确需要冷启动 SLO、部署启动基线或 cold/warm 比较时重新激活。实际 warm→cold 尝试暴露了前端把当前温度 `batch_complete` 当成全序列完成、随后不再领取 cold job 的编排缺陷；该缺陷记录但不在本次收尾中修复。
- 相邻问题：一次未绑定到 eligible 样本的 Realtime STT `STREAMING_SPEECH_PROVIDER_UNAVAILABLE` 在新连接建立后恢复，不推翻 40 个 exact 样本，也不允许声称整段运行零异常。正式 Task/自然状态查询/恢复问题继续由独立已知问题记录拥有；它们不再作为本次 L0 warm 稳态测量门。
- 非声明：预录 WebAudio 输入不是逐轮人工或物理声学确认；WebAudio started/fence completion 不是 physical-first-audible/physical-silence；没有 cold 数据、cold-minus-warm、AEC/double-talk、跨设备/房间、release 稳定性或 feature-complete/product-readiness/Production 信用。原 D-095 schema 报告仍会因 cold 缺失显示 `complete=false`，不得修改原始运行产物；当前闭环由本决定和新的 sanitized warm 证据解释。
- 重新评估条件：cold 启动进入 L0、产品或发布 SLO；需要严格物理声学 p95；改变 warm corpus、端点、样本最低数或成功资格；或把本次 bounded L0 信用升级为 feature-complete、product-readiness 或 Production Gate。

## D-098 同项目串行 Direct Task 只接受精确的受管前序效果，并保持状态能力同代

- 日期：2026-09-02
- 状态：Accepted repair decision（用户根据正式 Panel 与隔离运行证据明确批准修复并要求成功后重新部署）。
- 状态能力一致性：正式 `task.status` 必须把 Core Task、Attempt、admission 和 production supported operations 绑定到同一权威代。`accepted/queued` 的 admission fingerprint、queued 标志和 dispatch ownership 任一在组合期间变化，都不得与另一代能力集拼接；读路径有界重读或返回 stable stale，且不得产生 Task、outbox、Executor、文件、通知或音频副作用。D-088 语义不变：从未 claim/deliver 的初始队列可 update；busy/capacity defer 后只可 reprioritize；已经 claim/take-over 或 running 后两者均不可伪造为可用。
- 受管项目基线：当前 Direct D2 profile 可在一个精确 authenticated scope/project 内，把 clean Git tree 或“最新 terminal/completed Direct attempt 的已结算 journal expected-tree”作为下一次串行 attempt 的 admissible baseline。受管证明必须同时绑定 canonical Task/Attempt completed truth、相同 scope、相同 project root/HEAD、相同 spec/attempt、完整 Direct journal terminal/effect 状态和当前 exact tree/support fingerprint；缺一即按 dirty/changed target fail closed。下一 attempt 仍在隔离 worktree 中从该精确基线执行，并在 apply 前做 optimistic exact compare。
- 安全边界：该决定不把任意 dirty worktree 变成合法输入，不接受人工 tracked/untracked 改动、changed HEAD、unsafe link、foreign scope/project、nonterminal 或 failed/cancelled/interrupted/unknown attempt、cleanup/effect unknown，也不自动 commit/stash/reset/clean 或回滚用户文件。串行后继以实际 dispatch 时已经验证的前序 completed tree 为输入；并发覆盖或 apply-time 漂移仍冲突且零部分应用。
- 范围与证据：这是 Task authority + Direct D2 durability 的 Tier-3 修复；允许修改 production projection、authenticated project baseline reader、Direct journal reader及其自动化，不新增 SQLite schema、canonical lifecycle state、Executor profile、第二 authority、D1 或正向 `provide_input/pause/resume`。必须覆盖 P/N/B/S/T/C/R/I/F/K/X 的适用维度、zero forbidden effects、reopen/restart、真实 Direct file-Tool seam、正式 Web 投影和 clean isolated redeployment；完成前不恢复产品候选 PASS。
- 重新评估条件：需要跨 scope/project 接受效果、接受非 Direct/非 completed/unknown effect、合并任意用户脏改、自动 Git history/worktree mutation、schema migration、新 canonical state/Executor profile/primitive，或无法在现有 Store+journal 双重事实下证明同项目串行安全。

## D-099 异步确认绑定稳定意图，attempt 初始化绑定 seed 后基线

- 日期：2026-09-02
- 状态：Accepted root repair decision（用户在第二次真实多 Task 验收暴露下一层失败后，明确要求先定位共同根因，再批准按根因修复并重新部署）。
- 确认合同：material Task confirmation 绑定 principal/scope、origin、command、operation、精确 `task_id`、精确 `attempt_id`、参数、capability、context 和 model；完整可见 Task 集合及其 admission/event/result 等运行时快照只是签发与消费时各自的观测，不进入稳定 intent fingerprint。无关 Task 的创建、进度或终态以及同一 queued attempt 的合法 admission 重验不得使确认失效。消费前仍须从当前 Store 重解目标与策略；目标 attempt、capability、context、model、operation 或参数变化必须拒绝。
- 并发安全：放宽外层集合快照不放宽 Core mutation。最终调用以最新 canonical target 构造 precondition，`task.reprioritize` 继续在 SQLite 同一事务内校验精确 attempt/event head、accepted/unclaimed pending dispatch、无 cancel/fence/reconciliation 冲突；若 claim/running/terminal 或并发命令先发生，则返回 state/stale conflict 且零业务副作用。该决定不允许确认跨 retry attempt，也不复用已消费确认。
- 隔离基线：Direct attempt 同时维护两种不同事实：dispatch 时目标项目的原始 optimistic baseline，以及受信任 seed 将该 baseline 复制并 staged 后的隔离 baseline。`git add -A` 导致的 untracked→staged 表示变化是 seed 的预期内部变化，不是 Agent 副作用；attempt Agent 初始化后必须与 seed 后 tree/support/HEAD 比较。最终 patch 仍只包含 Agent 相对 seed 的变化，并仅在目标仍匹配原始 baseline 时应用。
- 风险与证据：这是 confirmation authority + Direct D2 isolated execution 的 Tier-3 修复；自动化必须覆盖确认期间无关 Task 漂移、queued reprioritize 真正 applied、目标 attempt/config drift 拒绝、前一 Task 留下 untracked 结果后后一 Task 完成，以及真实 initializer 写入仍 fail closed。保留现有确认单次消费、跨 scope/target 拒绝、apply-time drift、unsafe link、cleanup/restart 和零副作用负向合同。
- 明确排除：不改变项目 `exclusive` 串行、不增加抢占或自动重排、不开放 `provide_input/pause/resume`、不允许 running update/reprioritize、不接受任意用户脏改、不新增 SQLite schema/Task state/Executor profile/第二 authority，也不赋予本地部署产品或 Production 通过信用。
- 重新评估条件：需要确认跨 attempt/retry、按名称而非冻结 task identity 消费、允许 capability/context/model 漂移、移除 Store 原子 precondition、改变 seed staging/patch 语义，或引入 schema/公开协议迁移。
