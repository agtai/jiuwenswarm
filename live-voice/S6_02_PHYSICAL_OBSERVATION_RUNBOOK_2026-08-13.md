# S6-02 物理观察执行手册 — 2026-08-13

> S6-02 是 S6 六项里唯一无法由自动化或 AI 完成的一项：它要求**真人在真实
> Chrome 上用真实麦克风与真实输出设备**完成权限、设备与听感确认。本文是为此
> 准备的一次性执行手册；执行结果回填后 S6-02 才能判定。
> AI 不得声称自己听到了扬声器输出，也不得代替浏览器权限弹窗做选择。

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

## 2. 执行前提（已全部就绪，不需要你搭）

| 项 | 状态 |
|---|---|
| 私有 origin | `https://live-voice.localhost`（Caddy 本地 CA 已装，浏览器直接可信） |
| 五个服务 | `python D:\lvalpha\run-20260812\scripts\services.py status` 应全部 LISTENING |
| 前端 flags | `INTEGRATED_WEB` / `INTEGRATED_P1` / `PRODUCT_P3_MUTATION` = true |
| Speech 凭据 | Gateway 侧用户级环境变量，浏览器层不下发（已实测 0 泄漏） |
| 目标项目 | 一次性 fixture `D:\lvalpha\run-20260812\fixture-project`（无 remote） |

若有服务 down：`python D:\lvalpha\run-20260812\scripts\services.py start`。

### 2b. 页面预检（已代你跑过，2026-08-13）

| 检查 | 实测 |
|---|---|
| TLS | 用 Caddy 本地 CA 校验通过，TLSv1.3，证书 SAN 恰为 `live-voice.localhost` |
| 首页 | `HTTP/1.1 200 OK`，866 字节，`id="root"` 存在，3 个 module script |
| CSP | `default-src 'self'; connect-src 'self' wss://live-voice.localhost; media-src 'self' blob:; worker-src 'self' blob:; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'` |
| HTML 中的 Speech 凭据 | 0 |

也就是说：证书、同源、CSP（含音频所需的 `media-src blob:` 与 `worker-src blob:`）
都不会成为你的障碍。**Chrome 直接打开即可，不会有证书警告，不需要任何开关。**

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
"C:\Program Files\Google\Chrome\Application\chrome.exe" --user-data-dir="D:\lvalpha\run-20260812\browser-profile" https://live-voice.localhost
```

它会启动一个与你日常 Chrome 并存的独立实例。第一次启动是全新 profile：没有扩展、
没有历史站点权限、没有该 origin 的媒体互动记录。

**无痕只用于 O2**：O1 授予之后，同一 profile 不会再弹窗；O2（拒绝）就在这个专用
profile 里开一个无痕窗口做，这样不会破坏主窗口已授予的状态。

**绝对不要加的启动参数**：`--ignore-certificate-errors`、
`--unsafely-treat-insecure-origin-as-secure`、`--allow-running-insecure-content`
或任何关闭安全策略的开关。CA 已受信、origin 已是 https，这些都不需要，
且超出本次授权边界。

**顺手确认一下浏览器基线**：打开 `chrome://version`，把第一行版本号发我。
本机安装了两个版本目录（`151.0.7922.109` 与 `151.0.7922.77`），而 D111 声明的
基线是 `151.0.7922.109`；S6-02 要求「在声明的 Chrome 基线上」观察，所以实际跑的
版本要以你看到的为准记录，不能照抄旧记录。

### 2c. 在哪个页面、怎么让语音块出现

**页面**：只有一个 —— `https://live-voice.localhost` 打开后的**聊天页**。
Live Voice 没有独立路由，它的正式路由面板渲染在 `ChatPanel` 内部
（消息区下方、输入框上方），是一个可折叠 `<details>`，标题
**「Integrated Web 路由事实」**（`data-testid="live-voice-integrated-route"`）。

**「Formal P1 voice」块不是一进页面就有的**，它的渲染条件是
`p1VoiceEnabled = FEATURE_LIVE_VOICE_INTEGRATED_P1 && isConnected &&
p2Activation.status === 'active'`。P2 激活是**自动**的（没有"激活"按钮），
但它要求 `mode === 'agent'` 且已有 session。所以按下面三步走：

1. **工作区选中项目 `live-voice-alpha-fixture`**
   （`proj_43562811`，目录 `D:\lvalpha\run-20260812\fixture-project`，
   `work_mode=code`，未隐藏，会出现在项目列表里）。
   这一步决定 session 绑定哪个项目 —— 服务端 P2 授权要求所绑项目的
   `work_mode` 恰为 `code`，绑错项目会直接拒绝。
2. **聊天模式选择器保持/切到 `agent`**（这是默认值）。
   注意这与上一步的 `work_mode` 是**两个独立概念**：`work_mode` 属于工作区/项目，
   `mode` 属于聊天回合。P2 的自动激活看的是 `mode === 'agent'`。
   若界面上有待回答的追问或 evolution 状态，激活会被挡住，先把它处理掉。
3. **先发一条普通文字消息**。session 是首次发送时才创建的；session 建立后
   面板会自动激活 P2，`p2.agent_interaction` 变为 `formal`，
   「Formal P1 voice」块随即出现。

展开后你会用到两块：

1. **「音频输入与输出」**（`音频设备` fieldset）
   - 按钮 **「授权并加载设备」** ← **麦克风权限弹窗就是这里触发的**
   - 下拉 **「麦克风」** / **「扬声器」**（含「系统默认（明确选择）」）
   - 按钮 **「应用设备」**
   - 事实行：`设备选择状态`、`设备选择原因`（失败时看这里的原文）
2. **「Formal P1 voice」**
   - 按钮 **`Start formal voice turn`**（开始一轮正式语音）
   - 采集中变为 **`Stop and recognize`**（说完按它提交识别）
   - 播放中变为 **`Stop playback`**
   - 事实行：`P1 status`、`P1 reason`

**单次采集上限 30 秒**（`PRODUCT_P1_CAPTURE_MAX_DURATION_MS = 30_000`），
且与播放重叠期间的采集也计入这 30 秒。说完请及时按 `Stop and recognize`；
超限的采集会被整段丢弃且不会提交给 Speech 或 Agent，需要刷新重来。

## 3. 需要你完成的六项观察

每项都请记下**你实际看到/听到的**，不要写"应该如此"。

### O1 麦克风权限：授予

1. Chrome 打开 `https://live-voice.localhost`，按 §2c 三步让语音块出现
   （选 `live-voice-alpha-fixture` → `agent` 模式 → 发一条文字消息）。
2. 展开 **「Integrated Web 路由事实」**，确认 `p2.agent_interaction` 是 `formal`。
3. 点 **「授权并加载设备」**，在权限弹窗上点**允许**。
4. 「麦克风」「扬声器」按需选择，点 **「应用设备」**。
5. 点 **`Start formal voice turn`**，说一句可核对的话
   （建议：「请回复：语音联调成功。」），说完点 **`Stop and recognize`**。

**要记录**：是否出现权限弹窗；授予后是否开始采集；界面是否显示识别中间结果；
最终提交的文字是否与你说的一致。

### O2 麦克风权限：拒绝

1. 新开一个**无痕窗口**（保证权限状态干净），打开同一地址，同样按 §2c 三步
   把语音块调出来，展开同一区块。
2. 点 **「授权并加载设备」**，在弹窗上点**阻止**。

**要记录**：界面是否给出**显式**的不可用原因（而不是静默失败）；是否退回到
文字输入路径；有没有出现任何"看起来在录音"的假象。

### O3 麦克风权限：撤销

1. 在 O1 已授权的窗口里，地址栏左侧锁形图标 → 网站设置 → 麦克风改为**阻止**。
2. 回到页面，再点 **「授权并加载设备」** 或 **`Start formal voice turn`**
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

1. 用 O1 的窗口，`Start formal voice turn`，说一句会让 Agent 给出**较长**回答的话
   （建议：「请用三句话说明语音链路的三个层次。」），按 `Stop and recognize`。
2. 等待答案播放（`P1 status` 会进入 `playing`）。不要提前按 `Stop playback`。

**要记录**：**你是否从扬声器/耳机里听到了完整的一段答案**（不是只听到开头就
断掉）；听到的内容是否与屏幕上的文字答案一致；播放是否需要你先点一下页面
（autoplay / user activation）；播放过程中界面状态是否正确。

### O6 页面隐藏 / 后台 / 恢复

1. 在答案播放中把标签页切到后台（切到别的标签或最小化窗口），停留数秒，再切回。

**要记录**：切后台时播放与采集的行为；切回后是否出现重复播放、错位播放或
陈旧音频；界面状态是否与实际一致。

## 4. 回填格式

把结果按下表回给我（一句话一项即可，写你看到/听到的事实）：

| 项 | 值 |
|---|---|
| `chrome://version` 第一行 | |

| 观察 | 结果 | 你看到 / 听到的 |
|---|---|---|
| O1 授予 | PASS / FAIL | |
| O2 拒绝 | PASS / FAIL | |
| O3 撤销 | PASS / FAIL | |
| O4 设备切换/丢失 | PASS / FAIL | |
| O5 听感确认 | PASS / FAIL | |
| O6 隐藏/后台/恢复 | PASS / FAIL | |

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
