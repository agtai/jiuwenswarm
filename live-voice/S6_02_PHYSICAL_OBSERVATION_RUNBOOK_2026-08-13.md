# S6-02 物理观察执行手册 — 2026-08-13

> S6-02 是 S6 六项里唯一无法由自动化或 AI 完成的一项：它要求**真人在真实
> Chrome 上用真实麦克风与真实输出设备**完成权限、设备与听感确认。本文是为此
> 准备的一次性执行手册；执行结果回填后 S6-02 才能判定。
> AI 不得声称自己听到了扬声器输出，也不得代替浏览器权限弹窗做选择。
> `<RUN_ROOT>` 是机器私有的运行根目录，其绝对路径不入 Git；
> 本轮它位于一个 Git 之外的本地目录，由会话交接文档单独记录。

当前状态只看 [STATUS.md](STATUS.md)。O1–O4 已在同一 Chrome/物理设备基线完成并
记录为 PASS；若源码、浏览器权限或设备基线没有改变，不重复消费这些人工步骤。
当前复验只包含：缺陷 11 的真实路径区分、O5 大于 15 秒完整朗读、O6
隐藏/后台/恢复，以及对候选缺陷 12 的只观测诊断。诊断数据不足时保持
`UNMEASURED`，不得通过调整缓冲参数“试到听起来正常”。

## 1. 为什么只能由你做

[S5–S8 执行计划](roadmap/ALPHA_S5_S8_EXECUTION_PLAN_2026-08-12.md) 的 S6-02 退出条件
要求 AIO / SR / SS 三个模块共享**一次经过评审的物理**
`microphone → STT → real Agent → TTS → playout` 结果，其 required oracles 含
权限授予/拒绝/撤销、设备选择/切换/丢失、autoplay/user activation、
hidden/background/resume 与听感确认。这些都发生在浏览器权限层与物理音频设备上：

- 麦克风权限弹窗只接受真实用户手势，脚本点不了，也不该被绕过；
- 设备切换/拔出是物理事件；
- 「听到了完整答案」只能由人耳判定。

固定语料链路已由自动化全部覆盖（见
[D112](D112_ALPHA_REAL_MEDIA_ROUTE_2026-08-13.md) §8/§8b/§8c），所以本手册只做
物理部分，不重复已测项。

## 2. 执行前提（每次复验前重新核对）

| 项 | 状态 |
|---|---|
| 私有 origin | `https://live-voice.localhost`（Caddy 本地 CA 已装，浏览器直接可信） |
| 五个服务 | `python <RUN_ROOT>\scripts\services.py status` 应全部 LISTENING |
| 前端 flags | `INTEGRATED_WEB` / `INTEGRATED_P1` / `PRODUCT_P3_MUTATION` = true |
| Speech 凭据 | Gateway 侧用户级环境变量，浏览器层不下发（已实测 0 泄漏） |
| 目标项目 | 一次性 fixture `<RUN_ROOT>\fixture-project`（无 remote） |

若有服务 down：`python <RUN_ROOT>\scripts\services.py start`。

### 2a. 候选源码与构建预检（Main 执行）

复验必须绑定一个干净候选，且包含缺陷 11 的修复提交 `10062c3e`。先执行：

```powershell
Set-Location '<WORKTREE>' -ErrorAction Stop
git status --short --branch
$candidate = git rev-parse HEAD
git merge-base --is-ancestor 10062c3e $candidate
if ($LASTEXITCODE -ne 0) { throw 'candidate does not contain defect-11 repair 10062c3e' }
$python = (Resolve-Path -LiteralPath '.\.venv\Scripts\python.exe' -ErrorAction Stop).Path
& $python '<RUN_ROOT>\scripts\services.py' status
```

工作树必须干净；记录 `$candidate`、branch/upstream 与 ahead/behind。前端必须由同一
候选重新构建，不复用修复前的 `dist`：

```powershell
$env:VITE_FEATURE_LIVE_VOICE_INTEGRATED_WEB = 'true'
$env:VITE_FEATURE_LIVE_VOICE_INTEGRATED_P1 = 'true'
$env:VITE_FEATURE_LIVE_VOICE_PRODUCT_P3_MUTATION = 'true'
Remove-Item Env:VITE_FEATURE_LIVE_VOICE_STREAMING_SPEECH -ErrorAction SilentlyContinue
Remove-Item Env:VITE_FEATURE_LIVE_VOICE_TASK_DEMO -ErrorAction SilentlyContinue
Push-Location 'jiuwenswarm\channels\web\frontend'
try { npm.cmd run build } finally { Pop-Location }
```

随后按 `<RUN_ROOT>\caddy\Caddyfile` 头部的已冻结部署映射让 Caddy 服务这次构建，
再运行 `services.py start` / `status`。只有五个服务全部 `LISTENING`、
`https://live-voice.localhost` 返回 200、页面源码不含 Speech 凭据后才交给人工观察。
不得通过放宽 CSP、忽略证书错误或改用日常浏览器 profile 来清除预检失败。

### 2b. 页面预检（已代你跑过，2026-08-13）

| 检查 | 实测 |
|---|---|
| TLS | 用 Caddy 本地 CA 校验通过，TLSv1.3，证书 SAN 恰为 `live-voice.localhost` |
| 首页 | `HTTP/1.1 200 OK`，866 字节，`id="root"` 存在，3 个 module script |
| CSP | `default-src 'self'; connect-src 'self' wss://live-voice.localhost; media-src 'self' blob:; worker-src 'self' blob:; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'` |
| HTML 中的 Speech 凭据 | 0 |
| 页面渲染 | 真实 UI 可读（第一次预检漏了这一项，见下） |
| 页面内 `new WebSocket(.../ws)` | 312 ms 打开成功，`readyState=1` |
| `/ws/live-voice/media` | 子协议 `live-voice.media.v1` 协商成功 |

也就是说：证书、同源、CSP（含音频所需的 `media-src blob:` 与 `worker-src blob:`）
都不会成为你的障碍。**Chrome 直接打开即可，不会有证书警告，不需要任何开关。**

**修正记录**：这份预检最初只验了 HTTP 200 就交给了你，结果你打开是**整页空白**。
根因是声明的 CSP 没有 `script-src`（回退到 `default-src 'self'`）而 Vite dev server
注入了内联 refresh preamble，被拦后 React 没挂载。已改为由 Caddy 直接服务生产构建
（内联脚本 0），CSP 未放宽，另修了两处：`try_files` 曾把 `/ws` 重写成 `/index.html`
导致 WSS 升级全失败；CSP 缺 `font-src` 导致构建自带的 `data:` 字体被拦。
完整取证见 [D112](D112_ALPHA_REAL_MEDIA_ROUTE_2026-08-13.md) §3b。

**由此带来的一个操作差异**：前端 flags 现在是**构建期**烘焙的。如果之后改了前端源码，
必须按 `<RUN_ROOT>\caddy\Caddyfile` 头部记录的命令带同一组 flags
重新 `npm run build`，否则你看到的还是旧构建。

### 2b2. 用哪个浏览器：普通 Chrome 的**专用 profile**

用你平常那个 Chrome 程序，但**开一个独立 profile**，不要用日常 profile，也不要
把无痕当主战场。

**为什么不是日常 profile**

- 权限状态必须确定且要跨观察保留：O1 授予 → O3 再从站点设置撤销。日常 profile
  可能早就为这个 origin 存过一次决定，那样 O1 的弹窗根本不会出现，观察就无效了。
- 扩展会干扰：广告/隐私/脚本拦截类扩展可能挡掉 `getUserMedia`、WebSocket
  或 `blob:` worker（本站 CSP 正是 `worker-src 'self' blob:` /
  `media-src 'self' blob:`）。干净 profile 里出问题才能归因到产品，而不是扩展。
  这一点直接决定我能否把失败归属到 Alpha 还是 develop。

**为什么隔离不会带来证书麻烦**

Caddy 的本地 CA `CN=Caddy Local Authority - 2026 ECC Root` 已在**当前 Windows
用户**的 Root 信任库（有效期至 2036），所以该用户的**任何** Chrome profile
（含全新 profile 与无痕）都信任它。隔离在证书上零成本。

**启动命令**（profile 落在 Git 之外的运行根目录）

```bash
"<CHROME>" --user-data-dir="<RUN_ROOT>/browser-profile" https://live-voice.localhost
```

它会启动一个与你日常 Chrome 并存的独立实例。第一次启动是全新 profile：没有扩展、
没有历史站点权限、没有该 origin 的媒体互动记录。

**无痕只用于 O2**：O1 授予之后，同一 profile 不会再弹窗；O2（拒绝）就在这个专用
profile 里开一个无痕窗口做，这样不会破坏主窗口已授予的状态。

**绝对不要加的启动参数**：`--ignore-certificate-errors`、
`--unsafely-treat-insecure-origin-as-secure`、`--allow-running-insecure-content`
或任何关闭安全策略的开关。CA 已受信、origin 已是 https，这些都不需要，
且超出本次授权边界。

**浏览器基线已确认**：实测运行 **`151.0.7922.77`（正式版本，64 位）**。
本机同时装有 `151.0.7922.109` 目录，而 D111 声明的基线是 `.109`；既然实际跑的是
`.77`，S6-02 的声明基线就更正为 `.77`（D112 §3b-5），不沿用旧记录的值。

### 2c. 在哪个页面、怎么让语音块出现

**页面**：只有一个 —— `https://live-voice.localhost` 打开后的**聊天页**。
Live Voice 没有独立路由，它的正式路由面板渲染在 `ChatPanel` 内部
（消息区下方、输入框上方），是一个可折叠 `<details>`，标题
**「Integrated Web 路由事实」**（`data-testid="live-voice-integrated-route"`）。

**正式 P1 语音块不是一进页面就有的**，它的渲染条件是
`p1VoiceEnabled = FEATURE_LIVE_VOICE_INTEGRATED_P1 && isConnected &&
p2Activation.status === 'active'`。P2 激活是**自动**的（没有"激活"按钮），
但它要求 `mode === 'agent'` 且已有 session。所以按下面三步走：

1. **在新任务输入框下方的项目选择器中选中 `live-voice-alpha-fixture`**
   （目录 `<RUN_ROOT>\fixture-project`，
   `work_mode=code`，未隐藏，会出现在项目列表里）。
   这一步决定 session 绑定哪个项目 —— 服务端 P2 授权要求所绑项目的
   `work_mode` 恰为 `code`，绑错项目会显示 `FORMAL_P1_NOT_ACTIVE`。侧栏里
   看见项目名不等于新任务已经绑定该项目，必须检查输入框下方的选择器。
2. **聊天模式选择器保持/切到 `agent`**（这是默认值）。
   注意这与上一步的 `work_mode` 是**两个独立概念**：`work_mode` 属于工作区/项目，
   `mode` 属于聊天回合。P2 的自动激活看的是 `mode === 'agent'`。
   若界面上有待回答的追问或 evolution 状态，激活会被挡住，先把它处理掉。
3. **先发一条普通文字消息**。session 是首次发送时才创建的；session 建立后
   面板会自动激活 P2，`p2.agent_interaction` 变为 `formal`，
   顶部 **`Live Voice`** 按钮随即可以打开正式 P1 语音块。

你会用到两块：

1. **「Integrated Web 路由事实」**：展开后确认
   `p2.realtime_conversation` 是 `formal`。P1 在尚未启动麦克风时可以显示
   `FORMAL_P1_NOT_ACTIVE`；打开顶部 `Live Voice` 后应出现
   **`P1 · Gateway Speech · formal`**，这才是本轮要测的正式语音路线。
2. **「Live Voice」正式语音块**
   - 按钮 **`Start speaking`**（开始一轮正式语音并触发麦克风权限）
   - 采集中变为 **`Stop and recognize`**（说完按它提交识别）
   - 播放中变为 **`Stop playback`**
   - 状态/原因直接显示在块内；失败时记录原文

**单次采集上限 30 秒**（`PRODUCT_P1_CAPTURE_MAX_DURATION_MS = 30_000`），
但它不是自动 EOT 的等待时间，也不是语音播放上限。短回复允许播放与下一轮采集
重叠；估算超过 20 秒的长回复会在完整播放后才启动下一轮采集。正式 streaming
playout 独立硬上限为 180 秒。正常 server VAD 路径中，说完后应自动停止并识别；
`Stop and recognize` 只用于手动提交/降级路径。

### 2d. 缺陷 11 真实路径区分（Main 执行，人工 O5 前完成）

使用 Git 之外的 `s6_02_realtime_playout.py`，保持 downlink ACK 为真实 20 ms/帧
节奏。控制组必须来自一个一次性 detached worktree，对候选执行
`git revert --no-commit 10062c3e`；不得改写、切换或污染候选 worktree，也不得把控制组
推送到远端。候选组恢复为包含 `10062c3e` 的干净源码并重新构建/重启。

两组使用相同 Provider、voice、长文本、服务配置和探针参数：

| 组 | 必须观察到的区分结果 |
|---|---|
| 控制组（回退 `10062c3e`） | `first_audio_emitted=true`，约 15,000 ms 出现 `STREAMING_SPEECH_PROVIDER_TIMEOUT`，长回答未完整送完 |
| 候选组（恢复 `10062c3e`） | 总流持续时间大于 15,000 ms，downlink 完整，`degradation_reason=null`，playout receipt 被接受 |

每组至少一个有效样本。记录候选 SHA、输入文本哈希、总时长、首帧/末帧时刻、帧数、
最后 ACK 序号、降级原因和 probe 退出码。控制组失败与候选组通过两者缺一不可；只有
自动化通过或只有候选通过都不能关闭该真实路径证明。

同一候选样本同时采集下列音质诊断；没有某个观测面时明确记为 `UNMEASURED`：

| 观测 | 记录值 |
|---|---|
| 浏览器连续播放调度 underrun 次数 | count；当前播放实现是 `AudioBufferSourceNode` 调度，不得误写成输出 AudioWorklet |
| downlink 帧到达间隔 | sample、p50、p95、max |
| 浏览器已调度未结束 source 峰值 | peak |
| 浏览器 playout queue | capacity、peak depth |
| Gateway sender queue | configured max、peak pending frames |
| 人耳音质 | 是否仍有撕裂/咔哒/电流感，以及大致发生位置 |

这些值用于归因候选缺陷 12，不构成对其修复的预设。尤其不能仅凭
`max_pending_frames=8` 就认定 160 ms 缓冲是根因。

## 3. 六项观察定义与本轮复验范围

每项都请记下**你实际看到/听到的**，不要写"应该如此"。O1–O4 保留如下，供环境
变化时定向复验；当前环境未变化时直接复用已记录 PASS，本轮只执行 O5 和 O6。

### O1 麦克风权限：授予

1. Chrome 打开 `https://live-voice.localhost`，按 §2c 三步让语音块出现
   （选 `live-voice-alpha-fixture` → `agent` 模式 → 发一条文字消息）。
2. 展开 **「Integrated Web 路由事实」**，确认
   `p2.realtime_conversation` 是 `formal`。
3. 点顶部 **`Live Voice`**，确认块内出现 **`P1 · Gateway Speech · formal`**。
4. 点 **`Start speaking`**，在权限弹窗上点**允许**。
5. 说一句可核对的话（建议：「请回复：语音联调成功。」）。正常 server VAD
   应自动停止并识别；本步不要提前点 `Stop and recognize`。

**要记录**：是否出现权限弹窗；授予后是否开始采集；界面是否显示识别中间结果；
最终提交的文字是否与你说的一致。

### O2 麦克风权限：拒绝

1. 新开一个**无痕窗口**（保证权限状态干净），打开同一地址，同样按 §2c 三步
   把语音块调出来，展开同一区块。
2. 点顶部 **`Live Voice`** → **`Start speaking`**，在弹窗上点**阻止**。

**要记录**：界面是否给出**显式**的不可用原因（而不是静默失败）；是否退回到
文字输入路径；有没有出现任何"看起来在录音"的假象。

### O3 麦克风权限：撤销

1. 在 O1 已授权的窗口里，地址栏左侧锁形图标 → 网站设置 → 麦克风改为**阻止**。
2. 回到页面，再点 **`Live Voice`** → **`Start speaking`**
   （必要时按提示刷新）。

**要记录**：撤销后是否立即停止采集；是否给出显式原因；文字路径是否仍可用。

### O4 设备切换与丢失

1. 在有多个输入设备的情况下（例如内置麦克风 + 耳机麦克风），先用
   **「麦克风」** 下拉明确选中其中一个并 **「应用设备」**。
2. 开始一轮语音，说话中途在系统里切换默认输入设备，或直接拔出正在使用的
   USB/耳机麦克风。

**要记录**：切换后是否继续采集或给出显式提示；拔出后是否 fail closed（明确报错）
而不是继续显示假的采集状态；恢复插回后能否重新开始一轮。

### O5 听感确认（本项是 S6-02 的核心）

1. 先点 `Start speaking`，只说「你好」，然后完全不点 `Stop and recognize`。
   停止说话后应由 server VAD 自动结束 listening、识别并提交；若长时间停在
   listening，本项直接记 FAIL。这个测试必须作为服务重启后的第一轮语音，才能覆盖
   cold Provider open。
2. 再点 `Start speaking`，说一句会让 Agent 给出**较长**回答的话
   （建议：「请用至少六句话，依次编号一到六，详细说明语音采集、语音识别、Agent
   推理、语音合成、浏览器播放和失败降级；最后明确说『以上六项已讲完』。」），
   正常路径同样等待自动停止和识别，不要点 `Stop and recognize`。
3. 等待答案播放。不要提前按 `Stop playback`。

**要记录**：「你好」是否自动结束 listening 并识别；**你是否从扬声器/耳机里听到了
完整的一段答案**（不是只听到开头就断掉）；实际播放是否大于 30 秒；是否听到末尾
「以上六项已讲完」；听到的内容是否
与屏幕上的文字答案一致；播放是否需要你先点一下页面（autoplay / user activation）；
播放过程中界面状态是否正确；是否仍有撕裂、咔哒或电流感。

### O6 页面隐藏 / 后台 / 恢复

1. 另开一轮同样的长回答；确认开始播放后，把标签页切到后台（切到别的标签或
   最小化窗口）至少 5 秒，再切回。不要在后台按 `Stop playback`。

**要记录**：切后台时播放与采集的行为；切回后是否出现重复播放、错位播放或
陈旧音频；界面状态是否与实际一致。持续正确播放或显式 fail closed 都记录原始事实；
静默卡住、状态与声音不一致、重复或陈旧音频均为 FAIL。

## 4. 回填格式

把结果按下表回给我（一句话一项即可，写你看到/听到的事实）。O1–O4 若未重跑，
写 `REUSED` 并引用此前 PASS，不得伪装成新观察：

| 观察 | 结果 | 你看到 / 听到的 |
|---|---|---|
| V11 控制组 | PASS / FAIL | 约 15 s timeout、帧数、退出码 |
| V11 候选组 | PASS / FAIL | >15 s 完整、帧数、退出码、degradation |
| O1 授予 | REUSED / PASS / FAIL | |
| O2 拒绝 | REUSED / PASS / FAIL | |
| O3 撤销 | REUSED / PASS / FAIL | |
| O4 设备切换/丢失 | REUSED / PASS / FAIL | |
| O5a 冷启动短句自动 EOT | PASS / FAIL | “你好”是否自动结束 listening 并识别 |
| O5b 长回答听感确认 | PASS / FAIL | 是否越过 30 s、完整到末尾、音色/质量 |
| O6 隐藏/后台/恢复 | PASS / FAIL | |
| D12 诊断 | MEASURED / UNMEASURED | underrun、interarrival、in-flight/queue peaks、听感 |

任何一项 FAIL 请附上你看到的界面文案或错误提示原文（`设备选择原因` /
`P1 reason` 这两行的原文最有用；不要截图里的凭据）。我据此定位归属
（Alpha 引入 vs develop 既有）、修复并补回归测试，然后你只需重跑失败的那一项。

## 4b. 我在你执行期间会做什么

- 我不进浏览器、不代你点权限弹窗、不声称听到了扬声器输出。
- 你执行时服务端日志与权威 Store 会同步记录；你回填后我会用
  [D112](D112_ALPHA_REAL_MEDIA_ROUTE_2026-08-13.md) §8g 的同一套去敏 trace 复现
  手段，独立核对你观察到的每一项在服务端是否留下了一致的事实，再据此判定 S6-02。
- 若某项失败，我按本轮已用过的方式定位：先加一次进程内/裸协议探针分辨是哪一层
  门禁，再三方对照归属，Alpha 的修并加回归测试，develop 既有的只记录不修。

## 5. 边界

- 不要为了让某项通过而改系统信任设置、hosts 文件或浏览器安全开关；
  也不要为省事去用日常 profile 的既有权限状态顶替一次真实的授权观察。
- 不要用真实项目做目标：工作区必须选 `live-voice-alpha-fixture`，
  不要选你自己的项目，也不要选 JiuwenSwarm 源码仓库。
- 观察记录里不要包含 key / token / 浏览器 profile 路径 / 原始音频。
