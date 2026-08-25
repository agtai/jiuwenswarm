# OpenAI Realtime Native Interaction Engine 设计

- 日期：2026-08-25
- 状态：Accepted design；implementation 尚未开始
- 风险：Tier-3
- 能力边界：Interaction Intelligence / Realtime Media / Conversation Runtime / Agent Bridge / Voice–Task Bridge 组合
- 默认路径：`cascade`
- 可选路径：`openai-realtime-native`
- 默认 Native 模型：`gpt-realtime-2.1-mini`
- 决策记录：[D-098](../decisions/DECISIONS.md#d-098-以独立-tier-3-合同激活-openai-realtime-native-interaction-engine)

## 1. 目的与验收口径

本设计在 Live Voice 中新增真正的 `OpenAIRealtimeNativeInteractionEngine`。它让一个连续的 OpenAI Realtime session 同时承担音频输入、模型级语义/VAD/EOT、可打断音频输出和有限 action proposal；它不是现有 Streaming Speech Adapter 的新模式，也不是 `STT → Agent → TTS` Cascade 的改名。

Native Engine 的正向旅程必须同时满足：

1. 浏览器音频通过 Gateway 的服务端 Provider 连接进入一个连续 Realtime session；浏览器永远不接触 Provider 凭据。
2. Provider 原生事件投影为闭集 `LISTEN / SILENCE / TURN_COMMIT / SPEAK / STOP / REVISE / DELEGATE` proposal。
3. 简单前台回答可以直接使用 Provider 的 native audio，但每个音频单元仍须经过 Runtime response/generation fence 和 Audio I/O presentation ACK。
4. Jiuwen 对话与 Tool 只可通过 Agent Bridge；后台 Task 只可通过 Voice–Task Bridge/P3；Provider function call 本身没有业务执行权限。
5. 打断必须停止本地播放、取消 Provider response、按实际播放游标 truncate Provider conversation，并使旧 generation 的迟到 PCM、transcript、done 和 ACK 全部失效。
6. 现有 Cascade 保持默认并完整回归；Native 不可用时不得在同一 interaction 中静默切回 Cascade。

源码、确定性自动化和独立 Tier-3 冻结候选审核通过，只产生 source/automation credit。真实 Provider、真实设备和人工可听旅程仍是独立 Gate；没有相应凭据和环境时保持 `NOT_RUN`，不得由 fake 结果替代。

Provider 合同以 2026-08-25 查验的 OpenAI 官方文档为准：[Realtime overview](https://developers.openai.com/api/docs/guides/realtime)、[WebSocket](https://developers.openai.com/api/docs/guides/realtime-websocket)、[conversations](https://developers.openai.com/api/docs/guides/realtime-conversations)、[VAD](https://developers.openai.com/api/docs/guides/realtime-vad) 和 [`gpt-realtime-2.1-mini`](https://developers.openai.com/api/docs/models/gpt-realtime-2.1-mini)。实现前和真实 probe 前分别重新核对 event/model capability；发现不兼容即触发第 16 节重新评估。

## 2. 明确排除

本包不做以下事项：

- 不把旧 `codex/openai-realtime-native-voice@42f448aff7f8af9b0759c59a841f6a57a5792449` 的 exact-text Speech Adapter 当作 Native Engine。
- 不在 `openai_streaming_speech.py` 继续增加 Native mode flag 或交互状态机。
- 不改变 Cascade 的默认激活、现有 `TurnCommit` wire schema、SQLite schema 或 P3 command contract。
- 不把 OpenAI MCP 或 Jiuwen Tool schema直接交给 Provider；不允许 Provider 直接调用 Agent、Tool、Task、Store、History 或 Audio Device。
- 不承诺 AEC、double-talk、跨设备/房间、Provider SLO、Production、feature-complete、远端分支或部署。
- 不在 Native activation 失败后自动改走 Cascade；显式重新激活另一 Engine 是新的 interaction。

## 3. 选择方案

采用“共享 Realtime session kernel + 独立 Native Interaction Engine”。

### 3.1 共享的 Provider session kernel

`OpenAIRealtimeSession` 只拥有 Realtime transport 和资源生命周期：

- server-side WebSocket 建连与 session negotiation；
- 单调 client event ID、Provider event replay ledger 和 correlation；
- 有界 send/receive queue、deadline、close 和 unique finalization；
- Provider protocol error、timeout、remote close 和 cleanup error 的确定性优先级；
- PCM16 编解码、F32/PCM16 转换和线性重采样可复用现有已测实现。

Kernel 不理解 `TurnCommit`、Agent、Task、History、Runtime generation 或产品路由。现有 OpenAI Streaming Speech Adapter 后续只抽取并消费这个 kernel，不接受 Native action 语义。

### 3.2 独立的 Native Engine

`OpenAIRealtimeNativeInteractionEngine` 消费 kernel 的 typed Provider events，维护 Provider-facing interaction state，并只产生意图 proposal。它不获得业务 authority。

建议源码边界：

- `jiuwenswarm/server/live_voice/openai_realtime_session.py`：共享 transport/session/finalization kernel；
- `jiuwenswarm/server/live_voice/openai_realtime_native_engine.py`：Provider event、state machine 和 action proposal；
- `jiuwenswarm/server/live_voice/native_interaction_contract.py`：独立 closed v1 contract；
- `jiuwenswarm/server/live_voice/native_interaction_runtime.py`：Native proposal 与 Conversation Runtime/Bridge 的 authority adapter；
- `jiuwenswarm/gateway/live_voice/`：只增加 activation 和 dedicated media 的薄 wiring；
- `product_composition_registry.py`：只组合 owner，不吸收 Provider protocol 或状态机。

### 3.3 不采用的方案

不采用以下两种方案：

1. 在 2,000+ 行的 `openai_streaming_speech.py` 上叠加 Native flags。Speech Adapter 的 batch/streaming exact-text conformance 与连续原生交互的 commit、function call、barge-in 和 history 语义不同，继续叠加会形成双重 authority 和不可审计 finalization。
2. 用 Native wrapper 包装现有 `STT → submit → TTS` route。这仍是 Cascade，只改变名称，不能提供模型级 EOT、连续 session 或 native audio response。

## 4. 配置与激活

配置保持显式、closed、fail-closed：

```text
LIVE_VOICE_INTERACTION_ENGINE=cascade                  # 默认
LIVE_VOICE_INTERACTION_ENGINE=openai-realtime-native  # 显式 opt-in
LIVE_VOICE_NATIVE_REALTIME_MODEL=gpt-realtime-2.1-mini
```

未知 Engine 值、空 Native model、Provider 不支持要求的 audio/function capability、session negotiation 不完整或凭据不可用，都在 activation 期间返回 typed unavailable/rejected，不创建半激活 Runtime interaction，不注册可写 media authority。

model 可显式覆盖，但不得由 Provider 响应、浏览器 payload 或未认证 RPC 临时改变。Provider key 继续只由 Gateway secret/config seam 读取并只存在于服务端。

同一 interaction 只绑定一个 Engine。Native session 失败后先完成 Runtime/Media/Provider cleanup；用户若选择 Cascade，必须建立新的 activation/interaction/generation identity。

## 5. 新增 closed 合同：`live-voice.native-interaction.v1`

现有共享 `TurnCommit` 要求非空 `text`。Native audio turn 可能没有可用 transcript，强制伪造文本会把审计投影升级为输入 authority。因此新增独立 v1 内部合同，而不修改 v2 序列化或数据库。

### 5.1 `NativeTurnCommit`

必填字段：

- `contract_version = "live-voice.native-interaction.v1"`；
- exact `scope_id / interaction_id / turn_id`；
- Provider `session_id / conversation_item_id`；
- `input_audio_start_ms / input_audio_end_ms / committed_audio_ms`；
- exact `provider_event_id / correlation_id / causation_id`；
- Runtime activation generation/fence binding。

可选字段：

- `audit_transcript`；
- transcript Provider item/event provenance；
- bounded semantic/VAD audit metadata。

`audit_transcript` 只可用于 subtitle/diagnostic 或在后续 delegate admission 中作为 untrusted request material；缺失 transcript 不影响 native audio commit。它不能单独触发 Agent、Tool、Task、History 或 presentation。

### 5.2 `NativeActionProposal`

每个 proposal 必须绑定 exact interaction、turn、Provider event、Runtime generation/fence 和 action-specific payload。closed action set 复用现有 `InteractionAction` 的八项 vocabulary，但 Native payload 使用 v1 codec 做 closed parsing；未知 action/field、重复 event、changed replay 或 cross-scope binding 一律拒绝。

### 5.3 Delegate 转换边界

只有 Runtime 验证通过的 `DELEGATE` proposal 才转换为现有标准 `TurnCommit`。转换后的非空 `text` 来自 bounded `jiuwen_delegate.request_text`，并带 exact native proposal、Provider call/item、interaction/turn 和 correlation provenance。

这个标准 `TurnCommit` 随后进入现有 committed-input resolver：

- 前台对话/Tool → Agent Bridge；
- 后台 Task → Voice–Task Bridge/P3。

Native v1 本身不新增持久化 authority、schema migration 或第二个 routing classifier。

### 5.4 Gateway–AgentServer carrier 与 Browser downlink 投影

源码勘察确认 Provider session/原始音频必须留在 Gateway，而 Conversation Runtime、Agent Bridge 和 Voice–Task Bridge/P3 留在 AgentServer。D-099 因此把跨进程 carrier 明确纳入同一个 `live-voice.native-interaction.v1`，风险仍为 Tier-3：

- Native activation 继续使用现有 authenticated P2 activation，不增加 Browser RPC。AgentServer 为 exact session/scope/interaction/activation generation 生成一个随机 256-bit capability；Gateway response observer 取得它，向 Browser 转发前必须剥离，Browser payload、日志和 telemetry 永远不可见。
- Gateway→AgentServer 只新增三个 internal E2A request method：`live_voice.internal.native.propose`、`live_voice.internal.native.presentation_ack`、`live_voice.internal.native.close`。它们不进入 Web registered/forwarded/allowlisted method set；每次调用都绑定 exact capability、v1 payload、request replay identity 和当前 activation lease。
- `native.propose` 承载 Provider action/turn/response/done/delegate proposal，并承载同一 Provider event 的 metadata-only audio observation。audio observation 的 closed fields 仅为 `provider_event_id`、`provider_response_id`、`provider_item_id`、`content_index`、`sequence`、`sample_count`、`content_sha256` 和已 admission 的 `ResponseRef`；严禁 PCM、base64、bytes 或任何可还原音频内容。AgentServer 用该元数据先生成并返回 Runtime-authored audio `PresentationUnit`，Gateway 只有在 exact typed admission 成功后才把仍在本进程的对应 PCM 放入 dedicated-media downlink。Runtime admission 或 canonical delegate result 是 `native.propose` 的 typed response；delegate completion 不是 Gateway 可自报的第二个 request method。
- `native.presentation_ack` 只承载现有 Audio I/O/Media 验证后的 response/generation/delivery ACK 或实际 played cursor；`native.close` 只关闭 exact Native route。两者都不能修改 Task 或绕过 Runtime。
- Browser-visible 扩张保持为两个闭合集合且不新增 RPC：Native P2 activation 在 Gateway 删除私有 capability 后返回 exact `native_interaction={contract_version:"live-voice.native-interaction.v1",engine:"openai-realtime-native",model}` descriptor，Cascade activation 不含该字段；现有 `live_voice.composition.p2.notification.next` 增加 exact `kind="native.audio"` 变体。后者绑定 activation、`ResponseRef`、audio `PresentationUnit` 和现有 response-bound dedicated-media downlink descriptor；不增加媒体 frame/control、WebSocket subprotocol 或 Browser authority。Gateway 从自己的有界 Native downlink queue 投影该变体，队列为空时继续读取原 AgentServer P2 notification，不吞掉 Agent/Task 事实。descriptor 的 Engine/model 来自服务端配置与私有 activation seam，不接受 Browser local storage、query 或请求字段覆盖。

该扩张不修改 shared `TurnCommit`、SQLite、P3 command、media v1 或 canonical history schema。任何更多 Browser method/notification kind、持久 capability、第二队列/Runtime owner 或通用 Gateway→AgentServer execution API 都触发第 16 节重新评估。

## 6. Authority 划分

| Owner | 唯一职责 | 明确禁止 |
|---|---|---|
| Gateway | Provider credential、WebSocket、dedicated media ingress/egress、activation wiring | Agent/Tool/Task/History 决策 |
| `OpenAIRealtimeSession` | transport、event ledger、queue、deadline、close/finalize | action、Runtime state、业务副作用 |
| Native Engine | Provider state、typed event → action proposal | 提交 Agent/Task、写 History、直接控制设备 |
| Conversation Runtime | interaction/turn/response/generation/fence、cancel admission、history eligibility | Provider credential、Task lifecycle |
| Audio I/O | 本地播放、实际 played cursor、presentation ACK | response authority、History |
| Agent Bridge | 标准 committed input → Jiuwen Agent/Tool | Task Store、Native session ownership |
| Voice–Task Bridge/P3 | authenticated Task targeting/command/result | Provider/Audio/Agent authority |
| Product composition | 组合上述 owners 并保留 exact binding | 新建第二状态机或第二 ledger |

所有可产生业务或展示副作用的路径都必须经过 owning authority 的 exact scope/interaction/turn/response/generation/delivery 验证。Engine proposal 成功不等于操作已执行。

## 7. 状态机和资源所有权

Provider resource lifecycle：

```text
NEW → CONNECTING → NEGOTIATING → READY
                                  ↓
LISTENING → USER_SPEAKING → TURN_COMMITTED → RESPONSE_PENDING
                                      ├→ SPEAKING
                                      └→ DELEGATING → DELEGATE_WAIT → RESPONSE_PENDING → SPEAKING
any active state → CANCELLING → READY
any state → CLOSING → CLOSED
any state → FAILED → CLOSING → CLOSED
```

规则：

- `OpenAIRealtimeSession` 是 WebSocket、send/receive tasks 和 close/finalize 的唯一 owner。
- Native Engine state 是 Provider projection，不可替代 Conversation Runtime 的 business lifecycle。
- 每个 Provider response 只有在 Runtime `accept_response` 后才获得 `ResponseRef + generation`。
- 每个 audio delta 进入 dedicated media 前必须匹配当前 response/generation fence。
- settle、cancel、close 都是 idempotent；第一次 primary failure 固定，cleanup failure 只附加诊断，不覆盖 primary failure。
- stale/duplicate/out-of-order Provider event 不得推进状态或产生副作用。

## 8. Provider 事件到 action 的映射

| Provider observation | Proposal / Runtime 动作 | 约束 |
|---|---|---|
| input speech started | `LISTEN`；若存在当前 speaking response，再提出 `STOP` | STOP 仍需 Runtime exact response/generation admission |
| input speech/semantic stopped | `SILENCE` | 不等于 authoritative commit |
| committed input audio item | `TURN_COMMIT(NativeTurnCommit)` | 必须绑定同一 input item、游标和 event ledger |
| response created | `SPEAK` candidate | 未经 Runtime `accept_response` 不得下发 PCM |
| `response.output_audio.delta` | fenced audio unit | stale generation、cancelled response、越界 sequence 全部丢弃 |
| response function call completed | `DELEGATE` | 只接受 exact `jiuwen_delegate` closed arguments |
| response cancelled | observation | 不能单独证明本地播放已停止或 history 可写 |
| response done | settle candidate | 需完整 Provider status、audio completion 和 presentation ACK 才可结算 |
| input speech 在 commit 前重新开始 | `REVISE` | 只撤销同一 turn 尚未提交的 pending `SILENCE`，不重写已提交 authority |
| malformed/unknown/replayed event | typed protocol failure / reject | zero forbidden side effects |

本设计使用 GA Realtime event vocabulary，包括 `response.output_audio.delta`。实现不得依赖旧 preview event 名称。

## 9. Barge-in、cancel 和 truncate

播放期用户开始说话时采用同一个 exact cancellation chain：

1. 浏览器 Audio I/O 立即停止当前本地播放，并回报最后实际播放的 Provider content cursor；本地停止只是 UX，不授予 Runtime settle/history authority。
2. Native Engine 从 Provider speech-start 产生绑定当前 `ResponseRef + generation` 的 `STOP` proposal。
3. Conversation Runtime 验证 proposal 后调用既有 exact cancel/barge-in seam，推进 generation fence。
4. Engine 只在 Runtime cancel admission 成功后发送 `response.cancel`。
5. Engine 使用 Audio I/O 的实际 played cursor 发送 `conversation.item.truncate`；不能用已接收、已排队或估算的字节数冒充已播放位置。
6. 旧 generation 的迟到 audio delta、transcript、done、function call 和 presentation ACK 全部 fail closed；不得写 assistant history、调用 Bridge 或恢复播放。

重复 STOP/cancel/truncate 必须幂等。缺少 current response、played cursor、scope binding 或 Runtime admission 时不发送 changed Provider mutation。

## 10. 安全委托与 Jiuwen 结果回送

Provider 只暴露一个 application function：

```json
{
  "name": "jiuwen_delegate",
  "arguments": {
    "request_text": "bounded non-empty string"
  }
}
```

规则：

- session instructions 把 direct response 限定为无业务副作用的普通前台对话；任何需要 Jiuwen Agent、Tool、Task、受保护状态或 authoritative project data 的请求都必须提出 `jiuwen_delegate`。这只是 Provider semantic proposal policy，不授予 Provider classifier 或执行 authority；即使 Provider违反指令，direct path 也没有可调用的 mutation surface。
- 不向 Provider 暴露 Jiuwen Tool、Task command、Store、filesystem、MCP 或任意动态 schema。
- Engine 只解析并提出 `DELEGATE`；它不执行 function。
- Runtime 验证 exact call/item/turn/generation、closed JSON、长度、Unicode/控制字符和 replay；失败为零 Agent/Tool/Task/history/audio side effect。
- 通过验证后才生成标准 `TurnCommit`，交给现有统一 committed-input resolver。
- Native carrier 不携带或保存 bearer。Native activation 仅在服务端内存保留现有认证器已经验证的非秘密 immutable principal；每次 Task delegate 仍重新校验该 principal 的 operation scope/expiry，重新解析当前 Session/Project/context，并执行既有 exact-Task 检查。`agent.chat` 的窄 product authority 不得被提升为 Task authority。
- Agent/Task Bridge 返回 canonical result 后，Runtime 先接受一个新的 native response generation，再由 Engine 把 sanitized canonical result 作为 `function_call_output` 发回 Provider。
- Provider 基于该 result 生成的 audio 仍经过新的 response/generation/presentation fence。

Provider 不能选择最终 Agent/Task route，不能把 function call completed 当作 Jiuwen 已执行，也不能直接把结果写入 canonical history。

## 11. History 与 transcript 规则

- Provider conversation context 不是 Live Voice canonical history。
- Native 直接回答不要求 exact-text gate 才能播放；audio 是第一等输出。
- input transcript 是可选 audit/subtitle projection，不是 `NativeTurnCommit` authority。
- direct assistant transcript 只有在 exact Provider item/response provenance 完整、`response.done` 成功、全部 PCM presentation ACK 完成且 generation 仍 current 时，才可投影到 canonical history；没有可靠完整 transcript 时只结算 presentation，不伪造 assistant text。
- 被打断或部分播放的 native response 不写 assistant text history；当前 API 没有足够精确的逐字 audio/text 对齐来安全截断 canonical text。
- Delegate 路径的标准 `TurnCommit` 和 Jiuwen canonical result 继续遵守现有 Agent/Task history 规则；“result 已产生”与“result 已向用户完整呈现”保持分离。
- stale、duplicate、cancelled、failed 或 cross-generation transcript/done/ACK 永远不能恢复 history eligibility。

## 12. Realtime kernel 的保留、抽取、重写和停止边界

### A. 原样复用

- PCM F32/PCM16 codec；
- linear resampler；
- Gateway config/secret seam；
- deterministic fake socket/event builders；
- dedicated media uplink/downlink；
- Runtime generation/presentation ledger。

### B. 抽取为共享 kernel

- Realtime WebSocket wrapper；
- monotonic event ID 与 replay ledger；
- bounded queue/deadline；
- transport cleanup 与 unique finalization；
- primary failure precedence 和 degradation mapping。

抽取必须用 Characterization tests 证明 Cascade Speech 语义不变，然后才允许 Native Engine 消费。

### C. Native 路径重写

旧 Speech Adapter 中以下假设不进入 Native：

- per-synthesis socket；
- `conversation="none"`；
- exact requested-text transcript gate；
- 生成完毕后整体释放 buffer；
- recognition final 是唯一 commit authority。

Native 使用连续 session、native input item commit、增量 fenced audio 和 optional transcript。

### D. Cascade-only

- `StreamingSpeechConformance`；
- `StreamingRecognitionRouteOwner`；
- batch/openai Cascade；
- 现有 `ProductP1VoiceRouteOwner` 的 STT final → submit → TTS；
- 旧分支的 exact-text Speech semantics。

### E. 明确停止

- 不新增第二套 WebSocket close/finalization owner；
- 不在大 Provider 文件继续复制 Native state；
- 不用 Speech Adapter 测试数冒充 Native Engine closure；
- 不让 Gateway、Engine 或浏览器成为 Agent/Task/History authority。

## 13. 失败、退化与关闭语义

失败优先级从 authority 到 transport：

1. scope/identity/fence/authorization 违反；
2. explicit Runtime cancel/interaction close；
3. operation deadline/budget；
4. Provider protocol/error/remote close；
5. local parse/codec/queue failure；
6. cleanup failure。

第一次 primary failure 一旦冻结，后续 cleanup 只追加 sanitized diagnostic。任何失败路径都必须：

- 停止新 proposal/audio admission；
- 使当前 Provider response/generation fence 失效；
- 关闭 send/receive tasks 和 WebSocket，且 close 最多一次；
- 不泄露 key、prompt、audio、function arguments 或 raw identity；
- 不静默创建 Cascade interaction；
- 返回 closed degradation/disposition，未知值 fail closed。

Native activation 不成功时产品可显示“Native unavailable；可重新选择 Cascade”。已经激活后的 Provider 失败只关闭该 Native interaction。

## 14. TDD 与 Tier-3 验证矩阵

实现必须按红—绿—重构推进，禁止先写大段生产代码再补覆盖。确定性 fake 不使用任意 sleep；所有 race 由 barrier、future、manual clock 和 explicit event injection 控制。

### 14.1 测试层

1. Contract tests：v1 closed codec、required/optional fields、replay、cross-scope、bounded delegate args、v2 `TurnCommit` compatibility。
2. Kernel characterization：抽取前后 Speech Adapter 的 connect/send/receive/deadline/close/failure precedence 等价。
3. Engine unit tests：连续 session negotiation、state transition、GA event mapping、unknown/malformed/out-of-order/replay。
4. Runtime authority tests：response/generation admission、stale audio、STOP/cancel/truncate、presentation ACK、history eligibility。
5. Bridge tests：delegate 正向 Agent/Tool/Task route，以及所有拒绝路径的 zero forbidden effects。
6. Gateway/Product tests：配置选择、Cascade default、Native opt-in、credential/server-only、media registration/cleanup、重连和同 session multi-turn。
7. Cumulative regressions：现有 Interaction/Runtime/Agent Bridge/Voice–Task Bridge/OpenAI Speech/Gateway/Formal Web 受影响套件。

### 14.2 风险维度

按根 `TESTING.md` 为每个 changed boundary 记录适用的 P/N/B/S/T/C/R/I/F/K/X：

- P：连续多轮 native audio、直接回答、Agent/Tool delegate、Task delegate；
- N：无效 config/model、malformed event/function args、unauthorized scope、stale generation；
- B：空/最大 audio、queue/argument/sequence 边界、无 transcript、零/末端 played cursor；
- S/T/C：state transition、deadline、barge-in 与 done/cancel/close、duplicate/reorder race；
- R/I：restart/remote close/half-open transport、Bridge result 回送、multi-turn session；
- F/K/X：failpoint、secret/privacy/closed schema、跨语言或 Product/Gateway contract seam。

任何可以改变 Agent、Tool、Task、audio/history authority、protected state 或另一 scope 的 negative/race path，都必须明确断言 forbidden side effects 为零。

### 14.3 冻结候选与真实 Gate

源码完成后先冻结 exact candidate HEAD/tree/config/test manifest，由独立 cold reviewer 检查：

- 设计/合同一致性；
- authority 与 double-owner 风险；
- concurrency/finalization/cancel race；
- security/privacy/secret handling；
- positive journey 和 negative zero-effect coverage；
- Cascade regression 与非声明。

只有 review 为 `C0/I0` 且 fix-only follow-up 关闭后，才允许使用机器私有凭据运行有界真实 OpenAI probe。probe 至少覆盖 connect/negotiation、连续两轮、native first audio、一次 barge-in、一次 safe delegate 和 cleanup；device/human journey 另记，不写入凭据、原始音频或 prompt。

## 15. 实施顺序与提交边界

计划采用可单独审查的本地提交：

1. design/decision；
2. v1 contract 与 authority tests；
3. shared Realtime kernel characterization/extraction；
4. continuous Native Engine session/event mapping；
5. Runtime response/generation/media fence；
6. barge-in/cancel/truncate；
7. safe delegate 与 Agent/Task Bridge composition；
8. history/config/close/Cascade regressions；
9. docs/evidence/review fixes。

不得 push。旧分支和原 worktree 不改写；实现基于 `hx/0812_live_voice_w3@1742c1b4e5fa5e7a25a7b41dad9c8eef8453e3cc` 的独立 worktree/branch。

## 16. 重新评估条件

出现以下任一情况时，停止实现并重新冻结设计、范围和 risk tier：

- 需要修改现有 `TurnCommit` wire/schema 或新增 SQLite migration；
- 需要第二个 committed-input classifier、Runtime、history、Task 或 Provider session owner；
- Provider 必须直接调用 Jiuwen Tool/MCP/Task 才能完成正向旅程；
- OpenAI GA event/function/VAD contract 与本设计不兼容；
- precise truncate 无法从 Audio I/O 获取实际 played cursor；
- direct response history 必须保存被打断的部分文本，但缺少可靠 audio/text alignment；
- Native failure 需要产品级自动 fallback/跨 Engine continuation；
- 范围扩展到 D-099 已冻结的单一 `native.audio` 变体之外的新客户端协议、public deployment、account/billing、Production 或 remote ref update。
