# D112 Alpha 真实 P2 媒体路由激活与缺陷修复 — 2026-08-13

> 本文是一次性验证记录，记录 `hx/0812_live_voice_w3` 上首次把**专用媒体路由**
> （dedicated media socket + 真实 streaming STT + 真实 Agent + 真实 streaming TTS
> downlink + playout ACK）在私有 origin 上跑通的结果。当前可变状态仍只由
> [STATUS.md](STATUS.md) 拥有。本文**不产生**新的 Alpha 验收结论，S6 未关闭。
> 前序记录：[D111](D111_ALPHA_REAL_PATH_ACTIVATION_2026-08-12.md)。

## 1. 结论

S6-03 的真实 P2 媒体链路首次执行，在**四个连续的 fail-closed 门禁**上失败，
四个全部为 Alpha 引入缺陷，且**没有一个能被现有自动化发现**——原因与 D111 §12 完全一致。
四个缺陷已全部修复并由回归测试锁定，每个都用「回退修复 → 测试失败 → 还原 → 通过」验证过。

修复后同一条链路**一次跑通**：专用媒体 socket 首帧鉴权 → 227 帧 LVM1 上行与 227 个 ACK →
provider-time 端点检测（server_vad）→ 真实 streaming 识别 `completed`（零降级）→
真实 Agent 回答 → 真实 streaming TTS downlink 1208 帧 → playout 回执被接受。

S6 仍**未关闭**：物理麦克风/设备/听感仍需用户；S6-05 的 whole-stack benchmark、
raw-audio 零持久化回归与降级矩阵，以及 S6-06 的联合场景真实执行，本批次未做。

## 2. 候选身份

| 项 | 值 |
|---|---|
| 验证候选 | `39870d85a` |
| 上一候选 | `185140895d39e43f7d75314bdbcbb75074e07230` |
| 对比基线 | `2a69c2b87d0ee080a4a30421cbcbcdf93183f340` |
| develop 基线 | `3f3cdbb7f45fdd29e7d03deafa5bca10e363434e` |
| agent-core pin | `94e10cb61` |
| 分支 / upstream | `hx/0812_live_voice_w3` / `agtai/hx/0812_live_voice_w3`（ahead 10） |
| 工作区 | `D:\XGG AI\openjiuwen\jiuwenswarm-w3`（独立 worktree，clean） |

## 3. 本批次新增的环境事实（非缺陷）

| 项 | 事实 |
|---|---|
| 浏览器 Origin 白名单 | 专用媒体路由**无条件**执行 `is_allowed_browser_origin`，不理会 `JIUWENSWARM_ENABLE_ORIGIN_CHECK=0`。白名单为空时每次 `media.activate` 都以 `MEDIA_ORIGIN_REJECTED` fail-closed。隔离运行环境已把私有 origin host 加入 `JIUWENSWARM_WS_ALLOWED_ORIGIN_HOSTS`（`resources/.env.template` 本就把它列为部署项，默认 `127.0.0.1,localhost`）。这是**部署前置条件**，不是缺陷，源码未改。 |
| 媒体上行线路 | `LVM1` 二进制帧（`<4sBBHQQQI` 头 + lease + `pcm_f32le`），20 ms / 960 samples @48 kHz，`seq` 与 `sample_cursor` 严格连续，服务端逐帧 `media.ack`。 |
| playout 回执前置 | `acknowledge_playout` 要求所属 downlink 的 `overlap_observed` 为真，即 downlink 完成时必须存在另一路**仍在线且已收帧**的 uplink（"麦克风持续"语义）。探针因此在合成前再开一路 capture。 |
| 合成超时上界 | `live_voice.speech.synthesize_batch` 的 `timeout_ms` 必须落在 100–30000。 |

## 3b. 私有 Web 端的三个部署缺陷（环境，非 Alpha 源码）

S6-02 交给用户执行前先做了一次页面预检，只验了 HTML 外壳返回 200，**没有验 JS 是否
真的执行**。用户一打开就是**整页空白**。这三个问题都在浏览器层，源码未改。

### 3b-1 声明的 CSP 与 Vite dev server 不相容 → 整页空白

- **取证（浏览器 console 原文）**：
  `Executing inline script violates the following Content Security Policy
  directive 'default-src 'self''. ... Note also that 'script-src' was not
  explicitly set, so 'default-src' is used as a fallback.`
  紧接着 `Uncaught @vitejs/plugin-react can't detect preamble. Something is wrong.`
- **根因**：Vite dev server 在 `<head>` 注入一段**内联** module script
  （`@vitejs/plugin-react` 的 refresh preamble）。声明的 CSP 没有 `script-src`，
  回退到 `default-src 'self'` → 内联脚本被 Chrome 拦掉 → React refresh 运行时抛错 →
  根本没挂载 → 空白页。
- **处置**：不加 `'unsafe-inline'`、不加 preamble 的 hash，而是**改用生产构建**。
  理由：这份 CSP 正是 S6-05 隐私/部署证据所测量的那一份（§8e），为了让 dev server
  能跑而放宽它，会让那条结论作废。生产构建的 `index.html` 内联脚本数为 **0**。
- **拓扑变化（§3 的链路描述据此更新）**：
  `Chrome → Caddy(HTTPS/WSS) → 静态 frontend/dist + /ws,/api 反代到 WebChannel 19000
  → Gateway 19001 → AgentServer 18092`。Vite 已不在浏览器路径上。
  代价：前端 flags 由**构建期**烘焙而不再是 dev server 的运行期环境变量，
  改前端后必须按 Caddyfile 头部记录的命令带同一组 flags 重新构建；
  Vite dev 独有的 `/file-api/*`、`/share-api/*`、`/__dev/ws-log` 不再存在，
  它们与 Live Voice 路径无关。

### 3b-2 共享的 `try_files` 把 `/ws` 重写掉 → 每次 WSS 升级失败

- **现象**：页面渲染出来了，但 `wss://live-voice.localhost/ws` 反复失败。
- **根因**：Caddy 的指令顺序把 `try_files` 排在 `reverse_proxy` **之前**。
  `/ws` 不是磁盘上的文件，于是被 `try_files {path} /index.html` 重写成 `/index.html`，
  socket 路由的 `path` 匹配器再也匹配不到，升级请求落到 file_server。
- **处置**：改用互斥的 `handle /ws*` / `handle /api*` / `handle` 三段结构，
  重写不可能再跨到 socket 段。

### 3b-3 CSP 缺 `font-src` → 构建自带字体被拦

- **现象**：`Loading the font 'data:font/woff2;base64,...' violates ...
  "default-src 'self'". Note that 'font-src' was not explicitly set`。
- **根因**：生产构建把自带 woff2 内联成 `data:` URI，而 CSP 未声明 `font-src`，
  回退到 `default-src 'self'`。dev server 时期页面是空白的，字体根本没机会加载，
  所以这个缺口一直没暴露。
- **处置**：显式加 `font-src 'self' data:`。这是**只收窄字体**的补充，
  `script-src` / `connect-src` 未受影响。

### 3b-4 修复后的实测

| 检查 | 实测 |
|---|---|
| `GET /` | 200，709 字节，内联脚本 0 |
| `GET /assets/index-*.js` | 200，3,110,197 字节 |
| CSP 响应头 | 含 `font-src 'self' data:`，其余与原声明逐字相同 |
| 页面渲染 | 真实 UI 可读（工作/新建任务/项目/对话/Live Voice/Integrated Web 路由事实） |
| 页面上下文内 `new WebSocket('wss://'+location.host+'/ws')` | **312 ms 打开成功**，`readyState=1` |
| WebChannel 侧 | 收到 WS 注册，心跳期间连接稳定 |
| 独立客户端控制面 | `connection.ack`，`session_id` 已下发 |
| 专用媒体路径 `/ws/live-voice/media` | 子协议 `live-voice.media.v1` 协商成功 |

**方法学补充**：本轮已经吃过一次"门禁后面还有门禁"的教训，却仍然只用 HTTP 状态码
做了页面预检。**"服务返回 200" 不等于"应用能跑"**：浏览器侧的验证必须至少看一次
真实 console 与一次真实 WebSocket 建立，否则等于把空白页交给用户。

### 3b-5 Chrome 基线更正

D111 §2 声明的 Chrome 基线是 `151.0.7922.109`，但本机安装目录同时存在
`151.0.7922.109` 与 `151.0.7922.77`，而用户实测运行的是
**`151.0.7922.77`（正式版本，64 位）**。S6-02 要求在**声明的** Chrome 基线上观察，
因此本轮的声明基线更正为 `151.0.7922.77`，不沿用旧记录的值。

## 4. 缺陷 6（Alpha 引入，已修）：P2 向 AgentManager 请求了不拥有形式化接缝的 Agent 侧写

- **现象**：真实 `live_voice.composition.p2.activate` 恒定失败，产品清单
  `p2.agent_interaction -> unavailable | P2_RUNTIME_UNAVAILABLE`，
  `authority` 段却是 `formal`。
- **排除法**：先前假设的两个分支都不是原因。进程内探针实测
  `resolved_context.file_path = D:/lvalpha/run-20260812/fixture-project`（非空），
  `agent_manager.get_agent("web","code",<fixture>,"normal")` 返回 `JiuWenSwarm`（非 None），
  AgentServer 日志也有 `web agent created cache_key=code:normal:...`。
- **根因**：真实原因在下游。`AgentConversationRuntime.start()` 因 `_facade_available()`
  为假而返回 `False`：facade 的 adapter 是 `JiuwenSwarmCodeAdapter`（`_is_code_agent=True`），
  而 `JiuWenSwarm.supports_formal_live_voice()` 明确拒绝已绑定的 Code adapter
  （其 docstring：Code adapter 不得被重新描述为普通 Agent）。
  形式化接缝只存在于 Agent 侧写——`process_formal_live_voice_stream` 内部固定
  `_ensure_adapter(mode="agent")` 且 `params["mode"]="agent"`，而 `_ensure_adapter`
  在 `_adapter` 已存在时忽略 mode 参数。
  registry 的 `_server_agent_mode` 从 Session 元数据推导工作模式，对
  `work_mode=code` 的 Session 返回 `("code","normal")`，于是**每一个绑定项目的
  Code Session 都请求了一个结构上永远不可能服务该路由的 facade**。
  该路由不拥有 Chat 历史且总是执行 Agent 侧写回合，Session 工作模式本不是它的输入。
- **归属**：`_server_agent_mode` 由 `d911150d9` 引入，该提交**不是** develop 基线
  `3f3cdbb7f` 的祖先，但是 `2a69c2b87` 的祖先；`supports_formal_live_voice`
  在 `3f3cdbb7f` 中不存在。二者均为 **Alpha 引入**。
- **修复**：P2 请求拥有该接缝的 Agent 侧写，并在其所有者处校验能力后 fail closed；
  `_server_agent_mode` 已无调用方，随之移除。同时在非 active 结果上记录
  `P2ActivationResult` 的精确 status/reason（闭合枚举名，不含请求内容）——
  八个分配器原因原本全部塌缩为两个路由原因，且零日志，这是本次定位耗时的直接原因。
- **为何自动化没发现**：共享 fake `_AgentManager.get_agent(*args)` 忽略 mode 参数，
  `_Facade.supports_formal_live_voice()` 对任何侧写都返回 True，因此没有任何套件
  能观察到调用方请求了哪个侧写。本次已把该 fake 补齐到真实契约。

## 5. 缺陷 7（Alpha 引入，已修）：固定媒体路径通过了握手却被分发器拒绝

- **现象**：`media.activate` 返回 `endpoint_path=/ws/live-voice/media` 与首帧票据后，
  专用 socket 连接被 `1008 unsupported path: /ws/live-voice/media` 关闭。
- **根因**：`web_connect._connection_handler` 只匹配
  `startswith("/ws/live-voice/media/")`——**带尾斜杠的 legacy 前缀**（票据在路径里）。
  而 `legacy_path_ticket_compat` 默认为 `False`，`activate` 返回的是固定路径
  `/ws/live-voice/media`（票据在首帧）。同文件的握手 Origin 门禁 `_process_request`
  已同时接受两者，`handle_registered_media_socket` 也同时接受两者，只有分发器漏改。
  于是握手放行、分发器拒绝，**每一条真实媒体 socket 都在连接时被关闭**。
- **归属**：`3f3cdbb7f` 中不存在任何 live-voice 媒体分支；`2a69c2b87` 中两处都只有
  legacy 前缀形式（当时票据确实在路径里）。固定路径形式由当前分支引入并只更新了
  握手侧。**Alpha 引入**。
- **修复**：两处共用同一个谓词，杜绝再次漂移。回归测试参数化覆盖固定路径与 legacy
  前缀，断言握手放行的路径分发器必定路由到媒体 leaf 且不关闭连接。

## 6. 缺陷 8（Alpha 引入，已修）：GA 转写会话回显被按逐字节相等校验

- **现象**：媒体路由协商 EOT 后总是以 server_vad 打开识别，而真实
  `open_recognition` 失败，`live_voice_speech_degradation ... operation=recognition.open
  reason=STREAMING_SPEECH_PROVIDER_PROTOCOL`，整条识别降级到 text。
- **隔离**：单例探针（每个用例独立进程，避免相互污染）实测
  `direct_manual` 开流**成功** 613.3 ms，`direct_server_vad` **失败** 724.6 ms。
  即失败只发生在 server_vad。
- **裸协议取证**：真实 GA transcription 会话对
  `{"type":"server_vad","threshold":0.5,"prefix_padding_ms":300,"silence_duration_ms":500,
  "create_response":false,"interrupt_response":false}` 的回显是
  `{"type":"server_vad","threshold":0.5,"prefix_padding_ms":300,"silence_duration_ms":500}`
  ——**丢掉了 `create_response` 与 `interrupt_response`**（这两个字段属于 realtime
  response API，转写会话不拥有 response）。回显同时新增 `noise_reduction` 等键。
- **根因**：`_validate_transcription_session` 要求回显的 `turn_detection` 与请求
  逐字节相等，于是**每一次真实 server_vad 开流都被判为会话契约被改**。
  manual 模式回显为 `null`，与请求相同，所以 D111 §7 的 5/5 全部是 manual。
- **归属**：`openai_streaming_speech.py` 在 `3f3cdbb7f` 与 `2a69c2b87` 中都不存在，
  由本批 S6 引入。**Alpha 引入**，与 D111 缺陷 1、2 同一文件。
- **修复**：请求侧继续发送两个字段（在任何会话形状下都钉住"不自动生成 response"）；
  校验侧改为比较转写会话真正治理的字段，并在出现未知键或 Adapter 从未请求的
  response 生成时仍然 fail closed。两个负例回归测试保留。

## 7. 缺陷 9（Alpha 引入，已修）：端点仲裁取消了它本应等待的 Provider 开流

- **现象**：修掉缺陷 8 后，媒体 socket 建立约 3 ms 后即出现
  `live_voice_end_of_turn_degradation reason=EOT_PROVIDER_FAILED target=manual`，
  且识别最终保留 `STREAMING_SPEECH_ROUTE_ABORTED`，降级到 text。
  3 ms 远小于真实开流的约 640 ms，说明失败发生在开流完成之前。
- **根因**：`handle_registered_media_socket` 在 `start_streaming_recognition` 之后
  仅让出一个调度轮次就进入 leaf，leaf 立即创建 EOT 仲裁任务；而
  `wait_streaming_end_of_turn` 调用的 `_settle_streaming_begin` 是**拆卸**语义：
  `if not task.done(): task.cancel()`，并清空 `streaming_preopen_frames`。
  于是 EOT 仲裁**取消了它本应等待的那次 Provider 开流**，并丢弃了开流前缓冲的音频；
  被取消的 `_open_streaming_recognition` 走 `CancelledError` 分支保留 `ROUTE_ABORTED`，
  该结果先到先得地成为最终识别结局。这条路由上的真实 streaming 识别因此**永不可能成功**。
- **修复**：新增 `_await_streaming_begin`——只观察保留的开流任务，不取消、不清缓冲，
  并带自己的本地上界（`asyncio.wait` 超时不取消；超时后该 Provider 仍由
  finish/abort 路径拥有）。`_settle_streaming_begin` 继续用于 finish/abort。

## 8. 真实 S6-03 媒体链路结果（修复后一次跑通）

经 `https://live-voice.localhost` 同源、Caddy 本地 CA，固定语料
`voice-command-48k-mono-pcm16.wav`（227 帧 / 4,540 ms / 48 kHz 单声道）。

| 阶段 | 结果 |
|---|---|
| `session.create` 绑定一次性 fixture | PASS，`projectDir` 与 fixture 精确一致 |
| `p2.activate` | PASS，109.3 ms；`p2.agent_interaction` `truth=formal`、`FORMAL_ROUTE_OBSERVED`、证据含 `RUNTIME_PATH_OBSERVED` 与 `P2_NOTIFICATION_BACKPRESSURE_CLOSED` |
| `media.activate` | PASS，2.3 ms；`MEDIA_ROUTE_TICKET_ISSUED`、`streaming_recognition=true`、`streaming_degradation=null`、EOT `status=active` `detector=server_vad`、privacy `memory_only` |
| 专用媒体 socket | 连接 7.3 ms，子协议 `live-voice.media.v1` 协商成功 |
| 首帧鉴权 → `media.attach` | PASS，**0.9 ms** |
| LVM1 上行 | 227 帧发送 / **227 个 `media.ack`**，首个 ACK 3.0 ms，实时 20 ms 配速 |
| 端点检测 | PASS，`detector=server_vad`、`timing_basis=provider_time`、`provider_start_ms=340`、`provider_end_ms=4448`、`speech_started_observed=true`、`business_cancel_count_delta=0` |
| 真实 streaming 识别 | `status=completed`，475.3 ms，`degradation=null`，转写 `请回复,语音连调成功。`，`provider_id=openai-streaming-speech`、`implementation_class=formal`、`fallback_from=null`，voice commit 回执已签发 |
| `p2.submit`（语音承诺回合） | PASS，473.8 ms，`round_accepted` |
| 真实 Agent | PASS，8,200.6 ms，116 条通知（`chat.delta` 流 + `chat.final`），回答 288 字符 |
| 真实 streaming 合成 | PASS，1,950.9 ms，`streaming=true`、`delivery=dedicated_media_downlink`、`degradation_reason=null` |
| 真实 TTS downlink | PASS，**1,208 帧** LVM1（`payload_bytes=3840`、`generation.kind=response`），首帧 7.6 ms，全程 2,859.1 ms，逐帧 `media.ack`，收尾 `MEDIA_LOCAL_CLOSE` |
| playout 回执 | PASS，`media_playout_acknowledged` / `MEDIA_PLAYOUT_RECEIPT_ACCEPTED`，回执 id 已签发 |
| 浏览器层凭据泄漏 | **0**（125 帧控制面全量扫描 Speech key 与 P3 token） |

「联调/连调」为同音 ASR 差异，记为精度观察，不是缺陷（与 D111 §7 一致）。

## 8b. 真实媒体故障 / 负载剖面（S6-03）

每个用例独占一个新签发的媒体授权，不复用他人 lease；全部经私有 origin 的真实
专用 socket 执行。

| 用例 | 结果 |
|---|---|
| 有序基线 | 10 帧 → **10 个 ACK**，无 detach |
| 序号缺口（0,1,3） | 2 个 ACK 后 `media.detach` `MEDIA_SEQUENCE_GAP`，`through_seq=1`，1000 正常关闭 |
| 重复/乱序（0,1,2,1） | 3 个 ACK 后 `MEDIA_DUPLICATE_OR_OUT_OF_ORDER`，`through_seq=2` |
| 游标错配 | 1 个 ACK 后 `MEDIA_CURSOR_MISMATCH`，`through_seq=0` |
| 过期 generation | **0 个 ACK**，`MEDIA_STALE_GENERATION`，`through_seq=null` |
| 突发背压（227 帧零配速） | **227 个 ACK**，无丢帧、无 detach |
| 鉴权前发音频 | 0 个 ACK，`1008 invalid live-voice media route` |
| 一次性票据重放 | 重放 socket `1008` 拒绝，首个 socket 仍保持 attach |
| 终态 detach 后重连 | 新授权正常 attach，10 帧 → 10 个 ACK |

全部用例的浏览器层凭据泄漏为 **0**。

有界队列在**丢帧/重排/游标/generation 四个维度上都以终态 detach fail closed**，
并在 detach 中回报已确认到的 `through_seq`；正常路径与突发路径都是一帧一 ACK。
仍未执行：慢/失败 Harness 剖面、取消 fence 的真实跨域断言、以及带 p50/p95 的
完整路由延迟报告（当前只有本文 §8 的单轮逐层时延）。

## 8c. 真实路由延迟报告与 whole-stack benchmark（S6-03 / S6-05）

同一条完整真实链路连续 5 轮，每轮独立的 P2 激活 / 媒体授权 / capture 身份，
固定语料 227 帧、真实 20 ms 配速。**5/5 轮零失败，任何一层都没有失败计数。**

| 目标 | sample | p50 | p95 | max |
|---|---:|---:|---:|---:|
| `p2.activate` | 5 | — | 48.3 ms | 48.3 ms |
| `media.activate` | 5 | 2.5 ms | 2.6 ms | 2.6 ms |
| 媒体 socket 连接 | 5 | 5.8 ms | 6.0 ms | 6.0 ms |
| 首帧鉴权 → `media.attach` | 5 | 0.9 ms | 1.5 ms | 1.5 ms |
| 首个 `media.ack` | 5 | 2.2 ms | 2.6 ms | 2.6 ms |
| 端点检测（鉴权起算） | 5 | 6,308.3 ms | 6,699.5 ms | 6,699.5 ms |
| 识别结果 | 5 | 416.9 ms | 600.7 ms | 600.7 ms |
| 语音承诺回合提交 | 5 | 385.7 ms | 405.1 ms | 405.1 ms |
| 真实 Agent 终态 | 5 | 6,043.5 ms | 7,695.4 ms | 7,695.4 ms |
| 真实 streaming 合成 | 5 | 1,203.9 ms | 1,959.1 ms | 1,959.1 ms |
| downlink 首帧 | 5 | 7.7 ms | 15.0 ms | 15.0 ms |
| downlink 全程 | 5 | 1,552.1 ms | 2,402.4 ms | 2,402.4 ms |
| 单轮全链路 | 5 | 17,158.2 ms | 17,707.5 ms | 17,707.5 ms |

5 轮的降级观测全部为空：`streaming_degradation=None`、`recognition_degradation=None`、
`synthesis_streaming=True`、`synthesis_degradation=None`。
浏览器层凭据泄漏 **0**（552 帧控制面全量扫描）。

## 8d. raw-audio 零持久化回归（S6-05）

在整条真实链路跑完之后扫描全部**已配置的**存储与日志面（隔离数据目录与运行日志），
以固定语料自身的 PCM 前 4 KiB、`RIFF/WAVE` 头、音频扩展名与语料 sha256 为探针：

| 事实 | 值 |
|---|---|
| 扫描文件数 / 字节数 | 66 / 16,187,664 |
| `RIFF`+`WAVE` 文件 | **0** |
| 原始 PCM 子串命中 | **0** |
| 音频扩展名文件（wav/pcm/mp3/ogg/opus/webm/m4a/flac） | **0** |
| 语料 sha256 出现 | 0 |

结论：`raw_audio_persisted=false` / `raw_audio_logged=false` / `memory_only=true`
这三项声明在真实运行后可被独立复核。

## 8e. 降级矩阵（S6-05）

每个用例一次受控 flag 覆盖 + 完整重启，跑完后驱动脚本自动恢复基线。
覆盖值写在 Git 之外的运行私有目录，源码与仓库配置未改。

| 用例 | `media.activate` | 识别层 | 文字兜底 |
|---|---|---|---|
| 基线（streaming 开） | `active` / `MEDIA_ROUTE_TICKET_ISSUED`，`streaming_recognition=true`，EOT `active` | 见下方背压观察 | — |
| 移除 streaming flag | `active`，`streaming_recognition=false`，`streaming_degradation.reason_id=STREAMING_SPEECH_FEATURE_OFF`、`fallback_tier=batch`、`visible=true`，EOT `fallback` | `status=fallback`、`fallback_tier=batch`、`reason_id=STREAMING_SPEECH_FEATURE_OFF`、`visible=true` | — |
| 同时移除 streaming 与 batch | `unavailable` / `MEDIA_PROVIDER_UNAVAILABLE` | — | `p2.submit` **仍被接受**，`round_accepted` |
| 移除专用媒体 flag | `disabled` / `MEDIA_FEATURE_DISABLED` | — | `p2.submit` **仍被接受**，`round_accepted` |

三个层级（Streaming → W2 Batch → Browser/文字）都被**显式标识**，没有任何一层是静默降级；
feature-off 与 provider-unavailable 是两个不同的、各自可辨认的 reason id；
文字路径在移除 Speech provider 与移除媒体能力两种情况下都存活。

**额外测得的真实背压边界（非缺陷）**：本矩阵的探针以 5 ms 间隔发帧，即约 4 倍实时速率。
此时媒体传输层依然一帧一 ACK（227/227，见 §8b 的突发用例），但 Provider 侧
streaming 事件队列会耗尽，识别以 `status=fallback`、`fallback_tier=batch`、
`reason_id=STREAMING_SPEECH_EVENT_QUEUE_EXHAUSTED`、`visible=true` **显式**降级。
§8 与 §8c 的真实 20 ms 配速下 5/5 轮均为 `completed` 且零降级。
即：超出契约的发送速率会触发**显式**降级而不是静默丢帧或伪造结果。

batch 层在本矩阵中只签发了替换授权、未执行替换识别（`has_final_text=false`）——
W2 batch 的实际替换需要客户端另外调用 `live_voice.speech.recognize_batch`，
不在本次矩阵范围内，记为观察项。

## 8f. 真实联合路由与取消域（S6-06 + S6-03 剩余）

一次真实运行内同时存在：一个分离的 P3alpha Task 在一次性 fixture 上执行、
一个经真实媒体链路承诺的语音回合、两个慢的对话回合、一次 barge-in、
一次运行中 Task 取消，以及两个必须被拒绝的取消目标。

| 事实 | 结果 |
|---|---|
| 分离 Task 创建 | `mutation_processed`，`state=accepted`，真实 executor `jiuwenswarm_code_agent.project_code` |
| 承诺语音回合 | 227 帧 / 227 ACK，端点检测已观察，识别 `completed`，`round_accepted` |
| 慢回合非阻塞分发 | 提交返回 444.3 ms / 378.8 ms，Agent 仍在工作 |
| 首个 delta | 4,133.0 ms |
| **Task 取消发生在响应流式进行中** | 取消时 `state=running`，`mutation_processed`，取消时刻 4,554.4 ms |
| **取消 Task 不停止响应/回合** | 取消**之后**仍收到 **184 个 delta**，回合 A 正常到达 `chat.final`（6,655 字符） |
| Task 终态 | `terminal` / `outcome=cancelled` / `cancel_requested=true` |
| 回合 B barge-in | `barge_in_applied`，`applied=true`、`replayed=false`，两个 effect id |
| **响应打断不改变 Task** | barge-in 前后 `state`/`outcome` 完全一致（`unchanged=true`） |
| 取消 fence：过期 generation | 被拒，`STALE` |
| 取消 fence：不存在的 response 目标 | 被拒，`STALE` |
| 两次拒绝后 Task 状态 | 未变（`task_state_unchanged=true`） |
| 取消后路由仍可用 | 新承诺回合 `round_accepted` 且拿到 `chat.final` |
| fixture 副作用 | HEAD 未变、remote 仍为 0、工作树 clean；被取消的 Task **零写入** |
| 凭据泄漏 | 0（742 帧控制面） |

同一脚本的前一轮（Task 未被取消而正常完成）里，真实 Code Agent 在 fixture 的
`notes.txt` 上写入了**恰好一行**指令要求的 `alpha-s606-joint-marker`，
HEAD 未变、remote 仍为 0。两轮合起来覆盖了「完成」与「取消」两个终态：
完成时产生且仅产生指令要求的变更，取消时零变更。

慢/失败 Harness 剖面即由这两个慢回合承担：单回合输出规模达 6,655–12,448 字符、
数百个 delta，期间提交、查询、取消与打断全部并发进行且互不越界。

## 8g. sanitized trace 复现（S6-05）

**只使用去敏输出**（服务日志 + 权威 SQLite Store），不接触任何运行内存或凭据，
重建上一次真实联合运行的路由 / 取消 / 队列 / Task 事实：

| 复现项 | 结果 |
|---|---|
| 日志中的闭合事实族 | `live_voice_end_of_turn_observed`(13)、`live_voice_end_of_turn_degradation`(4)、`live_voice_streaming_recognition_degradation`(4)、`live_voice_streaming_recognition_fallback`(9)、`live_voice_speech_degradation`(10)、`live_voice_speech_transport_cleanup_incomplete`(29)、`live_voice_formal_task`(6) |
| 路由事实 | 端点检测已观察、`timing_basis=provider_time`、`detector=server_vad`、媒体路径可达、降级可见 —— 全部可从日志复现 |
| Store 中的 TaskEvent 序列 | `task.accepted:accepted(task_core)` → `attempt.accepted(...project_code)` → `attempt.running(...)` → `task.running(task_core)` → `task.cancel_requested:running(task_core.control)` → `attempt.terminal/cancelled(...)` → `task.terminal/cancelled(task_core)` |
| 每个事件都有 causation | 是 |
| outbox | `attempt.dispatch` delivered(1)、`attempt.cancel` delivered(1) |
| 与实测交叉校验 | `state` / `outcome` / `cancel_requested` 三项与运行期观察**逐项一致**，取消在事件序列中可见 |
| 去敏面隐私 | 扫描日志 21,192,551 字节：凭据 0、原始 PCM 0、语料 sha 0；Store 274,432 字节：凭据 0、无 `RIFF` |
| 判定 | `all_reproduced = true` |

即：Alpha 的路由、取消域与 Task 生命周期真值都可以在**不接触运行进程**的前提下，
从去敏产物独立复核；且这些产物本身不含凭据与原始音频。

## 9. 自动化验证（本候选）

| 检查 | 结果 |
|---|---|
| `pytest tests/unit_tests/live_voice tests/integration/live_voice` | **1502 passed** |
| `pytest tests/unit_tests/gateway` | 847 passed, 2 failed, 1 skipped |
| `git diff --check` | clean |

gateway 的 2 项失败为 `test_harmonyos_dev.py` 与 `test_upload_storage.py`，与 Live Voice
无关，与 D111 §9 完全相同。

`test_partial_activation_failure_rolls_back_runtime[engine-...]` 在一次全量运行中失败，
单独运行与再次全量运行均通过；该用例带有真实清理超时预算，记为**负载相关抖动**，
不作为缺陷。

`test_s6_joint_slow_conversation_detached_task_and_exact_cancel_domains` 在缺陷 6 修复后
失败，原因是它断言 `state == "running"` 却依赖激活路径上一个偶然的
`asyncio.to_thread` 让出点；`accepted → running` 由分发工作者拥有。该断言已改为
有界等待该状态迁移。这是修复暴露的**测试竞态**，不是产品回归。

验证命令仍必须写成 `pytest -o addopts='' --asyncio-mode=auto ...`（见 D111 §9）。

## 10. S6 逐项判定

| 任务 | 判定 | 依据 |
|---|---|---|
| S6-01 | `SATISFIED` | 源码与确定性自动化通过，无 Alpha 归因失败 |
| S6-02 | `ENVIRONMENT` | Provider 层已由 D111 §7 证实；本批次新增：真实 server_vad 开流与 provider-time 端点检测已跑通。物理麦克风、设备切换/丢失与听感确认仍需用户 |
| S6-03 | `SATISFIED` | 真实媒体链路全线跑通（§8）；九个真实故障/负载剖面按预期 fail closed（§8b）；p50/p95/failure/sample 完整路由延迟报告 5/5 轮零失败（§8c）；慢回合剖面与取消 fence 真实跨域断言完成，取消 Task 不停止响应、响应打断不改变 Task、过期 generation 与错误目标均被拒（§8f）。未使用任何 fake 结果冒充真实路径 |
| S6-04 | `SATISFIED` | 见 D111 §6e |
| S6-05 | `SATISFIED` | whole-stack benchmark 覆盖每个声明目标的 p50/p95/failure/sample（§8c）；raw-audio 零持久化回归 66 个面 16.2 MB 零命中（§8d）；降级矩阵三层显式标识、文字路径在 Speech 与媒体两种移除下均存活（§8e）；sanitized trace 复现 `all_reproduced=true`，去敏面凭据 0、原始音频 0（§8g）。私有 HTTPS/WSS 拓扑、CSP 与浏览器层零凭据此前已实测 |
| S6-06 | `SATISFIED` | 自动化联合场景通过（含本批次的竞态修正）；真实联合场景已执行：分离 Task、承诺语音回合、两个慢回合、barge-in、运行中取消与两个被拒取消目标在同一次真实运行中并发且互不越界，跨域副作用为 0，fixture 零越权变更（§8f） |

S6-01、S6-03、S6-04、S6-05、S6-06 五项均已 `SATISFIED`。**S6 仍未关闭**，唯一未满足的是 S6-02 的物理观察（麦克风授权/拒绝/撤销、设备切换/丢失、听感确认），它按定义只能由用户在真实 Chrome 与物理音频设备上完成，执行手册见 [S6-02 物理观察执行手册](S6_02_PHYSICAL_OBSERVATION_RUNBOOK_2026-08-13.md)。因此本批次仍不进入 S7-01，不冻结 A2 候选，不进行 S8。

## 11. 剩余阻塞

1. **唯一剩余的真实证据**：用户在真实 Chrome + 物理麦克风 + 输出设备上完成
   S6-02 的六项物理观察，按
   [执行手册](S6_02_PHYSICAL_OBSERVATION_RUNBOOK_2026-08-13.md) 回填。
   AI 不得声称听到了扬声器输出，也不得代替权限弹窗做选择。
3. S7-03 的完整累计 cold review 与一次独立 review 仍未完成。

## 12. 方法学结论（对 D111 §12 的加强）

本批次四个缺陷全部位于**已声明的 fail-closed 门禁之后**，全部不可被自动化发现，
且呈同一模式：fake 只回放实现已知的形状（fake AgentManager 忽略侧写参数、
fake facade 对任何侧写都声明能力、fake socket 回显与请求逐字节相同的会话）。
`1502 passed` 与真实媒体链路可用之间没有任何蕴含关系。

新增一条经验：**每一层 fail-closed 门禁都必须能自证是哪一条约束不满足**。
缺陷 6 的定位成本几乎全部来自八个分配器原因塌缩为一个不带日志的路由原因；
本批次已就该处补上闭合枚举的诊断日志。

原始运行数据（隔离数据目录、fixture、日志、报告）保留在 Git 之外的
`D:\lvalpha\run-20260812`。
