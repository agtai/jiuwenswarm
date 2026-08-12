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
| S6-03 | `ENVIRONMENT` | 真实媒体链路（首帧鉴权 → LVM1 上行/ACK → 真实 STT → 真实 Agent → 真实 TTS downlink → playout ACK）已首次跑通并给出逐层时延；有界队列/背压/丢包/重排/断连重连、慢 Harness、取消 fence 与完整路由延迟报告尚未执行 |
| S6-04 | `SATISFIED` | 见 D111 §6e |
| S6-05 | `ENVIRONMENT` | whole-stack benchmark、raw-audio 零持久化回归与降级矩阵未执行 |
| S6-06 | `ENVIRONMENT` | 自动化联合场景通过（含本批次的竞态修正）；真实联合场景未执行 |

**S6 未满足退出条件**，故本批次不进入 S7-01，不冻结 A2 候选，不进行 S8。

## 11. 剩余阻塞

1. 用户在真实 Chrome + 麦克风 + 输出设备上完成 S6-02/03/06 的物理与听感确认。
2. S6-03 剩余的故障/负载剖面与完整路由延迟报告；S6-05 的 whole-stack benchmark、
   raw-audio 零持久化回归与降级矩阵；S6-06 的真实联合慢回合 + 分离 Task 场景。
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
