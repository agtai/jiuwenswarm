# Live Voice「说完最后一个字 → 听到第一个字」逐段耗时分解 — 2026-09-03

> 本文只做**测量与分解分析**，不改任何产品代码。优化优先级仍以
> [STATUS](../STATUS.md) 与 [延迟优化计划](../roadmap/LATENCY_OPTIMIZATION_PLAN_2026-08-18.md)
> 为唯一权威；本文提供的数字用来给这些计划的抓手排序。

## 1. 数据来源与口径

- **测量源**：2026-08-25 已被用户判 `PASS`（[D-097](../decisions/DECISIONS.md)、
  行为源 `ba06d9825`）的普通 Chrome 暖态 L0 运行，证据目录
  `logs/l0-ordinary-d095-ba06d9825-20260825/`。真实 OpenAI STT/TTS、真实
  JiuwenSwarm Agent（`deepseek-v4-flash`）、固定语料、普通已安装 Chrome、
  一次人工手势解锁播放。共 **40 轮**（20 首音 + 20 打断），全部 `eligible`。
- **分解工具**：`scripts/live_voice/l0_segment_breakdown.py`（本分支新增）。它把
  L0 观测里 18 个内容无关里程碑按 `provider_eot` 时间边界归轮，逐段算
  p50/p95/max。下表取 **20 个首音轮**（打断轮的采集收尾时序被 barge 扰动，
  不用于首音分解）。
- **当前 HEAD 有效性**：8/25 源 `ba06d9825` 到当前 `fec2bbe2d` 相隔 52 个提交，
  逐文件核对后，延迟关键路径文件里**只有** `productP1VoiceRoute.ts` 被动过，
  且改动仅为新增 `capture_during_playout` 选项（默认保持原行为）与一条首帧诊断
  日志，**不改 VAD、播放提前量、下行开启时序、TTS 流水线、队列容量**。因此
  8/25 的分解对当前代码的延迟画像仍然成立。VAD/播放提前量常量在当前 HEAD 实测：
  `silence_duration_ms = 1200`、`PLAYOUT_STARTUP_LEAD_SECONDS = 1.0`、
  `_DEFAULT_MAX_PENDING_FRAMES = 8`（均未变）。

### 口径关键点：两个「说完」不是一回事

L0 的锚点 `provider_eot` = **服务端 VAD 判定的回合结束**，它发生在用户
**真正停止说话之后又静音 `silence_duration_ms = 1200ms`** 才触发。所以：

- **机器可测部分**（`provider_eot → 首音`）：p50 **≈ 4.83s**、p95 ≈ 5.60s
  （8/25 证据原文；本文工具复算锚点 p50 4.96s，差异来自归轮方式，量级一致）。
- **用户真实感知**（用户闭嘴 → 听到第一个字）：还要在前面加 VAD 静音等待
  ≈ **1.2s**，即 p50 **≈ 6.0s**、p95 ≈ 6.8s。

用户问的「说完最后一个字到听到第一个字」是后者，约 **6 秒（p50）**。

> 备注：记忆里曾有「机器部分约 11.5s」的说法，那是**测量前**的结构性投影
> （假设 Agent 6–8s + 1.0s 提前量 + 1.2s VAD）。实测 `deepseek-v4-flash`
> 首 token 只要约 2.1s，比旧假设快得多，所以真实值约 6s，明显好于旧投影。

## 2. 逐段分解（20 首音轮，p50）

从用户闭嘴到听到第一个字，按发生顺序：

| # | 段（里程碑区间） | p50 | p95 | 归属 | 说明 |
|---|---|---:|---:|---|---|
| 0 | 闭嘴 → 服务端 VAD EOT | ~1200 | ~1200 | **Live Voice 配置** | `silence_duration_ms=1200`，等静音判定回合结束 |
| 1 | EOT → STT final | 421 | 1095 | Provider(STT) | OpenAI 流式识别返回最终文本 |
| 2 | STT final → 统一提交 | 172 | 189 | **Live Voice** | 语音承诺回合提交 |
| 3 | 提交 → Agent 请求开始 | 40 | 51 | **Live Voice** | 分派到 Agent/Task 路由 |
| 4 | Agent 请求 → 首个 delta | **2101** | 2697 | 模型(LLM) | `deepseek-v4-flash` 首 token 前的思考 |
| 5 | 首 delta → 首个可念句 | 36 | 59 | 模型/Runtime | 短答里首句≈全文 |
| 6 | 可念句 → chat.final | 5 | 6 | 模型 | 短答几乎瞬间收尾 |
| 7 | chat.final → TTS 请求 | 128 | 134 | **Live Voice** | 生成 PresentationUnit 并下发网关 |
| 8 | TTS 请求 → Provider 首块音频 | 813 | 1031 | Provider(TTS) | OpenAI TTS 产出第一块音频 |
| 9 | Provider 首音 → 下行 ticket | 6 | 7 | Live Voice | 网关签发下行票据 |
| 10 | 下行 ticket → 浏览器首帧 | 329 | 346 | **Live Voice 架构** | 浏览器新开专用媒体 WS（连接+attach+首帧到达） |
| 11 | 浏览器首帧 → WebAudio 调度 | 0 | 1 | Live Voice | 入队 |
| 12 | WebAudio 调度 → **实际出声** | 680 | 698 | **Live Voice 配置** | 固定 1.0s 播放提前量缓冲 |

（各段 p50 之和 ≈ 4731ms；端到端锚点 p50 ≈ 4960ms。两者不等是因为「各段 p50 之和」
不等于「和的 p50」，量级一致即可。）

## 3. 哪些是 Live Voice 带来的时延

把 12 段按「谁的责任」聚合（p50）：

| 类别 | 合计 p50 | 占约 5.9s 的比例 | 明细 |
|---|---:|---:|---|
| **Live Voice 自有开销**（不换模型/Provider 就能优化） | **~2555ms** | **~43%** | VAD 静音 1200 + 提交/分派 212 + chat.final→TTS 128 + 下行开启 335 + 播放提前量 680 |
| 模型（LLM 首 token，最大单块） | ~2142ms | ~36% | Agent 首 delta 2101 + 收尾 41 |
| Provider（STT+TTS，Live Voice 选型但延迟在外部） | ~1234ms | ~21% | STT 421 + TTS 首音 813 |

结论：

- **最大单块是模型首 token（2.1s，36%）**，这不是 Live Voice 管线的锅，但 Live Voice
  可以通过「先念一句真话的确认语」来降低**感知**延迟，或换更快模型/裁剪上下文来降**实际**值。
- **Live Voice 自有开销约 2.55s（43%）**，是不动模型/Provider 就能收割的部分。其中最肥的三块：
  VAD 静音 **1200ms**、播放提前量 **680ms**、下行开启 **335ms**。

## 4. 优化建议、难度与预计效果

按「性价比」排序。数字均相对本基线的 p50。

### 抓手 A：自适应播放提前量（固定 1.0s → 自适应 200–300ms）
- **改哪**：`browserAudioIOAdapter.ts` 的 `PLAYOUT_STARTUP_LEAD_SECONDS`，按
  Provider 到块间隔与解码健康度做自适应缓冲（计划 §4 已给形状）。
- **难度**：**低–中**。一个常量→一段自适应逻辑 + 欠载/重缓冲护栏。
- **预计效果**：**-0.4s p50**（680→~250ms）。**风险**：过激会让 p95 欠载/爆音，
  需前提把网关 `_DEFAULT_MAX_PENDING_FRAMES=8` 适当加大（在途仅 160ms）。

### 抓手 B：下行 socket 与 TTS 合成并行预开（335ms）
- **改哪**：`productP1VoiceRoute.ts::playAgentText` 当前在 `synthesizeAuthoritative`
  返回**之后**才开专用媒体 WS。可把下行连接/attach 与合成并行发起，保持 generation
  fence。计划 §4「不要用后继采集就绪去阻塞首个下行」是同一处代码的邻居。
- **难度**：**中**。socket 生命周期 + 取消栅栏 + 失败要降级不能吞答案。
- **预计效果**：**-0.2~0.3s p50**。风险低（纯提前建连）。

### 抓手 C：VAD 静音 1200ms → 800ms 或语义 VAD（最多 -0.4s）
- **改哪**：`streaming_speech.py::ServerVadConfig.silence_duration_ms`；或接语义 VAD。
- **难度**：**中**。必须用中文换气语料重跑 false-EOT / missed-EOT / 时延三指标
  （D115 当年正是因为换气误断把它从 500 提到 1200）。语义 VAD 还需 Provider 能力开关。
- **预计效果**：**-0.4s p50**（到 800ms）。**风险**：正确性——静音太短会把换气当结束，
  切断用户说话。这是延迟与正确性的硬权衡，**不能只看延迟**。

### 抓手 D：句级 Agent→TTS 流水线（结构性最大杠杆，但对短答收益小）
- **改哪**：Conversation Runtime 里放一个「稳定句 owner」，在 `chat.final` 之前
  按保守句界把第一句作为权威 AUDIO 候选放出去；barge-in/改写/过期都要取消
  （计划 §5，`liveVoiceStreamingSpeech.ts` 已有句切分/改写/过期 oracle 可复用）。
- **难度**：**高**。改写回退、十进制/代码块内标点、过期 generation、历史权威仍归最终答案——
  这些都要处理，是计划里最重的一包。
- **预计效果**：**对本语料的短答几乎为 0**（因为这里 chat.final ≈ 首 delta+40ms）。
  **对真实多句长答是几秒级**：长答里 Agent 要 6–8s+，当前 TTS 死等 chat.final；
  改成首句就绪（约 +2.1s）即可开念。计划目标是 p50 -40%、把普通对话拉到 5–7s 带。
  **想真正把「6 秒」压到「2–3 秒」，这一包是必经之路，别的抓手都是边角。**

### 抓手 E：真话确认语降低感知延迟（不改实际值）
- **改哪**：Conversation Runtime 对确实慢的工具/Task 回合，先发一句短的、
  基于真实状态的 AUDIO 确认（计划 §5）。
- **难度**：**中–高**。必须真实（accepted/queued 不能念成 running/completed），
  且 barge-in 能取消。
- **预计效果**：**感知延迟目标 3–4s**（实际值不变）。适合掩盖那 2.1s 的模型首 token。

### 抓手 F：EOT 后串行化改并行 + 提交精简（约 -0.2s）
- **改哪**：`productP1VoiceRoute.ts` 的 EOT 收尾（排空→ACK→关上行→才发 final）与
  STT-final 获取并行（计划 §4）；第 2/3 段的提交/分派开销顺带压。
- **难度**：**低–中**。要保住完整帧/ACK 证明，不能简单提前调用 finish。
- **预计效果**：**-0.1~0.2s p50**。

### 不建议（计划已否）
- 全局 VAD 回 500ms（正确性回退）、无脑把媒体队列铺到 64 帧（+1.28s 陈旧积压）、
  Opus 当首要杠杆、raw delta 直接浏览器 TTS（不可撤回的临时音频）。

## 5. 汇总：把 6 秒压到几秒的路线

| 阶段 | 抓手 | 累计预计 p50 | 难度 |
|---|---|---:|---|
| 现状 | — | ~6.0s | — |
| 低风险管线批 | A + B + F | ~5.1s | 低–中 |
| 加 VAD 调参 | + C | ~4.7s | 中（含正确性回归） |
| 结构性重构 | + D（长答场景） | 普通对话 **~5→7s 带**、短答边际 | 高 |
| 感知优化 | + E | 感知 **3–4s** | 中–高 |

即：**不改模型的前提下，低风险管线批能把机器部分从 4.8s 压到约 3.9s（-0.9s，与计划 §7
的 -1.0s 目标一致）**；要突破到「2 秒级」的观感，必须叠加句级流水线（D）与确认语（E），
或换更快模型缩短那 2.1s 的首 token。所有目标都以**冻结环境+语料+样本量后的实测**为准，
不接受无实测的「2 秒」结论。

## 5b. 新基线核验（w3 推进 9 提交后，2026-09-03）——**已修正：需要更新**

w3 从 `fec2bbe2d` 前进到 `69c82b656`（9 个提交：生成打断、OpenAI Realtime 原生、
任务语义、去词法语音确认、checkpoint 泛化等，+21k 行）。对本文数据做了**代码事实核验**
（物理复测需人工普通 Chrome，见 §6）。

> **修正记录**：本节首版曾判"结构与结论不变、无需更新"。该判断只核对了常量、chat.final
> 门控、合成入口、下行时序与 STT，**漏查了"新插入的模型调用"这一类**。复核后发现 9 个提交
> 在首音关键路径上新增了两次串行模型调用（下文 ①②），本文 §2/§3 的数字对新基线
> **不再完整**。以下为修正后的结论。

### ① 每轮新增：提交后的语义解析模型调用（落在段 3）

- **代码事实**：`product_composition_registry._resolve_semantic_input`（5027 行）在
  `semantic_binding is None`（即每个新提交轮）时**无任何分类器短路**，直接调用
  `p3_authenticated_composition.resolve_production_semantics` →
  `task_semantics.TaskSemanticResolver.resolve()` → `model.invoke`，预算
  `SEMANTIC_MODEL_TIMEOUT_SECONDS = 45s`。它在 `agent_request_start` 里程碑
  （`agent_bridge_runtime.py:894`）**之前**执行。
- **影响**：本文段 3（提交→Agent 请求开始）在 8/25 为 **40ms**，因为当时该解析器
  不存在（`task_semantics.py` 于 `7a6ea64a3`/`87248911f` 新增）。新基线上**每一轮、
  含纯短对话**都要在此多付一次模型调用（外部观测约 1.1–2.1s，见下"未独立复测"说明）。
- 其后还有两次**仅任务/委派轮**触发的模型调用：委派授权校验（`task_semantics.py:995`，
  最多 2 次尝试；用于防误建任务，**不能删**）与 `task.adjust` 修订（`:1052`，12s 预算）。

### ② 工具轮/长答新增：回答完成后的口语二次修订（落在 chat.final 之前）

- **代码事实**：`runtime/agent_adapter/formal_live_voice.py:85 finalize_spoken_answer`，
  由 `c707c1e2d` 引入，8/25 基线与 `fec2bbe2d` **均不存在**。触发条件
  `len(candidate) > 200 or tool_results`（`spoken_tool_results` 收集本轮**所有**工具结果，
  故任何跑过工具的轮次必触发）；`asyncio.timeout(12)`；超时/失败回退原答案。
  调用点 `interface_deep.py:9558`：在 `chat.final` 事件上、**yield 最终 chunk 之前**同步
  等待——即 TTS 能启动之前的一段纯串行等待，无独立开关。
- **影响**：本文 §2 语料为短无工具对话（≤200 字、无工具），**从未触发**该修订，故
  8/25 数字对短对话仍成立；但对**工具轮/长答**，chat.final 前会多出最长 12s 的串行等待，
  且超时时白等 12s 后仍念原长答（外部观测 11.98s 超时、9.80s 完成，见下）。

### 归属修正：这两项是 Live Voice 的**设计开销**，不是"模型固有延迟"

本文 §3 把"Agent 首 token 2.1s"归为模型固有。修正后需区分：**Agent 原本执行任务的模型
耗时**（固有）vs **Live Voice 为语义判断、口语修订额外插入的模型调用**（设计开销，
可优化）。①② 均属后者，应计入"Live Voice 自有开销"。对短对话，Live Voice 份额从 43%
上调（加上①约 1–2s）；对工具轮/长答，①+② 合计可达 **10–14s**，远超 §4 任何单个抓手。

### 数据有效性结论（替换首版）

| 场景 | 8/25 数字是否仍可用 | 说明 |
|---|---|---|
| 短无工具对话 | **部分可用** | 段 0–2、4–12 结构与量级不变；**段 3 已失效**（40ms → +1 次语义模型调用） |
| 工具轮 / 长答（>200 字） | **不可用** | 新增 ①+② 串行等待，本文语料未覆盖，须重测 |

未变项（仍成立）：三个可调常量（VAD 1200 / 提前量 1.0 / 在途帧 8）、L0 里程碑集、
抓手 D 未实现、`synthesizeAuthoritative` 仍为正式路径合成入口、STT 客户端改写不加往返。

**未独立复测声明**：①②的**存在、触发条件、预算、串行位置**均为本文源码核验；其
**实测秒数**（语义 1.1–2.1s / 2.74s+1.74s，修订 11.98s 超时 / 9.80s）来自外部会话
的运行日志，本文未能取得原始日志、亦未做物理复测，仅确认其与代码机制一致。

### 修正后的抓手排序（替换 §4/§5 的顺序）

1. **收窄口语二次修订（②）**：让首答直接形成≤200 字、经核实的口语结论；把触发条件从
   "有工具结果即修订"收窄；超时不应白等 12s 后仍退回长答。难度中，**单项收益 10–12s**（工具轮）。
2. **精简语义链（①）**：减少重复上下文准备、精简输入；保留委派授权校验（防误建任务），
   不得退回关键词规则。难度中，收益 1–2s/轮（**每轮**都受益）。
3. 其后才是原 §4 的 A（提前量）、B（下行预开）、F（EOT 并行）、C（VAD）——合计约 1s。
4. 长答仍慢时再做 D（句级分段播报）。

**唯一值得注意的新变量**：这批提交引入了 **OpenAI Realtime 原生双工路由**（模型级
speech-to-speech，独立于本文测的正式 STT→LLM→TTS 链路）。若产品切到该路由，
本文段 1+4+8（≈3.3s）会被单条双工流取代，但历史 p95 3.06s 的口径是预录音输入、
浏览器 EOT→WebAudio 启动，**不能**用于预测含工具/后台任务的完整业务延迟，
建议对该路由单独立一份 L0 基线。

- **三个可调常量全部未变**：`silence_duration_ms=1200`、`PLAYOUT_STARTUP_LEAD_SECONDS=1.0`、
  `_DEFAULT_MAX_PENDING_FRAMES=8`。
- **L0 里程碑集未变** → 旧数据可直接比较，分解工具仍适用。
- **抓手 D（句级 Agent→TTS 流水线）未实现** → 段 5–8 的 chat.final 门控结构不变；
  `first_stable_speakable_sentence` 仍只是观测点、不触发 TTS。
- **正式路径时序 seam 未变**：`synthesizeAuthoritative` 仍是正式路径合成入口
  （`nativeDelivery ?? synthesizeAuthoritative` 只在新的 Realtime 原生路由分流），
  下行开启顺序与播放提前量未动。那 +1067/+1045 行主要是 Realtime 原生路由、任务语义、
  边界守卫，与首音路径正交。STT 客户端改写只动 socket 清理/关闭预算与长采集上限
  （35s→61.5+3.5s），不加首音路径往返。

绝对 p50 数值仍会有正常的 Provider/模型逐轮抖动，但这 9 个提交里没有任何改动会系统性
移动某一段，故不重跑也可用。

**唯一值得注意的新变量**：这批提交引入了 **OpenAI Realtime 原生双工路由**（模型级
speech-to-speech，独立于本文测的正式 STT→LLM→TTS 链路）。若产品未来切到该路由，
本文段 1+4+8（STT+首 token+TTS 首音，≈3.3s / 占约 55%）会被单条双工流取代——
那可能是比正式路径任何抓手（A–F）都大的延迟改写。**真正的延迟故事未来可能转移到原生路由上**，
建议对该路由单独立一份 L0 基线。

## 6. 复现实测（可选，需人工普通 Chrome）

服务已按受控启动器部署（`formal-web-validation`，四端口 5173/18092/19000/19001）。
自动批次面板为**普通已安装 Chrome + 一次人工点击**设计，内置/自动化浏览器的语音
开启会停在准备状态（见 2026-09-02 启动记录），因此新一轮物理数据需人工在普通
Chrome 里点一次「开始自动批次」并授权麦克风：

```
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/live_voice/run_l0_ordinary_chrome_series.ps1 -EnvironmentRef ordinary-chrome-machine-current
```

跑完后对新证据目录执行分解：

```
.venv/Scripts/python.exe scripts/live_voice/l0_segment_breakdown.py --evidence-directory <新证据目录>
```
