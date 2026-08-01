# Live Voice 当前状态

- 最后更新：2026-08-01
- 工作分支：`hx/0731_live_voice_ux`
- 远端跟踪：`agtai/hx/0731_live_voice_ux`
- 建立方案时的代码基线：`7b69fdeb`
- V0 核心实现提交：`346f802a`；本次路线/验收文档更新前的已推送快照：`21139d84fab3be88bbb89f7bfa25df6913b193b5`
- 当前里程碑：两周 V0 Vertical Slice Candidate
- 实现状态：真实“麦克风 → Agent → Terminal Tool → 完整回答 → 浏览器 TTS → 自动回听”主链已在固定 Windows/Chrome 环境成功跑通一次；[V0_ACCEPTANCE.md](V0_ACCEPTANCE.md) 已定义完整 Gate，但稳定性、分阶段打断和跨环境放行尚未执行完

跨机器恢复先读 [HANDOFF.md](HANDOFF.md)；启动和固定环境按 [E2E_RUNBOOK.md](E2E_RUNBOOK.md) 执行；V0 是否放行以 [V0_ACCEPTANCE.md](V0_ACCEPTANCE.md) 为准。

当前量化判断：代码实现约 **97%**，整体 Demo 约 **90%**，上台成熟度约 **78%**。提升来自真实麦克风、真实 Agent/Tool、完整 TTS 和自动回听首次贯通，以及 47 项 Live Voice 自动化全部通过；尚未完成连续 10 Turn、分阶段 10 次打断、soak 和连续 3 次主演示，因此不能称为 Demo 已放行。

## 当前结论

核心产品命题已从“代码路径推断可行”推进到“固定真机上实际成立”：用户说出“调用终端查看当前分支”，Chrome 产生完整 final，新会话 promotion 没有让 Live Voice 退出，Agent 真实调用 `git branch --show-current`，工具返回 `hx/0731_live_voice_ux`，完整回答从 Jabra 耳机朗读，随后自动回到 Listening。用户确认斜杠、数字和下划线组成的分支名也完整听到。

这次成功证明了受控 Demo 的主链和感知效果，但只是一次主链证据，不等于稳定性放行。之后又成功进入两轮回听，说明循环可以继续；同时 Web Speech 把 `git` 识别为“地图”或“史记”，暴露出中文技术词准确率风险。真实 supplement 打断、speaking 本地停声、工具副作用隔离和长时运行仍需专项验证。

已接受新的累计路线：不另建覆盖全部功能的模拟 UX 原型；V0 之后依次推进 V1/P1 Product Alpha、V2/P2 Realtime Alpha、V3α/P3α Task Alpha、V3 Full Capability Beta，最后进入 RC/Production hardening。各版保留前版能力并用正式实现替换 shortcut；共享契约冻结后可部分并行。详细见 `DECISIONS.md` 的 D-018。

## 本轮实现与修复

### 语音识别和 Turn 生命周期

- 修复 `new` session promotion 分两次 React 渲染到达时，promotion signal 被提前消费并导致 Live Voice 退出的问题。
- 用户消息本地 echo 早于 `processing=true` 时，不再误判为“无可朗读回答”并提前重新开麦。
- 将一个用户 capture 与单个浏览器 SpeechRecognition 实例解耦：Chrome 约 4 秒自然结束时可在同一逻辑 capture 内续启，final/interim 尾段合并后只提交一次。
- 区分 8 秒初始静默窗口和有结果后的 2.2 秒结束语音窗口；浏览器初始 `no-speech` 可在阈值内重试，手动停止或终止错误不会被错误重启。
- 修复 manual stop 与自动 retry 的竞态，旧识别实例和迟到回调继续受 generation 隔离。

### 回答朗读

- 完整 assistant 消息不再被普通 TTS 的 500 字默认上限静默截断；Live Voice 先完整清洗，再以约 220–300 字按中英文句末优先分片，超长句硬切并保持 FIFO。
- 显示文本保持不变，只修改朗读副本：路径、分支、下划线、斜杠、缩写和连续字母数字转换成 `zh-CN` 系统音色可稳定读出的形式。
- 分片 key 使用 `${message.id}:${chunkIndex}`，继续复用现有 `responseEpoch`；打断、退出或新 Turn 会使整条旧队列和迟到回调失效。
- Live Voice 启用时取得进程内 TTS 所有权；旧的服务端 `tts.synthesize` 路径在请求前和音频返回后都检查 ownership revision，历史消息手动朗读也在播放前检查 owner；启用瞬间的全局 stop 会终止已有浏览器或生成音频。

### supplement 隔离

- ACK 前 quarantine 现在除旧 delta/final/reasoning/media 外，也隔离旧 `chat.tool_call` 和 `chat.tool_update`。
- 旧流关闭产生的短暂 `processing=false` 会在 barrier 内暂存，避免替代回答尚未开始时 Live Voice 提前结束 Turn；请求失败时会恢复被暂存的停止边缘。
- Gateway 不再静默吞掉 Agent cancel 异常，会记录可诊断 warning 后继续 replacement。

这些仍是 Demo 级本地防线。Gateway 的 supplement ACK 目前早于 AgentServer cancel 和 replacement 入队完成，真实工具副作用也没有 generation fence；前端隔离不能证明旧副作用已取消。

## 验证记录

### 自动化和静态检查

| 日期 | 验证 | 结果 |
|---|---|---|
| 2026-08-01 | Live Voice 纯逻辑 | **47/47 通过**：core 9、turn lifecycle 6、TTS text/chunking 10、message gate 7、supplement quarantine 6、speech lifecycle 7、TTS ownership 2 |
| 2026-08-01 | 相关既有回归 | **22/22 通过**：stream delta 7、session creation 8、chat store/settle 7 |
| 2026-08-01 | 全前端 TypeScript | `tsc --noEmit` 通过 |
| 2026-08-01 | Vite production build | 通过，**4490 modules** |
| 2026-08-01 | Python 与工作树检查 | `ruff`、`git diff --check` 通过 |

### 固定环境真实 E2E

- 环境：Windows、Chrome `150.0.7871.187`、Jabra EVOLVE 30 II、`zh-CN`、Node.js `24.14.0`、Python `3.12.9`、模型标签 `deepseek-v4-flash`。
- 本轮 Python 临时复用主仓现有 `.venv`；这是本机便利措施，不是跨机器恢复方案。新机器仍必须按 `uv.lock` 创建自己的 `.venv`。
- 文字强制工具 smoke 成功，证明模型、项目注册、Agent 和 Terminal Tool 可用。
- 真实麦克风完整识别“调用终端查看当前分支”，final 只进入一个逻辑 Turn；`new` session promotion 后 Live Voice 保持激活。
- 本轮计时证据：`T+1.050s` 进入 Agent working；真实工具执行 `git branch --show-current` 并返回 `hx/0731_live_voice_ux`；`T+7.420s` Agent 完成；`T+8.922s` 进入 TTS；`T+17.215s` 完整朗读结束并回到 Listening。
- 用户确认完整听到技术标识符中的斜杠、数字和下划线。
- 初始静默测试的 UI 轮询从点击 Retry 后计时，而不是从 Recognition `onstart` 精确计时；`T+7.293s` 仍为 Listening，`T+7.816s` 进入可见 `no-speech`，与约 8 秒的配置窗口一致，也没有被 Chrome 更早的自然结束误伤。
- 自动回听又接收了 2 个 follow-up，证明循环继续；但 Web Speech 把 `git` 误识别为“地图”或“史记”，尚不能据此记为 3 个准确语音 Turn。

## 尚未完成与不能宣称的内容

- 尚未完成连续 10 个准确语音 Turn、分阶段 10 次用户可感知打断、20 分钟或 20 Turn 稳定性，以及主演示脚本连续成功 3 次。
- 10 次打断必须拆分：thinking 3 次和 tool 4 次验证真实 `supplement`；speaking 3 次验证立即停声后普通 `chat.send`。当前没有任何一组可以写成已通过，也不能把 speaking 样本计入 supplement。
- 尚未测量并通过 speaking 本地静音目标 `<300ms` 和全部样本旧声音恢复 0 次；本轮主链没有证明真实 supplement 的 cancel/replacement 顺序可靠。
- supplement P1 协议风险仍在：ACK 早于 AgentServer cancel/replacement 完成；`chat.tool_result` 和真实工具副作用缺少 generation ID，前端不能可靠 fence。
- Web Speech 对中文句子中的英文技术词准确率不稳定，需要继续真机测试口令、说法和必要的 Provider fallback。
- Desktop/WebView2、Team、多语言、全双工/AEC、断线恢复和服务端 streaming TTS 未验证，也不属于本轮已经完成的能力。
- 当前固定演示环境可用不等于跨环境兼容；模型、Chrome Speech 服务、麦克风权限和网络仍是机器私有条件。

## 下一步

1. 以 [V0_ACCEPTANCE.md](V0_ACCEPTANCE.md) 为唯一放行清单，先固定 candidate SHA、干净工作区和环境身份，复跑自动化与文字 Tool smoke。
2. 在相同固定环境完成 10 个准确语音 Turn；记录每轮识别文本、唯一提交、Agent/Tool 结果、TTS 和自动回听状态，专项统计技术词误识别。
3. 完成 thinking 3 次、tool 4 次真实 supplement 和 speaking 3 次本地停声/普通发送；核对实际路由、静音、旧 tool UI、`chat.tool_result`、warning、副作用和旧声音恢复。
4. 完成 20 分钟或 20 Turn soak，并把主演示脚本连续跑通 3 次；失败必须保留复现时间线，不用成功录像替代失败记录。
5. 在新的独立环境按 lockfile 重建依赖，并用全新 Codex session 完成无旧对话理解测试；机器私有模型配置和麦克风权限仍从受控渠道注入。
6. V0 Gate 全部通过后才标记 Released/冻结并进入 V1/P1；核心稳定前不开始 Team、后台任务 stretch 或全双工新架构。

## 接手者注意事项

- 开始工作前执行 `git status --short --branch`，确认位于 `hx/0731_live_voice_ux`，并区分本轮已知修改与意外文件。
- 真实环境、服务拓扑、无密钥配置和时序证据见 [E2E_RUNBOOK.md](E2E_RUNBOOK.md)。
- partial/interim transcript 绝不能触发 Agent、Tool 或 Task；浏览器重启只能延续同一个逻辑 capture。
- 插话或退出必须先本地停播；不要把 ACK quarantine、TTS ownership 或本地 epoch 描述成生产一致性协议。
- processing 中 final 才是 supplement；只剩 TTS 时是停声后的普通下一 Turn，不得混用验收计数。
- 真实主链已通过一次，但完整放行闸门未通过；只能称为 V0 Candidate，不得写成“Live Voice Demo 已完成/已冻结”。
