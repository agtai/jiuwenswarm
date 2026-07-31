# Live Voice 当前状态

- 最后更新：2026-07-31
- 工作分支：`hx/0731_live_voice_ux`
- 远端跟踪：`agtai/hx/0731_live_voice_ux`
- 建立方案时的代码基线：`7b69fdeb`
- 当前里程碑：D0 Prototype / 两周纵向 Demo
- 实现状态：尚未开始；完整方案、Demo 方案和接续机制已经固化到仓库

## 当前目标

先完成一条真实的 Live Voice 纵向链路：用户通过语音调用现有 JiuwenSwarm Agent 和工具，听到真实结果，并能在 Agent 工作或朗读时打断、补充和纠正。

当前目标不是只做听写/朗读，也不是在两周内完成生产级实时媒体和通用 Task Control。

## 已完成

- 完整目标方案已保存为 `FULL_SOLUTION_2026-07-30.md`。
- 两周 Demo 的范围、与完整版区别、Hardcode、日程和验收已保存为 `TWO_WEEK_DEMO.md`。
- 已建立 `DECISIONS.md`，记录关键取舍。
- 已确认仓库可复用能力：
  - `useSpeech.ts` 已有 Browser STT/TTS；
  - `InputArea.tsx` 已有部分语音输入和自动提交骨架，但 UI/指针交互被注释；
  - `useWebSocket.ts` 已有 `chat.send`、`supplement` 和流式回复；
  - `stopAllTts()` 可立即停止本地声音；
  - Gateway 的 supplement 路径可取消旧生成并接收新要求；
  - `schedule.run/status/cancel` 可作为可选的受限后台任务演示。
- 已确认当前服务端 `tts.synthesize` 没有注册，Demo 主线不依赖它。

## 正在进行

目前没有代码实现正在进行。下一次会话应从 D1 真机语音 Spike 开始。

## 下一步

1. 在目标 Windows 演示机上测试 Chrome、Edge、WebView2 的麦克风权限、`zh-CN` SpeechRecognition、中文 SpeechSynthesis 和停止延迟。
2. 当天决定正式演示入口：Desktop/WebView2、Web 浏览器，或单一云 Speech Provider fallback。
3. 实现带 feature flag 的最小 `LiveVoiceDemo` UI 和状态机。
4. 打通 final transcript → 真实 `chat.send` → Agent/Tool → 回答 → 自动朗读。

详细排期和退出条件见 `TWO_WEEK_DEMO.md`。

## 当前未开始

- Live Voice UI、功能开关和状态机。
- final transcript 的唯一提交与重复保护。
- Agent 回复自动朗读和 TTS 队列。
- 本地 `responseEpoch`。
- 插话及 supplement 接线。
- 真机权限、错误和稳定性验证。
- 可选后台任务体验。

## 已知风险

- Web Speech API 在目标 WebView2 中的实际支持和权限持久性尚未真机确认。
- Windows Desktop 启动流程可能清理 WebView storage，导致麦克风权限反复申请。
- 浏览器 TTS 播放时继续监听可能产生自回声；Demo 预设使用耳机。
- 当前 `useSpeechSynthesis.speak()` 每次调用会先取消上一次播放，不能直接对每个 token 调用；需要整段朗读或小型句子 FIFO。
- Agent 流式 delta、final 和 supplement 之间的迟到输出需要本地 epoch 防护。

## 开放问题

- D1 实测后，演示默认使用 Desktop 还是浏览器？
- Browser Speech 是否稳定到足以作为主 Demo，还是需要 Azure Speech fallback？
- D4 先整段朗读还是直接做句子 FIFO？默认策略是先整段，稳定后升级。
- D7 是否提前通过，从而允许增加后台任务 stretch？

## 验证记录

| 日期 | 验证 | 结果 |
|---|---|---|
| 2026-07-31 | 只读检查现有 STT/TTS、Chat、supplement、TTS handler 和 schedule 接口 | 确认可以复用；尚未运行真机语音 E2E |

后续每次验证应记录：运行环境、命令或操作步骤、结果、失败原因和关联提交。

## 接手者注意事项

- 开始工作前先执行 `git status --short --branch`，确认位于 `hx/0731_live_voice_ux` 且没有混入其他功能的未提交修改。
- 不要把另一 worktree 或其他分支的修改带入本分支。
- 不要先实现 WebRTC、完整媒体协议或 Task Core；先完成 D1–D4 的真实 Agent 语音闭环。
- partial transcript 绝不能触发 Agent、Tool 或 Task。
- 插话时必须先本地停止声音，再处理服务端取消或补充。
- 任何新增 shortcut 都必须更新 `TWO_WEEK_DEMO.md` 的 Shortcut Ledger。
- 完成实质性工作后，在同一提交或紧邻提交中更新本文件并推送远端。
