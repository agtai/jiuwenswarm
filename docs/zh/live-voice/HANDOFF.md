# Live Voice 跨机器交接快照

- 快照日期：2026-08-01
- 开发分支：`hx/0731_live_voice_ux`
- 共享远端：`agtai`（`https://github.com/agtai/jiuwenswarm.git`）
- V0 核心实现提交：`346f802a`；本次路线/验收文档更新前的已推送快照：`21139d84fab3be88bbb89f7bfa25df6913b193b5`
- 权威恢复点：pull 后的 `agtai/hx/0731_live_voice_ux` 分支 tip；预期本地/远端差异 `0 0`、工作区干净
- 当前阶段：V0 Candidate 已提交并推送，但完整真机 Gate 尚未通过，因此还不是 V0 Released / 已冻结
- 当前目标：执行 [V0_ACCEPTANCE.md](V0_ACCEPTANCE.md)，把已真实贯通一次的纵向主链推进到可重复、可打断、可连续运行的 V0 放行状态

## 接手后先做什么

1. `git fetch agtai`，切换并更新 `hx/0731_live_voice_ux`。
2. 依次阅读 [README.md](README.md)、本文件、[STATUS.md](STATUS.md)、[TWO_WEEK_DEMO.md](TWO_WEEK_DEMO.md)、[V0_ACCEPTANCE.md](V0_ACCEPTANCE.md) 和 [DECISIONS.md](DECISIONS.md)。
3. 准备演示机时严格执行 [E2E_RUNBOOK.md](E2E_RUNBOOK.md)，新机器必须从 lockfile 重建依赖，不复制 `.venv` 或 `node_modules`。
4. 当前第一优先级是连续 10 Turn、分阶段 10 次打断、soak、连续 3 次主演示和冷环境恢复，不是继续添加 Team、后台任务或新架构。

本目录是 Git 中的接续入口。不要依赖旧对话、未提交文件或某台机器的 `.codex` / `.agent` 目录恢复项目事实。

## 当前已经能做什么

- Live Voice 只在 Agent 模式开放；final transcript 在 Agent processing 时复用真实 `supplement`，空闲或只剩 TTS 时复用普通 `chat.send`，interim 只有显示副作用。
- Web Speech 的浏览器实例自然结束不会直接结束用户 Turn；约 4 秒早退可以在同一逻辑 capture 中续启并合并尾段，手动停止不会被 retry 复活。
- 初始静默窗口固定 8 秒，有识别结果后的结束语音窗口为 2.2 秒。
- `new` session promotion 分两次渲染时会保留 Live Voice；普通 session 切换仍退出并清理。
- 用户 echo 先于 `processing=true` 到达时，不会提前重新开麦。
- 完整 assistant 回答经过无 500 字截断的 Live Voice 清洗后，以约 220–300 字分片进入 TTS FIFO。
- 朗读副本会把路径、分支、斜杠、下划线、缩写和字母数字转换为可听形式，聊天页面显示文本不变。
- 每个分片用 `${message.id}:${chunkIndex}` 去重，并受同一 `responseEpoch` 控制；打断、退出和新 Turn 会让旧队列失效。
- Live Voice 拥有浏览器 TTS 时，进程内 owner/revision 会阻止旧服务端音频与之双播；历史消息手动朗读也会在播放前检查 owner。
- supplement ACK 前隔离旧 delta/final/reasoning/media/tool_call/tool_update，并暂存旧流的 `processing=false` 停止边缘。

## 2026-08-01 已完成的验证

### 自动化

- Live Voice 纯逻辑：**47/47**（core 9、turn lifecycle 6、TTS 10、message gate 7、quarantine 6、speech lifecycle 7、TTS owner 2）。
- 相关既有回归：**22/22**（stream delta 7、session creation 8、chat store/settle 7）。
- 全前端 TypeScript、Vite production build（4490 modules）、Python `ruff` 和 `git diff --check` 通过。

### 真实固定环境

- Windows；Chrome `150.0.7871.187`；Jabra EVOLVE 30 II；`zh-CN`；Node.js `24.14.0`；Python `3.12.9`；模型标签 `deepseek-v4-flash`。
- Python 本轮临时复用主仓现有 `.venv`；这是本机临时措施，不是恢复规范。
- 文字强制 Terminal Tool smoke 成功。
- 麦克风完整识别“调用终端查看当前分支”；新会话 promotion 保持 Live Voice。
- `T+1.050s` Agent working；真实调用 `git branch --show-current`，结果为 `hx/0731_live_voice_ux`；`T+7.420s` Agent 完成；`T+8.922s` 开始 TTS；`T+17.215s` 完整朗读结束并回 Listening。
- 用户确认完整听到分支名中的斜杠、数字和下划线。
- 静默测试的 UI 轮询从点击 Retry 后计时；`T+7.293s` 仍为 Listening，`T+7.816s` 显示 `no-speech`，与约 8 秒的配置窗口一致。
- 自动回听又接收了 2 个 follow-up，但 `git` 被识别成“地图”或“史记”，只能证明循环继续，不能计为准确率验收通过。

详细非敏感证据和启动方式见 [E2E_RUNBOOK.md](E2E_RUNBOOK.md)。

## 仍未完成：当前唯一主线

- 10 个准确语音 Turn，重复提交为 0。
- 10 次用户可感知打断：thinking 3 次、tool 4 次必须走真实 supplement；speaking 3 次必须立即停声并恰好走一次普通 `chat.send`。三类分别记数，旧声音恢复 0 次，并检查旧工具 UI、迟到 result、warning 和副作用。
- 连续 20 分钟或 20 Turn 无需刷新。
- 主演示脚本连续成功 3 次。
- 在独立环境从 `uv.lock` / `package-lock.json` 重建并复测，不依赖主仓 `.venv`。

任何一项未通过，都不能写成“Demo 已完成”。当前真实主链成功一次是关键进展，但不是放行替代品。

## 量化进度口径

| 维度 | 完成度 | 含义 |
|---|---:|---|
| 代码实现 | 约 97% | 主链、识别生命周期、分片朗读、TTS 单一所有权、Demo 隔离和自动化基本完成 |
| 整体 Demo | 约 90% | 真实 Speech → Agent → Tool → Speech 已成功一次，重复性与打断闸门未完成 |
| 上台成熟度 | 约 78% | 固定环境和首条时序证据已建立，仍缺 10 Turn、10 次打断、soak 和连续彩排 |

这些数字是项目判断，不是测试覆盖率；后续真实失败必须如实下调。

## 当前最重要的已知风险

### Web Speech 技术词准确率

中文句子中的 `git` 在连续回听中被误识别为“地图”或“史记”。主链没有断，但请求语义会偏移。先用固定口令和真机样本量化；若仍不稳定，再按既有 Day 1/Day 2 闸门评估单一 Speech Provider fallback。

### supplement 仍不是端到端 fence

前端现在可以隐藏更多旧 UI 事件并保持 processing 状态，但 Gateway 的 supplement ACK 仍早于 AgentServer cancel/replacement 完成。`chat.tool_result` 与真实工具副作用没有 generation ID，旧副作用无法由前端可靠撤销或归属。真实 10 次打断必须专项观察，不能把 ACK 解释成“旧 Agent 和工具已确定停止”。

### speaking 打断不是 supplement

当前回答只有在 Agent 完成后才进入浏览器 TTS。因此 speaking 时重新开麦会立即停止本地声音，但新 final 通常发生在 `processing=false`，实际是普通 `chat.send`。它能验证“停声并修改下一轮”，不能证明服务端 Agent cancel。验收必须按 [V0_ACCEPTANCE.md](V0_ACCEPTANCE.md) 分开记录。

### 固定环境仍有机器私有状态

模型配置、浏览器权限、Chrome Speech 服务、硬件和网络不会进入 Git。本轮复用主仓 `.venv` 也只是临时便利；跨机器必须按运行手册重建并重新验收。

## 不要重复做或提前做的事情

- 不要另写语音专用 Agent 协议、发送 partial transcript、写死 Agent 答案或工具结果。
- 不要把本地 epoch、quarantine、TTS owner/revision 描述成生产 generation fence。
- 不要在稳定性闸门通过前实现 Team、后台任务 stretch、多语言、WebView2 或全双工媒体。
- 不要另建一套覆盖全部功能、依赖模拟状态或 hardcode 结果的 UX 原型；V1/V2/V3 在同一真实工程路径上累计替换 V0 shortcut。
- 不要提交 API key、Slack token、用户配置、浏览器 profile、`.venv`、`node_modules` 或本机绝对路径。

## 每次继续工作后的交接要求

- 更新 [STATUS.md](STATUS.md) 的真实结果、失败、时序和下一步。
- 技术选择变化时更新 [DECISIONS.md](DECISIONS.md)；新增临时简化时更新 [TWO_WEEK_DEMO.md](TWO_WEEK_DEMO.md) 的 Shortcut Ledger。
- 提交并推送到 `agtai/hx/0731_live_voice_ux`；只存在本机或对话中的信息不算交接完成。
