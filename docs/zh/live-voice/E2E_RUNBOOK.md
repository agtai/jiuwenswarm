# Live Voice 固定环境与真实 E2E 运行手册

本手册用于把“代码可以构建”推进到“固定演示机上真实可演示”。它固定可复现边界，但不会把密钥、个人配置或硬件状态写进 Git。

本文是环境、依赖、服务启动和健康检查的权威入口。V0 的固定语料、分阶段打断、放行 Gate 和证据汇总以 [V0_ACCEPTANCE.md](V0_ACCEPTANCE.md) 为准；现场展示话术以 [DEMO_SHOWCASE.md](DEMO_SHOWCASE.md) 为准。

## 1. 为什么必须固定环境

Live Voice 同时依赖浏览器语音能力、麦克风权限、音频设备、外部模型 Provider、网络、后端配置和前后端依赖。只固定源码不能保证另一台机器得到相同结果。

因此分三层固定：

| 层 | 固定方式 | 是否进 Git |
|---|---|---|
| 源码和方案 | 分支、commit、本文档 | 是 |
| Python/Node 依赖 | `uv.lock`、`package-lock.json` | 是 |
| 密钥、浏览器权限、硬件和网络 | 演示机检查清单与无密钥证据 | 否，只记录结果 |

## 2. 推荐的 Demo 基线

- Windows 10/11 x64；最终彩排和演示使用同一台机器。
- Chrome/Chromium 107 或更高；推荐固定当前 Chrome stable 的确切版本，并在最终彩排到演示之间暂停升级。
- Python 3.12.9。仓库允许 `>=3.11,<3.14`，该确切版本已用于当前开发验证。
- Node.js 24.14.0。仓库最低要求 Node 18，该确切版本已通过当前前端测试和构建。
- 中文 `zh-CN`、默认麦克风、耳机、单用户、单浏览器窗口、稳定网络。
- 网络必须同时能访问模型 Provider 和浏览器 Web Speech 所需服务。

2026-08-01 首次真实贯通使用的已知可用组合：

| 项 | 实测值 |
|---|---|
| 浏览器 | Chrome `150.0.7871.187` |
| 音频设备 | Jabra EVOLVE 30 II |
| 语言 | `zh-CN` |
| Node.js | `24.14.0` |
| Python | `3.12.9` |
| 模型标签 | `deepseek-v4-flash` |

这组值是当前证据基线，不是兼容性承诺。模型 key/base、浏览器 profile、Windows 用户目录和其他机器私有配置不得写入 Git。

这不是正式兼容性矩阵；它是受控 Demo 的可复现范围。

## 3. 获取代码与固定依赖

```powershell
git clone --origin agtai https://github.com/agtai/jiuwenswarm.git
Set-Location jiuwenswarm
git fetch agtai
git switch --track agtai/hx/0731_live_voice_ux
git status --short --branch
```

如果仓库已经通过普通 `git clone` 获取、远端名为 `origin`，使用 `origin/hx/0731_live_voice_ux`，或将它重命名为 `agtai`。验收前记录 `git rev-parse HEAD`，工作区必须无意外修改。

Python 依赖以根目录 `uv.lock` 为准：

```powershell
uv sync --python 3.12.9 --frozen
& .\.venv\Scripts\python.exe --version
```

前端依赖以 `package-lock.json` 为准：

```powershell
Set-Location jiuwenswarm\channels\web\frontend
npm ci
node --version
npm --version
Set-Location ..\..\..\..
```

不要复制另一台机器的 `.venv` 或 `node_modules`；它们不是跨机器交接物。

2026-08-01 的首次 E2E 为了快速验证，临时复用了同一机器主仓已经存在的 Python `.venv`。这只能证明该机器组合可运行，不能作为恢复步骤；新机器和最终彩排环境仍必须执行上面的 `uv sync --frozen`，并重新跑完整验收。

## 4. 本机配置检查

后端需要一个可用的默认模型配置，至少包括非空的 API base、API key、model name 和 client/provider。只检查“是否存在/是否可用”，不要把值贴到日志、文档或 commit 中。

推荐从 Web UI 的 **Settings → Configuration → Model Configuration** 注入或选择默认模型；高级用户也可以使用机器私有的用户工作区 `config/config.yaml` / `.env`。验收只在 UI 中确认必填项非空或已掩码，并通过下一节的文字 Tool smoke 验证实际可用；不要让终端、Codex 或截图打印完整配置。任一必填项缺失时停止外部模型和真实语音验收，从受控渠道补齐后再继续。

还要检查：

- 演示用仓库目录已在 JiuwenSwarm 中注册为 code project。
- 模型 Provider 的 HTTPS endpoint 可从演示机访问。
- Chrome 已允许当前 localhost 站点使用麦克风。
- 默认麦克风和耳机正确，系统输入电平可见。
- 端口 `18092`、`19000`、`19001`、`5173` 未被其他进程占用。

用户工作区配置和 `.env` 是机器私有状态。不得提交完整配置、API key、Slack token 或其他凭据。

## 5. 服务拓扑与健康判据

```text
Chrome http://localhost:5173
  → 同源 ws://localhost:5173/ws
  → Vite proxy
  → WebChannel ws://127.0.0.1:19000/ws
  → Gateway
  → AgentServer ws://127.0.0.1:18092
  → 外部模型 Provider / 本地工具
```

默认端口：

- AgentServer：`AGENT_SERVER_PORT=18092`
- WebChannel：`WEB_PORT=19000`，路径 `/ws`
- Gateway：`GATEWAY_PORT=19001`，路径 `/acp`、`/tui`
- Vite：`FRONTEND_PORT=5173`

`19001` 是 WebSocket 端口，没有可依赖的 HTTP `/health`。浏览器 WebSocket 实际收到 `connection.ack` 才说明 Gateway 已连接到就绪的 AgentServer；仅仅“端口正在监听”不算后端健康。

## 6. 启动后端

### 方案 A：显式临时关闭外部 IM channel

如果用户配置中 Slack 或其他 IM channel 已启用，完整启动会尝试外部连接。演示前先备份用户配置，显式临时关闭无关 channel，演示后恢复。不要提交这个配置，也不要在进程运行中热改配置。

然后按仓库正常方式启动：

```powershell
& .\.venv\Scripts\python.exe -m jiuwenswarm.app
```

注意：该命令启动后端服务，但不启动 Vite 前端。

### 方案 B：仅本次 E2E 的进程内 Slack 屏蔽

当不希望修改用户配置时，可以用两个终端启动拆分服务。这个方案只用于临时 E2E，不是产品启动方式；配置热加载或设置修改可能绕过屏蔽。

终端 1：

```powershell
& .\.venv\Scripts\python.exe -m jiuwenswarm.server.app_agentserver
```

终端 2：

```powershell
& .\.venv\Scripts\python.exe -c "import jiuwenswarm.common.config as c; real=c.get_config; c.get_config=lambda:(lambda x:(x.setdefault('channels',{}).setdefault('slack',{}).__setitem__('enabled',False),x)[1])(real()); import jiuwenswarm.gateway.app_gateway as g; g.main()"
```

这只在 Gateway 进程内把 Slack 设为禁用，避免为 Live Voice 验证产生无关外部连接。若还有其他已启用 IM channel，应使用方案 A 明确关闭。

## 7. 启动前端

新终端：

```powershell
Set-Location jiuwenswarm\channels\web\frontend
npm run dev
```

打开 `http://localhost:5173`。确认浏览器连接成功并在开发者工具 WebSocket 帧中看到 `connection.ack`。在 UI 中选择或创建指向当前仓库目录的 code project，进入 Agent 模式。

V0 验收必须使用默认配置。启动前显式清除两个 Post-V0 开关，避免把增量行为误算进 V0 Gate：

```powershell
Remove-Item Env:VITE_FEATURE_LIVE_VOICE_STREAMING_SPEECH -ErrorAction SilentlyContinue
Remove-Item Env:VITE_FEATURE_LIVE_VOICE_TASK_DEMO -ErrorAction SilentlyContinue
```

恢复新开发后，单独验证稳定句预读时才在启动 Vite 的同一终端设置：

```powershell
$env:VITE_FEATURE_LIVE_VOICE_STREAMING_SPEECH = 'true'
npm run dev
```

该开关只启用 chatStore 稳定句预读，不等于启用 token/audio streaming TTS。首次验证时关闭 cron、proactive response 和其他可能向同一 Session 注入 assistant 输出的来源；当前服务端事件没有 response/generation provenance，并发输出可能归错 Turn。若 processing 已停止、预读队列已经 drain 但权威 `chat.final` 一直缺失，当前实现等待 10 秒后废弃该 epoch 并显示可 Retry 错误；不得把 provisional 当作 final，也不得补播或重放未确认文本。开关开启时，speaking 可能与 Agent processing 重叠；打断样本必须按新 final 到达时的实际 processing 状态分类，不再预设 speaking 都是普通 `chat.send`。验证结束后清除该变量。

### 7.1 受限 Task Demo：只在独立受控环境验证

这个切片默认关闭，也不属于 V0 验收。先关闭稳定句开关，再单独启用：

```powershell
Remove-Item Env:VITE_FEATURE_LIVE_VOICE_STREAMING_SPEECH -ErrorAction SilentlyContinue
$env:VITE_FEATURE_LIVE_VOICE_TASK_DEMO = 'true'
npm run dev
```

**安全警告：这不是只读“查看仓库”。** 确认启动或替换会真实调用 AutoHarness `schedule.run`，固定使用有代码副作用的 `extended_evolve_pipeline`，可能生成或修改本地 Harness 代码包。取消只能阻止尚未发生的后续执行，不能撤销已有修改；Live Voice 的“打断并说话”或退出只停止本地语音反馈，不会取消 `schedule.run` 或已创建任务。只允许在单一 Session、可丢弃或已备份的目标环境验证，并先在页面常驻披露中向验收者说明这些边界。

任务口令只接受 committed final；partial/interim 必须保持零请求。启动和替换继续要求显式“确认”，但为适配真实 ASR，目标前可使用 `：`、`:`、`，`、`,`、空格或口述“冒号”，固定命令末尾可带 `。！？!?`。推荐流程：

| 语音 | 预期行为 |
|---|---|
| `启动后台演进任务，<目标>` | 只要求明确确认，零任务请求 |
| `确认启动后台演进任务，<目标>` | 真实 `schedule.run`，页面显示来源返回的真实 task ID/状态 |
| `检查后台任务进度` 或 `检查后台演进任务进度` | 对最后可见真实 task ID 调用 `schedule.status` |
| `取消后台演进任务` | 只要求确认，零取消请求 |
| `确认取消后台演进任务` | 对最后可见真实 task ID 调用 `schedule.cancel` |
| `替换后台演进任务，<目标>` | 只要求确认，零任务请求 |
| `确认替换后台演进任务，<目标>` | 先确认取消 A，再创建不同真实 ID 的 successor B |

必须先进入已经保存的真实 Session；`session_id=new` 时不会发任务请求。capture 期间若切换 Session，本次口令也必须以零请求失效。不要使用过于通用的“检查进度”，它会继续走普通 Chat/Agent，不属于任务口令。

如果 `schedule.run` 超时、断线、payload 无效或缺少 task ID，前端会用同一稳定 command ID 查询服务端 scoped exact-key list，并只接受 namespace、key、query、pipeline 和冻结 target 全部严格匹配且无业务错误的记录；对账不能证明结果时才进入 `mutation-unknown`，且 status/cancel 不会退回操作旧 predecessor。后端对 list/status/cancel/logs/delete 强制校验创建 owner 与项目 target，任务也冻结进程内 Agent context 并返回项目/来源 provenance。command journal、最后可见任务和 latch 仍只在当前页面/Session 内存中，刷新后的自动恢复尚未实现。执行前必须核对界面显示的绝对项目 target；真实有副作用 E2E 仍应在单用户、可丢弃或已备份环境进行，因为跨进程一致性、exactly-once、外部副作用 reconciliation 和重启后的 Agent context 恢复尚未完成。

验证结束后执行：

```powershell
Remove-Item Env:VITE_FEATURE_LIVE_VOICE_TASK_DEMO -ErrorAction SilentlyContinue
```

真实任务测试必须保存脱敏的 task ID、原始状态、请求顺序和目标环境说明；不能用 UI 反馈代替后台事实。

## 8. 先做文字工具冒烟，再做语音

先用文字发送一个强制使用真实终端工具、结果可核对的请求：

```text
必须调用终端执行 git status --short --branch，不要根据上下文猜测。
```

成功证据不是“回答看起来合理”，而是 WebSocket/后端日志实际出现以下顺序中的真实事件：

```text
project.create（首次注册时）
→ session.create
→ chat.send
→ chat.tool_call
→ chat.tool_result
→ chat.final
```

如果文字冒烟都失败，先修后端、项目注册、模型或工具配置，不要把问题归咎于 Live Voice。

## 9. 真实 Live Voice 验收

1. 连接耳机，确认 Chrome 麦克风权限和默认输入设备。
2. Agent 模式进入 Live Voice，状态必须变为 Listening。
3. 说：“必须调用终端执行 git status --short --branch，不要根据上下文猜测。”
4. interim 期间消息列表不能新增用户消息；final 后只能新增一条。
5. 核对真实 `chat.tool_call`、`chat.tool_result`、`chat.final`。
6. 完整回答必须从耳机实际朗读。
7. thinking/tool 时重新开麦并在新 final 到达时确认 Agent 仍在 processing；该样本必须真实走 `chat.interrupt(intent=supplement)`。
8. speaking 时重新开麦；旧声音应立即停止且不能恢复，但 Agent 已完成时新 final 应作为一次普通 `chat.send`，不能冒充 supplement。
9. 按 [V0_ACCEPTANCE.md](V0_ACCEPTANCE.md) 完成连续 10 Turn、3 次 thinking supplement、4 次 tool supplement、3 次 speaking 停声/普通发送，以及 20 分钟或 20 Turn soak。
10. 完整执行 [DEMO_SHOWCASE.md](DEMO_SHOWCASE.md) 的主演示脚本，连续成功 3 次。

同时观察：ACK 前的旧 `chat.tool_call` / `chat.tool_update` 和短暂 `processing=false` 当前已有前端隔离，但 `chat.tool_result` 与工具真实副作用没有 generation fence。打断后必须核对旧工具结果、实际副作用和 Gateway cancel warning，不能只看 UI 是否隐藏。

## 10. 2026-08-01 首次真实贯通记录

### 环境与前置检查

- Windows、Chrome `150.0.7871.187`、Jabra EVOLVE 30 II、`zh-CN`、Node.js `24.14.0`、Python `3.12.9`、模型标签 `deepseek-v4-flash`。
- 文字强制 Terminal Tool smoke 成功，确认 Agent、项目、模型和真实工具链可用。
- Python 本轮临时复用主仓 `.venv`；未将该目录或任何配置写入 Git。
- 测试时 `HEAD` 为交接基线 `48a9fe4c571c98aabbf93688727ec8823f6d0c00`，工作区包含本轮候选修复，因此本记录不是对旧基线的通过声明。提交后可用 `git log -1 --format=%H -- docs/zh/live-voice/E2E_RUNBOOK.md` 定位包含本记录和实现的首个可恢复快照。

### 主链时间线

口令为“调用终端查看当前分支”。浏览器完整识别该句；final 只提交一个逻辑 Turn，新会话从 `new` promotion 到真实 session 时 Live Voice 保持激活。

| 相对时间 | 观察 |
|---:|---|
| `T+1.050s` | 进入 Agent working |
| 处理中 | 真实 Terminal Tool 执行 `git branch --show-current` |
| 处理中 | 工具结果为 `hx/0731_live_voice_ux` |
| `T+7.420s` | Agent 完成 |
| `T+8.922s` | 进入浏览器 TTS |
| `T+17.215s` | 完整朗读结束，自动回到 Listening |

用户确认完整听到分支名中的斜杠、数字和下划线。页面仍显示原始回答，只有 TTS 副本进行了技术标识符朗读化。

### 静默与连续回听

- 初始静默测试的 `T+` 基准是点击 Retry 后开始的 UI 轮询，不是 Recognition `onstart` 的仪器时间；`T+7.293s` 仍为 Listening，`T+7.816s` 显示 `no-speech`，与约 8 秒的配置窗口一致。Chrome 更早的自然结束没有提前终止逻辑 capture。
- 自动回听又接收了 2 个 follow-up，证明 TTS 后回 Listening 的循环能继续。
- 两轮中 Web Speech 将 `git` 识别为“地图”或“史记”。因此它们是循环证据，不计入“准确 10 Turn”，并记录为中文技术词准确率风险。

### 本记录能和不能证明什么

已证明：文字工具 smoke、真实麦克风 final、`new` session promotion、真实 Agent/Terminal Tool、完整技术标识符 TTS、自动回听和约 8 秒初始静默窗口在这一组固定环境中可以成立。

未证明：10 个准确语音 Turn、7 次 processing supplement、3 次 speaking 停声/普通发送、旧副作用 fence、20 分钟或 20 Turn、主演示脚本连续 3 次、Desktop/WebView2 或任何生产可靠性指标。

## 11. 证据记录模板

只记录非敏感信息：

```text
日期/时间：
Git commit：
工作区是否干净：
Windows 版本/build：
Chrome 版本：
Python 版本：
Node/npm 版本：
模型 Provider 标签（不得记录 key/base 完整值）：
麦克风/耳机型号或标签：
Chrome 麦克风权限：允许 / 拒绝
网络：固定网络标签
端口：18092 / 19000 / 19001 / 5173
connection.ack：通过 / 失败
文字 tool smoke：通过 / 失败
真实语音 final：通过 / 失败
new session promotion 保持：通过 / 失败
tool_call/tool_result/final：通过 / 失败
实际 TTS：通过 / 失败
技术标识符完整听到：通过 / 失败
8 秒初始静默阈值：通过 / 失败
10 Turn 通过数 / 重复提交：
thinking supplement：__ / 3
tool supplement：__ / 4
speaking playback stop + chat.send：__ / 3
10 次打断旧声音恢复次数：
实际路由证据缺失次数：
迟到 tool_result / cancel warning / 可观察副作用：
20 分钟或 20 Turn：
完整脚本连续成功次数：
ASR 误识别样本：
已知问题与复现步骤：
```

截图和脱敏日志可以作为本机验收证据，但提交前必须确认不包含密钥、用户目录、私人对话或其他敏感信息。

## 12. 结束与恢复

- 退出 Live Voice，确认麦克风和声音均停止。
- 停止 Vite、Gateway 和 AgentServer 进程。
- 若采用方案 A，恢复之前备份的用户 channel 配置。
- 按 [V0_ACCEPTANCE.md](V0_ACCEPTANCE.md) 保存脱敏验收结果，更新 [STATUS.md](STATUS.md) 与 [HANDOFF.md](HANDOFF.md) 中的通过项、失败项和下一步。Post-V0 正常提交并推送；V0 验收必须在 `2c700934...` 的独立 checkout/worktree 中完成，验收证据和后续开发事实分别提交，不得混为同一放行结论。
