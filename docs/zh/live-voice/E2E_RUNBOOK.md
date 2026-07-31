# Live Voice 固定环境与真实 E2E 运行手册

本手册用于把“代码可以构建”推进到“固定演示机上真实可演示”。它固定可复现边界，但不会把密钥、个人配置或硬件状态写进 Git。

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

## 4. 本机配置检查

后端需要一个可用的默认模型配置，至少包括非空的 API base、API key、model name 和 client/provider。只检查“是否存在/是否可用”，不要把值贴到日志、文档或 commit 中。

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
7. thinking 或 speaking 时重新开麦，说：“停，只分析 Live Voice 相关代码。”
8. 旧声音应立即停止；新要求只提交一次；旧声音不能恢复。
9. 重复到 10 个语音 Turn、10 次打断，并持续 20 分钟或 20 Turn。
10. 完整执行 [TWO_WEEK_DEMO.md](TWO_WEEK_DEMO.md) 第 10 节脚本，连续成功 3 次。

同时观察：打断后是否仍显示迟到的旧 `chat.tool_call` / `chat.tool_update` UI。若出现，按 [HANDOFF.md](HANDOFF.md) 的已知风险处理。

## 10. 证据记录模板

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
tool_call/tool_result/final：通过 / 失败
实际 TTS：通过 / 失败
10 Turn 重复提交：
10 次打断旧声音恢复次数：
20 分钟或 20 Turn：
完整脚本连续成功次数：
已知问题与复现步骤：
```

截图和脱敏日志可以作为本机验收证据，但提交前必须确认不包含密钥、用户目录、私人对话或其他敏感信息。

## 11. 结束与恢复

- 退出 Live Voice，确认麦克风和声音均停止。
- 停止 Vite、Gateway 和 AgentServer 进程。
- 若采用方案 A，恢复之前备份的用户 channel 配置。
- 更新 [STATUS.md](STATUS.md) 中的通过项、失败项和下一步，提交并推送；不要只在对话里报告结果。
