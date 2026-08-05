# Live Voice 固定环境与真实 E2E 运行手册

- 最近恢复审计：2026-08-02
- 适用共享分支：`hx/0803_live_voice`；`d4c3e32a` 在 Gate 3 FAIL，`ee2896a4afb186e693c720476b6de10797e66f72` 已完成 Gate 0–6 并标记 `V0 Released / 已冻结`
- 最终脱敏证据：[evidence/V0_20260802_ee2896a4.md](../evidence/V0_20260802_ee2896a4.md)；本文仍是以后重建相同受控环境的操作手册
- 当前交付解释：D-046 定义 Week 2 cumulative Integrated Demo，D-055 将 Week 3–4 产品载体调整为 Integrated Web Alpha。下述 V0/稳定句/Task 三种旧模式仍按现有代码诚实记录；Integrated 模式尚未实现，不得把计划中的组合命令当作可运行事实。

本手册用于把“代码可以构建”推进到“固定演示机上真实可演示”。它固定可复现边界，但不会把密钥、个人配置或硬件状态写进 Git。

本文是环境、依赖、服务启动和健康检查的权威入口。V0 的固定语料、分阶段打断、放行 Gate 和证据汇总以 [V0_ACCEPTANCE.md](../validation/V0_ACCEPTANCE.md) 为准；现场展示话术以 [DEMO_SHOWCASE.md](../demo/DEMO_SHOWCASE.md) 为准。

## 1. 为什么必须固定环境

Live Voice 同时依赖浏览器语音能力、麦克风权限、音频设备、外部模型 Provider、网络、后端配置和前后端依赖。只固定源码不能保证另一台机器得到相同结果。

因此分三层固定：

| 层 | 固定方式 | 是否进 Git |
|---|---|---|
| 源码和方案 | 分支、commit、本文档 | 是 |
| Python/Node 依赖 | `uv.lock`、`package-lock.json` | 是 |
| 密钥、浏览器权限、硬件和网络 | 演示机检查清单与无密钥证据 | 否，只记录结果 |

## 2. V0 历史复现基线

- Windows 10/11 x64；最终彩排和演示使用同一台机器。
- Chrome/Chromium 107 或更高；推荐固定当前 Chrome stable 的确切版本，并在最终彩排到演示之间暂停升级。
- Python 3.12.9。仓库允许 `>=3.11,<3.14`，该确切版本已用于当前开发验证。
- Node.js 24.14.0。仓库最低要求 Node 18，该确切版本已通过当前前端测试和构建。
- 中文 `zh-CN`、默认麦克风、耳机、单用户、单浏览器窗口、稳定网络。
- 网络必须同时能访问模型 Provider 和浏览器 Web Speech 所需服务；首次依赖恢复还要访问 Python/Node 包源。

仓库通过 `pyproject.toml` 约束 Python 范围、通过 lockfile 固定依赖，但目前没有 `.python-version`、`.nvmrc`、Volta 或 `engines` 来自动安装精确运行时，也没有固定 `uv`/npm 自身版本。新机器需要先人工安装 Python `3.12.9`、Node `24.14.0` 和 `uv`；可参考 [安装指南](../../docs/zh/安装指南.md) 与 [Quickstart](../../docs/zh/Quickstart.md)，然后以本节的精确版本检查作为 Gate。lockfile 固定的是依赖集合，不是操作系统、Chrome 或硬件。

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

这不是正式兼容性矩阵；它是受控 V0 Demo 的可复现范围。D-055 不倒写该历史环境，也不能用它单独签署当前 Web Alpha。

### 2.1 当前 Web Alpha 验收基线

- 产品载体是 JiuwenSwarm 桌面 Web 前端。X-WEB 真实 Gate 前必须明确冻结单一 Chromium 或 Chrome+Edge 双 Chromium 基线；每次 candidate 必须覆盖该范围中的每个浏览器并记录精确浏览器、OS、origin、设备和网络标签。当前 Chrome 历史/开发证据不自动承诺 Chrome+Edge 或更宽范围。
- 前端 `AGENTS.md` 要求修改后的代码兼容 Chrome/Chromium 107 及以上，这是实现下限；它不替代 X-WEB 对实际 Alpha candidate 的精确浏览器/版本证据范围决定。
- `localhost` 可以用于本地开发和受控验证；非 localhost 的 Alpha 部署必须使用 HTTPS/WSS 或等价安全上下文，并验证 Gateway/AgentServer 反向代理、CSP、CORS 和实时连接路由。
- 浏览器必须分别验证麦克风允许、拒绝、撤销，设备变化/丢失，autoplay/user-activation，页面隐藏/后台/恢复，以及 refresh/reconnect 后无陈旧音频、重复提交或静默失败。
- Speech/模型 Provider 凭据只存在 Gateway/服务端；浏览器 storage、URL、日志和 bundle 中不得出现长期 Provider 密钥。原始音频默认不持久化。
- AudioWorklet/MediaRecorder、媒体编码/采样率/frame、WebSocket/WebTransport 和 Provider 仍由对应 B/C 包在接线前决定；运行手册只记录候选实际采用且通过 review 的路线，不提前给计划路线写成功命令。
- 移动 Web、PWA 和公开跨浏览器/跨 OS 兼容矩阵不属于当前 Alpha Gate；任何未被后续范围决定纳入的浏览器结果只能作为探索证据，不能扩大产品承诺。

## 3. 获取代码与固定依赖

```powershell
$env:GIT_LFS_SKIP_SMUDGE = '1'
git clone --origin agtai --branch hx/0803_live_voice --single-branch https://github.com/agtai/jiuwenswarm.git
Set-Location jiuwenswarm
git pull --ff-only agtai hx/0803_live_voice
git status --short --branch
git status --porcelain
git rev-list --left-right --count HEAD...agtai/hx/0803_live_voice
```

`GIT_LFS_SKIP_SMUDGE=1` 当前是必要绕过：agtai 的 LFS 端点缺少与 Live Voice 无关的 `docs/assets/videos/compression.mp4`，普通 checkout 会收到 404。跳过该媒体不影响 Live Voice 源码、文档、tests、依赖或运行；在对象补传前不要执行全仓 `git lfs pull`。如果仓库已经由其他方式 clone，确保本地 `hx/0803_live_voice` 跟踪正确的 `agtai`/`origin` 分支并 `pull --ff-only`。验收前记录 `git rev-parse HEAD`，upstream 差异必须 `0 0`，工作区不得有意外修改。
Python 依赖以根目录 `uv.lock` 为准：

```powershell
uv sync --python 3.12.9 --frozen
& .\.venv\Scripts\python.exe --version
```

前端依赖以 `package-lock.json` 为准：

```powershell
Push-Location jiuwenswarm\channels\web\frontend
npm ci
node --version
npm --version
Pop-Location
```

不要复制另一台机器的 `.venv` 或 `node_modules`；它们不是跨机器交接物。

2026-08-01 的首次 E2E 为了快速验证，临时复用了同一机器主仓已经存在的 Python `.venv`。这只能证明该机器组合可运行，不能作为恢复步骤；新机器和最终彩排环境仍必须执行上面的 `uv sync --frozen`，并重新跑完整验收。

## 4. 本机配置检查

### 4.1 先隔离 JiuwenSwarm 用户数据

源码 worktree 不是全部运行状态。默认 `%USERPROFILE%\.jiuwenswarm` 包含模型配置、project 注册、Session、Task、日志和 memory；复用它会让累计开发与 V0 证据交叉污染。启动任何后端进程前，在该终端选择一个明确的绝对目录：

```powershell
# 本次选择一个轨道：V0 用 v0；累计开发/Task Demo 改为 post-v0。
$runKind = 'v0'
$runLabel = Get-Date -Format 'yyyyMMdd-HHmmss'
$dataDirForRun = [IO.Path]::GetFullPath((Join-Path (Split-Path -Parent (Get-Location)) ("jiuwenswarm-data-live-voice-{0}-{1}" -f $runKind,$runLabel)))
if (Test-Path -LiteralPath $dataDirForRun) { throw "Refusing to reuse data dir: $dataDirForRun" }
New-Item -ItemType Directory -Path $dataDirForRun -ErrorAction Stop | Out-Null
$env:JIUWENSWARM_DATA_DIR = (Resolve-Path -LiteralPath $dataDirForRun).Path
$env:JIUWENSWARM_DATA_DIR  # 记录这个非敏感绝对路径，后续每个后端终端都重复设置
```

路径必须是新建的绝对空目录，且 V0 与 Post-V0 不共用；命令遇到同名目录会停止，不会用 `-Force` 复用旧数据。首次启动会初始化该用户工作区；模型和 code project 需要在对应隔离目录中从受控渠道重新配置。不要把默认用户目录整体复制进来，也不要删除旧目录来制造“干净环境”。环境变量只对当前 PowerShell 进程及其子进程有效；每个 AgentServer/Gateway/Web/Vite 启动终端都必须把记录的同一绝对路径重新赋给 `JIUWENSWARM_DATA_DIR`，验证结束后停止进程，再清除变量。

### 4.2 私有配置与设备

后端需要一个可用的默认模型配置，至少包括非空的 API base、API key、model name 和 client/provider。只检查“是否存在/是否可用”，不要把值贴到日志、文档或 commit 中。

推荐从 Web UI 的 **Settings → Configuration → Model Configuration** 注入或选择默认模型；高级用户也可以使用机器私有的用户工作区 `config/config.yaml` / `.env`。验收只在 UI 中确认必填项非空或已掩码，并通过下一节的文字 Tool smoke 验证实际可用；不要让终端、Codex 或截图打印完整配置。任一必填项缺失时停止外部模型和真实语音验收，从受控渠道补齐后再继续。

还要检查：

- 演示用仓库目录已在 JiuwenSwarm 中注册为 code project。
- 模型 Provider 的 HTTPS endpoint 可从演示机访问。
- Chrome 已允许当前 localhost 站点使用麦克风。
- 默认麦克风和耳机正确，系统输入电平可见。
- 端口 `18092`、`19000`、`19001`、`5173` 未被其他进程占用。可在启动前只读检查：

  ```powershell
  Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
    Where-Object LocalPort -In 18092,19000,19001,5173 |
    Select-Object LocalAddress,LocalPort,OwningProcess
  ```

用户工作区配置和 `.env` 是机器私有状态。不得提交完整配置、API key、Slack token 或其他凭据。

## 5. 服务拓扑与健康判据

下图是当前 localhost 开发/V0/Post-V0 验证拓扑，不是最终 Web Alpha 部署证明：

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

Web Alpha candidate 还必须在声明的安全 origin 上验证 `browser → same-origin/reverse proxy → Gateway → AgentServer`。实际 path、HTTPS/WSS 终止点、CSP/CORS、认证/凭据边界和诊断入口必须记录为环境证据；localhost 的 `ws://` 成功不能替代部署 Gate。

运行日志位于选定数据目录的 `agent/.logs/`，Web 开发日志还可能写到前端 `logs/ws-dev.log`。单独打开的日志终端不会继承其他 PowerShell 的环境变量；需要保留事件顺序时，先把第 4.1 节记录的同一绝对路径重新绑定并确认日志文件存在：

```powershell
$dataDirItem = Get-Item -LiteralPath '<替换为第 4.1 节记录的绝对数据目录>' -Force -ErrorAction Stop
if (-not $dataDirItem.PSIsContainer -or $dataDirItem.PSProvider.Name -ne 'FileSystem') { throw 'Data dir must be an existing filesystem directory' }
$env:JIUWENSWARM_DATA_DIR = $dataDirItem.FullName
$logPath = Join-Path $env:JIUWENSWARM_DATA_DIR 'agent\.logs\full.log'
if (-not (Test-Path -LiteralPath $logPath -PathType Leaf)) { throw "Log file not found: $logPath" }
Get-Content -LiteralPath $logPath -Wait
```

截取证据前必须脱敏，不打印模型配置、用户路径或私有对话。

## 6. 启动后端

### 方案 A：显式临时关闭外部 IM channel

如果用户配置中 Slack 或其他 IM channel 已启用，完整启动会尝试外部连接。演示前先备份用户配置，显式临时关闭无关 channel，演示后恢复。不要提交这个配置，也不要在进程运行中热改配置。

然后按仓库正常方式启动：

```powershell
Set-Location '<替换为本次代码 worktree 的绝对路径>' -ErrorAction Stop
if (-not (Test-Path -LiteralPath '.\pyproject.toml')) { throw 'Not at the worktree root' }
$dataDirItem = Get-Item -LiteralPath '<替换为第 4.1 节记录的绝对数据目录>' -Force -ErrorAction Stop
if (-not $dataDirItem.PSIsContainer -or $dataDirItem.PSProvider.Name -ne 'FileSystem') { throw 'Data dir must be an existing filesystem directory' }
$env:JIUWENSWARM_DATA_DIR = $dataDirItem.FullName
& .\.venv\Scripts\python.exe -m jiuwenswarm.app
```

注意：该命令启动后端服务，但不启动 Vite 前端。

### 方案 B：仅本次 E2E 的进程内 Slack 屏蔽

当不希望修改用户配置时，可以用两个终端启动拆分服务。这个方案只用于临时 E2E，不是产品启动方式；配置热加载或设置修改可能绕过屏蔽。

终端 1：

```powershell
Set-Location '<替换为本次代码 worktree 的绝对路径>' -ErrorAction Stop
if (-not (Test-Path -LiteralPath '.\pyproject.toml')) { throw 'Not at the worktree root' }
$dataDirItem = Get-Item -LiteralPath '<替换为第 4.1 节记录的绝对数据目录>' -Force -ErrorAction Stop
if (-not $dataDirItem.PSIsContainer -or $dataDirItem.PSProvider.Name -ne 'FileSystem') { throw 'Data dir must be an existing filesystem directory' }
$env:JIUWENSWARM_DATA_DIR = $dataDirItem.FullName
& .\.venv\Scripts\python.exe -m jiuwenswarm.server.app_agentserver
```

终端 2：

```powershell
Set-Location '<替换为本次代码 worktree 的绝对路径>' -ErrorAction Stop
if (-not (Test-Path -LiteralPath '.\pyproject.toml')) { throw 'Not at the worktree root' }
$dataDirItem = Get-Item -LiteralPath '<替换为第 4.1 节记录的绝对数据目录>' -Force -ErrorAction Stop
if (-not $dataDirItem.PSIsContainer -or $dataDirItem.PSProvider.Name -ne 'FileSystem') { throw 'Data dir must be an existing filesystem directory' }
$env:JIUWENSWARM_DATA_DIR = $dataDirItem.FullName
& .\.venv\Scripts\python.exe -c "import jiuwenswarm.common.config as c; real=c.get_config; c.get_config=lambda:(lambda x:(x.setdefault('channels',{}).setdefault('slack',{}).__setitem__('enabled',False),x)[1])(real()); import jiuwenswarm.gateway.app_gateway as g; g.main()"
```

这只在 Gateway 进程内把 Slack 设为禁用，避免为 Live Voice 验证产生无关外部连接。若还有其他已启用 IM channel，应使用方案 A 明确关闭。

## 7. 启动前端

Vite 也会读取 `JIUWENSWARM_DATA_DIR`，所以前端终端必须使用与本次后端相同的隔离路径。**当前已实现的**默认 V0、稳定句预读和 Task Demo 三种模式一次只能选一种；切换模式时先按 `Ctrl+C` 停止现有 Vite，确认 `5173` 已释放，再在新终端完成变量设置后启动。不得先运行 `npm run dev` 再修改变量。

### 7.1 计划中的 cumulative Integrated / Web Alpha 模式：当前不可运行

Week 2 Gate 要求在同一 Session 和同一累计产品路径中组合 P1、P2、P3alpha、Context、Progress、Failure/Degradation 和 Observability，并由 route telemetry 标记每段 `formal/fallback/demo_substitute/unsupported/unknown`。当前代码和下面的命令尚未提供这种组合模式，因此：

- 不得同时打开现有两个 Post-V0 flag 并把偶然共存称为 Integrated Demo；
- 不得拼接多个独立运行的截图或结果计算 Replacement Ledger；
- 不得使用 fake Provider/Executor 作为真实 showcase 成功；
- 在正式 Integrated route、组合 flag/capability、trace 和关闭路径落地前，[INTEGRATED_SHOWCASE.md](../demo/INTEGRATED_SHOWCASE.md) 保持 `NOT RUNNABLE YET`，Week 2 score 保持未开始；
- 新组合模式落地时，必须在本节记录精确启动变量/配置、互斥与兼容规则、route trace 检查、停止/恢复流程和实际 tested candidate，不能提前写占位命令。

Integrated 模式实现后仍要保留下述 V0 模式用于不可变回归，并允许每个 formal module 单独切回其声明的 fallback。Week 2/Week 4 分别按 [INTEGRATED_DEMO_ACCEPTANCE.md](../validation/INTEGRATED_DEMO_ACCEPTANCE.md) 和 [ALPHA_ACCEPTANCE.md](../validation/ALPHA_ACCEPTANCE.md) 取证。

### 7.2 默认 V0 模式

在新终端执行；两个 Post-V0 flag 必须在启动前清除：

```powershell
Set-Location '<替换为本次代码 worktree 的绝对路径>' -ErrorAction Stop
$dataDirItem = Get-Item -LiteralPath '<替换为第 4.1 节记录的绝对数据目录>' -Force -ErrorAction Stop
if (-not $dataDirItem.PSIsContainer -or $dataDirItem.PSProvider.Name -ne 'FileSystem') { throw 'Data dir must be an existing filesystem directory' }
$env:JIUWENSWARM_DATA_DIR = $dataDirItem.FullName
Remove-Item Env:VITE_FEATURE_LIVE_VOICE_STREAMING_SPEECH -ErrorAction SilentlyContinue
Remove-Item Env:VITE_FEATURE_LIVE_VOICE_TASK_DEMO -ErrorAction SilentlyContinue
Set-Location jiuwenswarm\channels\web\frontend
npm run dev
```

打开 `http://localhost:5173`。确认浏览器连接成功并在开发者工具 WebSocket 帧中看到 `connection.ack`。在 UI 中选择或创建指向当前 worktree 绝对路径的 code project，进入 Agent 模式。

### 7.3 单独验证稳定句预读

只有恢复累计开发且不做 V0 Gate 时，才在新的 Vite 启动终端执行：

```powershell
Set-Location '<替换为累计开发 worktree 的绝对路径>' -ErrorAction Stop
$dataDirItem = Get-Item -LiteralPath '<替换为第 4.1 节记录的绝对数据目录>' -Force -ErrorAction Stop
if (-not $dataDirItem.PSIsContainer -or $dataDirItem.PSProvider.Name -ne 'FileSystem') { throw 'Data dir must be an existing filesystem directory' }
$env:JIUWENSWARM_DATA_DIR = $dataDirItem.FullName
Remove-Item Env:VITE_FEATURE_LIVE_VOICE_TASK_DEMO -ErrorAction SilentlyContinue
$env:VITE_FEATURE_LIVE_VOICE_STREAMING_SPEECH = 'true'
Set-Location jiuwenswarm\channels\web\frontend
npm run dev
```

该开关只启用 chatStore 稳定句预读，不等于启用 token/audio streaming TTS。首次验证时关闭 cron、proactive response 和其他可能向同一 Session 注入 assistant 输出的来源；当前服务端事件没有 response/generation provenance，并发输出可能归错 Turn。若 processing 已停止、预读队列已经 drain 但权威 `chat.final` 一直缺失，当前实现等待 10 秒后废弃该 epoch 并显示可 Retry 错误；不得把 provisional 当作 final，也不得补播或重放未确认文本。开关开启时，speaking 可能与 Agent processing 重叠；打断样本必须按新 final 到达时的实际 processing 状态分类，不再预设 speaking 都是普通 `chat.send`。验证结束后清除该变量。

### 7.4 受限 Task Demo：只在独立受控环境验证

这个切片默认关闭，也不属于 V0 验收。确认现有 Vite 已停止，再在新的 Vite 启动终端单独启用：

```powershell
Set-Location '<替换为累计开发 worktree 的绝对路径>' -ErrorAction Stop
$dataDirItem = Get-Item -LiteralPath '<替换为第 4.1 节记录的绝对数据目录>' -Force -ErrorAction Stop
if (-not $dataDirItem.PSIsContainer -or $dataDirItem.PSProvider.Name -ne 'FileSystem') { throw 'Data dir must be an existing filesystem directory' }
$env:JIUWENSWARM_DATA_DIR = $dataDirItem.FullName
Remove-Item Env:VITE_FEATURE_LIVE_VOICE_STREAMING_SPEECH -ErrorAction SilentlyContinue
$env:VITE_FEATURE_LIVE_VOICE_TASK_DEMO = 'true'
Set-Location jiuwenswarm\channels\web\frontend
npm run dev
```

**安全警告：这不是只读“查看仓库”。** 确认启动或替换会真实调用 `schedule.run`，固定使用有代码副作用的 `project_code_pipeline` 和项目绑定 JiuwenSwarm Code Agent，可能直接修改当前已保存的 Git 项目。后台上下文禁用全部 shell 命令，因此测试、脚本、Git 与远端命令都不能运行；明确要求运行测试或 shell 的任务会在创建前拒绝。取消只能阻止尚未发生的后续执行，不能撤销已有修改；Live Voice 的“打断并说话”或退出只停止本地语音反馈，不会取消 `schedule.run` 或已创建任务。只允许在单一 Session、可丢弃或已备份的目标环境验证，并先在页面常驻披露中向验收者说明这些边界。所有正在运行的 AgentServer/Gateway 进程都必须是在各自启动终端中显式设置同一个 Post-V0 专用 `JIUWENSWARM_DATA_DIR` 后启动；仅给 Vite 终端设置变量不算隔离。

> **项目绑定验收基线：** D-056 已选择项目绑定 Code Agent，D-057 已接受一次隔离正向 E2E；脱敏样本见 [D-031 project-bound evidence](../evidence/D031_20260805_PROJECT_BOUND.md)。旧 `d031-05` 的 AutoHarness/runtime-extension 混合合同不得再使用。每次正向验证仍必须证明页面 target、Code Agent root 与 Git root 完全一致，并从响应读取 `effective_execution_root`、`artifact_kind=git_visible_project_change`、`executor=jiuwenswarm_code_agent`、`pipeline=project_code_pipeline`；任一事实缺失或冲突都停止，不得用 UI 文案或最终变化反推执行根。

Task Demo 启动前先建立可核对的执行身份：

1. 确认 Vite 以及所有正在运行的 AgentServer/Gateway 进程都使用同一个 Post-V0 专用绝对 `JIUWENSWARM_DATA_DIR`，不是 V0 或默认用户目录。
2. 在 UI 注册并保存**本次可丢弃 Git 目标的精确绝对路径**为 code project；用 `git rev-parse --show-toplevel` 核对页面 target，不允许用累计源码仓库、相似目录名或旧目标代替。
3. 创建一个用于普通文字冒烟的持久 Session，等待真实 session ID 生成；`session_id=new` 或项目路径/ID不匹配时不得继续。
4. 先用文字强制 Terminal Tool 读取当前短 SHA 和绝对仓库根，只确认普通 Agent 会话目标与面板一致。Task Demo 的 `schedule.run`/`schedule.status` 还必须返回受信的 project execution contract；其中 effective execution root 必须与页面 target 和 `git rev-parse --show-toplevel` 精确一致，artifact/executor/pipeline 必须匹配上方固定值。
5. 等文字冒烟完全结束后重新检查目标。普通 Agent 初始化可能已创建 runtime support paths；只在确认目标确实是可丢弃环境后，精确清理或接受这些已识别变化并重新记录 baseline。仅为删除已知目标变化不需要重启服务。随后新建一个无旧 Chat 历史的持久 Session 进行 D-031 正向验证，并再次核对项目 ID/路径。

任务口令只接受 committed final；partial/interim 必须保持零请求。启动和替换继续要求显式“确认”，但为适配真实 ASR，目标前可使用 `：`、`:`、`，`、`,`、空格、口述“冒号”、“任务内容是/为”或“目标是/为”，固定命令末尾可带 `。！？!?`。“后台代码优化任务”是主要语音口令，“后台演进任务”仅保留兼容。推荐流程：

| 语音 | 预期行为 |
|---|---|
| `启动后台代码优化任务，任务内容是<目标>` | 只要求明确确认，零任务请求 |
| `确认启动后台代码优化任务，任务内容是<目标>` | 真实 `schedule.run`，页面显示来源返回的真实 task ID/状态 |
| `检查后台任务进度` 或 `检查后台代码优化任务进度` | 对最后可见真实 task ID 调用 `schedule.status` |
| `取消后台代码优化任务` | 只要求确认，零取消请求 |
| `确认取消后台代码优化任务` | 对最后可见真实 task ID 调用 `schedule.cancel` |
| `替换后台代码优化任务，任务内容是<目标>` | 只要求确认，零任务请求 |
| `确认替换后台代码优化任务，任务内容是<目标>` | 先确认取消 A，再创建不同真实 ID 的 successor B |

必须先进入已经保存的真实 Session；`session_id=new` 时不会发任务请求。capture 期间若切换 Session，本次口令也必须以零请求失效。不要使用过于通用的“检查进度”，它会继续走普通 Chat/Agent，不属于任务口令。

如果 `schedule.run` 超时、断线、payload 无效或缺少 task ID，前端会用同一稳定 command ID 查询服务端 scoped exact-key list，并只接受 namespace、key、query、pipeline 和冻结 target 全部严格匹配且无业务错误的记录；对账不能证明结果时才进入 `mutation-unknown`，且 status/cancel 不会退回操作旧 predecessor。一次逻辑命令在恢复时可能出现多个同 key `schedule.run` wire attempt；验收要检查持久层只有一个 create command、一个 task 和一个 execution，而不是把“只能看到一次网络请求”当作合同。后端按 Web request 字段对 list/status/cancel/logs/delete 校验创建 owner 与项目 target，任务也冻结进程内 Agent context 并返回项目/来源 provenance；这能阻止正常客户端串线，但 Web 身份仍可由恶意请求伪造，不是生产鉴权。command journal、最后可见任务和 latch 仍只在当前页面/Session 内存中，刷新后的自动恢复明确 unsupported。后端 Task JSON 与日志属于当前机器的 `JIUWENSWARM_DATA_DIR`；前端 task projection/card/command state 只在浏览器页面内存，刷新即丢。二者都不会随 Git 或换机恢复。执行前必须核对界面显示的绝对项目 target；真实有副作用 E2E 仍应在单用户、可丢弃或已备份环境进行，因为跨进程一致性、exactly-once、外部副作用 reconciliation 和重启后的 Agent context 恢复尚未完成。

Live Voice 创建的一次性代码优化任务还要求目标 Git 项目的 tracked 或未忽略 untracked 文件在执行前后发生变化。只有 Code Agent 正常终止且目标指纹变化，调度状态才可为成功；零变化、只有 `.pytest_cache` 等忽略文件变化、只改外部目录、目标不可读或目标不是有效 Git 项目都必须返回失败。该检查只能拒绝无效果任务，不能证明修改内容正确。需要快速验证结果门槛时，运行 `python -m pytest -o addopts='' tests/unit_tests/auto_harness/test_schedule_task_service.py -q -k live_voice_result_contract`，不必启动真实模型流水线。

任务启动播报和终态播报必须分开计数。当前终态合同是 safe at-most-once：只有终态被采用时恰好存在安全语音窗口才尝试一次，不排队延迟补播。因此终态播报 `0` 或 `1` 次符合该合同，超过 `1` 次失败；不要把 `0` 写成“必达通知通过”。如果验收目标要求 guaranteed/eventual delivery，必须等待正式 TaskEvent/notification owner 提供可恢复投递合同。

当前 Code Agent 还可能在选定项目内创建 `.gitignore`、`coding_memory/`、`prompt_attachment/` 和 `.agent_history/` 等 runtime support paths。D-057 将其位置治理归给 Agent Runtime/workspace isolation；D-031 验收必须逐项记录这些路径，不能宣称绝对“意外文件为零”。若当前 Gate 明确要求 clean workspace，则这些路径仍是失败项，不能用 D-031 已关闭豁免。

手工文件清单必须显式证明非 ASCII 路径被完整记录。`d031-05` 的 PowerShell `git ls-files | Get-FileHash | Export-Csv` 基线只保存 2,665 行并漏掉 140 个非 ASCII 路径，后续对比会把它们误报为新增；该 TSV 不得作为证据。优先使用调度器的 Git-visible 指纹、干净的 `git status` 和经 UTF-8 路径样本校验的独立清单实现。

验证结束后执行：

```powershell
Remove-Item Env:VITE_FEATURE_LIVE_VOICE_TASK_DEMO -ErrorAction SilentlyContinue
```

真实任务测试必须保存脱敏的 task ID、原始状态、请求顺序和目标环境说明；不能用 UI 反馈代替后台事实。已接受的 2026-08-05 样本格式见 [D-031 project-bound evidence](../evidence/D031_20260805_PROJECT_BOUND.md)。

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
9. 按 [V0_ACCEPTANCE.md](../validation/V0_ACCEPTANCE.md) 完成连续 10 Turn、3 次 thinking supplement、4 次 tool supplement、3 次 speaking 停声/普通发送，以及 20 分钟或 20 Turn soak。
10. 完整执行 [DEMO_SHOWCASE.md](../demo/DEMO_SHOWCASE.md) 的主演示脚本，连续成功 3 次。

同时观察：ACK 前的旧 `chat.tool_call` / `chat.tool_update` 和短暂 `processing=false` 当前已有前端隔离，但 `chat.tool_result` 与工具真实副作用没有 generation fence。打断后必须核对旧工具结果、实际副作用和 Gateway cancel warning，不能只看 UI 是否隐藏。

## 10. 2026-08-01 首次真实贯通记录

### 环境与前置检查

- Windows、Chrome `150.0.7871.187`、Jabra EVOLVE 30 II、`zh-CN`、Node.js `24.14.0`、Python `3.12.9`、模型标签 `deepseek-v4-flash`。
- 文字强制 Terminal Tool smoke 成功，确认 Agent、项目、模型和真实工具链可用。
- Python 本轮临时复用主仓 `.venv`；未将该目录或任何配置写入 Git。
- 测试时 `HEAD` 为交接基线 `48a9fe4c571c98aabbf93688727ec8823f6d0c00`，工作区包含本轮候选修复，因此本记录不是对旧基线的通过声明。提交后可用 `git log -1 --format=%H -- live-voice/runbooks/E2E_RUNBOOK.md` 定位包含本记录和实现的首个可恢复快照。

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

### 2026-08-02 V0 Gate 1 候选切换记录

- Attempt 1 在旧候选 `2c700934...` 上真实完成 `chat.send → chat.tool_call → chat.tool_result → chat.final`，Terminal Tool 返回 `2c700934,1`。
- dirty count `1` 的根因是 JiuwenSwarm runtime 在仓库根写入旧候选未忽略的 `.agent_history/`；因此该次 attempt 为 **FAIL**，不能计作 Gate 1 PASS。
- 新候选 `d4c3e32aa34a4d26b346cdf0396788d39930cd6b` 的父提交为 `2c700934...`，唯一变化是 `.gitignore` 新增三行忽略 runtime file operation logs。
- 新候选 checkout 恢复 clean 后，Gate 0 已 PASS；Gate 1 固定自动化、TypeScript、build、Ruff、`git diff --check` 和真实文字工具 smoke 已全部 PASS。
- 新的真实工具链返回 `d4c3e32a,0`，Gate 2 也 PASS；但 Gate 3 Attempt 1 随后 FAIL，`d4c3e32a` 仅保留为失败历史。后续语音 Gate 必须等待 D-037 新 Candidate，不能从旧 Turn 4 续算。

### 2026-08-02 V0 Gate 2 语音样本

- final transcript 为“廖永终端查看当前提交编号前八位并统计未提交文件数量只回答编号和数量”；Web Speech 将“调用”误识别成“廖永”。
- 本次唯一一次 `chat.send → chat.tool_call → chat.tool_result → chat.final` 返回真实 `d4c3e32a 0`，候选工作区仍 clean；用户确认完整听到“d4c3e32a 0”。
- 该转写偏差记录为 ASR fidelity 和关键动词鲁棒性风险，后续必须继续处理，但当前 Agent 已正确执行工具任务链，不把它单独列为任务链阻塞。
- 用户确认完整回答只播一次。虽未即时观察 `Listening`，但无 Retry/再次说话，随后页面显示“未检测到语音”；这是自动重新进入识别并经历静默超时的强间接证据，与 TTS 后自动回听一致。结合唯一 send/tool/result/final、`new` Session 和 dirty=`0`，Gate 2 记 **PASS**，但没有直接状态时间线截图。

### 2026-08-02 V0 Gate 3 Attempt 1：Turn 3 FAIL

- Turn 1/2 正常；Turn 3 ASR 将“年月日”识别成“念月日”，Agent 选择 `git log -1 --format=%ad --date=format:'%m月%d日'`。
- Git for Windows `2.47.1.windows.2` 可在 Agent 外稳定复现该非 ASCII 日期 format OOM；`--date=short`/ASCII 对照立即成功。单个异常 Git 子进程曾达到约 8.5 GB Working Set / 49 GB Private Memory。
- 同一 request 记录 11 次 tool call、10 次相同失败 result、0 个 Turn 3 final；第 11 次在途时由 `chat.interrupt(intent=cancel)` 终止。候选 dirty=`0`，资源恢复，Agent 服务以同一隔离数据目录重启。
- CircuitBreaker 默认关闭且默认错误阈值过晚。本 attempt 记 **FAIL**；先建立带低阈值确定性失败熔断的新 Candidate，再从新 Session Turn 1 重跑。日期口令改成 `YYYY-MM-DD` 只隔离平台缺陷，不证明生产工具资源保护完成。

## 11. 证据记录模板

只记录非敏感信息：

```text
日期/时间：
Git commit：
工作区是否干净：
OS 版本/build：
Chrome 版本：
Edge 版本：
Web origin 与 secure-context 状态：
HTTPS/WSS 终止点与反向代理标签：
CSP/CORS/实时连接路由：通过 / 失败
麦克风允许/拒绝/撤销：
设备变化/丢失与恢复：
autoplay/user-activation：
页面隐藏/后台/恢复：
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
- 记录本次使用的 `JIUWENSWARM_DATA_DIR` 标签，停止所有引用它的进程后执行 `Remove-Item Env:JIUWENSWARM_DATA_DIR -ErrorAction SilentlyContinue`；不要自动删除证据目录。
- 按 [V0_ACCEPTANCE.md](../validation/V0_ACCEPTANCE.md) 保存脱敏验收结果，只在 [STATUS.md](../STATUS.md) 更新通过项、失败项和下一步，并按根 `AGENTS.md` 对每次 commit 和 push 分别取得明确批准；`ee2896a4` 已冻结，后续只在独立 checkout/worktree 中复现或调查回归，`d4c3e32a` 只作失败历史，Release 证据和后续开发事实分别提交，不得混为同一能力结论。
