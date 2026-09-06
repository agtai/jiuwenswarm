# OpenJiuwen LiveVoice 与官方 Hermes Voice 的逐模块对比、解释与瘦身分析 — 2026-09-06

> 状态：只读分析（Tier 0 文档），不改代码、不授予任何验收或远端更新。本文取代此前以个人仓库
> `bielcarpi/hermes-live-voice` 为对标的模块对比（[中文架构指南](OPENJIUWEN_LIVEVOICE_HERMES_MODULE_ARCHITECTURE_ZH_2026-08-31.md)
> 保留为历史读物）；[总计划](../roadmap/LIVEVOICE_SLIMMING_MASTER_PLAN.md) §3 的 Hermes 列已按本文改为官方数字。
>
> - Hermes 侧：官方仓库 `NousResearch/hermes-agent`，clone 于本地
>   `D:/XGG AI/openjiuwen/hermes-agent-review-9a84bee26`，HEAD `9a84bee265daad14340a80d7585928cd8ea1f9eb`
>   （2026-09-06 13:32 +0530，32,026 个提交）。该 clone 不在本仓库内，只作阅读。
> - LiveVoice 侧：`hx/0812_live_voice_w3@7c7aad7b8`（本分支 HEAD 只叠加文档与脚本）。模块数字来自
>   `scripts/live_voice/slimming/module_buckets.py --rev HEAD`，与总计划 §3 一致；Native（OpenAI Realtime）
>   8 个文件 7,758 行按用户决定排除。
> - 口径：physical LOC（空行、注释、docstring 计入）。Hermes 的数字由
>   `scripts/live_voice/slimming/hermes_voice_inventory.py --repo <clone>` 复现（文件白名单、共享宿主
>   segment 规则和测试文件规则都写在脚本里）。

## 1. 结论先行

1. **官方 Hermes 的语音生产面是 20,265 行**（白名单口径）：59 个专属文件 18,140 行 + 40 个 Python 共享宿主
   文件里的语音 symbol 段 2,125 行（TS 宿主里另有几百行未计，见 §3.2）。去掉 LiveVoice 没有对应物的 wake word（1,518）、Google Meet 的 Realtime
   speak-only 客户端（198，对应被排除的 Native）与 setup/doctor 支持代码（662）后，**可比集 17,887 行**。
   Hermes 语音相关测试 108 个文件 25,226 行，测试/生产比 1.24。
2. **LiveVoice 专属生产面 171,431 行（不含 Native）+ 共享宿主 segment 约 4.3K ≈ 175.7K**，是官方
   Hermes 可比集的 **9.6 倍**（LiveVoice 专属 171,431 对 Hermes 可比集 17,887；含共享 segment 的生产面对
   生产面是 8.7 倍）。Hermes 的非行为行占 32%，LiveVoice 只占 8%，按行为行算（生产面口径）差距约
   **11.7 倍**（Hermes ≈13.8K 行为行，LiveVoice ≈161.6K）。
3. **差距的分布不均匀**（§4）：Speech provider 只有 1.6 倍（Hermes 用 6K 行装了 18 个 STT/TTS
   provider，LiveVoice 用 9.9K 行装了 2 个 provider 家族，多出来的是合同与编排层）；Browser/本地音频边缘
   1.8 倍；Conversation Runtime 2.6 倍。**真正的数量级差距在四处**：Committed input/product authority
   43 倍、Composition/config 264 倍、Formal Web/UI 13 倍、Task 五模块 38.3K 对 0。
4. **Hermes 的 voice 层里没有任何 Task/Store/Executor/Durability 代码**。后台工作属于 agent core：
   `delegate_task(background=true)`、`terminal(background=true)`、cron，靠一组 profile 本地的小型
   SQLite 台账（执行台账 384 行、投递队列 379 行、异步委托台账 914 行、会话 turn lease 131 行、fire
   fence/claim 472 行、完成通知投递约 400 行、subagent 公共合同 416 行、后台进程 233 行，合计约
   3,300 行）支撑 30 多个平台。这是本文对 AgentCore 下沉最重要的校准点（§8）。
5. **对瘦身计划的影响**：总计划 §2 的移除清单、§5 的包与 §1.4 的 v1 规划中心（≈50,200，实测预期
   60K–65K）不变；官方对比改变的是解释线与三处校准：(a) §3 表的 Hermes 列全部换成官方数字，Task
   五模块的 Hermes 值变为 0，对照改为 core substrate；(b) AgentCore F1–F6 的规划中心建议从 5,300
   下调到 **约 4,100（区间 3,150–5,700）**，逐 seam 以 Hermes 台账尺寸为下界、以 LiveVoice 产品
   invariant 为增量（§8.2）；(c) F5 Checkpoint Publication 是六个 seam 里唯一没有任何 Hermes 对应物
   的，建议在 A2 decision record 中评估并入 F6 的 append-only facts（§8.6）。
6. **不能因为 Hermes 没有对应模块就下沉**：本文逐项判定了 LiveVoice 独有而 Hermes 没有的责任
   （语义路由、committed input journal、presentation ledger、进度仲裁、Direct project journal、D1
   checkpoint 值、tool hold、speculative dialogue），其中只有 consumer cursor 与 checkpoint publication
   两项是通用的，其余全部 `JIUWEN_KEEP` 或按机制收缩（§8.3）。

## 2. 官方 Hermes Voice 的心智模型

Hermes 不是一个"语音产品"，而是一个文本 agent 加上三种把语音接进文本管线的方式。语音层的
全部工作是：把麦克风或平台音频变成一条普通文本消息，把 agent 的文本回复变成音频，以及在
说话时打断。它没有语音专属的 turn/response 权威（通用的 gateway run generation 加会话 turn lease 就是它的
fence），没有语义路由，没有语音专属的 Task。

### 2.1 三条调用链

```text
(1) CLI / TUI 连续语音（单进程，麦克风与扬声器是进程全局）
  AudioRecorder(sounddevice) --VAD 静音停录--> WAV
    -> transcribe_recording -> transcribe_audio(provider 分发) -> 文本
    -> 幻觉过滤 / 停止词 / TTS 回声判定（voice_mode_transcript）
    -> _pending_input.put(_VoiceInputMessage)  或  voice.transcript RPC -> prompt.submit
    -> AIAgent 正常 turn（进程内）
    -> LLM delta -> SentenceChunker -> StreamingTTSProvider（或按句整文件 TTS）-> 扬声器
    -> 整个 turn 期间 full_duplex_listen 开着麦克风：
         generation 阶段 tripped -> agent.interrupt()
         playback 阶段 tripped   -> mark_speech_interrupted + 切 TTS + stop_playback
       捕获到的插话转写后作为下一条消息入队；纯停止词结束语音聊天

(2) Desktop（Tauri/React）经本地 web server
  use-mic-recorder -> 文件 -> POST /api/audio/transcribe（或 client-direct 直连 provider）
    -> prompt.submit（携带 interrupted: true 的 latch）
    -> WS /api/audio/speak-stream：客户端喂 LLM delta，服务端 SentenceChunker 切句，
       回传 int16 PCM 帧；{"stop":true} 或断线 = 插话
    -> voice-barge-in 在浏览器侧做 VAD（RMS 地板校准，无回声消除）
    -> use-voice-conversation 状态机 idle/listening/transcribing/thinking/speaking

(3) Gateway 平台（Telegram/Discord/Matrix/… 共 30 余个 adapter）
  语音消息附件 -> run_inbound._enrich_message_with_transcription（STT，失败则中性标记）
    -> 普通 MessageEvent（message_type=VOICE）-> 正常 turn
    -> 回复：/voice 模式 all|voice_only|off（每聊天，JSON 持久化）决定是否自动 TTS
       -> text_to_speech_tool 整文件合成 -> send_voice 语音气泡（Ogg/Opus 修复）
       -> 语音输入 turn 上可用 StreamingTTSConsumer 流式 PCM（树内没有 adapter 覆写
          begin_streaming_tts，因此当前总是回退整文件）
  Discord 语音频道：VoiceReceiver 解密 RTP、按 SSRC 分用户、静音切分 -> WAV -> STT
    -> _handle_voice_channel_input 合成 MessageEvent -> 回复经 VoiceMixer（环境音 + 语音 ducking）播放
```

### 2.2 Hermes 有意没有的东西

| Hermes 没有 | 它用什么代替 | 对 LiveVoice 的含义 |
|---|---|---|
| 流式识别（partial hypothesis） | 识别以整段 WAV/m4a 为单位；TUI 的 `voice.record` 是 VAD 定界的 push-to-talk | LiveVoice 的 streaming STT 路线是 Hermes 没有的能力，其代码有存在理由，但没有 9.9K 行的理由 |
| 语音专属的 turn commit / response 权威 | 转写入队即提交；response 的身份是 gateway 通用的 `run_generation`（每会话单调，用于 turn lease、stale-run 检测、投递后回调与流式 TTS 去重）加 `SessionTurnLeaseLostError` fence | LiveVoice 的 `TurnCommit`、`ResponseRef`、generation fence 是跨三进程（浏览器/Gateway/AgentServer）的必要物，但三套 fence 应是一套 |
| 语义路由（对话 vs 任务） | 每条转写都是普通消息；后台工作由模型自己调用 `delegate_task`/`terminal`/cron 工具 | LiveVoice 的语义判断是产品决定（D-107–D-112），保留；但它周围的四套 CAS ledger 不是 |
| 语音专属 Task/Store/Executor | agent core 的 cron + 异步委托 + 后台进程台账（§8.1） | 印证总计划的判断：通用 Task truth 放错了层 |
| 呈现台账（说了什么、被确认播放了什么） | `StreamingTTSHandle.audible` 一个布尔 + `_settle` 的 outcome 标志；desktop 的 end/stall | LiveVoice 的 `PresentationLedger` 是 D-115（faithful voice delivery）的要求，保留 |
| 共享 schema 模块 | 3 个 pydantic 请求模型 + docstring 里写的 WS 协议 + hooks 内的 TS 类型 | LiveVoice 需要 schema，但需要一份而不是三套 Python 家族加一份 TS 副本 |
| 观测/隐私 conformance | `HERMES_VOICE_DEBUG=1` 的 stderr breadcrumb、`detect_audio_environment`、doctor 脚本 | LiveVoice 的隐私零泄露断言是产品要求，但三条观测通道与无 caller 支持代码不是 |
| 组合根/注册表 | `register()` 两行、FastAPI router include、函数内 lazy import | LiveVoice 15.8K 行的 registry 没有 Hermes 对应物，也不需要 |
| tool hold / speculative dialogue | agent turn 等 STT 完成后才开始；最近的机制是 busy 路径把 interrupt 降级为 queue | LiveVoice 独有；不下沉（§8.3） |

### 2.3 进程拓扑差异

Hermes 的语音状态是进程全局的（一个麦克风、一个扬声器、一个 TTS lease 计数），agent 在同一
进程或 gateway 进程里；desktop 通过本地 web server 访问。LiveVoice 是浏览器 ↔ Gateway ↔
AgentServer 三进程，音频权威在浏览器，Provider 传输在 Gateway，Agent 与 Task 在 AgentServer。
这个拓扑解释了 LiveVoice 为什么必须有 media transport、E2A carrier 和跨进程 generation
fence，也解释了为什么这些东西不能像 Hermes 那样各自只有几十行。

## 3. 官方 Hermes Voice 逐模块清单

### 3.1 专属文件（59 个，18,140 行）

**A. CLI/TUI 语音循环（5 文件，3,993 行）**

| 文件 | LOC | 责任 |
|---|---:|---|
| `tools/voice_mode.py` | 1,572 | 本地音频边缘：`AudioRecorder`/`TermuxAudioRecorder`（VAD 静音停录、最大时长、RMS）、`listen_for_speech`、`full_duplex_listen` + `_BargeDetector`（地板校准、playback grace、tripped phase）、`play_audio_file`/`stop_playback`（sounddevice/系统播放器/WSL PowerShell 回退）、thinking 提示音、`detect_audio_environment`、超大 WAV 分块转写 |
| `hermes_cli/cli_voice_mixin.py` | 849 | CLI 的语音处理器：录音开停、转写入队、TTS 后台线程、full-duplex 监听器（generation 阶段 `agent.interrupt()`，playback 阶段切 TTS）、插话转写与 TTS 回声丢弃、wake word 启停、TTS lease |
| `tui_gateway/methods_voice.py` | 779 | TUI/desktop 的 JSON-RPC `voice.*`/`wake.*` 处理器与进程全局状态：per-turn 流式 TTS 消费者 begin/stop、full-duplex 监听、`_fd_trip`（先切 TTS 再打断所有运行中的 turn）、client PCM 推送、VAD 定界 push-to-talk |
| `hermes_cli/voice.py` | 683 | 进程级录音 + TTS API：push-to-talk、连续 VAD 循环（无语音上限、busy probe、TTS 期间不计静音）、`speak_text`（有流式 provider 走 `stream_tts_to_speaker`，否则整文件） |
| `tools/voice_mode_transcript.py` | 110 | Whisper 幻觉过滤、停止词精确匹配、TTS 回声相似度判定 |

**B. STT provider（9 文件，2,094 行）**

| 文件 | LOC | 责任 |
|---|---:|---|
| `tools/transcription_tools.py` | 602 | provider 解析（显式 `stt.provider` 优先，本地 faster-whisper 空闲卸载）、校验/预处理/分发、凭据文件拒绝上传、错误信封 |
| `tools/transcription_cloud.py` | 426 | Groq、OpenAI 兼容、Mistral、xAI、ElevenLabs、DeepInfra 六个云 STT |
| `tools/transcription_audio.py` | 279 | 转码 16 kHz 单声道 m4a、大小上限、SILK/CAF 转换、静音裁剪、时长探测 |
| `tools/transcription_local.py` | 263 | faster-whisper 加载（CUDA→CPU 回退、Apple Silicon 强制 CPU）、反幻觉 kwargs、置信度过滤、本地命令模板 |
| `tools/transcription_command.py` | 252 | 用户声明的 command provider、plugin provider 分发、`pre_transcription` 钩子 |
| `tools/transcription_common.py`、`tools/audio_container.py` | 141 | 信封/常量、magic-byte 容器嗅探 |
| `agent/transcription_provider.py`、`agent/transcription_registry.py` | 131 | provider ABC 与注册表 |

**C. TTS provider（14 文件，3,858 行）**

| 文件 | LOC | 责任 |
|---|---:|---|
| `tools/tts_tool.py` | 682 | 配置解析、内置引擎选择、长文本分块合成、输出策略（Opus 语音气泡）、`MEDIA:` 标记、需求检查 |
| `tools/tts_tool_providers.py` | 612 | Edge、ElevenLabs、xAI（自动语音标签）、MiniMax（区域/凭据）、Mistral、Gemini（persona prompt、音频标签重写） |
| `tools/tts_tool_delivery.py` | 451 | provider 字符上限、分块打包、ffmpeg 转码/拼接/Ogg 容器修复、平台上传上限 |
| `tools/tts_tool_speaker.py` | 353 | 扬声器流水线：按句合成与播放重叠（`_SyncSentencePipeline`）、流式 provider 的预取 FIFO 播放（`_StreamerPlayback`）、重复句跳过 |
| `tools/tts_streaming.py` | 340 | `SentenceChunker`（所有 surface 共用的切句器，去 `<think>`）、`StreamingTTSProvider` ABC + 注册表、ElevenLabs/OpenAI/Gemini/xAI 四个流式实现、每句字节上限、speech-interrupted latch |
| `tools/tts_command_provider.py` | 342 | shell 命令型 TTS/STT provider 的模板渲染与进程树清理 |
| `tools/tts_text_normalize.py` | 219 | Markdown → 口语脚本（符号展开、温度区间、表格/代码块处理） |
| `tools/tts_tool_local.py`、`tools/neutts_synth.py` | 269 | NeuTTS、Piper、KittenTTS 本地引擎与 LRU 模型缓存 |
| `tools/tts_tool_lifecycle.py` | 170 | warm/release lease：desktop 打开朗读时预热本地模型，最后一个 lease 释放时卸载 |
| `tools/tts_tool_openai.py`、`tools/tts_tool_plugins.py` | 248 | OpenAI/DeepInfra 后端、plugin provider 分发 |
| `agent/tts_provider.py`、`agent/tts_registry.py` | 172 | provider ABC（synthesize/stream/warm/release/voice_compatible）与注册表 |

**D. Gateway/web 语音（4 文件，1,303 行）**

| 文件 | LOC | 责任 |
|---|---:|---|
| `hermes_cli/web_routers/audio.py` | 485 | desktop 路由：上传转写、client-direct 配置、ElevenLabs 音色、`speak`（base64）、`tts_lease`、`speak_stream_ws`（text in / PCM out，服务端切句，idle flush，stop=插话） |
| `gateway/run_voice.py` | 371 | `/voice` 模式（`<platform>:<chat_id>` 键，多路复用时加 profile 前缀；JSON 持久化，镜像到 adapter）、Discord 语音频道 join/leave/timeout、转写去重与回显、自动语音回复判定与投递 |
| `gateway/streaming_tts_consumer.py` | 229 | LLM delta → 子句队列 → streamer → adapter PCM sink；`_settle` 保证失败或中断后不报完成；跨线程 abort |
| `tools/voice_client_config.py` | 218 | 决定 desktop 能否直连 provider（relay verdict 不含密钥） |

**E. Desktop 语音（18 文件，4,149 行）**

| 文件 | LOC | 责任 |
|---|---:|---|
| `lib/voice-playback.ts` | 757 | 一个 WebSocket + 一个 AudioContext 的 speech session、autoplay 解锁、stall 超时、client-direct session、中断 latch（`interrupted: true` 随下一次 `prompt.submit`） |
| `hooks/use-voice-conversation.ts` | 736 | 对话循环状态机 idle/listening/transcribing/thinking/speaking、barge monitor 拥有麦克风、生成阶段打断后的 settle 等待、rearm |
| `lib/voice-client-direct.ts` | 380 | 浏览器直连 provider 的 STT/TTS、配置缓存、切句 |
| `hooks/use-composer-voice.ts` | 329 | composer 的语音入口（按键、状态、TTS lease 同步） |
| `lib/voice-barge-in.ts` | 326 | 浏览器 VAD：校准、持续多数判定、playback grace、pre-roll、utterance 定界 |
| `hooks/use-mic-recorder.ts`、`hooks/use-voice-recorder.ts` | 411 | 录音 |
| `voice-activity.tsx`、`voice-menu.tsx`、`settings/voice-provider-fields.tsx` | 555 | UI |
| `lib/speech-text.ts`、`lib/voice-stop-word.ts`、`lib/tts-lease.ts`、`store/voice-prefs.ts`、`lib/audio-context.ts`、`store/voice-playback.ts` | 483 | 口语文本清洗、停止词、lease、偏好、AudioContext、播放 store |
| `hooks/use-auto-speak-replies.ts`、`lib/thinking-sound.ts` | 172 | "朗读回复"开关的自动播报、thinking 提示音 |

**F. 平台专属（2 文件，365 行）**：`plugins/platforms/discord/voice_mixer.py` 224（环境音床 + 语音
ducking 的 `discord.AudioSource`）、`plugins/google_meet/audio_bridge.py` 141（Chrome 假麦克风的虚拟设备）。

**排除项**：G wake word 1,518（`tools/wake_word.py`、`wake_word_engines.py`：openWakeWord/sherpa-onnx/
Porcupine；desktop `store/wake-word.ts`），LiveVoice 无对应；H `plugins/google_meet/realtime/openai_client.py`
198（OpenAI Realtime 的 speak-only 同步客户端，`response.cancel` 做插话），对应被排除的 Native；
I `hermes_cli/setup_tts.py` 266、`scripts/discord-voice-doctor.py` 396（setup 向导与诊断脚本）。G 只计三个核心文件，
desktop 的 wake 指示窗与捕获文件另约 0.8K；H 未计 Meet bot 的 say 管线；两者都不进可比集，只影响 20,265 这个
白名单口径的生产面数字。

### 3.2 共享宿主里的语音 segment（Python 宿主，40 文件，2,125 行）

| 宿主 | LOC | 内容 |
|---|---:|---|
| `plugins/platforms/discord/adapter.py` | 846 | `VoiceReceiver` 289（RTP 解密、SSRC→用户、静音切分、`pcm_to_wav`）、join/leave/timeout、`play_in_voice_channel`、`send_voice`、ack 播放、mixer 安装 |
| `gateway/platforms/base.py` | 169 | `AudioFormat`、`StreamingTTSHandle`、`begin/write/finish/abort_streaming_tts` 默认实现、`send_voice`/`play_tts`、`_synthesize_auto_tts`、`_should_auto_tts_for_chat` 三层判定 |
| `gateway/run_inbound.py` | 154 | 入站语音附件转写、回显、失败中性标记、pending 事件只转写一次 |
| `hermes_cli/cli_tui_mixin.py`、`cli_chat_turn_mixin.py`、`cli_status_bar_mixin.py`、`cli_commands_mixin.py` | 255 | TUI 录音键、音量条、turn 音频装配/释放、状态栏、`/voice` 命令 |
| 各平台 `send_voice`（Telegram 111、Matrix 75、Feishu 44、Slack 28、其余 13 个共 67） | 325 | 语音气泡发送与转码 |
| `gateway/slash_commands.py`、`run_turn.py`、`run.py`、`run_turn_runner.py`、`run_agent_cache.py`、`tui_gateway/prompt_turn.py` | 204 | `/voice` 命令、流式 TTS 消费者 start/finalize、媒体判定、语音频道 ack 回调、sidecar 说明、TUI turn 语音装配 |
| `hermes_cli/nous_subscription.py`、`setup_summary.py`、`doctor_live.py`、`tools_config_providers.py`、`web_models.py`、`web_server.py`、`config.py`、`tui_gateway/methods_profiles.py`、`cli.py`、`agent/models_dev.py` | 172 | 订阅能力、setup 摘要、音频探针、配置校验/镜像、请求模型 |

只扫描 Python 宿主。TUI/desktop 的 TypeScript 宿主（`useInputHandlers.ts` 的录音键、`createGatewayEventHandler.ts`
的 `voice.transcript`/`voice.status`、composer 与 settings 里的语音控件等）另有几百行到约 1K 行未计；LiveVoice
的共享宿主 4,054 行含 TS 宿主，所以 §6 的共享宿主倍数偏高。

### 3.3 测试

108 个语音相关测试文件 25,226 行（最大：`tests/gateway/test_voice_command.py` 2,043、
`tests/tools/test_voice_mode.py` 1,602、`test_transcription_tools.py` 1,351、`test_tts_streaming.py` 973、
`tests/integration/test_voice_channel_flow.py` 761、`test_streaming_tts_consumer.py` 673）。测试替身与
`_reset_*_for_tests` 钩子留在 `tests/`，生产树里只有 `_reset_tts_leases_for_tests`、`tts_lease_holders` 与 desktop
`resetTtsLeasesForTests` 共约 10 行。

## 4. 模块对比（LiveVoice 18 模块 ↔ 官方 Hermes）

Hermes 列是把 §3 的 17,887 行可比集按责任分配到 LiveVoice 的 18 个模块（整文件分配，分配和恰为
17,887；文件内的责任混合以主责任计）。v1 目标沿用总计划 §3。

| # | LiveVoice 模块 | HEAD | 官方 Hermes 对应物 | Hermes | 倍数 | 差异性质 | v1 目标 |
|---:|---|---:|---|---:|---:|---|---:|
| 1 | Browser Audio Edge | 8,429 | `voice_mode.py`（CLI 本地音频）1,572；desktop 录音/播放/VAD/活动指示/thinking 提示音 1,888；Discord `VoiceReceiver` 段 846 + `voice_mixer` 224；Meet `audio_bridge` 141 | 4,671 | 1.8 | 合理但过重：`productP1VoiceRoute.ts` 4,099 行混装 capture/recognition/playout/diagnostics | 5,500 |
| 2 | Web/Gateway media transport | 17,409（不含 Native 段约 15,100） | `web_routers/audio.py` 485、`voice-client-direct.ts` 380、`voice_client_config.py` 218、`streaming_tts_consumer.py` 229、`base.py` 段 169、17 个平台 `send_voice` 325、`run_turn` 流式段 51、`run_voice` 频道生命周期与模式持久化 213 | 2,070 | 7.3 | 合理但过重：三条 route 各自 lifecycle/fallback；`dedicated_media_registration.py` 7,276 行混装 | 5,500 |
| 3 | Speech provider | 9,909 | STT 9 文件 2,094 + TTS 14 文件 3,858 + 订阅/配置小段 66 | 6,018 | 1.6 | 合理但过重：Hermes 18 个 provider，LiveVoice 2 个 provider 家族；多出的是 degradation/cleanup owner 与 conformance 合同 | 6,000 |
| 4 | Committed input / product authority | 16,850 | `run_inbound` STT 注入 154、`voice_mode_transcript` 110、`run_voice` 输入去重/授权 70、`_VoiceInputMessage` 15、`run.py` 媒体判定 42 | 391 | 43 | 存在合理（语义路由、确认、项目 scope 是产品决定），规模不合理：四套一次性授权 CAS ledger | 3,800（5K–7K 更可信） |
| 5 | Conversation Runtime | 8,224 | `use-voice-conversation.ts` 736、`hermes_cli/voice.py` 683、`cli_voice_mixin.py` 849、`methods_voice.py` 779、`cli_chat_turn_mixin` 80、`prompt_turn` 23 | 3,150 | 2.6 | 合理但三套 fence 应合一 | 4,500 |
| 6 | Agent bridge | 3,015 | `voice_ack_callback` 15、`_voice_channel_sidecar_note` 21（agent 在进程内，无桥） | 36 | 84 | 合理（Agent 在 Jiuwen harness 后面）但两层重叠 | 1,300 |
| 7 | Task domain/control | 5,342 | 无（core substrate 见 §8.1） | 0 | — | 层级不合理：通用值类型应归 AgentCore | 1,000 |
| 8 | Task Store | 15,175 | 无 | 0 | — | 同上：整个通用 Store 由 F1–F6 替代 | 600 |
| 9 | Project executor | 6,755 | 无（cron 的 workdir/外部 worker 是最近的核心机制） | 0 | — | 项目 seam 合理；generic attempt/lease/settlement 应归 F4/F6 | 3,200 |
| 10 | Checkpoint/effect | 2,953 | 无 | 0 | — | codec/identity 合理；verifier 归 F5/F6 | 800 |
| 11 | Task event/progress | 8,078 | 无（完成通知在 `run_notifications`，非语音代码） | 0 | — | 游标归 F2/F3；两套 queue/ACK/lease 机制应合一 | 1,500（2K–3K 更可信） |
| 12 | Presentation/history | 2,045 | `run_voice` 自动语音回复判定与投递 88 | 88 | 23 | 合理且必要（D-115） | 2,500 |
| 13 | Formal Web/UI | 16,906 | desktop composer/menu/settings/prefs/lease/口语清洗/停止词/自动朗读 1,145、CLI TUI/状态栏/命令段 175、`/voice` slash 52 | 1,372 | 12 | 合理但过重：Panel 9,344 行装 P1/P2/P3 owner 与仲裁；三个 Task UI owner | 5,600（6K–8K 更可信） |
| 14 | Composition/config | 19,826 | 配置校验/镜像/请求模型/setup 摘要 75 | 75 | 264 | 规模不合理：registry 15,825 行是 handler 工厂 + 逐 handler 重复校验 | 2,700 |
| 15 | Observability | 17,322 | `doctor_live._probe_audio` 16（另 `detect_audio_environment` 在 `voice_mode.py` 内、doctor 脚本 396 不计） | 16 | — | 部分合理：隐私 conformance 与 profiling 是产品要求；三通道与无 caller 支持代码不是 | 3,500 |
| 16 | Schema/protocol | 7,474 | 无独立模块（3 个请求模型计入 14） | 0 | — | 需要 schema，不需要三套 Python 家族 + TS 副本 | 2,000 |
| 17 | Legacy/compat | 3,058 | 无 | 0 | — | 不必要 | 0 |
| 18 | Test/reference in prod | 2,661 | 无（test hook 约 10 行） | 0 | — | 不必要 | 200 |
| | **合计** | **171,431** | | **17,887** | **9.6** | | **≈50,200** |

三点补充：

- 模块 1 的 Hermes 值里有 1,572 行是 CLI 本地音频（sounddevice 录放、Termux、WSL 回退），LiveVoice
  的浏览器边缘没有这部分工作；只看浏览器对浏览器，LiveVoice 8,429 对 desktop 1,888，4.5 倍。
- 模块 3 的对比方向与个人仓库相反：官方 Hermes 的 provider 面比 LiveVoice 宽得多（6 个云 STT + 本地
  faster-whisper + 命令/plugin provider；12 个 TTS 后端 + 4 个流式实现），却只用 6K 行。LiveVoice 的
  9.9K 行里，`openai_streaming_speech.py` 2,921、`batch_speech.py` 2,745、`streaming_speech.py` 2,230
  各自同时装 provider 合同、传输与编排（19/21/31 个类）。
- 模块 7–11 的对比对象不再是"Hermes 的 Task 代码"（个人仓库有 `FileTaskStore`/`TaskSupervisor`），
  而是 Hermes agent core 的后台工作 substrate，约 3,300 行，见 §8.1。
- 可比集里残留约 10 行 wake word 代码（`_stop_cli_wake_word`、`_persist_wake_word_enabled`），忽略。

## 5. 用 Hermes Voice 的语言解释 LiveVoice 的模块

### 5.1 概念对照表

| LiveVoice 概念 | 在官方 Hermes 里是 | 说明 |
|---|---|---|
| `TurnCommit` / committed input | CLI 的 `_pending_input.put(_VoiceInputMessage)`；TUI/desktop 的 `voice.transcript` → `prompt.submit`；gateway 的 `adapter.handle_message(MessageEvent(VOICE))` | Hermes 的"提交"就是入队；LiveVoice 把它做成 durable journal（`unified_committed_input`）是因为浏览器可能在提交与 Agent 开始之间断线 |
| `ResponseRef` / response generation | gateway 通用的 `run_generation`：每会话单调，作 turn lease 的 generation、stale-run 检测、投递后回调与 `_mark_streaming_tts_completed_turn` 去重；不是语音专属 | LiveVoice 需要语音专属的 generation 是因为浏览器、Gateway、AgentServer 各自持有一段 response 的生命周期 |
| `PresentationLedger` / presentation ACK | `StreamingTTSHandle.audible` 布尔 + `StreamingTTSConsumer._settle`（失败或中断后绝不报完成）；desktop session 的 end/stall | LiveVoice 要求历史只记录被确认播放的内容（D-115），Hermes 不做这个承诺 |
| 播放期插话 | `_BargeDetector` tripped phase=`playback`：`mark_speech_interrupted` → `_tts_stream_stop` → `stop_playback`；捕获插话转写后作为下一条消息 | 同一件事；Hermes 用 VAD 地板 + TTS 回声相似度代替回声消除 |
| 生成期打断（D-104/D-106） | phase=`generation`：`agent.interrupt()`；latch 经 `take_speech_interrupted` 变成 `SPEECH_INTERRUPTED_NOTE` 或 desktop 的 `interrupted: true` | 同一件事；Hermes 里它和播放期插话是同一个监听器的两个分支，LiveVoice 是两套 fence（加 Native 三套） |
| tool hold / speculative dialogue | 无；Hermes 等 STT 完成才开始 agent turn；最近的是 busy 路径的 `_agent_has_active_subagents` 把 interrupt 降级为 queue | LiveVoice 独有的时延优化；不下沉 |
| 语义路由（`task_semantics`） | 无；每条转写是普通消息，模型自己决定调用 `delegate_task`/`terminal(background)`/cron | 产品决定 D-107–D-112；Hermes 把"这是不是后台任务"交给主模型的工具调用 |
| Voice Task / `PersistentTaskCore` | `delegate_task(background=true)` + `async_delegation` SQLite 台账；cron job + `executions` 台账 | Hermes 的后台任务不是语音概念；完成后以合成消息事件注入会话 |
| 进度通知仲裁（`progress_notification_arbiter`） | `_enqueue_process_completion_notification` 短窗口 fan-in、`_classify_completion_target`、at-most-once 投递身份 | Hermes 约 100 行做 coalescing；LiveVoice 2,212 行因为要决定"现在能不能出声" |
| `TaskEventSubscription` 游标 | `claim_completion_delivery`/`release`/`drop`（claim 行，无 cursor）；唯一的 durable cursor 在 `hosted_room_policy_checkpoint._ensure_cursor_and_transcript` | consumer cursor 是核心级原语（Hermes 在 hosted room 用它做 exactly-once），故 F3 通用 |
| D1 checkpoint | 无；会话 transcript 的 watermark（`get_active_message_watermark`） | 六个 seam 里唯一无 Hermes 对应物 |
| D2 external-effect journal | `fire_claim_fence`（副作用在 fire claim 下执行，claim 丢失即 `_FireClaimLostDuringSideEffect`）+ `delivery_queue.enqueue` 幂等 + UNKNOWN 终态 | Hermes 用约 140 行表达"副作用只在拥有权下发生、不确定就标 unknown 不重放" |
| Direct project executor | cron 的 `_CronRunScope`/`_resolve_job_workdir`/`_launch_external_cron_worker`/worktree 维护 | 项目/worktree/patch 策略在 Hermes 也是 job 侧的，不在 core |
| `ProductCompositionRegistry` | `register()` 两行 + router include + lazy import | — |
| `live_voice_contract_v2` | `web_models` 三个请求模型 + docstring 里的 WS 协议 | — |
| `latency_measurement`/L0 | 无；`HERMES_VOICE_DEBUG=1` 的 stderr breadcrumb | — |
| voice mode `all|voice_only|off` | 同名概念（每聊天，JSON 持久化） | LiveVoice 对应的是 feature flag + activation journal |

### 5.2 逐模块解释与判断

每条按"Hermes 里这是什么 → LiveVoice 多了什么 → 是否合理必要"写；判断分三级：**必要**、
**合理但过重**、**不必要**。

1. **Browser Audio Edge（8,429）**。Hermes：`use-mic-recorder` 录一段文件，`voice-playback` 开一个
   WS 播 PCM，`voice-barge-in` 做 VAD；CLI 侧 `AudioRecorder` 直接读 sounddevice。LiveVoice 多了：
   多 device/page 的 ownership（`browserLiveVoiceOwnership`）、设备选择、AudioWorklet capture
   processor、playout receipt（证明播到了哪一帧）、verified-headset 近端插话候选、音频诊断。
   判断：ownership、playout proof、近端候选是**必要**（三进程拓扑 + D-115 需要"播放证据"）；
   4,099 行的 `productP1VoiceRoute.ts` 把四件事装在一起是**过重**；音频诊断 414 行应归观测。
2. **Web/Gateway media transport（17,409）**。Hermes：一个上传接口、一个 speak-stream WS、
   一个 PCM sink 抽象、每平台一个 `send_voice`。LiveVoice 多了：Browser↔Gateway 的 `LVM1` 二进制帧
   与控制对象、同源握手与 media ticket、三条 route（streaming STT、streaming TTS、dedicated media）
   各自的 lifecycle/backpressure/fallback、首帧诊断、Native 段。判断：帧协议与 ticket 是**必要**
   （Hermes 的 desktop 只播 PCM 不上传实时音频，LiveVoice 双向实时）；三条 route 各写一遍 lifecycle
   与 fallback 投影、registration 7,276 行混装 registration/product authority/diagnostics 是**过重**。
3. **Speech provider（9,909）**。Hermes：provider ABC + 注册表，每个 provider 几十到一百多行，
   `SentenceChunker` 一处切句。LiveVoice 多了：batch 与 streaming 双路径、TEXT 降级事实、
   transport cleanup owner、recognition commit owner、provider-neutral streaming conformance（31 个类）。
   判断：双路径与降级是**必要**（Hermes 没有流式识别，也不承诺降级）；每个文件都自带一套 owner/
   cleanup/snapshot 类是**过重**。Hermes 证明一个 provider 抽象 + 注册表 + 切句器 340 行够用。
4. **Committed input / product authority（16,850）**。Hermes：转写就是消息；授权只有
   `_is_user_authorized(source)` 一次调用；去重一个小字典。LiveVoice 多了：语义判断（`task_semantics`
   1,207）、pre-command 连续性、committed input journal（含 semantic pending contexts）、critical-token
   澄清、P3 confirmation ledger、product authority、production task intent、`p3_authenticated_composition`
   5,386 行的认证/翻译/构造根。判断：语义判断、确认、项目 scope 授权是**必要**（产品决定；Hermes
   把这些交给模型与平台 ACL）；四套一次性授权 CAS ledger（`p3_confirmation` 979、`product_authority`
   1,302、`production_task_intent` 内的确认消费、`unified_committed_input` 的 request binding）与
   5,386 行的组合根是**过重**，应合成一个 authorization owner + 一个 journal。
5. **Conversation Runtime（8,224）**。Hermes：一个状态机（desktop 5 个状态；CLI 用几个 Event 与
   flag）、一个 full-duplex 监听器、一个 interrupted latch。LiveVoice 多了：`AgentConversationRuntime`
   4,937 行的 response/presentation 权威、优先级事件循环与 effect outbox、播放期插话与生成期打断
   两套 fence（Native 第三套）、speculative dialogue。判断：跨进程的 response 权威与 effect outbox
   是**必要**；三套 fence 是**过重**，Hermes 的 `_fd_trip` 用同一个函数处理两个 phase。
6. **Agent bridge（3,015）**。Hermes：agent 在进程内，语音只多了 ack 回调与 sidecar 说明。
   LiveVoice 多了：`AgentBridgeRuntime` + `JiuWenSwarmRoundHarness` 两层 round 预留/取消、formal
   facade、tool gate。判断：一层薄 adapter 是**必要**（Agent 在 Jiuwen harness 后面，round 需要精确
   取消）；两层是**过重**；tool gate 只在 rail 存在前有意义。
7. **Task domain/control（5,342）**、**8. Task Store（15,175）**、**9. Project executor（6,755）**、
   **10. Checkpoint/effect（2,953）**、**11. Task event/progress（8,078）**。Hermes：语音层为零；
   后台工作在 core 用 §8.1 的约 3.3K 行台账支撑。LiveVoice 多了：`formal_task_models` 42 个值类型、
   `SqliteTaskStore` 一个 15,175 行的类、Direct attempt journal、D1/D2 值与 verifier、live/authority
   两种订阅、进度返回与仲裁。判断：LiveVoice 有 durable Task 是**必要**（产品要能在语音里派发并
   跟踪项目任务，Hermes 也有这个能力，只是在 core）；把通用 Task/Attempt/outbox/cursor/lease/
   settlement 放在 LiveVoice 里、并且规模是 Hermes core substrate 的 11 倍，是**层级与规模都不合理**。
   §8 给出按 Hermes 尺寸校准的下沉与删除分账。
8. **Presentation/history（2,045）**。Hermes：`_should_send_voice_reply` 三层判定 + `_send_voice_reply`。
   LiveVoice 多了：presentation 台账、P2 response generation owner、幂等 history writer。判断：**必要**
   （D-115：历史只记录被确认播放的内容），规模已接近目标。
9. **Formal Web/UI（16,906）**。Hermes：composer 语音按钮、菜单、设置字段、偏好、口语清洗、停止词，
   约 1.3K。LiveVoice 多了：9,344 行的集成面板（P1/P2/P3 owner、recovery、diagnostics、13 个通知
   仲裁函数）、三个 Task UI owner、三本同模式 journal、web activation。判断：Task UI、通知仲裁、
   activation journal 是**必要**（Hermes desktop 没有任务面板，任务完成只是消息）；一个 9,344 行的
   Panel 与三个平行 owner 是**过重**。
10. **Composition/config（19,826）**。Hermes：`register()`、router include、`_validate_voice` 9 行、
    lazy import。LiveVoice 多了：15,825 行 registry（25 个类，P1/P2/P3 handler 工厂 + 逐 handler
    的 scope/session/principal 校验）、P2 interaction adapter、配置→能力声明合同、组合根。判断：
    default-off 的组合根与能力声明是**合理**（多宿主部署）；registry 的规模**不合理**，Hermes 证明
    注册本身是两行的事，校验应在 owner 处做一次而不是每个 handler 一次。
11. **Observability（17,322）**。Hermes：debug breadcrumb、音频环境探测、doctor 脚本。LiveVoice
    多了：OTel 六文件、被动 profiling、音频诊断 JSONL、L0 测量、隐私 conformance、部署观测、
    fault harness。判断：隐私零泄露断言与 profiling 报告是**必要**（产品与 demo 要求）；三条通道
    各有 exporter/投影、无 caller 的 fault harness/privacy contract、部署观测放在生产路径是**不必要**。
12. **Schema/protocol（7,474）**。Hermes：无。LiveVoice 多了：Python contract v2（50 个类）、TS
    副本（81 个导出，52 个同名类型）、v1、composition contract、speech RPC。判断：一份 canonical
    schema 是**必要**（三进程 + TS/Python 双语言）；手写副本是**不必要**。
13. **Legacy/compat（3,058）** 与 **Test/reference in prod（2,661）**：Hermes 的对应量约 20 行。
    **不必要**，按 G1/G2 gate 退休。

## 6. 代码量对比

| 口径 | 官方 Hermes | LiveVoice | 倍数 |
|---|---:|---:|---:|
| 专属生产文件 | 18,140（59 文件） | 171,431（137 文件，不含 Native） | 9.5 |
| 共享宿主 segment | 2,125（40 个 Python 宿主文件；TS 宿主未计） | ≈4,300（4,054 归因，含 TS 宿主 + 未归因新增约 0.3K） | 2.0（偏高） |
| 生产面合计 | 20,265 | ≈175,700 | 8.7 |
| 可比集（去 wake word、Realtime 客户端、setup/doctor） | 17,887 | 171,431 | 9.6 |
| 非行为行占比（空行/注释/docstring） | 32% | 8% | — |
| 行为行估算 | ≈13,800 | ≈161,600 | 11.7 |
| 最大单文件 | `voice_mode.py` 1,572 | `product_composition_registry.py` 15,825 | 10.1 |
| 单文件 ≥ 2,000 行 | 0 个 | 21 个 | — |
| 语音相关测试 | 25,226（108 文件；测试/生产 1.24） | 后端 `tests/unit_tests/live_voice` 125.6K（98 文件；测试/生产 0.73，前端测试未计） | — |
| provider 数 | STT 8 个注册 key（6 个云 + local + local_command；command/plugin 为分发路径）、TTS 12 后端 + 4 流式（§1 的 "18 个" = 6 云 STT + 12 TTS） | STT/TTS 各 1 个 OpenAI 兼容家族 + OpenAI 流式 + provider-neutral 流式合同 | — |

两条读法：

- **按行为行看差距更大而不是更小**：Hermes 三分之一的行是注释与 docstring，LiveVoice 十二分之一。
  LiveVoice 的膨胀在类与校验，不在解释。
- **v1 目标 50K–65K 仍是官方可比集的 2.8–3.6 倍**。差在 Batch+Streaming 双路径与 TEXT 降级、
  三进程媒体协议、committed input 与确认/项目 scope 的产品策略、D1/D2 durability 的 Jiuwen 部分、
  DOM/audio/history 分面呈现证明。这些是 OpenJiuwen 要保留的合同，不是可删的重复。

## 7. 瘦身重构分析（在保证 LiveVoice 正确的前提下）

### 7.1 总计划不变的部分

官方对比没有改变总计划 §2 的移除清单（G1 现在可删 9,281 行；G2 legacy 单 owner 后约 3.7K；
G3 AgentCore cutover 后；G4 schema 单源后）、§5 的实施包与 §6 的 gate。按机制分账也不变：
死代码、legacy 与生产树内测试代码约 12–14K（总计划 §3 记 12K，逐模块验证 §3.1 记 14K；已逐项验证）、AgentCore 转移约 25K、观测收敛约 10K、schema 单源约
5K、并行 owner 与逐层重复校验的收敛约 69K（只确认方向）。规划中心 ≈50,200，实测预期 60K–65K。

### 7.2 官方对比新增或加强的判断

| 模块 | 官方 Hermes 给出的证据 | 对包的影响 |
|---|---|---|
| 3 Speech provider | 一个 provider ABC + 注册表 + 一个切句器（`tts_streaming.py` 340 行）承载 4 个流式实现；每个 provider 平均约 60–150 行 | B2e 拆 contract/传输/orchestration 时，以"一个 provider 抽象、一个 route lifecycle"为形态；6,000 是中心，4,500 可信 |
| 2 Media transport | `StreamingTTSConsumer` 229 行完成 delta→句→PCM→sink 与 settle/abort；`speak_stream_ws` 146 行完成整个 WS 协议 | B2a 的"三条 route lifecycle 合一"有现成形态：一个 consumer + 一个 handle 协议 |
| 4 Product authority | 授权是一次 `_is_user_authorized` 调用；去重是一个字典 | B2b 合成一个 authorization owner 的方向被印证；3,800 偏激进，5K–7K 更可信不变 |
| 5 Conversation Runtime | `_fd_trip` 一个函数处理 playback/generation 两个 phase | B2c 的"一个 response fence"有现成形态 |
| 11 Task event/progress | 完成通知 coalescing 约 100 行、at-most-once 身份约 40 行 | 仲裁与进度返回两套 queue/ACK/lease 合一后 2K–3K 更可信，1,500 偏激进不变 |
| 14 Composition | 注册两行、校验在 owner 处一次 | B2b 的 registry 抽取以"handler 自带校验、registry 只注册"为验收形态 |
| 15 Observability | 生产路径几乎为零 | 3,500 足够容纳隐私 conformance + 一个 exporter；B4 不放宽 |
| 7–11 Task 家族 | core substrate ≈3.3K | §8：AgentCore 侧 F1–F6 中心下调到约 4,100；Jiuwen 侧目标不变 |

### 7.3 能去掉多少（汇总）

| 阶段 | 可去掉 | 依据 |
|---|---:|---|
| 现在（A1，G1） | 9,281 | 零生产 caller，oracle 先迁（可去掉性验证 §4.1） |
| legacy 单 owner 后（D1，G2） | ≈3,700 | legacy 链 2,459 + L0 750 + AutoHarness 493 + AR-065 |
| AgentCore cutover 后（C2/C3，G3） | 模块 7–11 从 38,303 降到 v1 目标 7,100–8,600，离开 LiveVoice 29,700–31,200（总计划按机制记：AgentCore 转移约 25K，其余是死代码与模块内结构收敛）；AgentCore 侧另写约 4.1K 新代码，不是搬迁 | §8.4 |
| schema 单源后（B3，G4） | ≈5K | 三套 Python 家族与 TS 副本 |
| 观测收敛（B4） | ≈10K | 三通道合一 + 支持代码退休 |
| 结构收敛（B2a–e） | 方向约 69K，实测预期 45–55K | 三套 fence、四套 CAS、三条 route lifecycle、三个 Task UI owner、registry 逐 handler 校验 |

### 7.4 正确性守护

与逐模块验证 §4 相同：死代码退休以 import 扫描与 oracle 迁移为 gate；AgentCore 转移以
`test_persistent_task_core.py`（10,906 行）等 race/restart/corruption 用例为 adoption oracle，旧
Store 只读保留直到 canary 与 rollback 演练通过；观测与 schema 以隐私零泄露断言与字节/语义
等价为 gate；结构收敛只做行为保持的合并，前后测试集等价，加合成语音 journey 与物理 demo
journey。Hermes 的测试形态（测试/生产 1.26，替身留在 `tests/`）是 LiveVoice 退休生产树内 2,661
行测试代码时的参照。

## 8. 下沉到 AgentCore：按 Hermes core 校准的分析与瘦身

### 8.1 Hermes 的 agent core 如何拥有后台工作

| 组件 | LOC | 拥有什么 | 设计性质 |
|---|---:|---|---|
| `cron/executions.py` | 384 | 执行台账：`claimed → running → completed/failed/unknown`，`handoff_pending` 过渡，终态行不可改写，`recover_interrupted_executions` 把确证丢失的尝试标为 unknown 且不安排重试 | F1 + F4 的最小形态 |
| `cron/delivery_queue.py` | 379 | at-most-once 投递：`pending → delivering → delivered/failed/unknown`，按 execution_id 幂等入队，`claim_next` 原子认领，`recover_abandoned` 把死 owner 的行 fence 为 unknown，"never replay uncertain sends" | F2 outbox 的最小形态 |
| `tools/async_delegation.py` | 914 | 后台委托注册表 + SQLite 台账：`claim/release/drop/complete_completion_delivery`，重启后 `restore_undelivered_completions`，stale monitor，按会话打断 | F2 claim + F4 ownership |
| `gateway/run_notifications.py` 完成投递段 | ≈380 | 14 个方法（`_resolve_async_delegation_session`、`_completion_delivery_identity`、`_mark_completions_delivered_locked`、`_completion_identity_seen`、`_classify_completion_target`、`_settle_durable_claim`、`_preflight_completion_delivery`、`_deliver_completion_notification`、`_format_coalesced_process_completions`、`_record_coalesced_completion_siblings`、`_flush_process_completion_batch`、`_cancel_process_completion_batch_tasks`、`_enqueue_process_completion_notification`、`_enrich_async_delegation_routing`）：认领 durable 行、目标分类、at-most-once 身份、短窗口 coalescing | F2 consumer |
| `hermes_state_compression.py` turn lease | ≈120 | `try_acquire/acquire/refresh/release_session_turn_lease` 与 key helper；`SessionTurnLeaseLostError`（定义在 `hermes_state_errors.py`） | F4 lease |
| `cron/jobs.py` fire fence + `cron/scheduler.py` claim/heartbeat/sweep | 472 | `jobs.py`（98）：`_oneshot_run_claim_ttl_seconds`、`_job_running_in_this_process`、`_fire_job_lock`、`_under_fire_fence`、`fire_claim_fence`；`scheduler.py`（374）：`try_register_running_job`、`release_running_job`、`sweep_stale_inflight`、`mark_running_jobs_interrupted`、`drain_delivery_queue`、`_run_with_fire_claim_heartbeat`、`_FireClaimLostDuringSideEffect`、`_FireOwnership`、`_maybe_reap_dead_owners`、`_submit_with_guard`。每 job 的 fire fence 包住外部副作用，in-flight 去重，heartbeat 续约，stale sweep 强制释放，shutdown 标记 interrupted，dead-owner reap | F4 + F6 |
| `agent/subagent_lifecycle.py` | 416 | 公共合同：7 个 frozen dataclass + 状态枚举 + 错误类型 + 一个 service（launch/status/wait/cancel/result/reconnect），terminal 快照有界保留，从不返回活记录 | public API 的尺寸参照 |
| `tools/terminal_tool_background.py` | 233 | 后台进程 spawn + 完成 watcher | — |
| **合计** | **≈3,300**（3,298） | | |

四个可直接借用的设计规则：每个关注点一张 profile 本地的小表，而不是一个 15K 行的 Store；
UNKNOWN 是一等终态，不确定就不重放；终态行不可改写；拥有权来自进程存活 + TTL + claim token，
而不是复杂的 epoch 层级。这个后台工作 substrate 里没有 consumer cursor（用 delivered 标志与 claim 行；Hermes 唯一
的 durable cursor 在 hosted room 的策略投影里）、没有 checkpoint（transcript 就是状态）、没有 external-effect
journal（用 fire fence + 幂等入队）。

### 8.2 F1–F6 逐 seam 校准

| Seam | Hermes 对应物与尺寸 | LiveVoice 现状（行数） | 通用且需新增的 invariant | 校准后的规划中心（区间） | 原中心 |
|---|---|---|---|---:|---:|
| F1 Scoped Task/Attempt/Command/Result | `executions.py` 384 + 委托记录约 250 | `formal_task_models` 2,628 中的 Task/Attempt/command/result 值、`task_store` 的对应表 | `(scope, task)` 约束、Task–Attempt 关系、generation/revision CAS、幂等 command ledger、不可变 result、retry lineage、recover admission（含 `settle_unbound_queued_attempt`、`_settle_cancel_before_dispatch`、`project_has_unsettled_attempt`） | **900**（700–1,200） | — |
| F2 Transactional Event/Outbox | `delivery_queue.py` 379 + completion claim/release/drop ≈150 + preflight ≈100 | `task_store` outbox 表与 `_deliver_outbox` 等 | per-Task 单调 sequence、同事务 outbox、claim lease 与 `renew_outbox_claim`、complete/release/reclaim、dispatch receipt、busy/capacity defer | **900**（700–1,200） | — |
| F3 Consumer Cursor | `hosted_room_policy_checkpoint` 的 `_ensure_cursor_and_transcript`/`sync` ≈45 | `task_event_subscription` 1,568 的 authority replay 模式 | consumer/channel/scope/stream 身份、一行 cursor、expected sequence CAS | **250**（150–400） | — |
| F4 Execution Ownership/Cancel/Settlement | turn lease ≈120 + fire claim/heartbeat/sweep/interrupt 472 + `subagent_lifecycle` 416 | `project_code_executor` 的 attempt lease/ownership lock、`persistent_task_core` 的 settlement/drain | ExecutionRecord、owner lease/heartbeat/epoch、原子 admission、重复身份拒绝、单调 cancel settlement、terminal no-revival、restart reconcile、幂等 terminal callback、settlement fence 独立于不合作 delivery | **1,100**（900–1,500） | — |
| F5 Checkpoint Publication | 无（transcript watermark ≈10） | `durability_checkpoint` 499 + `durability_readers` 的 checkpoint prefix | publication reference、Task/Attempt/execution/source-event 绑定、digest/size/codec 元数据、publish/read verify 事务 | **350**（250–500） | — |
| F6 External-effect Journal | fire fence 98 + `_FireOwnership` 29 + 幂等入队 ≈40 | `durability_effects` 920 + effect prefix verifier + Direct journal 的效果部分 | provider key/replay policy、one-use authorization、append-only facts、claim lease/version、一个 reducer、unresolved-effect terminal fence、reconcile 端口、`latest_completed_project_effect` 的通用读端口 | **600**（450–900） | — |
| **合计** | Hermes 列分配 ≈2,500（§8.1 约 3,300 中其余约 800 行是 `terminal_tool_background` 与委托/通知台账里未对应到某个 seam 的部分） | | | **≈4,100（3,150–5,700）** | 5,300（3,600–8,100） |

校准规则：每个 seam 以 Hermes 用同类机制的行数为参照点（是参照不是下界：F3/F5 在 Hermes 只有几十行或没有；
F4 的下沿低于 Hermes 三项之和，因为 `subagent_lifecycle` 那 416 行公共合同层在 LiveVoice 由 C1 薄 adapter 承担），
增量只允许来自 LiveVoice 已在生产路径上证明需要的 invariant（当前分支重分析 §3.6 表列出的新 symbol）。原区间上沿 8,100 应视为
红线而不是预算：超过 5,700 的方案必须在 decision record 里说明 Hermes 的 substrate 缺了什么、
LiveVoice 产品为什么必须补。测试与 decision record 不计入此数。

### 8.3 不能因为 Hermes 没有就下沉的东西

| LiveVoice 独有责任 | Hermes 里的最近物 | 判定 | 理由 |
|---|---|---|---|
| 语义判断与 pre-command 连续性（`task_semantics`、`semantic_continuity`、semantic pending contexts） | 无 | `JIUWEN_KEEP` | 产品语义，依赖 Voice 与 Jiuwen 目录；已正确 `DIRECT_REUSE` 了 `openjiuwen.core.foundation.llm` |
| committed input journal（`unified_committed_input`） | 入队 | `JIUWEN_KEEP` | 存的是语音 digest 与控制恢复，不是 Task truth |
| `PresentationLedger`、P2 response generation owner | `audible` 布尔 | `JIUWEN_KEEP`（L1） | 语音呈现语义 |
| 进度通知仲裁、进度返回 | coalescing ≈100 行 | `JIUWEN_KEEP`，两套机制合一 | 决定"现在能不能出声"是语音策略；其 queue/ACK/lease 机制不是 F2 |
| Direct project attempt journal、`DirectProjectManagedBaselineReader` | cron workdir/外部 worker | `JIUWEN_KEEP`，收缩为 Git/worktree 事实 | 项目/patch/tree 指纹是 Jiuwen 策略；效果 truth 归 F6 后不再双份 |
| D1 checkpoint 值/codec、D2 effect 值/codec | 无 | `JIUWEN_KEEP`（codec），只有 publication 与 reducer 通用 | Voice/Project 语义在值里 |
| tool hold、speculative dialogue | busy 降级 | `JIUWEN_KEEP` | 无 durable owner、无 lease、无 restart reconcile，下沉只会给 AgentCore 一个无 adopter 的 public surface |
| 三套 fence（播放期、生成期、Native） | `_fd_trip` | `JIUWEN_KEEP`，合成一套 | 语音 response 语义 |
| consumer cursor | hosted room durable cursor | **通用**，F3 | Hermes 自己在 core 里用它做 exactly-once |
| checkpoint publication | 无 | **通用但最弱**，F5 | 见 §8.6 |

### 8.4 转移分账：Task 五模块 38,303 行去哪里

| 去向 | 行数 | 内容 |
|---|---:|---|
| 留在 LiveVoice（Jiuwen adapter/产品，模块 7–11 的 v1 目标） | ≈7,100（更可信 8,600） | envelope 投影、Executor 选择、project seam、D2 补偿策略、语音/文本进度呈现、importer/rollback reader |
| 离开 LiveVoice | ≈29,700–31,200 | 总计划按机制记：AgentCore 转移约 25K（`SqliteTaskStore` 的通用表与 reducer、`formal_task_models` 的通用值类型、`task_event_subscription` 的游标实现、Direct journal 的效果部分）、死代码约 1.5K（`TaskCore` 714、六个 `durability_*` 文件复制的 helper、`_LEGACY_DIRECT_*` 过渡物，记在"死代码与 legacy"）、其余为模块内结构收敛（两套 queue/ACK/lease 机制合一、Direct journal 收缩；逐模块验证 §3 第 7–11 行） |
| 其中在 AgentCore 重写为 F1–F6 的新代码 | ≈4,100 | §8.2；是新写的通用实现，不是搬迁的 LiveVoice 行 |
| 多仓净减 | ≈25,600–27,100 | 离开量减去 AgentCore 重写量 |

与总计划"AgentCore 转移约 25K"的机制口径一致；变化只在 AgentCore 侧：重写量的规划中心从约 5.3K 校准为约 4.1K。

### 8.5 AgentCore 自身的瘦身规则（从 Hermes 借来的验收形态）

1. **每个 seam 一张小表、一个 owner**：不建 God DAO；Hermes 的执行、投递、委托各自 ≤ 1K 行。
2. **public API 以 `subagent_lifecycle.py` 为尺寸级**：每个 seam 的 public export 不超过十来个
   不可变记录 + 一个 service；AgentCore 零基线审计 §7 拒绝的 public export 47→95、33 个纯转发
   Manager 方法、1.6K 行只有两个操作的 `cursor_dao.py`，用这个尺寸级复核。
3. **UNKNOWN 是一等终态**，terminal 行不可改写，不确定不重放；这三条直接对应 F4 的
   "terminal no-revival"与 F6 的"unresolved-effect terminal fence"，不需要额外状态机。
4. **拥有权 = 存活 + TTL + claim token**：epoch 只在需要区分同一 owner 的两代时引入，不作为默认层。
5. **没有生产 consumer 的东西不进 core**：Hermes 的 streaming TTS consumer 在树内没有 adapter
   adopter，是 core 代码里"先建抽象后无人用"的反例；AgentCore 每个 seam 提交时必须带 LiveVoice
   这一个真实 adopter 的 C1 adapter 草案。
6. **同口径计量**：seam 的 LOC 报告用本文的 physical LOC 口径，与 §8.2 的区间对照。

### 8.6 给 A2 decision record 的三条建议

1. **F5 并入 F6 评估**：checkpoint publication 是唯一没有 Hermes 对应物的 seam；把"发布了一个
   checkpoint"记为 F6 的一种 append-only fact（kind=checkpoint，带 digest/size/codec 元数据）可以
   少一个 public surface。若 Jiuwen 的 D1 resume 需要独立的 publish/read verify 事务，再单列。
2. **F3 以 Hermes hosted-room cursor 为原型**：一行 cursor + expected sequence CAS，不做 handle
   对象、不做 DAO。
3. **F2 的 busy/capacity defer 以 `delivery_queue` 的 `unknown` 与 `async_delegation` 的
   `release_completion_delivery` 为原型**：defer 是 claim 结果之一，不是新状态机。

## 9. 与个人仓库对比的差异

此前的对标对象 `bielcarpi/hermes-live-voice@3dd8af38`（25,254 行）是一个产品级独立仓库，自带
`LiveGatewaySession`、`TaskSupervisor`、`FileTaskStore`、Hermes `/v1/runs` adapter；因此模块 7–11
曾有 1,075/2,075/312 行的"Hermes 对应物"，模块 3 曾是 5.5 倍、模块 13 曾是 3.6 倍。官方 Hermes
的语音层没有 Task 代码，provider 面更宽，UI 更薄：模块 3 变为 1.6 倍、模块 13 变为 13 倍、模块
7–11 的对照改为 core substrate。两份对比对总计划的削减机制与包的结论相同；官方对比额外校准了
AgentCore 的尺寸并提供了每个收敛项的现成形态。

## 10. 本文不授予什么与证据入口

本文不改变 `STATUS.md`，不宣告任何包开始，不删除代码，不授予 AgentCore 接受或安装信用，不
授权远端操作；§8.2 的区间是规划中心，最终数字由 A2 的六份 decision record 决定。

- 复现 Hermes 数字：`python scripts/live_voice/slimming/hermes_voice_inventory.py --repo "D:/XGG AI/openjiuwen/hermes-agent-review-9a84bee26"`
- 复现 LiveVoice 数字：`python scripts/live_voice/slimming/module_buckets.py --rev HEAD`
- 总计划：[LIVEVOICE_SLIMMING_MASTER_PLAN.md](../roadmap/LIVEVOICE_SLIMMING_MASTER_PLAN.md)
- 逐模块验证：[OPENJIUWEN_LIVEVOICE_SLIMMING_THESIS_VERIFICATION_2026-09-05.md](OPENJIUWEN_LIVEVOICE_SLIMMING_THESIS_VERIFICATION_2026-09-05.md)
- 当前分支新增代码分析：[OPENJIUWEN_LIVEVOICE_CURRENT_BRANCH_ANALYSIS_AND_PLAN_2026-09-05.md](OPENJIUWEN_LIVEVOICE_CURRENT_BRANCH_ANALYSIS_AND_PLAN_2026-09-05.md)
- AgentCore 零基线审计：[OPENJIUWEN_AGENTCORE_FOUNDATION_ZERO_BASE_AUDIT_2026-09-01.md](OPENJIUWEN_AGENTCORE_FOUNDATION_ZERO_BASE_AUDIT_2026-09-01.md)
- 历史（个人仓库对标）：[OPENJIUWEN_LIVEVOICE_HERMES_MODULE_ARCHITECTURE_ZH_2026-08-31.md](OPENJIUWEN_LIVEVOICE_HERMES_MODULE_ARCHITECTURE_ZH_2026-08-31.md)
