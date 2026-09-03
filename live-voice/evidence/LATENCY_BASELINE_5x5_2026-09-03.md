# Live Voice 分场景「说完最后一个字 → 听到第一个字」实测基线 — 2026-09-03

> 本文是**实测**，替代 [LATENCY_SEGMENT_BREAKDOWN_2026-09-03.md](LATENCY_SEGMENT_BREAKDOWN_2026-09-03.md)
> 里基于 8/25 旧语料的推算。优先级仍以 [STATUS](../STATUS.md) 为权威。

## 1. 方法与口径

- **被测源**：w3 `69c82b656`（含语义解析器与口语二次修订的新基线），受控启动器
  `formal-web-validation` 部署，真实 OpenAI STT/TTS + `deepseek-v4-flash`，隔离数据目录
  `jiuwenswarm-data-live-voice-p3-9-acceptance-20260831-215317`，可丢弃项目 `proj_2b0bce69`。
- **驱动器**：`scripts/live_voice/latency_baseline_driver.py`（本分支新增，无浏览器）。用 OpenAI TTS
  合成 5 段中文语料，升采样 48k，按 **20ms 实时配速**送进专用媒体上行，尾部追加 2s 静音让服务端 VAD
  判定回合；随后与浏览器完全相同地走 `recognize_streaming_result → unified.submit（网关注入
  auth/voice claim/engine）→ notification.next(批 16) → chat.final → synthesize_batch → 下行 WS 首帧`。
- **"说完最后一个字"** = 驱动器发出**最后一个非静音帧**的时刻（用户真正闭嘴），不是 L0 的
  `provider_eot`。**"听到第一个字"** = 下行首个音频帧到达 + **浏览器尾巴 1009ms**（下行首帧→WebAudio
  实际出声，取 8/25 实测 p50：建连 329 + 播放提前量 680；该段代码未变，见 §6 声明）。
- **服务端切分**：`scripts/live_voice/latency_baseline_split.py` 用 `llm.log` 的 `llm_call_start` 偏移
  与 `agent_server.log` 的 submit/chat.final 锚点，把 Agent 段切成"语义解析 / 主模型 / 主模型之后
  （口语修订等）"。llm.log 只可靠记录 start，时长按串行相邻 start 差推得。
- **轮数**：每档 5 轮（short 补跑 2 轮后 6 成功 / 1 失败，失败为识别 authority 间歇竞争，
  见 §6）。n=5 时 **p99 ≈ max**，按用户要求同时给 mean / p50 / p99。
- 语料（语音）与预期触发：

| 档 | 语音内容 | 答案均长 | 预期触发 |
|---|---|---:|---|
| short | 请用一句话告诉我，你是谁。 | 41 字 | 仅每轮语义解析 |
| medium | 请用大约二百五十字介绍一下机器学习的基本概念。 | 203 字 | 语义 + 口语修订（>200 字） |
| long | 请详细介绍人工智能的发展历史，分成五个阶段… | 235 字 | 语义 + 口语修订 |
| tool | 请运行 git status 命令，告诉我当前项目的状态。 | 65 字 | 语义 + 口语修订（工具结果触发） |
| task | 帮我创建一个后台任务，任务内容是整理这个项目的 README 文件。 | 63 字 | 语义 + 委派授权校验 |

## 2. 总用时（每档 mean / p50 / p99 / max，ms）

| 档 | 说完→下行首帧 mean | p50 | p99 | max | **用户感知 p50**（+1009 浏览器尾巴） | 感知 p99 |
|---|---:|---:|---:|---:|---:|---:|
| short | 5882 | 5865 | 6218 | 6224 | **≈ 6.9 s** | ≈ 7.3 s |
| medium | 15178 | 15036 | 18970 | 19034 | **≈ 16.0 s** | ≈ 20.0 s |
| long | 15578 | 16834 | 19525 | 19583 | **≈ 17.8 s** | ≈ 20.6 s |
| tool | 13732 | 10598 | 19249 | 19262 | **≈ 11.6 s**（mean 14.7 s，双峰） | ≈ 20.3 s |
| task | 7539 | 7526 | 7933 | 7942 | **≈ 8.5 s** | ≈ 9.0 s |

tool 档双峰：3 轮 ≈10.5s、2 轮 ≈19s（修订撞 12s 超时），所以 mean 与 p50 差 3s。

## 3. 逐段用时（p50，ms）

| 段 | short | medium | long | tool | task | 责任方 |
|---|---:|---:|---:|---:|---:|---|
| 闭嘴 → 服务端 EOT（VAD 1200 + Provider 检测） | 2071 | 2133 | 2027 | 2146 | 2011 | **Live Voice 配置** |
| EOT → 上行 ACK 排空 | 46 | 56 | 36 | 57 | 23 | Live Voice |
| 排空 → STT final | 444 | 501 | 469 | 502 | 510 | Provider |
| `unified.submit` RPC 往返（**语义解析同步在内**） | 1561 | 1784 | 1593 | 1510 | **2888** | **Live Voice** |
| ├ 其中语义模型调用（切分器） | 1395 | 1630 | 1419 | 1334 | 2707 | Live Voice |
| └ 其中分派/日志 | 166 | 154 | 174 | 176 | 181 | Live Voice |
| submit 返回 → 首条通知 | 44 | 43 | 43 | 44 | 44 | Live Voice |
| submit 返回 → 首个 delta | 785 | 676 | 698 | 1974 | 1096 | 模型 |
| submit 返回 → chat.final | 1189 | **9641** | **11843** | **5742** | 1451 | 模型 + **修订** |
| ├ 其中主模型（切分器，到下一次调用/final） | 1197 | 2265 | 2764 | 1460 | 1456 | 模型 |
| └ 其中主模型之后到 final（口语修订等） | — | **6984** | **9240** | **4158**† | — | **Live Voice** |
| final → TTS 首块返回 | 587 | 706 | 584 | 591 | 642 | Provider |
| TTS 返回 → 下行首帧 | 4 | 4 | 4 | 4 | 4 | Live Voice |
| 下行首帧 → WebAudio 出声（8/25 实测沿用） | 1009 | 1009 | 1009 | 1009 | 1009 | **Live Voice 配置** |

† tool 档"主模型之后"还含工具往返后的续写生成，无法与修订完全分开；但 2/5 轮修订撞 12s 超时
（`live_voice_spoken_revision_failed`）说明修订是主体。每轮模型调用次数：short 2、medium/long 3、
task 3（语义 + 委派校验 + 主模型）、tool 4。**修订 12s 超时命中：medium 1/5、tool 2/5、long 0/5
（p99 11.3s 贴着上限）→ 15 轮里 3 轮（20%）白等满 12s 后仍念原长答。**

（各段 p50 之和≠总 p50，量级一致即可。）

## 4. 哪些是 Live Voice 带来的（按 p50 归类，含浏览器尾巴）

| 档 | Live Voice 自有 | 模型 | Provider(STT+TTS) | 感知总计 |
|---|---:|---:|---:|---:|
| short | ≈4.7 s（**69%**）= VAD/EOT 2.07 + 语义 1.40 + 分派 0.17 + 尾巴 1.01 + 杂 0.1 | 1.2 s (17%) | 1.0 s (15%) | 6.9 s |
| medium | ≈12.0 s（**75%**）= 上述 + **修订 7.0** | 2.3 s | 1.2 s | 16.0 s |
| long | ≈14.0 s（**78%**）= 上述 + **修订 9.2** | 2.8 s | 1.1 s | 17.8 s |
| tool | ≈8.9 s（~77%）= 上述 + 修订/续写 4.2† | 1.5 s(+) | 1.1 s | 11.6 s |
| task | ≈6.0 s（**70%**）= VAD/EOT 2.01 + 语义+委派校验 2.71 + 分派 0.18 + 尾巴 1.01 | 1.5 s | 1.2 s | 8.5 s |

结论：**在新基线上，连最短的对话里 Live Voice 自有开销都占近七成**；一旦答案超过 200 字或用了
工具，口语修订单独再加 4–9 秒，占比升到四分之三以上。模型本身（首 token + 生成）在所有档里都只有
1.2–2.8 秒，Provider 约 1 秒。"主要是 Agent 慢"在这份数据里不成立。

## 5. 与 8/25 基线的对照

- 8/25 短对话"机器可测"4.83s（锚点 `provider_eot`）；本次 short 机器部分（EOT→下行首帧）≈ 3.8s + 语义
  1.4s ≈ 5.2s，再加真实 VAD/EOT 等待 2.07s → 说完→下行首帧 5.87s。**新增的每轮语义调用（≈1.4s）
  是唯一系统性增量**，其余段与 8/25 量级一致（STT 0.44 vs 0.42、TTS 0.59 vs 0.81、通知 44 vs 128）。
- 8/25 语料永远测不到的两块，本次坐实：**口语修订 7–9s p50（20% 撞 12s 上限）**、**任务轮委派校验使
  语义阶段 2.7s**。

## 6. 诚实边界

- 浏览器尾巴 1009ms 沿用 8/25 实测（`browserAudioIOAdapter.ts` 提前量 1.0s、下行建连代码未变），
  本次未在浏览器里复测；其余全部为本次实测。
- n=5，p99 即 max，只能看量级与形状，不做 SLO 声明。
- short 有 1 轮识别失败：`streaming recognition result authority is absent or stale`
  （`dedicated_media_registration.py:4209` 的 activation 保持/记录替换竞争），27 轮里 1 次，已补跑。
- task 档"第一声"是任务确认语，不是任务结果；任务本身在后台继续。
- 修订与主模型的切分依赖 `llm.log` 的 start 偏移（end 事件大量缺失），tool 档的"主模型之后"
  含工具续写，不能全记给修订。
- 原始数据在本地 `logs/lv-latency-baseline-20260903-204016/`（`rounds.jsonl`、`summary.final.json`、
  `split.final.json`），gitignored，不含音频与转写文本。

## 7. 数据支撑的优先级（替代此前的推算版）

1. **口语二次修订**：medium/long/tool 各省 **4–9s p50**，并消灭 20% 的 12s 白等。首答直接≤200 字、
   经核实；触发条件收窄；超时不得回退长答。难度中。
2. **每轮语义解析 1.4s（任务轮 2.7s）**：影响 100% 的轮次。精简输入/上下文准备；保留委派授权校验，
   不退回关键词。难度中。
3. **闭嘴→EOT 2.07s**：VAD 1200 只是其中一部分，Provider 端点检测另占 ~0.85s；VAD 调到 800 + 检测
   并行化合计约 −0.5~0.8s。难度中（换气语料回归）。
4. **浏览器尾巴 1.0s**：提前量 1000→250（实习生分支 `a953b7311` 已实现可配置版）约 −0.7s。难度低。
5. Provider（STT 0.45 + TTS 0.6）与模型（1.2–2.8s）：非管线问题，后置。

按 1–4 全做：short 6.9→≈4.0s，medium/long 16–18→≈6–7s，tool 11.6→≈5s，task 8.5→≈5s（p50 估算，
须复测）。

## 8. 复现

```
.venv/Scripts/python.exe -X utf8 scripts/live_voice/latency_baseline_driver.py --rounds 5 --scenarios short,medium,long,tool,task
.venv/Scripts/python.exe -X utf8 scripts/live_voice/latency_baseline_split.py --rounds <dir>/rounds.jsonl --llm-log <datadir>/logs/logs/llm.log --agent-log <datadir>/agent/.logs/agent_server.log
```
