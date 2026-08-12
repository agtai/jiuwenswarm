# D111 Alpha 真实路径激活与真实 Provider 缺陷修复 — 2026-08-12

> 本文是一次性验证记录，记录在 `hx/0812_live_voice_w3` 上首次把 Alpha 真实环境
> （Speech 凭据 + 私有 HTTPS/WSS + 隔离运行时 + 一次性 Git fixture）全部装配起来
> 并跑通真实链路的结果。当前可变状态仍只由 [STATUS.md](STATUS.md) 拥有。
> 本文**不产生**新的 Alpha 验收结论，S6 未关闭。

## 1. 结论

[D110](D110_ALPHA_AUTOMATED_VERIFICATION_AND_ENVIRONMENT_BLOCK_2026-08-12.md)
记录的两个外部阻塞条件（Speech 凭据、私有 HTTPS/WSS）本批次已解除，真实路径首次
执行。执行立刻暴露 **4 个 Alpha 源码缺陷**和 **1 个 develop 既有运行期阻塞缺陷**，
全部为自动化测试无法发现的类型。四个 Alpha 缺陷已全部修复并由回归测试锁定，
每个都用「回退修复 → 测试失败 → 还原 → 测试通过」验证过测试确实有效。

修复后，真实 Streaming STT/TTS 与真实 P3alpha Executor 垂直**均已跑通**：
识别与合成各 5/5，形式化任务真实分发并 `terminal/completed`，真实 Code Agent 在
一次性 fixture 上产生了指令要求的确切变更且跨项目副作用为 0。

S6 仍**未关闭**：物理麦克风、设备切换与听感确认必须由用户在真实 Chrome 上完成，
S6-03/S6-05/S6-06 的真实测量尚未执行。因此未进入 S7，未执行 S8。

## 2. 候选身份

| 项 | 值 |
|---|---|
| 验证候选 | `3583c0fe2`（真实路径修复批次的最后一个提交） |
| 上一候选 | `82b2cc5f629e518d8631975517b72330f9c4992f` |
| 对比基线 | `2a69c2b87d0ee080a4a30421cbcbcdf93183f340` |
| develop 基线 | `3f3cdbb7f45fdd29e7d03deafa5bca10e363434e` |
| 分支 / upstream | `hx/0812_live_voice_w3` / `agtai/hx/0812_live_voice_w3`（ahead 8） |
| 累计 diff | 91 files, +45,044 / −1,159 |
| Python / Node / Chrome | 3.12.11 / v24.18.1 / 151.0.7922.109 |
| Vite | 5.4.21 |
| 工作区 | `D:\XGG AI\openjiuwen\jiuwenswarm-w3`（独立 worktree，clean） |

## 3. 本批次装配的真实环境

机器私有值不入 Git，只记录存在性与去敏标签。

| 项 | 事实 |
|---|---|
| Speech 凭据 | 六个 `LIVE_VOICE_SPEECH_*` 为 Windows 用户级环境变量；服务进程从注册表读入 |
| Speech 目标 | STT `gpt-4o-mini-transcribe-2025-12-15`、TTS `gpt-4o-mini-tts-2025-12-15`、voice `marin`、官方 OpenAI origin |
| 私有 origin | `https://live-voice.localhost` → Caddy v2.11.4（仅绑 127.0.0.1）→ Vite 5173 |
| 反代链 | `Chrome → Caddy(HTTPS/WSS) → Vite → WebChannel 19000 → Gateway 19001 → AgentServer 18092` |
| CSP | `default-src 'self'; connect-src 'self' wss://live-voice.localhost; media-src 'self' blob:; worker-src 'self' blob:` |
| 隔离运行时 | 新建空目录 `JIUWENSWARM_DATA_DIR`，未复用默认用户目录，未使用 `-Force` |
| 隔离 P3 Store | `<data>/live_voice/p3alpha/formal_tasks.sqlite3`（应用自有目录约束内） |
| 一次性 Git fixture | 新建本地仓库，**无 remote、无推送凭据、无用户数据**，seed 提交后 clean |
| Executor 目标 | 该 fixture；JiuwenSwarm 源码仓库与用户项目均未作为目标 |
| 外部 channel | 隔离配置中 feishu/slack/dingtalk 等全部 `enabled: false`，仅保留 `web` |
| Agent Provider 标签 | `deepseek-v4-flash`（去敏标签，不记录 key/base） |

后端 flags：`P3_ENABLED`、`PRODUCT_COMPOSITION_ENABLED`、`PRODUCT_P2_ENABLED`、
`PRODUCT_P3_TEXT_ENABLED`、`PRODUCT_P3_MUTATION_ENABLED`、`CRITICAL_INPUT_ENABLED`，
加私有 token / principal / 注册的一次性 project ID / 未来 UTC 到期时间。
Gateway flags：`LIVE_VOICE_FORMAL_STREAMING_SPEECH_ENABLED`、
`LIVE_VOICE_FORMAL_BATCH_SPEECH_ENABLED`、`DEDICATED_MEDIA_ENABLED`、
`END_OF_TURN_ENABLED`、`WEB_ALPHA_CREDENTIAL_ENABLED`，与 AgentServer 同一 token。
前端 flags：`INTEGRATED_WEB` / `INTEGRATED_P1` / `PRODUCT_P3_MUTATION` = true；
`TASK_DEMO` 与 `STREAMING_SPEECH` 均未设置。Vite 进程环境不含任何 `LIVE_VOICE_SPEECH_*`。

路线激活不以环境变量为准，而由下列实际事实证明：

- AgentServer 日志 `[LiveVoiceP3] authenticated formal route ready`（mutation authority 已就绪）；
- AgentServer 日志 `[LiveVoiceProduct] central composition registered; p2=True p3_text=True`；
- Gateway 日志收到 AgentServer `connection.ack {"status":"ready"}`；
- 浏览器层 WSS 首帧 `connection.ack`（253.6 ms）；
- `session.create` 返回的 `projectId`/`projectDir` 与注册的一次性 fixture 精确一致；
- 真实 Terminal Tool 返回 fixture 仓库自身的 `## main` 与 clean 工作树；
- Provider capability 实测 `transport=native_stream`、`native_partials=provider_native`。

## 4. 缺陷 1（Alpha 引入）：GA transcription item 生命周期事件被判为未知事件

- **现象**：真实 realtime STT 在 `input_audio_buffer.commit` 之后立即失败，
  降级事实 `STREAMING_SPEECH_PROVIDER_PROTOCOL`，streaming → text。
- **根因**：真实 GA `intent=transcription` 会话在 `input_audio_buffer.committed`
  与转写事件之间发送 `conversation.item.added` 与 `conversation.item.done`，
  且**不再**发送已退役的 beta 名 `conversation.item.created`。Adapter 的无害观察
  白名单只有旧名，于是抛 `SPEECH_PROVIDER_UNKNOWN_EVENT`，**每一次真实识别都失败**。
- **裸协议取证**：manual 与 server_vad 两种模式各抓一次完整 wire 序列，实际事件集为
  `session.created`、`session.updated`、（server_vad 时）`input_audio_buffer.speech_started`、
  `input_audio_buffer.speech_stopped`、`input_audio_buffer.committed`、
  `conversation.item.added`、`conversation.item.done`、
  `conversation.item.input_audio_transcription.delta`、`...completed`。
- **修复**：把两个 GA 名加入无害观察白名单。二者的 id 在 `item.id` 而非顶层 `item_id`，
  而本流的 committed 身份已由 `input_audio_buffer.committed` 绑定，因此不改变输出真值。
- **为何自动化没发现**：streaming 的全部 socket 都是 fake，只回放 Adapter 已知的事件。

## 5. 缺陷 2（Alpha 引入）：超时的传输关闭被取消，导致清理槽位永久泄漏

- **现象**：每次识别终态后 `live_voice_speech_transport_cleanup_incomplete
  kind=socket reason=timeout`，`provider.close()` 抛 `SPEECH_PROVIDER_CLEANUP_INCOMPLETE`。
- **根因**：`_TransportCleanupOwner.attempt()` 的预算是 50 ms，而真实 WebSocket
  close 握手需要一次网络往返，**永远**不可能在预算内完成。超时分支执行了
  `task.cancel()`；被取消的清理会被 `_release` 记入 `_failed` 且不再自动回收。
  于是每条流永久占用一个清理槽位，`MAX_INCOMPLETE_TRANSPORT_CLEANUPS = 32`
  在约 15 次识别后触发 `SPEECH_PROVIDER_CLEANUP_CAPACITY`，**STT 路由整体不可用**；
  同时被取消的 close 让传输处于半开状态。
- **修复**：超时分支不再取消任务，仅结束调用方等待。调用方仍是硬有界的，owner
  继续持有该任务；close 完成后槽位正常释放。`close()` 时的取消是整体关闭语义，保留不变。
- **实测**：修复后 5 轮真实识别的 `retained` 稳定在 1–2、`failed` 恒为 0，不再累积。

两个缺陷各有一个回归测试，且已用「回退修复 → 测试失败 → 还原 → 测试通过」验证其有效性
（`test_ga_transcription_item_lifecycle_events_do_not_fail_the_stream`、
`test_slow_transport_close_finishes_and_releases_its_cleanup_slot`）。
修复提交为 `31ee31abb`。

## 6. 缺陷 3（develop 既有，非 Alpha 范围，未修）

- **现象**：任何 `chat.send` 在 AgentServer 侧直接失败：
  `Processor 'ReasoningToolLoopCompactProcessor' does not exist in preset`。
  这不是静态检查问题，而是**运行期阻断全部 Agent 会话**。
- **归属**：`jiuwenswarm/resources/config.yaml` 的
  `react.context_engine_config.reasoning_tool_loop_compact_config`（`enabled: true`）
  与 `interface_deep.py:950` 的 processor 注册，均由 develop 提交
  `b06ff06d0 fix(harness)`（2026-07-14）引入；该提交是 develop 基线 `3f3cdbb7f` 的祖先。
  三个 ref（`3f3cdbb7f`、`2a69c2b87`、当前候选）的这两处内容完全相同，而 pin 的
  agent-core `94e10cb61` 中不存在该 processor。同批比对的
  `MessageSummaryOffloader` / `DialogueCompressor` / `CurrentRoundCompressor` /
  `RoundLevelCompressor` 四个 processor 均存在。
- **处置**：与 D110 §8 的 `app_gateway.py:974` F821 同类，**非本次范围，不修源码**。
  隔离运行环境通过用户配置把
  `react.context_engine_config.reasoning_tool_loop_compact_config` 置为 `null` 解除阻塞
  （配置深度合并只在用户值非 dict 时整体覆盖）。源码未改动。

## 6b. 缺陷 4（Alpha 引入，已修）：P3 模型构造调用了不存在的方法

- **现象**：真实 P3alpha 分发在一次性 fixture 上 **3/3 全部失败**。权威 Store 里
  outbox `state=suppressed`、`last_error=P3_MODEL_UNAVAILABLE`，attempt 与 task
  均为 `terminal/failed`，**项目零副作用**（HEAD 不变、remote 仍为 0、工作树无变化）。
- **根因**：`agent_ws_server._build_live_voice_p3_model` 调用
  `JiuWenSwarmDeepAdapter._build_model_from_entry`，该属性**不存在**。runtime 导出的是
  模块级公开函数 `build_model_from_entry`（`interface_deep.py:793`，其 docstring 明确
  说明 deep adapter / 模型缓存 / 图像模态预热共用这一份实现）。
  AttributeError 被模型解析吞掉，只以 `P3_MODEL_UNAVAILABLE` 这一 capability 错误浮现。
- **归属**：`_build_live_voice_p3_model` 在 develop 基线 `3f3cdbb7f` 中**不存在**，
  只在对比基线 `2a69c2b87` 与当前候选中存在，因此是 **Alpha 引入**；
  `build_model_from_entry` 在三个 ref 中一直同名存在。
- **为何自动化没发现**：全部 P3 套件使用 fake model resolver，从不真的构造模型。
  这是本轮第三次出现同一模式。
- **修复**：改调模块级函数。修复后同一真实分发越过模型构造，失败推进到下一层
  `EXECUTOR_CAPABILITY_UNAVAILABLE`（见 §11）。提交 `44b275d5d`，回归测试断言
  调用确实到达模块级函数且参数原样透传，回退修复即失败。

## 6d. 缺陷 5（Alpha 引入，已修）：分发读取纯访问器而非构建 Agent 句柄

- **现象**：越过缺陷 4 后，真实分发仍全部失败于
  `EXECUTOR_CAPABILITY_UNAVAILABLE: project dispatch requires a task-scoped
  execution Agent`（`project_code_executor.py:235` 的 `execution_agent is None`）。
  日志显示 `live_voice_formal_task agent created`，即 Agent 本身创建成功。
- **根因**：`AgentManagerProjectBindingResolver._resolve_transition` 用
  `agent.get_instance()`。该方法在 `interface.py:3172` 是纯访问器，其 docstring 明确写着
  「may return None before the root DeepAgent has been built; callers that need a live
  handle outside the chat path should await `ensure_instance` instead」。
  形式化任务正是这种调用方：它分发到一个刚创建、从未经历 chat turn 的项目 Agent 上。
- **修复**：改为 `await agent.ensure_instance()`。
- **为何自动化没发现**：覆盖该路径的全部 fake 只定义了 `get_instance`，不实现真实 facade
  的 `ensure_instance`，因此任何套件都观察不到差异。本次已把这些 fake 补齐到真实契约，
  回归测试才具备意义。提交 `3583c0fe2`。

## 6e. 真实 Executor 执行结果（S6-04 关键证据）

修复后同一真实分发**首次成功**：

| 事实 | 值 |
|---|---|
| outbox | `state=delivered`，`last_error=None` |
| task | `state=terminal`，`outcome=completed` |
| 一次性 fixture 工作树 | 已变化 |
| 实际写入 | `notes.txt` 新增恰好一行 `alpha-s6-executor-marker`（与指令一致） |
| fixture HEAD | 未变（未产生意外提交） |
| fixture remote | 仍为 0 个 |
| 跨项目副作用 | 0 |

同一 Store 中并存 3 个先前 `terminal/failed` 的任务，其 outbox 为 `suppressed`
且项目零副作用——fail-closed 与成功路径在同一权威账本上可对照。

## 6c. P3alpha 真实垂直已证实的正向事实

即使分发最终失败，下列产品权威事实由真实运行与权威 SQLite Store 共同证明：

- `live_voice.composition.p3.confirmation.issue` 正常签发，返回 `confirmation_id`
  与 `expires_at`，`replayed=false`；
- `live_voice.composition.p3.mutate` 返回 `mutation_processed`，并带回形式化 Task Core
  自有的 `task_id` / `attempt_id` / `outbox_id` / `state=accepted`；
- Store 中 TaskEvent 序列完整且是唯一生命周期真值：
  `task.accepted`(producer=`task_core`) → `attempt.terminal` → `task.terminal`
  (producer=`task_core.delivery`)，`causation_id` 指向对应 outbox/command；
- attempt 记录 `executor_id=jiuwenswarm_code_agent.project_code`、`attempt_number=1`；
  outbox `kind=attempt.dispatch`、`delivery_count=1`；commands 表持有幂等指纹；
- scope 精确绑定 `project_id` + `session_id` + `assurance=authenticated`；
- **重放保护实测有效**：脚本两次运行复用同一 `request_id` 但内容不同时，服务端返回
  `P3_CONFIRMATION_BINDING_MISMATCH / PERMISSION_DENIED`，正确拒绝；
- **终态不可取消实测有效**：对已 terminal 的任务发 `task.cancel` 返回
  `TASK_ALREADY_TERMINAL / CONFLICT`；
- **session scope 隔离实测有效**：换一个 session 后 `task.list` 返回 0 条，
  旧 session 的任务不可见；
- 全程浏览器层 42 帧扫描 Speech key 与 P3 token，**0 泄漏**。

## 7. 真实 Speech 结果（S6-02 Provider 层）

固定语料 `voice-command-48k-mono-pcm16.wav`（4,523 ms，口令「请回复：语音联调成功。」），
5 轮，官方 OpenAI origin。

| 指标 | sample | p50 | p95 | max |
|---|---:|---:|---:|---:|
| STT open | 5 | 642.1 ms | 708.7 ms | 708.7 ms |
| STT first partial（commit 起算） | 5 | 530.8 ms | 678.3 ms | 678.3 ms |
| STT final（commit 起算） | 5 | 850.4 ms | 960.2 ms | 960.2 ms |
| TTS first chunk | 5 | 1,074.4 ms | 2,017.5 ms | 2,017.5 ms |
| TTS completed | 5 | 1,741.8 ms | 3,093.7 ms | 3,093.7 ms |

- STT success 5 / 5，failure 0；每轮 7–8 个 partial；`timing_basis=exact_source_cursor`。
- 转写样本：`请回复语音联调成功。` / `请回复语音连调成功`（「联调」「连调」为同音 ASR 差异，
  记为 ASR 精度观察，不是缺陷）。
- TTS success 5 / 5，failure 0；每轮 6–8 个 chunk，2,150–2,800 ms 音频。
- 去敏 Provider 标签：`provider_id=openai-streaming-speech`、`implementation_class=formal`。
- 能力事实：recognition `transport=native_stream`、`native_partials=provider_native`、
  `server_vad=provider_native`、`provider_cancel_ack=unavailable`；synthesis
  `transport=native_stream`、`chunk_text_spans=unavailable`、`provider_cancel_ack=unavailable`。
  实测 chunk 未携带 text span，与 capability 的 `unavailable` 声明一致——这是
  **显式声明的能力缺口**，不是隐藏降级；是否作为 Alpha 接受偏差需在 A2 判定。
- 成本：5 轮 STT + 5 轮 TTS，音频量约 23 s + 12 s，远低于 D-078 的 $5–10 月度上限。

`provider.close()` 仍会因 100 ms 的整体关闭预算而报保留清理，这是有意的硬有界关闭语义，
不影响业务输出；记为观察项。

## 8. 真实产品链路结果

经 `https://live-voice.localhost` 同源、使用 Caddy 本地 CA（未使用任何跳过校验的开关）：

| 检查 | 结果 |
|---|---|
| WSS 同源握手 + `connection.ack` | PASS，253.6 ms |
| `session.create` 绑定一次性 fixture | PASS，`projectId`/`projectDir` 精确一致，非 `new` |
| 文字强制 Terminal Tool smoke | PASS，4,262.8 ms，`tool_call=1`、`tool_result=1`、`final=1` |
| 工具真实副作用 | 返回 fixture 自身 `## main` 与 clean 工作树 |
| 浏览器层凭据泄漏 | 0（124 帧全量扫描 Speech key 与 P3 token） |

## 9. 自动化验证（本候选）

| 检查 | 结果 |
|---|---|
| `pytest tests/unit_tests/live_voice tests/integration/live_voice` | **1496 passed**（含 2 个新回归测试） |
| `pytest tests/unit_tests/gateway` | 845 passed, 2 failed, 1 skipped |
| `pytest tests/unit_tests/live_voice/test_openai_streaming_speech.py` | 61 passed |
| `git diff --check` | clean |

gateway 的 2 项失败为 `test_harmonyos_dev.py` 与 `test_upload_storage.py`，与 Live Voice 无关。

**验证命令陷阱**：`pytest.ini` 把 `--asyncio-mode=auto` 放在 `addopts` 里，
常用的 `-o addopts=''` 会连它一起清除，导致所有未显式标记的 async 测试报
`async def functions are not natively supported`。实测该误用会把 live_voice 从
1496 passed 变成 26 failed、gateway 从 2 failed 变成 15 failed。
后续验证必须写成 `pytest -o addopts='' --asyncio-mode=auto ...`。

## 10. S6 逐项判定

| 任务 | 判定 | 依据 |
|---|---|---|
| S6-01 | `SATISFIED` | 源码与确定性自动化通过，无 Alpha 归因失败 |
| S6-02 | `ENVIRONMENT` | 真实 Streaming STT/TTS 已首次跑通并给出 p50/p95/failure/sample；物理麦克风、设备切换与听感确认仍需用户 |
| S6-03 | `ENVIRONMENT` | 真实 Agent/Tool 文字路径已验证；P2 真实媒体、故障/负载与延迟测量未执行 |
| S6-04 | `SATISFIED` | 授权、确认、命令幂等、TaskEvent 权威、outbox、scope 隔离、重放与终态保护均在真实运行中证实；修掉缺陷 4、5 后真实 attempt 首次成功分发并 `completed`，真实 Code Agent 在一次性 fixture 上产生了指令要求的确切变更，跨项目副作用为 0（见 §6e） |
| S6-05 | `ENVIRONMENT` | 私有 HTTPS/WSS 同源拓扑已建立并实测；whole-stack benchmark、raw-audio 零持久化回归与降级矩阵未执行 |
| S6-06 | `ENVIRONMENT` | 依赖 S6-02/03/05 的剩余真实路径 |

**S6 未满足退出条件**，故本批次不进入 S7-01，不冻结 A2 候选，不进行 S8。

## 11. 剩余阻塞

1. 用户在真实 Chrome + 麦克风 + 输出设备上完成 S6-02/03/06 的物理与听感确认。
2. S6-03 的真实 P2 媒体/故障/负载测量；S6-05 的 whole-stack 隐私与降级回归；
   S6-06 的联合慢回合 + 分离 Task 场景（其 P3 侧前提已由 §6e 打通）。
3. S7-03 的 45,044 行完整累计 cold review 与一次独立 review 仍未完成（D110 §10 已记，本批次未推进）。

## 12. 本批次的方法学结论

五个真实路径缺陷（GA 事件白名单、清理槽位泄漏、P3 模型构造、分发 Agent 句柄，
以及 develop 既有的 processor 缺失）中，四个 Alpha 归因缺陷**没有一个**能被现有自动化发现，原因完全一致：streaming 的
socket、P3 的 model resolver 与 executor 都是 fake，只回放实现已知的形状。
`4731 passed` 与真实链路可用之间没有任何蕴含关系。

因此后续任何「真实路径」判定都必须绑定真实 Provider/设备/网络/Executor 的运行证据，
并优先以权威 Store（SQLite）与去敏日志作为事实来源，而不是产品响应信封的字段。

任一缺失都不得关闭 S6，也不得据此给出 Alpha PASS。原始运行数据（隔离数据目录、
fixture、日志、报告）保留在 Git 之外的 `D:\lvalpha\run-20260812`。
