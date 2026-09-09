# Demo repair deployment and measured results / 修复部署与测量结果

2026-09-09. **PARTIAL / 部分通过**. Implementation and controlled local deployment
are complete for the reviewed repairs. The integrated journey is not accepted:
successful business/audio operations coexist with transmission accumulation and
playback/recovery failures. No new physical hearing acceptance is claimed.

## Candidate and evidence / 版本与证据

- Deployed product: `9e9e5ebc5f78928fa206d66237635310e3c220b2`, branch
  `codex/demo-live-voice-20260909`, including executor repair `a4029b7c`.
- gpt-realtime-2.1, speed 1.25, minimal, server-vad-450; Python 3.11.15,
  websockets 15.0.1, installed AgentCore package
  `openjiuwen 0.1.16+jiuwenswarm.responses2` from the Demo venv, per user choice.
- Frontend rebuilt (4,658 modules); bundle `/assets/index-C1PkIc6X.js`. Formal
  startup speech/identity/receipt probes passed; runtime contract records the
  deployed source and validated routes/bundle. No remote update.
- Browser page: `http://127.0.0.1:5173/chat/web_1a0863c62b0_83f0a50d169c`;
  API/media are same-origin. The two owned isolated test browsers were stopped.
  These use injected speech and real Provider/Agent/Task, not a physical headset.
- Private evidence is under `logs/demo-20260909/`: `repair-browser-1/`,
  `repair-browser-2/`, `repair-profile-merged/profile.json` and
  `repair-profile-final/profile.html`; server log is
  `logs/swarm-20260909-145338.log`. The final combined report contains 25,012
  diagnostic records, 8,811 spans and 118 failure/cancel/fallback records. The
  last count is not a count of independent defects. Browser clocks are distinct.

## Journey outcomes / 实际流程结果

| Operation / 操作 | Observed outcome / 结果 |
|---|---|
| Ordinary Shenzhen question / 深圳普通问答 | Answer played. Injected punctuation split the input into two VAD turns; the first response was cancelled, the second is measured below. |
| Create Guangzhou itinerary / 创建广州行程 | Real Task `task-1d671a88fab14119bb750299e7a32015` executed and applied `秋日广州行程.md` (3,518 bytes). All 37 original files retained their hashes; this was rechecked after both browser runs. |
| Creation receipt / 创建回执 | Continuation obtained audio but did not reach observed playback; `PLAYOUT_BUFFER_WAIT_TIMEOUT` occurred at 12:57:02.830 UTC. Subsequent cleanup included capability rejection, RuntimeClosed and P2RouteNotFound records; these are retained, not treated as a clean recovery. |
| Query / 查询 | A refreshed context contained the real Task before binding; the query returned its running state. Initial query feedback took 4.216 s by the browser EOT metric. |
| Completion notice / 完成播报 | Browser render observed at 12:58:11.022 UTC; server recorded `presentation_acknowledged` for the exact Task at 12:58:16.326 UTC. This notice was delivered despite later connection failure. |
| Input saturation / 输入积压 | At 12:58:26.592 UTC, input backpressure closed media with the public transport-failure classification. The queue had reached approximately 15 s of age. Re-listen explicitly succeeded; stability is not closed. |
| Long answer and interruption / 长回答与打断 | Hangzhou answer played, spoken interruption stopped it, successor Shenzhen answer played and listening continued. This is a positive interruption sample, not proof of every failure/recovery sequence. |
| Second create and adjustment / 第二次创建与调整 | Connection failed/recovered during the follow-up creation attempt. No second Task was observed; the adjustment driver waited for its published context and did not send an adjustment. The synthetic input source also did not finish cleanly after capture shutdown, so this cannot count as a completed retry utterance. |

## A–H boundaries / 测量边界

| Boundary / 边界 | Measurement / 当前可观测内容 |
|---|---|
| A microphone; A→B capture / 麦克风至浏览器 | No physical final-phoneme observation in this digital-input run. Processed energy-tail timing is an estimate and can be affected by pauses/noise. |
| B continuous upload; B→C / 浏览器持续上传至 Gateway | Local send/receive/queue spans exist. Unsynchronized browser/server clocks do not establish one-way transit. |
| C Gateway→D Provider endpoint / 上行至 Provider 判停 | Gateway queue residence, offer/send lock, encoding, socket/drain and loop lag are recorded on sampled frames, joined by exact source event ID. Actual Provider frame receipt/internal processing remains unobserved. |
| D endpoint→request; D/E request→created / 判停至请求与创建确认 | Same Gateway clock intervals; the latter includes dispatch/transit/Provider acknowledgement, not pure compute. |
| E created→first audio / 创建确认至首音频返回 | Provider audio generation plus unseparated delivery/observation. It excludes processing already overlapping streaming input. |
| E/F admission and F downlink / 准入及下行 | First Provider audio→admission end→first Gateway frame, same server clock. |
| F→G transit; G scheduling/render / 下行至浏览器、排播与渲染 | One-way transit unknown; browser PCM acceptance, scheduling and playback-clock polling use one browser clock. Polling overshoot is not physical speaker latency. |
| H headphone sound / 耳机出声 | Unmeasured. Output timestamp is a device-clock estimate, not a microphone recording of the headphone. |

Some Gateway queue diagnostics use Windows `time.monotonic`, whose resolution
can be much coarser than the formatted decimal places. A recorded 0 ms does not
prove zero work. Decimal precision does not establish measurement accuracy.
Nested spans and cross-process intervals must not be added as a precise ledger.

## Per-response stages / 逐回答分段

Milliseconds / 单位 ms. `—` means unobserved or inapplicable, not zero. Generation
numbers refer to browser-1 and its exact response IDs in the merged profile.
The endpoint and all stages are observation boundaries, not acoustic endpoints.

| Operation / 操作 (gen) | D 判停→请求 / endpoint→sent | D/E 请求→创建 / sent→created | E 创建→首音 / created→audio | E/F 首音→准入 / audio→admission | F 准入→下行 / admission→frame | G PCM→排播 / schedule | G 排播→渲染观测 / render | Browser D→G EOT→render |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Shenzhen answer / 深圳回答 (2) | 16.581 | 144.998 | 522.483 | 10.535 | 49.988 | 51.0 | 33.5 | 811.0 |
| Create feedback / 创建即时反馈 (4) | 23.561 | 150.227 | 943.618 | 21.697 | 85.134 | 141.6 | 53.6 | 1388.3 |
| Create receipt, unplayed / 创建回执未播 (5) | — | 157.802 | 480.641 | 198.573 | 269.118 | — | — | — |
| Query feedback / 查询即时反馈 (6) | 139.035 | 2778.047 | 938.800 | 56.298 | 163.221 | 141.0 | 35.6 | 4215.8 |
| Query result / 查询结果 (7) | — | 5912.272 | 50.011 | 15.953 | 141.106 | 197.2 | 25.9 | — |
| Completion notice / 完成播报 (8) | — | — | — | — | — | 1659.9 | 52.2 | — |
| Hangzhou, interrupted / 杭州回答被打断 (9) | 18.824 | 215.968 | 732.255 | 10.659 | 79.468 | 140.9 | 36.9 | 1214.2 |
| Shenzhen after interrupt / 打断后深圳回答 (10) | 28.181 | 151.883 | 652.156 | 13.108 | 104.001 | 152.8 | 32.5 | 1093.0 |

The analyzer labels gen 8 `legacy_unknown`; the exact Task notification and
played-ACK evidence above establishes its business meaning. Do not reinterpret
missing Native stages as zero synthesis time. Cancelled gen 1/3 have no measured
first sound and are not silently included in successful response averages.

For gen 2, the browser measured EOT→PCM **726.5 ms**, then schedule **51.0 ms**
and render polling **33.5 ms**, totaling **811.0 ms** on one browser clock.
The processed-energy-tail→EOT estimate was **756.5 ms**, and EOT→output-device
estimate **852.379 ms**: together **1608.879 ms**. This is a software estimate,
not “the user's final sound to audible headphone response.” That distinction
explains why an EOT-only figure cannot be used as the complete physical delay.

中文结论：短问答本次可以很快，但查询和后续回执仍出现秒级等待；不能宣布
首音稳定降至 0.811 秒，也不能把 1.609 秒的软件估计称为耳机实测。

English: a short response was fast in this run, while query/continuation waits
remained multi-second. Neither stable 811 ms latency nor a physically measured
1.609 s user-end-to-headphone delay has been established.

## Task and notification spans / 后台任务与通知分段

Milliseconds, nested durations / 单位 ms，包含嵌套，父子不能重复相加。

| Operation/module / 操作与模块 | Duration ms |
|---|---:|
| Create arguments generated / 创建参数生成 | 1316.085 |
| Native business create / 创建业务调用总段 | 1285.641 |
| Create source wait / 创建来源等待 | 4.616 |
| Create task intent / 创建意图处理 | 541.596 |
| Confirmation issue / 签发确认 | 59.601 |
| Confirmation consume / 消费确认 | 293.326 |
| Formal create invoke / 正式创建调用 | 231.357 |
| Executor dispatch / 执行派发 | 5240.132 |
| Executor attempt / 执行尝试总段 | 45940.415 |
| Worktree create / 工作区创建 | 211.450 |
| Seed admitted bytes and index / 基线字节与索引同步 | 1869.556 |
| Acquire Agent / 获取 Agent | 19.750 |
| Agent stream / Agent 执行总段 | 34030.055 |
| Five model streams / 五轮模型流 | 3133.119; 3377.696; 12277.566; 4183.198; 4081.870 |
| list_files / 文件列表 | 108.160 |
| declare_file_effect_plan / 声明文件修改计划 | 595.377 |
| write_file / 写文件 | 103.049 |
| read_file / 读文件 | 140.514 |
| Artifact diff / 产物差异 | 464.415 |
| Artifact collect / 产物收集 | 93.716 |
| Prepare project effect / 准备项目变更 | 1175.624 |
| Settle effect / 变更落地 | 2745.429 |
| Cleanup / 清理 | 785.372 |
| Query arguments / 查询参数生成 | 473.185 |
| Native business query / 查询业务调用总段 | 2149.101 |
| Query source wait / 查询来源等待 | 0.544 |
| Query task intent / 查询意图处理 | 1166.917 |
| Formal query invoke / 正式查询调用 | 543.070 |
| Context-get arguments / 上下文读取参数生成 | 572.507 |
| Notification select / 通知选择 | 1.175 |
| Notification synthesis begin / 通知合成启动 | 333.342 |
| Notification synthesis first audio / 通知合成首音段 | 1136.540 |
| Notification synthesis produce / 通知音频生成总段 | 4281.179 |

Task creation receipt, Task execution, artifact application and notice playback
are distinct outcomes. Their wall-clock endpoints must not be substituted for
each other or summed from overlapping module spans.

## Transmission and host resources / 传输与主机资源

NODELAY is confirmed enabled on the deployed Native connection, but the real
journey still accumulated approximately 15 s of queued input. Send-lock and
encoding observations were small; blocked socket/drain and TCP retransmissions
were observed. This proves where backpressure manifests, not which host/router/
network/Provider component originally caused it.

An isolated 20/100/100/20 ms packetization comparison on the same observed peer
returned maximum queue ages of 59.877 / 3584.593 / 4353.010 / 233.272 ms. Larger
packets did not improve this comparison; no production batching change or peer
pin was made. Connection conditions vary, so NODELAY is not the sole root cause.

The user reports no proxy or VPN. After the user raised CPU/RAM pressure, a
read-only one-second host sampler accompanied a 45-second production-format
Realtime transport probe. Both use the same host performance counter for joins;
no microphone, Agent, Task or actual browser output was exercised in this probe.
Evidence: `repair-probes/host-host-correlated-1.json`,
`transport-host-correlated-1.json`, `host-correlated-1-summary.json`.

| Measurement / 测量项 | Observed / 本次结果 |
|---|---|
| CPU | Median 81.842%, maximum 100%; processor queue maximum 39 |
| Available physical memory / 可用内存 | 1656–2799 MB during this probe; earlier snapshot 1218 MB |
| Commit limit use / 提交内存占上限 | 49.277–54.248%; not an observed commit-limit exhaustion |
| Hard page input / 磁盘调入内存页 | Median 3284 pages/s; peak 48326 pages/s |
| Page output / 页面写出 | Usually zero, peak 27124 pages/s |
| Socket send wait / 单次发送等待 | Maximum 3377.477 ms |
| Queued audio age / 音频排队年龄 | Maximum 11269.702 ms; 1718 of 2250 source frames sent before probe stop |
| Probe event-loop lag / 事件循环停顿 | p95 11.439 ms, maximum 33.295 ms |
| TCP timeout episodes / TCP 超时次数 | First sample 1, last 68; retransmitted bytes increased by 253968 |

The longest socket wait overlapped page-out activity; another 2.570 s wait
overlapped approximately 100% CPU. This establishes coexistence, not causation.
Small event-loop pauses argue against a single multi-second Python scheduling
freeze, but cannot rule out host networking/driver/resource effects. Host CPU
and memory were not sampled during the original human failure, so this later
run cannot reconstruct that historical cause.

Hard-page-fault counters also include executable/mapped-file reads; they are
not by themselves proof of insufficient RAM or pagefile thrashing. Correlate
disk and commit pressure, as described by
[Microsoft's performance-counter guidance](https://learn.microsoft.com/en-us/troubleshoot/windows-client/performance/how-to-determine-the-appropriate-page-file-size-for-64-bit-versions-of-windows).

中文结论：本机资源压力是有效嫌疑，不能仅凭 TCP 重传宣称外网故障。
需要在同一网络、同一格式下补做低负载对照；未关闭用户应用或改变系统设置。

English: host resource pressure remains a credible contributor. TCP retransmission
alone does not locate the fault outside this computer. A controlled low-load
comparison is still required; user applications and system settings were preserved.

## Acceptance credit of this run / 本次证据可授予的验收范围

This run establishes the successful operations listed above. It does not close
sustained full-duplex transmission, a complete voice adjustment journey,
prepared continuation/playback-timeout recovery or physical first sound. Focused
checks cannot substitute for those missing product observations. No wired/USB
headphone calibration recording was supplied in this run; its measurement
protocol remains in [the timing runbook](../runbooks/TIMING_CALIBRATION.md).
The [current execution packet](../STATUS.md#current-execution-packet) owns ongoing
dependencies and remaining work; this record preserves the dated results only.
